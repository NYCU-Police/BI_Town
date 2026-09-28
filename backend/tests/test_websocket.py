from fastapi.testclient import TestClient
from tests.ws_helpers import take_session

from app import state
from app.config import INITIAL_DAY, INITIAL_TIME
from app.main import app
from app.simulation.player_talk import Dossier

client = TestClient(app)


def test_websocket_connects_and_sends_snapshot() -> None:
    with client.websocket_connect("/ws") as websocket:
        _session, message = take_session(websocket)
        data = message["data"]
        assert data["day"] == INITIAL_DAY
        assert data["time"] == INITIAL_TIME
        ids = {agent["id"] for agent in data["agents"]}
        assert {"mina", "alex"} < ids
        player_ids = {agent_id for agent_id in ids if agent_id.startswith("player_")}
        assert player_ids == {data["you"]}
        assert data["events"] == []


def test_unknown_token_is_replaced() -> None:
    with client.websocket_connect("/ws?player_token=not-a-real-token") as websocket:
        session, _snapshot = take_session(websocket)
        assert session["player_token"] != "not-a-real-token"


def test_known_token_keeps_the_dossier() -> None:
    with client.websocket_connect("/ws") as first:
        session, _snapshot = take_session(first)
        token = str(session["player_token"])
        dossier = state.world.dossiers[token]
        assert isinstance(dossier, Dossier)
        dossier.memory["mina"] = [("player", "還在")]
        with client.websocket_connect(f"/ws?player_token={token}") as second:
            again, snap = take_session(second)
            assert again["player_token"] == token
            kept = state.world.dossiers[token]
            assert isinstance(kept, Dossier)
            assert kept.memory["mina"] == [("player", "還在")]
            assert snap["data"]["you"] != _snapshot["data"]["you"]
