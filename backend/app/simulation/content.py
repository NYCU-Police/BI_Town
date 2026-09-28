"""Namespaced drawing ids. Wire payloads keep the plain ids."""

from app.config import FOOD_ITEMS, PARK_PRODUCT_ID, TOOL_IDS
from app.simulation.poi import POIS

RESIDENT_IDS = ("mina", "alex", "rin", "player")


def to_content_id(namespace: str, plain_id: str) -> str:
    """poi / agent / item / tool / fx plus the id the API already uses."""
    return f"{namespace}.{plain_id}"


def content_ids() -> tuple[str, ...]:
    seen: list[str] = []
    for content_id in (
        *(to_content_id("poi", poi_id) for poi_id in POIS),
        *(to_content_id("agent", agent_id) for agent_id in RESIDENT_IDS),
        *(to_content_id("item", item_id) for item_id in sorted(FOOD_ITEMS)),
        to_content_id("item", PARK_PRODUCT_ID),
        *(to_content_id("tool", tool_id) for tool_id in TOOL_IDS),
    ):
        if content_id not in seen:
            seen.append(content_id)
    return tuple(seen)
