"""Player intents, item sources, and the hunger decision order."""

import pytest
from fastapi.testclient import TestClient

from app import config, state
from app.config import (
    BREAD_RESPAWN_MINUTES,
    BREAD_STOCK_MAX,
    CAFE_HUNGER_RESTORE_PER_MINUTE,
    EAT_FULLNESS_RESTORE,
    HUNGER_ACTION_THRESHOLD,
    SOCIAL_COMPANY_PER_MINUTE,
    SOCIAL_DECAY_PER_MINUTE,
)
from app.main import app
from app.models.schemas import Intent, TargetRef
from app.simulation.llm_session import Decision, DecisionJob, ReadyDecision
from app.simulation.poi import POIS
from app.simulation.world import World

client = TestClient(app)


def _move(poi_id: str) -> Intent:
    return Intent(action="move_to", target=TargetRef(type="poi", id=poi_id))


def _at(world: World, agent_id: str, poi_id: str) -> None:
    agent = world.agents[agent_id]
    place = POIS[poi_id]
    agent.location = poi_id
    agent.target_location = poi_id
    agent.position = place.position
    agent.state = "idle"


def test_connection_adds_and_removes_a_player() -> None:
    with client.websocket_connect("/ws") as watcher:
        first = watcher.receive_json()
        you = first["data"]["you"]
        assert you.startswith("player_")
        assert you in {agent["id"] for agent in first["data"]["agents"]}
        with client.websocket_connect("/ws") as other:
            other_snap = other.receive_json()
            other_id = other_snap["data"]["you"]
            joined = watcher.receive_json()
            assert joined["type"] == "agent_update"
            assert {agent["id"] for agent in joined["data"]["agents"]} == {other_id}
        left = watcher.receive_json()
        assert left["data"]["removed"] == [other_id]
        assert other_id not in state.world.agents
    assert you not in state.world.agents
    assert all(not agent_id.startswith("player_") for agent_id in state.world.agents)


def test_intent_result_and_same_place_rules() -> None:
    with client.websocket_connect("/ws") as websocket:
        snapshot = websocket.receive_json()
        player_id = snapshot["data"]["you"]
        websocket.send_json(
            {
                "type": "intent",
                "client_seq": 1,
                "intent": {
                    "action": "pick_up",
                    "target": {"type": "poi", "id": "cafe"},
                    "item": "bread",
                },
            }
        )
        denied = websocket.receive_json()
        assert denied == {
            "type": "intent_result",
            "client_seq": 1,
            "ok": False,
            "reason": "not_here",
        }
        websocket.send_json(
            {
                "type": "intent",
                "client_seq": 2,
                "intent": {
                    "action": "pick_up",
                    "target": {"type": "tile", "id": "3,4"},
                    "item": "bread",
                },
            }
        )
        tiled = websocket.receive_json()
        assert tiled["ok"] is False
        assert tiled["reason"] == "unsupported_target"
        assert tiled["client_seq"] == 2
        assert player_id in state.world.agents


def test_rate_limit_and_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "INTENT_RATE_LIMIT_PER_SEC", 1)
    monkeypatch.setattr(config, "INTENT_MAX_BYTES", 160)
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "intent",
                "client_seq": 1,
                "intent": {"action": "eat", "item": "bread"},
            }
        )
        first = websocket.receive_json()
        assert first["type"] == "intent_result"
        assert first["client_seq"] == 1
        websocket.send_json(
            {
                "type": "intent",
                "client_seq": 2,
                "intent": {"action": "eat", "item": "bread"},
            }
        )
        limited = websocket.receive_json()
        assert limited["ok"] is False
        assert limited["reason"] == "rate_limited"
        assert limited["client_seq"] == 2
        websocket.send_json(
            {
                "type": "intent",
                "client_seq": 3,
                "intent": {"action": "eat", "item": "x" * 400},
            }
        )
        oversized = websocket.receive_json()
        assert oversized["reason"] == "too_large"
        assert oversized["client_seq"] == 0


def test_hunger_beats_schedule_and_collapse_blocks_movement() -> None:
    world = World()
    world.time = "09:00"
    world.bodies["mina"].hunger = 10
    world.tick()
    mina = world.agents["mina"]
    assert mina.target_location == "cafe"
    assert mina.state == "walking"
    assert mina.target_location != "office"

    stayed = World()
    stayed.bodies["mina"].energy = 0
    stayed.tick()
    assert stayed.agents["mina"].state == "idle"
    assert stayed.agents["mina"].location == "mina_home"


