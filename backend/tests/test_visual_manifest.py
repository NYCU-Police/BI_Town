"""Every backend content id resolves through the Godot manifest."""

import json
import re
from pathlib import Path

from app.simulation.content import content_ids
from app.simulation.poi import POIS

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "game" / "data" / "visual_manifest.json"
_WORLD = _ROOT / "game" / "scripts" / "world.gd"
_VECTOR = re.compile(
    r'"([a-z_]+)"\s*:\s*Vector2\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)'
)


def test_manifest_resolves_content_and_matches_poi_coordinates() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    content = manifest["content"]
    assert set(content) == set(content_ids())

    script = _WORLD.read_text(encoding="utf-8")
    block = script.split("const POIS := {", 1)[1].split("}", 1)[0]
    godot = {
        match.group(1): (float(match.group(2)), float(match.group(3)))
        for match in _VECTOR.finditer(block)
    }

    for content_id, entry in content.items():
        art = str(entry.get("art", ""))
        if art:
            relative = art.removeprefix("res://")
            assert (_ROOT / "game" / relative).is_file(), content_id
        if content_id not in POIS:
            continue
        poi = POIS[content_id]
        assert (float(entry["x"]), float(entry["y"])) == (poi.x, poi.y)
        assert godot[content_id] == (poi.x, poi.y)
