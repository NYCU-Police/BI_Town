from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.simulation.game_config import build_game_config
from app.simulation.poi import POIS

client = TestClient(app)

_SCRIPTS = Path(__file__).resolve().parents[2] / "game" / "scripts"
_WORLD_SCENE = Path(__file__).resolve().parents[2] / "game" / "scenes" / "world.tscn"
_FORBIDDEN = (
    "const POIS",
    "const BY_ID",
    "_LOW_NEED",
    "_HUNGRY_BELOW",
    "_EAT_HUNGER",
    "麵包",
    "木材",
    "澆水壺",
)


def test_game_config_matches_poi_and_config() -> None:
    payload = build_game_config().model_dump()
    assert payload["version"] == 1
    assert config.GAME_CONFIG_VERSION == 1
    assert "residents" not in payload
    assert payload["poi_pick_radius"] == config.POI_PICK_RADIUS
    assert payload["agent_pick_radius"] == config.AGENT_PICK_RADIUS
    assert config.NEED_HUNGRY == int(config.NEED_HUNGRY)
    assert config.EAT_FULLNESS_RESTORE == int(config.EAT_FULLNESS_RESTORE)
    assert payload["need_low"] == int(config.NEED_HUNGRY)
    assert payload["eat_restore"] == int(config.EAT_FULLNESS_RESTORE)
    assert {
        poi["id"]: (poi["name"], poi["x"], poi["y"]) for poi in payload["pois"]
    } == {poi_id: (poi.name, poi.x, poi.y) for poi_id, poi in POIS.items()}
    assert [(item["id"], item["name"], item["food"]) for item in payload["items"]] == [
        (item_id, name, item_id in config.FOOD_ITEMS)
        for item_id, name in config.ITEM_DISPLAY
    ]


def test_each_connection_sends_game_config_before_the_snapshot() -> None:
    with client.websocket_connect("/ws") as first:
        session = first.receive_json()
        first_config = first.receive_json()
        first_snapshot = first.receive_json()
        token = session["player_token"]
    assert first_config["type"] == "game_config"
    assert first_snapshot["type"] == "world_snapshot"
    assert first_config["data"]["version"] == 1
    assert "residents" not in first_config["data"]
    assert {poi["id"] for poi in first_config["data"]["pois"]} == set(POIS)

    with client.websocket_connect(f"/ws?player_token={token}") as second:
        second.receive_json()
        second_config = second.receive_json()
        second_snapshot = second.receive_json()
    assert second_config == first_config
    assert second_snapshot["type"] == "world_snapshot"


def test_client_scripts_do_not_hardcode_config_copy() -> None:
    offenders: list[str] = []
    place_names = [poi.name for poi in POIS.values()]
    for path in sorted(_SCRIPTS.glob("*.gd")):
        text = path.read_text(encoding="utf-8")
        for token in (*_FORBIDDEN, *place_names):
            if token in text:
                offenders.append(f"{path.name}: {token}")
    scene = _WORLD_SCENE.read_text(encoding="utf-8")
    for poi_id in POIS:
        marker = f'[node name="{poi_id}"'
        if marker in scene:
            offenders.append(f"world.tscn: {marker}")
    assert offenders == []
