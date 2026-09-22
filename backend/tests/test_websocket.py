from fastapi.testclient import TestClient

from app.config import INITIAL_DAY, INITIAL_TIME
from app.main import app

client = TestClient(app)


def test_websocket_connects_and_sends_snapshot() -> None:
    with client.websocket_connect("/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "world_snapshot"
        data = message["data"]
        assert data["day"] == INITIAL_DAY
        assert data["time"] == INITIAL_TIME
        assert {agent["id"] for agent in data["agents"]} == {"mina", "alex"}
        assert data["events"] == []
