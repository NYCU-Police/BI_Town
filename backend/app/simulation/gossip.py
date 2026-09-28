"""Tag gossip and culprit avoidance. No model calls."""

from __future__ import annotations

from app import config as app_config
from app.simulation.poi import POIS, home_for

_FACTS = "facts"


def absolute_minute(day: int, time: str) -> int:
    hour, minute = time.split(":")
    return (day - 1) * 24 * 60 + int(hour) * 60 + int(minute)


def routine_places(resident_id: str) -> set[str]:
    places = {home_for(resident_id).id}
    places.update(app_config.WORK_PLACES.get(resident_id, ()))
    return places


def record_returned_tags(
    world: object,
    resident_id: str,
    token: str,
    fact_ids: list[str],
) -> None:
    """Tags the resident actually handed back. This never starts avoidance."""
    tags = _tags_of(getattr(world, "case", None), fact_ids)
    if not tags or not token:
        return
    rows = _asked(world).setdefault(resident_id, {}).setdefault(token, {})
    for tag in tags:
        rows.setdefault(tag, set()).add(resident_id)


def tags_for(world: object, resident_id: str, token: str) -> list[str]:
    found = _heard(world).get(resident_id, {}).get(token, {})
    return sorted(found)


def tick_gossip(world: object) -> None:
    residents = _idle_by_place(world)
    seen: set[tuple[str, str]] = set()
    waits = _waits(world)
    for group in residents.values():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                pair = tuple(sorted((left, right)))
                seen.add(pair)
                waits[pair] = waits.get(pair, 0) + 1
                if waits[pair] >= app_config.GOSSIP_INTERVAL_MINUTES:
                    waits[pair] = 0
                    spread_tags(world, left, right)
    for pair in list(waits):
        if pair not in seen:
            del waits[pair]


def spread_tags(world: object, left: str, right: str) -> None:
    """Copy tag sets both ways. Only tags from someone else can scare the culprit."""
    asked = _asked(world)
    left_before = _snapshot(asked.get(left, {}))
    right_before = _snapshot(asked.get(right, {}))
    _copy(asked, left, right)
    _copy(asked, right, left)
    _merge_heard(world, right, left_before)
    _merge_heard(world, left, right_before)
    _scare_from(world, left, right_before)
    _scare_from(world, right, left_before)


def is_avoiding(world: object, resident_id: str, token: str) -> bool:
    until = _avoid(world).get(resident_id, {}).get(token)
    if until is None:
        return False
    now = absolute_minute(getattr(world, "day", 1), getattr(world, "time", "08:00"))
    return now < until


def rewrite_action(
    world: object,
    resident_id: str,
    action: str,
    target: str,
    location: str,
) -> tuple[str, str]:
    """Keep home and work. Do not stop where an avoided player is standing."""
    if action not in {"stay", "move_to", "talk_to"}:
        return action, target
    blocked = _blocked_places(world, resident_id)
    if not blocked:
        return action, target
    routine = routine_places(resident_id)
    if action == "move_to" and target in routine:
        return action, target
    stuck = (action in {"stay", "talk_to"} and location in blocked) or (
        action == "move_to" and target in blocked
    )
    if not stuck:
        return action, target
    return "move_to", _escape(resident_id, location, blocked, routine)


def _scare_from(
    world: object,
    receiver: str,
    incoming: dict[str, dict[str, set[str]]],
) -> None:
    case = getattr(world, "case", None)
    if not isinstance(case, dict) or case.get("culprit_id") != receiver:
        return
    sensitive = _sensitive_tags(case, receiver)
    if not sensitive:
        return
    now = absolute_minute(getattr(world, "day", 1), getattr(world, "time", "08:00"))
    until = now + app_config.CULPRIT_AVOID_MINUTES
    avoid = _avoid(world).setdefault(receiver, {})
    for token, origins in incoming.items():
        foreign = {
            tag for tag, who in origins.items() if who - {receiver}
        }
        if foreign & sensitive:
            avoid[token] = until


def _snapshot(
    rows: dict[str, dict[str, set[str]]],
) -> dict[str, dict[str, set[str]]]:
    return {
        token: {tag: set(who) for tag, who in origins.items()}
        for token, origins in rows.items()
    }