def test_cafe_restores_hunger_home_restores_energy_and_social_follows_company() -> None:
    world = World()
    _at(world, "mina", "cafe")
    _at(world, "alex", "cafe")
    world.bodies["mina"].hunger = 40
    world.bodies["mina"].social = 40
    world.bodies["alex"].social = 40
    world.time = "10:00"
    world.tick()
    assert world.bodies["mina"].hunger == pytest.approx(
        40 + CAFE_HUNGER_RESTORE_PER_MINUTE
    )
    assert world.bodies["mina"].social == pytest.approx(40 + SOCIAL_COMPANY_PER_MINUTE)

    alone = World()
    social = alone.bodies["alex"].social
    alone.time = "10:00"
    alone.tick()
    assert alone.bodies["alex"].social == pytest.approx(
        social - SOCIAL_DECAY_PER_MINUTE
    )
    assert alone.bodies["alex"].energy > config.NEED_START_ENERGY


def test_bread_respawns_up_to_the_cap_and_park_tool_makes_wood() -> None:
    world = World()
    assert world.bread_stock == BREAD_STOCK_MAX
    world.bread_stock = BREAD_STOCK_MAX - 1
    for _ in range(BREAD_RESPAWN_MINUTES):
        world.tick()
    assert world.bread_stock == BREAD_STOCK_MAX
    world.tick()
    assert world.bread_stock == BREAD_STOCK_MAX

    player = "player_wood"
    world.add_player(player)
    _at(world, player, "park")
    made = world.apply_intent(
        player,
        Intent(
            action="use_tool",
            target=TargetRef(type="poi", id="park"),
            item="watering_can",
        ),
    )
    assert made.ok
    assert world.bodies[player].items["wood"] == 1
    assert made.events[0].event == "produced"
    _at(world, player, "cafe")
    wrong = world.apply_intent(
        player,
        Intent(
            action="use_tool",
            target=TargetRef(type="poi", id="cafe"),
            item="watering_can",
        ),
    )
    assert wrong.ok is False
    assert wrong.reason == "wrong_place"


def test_needs_are_integers_and_omitted_until_they_change() -> None:
    world = World()
    result = world.tick()
    mina = next(agent for agent in result.changed_agents if agent.id == "mina")
    assert mina.needs is None
    assert all(agent.id != "alex" for agent in result.changed_agents)

    world.bodies["alex"].energy = 10.4
    world._sent_needs["alex"] = (
        world._sent_needs["alex"][0],
        10,
        world._sent_needs["alex"][2],
    )
    world.time = "10:00"
    result = world.tick()
    alex = next(agent for agent in result.changed_agents if agent.id == "alex")
    assert alex.needs is not None
    assert alex.needs.energy == 11
    assert isinstance(alex.needs.hunger, int)


def test_player_feeds_mina() -> None:
    world = World()
    player_id = "player_e2e"
    world.add_player(player_id)
    moved = world.apply_intent(player_id, _move("cafe"))
    assert moved.ok
    assert world.agents[player_id].state == "walking"
    for _ in range(12):
        if (
            world.agents[player_id].state == "idle"
            and world.agents[player_id].location == "cafe"
        ):
            break
        world.tick()
    assert world.agents[player_id].location == "cafe"
    assert world.agents[player_id].state == "idle"

    picked = world.apply_intent(
        player_id,
        Intent(
            action="pick_up",
            target=TargetRef(type="poi", id="cafe"),
            item="bread",
        ),
    )
    assert picked.ok
    ate = world.apply_intent(player_id, Intent(action="eat", item="bread"))
    assert ate.ok
    assert ate.events[0].event == "ate"
    again = world.apply_intent(
        player_id,
        Intent(
            action="pick_up",
            target=TargetRef(type="poi", id="cafe"),
            item="bread",
        ),
    )
    assert again.ok
    assert world.bodies[player_id].items["bread"] == 1

    _at(world, "mina", "cafe")
    world.bodies["mina"].hunger = HUNGER_ACTION_THRESHOLD - 1
    before = world.bodies["mina"].hunger
    gave = world.apply_intent(
        player_id,
        Intent(
            action="give",
            target=TargetRef(type="agent", id="mina"),
            item="bread",
        ),
    )
    assert gave.ok
    kinds = [event.event for event in gave.events]
    assert kinds == ["gave", "ate"]
    assert gave.events[1].agent_id == "mina"
    assert gave.events[1].item == "bread"
    assert world.bodies["mina"].hunger == pytest.approx(before + EAT_FULLNESS_RESTORE)
    assert world.bodies["mina"].hunger > before


def test_collapse_overrides_llm_movement() -> None:
    async def _stay(_messages: list, _schema: dict) -> str:
        return '{"action":"stay","target":"","say":"","thought":""}'

    world = World(brain_mode="llm", decider=_stay)
    assert world.llm is not None
    world.llm.opening = False
    mina = world.llm.by_id["mina"]
    mina.energy = 0
    world.llm.inbox.append(
        ReadyDecision(
            job=DecisionJob(agent_id="mina", messages=[]),
            decision=Decision(action="move_to", target="cafe"),
        )
    )
    world.tick()
    assert mina.state != "walking"
    assert mina.location == "mina_home"
    assert mina.energy > 0
