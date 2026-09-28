from collections import deque
from dataclasses import dataclass, field

from app.config import (
    BREAD_RESPAWN_MINUTES,
    BREAD_STOCK_MAX,
    EAT_FULLNESS_RESTORE,
    FOOD_ITEMS,
    GAME_MINUTES_PER_TICK,
    HUNGER_ACTION_THRESHOLD,
    INITIAL_DAY,
    INITIAL_TIME,
    MAX_WORLD_EVENTS,
    NEED_START_ENERGY,
    NEED_START_FULLNESS,
    NEED_START_SOCIAL,
    PARK_PRODUCT_ID,
    PARK_TOOL_ID,
    TOOL_IDS,
    current_brain_mode,
)
from app.models.schemas import (
    Agent,
    Intent,
    ItemStack,
    Needs,
    WorldEvent,
    WorldSnapshot,
    WorldState,
)
from app.simulation.clock import advance_clock
from app.simulation.fake_agent import apply_schedule, move_agent
from app.simulation.llm_session import Decider, LlmSession
from app.simulation.needs import (
    NeedValues,
    clamp_need,
    is_collapsed,
    round_need,
    tick_need_values,
)
from app.simulation.poi import POIS, home_for


@dataclass
class Body:
    hunger: float
    energy: float
    social: float
    items: dict[str, int] = field(default_factory=dict)
    tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class TickResult:
    events: list[WorldEvent]
    changed_agents: list[Agent]


@dataclass(frozen=True)
class IntentResult:
    ok: bool
    reason: str | None
    events: list[WorldEvent]
    changed_agents: list[Agent]


def _agent_at_home(agent_id: str, name: str) -> Agent:
    home = home_for(agent_id)
    return Agent(
        id=agent_id,
        name=name,
        position=home.position,
        location=home.id,
        target_location=home.id,
        state="idle",
    )


def _spawn_body() -> Body:
    return Body(
        hunger=NEED_START_FULLNESS,
        energy=NEED_START_ENERGY,
        social=NEED_START_SOCIAL,
    )


