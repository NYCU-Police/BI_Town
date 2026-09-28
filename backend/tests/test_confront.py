"""Confrontation, tag gossip, and culprit avoidance."""

import asyncio
import json

import pytest

from app import config
from app.models.schemas import Intent, TargetRef
from app.simulation.gossip import is_avoiding, record_returned_tags, rewrite_action
from app.simulation.llm_session import Decision, DecisionJob, service_pending
from app.simulation.player_talk import note_ids, note_texts, open_token
from app.simulation.poi import POIS
from app.simulation.world import World

_TRUTH = "Alex 承認他七點前就出了門，並沒有在睡覺。"
_CRACK = "Alex 沒有再重複他七點還在家裡。"
_WITNESS = "早上七點十分，我看見 Alex 從咖啡廳側門出來。"


def _place(world: World, agent_id: str, poi_id: str, state: str = "idle") -> None:
    agent = world.agents[agent_id]
    place = POIS[poi_id]
    agent.location = poi_id
    agent.target_location = poi_id
    agent.position = place.position
    agent.state = state


def _llm(decider) -> tuple[World, str]:
    world = World(brain_mode="llm", decider=decider)
    world.add_player("player_test")
    _place(world, "player_test", "plaza")
    _place(world, "alex", "plaza")
    _place(world, "rin", "plaza")
    token = open_token(world, None)
    world.player_tokens["player_test"] = token
    dossier = world.dossiers[token]
    dossier.notes.extend(["mina_closed_full", "rin_saw_alex"])
    return world, token


def _present(fact_id: str) -> Intent:
    return Intent(
        action="present_evidence",
        target=TargetRef(type="agent", id="alex"),
        fact_id=fact_id,
    )


def _reply(fact_ids: list[str]) -> str:
    return json.dumps(
        {"reply": "我看看。", "revealed_fact_ids": fact_ids, "mood": "calm"}
    )


def test_rules_mode_refuses_before_checking_the_notebook() -> None:
    world = World()
    world.add_player("player_test")
    _place(world, "player_test", "plaza")
    _place(world, "alex", "plaza")
    result = world.apply_intent("player_test", _present("rin_saw_alex"), 1)
    assert result.reason == "npc_unavailable"


def test_unrelated_note_does_not_unlock() -> None:
    seen: list[str] = []

    async def fake(messages, _schema):
        seen.append(messages[0]["content"] + "\n" + messages[1]["content"])
        return _reply([])

    world, token = _llm(fake)
    assert world.apply_intent("player_test", _present("mina_closed_full"), 1).ok
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    blob = seen[0]
    assert "alex_left_home" not in blob
    assert "玩家拿出的證據" not in blob
    notes = note_texts(world, token)
    assert _TRUTH not in notes
    assert _CRACK not in notes


def test_matching_note_adds_the_truth_to_the_allow_list() -> None:
    seen: list[str] = []

    async def fake(messages, _schema):
        seen.append(messages[0]["content"] + "\n" + messages[1]["content"])
        return _reply(["alex_left_home"])

    world, token = _llm(fake)
    assert world.apply_intent("player_test", _present("rin_saw_alex"), 1).ok
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    blob = seen[0]
    assert "alex_left_home" in blob
    assert "玩家拿出的證據" in blob
    assert _WITNESS in blob
    assert "不能否認證據本身" in blob
    assert _TRUTH in note_texts(world, token)
    assert world.llm.talk_log[0]["reply"] == "我看看。"


def test_missing_admission_writes_crack_text() -> None:
    async def fake(_messages, _schema):
        return _reply([])

    world, token = _llm(fake)
    assert world.apply_intent("player_test", _present("rin_saw_alex"), 1).ok
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    assert world.llm.talk_log[0]["reply"] == config.CONFRONT_CRACK_REPLY
    notes = note_texts(world, token)
    assert _CRACK in notes
    assert _TRUTH not in notes
    assert note_ids(world, token)[-1] == ""


def test_unknown_fact_is_refused() -> None:
    world, _token = _llm(lambda _messages, _schema: _reply([]))
    result = world.apply_intent("player_test", _present("not_a_note"), 1)
    assert result.reason == "not_in_notes"


