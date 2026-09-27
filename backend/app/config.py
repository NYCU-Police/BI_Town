"""Central settings. No magic numbers in route or simulation code."""

import os

SERVICE_NAME = "BI_Town"
VERSION = "0.1.0"


def deployment_value(name: str) -> str:
    """Identity baked in at image build. Blank means this process was not deployed."""
    value = os.environ.get(name, "").strip()
    return value or "unknown"

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


def current_brain_mode() -> str:
    """rules keeps the schedule. llm is opt-in and must not be the deploy default."""
    raw = os.environ.get("BRAIN_MODE", "rules").strip().lower()
    if raw in {"rules", "llm"}:
        return raw
    return "rules"


def current_llm_think() -> bool:
    """Ollama think mode. Off unless the host explicitly opts in."""
    raw = os.environ.get("LLM_THINK", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


LLM_IDLE_DECISION_MINUTES = 15
LLM_MAX_CONSECUTIVE_DIALOGUE = 4
LLM_DIALOGUE_COOLDOWN_MINUTES = 30
LLM_RECENT_SAY_LIMIT = 5
LLM_RECENT_SAY_PROMPT_LIMIT = 3
LLM_RECENT_THOUGHT_LIMIT = 3
LLM_SAY_SIMILARITY = 0.8
LLM_UNANSWERED_MINUTES = 30
LLM_MEMORY_PROMPT_LIMIT = 10
LLM_MEMORY_STORE_LIMIT = 50
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LLM_MODEL = "qwen3:14b"
DEFAULT_LLM_TIMEOUT_SECONDS = 60.0
LLM_TEMPERATURE = 0.8
