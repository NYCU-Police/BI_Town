from collections import deque
from dataclasses import dataclass

from app.config import (
    GAME_MINUTES_PER_TICK,
    INITIAL_DAY,
    INITIAL_TIME,
    MAX_WORLD_EVENTS,
)
from app.models.schemas import Agent, Position, WorldEvent, WorldSnapshot, WorldState
from app.simulation.clock import advance_clock
from app.simulation.fake_agent import apply_schedule, move_agent
from app.simulation.poi import POIS


@dataclass(frozen=True)
class TickResult:
    events: list[WorldEvent]
    changed_agents: list[Agent]


def _agent_at_home(agent_id: str, name: str) -> Agent:
    home = POIS["home"]
    return Agent(
        id=agent_id,
        name=name,
        position=Position(x=home.x, y=home.y),
        location="home",
        target_location="home",
        state="idle",
    )


class World:
    """Server-authoritative in-memory world. tick() is synchronous and testable."""

    def __init__(self) -> None:
        self.day = INITIAL_DAY
        self.time = INITIAL_TIME
        self.agents: dict[str, Agent] = {
            "mina": _agent_at_home("mina", "Mina"),
            "alex": _agent_at_home("alex", "Alex"),
        }
        self.events: deque[WorldEvent] = deque(maxlen=MAX_WORLD_EVENTS)

    def add_event(self, event: WorldEvent) -> None:
        self.events.append(event)

    def recent_events(self) -> list[WorldEvent]:
        return list(self.events)

    def agent_list(self) -> list[Agent]:
        return list(self.agents.values())

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

    def tick(self) -> TickResult:
        action_time = self.time
        new_events: list[WorldEvent] = []
        changed_ids: set[str] = set()

        for agent in self.agents.values():
            before = (agent.state, agent.target_location)
            event = apply_schedule(agent, action_time)
            if event is not None:
                self.add_event(event)
                new_events.append(event)
            if (agent.state, agent.target_location) != before:
                changed_ids.add(agent.id)

        for agent in self.agents.values():
            before = (agent.state, agent.location, agent.position.x, agent.position.y)
            event = move_agent(agent, action_time)
            if event is not None:
                self.add_event(event)
                new_events.append(event)
            after = (agent.state, agent.location, agent.position.x, agent.position.y)
            if after != before:
                changed_ids.add(agent.id)

        self.day, self.time = advance_clock(
            self.day,
            self.time,
            GAME_MINUTES_PER_TICK,
        )
        changed_agents = [
            self.agents[agent_id]
            for agent_id in self.agents
            if agent_id in changed_ids
        ]
        return TickResult(events=new_events, changed_agents=changed_agents)
