"""Skip the session frame, then the snapshot."""


def take_session(websocket: object) -> tuple[dict[str, object], dict[str, object]]:
    receive = websocket.receive_json  # type: ignore[attr-defined]
    session = receive()
    assert session["type"] == "session"
    token = session["player_token"]
    assert isinstance(token, str)
    assert len(token) == 43
    snapshot = receive()
    assert snapshot["type"] == "world_snapshot"
    return session, snapshot
