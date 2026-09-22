from fastapi.testclient import TestClient

from app import state
from app.config import (
    GAME_MINUTES_PER_TICK,
    INITIAL_DAY,
    INITIAL_TIME,
    SERVICE_NAME,
    VERSION,
)
from app.main import app
from app.simulation.clock import advance_clock

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": VERSION,
    }


def test_world() -> None:
    response = client.get("/api/world")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "day": INITIAL_DAY,
        "time": INITIAL_TIME,
        "agent_count": 2,
    }


def test_world_reflects_tick() -> None:
    state.world.tick()
    response = client.get("/api/world")
    assert response.status_code == 200
    expected_day, expected_time = advance_clock(
        INITIAL_DAY,
        INITIAL_TIME,
        GAME_MINUTES_PER_TICK,
    )
    body = response.json()
    assert body["day"] == expected_day
    assert body["time"] == expected_time
    assert body["agent_count"] == 2


def test_agents() -> None:
    response = client.get("/api/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 2
    assert {agent["id"] for agent in agents} == {"mina", "alex"}
    for agent in agents:
        assert set(agent.keys()) == {
            "id",
            "name",
            "position",
            "location",
            "target_location",
            "state",
        }
        assert set(agent["position"].keys()) == {"x", "y"}
        assert isinstance(agent["position"]["x"], (int, float))
        assert isinstance(agent["position"]["y"], (int, float))


def test_events_empty_at_start() -> None:
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json() == []


def test_events_reflect_simulation() -> None:
    state.world.tick()
    response = client.get("/api/events")
    assert response.status_code == 200
    events = response.json()
    assert events
    assert events[0] == {
        "timestamp": "08:00",
        "agent_id": "mina",
        "event": "left",
        "location": "home",
    }
