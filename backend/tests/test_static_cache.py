from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main

SHELL_FILES = (
    "index.html",
    "index.js",
    "index.wasm",
    "index.pck",
    "build_info.json",
)


@pytest.fixture
def godot_web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in SHELL_FILES:
        (tmp_path / name).write_bytes(b"v1-" + name.encode())
    (tmp_path / "other.txt").write_bytes(b"leave-me")
    monkeypatch.setattr(main, "STATIC_WEB_DIR", str(tmp_path))
    main._mount_godot_web(main.app)
    yield TestClient(main.app)
    main.app.router.routes[:] = [
        route
        for route in main.app.router.routes
        if getattr(route, "name", None) != "godot_web"
    ]


def test_godot_shell_revalidates_with_etag(godot_web: TestClient) -> None:
    for name in SHELL_FILES:
        response = godot_web.get(f"/{name}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        etag = response.headers["etag"]
        assert etag
        again = godot_web.get(f"/{name}", headers={"If-None-Match": etag})
        assert again.status_code == 304
        assert again.headers["etag"] == etag
        assert again.headers["cache-control"] == "no-cache"

    root = godot_web.get("/")
    assert root.status_code == 200
    assert root.headers["cache-control"] == "no-cache"
    assert root.content == b"v1-index.html"
    root_again = godot_web.get("/", headers={"If-None-Match": root.headers["etag"]})
    assert root_again.status_code == 304


def test_other_static_files_are_not_forced_to_revalidate(godot_web: TestClient) -> None:
    response = godot_web.get("/other.txt")
    assert response.status_code == 200
    assert response.headers.get("cache-control") != "no-cache"


def test_shell_paths() -> None:
    assert main.cache_control_for_godot_shell("/index.wasm") == "no-cache"
    assert main.cache_control_for_godot_shell("/") == "no-cache"
    assert main.cache_control_for_godot_shell("/api/health") is None
    assert main.cache_control_for_godot_shell("/other.txt") is None
