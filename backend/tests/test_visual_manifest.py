"""Manifest keys are the namespaced content ids, and packs stay behind the binder."""

import json
from pathlib import Path

from app.simulation.content import content_ids

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "game" / "data" / "visual_manifest.json"
_GAME = _ROOT / "game"
_CATEGORY = {
    "poi": "poi",
    "agent": "actors",
    "item": "items",
    "tool": "tools",
    "fx": "fx",
}
_SHEET_ANIMS = {
    "idle_down": [[0, 0]],
    "idle_up": [[1, 0]],
    "idle_left": [[2, 0]],
    "idle_right": [[3, 0]],
    "walk_down": [[0, 0], [0, 1], [0, 2], [0, 3]],
    "walk_up": [[1, 0], [1, 1], [1, 2], [1, 3]],
    "walk_left": [[2, 0], [2, 1], [2, 2], [2, 3]],
    "walk_right": [[3, 0], [3, 1], [3, 2], [3, 3]],
}


def test_manifest_matches_namespaced_content_ids() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == set(content_ids())
    for content_id, entry in manifest.items():
        namespace, _name = content_id.split(".", 1)
        if namespace == "poi":
            assert entry["kind"] == "none"
        elif namespace == "agent":
            assert entry["kind"] == "spritesheet"
            assert entry["frame_size"] == [16, 16]
            assert entry["anims"] == _SHEET_ANIMS
        elif namespace == "fx":
            assert entry["kind"] == "sprite"
            assert str(entry["file"]).endswith(".png")
        else:
            assert entry["kind"] == "sprite"
        assert entry["category"] == _CATEGORY[namespace]
        assert entry["footprint"] == [16, 16] or entry["footprint"] == [32, 32]
        assert entry["origin"] == [0.5, 1.0]
        assert str(entry["placeholder_color"]).startswith("#")
        assert "x" not in entry
        assert "y" not in entry
        assert "art" not in entry
        if namespace == "agent":
            assert str(entry["name_color"]).startswith("#")
    poi_colors = {
        str(entry["placeholder_color"]).lower()
        for content_id, entry in manifest.items()
        if content_id.startswith("poi.")
    }
    assert len(poi_colors) == 9
    player = manifest["agent.player"]
    assert str(player["placeholder_color"]).lower() not in poi_colors
    assert str(player["name_color"]).lower() not in poi_colors
    assert manifest["fx.hungry"]["file"] == "emote19.png"
    assert manifest["fx.collapsed"]["file"] == "emote28.png"
    assert manifest["fx.chat"]["file"] == "emote20.png"


def test_pack_paths_are_only_in_visual_binder() -> None:
    offenders: list[str] = []
    for pattern in ("*.gd", "*.tscn"):
        for path in _GAME.rglob(pattern):
            if ".godot" in path.parts or path.name in {
                "visual_binder.gd",
                "town_map.gd",
                "hud.gd",
                "game_audio.gd",
            }:
                continue
            text = path.read_text(encoding="utf-8")
            if "res://assets/packs/" in text or "res://assets/characters/" in text:
                offenders.append(str(path.relative_to(_ROOT)))
    assert offenders == []
