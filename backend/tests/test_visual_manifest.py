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


def test_manifest_matches_namespaced_content_ids() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == set(content_ids())
    for content_id, entry in manifest.items():
        namespace, _name = content_id.split(".", 1)
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


def test_pack_paths_are_only_in_visual_binder() -> None:
    offenders: list[str] = []
    for pattern in ("*.gd", "*.tscn"):
        for path in _GAME.rglob(pattern):
            if ".godot" in path.parts or path.name == "visual_binder.gd":
                continue
            text = path.read_text(encoding="utf-8")
            if "res://assets/packs/" in text or "res://assets/characters/" in text:
                offenders.append(str(path.relative_to(_ROOT)))
    assert offenders == []
