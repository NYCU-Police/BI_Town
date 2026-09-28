import os

import pytest

os.environ["BRAIN_MODE"] = "rules"

import app.config as config  # noqa: E402
from app.state import reset_world  # noqa: E402
from app.websocket.manager import manager  # noqa: E402

config.SIMULATION_LOOP_ENABLED = False


@pytest.fixture(autouse=True)
def fresh_world() -> None:
    reset_world()
    manager._connections.clear()
    manager.players.clear()
    manager.socket_by_token.clear()
    manager.token_by_socket.clear()
    manager.retired.clear()
