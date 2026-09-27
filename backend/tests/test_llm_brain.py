import asyncio
import logging
import time

from app import state
from app.simulation.llm_session import service_pending
from app.simulation.loop import broadcast_tick
from app.simulation.world import World

STAY = '{"action":"stay","target":"","say":"早安","thought":"先看看周圍"}'


def test_llm_decisions_emit_said_and_thought() -> None:
    calls: list[int] = []

    async def fake(_messages: list[dict[str, str]], _schema: dict) -> str:
        calls.append(1)
        return STAY

    world = World(brain_mode="llm", decider=fake)
    assert {agent.id for agent in world.agent_list()} == {"mina", "alex", "rin"}

    first = world.tick()
    assert first.events == []
    assert calls == []
    assert world.llm is not None
    assert world.llm.queue.qsize() == 3

    asyncio.run(service_pending(world.llm))
    assert len(calls) == 3

    second = world.tick()
    said = [event for event in second.events if event.event == "said"]
    thought = [event for event in second.events if event.event == "thought"]
    assert {event.agent_id for event in said} == {"mina", "alex", "rin"}
    assert {event.content for event in said} == {"早安"}
    assert {event.content for event in thought} == {"先看看周圍"}
    assert world.time == "08:02"


def test_tick_does_not_wait_for_the_model() -> None:
    async def slow(_messages: list[dict[str, str]], _schema: dict) -> str:
        await asyncio.sleep(30)
        return STAY

    world = World(brain_mode="llm", decider=slow)
    started = time.perf_counter()
    world.tick()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert world.time == "08:01"
    assert world.llm is not None
    assert world.llm.queue.qsize() == 3
    assert world.llm.inbox == []


def test_idle_tick_still_broadcasts_time(monkeypatch) -> None:
    sent: list[dict] = []

    async def capture(payload: dict) -> None:
        sent.append(payload)

    monkeypatch.setattr("app.simulation.loop.manager.broadcast", capture)
    world = state.world
    world.time = "10:00"
    for agent in world.agents.values():
        agent.state = "idle"
        agent.location = "office"
        agent.target_location = "office"

    result = world.tick()
    assert result.changed_agents == []
    assert result.events == []
    assert world.time == "10:01"

    asyncio.run(broadcast_tick(result))
    assert sent[0]["type"] == "agent_update"
    assert sent[0]["data"]["day"] == 1
    assert sent[0]["data"]["time"] == "10:01"
    assert sent[0]["data"]["agents"] == []


def _actor_id(messages: list[dict[str, str]]) -> str:
    user = next(item["content"] for item in messages if item["role"] == "user")
    for agent_id in ("mina", "alex", "rin"):
        if f"id: {agent_id}" in user:
            return agent_id
    raise AssertionError(user)


def test_decision_schema_limits_target_to_other_ids() -> None:
    schemas: dict[str, dict] = {}

    async def fake(messages: list[dict[str, str]], schema: dict) -> str:
        schemas[_actor_id(messages)] = schema
        return STAY

    world = World(brain_mode="llm", decider=fake)
    world.tick()
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))

    pois = ["home", "cafe", "office", "park"]
    assert schemas["alex"]["properties"]["target"]["enum"] == [*pois, "mina", "rin", ""]
    assert "alex" not in schemas["alex"]["properties"]["target"]["enum"]
    assert schemas["mina"]["properties"]["target"]["enum"] == [*pois, "alex", "rin", ""]
    assert "mina" not in schemas["mina"]["properties"]["target"]["enum"]
    assert schemas["rin"]["properties"]["target"]["enum"] == [*pois, "alex", "mina", ""]
    assert "rin" not in schemas["rin"]["properties"]["target"]["enum"]


def test_resident_name_target_maps_to_id() -> None:
    calls: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        actor = _actor_id(messages)
        calls.append(actor)
        if actor == "alex":
            return (
                '{"action":"talk_to","target":"Rin","say":"要不要走走",'
                '"thought":"想找 Rin"}'
            )
        return STAY

    world = World(brain_mode="llm", decider=fake)
    world.tick()
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    result = world.tick()

    said = [
        event
        for event in result.events
        if event.event == "said" and event.agent_id == "alex"
    ]
    assert len(said) == 1
    assert said[0].target_agent_id == "rin"
    assert calls.count("alex") == 1


def test_invalid_target_retries_once_then_stays_quietly(caplog) -> None:
    alex_calls: list[list[dict[str, str]]] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        if _actor_id(messages) != "alex":
            return STAY
        alex_calls.append(messages)
        if len(alex_calls) == 1:
            return (
                '{"action":"talk_to","target":"rina","say":"嘿",'
                '"thought":"這不該出現"}'
            )
        return (
            '{"action":"talk_to","target":"rina","say":"再試",'
            '"thought":"還是不該出現"}'
        )

    caplog.set_level(logging.WARNING, logger="app.simulation.llm_session")
    world = World(brain_mode="llm", decider=fake)
    world.tick()
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))
    result = world.tick()

    assert len(alex_calls) == 2
    assert "無法對話的對象 rina" in alex_calls[1][-1]["content"]
    alex_events = [event for event in result.events if event.agent_id == "alex"]
    assert alex_events == []
    assert all("LLM 失敗" not in (event.content or "") for event in result.events)
    assert any("rina" in record.message for record in caplog.records)
