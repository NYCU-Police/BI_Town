"""Town assembly, accusation, reveal, and the next morning. No model calls."""

from __future__ import annotations

import time
from typing import Any

from app import config as app_config
from app.simulation.cases import fact_text
from app.simulation.content import RESIDENT_IDS
from app.simulation.needs import is_collapsed
from app.simulation.player_talk import Dossier
from app.simulation.poi import home_for

PLAZA = "plaza"
_NAMES = {"mina": "Mina", "alex": "Alex", "rin": "Rin"}


def score_guess(case: dict[str, Any], culprit_id: str, motive_id: str) -> int:
    points = 0
    if culprit_id == case.get("culprit_id"):
        points += app_config.SCORE_CULPRIT
    if motive_id == case.get("motive_id"):
        points += app_config.SCORE_MOTIVE
    return points


def motive_options(case: object) -> list[dict[str, str]]:
    if not isinstance(case, dict):
        return []
    motives = case.get("motives")
    if not isinstance(motives, list):
        return []
    found: list[dict[str, str]] = []
    for motive in motives:
        if not isinstance(motive, dict):
            continue
        motive_id = motive.get("id")
        label = motive.get("label")
        if isinstance(motive_id, str) and isinstance(label, str):
            found.append({"id": motive_id, "label": label})
    return found


def motive_ids(case: object) -> set[str]:
    return {item["id"] for item in motive_options(case)}


def reveal_text(case: dict[str, Any]) -> str:
    culprit = str(case.get("culprit_id", ""))
    motive = _motive_label(case, str(case.get("motive_id", "")))
    lines = [f"犯人是{_NAMES.get(culprit, culprit)}。動機是{motive}。"]
    timeline = case.get("timeline")
    if isinstance(timeline, list):
        for step in timeline:
            if not isinstance(step, dict):
                continue
            fact_id = step.get("fact_id")
            when = step.get("time")
            if not isinstance(fact_id, str) or not isinstance(when, str):
                continue
            text = fact_text(case, fact_id)
            if text:
                lines.append(f"{when} {text}")
    return "\n".join(lines)


def remaining_seconds(deadline: float | None, now: float | None = None) -> int:
    if deadline is None:
        return 0
    current = time.monotonic() if now is None else now
    left = deadline - current
    if left <= 0:
        return 0
    return int(left + 0.999)


def resident_choices(world: object) -> list[dict[str, str]]:
    agents = getattr(world, "agents", {})
    found: list[dict[str, str]] = []
    for resident_id in RESIDENT_IDS:
        if resident_id == "player":
            continue
        agent = agents.get(resident_id)
        name = getattr(agent, "name", "") or _NAMES.get(resident_id, resident_id)
        found.append({"id": resident_id, "name": str(name)})
    return found


def open_assembly(world: object) -> None:
    if getattr(world, "phase", "play") != "play":
        return
    if getattr(world, "brain_mode", "rules") != "llm":
        return
    world.phase = "assembly"  # type: ignore[attr-defined]
    world.assembly_deadline = time.monotonic() + app_config.ACCUSE_WINDOW_SECONDS  # type: ignore[attr-defined]
    world.accusations = {}  # type: ignore[attr-defined]
    world.scores = {}  # type: ignore[attr-defined]
    world.ready_tokens = set()  # type: ignore[attr-defined]
    world.reveal_body = ""  # type: ignore[attr-defined]
    _queue(
        world,
        {
            "type": "assembly_open",
            "residents": resident_choices(world),
            "motives": motive_options(getattr(world, "case", None)),
            "remaining_seconds": app_config.ACCUSE_WINDOW_SECONDS,
        },
    )
    _mark(world, steer_to_plaza(world))


def accuse(world: object, token: str, culprit_id: str, motive_id: str) -> str | None:
    """Return a failure reason, or None when the guess is stored."""
    phase = getattr(world, "phase", "play")
    if phase != "assembly":
        return "not_now"
    accusations: dict[str, tuple[str, str]] = getattr(world, "accusations", {})
    if token in accusations:
        return "already_accused"
    if culprit_id not in _NAMES:
        return "bad_culprit"
    case = getattr(world, "case", None)
    if motive_id not in motive_ids(case):
        return "bad_motive"
    accusations[token] = (culprit_id, motive_id)
    world.accusations = accusations  # type: ignore[attr-defined]
    if _all_online(world, accusations):
        begin_reveal(world)
    return None


def note_ready(world: object, token: str) -> str | None:
    if getattr(world, "phase", "play") != "reveal":
        return "not_now"
    ready: set[str] = getattr(world, "ready_tokens", set())
    ready.add(token)
    world.ready_tokens = ready  # type: ignore[attr-defined]
    if _all_online(world, {item: ("", "") for item in ready}):
        begin_next_round(world)
    return None


