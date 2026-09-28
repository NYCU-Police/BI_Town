"""Player talk: rules refusal, queue priority, and one model call."""

import asyncio
import json
import time

import pytest

from app import config
from app.models.schemas import Intent, TargetRef
from app.simulation.llm_session import DecisionJob, service_pending
from app.simulation.player_talk import Dossier, open_token
from app.simulation.poi import POIS
from app.simulation.world import World
from app.websocket.manager import manager

_OK = json.dumps(
    {"reply": "我在。", "revealed_fact_ids": ["secret"], "mood": "calm"}
)


def _place(world: World, agent_id: str, poi_id: str) -> None:
    agent = world.agents[agent_id]
    place = POIS[poi_id]
    agent.location = poi_id
    agent.target_location = poi_id
    agent.position = place.position
    agent.state = "idle"


def _world(decider) -> tuple[World, str]:
    world = World(brain_mode="llm", decider=decider)
    world.add_player("player_test")
    _place(world, "player_test", "mina_home")
    _place(world, "mina", "mina_home")
    token = open_token(world, None)
    world.player_tokens["player_test"] = token
    return world, token


def _talk(text: str, seq: int = 1, target: str = "mina") -> Intent:
    return Intent(
        action="talk",
        target=TargetRef(type="agent", id=target),
        text=text,
    )


def test_rules_mode_refuses_without_calling_a_model() -> None:
    world = World()
    world.add_player("player_test")
    result = world.apply_intent(
        "player_test",
        _talk("child porn"),
        client_seq=1,
    )
    assert result.ok is False
    assert result.reason == "npc_unavailable"


def test_talk_requires_the_same_place_and_a_standing_resident() -> None:
    async def fake(_messages, _schema):
        return _OK

    world, _token = _world(fake)
    _place(world, "player_test", "plaza")
    away = world.apply_intent("player_test", _talk("你好"), 1)
    assert away.reason == "not_here"
    _place(world, "player_test", "mina_home")
    world.agents["mina"].state = "walking"
    walking = world.apply_intent("player_test", _talk("你好"), 2)
    assert walking.reason == "not_here"
    world.agents["mina"].state = "idle"
    assert world.llm is not None
    world.llm.by_id["mina"].fullness = 0
    down = world.apply_intent("player_test", _talk("你好"), 3)
    assert down.reason == "collapsed"


def test_length_filter_and_rate_limit() -> None:
    calls = 0

    async def fake(_messages, _schema):
        nonlocal calls
        calls += 1
        return _OK

    world, _token = _world(fake)
    assert world.apply_intent("player_test", _talk("   "), 1).reason == "empty"
    assert world.apply_intent("player_test", _talk("啊" * 201), 2).reason == "too_long"
    blocked = world.apply_intent("player_test", _talk("no child porn"), 3)
    assert blocked.reason == "rejected"
    assert calls == 0
    assert world.llm is not None
    assert world.llm.queue.player_count() == 0


def test_reply_drops_unknown_facts_and_is_unicast() -> None:
    seen: list[str] = []

    async def fake(messages, _schema):
        seen.append(messages[-1]["content"])
        return _OK

    world, token = _world(fake)
    first = world.apply_intent("player_test", _talk("早安"), 4)
    assert first.ok is True
    assert first.events[0].event == "conversing"
    second = world.apply_intent("player_test", _talk("再問一次"), 5)
    assert second.ok is True
    assert second.superseded_seq == 4
    assert second.events == []

    class _Socket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []

        async def send_json(self, payload: dict[str, object]) -> None:
            self.sent.append(payload)

    mine = _Socket()
    other = _Socket()
    manager.socket_by_token[token] = mine  # type: ignore[assignment]
    manager.socket_by_token["other-token"] = other  # type: ignore[assignment]
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    assert len(seen) == 1
    assert "再問一次" in seen[0]
    assert "<player>" in seen[0]
    assert len(world.llm.talk_log) == 1
    assert world.llm.talk_log[0]["client_seq"] == 5
    assert world.llm.talk_log[0]["revealed_fact_ids"] == []
    assert world.llm.talk_log[0]["reason"] is None
    assert mine.sent == [world.llm.talk_log[0]]
    assert other.sent == []
    dossier = world.dossiers[token]
    assert isinstance(dossier, Dossier)
    assert dossier.memory["mina"][-1] == ("resident", "我在。")
    limited = world.apply_intent("player_test", _talk("太快了"), 6)
    assert limited.reason == "talk_limited"


def test_queue_wait_does_not_call_the_model() -> None:
    calls = 0

    async def fake(_messages, _schema):
        nonlocal calls
        calls += 1
        return _OK

    world, token = _world(fake)
    assert world.llm is not None
    job = DecisionJob(
        agent_id="mina",
        messages=[],
        kind="talk",
        token=token,
        client_seq=9,
        player_id="player_test",
        enqueued_at=time.monotonic() - 30.0,
    )
    status, dropped = world.llm.queue.put_player(job)
    assert status == "ok"
    assert dropped is None
    asyncio.run(service_pending(world.llm))
    assert calls == 0
    assert world.llm.talk_log[0]["reason"] == "llm_timeout"
    assert world.llm.talk_log[0]["reply"] == config.DIALOGUE_FALLBACK_REPLY


def test_parse_failure_retries_once_then_falls_back() -> None:
    calls = 0

    async def fake(_messages, _schema):
        nonlocal calls
        calls += 1
        return "not-json"

    world, _token = _world(fake)
    assert world.apply_intent("player_test", _talk("嗯"), 1).ok is True
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    assert calls == 2
    assert world.llm.talk_log[0]["reason"] == "llm_parse"


def test_model_timeout_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DIALOGUE_TIMEOUT_SECONDS", 0.05)
    calls = 0

    async def fake(_messages, _schema):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return _OK

    world, _token = _world(fake)
    assert world.apply_intent("player_test", _talk("等一下"), 1).ok is True
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    assert calls == 1
    assert world.llm.talk_log[0]["reason"] == "llm_timeout"


def test_full_player_queue_is_busy_and_resident_jobs_make_room() -> None:
    async def fake(_messages, _schema):
        return _OK

    world, token = _world(fake)
    assert world.llm is not None
    for index in range(8):
        status, _dropped = world.llm.queue.put_player(
            DecisionJob(
                agent_id=f"r{index}",
                messages=[],
                kind="talk",
                token=f"t{index}",
                client_seq=index,
            )
        )
        assert status == "ok"
    busy = world.apply_intent("player_test", _talk("擠不進去"), 3)
    assert busy.reason == "busy"
    world.llm.queue._players.clear()
    for _index in range(8):
        assert world.llm.queue.put_nowait(
            DecisionJob(agent_id="alex", messages=[], kind="decision")
        )
    opened = world.apply_intent("player_test", _talk("騰個位子"), 4)
    assert opened.ok is True
    assert world.llm.queue.player_count() == 1
    assert any(
        item.decision is not None and item.decision.action == "stay"
        for item in world.llm.inbox
    )
    assert token in world.dossiers


def test_slow_clock_does_not_age_llm_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAME_MINUTES_PER_REAL_SECOND", "0.4")

    async def fake(_messages, _schema):
        return _OK

    world, _token = _world(fake)
    assert world.llm is not None
    world.llm.by_id["mina"].state = "walking"
    world.llm.by_id["mina"].target_location = "cafe"
    before = world.llm.now_minutes
    world.tick()
    assert world.time == "08:00"
    assert world.llm.now_minutes == before
