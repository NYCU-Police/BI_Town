"""Builtin cases. This round does not ask the model to phrase them."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from app.config import TRUST_SOLVE_MAX
from app.simulation.poi import POIS

_DIR = Path(__file__).parent
_ORDER = (
    "builtin_cashbox",
    "builtin_torn_notice",
    "builtin_unsigned_letter",
)
_SCHEMA = json.loads((_DIR / "case.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = Draft202012Validator(_SCHEMA)


def _load(case_id: str) -> dict[str, object]:
    raw = json.loads((_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
    errors = structure_errors(raw)
    if errors:
        raise RuntimeError(f"{case_id}: {'; '.join(errors)}")
    return raw


def case_for_day(day: int) -> dict[str, object]:
    """Rotate the three builtins. Day 1 is the cashbox."""
    return deepcopy(_CASES[(day - 1) % len(_CASES)])


def public_fact_ids(case: dict[str, object]) -> list[str]:
    return [str(fact["id"]) for fact in _facts(case) if fact["public"]]


def fact_text(case: dict[str, object], fact_id: str) -> str | None:
    for fact in _facts(case):
        if fact["id"] == fact_id:
            return str(fact["text"])
    return None


def allowed_facts(
    case: dict[str, object],
    resident_id: str,
    trust: int,
    held: set[str],
) -> list[dict[str, object]]:
    """Facts this resident may say. Public facts stay on the notice."""
    chosen: list[dict[str, object]] = []
    for fact in _facts(case):
        if fact["public"]:
            continue
        holders = fact["holders"]
        if not isinstance(holders, list) or resident_id not in holders:
            continue
        if trust < int(fact["requires_trust"]):
            continue
        needed = fact["requires_evidence"]
        if isinstance(needed, list) and any(item not in held for item in needed):
            continue
        chosen.append(fact)
    return chosen


def reachable(case: dict[str, object], trust_max: int = TRUST_SOLVE_MAX) -> set[str]:
    facts = _facts(case)
    start = {
        str(fact["id"])
        for fact in facts
        if fact["public"]
        or (
            int(fact["requires_trust"]) == 0
            and not fact["requires_evidence"]
        )
    }
    obtained = set(start)
    queue = list(start)
    while queue:
        queue.pop(0)
        for fact in facts:
            fact_id = str(fact["id"])
            if fact_id in obtained:
                continue
            needed = fact["requires_evidence"]
            evidence_ok = isinstance(needed, list) and all(
                item in obtained for item in needed
            )
            holders = fact["holders"]
            trust_ok = (
                int(fact["requires_trust"]) <= trust_max
                and evidence_ok
                and (bool(fact["public"]) or bool(holders))
            )
            unlocked = fact.get("unlocked_by", [])
            opened = isinstance(unlocked, list) and any(
                item in obtained for item in unlocked
            )
            if trust_ok or opened:
                obtained.add(fact_id)
                queue.append(fact_id)
    return obtained


def solvable(case: dict[str, object]) -> bool:
    got = reachable(case)
    culprit = case["culprit_id"]
    motive = case["motive_id"]
    has_culprit = any(
        fact.get("implicates") == culprit and fact["id"] in got
        for fact in _facts(case)
    )
    has_motive = any(
        fact.get("supports_motive") == motive and fact["id"] in got
        for fact in _facts(case)
    )
    return has_culprit and has_motive


def structure_errors(case: object) -> list[str]:
    errors = [
        error.message for error in _VALIDATOR.iter_errors(case)
    ]
    if not isinstance(case, dict):
        return errors or ["case is not an object"]
    facts = case.get("facts")
    motives = case.get("motives")
    timeline = case.get("timeline")
    if not isinstance(facts, list) or not isinstance(motives, list):
        return errors
    if not isinstance(timeline, list):
        return errors
    motive_ids = {
        item["id"] for item in motives if isinstance(item, dict) and "id" in item
    }
    if case.get("motive_id") not in motive_ids:
        errors.append("motive_id is not one of motives")
    ids = [item.get("id") for item in facts if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        errors.append("fact ids repeat")
    known = {item for item in ids if isinstance(item, str)}
    if not any(
        isinstance(item, dict) and item.get("public") is True for item in facts
    ):
        errors.append("no public fact")
    by_id = {
        str(item["id"]): item
        for item in facts
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for fact in by_id.values():
        for key in ("requires_evidence", "unlocked_by", "contradicts"):
            for ref in _refs(fact.get(key)):
                if ref not in known:
                    errors.append(f"{fact['id']}.{key} missing {ref}")
        truth_id = fact.get("truth_id")
        if isinstance(truth_id, str) and truth_id not in known:
            errors.append(f"{fact['id']}.truth_id missing {truth_id}")
    for beat in timeline:
        if not isinstance(beat, dict):
            continue
        if beat.get("fact_id") not in known:
            errors.append(f"{beat.get('id')} fact_id missing")
        if beat.get("place") not in POIS:
            errors.append(f"{beat.get('id')} place is not a POI")
    errors.extend(_lie_errors(by_id))
    return errors


def _lie_errors(by_id: dict[str, dict[str, object]]) -> list[str]:
    found: list[str] = []
    for lie in by_id.values():
        if lie.get("kind") != "lie":
            continue
        truth_id = lie.get("truth_id")
        if not isinstance(truth_id, str):
            continue
        truth = by_id.get(truth_id)
        if truth is None:
            continue
        matched = False
        for ref in _refs(truth.get("unlocked_by")):
            other = by_id.get(ref)
            if other is None:
                continue
            mutual = lie["id"] in _refs(other.get("contradicts")) and (
                ref in _refs(lie.get("contradicts"))
            )
            if mutual:
                matched = True
        if not matched:
            found.append(f"{lie['id']} is not tied to its truth")
    return found


def _facts(case: dict[str, object]) -> list[dict[str, object]]:
    facts = case["facts"]
    if not isinstance(facts, list):
        return []
    return [item for item in facts if isinstance(item, dict)]


def _refs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


_CASES = [_load(case_id) for case_id in _ORDER]
