import pytest

import app.config as config
from app.state import reset_world
from app.websocket.manager import manager

config.SIMULATION_LOOP_ENABLED = False


@pytest.fixture(autouse=True)
def fresh_world() -> None:
    reset_world()
    manager._connections.clear()
