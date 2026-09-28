"""Per-minute body needs. Hunger on the wire is the fullness meter."""

from dataclasses import dataclass

from app.config import (
    CAFE_HUNGER_RESTORE_PER_MINUTE,
    COLLAPSE_NEED,
    ENERGY_DECAY_PER_MINUTE,
    FULLNESS_DECAY_PER_MINUTE,
    HOME_ENERGY_RESTORE_PER_MINUTE,
    NEED_MAX,
    REST_ENERGY_PER_MINUTE,
    SLEEP_ENERGY_PER_MINUTE,
    SOCIAL_COMPANY_PER_MINUTE,
    SOCIAL_DECAY_PER_MINUTE,
)
from app.simulation.poi import POIS


@dataclass
class NeedValues:
    hunger: float
    energy: float
    social: float


def clamp_need(value: float) -> float:
    return min(NEED_MAX, max(0.0, value))


def round_need(value: float) -> int:
    return int(value + 0.5)


def is_home(location: str) -> bool:
    poi = POIS.get(location)
    return poi is not None and poi.owner is not None


def is_collapsed(hunger: float, energy: float) -> bool:
    return hunger <= COLLAPSE_NEED or energy <= COLLAPSE_NEED


def tick_need_values(
    needs: NeedValues,
    *,
    location: str,
    state: str,
    company: bool,
    asleep: bool,
    resting: bool,
) -> None:
    """One game minute. Cafe restores hunger while staying; home restores energy."""
    if asleep:
        needs.energy = clamp_need(needs.energy + SLEEP_ENERGY_PER_MINUTE)
    elif resting:
        needs.energy = clamp_need(needs.energy + REST_ENERGY_PER_MINUTE)
    elif state != "walking" and is_home(location):
        needs.energy = clamp_need(needs.energy + HOME_ENERGY_RESTORE_PER_MINUTE)
    else:
        needs.energy = clamp_need(needs.energy - ENERGY_DECAY_PER_MINUTE)

    if state != "walking" and location == "cafe":
        needs.hunger = clamp_need(needs.hunger + CAFE_HUNGER_RESTORE_PER_MINUTE)
    else:
        needs.hunger = clamp_need(needs.hunger - FULLNESS_DECAY_PER_MINUTE)

    if company:
        needs.social = clamp_need(needs.social + SOCIAL_COMPANY_PER_MINUTE)
    else:
        needs.social = clamp_need(needs.social - SOCIAL_DECAY_PER_MINUTE)
