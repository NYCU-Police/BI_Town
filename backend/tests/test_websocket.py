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
        ids = {agent["id"] for agent in data["agents"]}
        assert {"mina", "alex"} < ids
        player_ids = {agent_id for agent_id in ids if agent_id.startswith("player_")}
        assert player_ids == {data["you"]}
        assert data["events"] == []
