import asyncio
import json

from app.config import ACTIVITY_MINUTES
from app.simulation.llm_session import (
    Decision,
    decision_schema,
    service_pending,
    validate_decision,
)
from app.simulation.poi import activities_for
from app.simulation.world import World

SILENT = '{"action":"stay","target":"","say":"","thought":""}'


def _actor_id(messages: list[dict[str, str]]) -> str:
    user = next(item["content"] for item in messages if item["role"] == "user")
    for agent_id in ("mina", "alex", "rin"):
        if f"id: {agent_id}" in user:
            return agent_id
    raise AssertionError(user)


def _decision(
    action: str,
    target: str = "",
    say: str = "",
    thought: str = "想一下",
) -> str:
    return json.dumps(
        {"action": action, "target": target, "say": say, "thought": thought},
        ensure_ascii=False,
    )


def _drain(world: World) -> None:
    assert world.llm is not None
    if world.llm.queue.qsize():
        asyncio.run(service_pending(world.llm))


def test_do_target_is_limited_to_activities_here() -> None:
    world = World(brain_mode="llm", decider=lambda _m, _s: SILENT)
    assert world.llm is not None
    residents = world.llm.residents
    mina = world.llm.by_id["mina"]

    at_home = decision_schema("mina", residents)
    assert "do" in at_home["properties"]["action"]["enum"]
    assert "order_coffee" not in at_home["properties"]["target"]["enum"]
    assert validate_decision(
        Decision(action="do", target="order_coffee"),
        mina,
        world.llm.by_id,
    )

    mina.location = "cafe"
    at_cafe = decision_schema("mina", residents)
    assert "write_report" not in at_cafe["properties"]["target"]["enum"]
    assert (
        validate_decision(
            Decision(action="do", target="write_report"),
            mina,
            world.llm.by_id,
        )
        is not None
    )
    assert (
        validate_decision(
            Decision(action="do", target="order_coffee"),
            mina,
            world.llm.by_id,
        )
        is None
    )

    mina.location = "alex_home"
    visiting = decision_schema("mina", residents)
    assert "do" not in visiting["properties"]["action"]["enum"]
    assert activities_for("alex_home", "mina") == ()
    problem = validate_decision(
        Decision(action="do", target="cook"),
        mina,
        world.llm.by_id,
    )
    assert problem is not None
    assert (
        validate_decision(
            Decision(action="stay", target="cafe"),
            mina,
            world.llm.by_id,
        )
        is not None
    )


def test_activity_blocks_decisions_and_is_remembered() -> None:
    calls: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        user = next(item["content"] for item in messages if item["role"] == "user")
        if user.startswith("請安排今天的計畫"):
            return (
                '{"items":['
                '{"time":"09:00","place":"cafe","activity":"order_coffee","reason":"醒醒腦"},'
                '{"time":"10:00","place":"office","activity":"write_report","reason":"寫報告"},'
                '{"time":"12:00","place":"park","activity":"stroll","reason":"透氣"},'
                '{"time":"18:00","place":"library","activity":"study","reason":"安靜"}'
                "]}"
            )

        actor = _actor_id(messages)
        calls.append(actor)
        if actor == "mina":
            return _decision("do", "cook", thought="先煮飯")
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    world.tick()
    _drain(world)
    result = world.tick()
    assert world.llm is not None
    mina = world.llm.by_id["mina"]
    assert mina.state == "doing"
    assert mina.activity_name == "煮飯"
    assert mina.activity_remaining == ACTIVITY_MINUTES["cook"] - 1
    activity = [event for event in result.events if event.event == "activity"]
    assert len(activity) == 1
    assert activity[0].agent_id == "mina"
    assert activity[0].location == "mina_home"
    assert activity[0].content == "煮飯"
    assert activity[0].duration_minutes == ACTIVITY_MINUTES["cook"]
    assert any("煮飯" in item for item in mina.memories)

    calls.clear()
    for _ in range(8):
        world.tick()
        _drain(world)
    assert "mina" not in calls
    assert mina.state == "doing"


def test_reply_during_activity_then_continue() -> None:
    replied: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        user = next(item["content"] for item in messages if item["role"] == "user")
        if user.startswith("請安排今天的計畫"):
            return (
                '{"items":['
                '{"time":"09:00","place":"cafe","activity":"order_coffee","reason":"醒醒腦"},'
                '{"time":"10:00","place":"office","activity":"write_report","reason":"寫報告"},'
                '{"time":"12:00","place":"park","activity":"stroll","reason":"透氣"},'
                '{"time":"18:00","place":"library","activity":"study","reason":"安靜"}'
                "]}"
            )

        actor = _actor_id(messages)
        user = next(item["content"] for item in messages if item["role"] == "user")
        if actor == "mina":
            replied.append(user)
            return _decision("stay", say="我在煮飯", thought="先回他")
        if actor == "alex":
            return _decision("talk_to", "mina", "在嗎", "想打招呼")
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    assert world.llm is not None
    meeting = world.llm.by_id["mina"].position
    for resident in world.llm.residents:
        resident.location = "mina_home"
        resident.target_location = "mina_home"
        resident.position = meeting
        resident.state = "idle"
    mina = world.llm.by_id["mina"]
    mina.state = "doing"
    mina.activity_id = "cook"
    mina.activity_name = "煮飯"
    mina.activity_remaining = ACTIVITY_MINUTES["cook"]

    world.tick()
    _drain(world)
    world.tick()
    world.tick()
    _drain(world)
    world.tick()

    assert replied
    assert mina.state == "doing"
    assert mina.activity_id == "cook"
    assert mina.activity_remaining > 0
    said = [
        event
        for event in world.recent_events()
        if event.event == "said" and event.agent_id == "mina"
    ]
    assert said
    assert said[0].content == "我在煮飯"


def test_rules_mode_does_not_emit_activities() -> None:
    world = World()
    result = world.tick()
    assert result.events
    assert all(event.event != "activity" for event in result.events)
    assert world.agents["mina"].state == "walking"
    assert world.agents["mina"].activity == ""