def poll_round(world: object, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    phase = getattr(world, "phase", "play")
    deadline = getattr(world, "assembly_deadline", None)
    if phase == "assembly" and isinstance(deadline, float) and current >= deadline:
        begin_reveal(world)
        return
    if phase == "reveal" and isinstance(deadline, float) and current >= deadline:
        begin_next_round(world)


def begin_reveal(world: object) -> None:
    if getattr(world, "phase", "play") != "assembly":
        return
    case = getattr(world, "case", None)
    if not isinstance(case, dict):
        return
    world.phase = "reveal"  # type: ignore[attr-defined]
    world.assembly_deadline = time.monotonic() + app_config.REVEAL_HOLD_SECONDS  # type: ignore[attr-defined]
    world.reveal_body = reveal_text(case)  # type: ignore[attr-defined]
    accusations: dict[str, tuple[str, str]] = getattr(world, "accusations", {})
    scores: dict[str, int] = {}
    for token in getattr(world, "player_tokens", {}).values():
        guess = accusations.get(token)
        if guess is None:
            scores[token] = 0
        else:
            scores[token] = score_guess(case, guess[0], guess[1])
    world.scores = scores  # type: ignore[attr-defined]
    _queue(
        world,
        {
            "type": "reveal",
            "culprit_id": str(case.get("culprit_id", "")),
            "motive_id": str(case.get("motive_id", "")),
            "text": world.reveal_body,
            "remaining_seconds": app_config.REVEAL_HOLD_SECONDS,
        },
    )


def begin_next_round(world: object) -> None:
    if getattr(world, "phase", "play") == "play":
        return
    world.day = int(getattr(world, "day", 1)) + 1  # type: ignore[attr-defined]
    world.time = app_config.INITIAL_TIME  # type: ignore[attr-defined]
    world.phase = "play"  # type: ignore[attr-defined]
    world.skip_clock = True  # type: ignore[attr-defined]
    world.assembly_deadline = None  # type: ignore[attr-defined]
    world.accusations = {}  # type: ignore[attr-defined]
    world.scores = {}  # type: ignore[attr-defined]
    world.ready_tokens = set()  # type: ignore[attr-defined]
    world.reveal_body = ""  # type: ignore[attr-defined]
    world.asked_tags = {}  # type: ignore[attr-defined]
    world.heard_tags = {}  # type: ignore[attr-defined]
    world.avoid_until = {}  # type: ignore[attr-defined]
    world.gossip_wait = {}  # type: ignore[attr-defined]
    conversing = getattr(world, "conversing", None)
    if isinstance(conversing, set):
        conversing.clear()
    for dossier in getattr(world, "dossiers", {}).values():
        if isinstance(dossier, Dossier):
            dossier.clear_round()
    _send_home(world)
    _reset_needs(world)
    world.bread_stock = app_config.BREAD_STOCK_MAX  # type: ignore[attr-defined]
    world._bread_elapsed = 0  # type: ignore[attr-defined]
    install = getattr(world, "_install_case", None)
    if callable(install):
        install(world.day, reset_notes=False)
    world.notebook_dirty = True  # type: ignore[attr-defined]
    llm = getattr(world, "llm", None)
    talk_log = getattr(llm, "talk_log", None)
    if talk_log is not None and hasattr(talk_log, "clear"):
        talk_log.clear()
    changed = {str(agent_id) for agent_id in getattr(world, "agents", {})}
    _mark(world, changed)
    notice = ""
    notice_text = getattr(world, "notice_text", None)
    if callable(notice_text):
        notice = str(notice_text())
    _queue(
        world,
        {
            "type": "round_started",
            "day": world.day,
            "time": world.time,
            "notice": notice,
        },
    )


def steer_to_plaza(world: object) -> set[str]:
    """Point every resident at the plaza. Players stay where they are."""
    changed: set[str] = set()
    llm = getattr(world, "llm", None)
    residents = getattr(llm, "residents", None)
    if residents is not None:
        for resident in residents:
            if _steer_resident(resident):
                changed.add(resident.id)
        agents = getattr(world, "agents", None)
        if isinstance(agents, dict):
            for resident in residents:
                agents[resident.id] = resident.as_agent()
        return changed
    agents = getattr(world, "agents", {})
    depart = getattr(world, "_depart", None)
    for agent_id, agent in list(agents.items()):
        if str(agent_id).startswith("player_"):
            continue
        if not callable(depart):
            continue
        before = (agent.state, agent.target_location)
        depart(agent, PLAZA, getattr(world, "time", "18:00"))
        if (agent.state, agent.target_location) != before:
            changed.add(str(agent_id))
    return changed


def arrived_for_assembly(world: object, resident_id: str) -> bool:
    if getattr(world, "phase", "play") == "play":
        return False
    agents = getattr(world, "agents", {})
    agent = agents.get(resident_id)
    if agent is None:
        return False
    if getattr(agent, "location", "") != PLAZA:
        return False
    if getattr(agent, "state", "") == "walking":
        return False
    hunger = 0.0
    energy = 0.0
    llm = getattr(world, "llm", None)
    by_id = getattr(llm, "by_id", {})
    resident = by_id.get(resident_id) if isinstance(by_id, dict) else None
    if resident is not None:
        hunger = float(getattr(resident, "fullness", 0))
        energy = float(getattr(resident, "energy", 0))
    else:
        bodies = getattr(world, "bodies", {})
        body = bodies.get(resident_id)
        if body is not None:
            hunger = float(getattr(body, "hunger", 0))
            energy = float(getattr(body, "energy", 0))
    return not is_collapsed(hunger, energy)


def plaza_decision(location: str, state: str, collapsed: bool) -> tuple[str, str]:
    if collapsed or (location == PLAZA and state != "walking"):
        return "stay", ""
    return "move_to", PLAZA


def take_notices(world: object) -> list[dict[str, object]]:
    found = getattr(world, "round_notices", None)
    if not isinstance(found, list):
        return []
    notices = list(found)
    found.clear()
    return notices


def _steer_resident(resident: object) -> bool:
    if bool(getattr(resident, "collapsed", False)):
        return False
    location = str(getattr(resident, "location", ""))
    state = str(getattr(resident, "state", ""))
    before = (state, str(getattr(resident, "target_location", "")))
    if location == PLAZA and state != "walking":
        resident.target_location = PLAZA  # type: ignore[attr-defined]
        if state == "doing":
            resident.state = "idle"  # type: ignore[attr-defined]
    else:
        resident.target_location = PLAZA  # type: ignore[attr-defined]
        resident.state = "walking"  # type: ignore[attr-defined]
        resident.activity_id = ""  # type: ignore[attr-defined]
        resident.activity_name = ""  # type: ignore[attr-defined]
        resident.activity_remaining = 0  # type: ignore[attr-defined]
    after = (
        str(getattr(resident, "state", "")),
        str(getattr(resident, "target_location", "")),
    )
    return after != before


def _send_home(world: object) -> None:
    llm = getattr(world, "llm", None)
    residents = getattr(llm, "residents", None)
    agents = getattr(world, "agents", {})
    if residents is None:
        for agent_id, agent in agents.items():
            if str(agent_id).startswith("player_"):
                continue
            home = home_for(str(agent_id))
            agent.location = home.id
            agent.target_location = home.id
            agent.position = home.position
            agent.state = "idle"
        return
    for resident in residents:
        home = home_for(resident.id)
        resident.location = home.id
        resident.target_location = home.id
        resident.position = home.position
        resident.state = "idle"
        resident.activity_id = ""
        resident.activity_name = ""
        resident.activity_remaining = 0
        if isinstance(agents, dict):
            agents[resident.id] = resident.as_agent()


def _reset_needs(world: object) -> None:
    for body in getattr(world, "bodies", {}).values():
        body.hunger = app_config.NEED_START_FULLNESS
        body.energy = app_config.NEED_START_ENERGY
        body.social = app_config.NEED_START_SOCIAL
    llm = getattr(world, "llm", None)
    for resident in getattr(llm, "residents", []) or []:
        resident.fullness = app_config.NEED_START_FULLNESS
        resident.energy = app_config.NEED_START_ENERGY
        resident.social = app_config.NEED_START_SOCIAL
        resident.collapsed = False
    sent = getattr(world, "_sent_needs", None)
    if isinstance(sent, dict):
        sent.clear()


def _all_online(world: object, done: dict[str, object]) -> bool:
    from app.websocket.manager import manager

    online = [
        token
        for token in getattr(world, "player_tokens", {}).values()
        if token in manager.socket_by_token
    ]
    if not online:
        return False
    return all(token in done for token in online)


def _motive_label(case: dict[str, Any], motive_id: str) -> str:
    for motive in motive_options(case):
        if motive["id"] == motive_id:
            return motive["label"]
    return motive_id


def _queue(world: object, notice: dict[str, object]) -> None:
    found = getattr(world, "round_notices", None)
    if not isinstance(found, list):
        found = []
        world.round_notices = found  # type: ignore[attr-defined]
    found.append(notice)


def _mark(world: object, agent_ids: set[str]) -> None:
    pending = getattr(world, "pending_changed", None)
    if not isinstance(pending, set):
        pending = set()
        world.pending_changed = pending  # type: ignore[attr-defined]
    pending.update(agent_ids)


def take_changed(world: object) -> set[str]:
    pending = getattr(world, "pending_changed", None)
    if not isinstance(pending, set):
        return set()
    found = set(pending)
    pending.clear()
    return found
