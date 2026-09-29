"""Assembly, scoring, and the next morning. No model calls."""

import time

import pytest

from app.config import (
    BREAD_STOCK_MAX,
    INITIAL_TIME,
    NEED_START_FULLNESS,
    game_minutes_per_real_second,
)
from app.models.schemas import Intent, TargetRef
from app.simulation.assembly import open_assembly, score_guess
from app.simulation.cases import case_for_day
from app.simulation.player_talk import Dossier, open_token
from app.simulation.world import World
from app.websocket.manager import manager

_CASE = case_for_day(1)


def test_clock_default_is_slower_than_one_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GAME_MINUTES_PER_REAL_SECOND", raising=False)
    assert game_minutes_per_real_second() == 0.4
    monkeypatch.setenv("GAME_MINUTES_PER_REAL_SECOND", "nope")
    assert game_minutes_per_real_second() == 0.4
    monkeypatch.setenv("GAME_MINUTES_PER_REAL_SECOND", "2")
    assert game_minutes_per_real_second() == 2.0


@pytest.mark.parametrize(
    ("culprit", "motive", "points"),
    [
        ("alex", "jealousy", 60),
        ("mina", "cover_debt", 40),
        ("alex", "cover_debt", 100),
        ("rin", "cover_debt", 40),
        ("mina", "jealousy", 0),
    ],
)
def test_score_table(culprit: str, motive: str, points: int) -> None:
    assert score_guess(_CASE, culprit, motive) == points


def test_rules_mode_walks_through_eighteen() -> None:
    world = World()
    world.time = "17:59"
    world.tick()
    assert world.time == "18:00"
    assert world.phase == "play"
    world.tick()
    assert world.time == "18:01"
    assert world.phase == "play"


def test_assembly_freezes_the_clock_and_still_settles_needs() -> None:
    calls = 0

    async def fake(_messages, _schema):
        nonlocal calls
        calls += 1
        return "{}"

    world = World(brain_mode="llm", decider=fake)
    world.time = "17:59"
    world.tick()
    assert world.time == "18:00"
    assert world.phase == "assembly"
    assert world.agents["alex"].target_location == "plaza"
    assert world.agents["alex"].state == "walking"
    assert calls == 0
    before = world.llm.by_id["alex"].fullness if world.llm else 0
    world.assembly_deadline = time.monotonic() + 999
    world.tick()
    assert world.time == "18:00"
    assert world.llm is not None
    assert world.llm.by_id["alex"].fullness < before
    assert calls == 0


def _token(world: World, player_id: str = "player_test") -> str:
    world.add_player(player_id)
    token = open_token(world, None)
    world.player_tokens[player_id] = token
    return token


def _accuse(culprit: str, motive: str) -> Intent:
    return Intent(action="accuse", culprit_id=culprit, motive_id=motive)


def test_arrived_resident_refuses_talk() -> None:
    world = World(brain_mode="llm", decider=None)
    _token(world)
    open_assembly(world)
    player = world.agents["player_test"]
    player.location = "plaza"
    player.state = "idle"
    alex = world.agents["alex"]
    alex.location = "plaza"
    alex.state = "idle"
    alex.target_location = "plaza"
    assert world.llm is not None
    resident = world.llm.by_id["alex"]
    resident.location = "plaza"
    resident.state = "idle"
    resident.target_location = "plaza"
    result = world.apply_intent(
        "player_test",
        Intent(
            action="talk",
            target=TargetRef(type="agent", id="alex"),
            text="早安",
        ),
        1,
    )
    assert result.reason == "assembly"


def test_accuse_does_not_call_the_model_and_rejects_a_second_guess() -> None:
    calls = 0

    async def fake(_messages, _schema):
        nonlocal calls
        calls += 1
        return "{}"

    world = World(brain_mode="llm", decider=fake)
    _token(world)
    open_assembly(world)
    first = world.apply_intent("player_test", _accuse("mina", "jealousy"), 1)
    assert first.ok is True
    assert calls == 0
    again = world.apply_intent("player_test", _accuse("alex", "cover_debt"), 2)
    assert again.reason == "already_accused"
    assert calls == 0


def test_wrong_guess_still_reveals_the_culprit() -> None:
    world = World(brain_mode="llm", decider=None)
    token = _token(world)
    open_assembly(world)
    assert world.apply_intent("player_test", _accuse("mina", "jealousy"), 1).ok
    world.assembly_deadline = time.monotonic() - 1
    world.tick()
    assert world.phase == "reveal"
    assert "Alex" in world.reveal_body
    assert "補上欠款" in world.reveal_body
    assert "想報復 Mina" not in world.reveal_body
    assert world.scores[token] == 0


def test_missing_accusation_scores_zero() -> None:
    world = World(brain_mode="llm", decider=None)
    token = _token(world)
    open_assembly(world)
    world.assembly_deadline = time.monotonic() - 1
    world.tick()
    assert world.scores[token] == 0
    assert world.phase == "reveal"


def test_next_round_clears_the_dossier_and_keeps_the_token() -> None:
    world = World(brain_mode="llm", decider=None)
    token = _token(world)
    dossier = world.dossiers[token]
    assert isinstance(dossier, Dossier)
    dossier.trust["alex"] = 50
    dossier.notes.append("rin_saw_alex")
    dossier.cracks.append("破綻")
    dossier.memory["alex"] = [("player", "你好")]
    world.asked_tags["alex"] = {token: {"whereabouts": {"alex"}}}
    world.heard_tags["mina"] = {token: {"whereabouts": {"alex"}}}
    world.avoid_until["alex"] = {token: 999}
    open_assembly(world)
    world.assembly_deadline = time.monotonic() - 1
    world.tick()
    assert world.phase == "reveal"
    world.assembly_deadline = time.monotonic() - 1
    world.tick()
    assert world.phase == "play"
    assert world.day == 2
    assert world.time == INITIAL_TIME
    assert token in world.player_tokens.values()
    assert token in world.dossiers
    assert dossier.trust == {}
    assert dossier.notes == []
    assert dossier.cracks == []
    assert dossier.memory == {}
    assert world.asked_tags == {}
    assert world.heard_tags == {}
    assert world.avoid_until == {}
    assert world.agents["alex"].location == "alex_home"
    assert world.llm is not None
    assert world.llm.by_id["alex"].fullness == NEED_START_FULLNESS
    assert world.bread_stock == BREAD_STOCK_MAX
    assert "撕" in world.notice_text()


def test_one_ready_player_does_not_advance_the_others() -> None:
    world = World(brain_mode="llm", decider=None)
    first = _token(world, "player_test")
    second = _token(world, "player_two")
    manager.socket_by_token[first] = object()  # type: ignore[assignment]
    manager.socket_by_token[second] = object()  # type: ignore[assignment]
    open_assembly(world)
    world.phase = "reveal"
    world.assembly_deadline = time.monotonic() + 999
    assert world.apply_intent("player_test", Intent(action="next_round"), 1).ok
    assert world.phase == "reveal"
    assert world.apply_intent("player_two", Intent(action="next_round"), 2).ok
    assert world.phase == "play"
    assert world.day == 2
