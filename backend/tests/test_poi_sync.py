import re
from pathlib import Path

from app.simulation.poi import POIS

_GODOT = Path(__file__).resolve().parents[2] / "game" / "scripts" / "world.gd"
_VECTOR = re.compile(
    r'"([a-z_]+)"\s*:\s*Vector2\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)'
)


_NAME = re.compile(r'"([a-z_]+)"\s*:\s*"([^"]*)"')


def test_godot_place_names_match_poi() -> None:
    text = _GODOT.read_text(encoding="utf-8")
    block = text.split("const POI_NAMES := {", 1)[1].split("}", 1)[0]
    found = {match.group(1): match.group(2) for match in _NAME.finditer(block)}
    assert found == {poi_id: poi.name for poi_id, poi in POIS.items()}


def test_godot_place_ids_and_coordinates_match_poi() -> None:
    text = _GODOT.read_text(encoding="utf-8")
    block = text.split("const POIS := {", 1)[1].split("}", 1)[0]
    found = {
        match.group(1): (float(match.group(2)), float(match.group(3)))
        for match in _VECTOR.finditer(block)
    }
    assert set(found) == set(POIS)
    for poi_id, poi in POIS.items():
        assert found[poi_id] == (poi.x, poi.y)