def test_gossip_copies_tags_not_fact_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GOSSIP_INTERVAL_MINUTES", 1)
    world, token = _llm(lambda _messages, _schema: _reply([]))
    record_returned_tags(world, "alex", token, ["alex_was_home"])
    assert is_avoiding(world, "alex", token) is False
    record_returned_tags(world, "rin", token, ["rin_saw_alex"])
    from app.simulation.gossip import tick_gossip

    tick_gossip(world)
    stored = repr(world.asked_tags)
    assert _WITNESS not in stored
    assert "whereabouts" in world.heard_tags["alex"][token]
    assert is_avoiding(world, "alex", token) is True


def test_own_sensitive_tag_does_not_start_avoidance() -> None:
    world, token = _llm(lambda _messages, _schema: _reply([]))
    record_returned_tags(world, "alex", token, ["alex_was_home"])
    from app.simulation.gossip import spread_tags

    spread_tags(world, "alex", "rin")
    assert is_avoiding(world, "alex", token) is False
    record_returned_tags(world, "rin", token, ["rin_saw_alex"])
    spread_tags(world, "rin", "alex")
    assert is_avoiding(world, "alex", token) is True


def test_gossip_prompt_names_tags_not_the_other_fact() -> None:
    seen: list[str] = []

    async def fake(messages, _schema):
        seen.append(messages[1]["content"])
        return _reply([])

    world, token = _llm(fake)
    record_returned_tags(world, "rin", token, ["rin_saw_alex"])
    from app.simulation.gossip import spread_tags

    spread_tags(world, "rin", "alex")
    talk = Intent(
        action="talk",
        target=TargetRef(type="agent", id="alex"),
        text="你早上在哪？",
    )
    assert world.apply_intent("player_test", talk, 1).ok
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    prompt = seen[0]
    assert "有人問過這類事" in prompt
    assert "whereabouts" in prompt
    assert _WITNESS not in prompt
    history = prompt.index("<history>")
    assert prompt.index("你最近在躲這位玩家") < history


def test_avoidance_expires_on_the_minute() -> None:
    world, token = _llm(lambda _messages, _schema: _reply([]))
    world.time = "08:00"
    record_returned_tags(world, "rin", token, ["rin_saw_alex"])
    from app.simulation.gossip import spread_tags

    spread_tags(world, "rin", "alex")
    world.time = "08:59"
    assert is_avoiding(world, "alex", token) is True
    world.time = "09:00"
    assert is_avoiding(world, "alex", token) is False


def test_avoidance_keeps_home_and_work() -> None:
    world, token = _llm(lambda _messages, _schema: _reply([]))
    world.time = "08:00"
    record_returned_tags(world, "rin", token, ["rin_saw_alex"])
    from app.simulation.gossip import spread_tags

    spread_tags(world, "rin", "alex")
    _place(world, "player_test", "alex_home")
    home = rewrite_action(world, "alex", "move_to", "alex_home", "plaza")
    assert home == ("move_to", "alex_home")
    _place(world, "player_test", "office")
    work = rewrite_action(world, "alex", "move_to", "office", "plaza")
    assert work == ("move_to", "office")
    _place(world, "player_test", "plaza")
    assert world.llm is not None
    actor = world.llm.by_id["alex"]
    actor.location = "plaza"
    world.llm._commit(
        actor,
        Decision(action="stay"),
        world.time,
        DecisionJob(agent_id="alex", messages=[]),
    )
    assert actor.state == "walking"
    assert actor.target_location != "plaza"


def test_presenting_is_allowed_while_avoiding() -> None:
    async def fake(_messages, _schema):
        return _reply(["alex_left_home"])

    world, _token = _llm(fake)
    world.avoid_until["alex"] = {world.player_tokens["player_test"]: 10_000}
    result = world.apply_intent("player_test", _present("rin_saw_alex"), 1)
    assert result.ok is True


def test_a_game_minute_runs_gossip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GOSSIP_INTERVAL_MINUTES", 1)
    world = World()
    world.add_player("player_test")
    token = open_token(world, None)
    world.player_tokens["player_test"] = token
    _place(world, "mina", "plaza")
    _place(world, "alex", "plaza")
    record_returned_tags(world, "mina", token, ["mina_closed_full"])
    world._tick_minute()
    assert "cash" in world.asked_tags["alex"][token]