class World:
    """Server-authoritative in-memory world. tick() and apply_intent() are sync."""

    def __init__(
        self,
        brain_mode: str | None = None,
        decider: Decider | None = None,
    ) -> None:
        mode = current_brain_mode() if brain_mode is None else brain_mode
        if mode not in {"rules", "llm"}:
            mode = "rules"
        self.brain_mode = mode
        self.day = INITIAL_DAY
        self.time = INITIAL_TIME
        self.events: deque[WorldEvent] = deque(maxlen=MAX_WORLD_EVENTS)
        self.llm: LlmSession | None = None
        self.bodies: dict[str, Body] = {}
        self.bread_stock = BREAD_STOCK_MAX
        self._bread_elapsed = 0
        self._sent_needs: dict[str, tuple[int, int, int]] = {}
        if mode == "llm":
            self.llm = LlmSession(decider)
            self.agents = {
                resident.id: resident.as_agent() for resident in self.llm.residents
            }
        else:
            self.agents = {
                "mina": _agent_at_home("mina", "Mina"),
                "alex": _agent_at_home("alex", "Alex"),
            }
        for agent_id in self.agents:
            self.bodies[agent_id] = _spawn_body()
            self._sent_needs[agent_id] = self._rounded(agent_id)

    def add_event(self, event: WorldEvent) -> None:
        self.events.append(event)

    def recent_events(self) -> list[WorldEvent]:
        return list(self.events)

    def agent_list(self) -> list[Agent]:
        return [self._view(agent, include_needs=True) for agent in self.agents.values()]

    def to_world_state(self) -> WorldState:
        return WorldState(
            day=self.day,
            time=self.time,
            agent_count=len(self.agents),
        )

    def snapshot(self) -> WorldSnapshot:
        return WorldSnapshot(
            day=self.day,
            time=self.time,
            agents=self.agent_list(),
            events=self.recent_events(),
        )

    def add_player(self, player_id: str) -> Agent:
        spawn = POIS["plaza"]
        agent = Agent(
            id=player_id,
            name="玩家",
            position=spawn.position,
            location=spawn.id,
            target_location=spawn.id,
            state="idle",
        )
        self.agents[player_id] = agent
        self.bodies[player_id] = _spawn_body()
        self.bodies[player_id].tools = TOOL_IDS
        self._sent_needs[player_id] = self._rounded(player_id)
        return self._view(agent, include_needs=True)

    def remove_player(self, player_id: str) -> bool:
        if player_id not in self.agents:
            return False
        del self.agents[player_id]
        self.bodies.pop(player_id, None)
        self._sent_needs.pop(player_id, None)
        return True

    def tick(self) -> TickResult:
        self._respawn_bread()
        if self.llm is None:
            return self._tick_rules()
        return self._tick_llm()

    def apply_intent(self, player_id: str, intent: Intent) -> IntentResult:
        agent = self.agents.get(player_id)
        if agent is None or not player_id.startswith("player_"):
            return self._fail("no_player")
        action = intent.action
        if action == "move_to":
            return self._intent_move(agent, intent)
        if action == "pick_up":
            return self._intent_pick_up(agent, intent)
        if action == "eat":
            return self._intent_eat(agent, intent)
        if action == "give":
            return self._intent_give(agent, intent)
        if action == "use_tool":
            return self._intent_use_tool(agent, intent)
        return self._fail("bad_intent")

    def _tick_rules(self) -> TickResult:
        action_time = self.time
        new_events: list[WorldEvent] = []
        changed_ids: set[str] = set()

        for agent in self.agents.values():
            if agent.id.startswith("player_"):
                continue
            before = (
                agent.state,
                agent.target_location,
                self._item_count(agent.id, "bread"),
                self._hunger(agent.id),
            )
            event = self._decide_npc(agent, action_time)
            if event is not None:
                self.add_event(event)
                new_events.append(event)
            after = (
                agent.state,
                agent.target_location,
                self._item_count(agent.id, "bread"),
                self._hunger(agent.id),
            )
            if after != before:
                changed_ids.add(agent.id)

        for agent in self.agents.values():
            if self._collapsed(agent.id):
                if agent.state == "walking":
                    agent.state = "idle"
                    agent.target_location = agent.location
                    changed_ids.add(agent.id)
                continue
            before = (agent.state, agent.location, agent.position.x, agent.position.y)
            event = move_agent(agent, action_time)
            if event is not None:
                self.add_event(event)
                new_events.append(event)
            after = (agent.state, agent.location, agent.position.x, agent.position.y)
            if after != before:
                changed_ids.add(agent.id)

        for agent_id in self.agents:
            self._tick_body_needs(agent_id)
        self.day, self.time = advance_clock(
            self.day,
            self.time,
            GAME_MINUTES_PER_TICK,
        )
        return TickResult(
            events=new_events,
            changed_agents=self._pack(changed_ids),
        )

    def _tick_llm(self) -> TickResult:
        action_time = self.time
        assert self.llm is not None
        others = [
            (agent_id, agent.location)
            for agent_id, agent in self.agents.items()
            if agent_id not in self.llm.by_id
        ]
        kept = {
            agent_id: agent
            for agent_id, agent in self.agents.items()
            if agent_id not in self.llm.by_id
        }
        new_events, changed_ids = self.llm.advance(action_time, self.day, others)
        for event in new_events:
            self.add_event(event)
        self.agents = {
            resident.id: resident.as_agent() for resident in self.llm.residents
        }
        self.agents.update(kept)
        for agent in kept.values():
            if self._collapsed(agent.id):
                if agent.state == "walking":
                    agent.state = "idle"
                    agent.target_location = agent.location
                    changed_ids.add(agent.id)
                continue
            before = (agent.state, agent.location, agent.position.x, agent.position.y)
            event = move_agent(agent, action_time)
            if event is not None:
                self.add_event(event)
                new_events.append(event)
            after = (agent.state, agent.location, agent.position.x, agent.position.y)
            if after != before:
                changed_ids.add(agent.id)
            self._tick_body_needs(agent.id)
        self.day, self.time = advance_clock(
            self.day,
            self.time,
            GAME_MINUTES_PER_TICK,
        )
        return TickResult(
            events=new_events,
            changed_agents=self._pack(changed_ids),
        )

    def _decide_npc(self, agent: Agent, time: str) -> WorldEvent | None:
        if self._collapsed(agent.id):
            if agent.state == "walking":
                agent.state = "idle"
                agent.target_location = agent.location
            return None
        if (
            self._item_count(agent.id, "bread") > 0
            and self._hunger(agent.id) < HUNGER_ACTION_THRESHOLD
        ):
            return self._consume_food(agent, time)
        if self._hunger(agent.id) < HUNGER_ACTION_THRESHOLD:
            if agent.location == "cafe" and agent.state != "walking":
                return None
            return self._depart(agent, "cafe", time)
        return apply_schedule(agent, time)

    def _depart(self, agent: Agent, dest: str, time: str) -> WorldEvent | None:
        if dest not in POIS:
            return None
        if agent.state != "walking" and agent.location == dest:
            return None
        if agent.state == "walking" and agent.target_location == dest:
            return None
        event: WorldEvent | None = None
        if agent.state != "walking":
            event = WorldEvent(
                timestamp=time,
                agent_id=agent.id,
                event="left",
                location=agent.location,
            )
        agent.target_location = dest
        agent.state = "walking"
        return event

    def _consume_food(self, agent: Agent, time: str) -> WorldEvent:
        self._add_item(agent.id, "bread", -1)
        self._set_hunger(agent.id, self._hunger(agent.id) + EAT_FULLNESS_RESTORE)
        if agent.state == "walking":
            agent.state = "idle"
            agent.target_location = agent.location
        return WorldEvent(
            timestamp=time,
            agent_id=agent.id,
            event="ate",
            location=agent.location,
            item="bread",
        )

    def _intent_move(self, agent: Agent, intent: Intent) -> IntentResult:
        target = intent.target
        if target is None or target.type != "poi":
            return self._fail("bad_intent")
        if target.id not in POIS:
            return self._fail("unknown_place")
        if agent.state != "walking" and agent.location == target.id:
            return self._ok([], set())
        event = self._depart(agent, target.id, self.time)
        events = [event] if event is not None else []
        for item in events:
            self.add_event(item)
        return self._ok(events, {agent.id})

    def _intent_pick_up(self, agent: Agent, intent: Intent) -> IntentResult:
        target = intent.target
        if target is None or target.type != "poi" or not intent.item:
            return self._fail("bad_intent")
        if not self._present(agent, target.id):
            return self._fail("not_here")
        if target.id != "cafe" or intent.item != "bread":
            return self._fail("nothing_here")
        if self.bread_stock < 1:
            return self._fail("nothing_here")
        self.bread_stock -= 1
        self._add_item(agent.id, "bread", 1)
        event = WorldEvent(
            timestamp=self.time,
            agent_id=agent.id,
            event="picked_up",
            location=agent.location,
            item="bread",
        )
        self.add_event(event)
        return self._ok([event], {agent.id})

    def _intent_eat(self, agent: Agent, intent: Intent) -> IntentResult:
        item = intent.item
        if not item:
            return self._fail("bad_intent")
        if item not in FOOD_ITEMS:
            return self._fail("not_food")
        if self._item_count(agent.id, item) < 1:
            return self._fail("not_holding")
        event = self._consume_food(agent, self.time)
        self.add_event(event)
        return self._ok([event], {agent.id})

    def _intent_give(self, agent: Agent, intent: Intent) -> IntentResult:
        target = intent.target
        item = intent.item
        if target is None or target.type != "agent" or not item:
            return self._fail("bad_intent")
        other = self.agents.get(target.id)
        if other is None or other.id == agent.id:
            return self._fail("unknown_agent")
        if not self._same_place(agent, other):
            return self._fail("not_here")
        if self._item_count(agent.id, item) < 1:
            return self._fail("not_holding")
        self._add_item(agent.id, item, -1)
        self._add_item(other.id, item, 1)
        gave = WorldEvent(
            timestamp=self.time,
            agent_id=agent.id,
            event="gave",
            location=agent.location,
            target_agent_id=other.id,
            item=item,
        )
        self.add_event(gave)
        events = [gave]
        changed = {agent.id, other.id}
        if not other.id.startswith("player_") and self.llm is None:
            eaten = self._decide_npc(other, self.time)
            if eaten is not None:
                self.add_event(eaten)
                events.append(eaten)
        return self._ok(events, changed)

    def _intent_use_tool(self, agent: Agent, intent: Intent) -> IntentResult:
        target = intent.target
        tool = intent.item
        if target is None or target.type != "poi" or not tool:
            return self._fail("bad_intent")
        if tool not in self.bodies[agent.id].tools:
            return self._fail("unknown_tool")
        if not self._present(agent, target.id):
            return self._fail("not_here")
        if tool == PARK_TOOL_ID and target.id == "park":
            self._add_item(agent.id, PARK_PRODUCT_ID, 1)
            event = WorldEvent(
                timestamp=self.time,
                agent_id=agent.id,
                event="produced",
                location=agent.location,
                item=PARK_PRODUCT_ID,
            )
            self.add_event(event)
            return self._ok([event], {agent.id})
        return self._fail("wrong_place")

    def _present(self, agent: Agent, poi_id: str) -> bool:
        return agent.state != "walking" and agent.location == poi_id

    def _same_place(self, left: Agent, right: Agent) -> bool:
        return (
            left.state != "walking"
            and right.state != "walking"
            and left.location == right.location
        )

    def _fail(self, reason: str) -> IntentResult:
        return IntentResult(ok=False, reason=reason, events=[], changed_agents=[])

    def _ok(self, events: list[WorldEvent], changed_ids: set[str]) -> IntentResult:
        return IntentResult(
            ok=True,
            reason=None,
            events=events,
            changed_agents=self._pack(changed_ids),
        )

    def _respawn_bread(self) -> None:
        self._bread_elapsed += GAME_MINUTES_PER_TICK
        while self._bread_elapsed >= BREAD_RESPAWN_MINUTES:
            self._bread_elapsed -= BREAD_RESPAWN_MINUTES
            if self.bread_stock < BREAD_STOCK_MAX:
                self.bread_stock += 1

    def _company(self, agent_id: str) -> bool:
        agent = self.agents[agent_id]
        return any(
            other_id != agent_id and other.location == agent.location
            for other_id, other in self.agents.items()
        )

    def _tick_body_needs(self, agent_id: str) -> None:
        if self.llm is not None and agent_id in self.llm.by_id:
            return
        body = self.bodies[agent_id]
        agent = self.agents[agent_id]
        values = NeedValues(body.hunger, body.energy, body.social)
        tick_need_values(
            values,
            location=agent.location,
            state=agent.state,
            company=self._company(agent_id),
            asleep=False,
            resting=False,
        )
        body.hunger = values.hunger
        body.energy = values.energy
        body.social = values.social

    def _hunger(self, agent_id: str) -> float:
        if self.llm is not None and agent_id in self.llm.by_id:
            return self.llm.by_id[agent_id].fullness
        return self.bodies[agent_id].hunger

    def _energy(self, agent_id: str) -> float:
        if self.llm is not None and agent_id in self.llm.by_id:
            return self.llm.by_id[agent_id].energy
        return self.bodies[agent_id].energy

    def _social(self, agent_id: str) -> float:
        if self.llm is not None and agent_id in self.llm.by_id:
            return self.llm.by_id[agent_id].social
        return self.bodies[agent_id].social

    def _set_hunger(self, agent_id: str, value: float) -> None:
        value = clamp_need(value)
        if self.llm is not None and agent_id in self.llm.by_id:
            self.llm.by_id[agent_id].fullness = value
            return
        self.bodies[agent_id].hunger = value

    def _collapsed(self, agent_id: str) -> bool:
        return is_collapsed(self._hunger(agent_id), self._energy(agent_id))

    def _item_count(self, agent_id: str, item_id: str) -> int:
        return self.bodies[agent_id].items.get(item_id, 0)

    def _add_item(self, agent_id: str, item_id: str, delta: int) -> None:
        body = self.bodies[agent_id]
        count = body.items.get(item_id, 0) + delta
        if count <= 0:
            body.items.pop(item_id, None)
            return
        body.items[item_id] = count

    def _rounded(self, agent_id: str) -> tuple[int, int, int]:
        return (
            round_need(self._hunger(agent_id)),
            round_need(self._energy(agent_id)),
            round_need(self._social(agent_id)),
        )

    def _pack(self, changed_ids: set[str]) -> list[Agent]:
        packed: list[Agent] = []
        for agent_id, agent in self.agents.items():
            rounded = self._rounded(agent_id)
            needs_changed = self._sent_needs.get(agent_id) != rounded
            if agent_id not in changed_ids and not needs_changed:
                continue
            if needs_changed:
                self._sent_needs[agent_id] = rounded
            packed.append(self._view(agent, include_needs=needs_changed))
        return packed

    def _view(self, agent: Agent, *, include_needs: bool) -> Agent:
        copy = agent.model_copy(deep=True)
        if include_needs:
            hunger, energy, social = self._rounded(agent.id)
            copy.needs = Needs(hunger=hunger, energy=energy, social=social)
        else:
            copy.needs = None
        body = self.bodies[agent.id]
        copy.items = [
            ItemStack(id=item_id, count=count)
            for item_id, count in sorted(body.items.items())
            if count > 0
        ]
        copy.tools = list(body.tools)
        copy.collapsed = self._collapsed(agent.id)
        return copy
