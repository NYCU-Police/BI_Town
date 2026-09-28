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
LLM_THOUGHT_SIMILARITY = 0.9
LLM_MIN_STAY_MINUTES = 20
LLM_UNANSWERED_MINUTES = 30
LLM_MEMORY_PROMPT_LIMIT = 10
LLM_MEMORY_STORE_LIMIT = 50
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LLM_MODEL = "qwen3:14b"
DEFAULT_LLM_TIMEOUT_SECONDS = 60.0
LLM_TEMPERATURE = 0.8

NEED_MAX = 100.0
NEED_START_ENERGY = 80.0
NEED_START_FULLNESS = 70.0
NEED_START_SOCIAL = 65.0
ENERGY_DECAY_PER_MINUTE = 0.05
FULLNESS_DECAY_PER_MINUTE = 0.08
SOCIAL_DECAY_PER_MINUTE = 0.04
SOCIAL_COMPANY_PER_MINUTE = 0.04
EAT_FULLNESS_RESTORE = 35.0
CAFE_HUNGER_RESTORE_PER_MINUTE = 0.12
HOME_ENERGY_RESTORE_PER_MINUTE = 0.10
COLLAPSE_NEED = 0.0
BREAD_RESPAWN_MINUTES = 20
BREAD_STOCK_MAX = 4
FOOD_ITEMS = frozenset({"bread"})
TOOL_IDS = ("watering_can",)
PARK_TOOL_ID = "watering_can"
PARK_PRODUCT_ID = "wood"
PLAYER_ENABLED = True
INTENT_RATE_LIMIT_PER_SEC = 5
INTENT_MAX_BYTES = 4096
SLEEP_ENERGY_PER_MINUTE = 0.25
REST_ENERGY_PER_MINUTE = 0.08
TALK_SOCIAL_RESTORE = 12.0
NEED_TIRED = 55.0
NEED_EXHAUSTED = 30.0
NEED_PECKISH = 55.0
NEED_HUNGRY = 30.0
HUNGER_ACTION_THRESHOLD = NEED_HUNGRY
NEED_LONELY_HINT = 55.0
NEED_LONELY = 30.0
SLEEP_HOUR = 22
WAKE_HOUR = 7
PLAN_MIN_ITEMS = 4
PLAN_MAX_ITEMS = 6
REVIEW_HISTORY_DAYS = 3
EATING_ACTIVITIES = frozenset({"cook", "order_coffee", "shop"})
RESTING_ACTIVITIES = frozenset({"rest"})
SLEEPING_ACTIVITIES = frozenset({"sleep"})

# How long a place activity keeps a resident from making a new decision.
ACTIVITY_MINUTES = {
    "order_coffee": 10,
    "read_book": 25,
    "chat_staff": 10,
    "write_report": 40,
    "sort_accounts": 25,
    "meeting": 30,
    "shelve_books": 20,
    "borrow_book": 10,
    "study": 40,
    "shop": 10,
    "stroll": 20,
    "sit_bench": 15,
    "take_photo": 20,
    "read_board": 10,
    "wander": 15,
    "cook": 30,
    "rest": 20,
    "sleep": 60,
}
