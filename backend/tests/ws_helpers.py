"""Skip session and game_config, then read the snapshot."""


def take_session(websocket: object) -> tuple[dict[str, object], dict[str, object]]:
    receive = websocket.receive_json  # type: ignore[attr-defined]
    session = receive()
    assert session["type"] == "session"
    token = session["player_token"]
    assert isinstance(token, str)
    assert len(token) == 43
    game_config = receive()
    assert game_config["type"] == "game_config"
    snapshot = receive()
    assert snapshot["type"] == "world_snapshot"
    return session, snapshot