def _sensitive_tags(case: dict[str, object], resident_id: str) -> set[str]:
    found: set[str] = set()
    for fact in _fact_list(case):
        if fact.get("kind") != "lie" or fact.get("sensitive") is not True:
            continue
        holders = fact.get("holders")
        if not isinstance(holders, list) or resident_id not in holders:
            continue
        tags = fact.get("tags")
        if isinstance(tags, list):
            found.update(str(tag) for tag in tags)
    return found


def _tags_of(case: object, fact_ids: list[str]) -> set[str]:
    if not isinstance(case, dict):
        return set()
    wanted = set(fact_ids)
    found: set[str] = set()
    for fact in _fact_list(case):
        if fact.get("id") not in wanted:
            continue
        tags = fact.get("tags")
        if isinstance(tags, list):
            found.update(str(tag) for tag in tags)
    return found


def _blocked_places(world: object, resident_id: str) -> set[str]:
    active = {
        token
        for token in _avoid(world).get(resident_id, {})
        if is_avoiding(world, resident_id, token)
    }
    places: set[str] = set()
    tokens_by_player = getattr(world, "player_tokens", {})
    agents = getattr(world, "agents", {})
    for player_id, token in tokens_by_player.items():
        if token not in active:
            continue
        agent = agents.get(player_id)
        location = getattr(agent, "location", "")
        if location:
            places.add(location)
    return places


def _escape(
    resident_id: str,
    location: str,
    blocked: set[str],
    routine: set[str],
) -> str:
    for place in sorted(routine):
        if place not in blocked:
            return place
    for place in sorted(POIS):
        if place not in blocked and place != location:
            return place
    return home_for(resident_id).id


def _idle_by_place(world: object) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    agents = getattr(world, "agents", {})
    for agent_id, agent in agents.items():
        if agent_id.startswith("player_"):
            continue
        if getattr(agent, "state", "") != "idle":
            continue
        place = getattr(agent, "location", "")
        if place:
            grouped.setdefault(place, []).append(agent_id)
    return grouped


def _copy(
    asked: dict[str, dict[str, dict[str, set[str]]]],
    source: str,
    dest: str,
) -> None:
    for token, origins in asked.get(source, {}).items():
        if not origins:
            continue
        dest_rows = asked.setdefault(dest, {}).setdefault(token, {})
        for tag, who in origins.items():
            dest_rows.setdefault(tag, set()).update(who)


def _merge_heard(
    world: object,
    receiver: str,
    incoming: dict[str, dict[str, set[str]]],
) -> None:
    heard = _heard(world)
    for token, origins in incoming.items():
        if not origins:
            continue
        dest_rows = heard.setdefault(receiver, {}).setdefault(token, {})
        for tag, who in origins.items():
            dest_rows.setdefault(tag, set()).update(who)


def _heard(world: object) -> dict[str, dict[str, dict[str, set[str]]]]:
    found = getattr(world, "heard_tags", None)
    if isinstance(found, dict):
        return found
    fresh: dict[str, dict[str, dict[str, set[str]]]] = {}
    world.heard_tags = fresh  # type: ignore[attr-defined]
    return fresh


def _asked(world: object) -> dict[str, dict[str, dict[str, set[str]]]]:
    found = getattr(world, "asked_tags", None)
    if isinstance(found, dict):
        return found
    fresh: dict[str, dict[str, dict[str, set[str]]]] = {}
    world.asked_tags = fresh  # type: ignore[attr-defined]
    return fresh


def _avoid(world: object) -> dict[str, dict[str, int]]:
    found = getattr(world, "avoid_until", None)
    if isinstance(found, dict):
        return found
    fresh: dict[str, dict[str, int]] = {}
    world.avoid_until = fresh  # type: ignore[attr-defined]
    return fresh


def _waits(world: object) -> dict[tuple[str, str], int]:
    found = getattr(world, "gossip_wait", None)
    if isinstance(found, dict):
        return found
    fresh: dict[tuple[str, str], int] = {}
    world.gossip_wait = fresh  # type: ignore[attr-defined]
    return fresh


def _fact_list(case: dict[str, object]) -> list[dict[str, object]]:
    facts = case.get(_FACTS)
    if not isinstance(facts, list):
        return []
    return [fact for fact in facts if isinstance(fact, dict)]
