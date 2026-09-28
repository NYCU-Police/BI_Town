"""Ids the client must be able to draw. Art paths live in the Godot manifest."""

from app.config import FOOD_ITEMS, PARK_PRODUCT_ID, TOOL_IDS
from app.simulation.poi import POIS

RESIDENT_IDS = ("mina", "alex", "rin", "player")


def content_ids() -> tuple[str, ...]:
    seen: list[str] = []
    for content_id in (
        *POIS,
        *RESIDENT_IDS,
        *sorted(FOOD_ITEMS),
        PARK_PRODUCT_ID,
        *TOOL_IDS,
    ):
        if content_id not in seen:
            seen.append(content_id)
    return tuple(seen)
