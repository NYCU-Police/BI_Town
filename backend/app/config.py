"""Central settings. No magic numbers in route or simulation code."""

import os

SERVICE_NAME = "BI_Town"
VERSION = "0.1.0"

# Godot web export directory. Empty/missing = API-only (tests, local uvicorn).
STATIC_WEB_DIR = os.environ.get("STATIC_WEB_DIR", "")

SIMULATION_TICK_SECONDS = 1.0
GAME_MINUTES_PER_TICK = 1
SIMULATION_LOOP_ENABLED = True

INITIAL_DAY = 1
INITIAL_TIME = "08:00"

AGENT_SPEED_PER_TICK = 50.0
ARRIVAL_DISTANCE_THRESHOLD = 10.0
MAX_WORLD_EVENTS = 50
