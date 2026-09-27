import asyncio
import json
import logging
import time

from app import state
from app.config import LLM_DIALOGUE_COOLDOWN_MINUTES
from app.simulation.llm_session import service_pending
from app.simulation.loop import broadcast_tick
from app.simulation.poi import POIS
from app.simulation.world import World

STAY = '{"action":"stay","target":"","say":"早安","thought":"先看看周圍"}'
_PLAN = (
    '{"items":['
    '{"time":"08:30","place":"cafe","activity":"order_coffee","reason":"想喝咖啡"},'
    '{"time":"09:30","place":"office","activity":"write_report","reason":"處理工作"},'
    '{"time":"12:30","place":"park","activity":"stroll","reason":"出去走走"},'
    '{"time":"18:00","place":"library","activity":"study","reason":"安靜一下"}'
    "]}"
)


def _maybe_plan(messages: list[dict[str, str]]) -> str | None:
    user = next(item["content"] for item in messages if item["role"] == "user")
    if user.startswith("請安排今天的計畫"):
        return _PLAN
    if user.startswith("現在是第") and "你要睡了" in user:
        return '{"sentences":["今天先這樣。"]}'
    return None


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
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned

        schemas[_actor_id(messages)] = schema
        return STAY

    world = World(brain_mode="llm", decider=fake)
    world.tick()
    assert world.llm is not None
    asyncio.run(service_pending(world.llm))

    pois = list(POIS)
    home_activities = ["cook", "rest", "sleep"]
    assert schemas["alex"]["properties"]["target"]["enum"] == [
        *pois,
        "mina",
        "rin",
        *home_activities,
        "",
    ]
    assert "alex" not in schemas["alex"]["properties"]["target"]["enum"]
    assert schemas["mina"]["properties"]["target"]["enum"] == [
        *pois,
        "alex",
        "rin",
        *home_activities,
        "",
    ]
    assert "mina" not in schemas["mina"]["properties"]["target"]["enum"]
    assert schemas["rin"]["properties"]["target"]["enum"] == [
        *pois,
        "alex",
        "mina",
        *home_activities,
        "",
    ]
    assert "rin" not in schemas["rin"]["properties"]["target"]["enum"]
    for actor_id in ("mina", "alex", "rin"):
        assert schemas[actor_id]["required"] == [
            "action",
            "target",
            "say",
            "thought",
        ]
        assert "do" in schemas[actor_id]["properties"]["action"]["enum"]
        for activity_id in home_activities:
            assert activity_id in schemas[actor_id]["properties"]["target"]["enum"]


def test_resident_name_target_maps_to_id() -> None:
    calls: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        actor = _actor_id(messages)
        calls.append(actor)
        if actor == "alex":
            return (
                '{"action":"talk_to","target":"Rin","say":"要不要走走",'
                '"thought":"想找 Rin"}'
            )
        return STAY

    world = World(brain_mode="llm", decider=fake)
    _gather(world, "cafe")
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
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
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


SILENT = '{"action":"stay","target":"","say":"","thought":""}'
REPEAT_REASON = "你已經說過類似的話，請說新的內容"


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


def _user_text(messages: list[dict[str, str]]) -> str:
    return next(item["content"] for item in messages if item["role"] == "user")


def _gather(world: World, place: str) -> None:
    """Put everyone in one place. Spawn leaves each resident at their own home."""
    assert world.llm is not None
    poi = POIS[place]
    for resident in world.llm.residents:
        resident.location = place
        resident.target_location = place
        resident.position = poi.position
        resident.state = "idle"


def _drain(world: World) -> None:
    assert world.llm is not None
    if world.llm.queue.qsize():
        asyncio.run(service_pending(world.llm))


def test_prompt_names_places_and_recent_lines() -> None:
    prompts: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        actor = _actor_id(messages)
        if actor != "alex":
            return SILENT
        prompts.append(_user_text(messages))
        if len(prompts) == 1:
            return _decision("move_to", "cafe", "我去咖啡廳坐一下", "換個地方")
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    for _ in range(20):
        world.tick()
        _drain(world)
        if len(prompts) >= 2:
            break

    assert len(prompts) >= 2
    first = prompts[0]
    assert "mina_home（Mina 的家）" in first
    assert "alex_home（Alex 的家）" in first
    assert "cafe（咖啡廳）" in first
    assert "office（辦公室）" in first
    assert "park（公園）" in first
    second = prompts[1]
    assert "cafe（咖啡廳）" in second
    assert "你最近說過的話" in second
    assert "我去咖啡廳坐一下" in second


def test_system_prompt_tells_them_to_stop_repeating() -> None:
    captured: list[list[dict[str, str]]] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        captured.append(messages)
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    world.tick()
    _drain(world)
    system = next(item["content"] for item in captured[0] if item["role"] == "system")
    end_talk = (
        "對話沒有新內容、或對方重複同樣的話時，"
        "就結束對話：去別的地方或做自己的事"
    )
    assert end_talk in system
    assert "不要重複自己說過的話，也不要照搬別人說過的話" in system
    assert "你已經在某地點時，不要邀請別人去同一個地點" in system
    reply_first = "有人對你說話而你還沒回應時，優先回應對方，除非你的個性讓你刻意不理"
    assert reply_first in system
    assert "這個世界沒有手機或訊息，只能當面說話" in system
    own_thought = "你的想法只反映你自己的立場與處境，不要把別人說過的話當成自己的想法"
    assert own_thought in system


def test_similar_say_retries_then_stays_silent() -> None:
    calls: list[list[dict[str, str]]] = []
    first = "早安，要不要一起去公園走走"
    echo = "早安，要不要一起去公園走走啊"

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        if _actor_id(messages) != "alex":
            return SILENT
        calls.append(messages)
        utterance = first if len(calls) == 1 else echo
        return _decision("stay", say=utterance, thought="想打招呼")

    world = World(brain_mode="llm", decider=fake)
    world.tick()
    _drain(world)
    world.tick()
    assert world.llm is not None
    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    result = world.tick()

    assert len(calls) == 3
    assert REPEAT_REASON in calls[2][-1]["content"]
    assert "你最近說過的話" in _user_text(calls[1])
    assert first in _user_text(calls[1])
    assert [event for event in result.events if event.event == "said"] == []


def test_pair_cooldown_rejects_talk_then_allows_it() -> None:
    lines = [
        "風把帽子吹走了",
        "工作排到很晚",
        "椅子被人坐滿",
        "這杯飲料涼掉",
        "明天再決定時間",
        "冷卻結束後換話題",
    ]
    cursor = {"i": 0}

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        actor = _actor_id(messages)
        if actor == "mina":
            return SILENT
        say = lines[cursor["i"]]
        cursor["i"] += 1
        other = "rin" if actor == "alex" else "alex"
        return _decision("talk_to", other, say, say)

    world = World(brain_mode="llm", decider=fake)
    _gather(world, "cafe")
    assert world.llm is not None
    said: list[str] = []
    for _ in range(12):
        result = world.tick()
        said.extend(
            event.content or ""
            for event in result.events
            if event.event == "said"
        )
        if len(said) >= 4 and world.llm.dialogue.blocked("alex", "rin"):
            break
        _drain(world)

    assert len(said) == 4
    assert world.llm.dialogue.blocked("alex", "rin")

    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    rejected = world.tick()
    assert [event for event in rejected.events if event.event == "said"] == []

    consumed = 1
    while world.llm.dialogue.blocked("alex", "rin"):
        world.llm.dialogue.tick_cooldowns()
        consumed += 1
        assert consumed <= LLM_DIALOGUE_COOLDOWN_MINUTES
    assert consumed == LLM_DIALOGUE_COOLDOWN_MINUTES

    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    allowed = world.tick()
    resumed = [
        event
        for event in allowed.events
        if event.event == "said" and event.agent_id == "alex"
    ]
    assert len(resumed) == 1
    assert resumed[0].target_agent_id == "rin"
    assert resumed[0].content == "冷卻結束後換話題"


def test_situation_prompt_shows_company_unanswered_and_last_seen() -> None:
    prompts: list[str] = []
    question = "你今天要去公園嗎"

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        actor = _actor_id(messages)
        if actor == "alex":
            prompts.append(_user_text(messages))
        if actor == "rin":
            return _decision("talk_to", "alex", question, "想問他")
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    _gather(world, "rin_home")
    assert world.llm is not None
    world.tick()
    _drain(world)
    world.tick()
    for agent_id in ("alex", "mina"):
        resident = world.llm.by_id[agent_id]
        resident.location = "park"
        resident.target_location = "park"
        resident.state = "idle"
        resident.minutes_here = 8
    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)

    prompt = prompts[-1]
    assert prompt.startswith("目前狀況：")
    assert prompt.index("目前狀況") < prompt.index("最近的記憶")
    assert "你在 park（公園），已經待了 8 分鐘。" in prompt
    assert "Mina 就在你身邊。" in prompt
    assert "這裡只有你" not in prompt
    assert f"Rin 對你說：『{question}』（你還沒回應）" in prompt
    assert "你最後看到 Mina 是在 park（公園）。" in prompt
    assert "你最後看到 Rin 是在 rin_home（Rin 的家）。" in prompt

    world.llm.waiting.discard("alex")
    world.llm.now_minutes += 31
    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    assert "你還沒回應" not in prompts[-1]
    assert "沒有人在等你回應。" in prompts[-1]


def test_repeated_thought_retries() -> None:
    calls: list[list[dict[str, str]]] = []
    first = "她怎麼還沒到公園"
    echo = "她怎麼還沒到公園啊"
    reason = "請換個角度想想現在的處境"

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        if _actor_id(messages) != "alex":
            return SILENT
        calls.append(messages)
        thought = first if len(calls) == 1 else echo
        return _decision("stay", say="", thought=thought)

    world = World(brain_mode="llm", decider=fake)
    assert world.llm is not None
    world.tick()
    _drain(world)
    world.tick()
    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    result = world.tick()

    assert len(calls) == 3
    assert reason in calls[2][-1]["content"]
    thoughts = [
        event
        for event in result.events
        if event.event == "thought" and event.agent_id == "alex"
    ]
    assert thoughts == []


def test_llm_think_flag_is_sent_to_ollama(monkeypatch) -> None:
    from app.simulation.llm_session import OllamaDecider

    captured: list[dict] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"message": {"content": SILENT}}

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, json: dict) -> _Response:
            captured.append(json)
            return _Response()

    monkeypatch.setattr("app.simulation.llm_session.httpx.AsyncClient", _Client)

    async def ask() -> None:
        decider = OllamaDecider.from_env()
        await decider([{"role": "user", "content": "hi"}], {"type": "object"})

    monkeypatch.delenv("LLM_THINK", raising=False)
    asyncio.run(ask())
    monkeypatch.setenv("LLM_THINK", "true")
    asyncio.run(ask())
    monkeypatch.setenv("LLM_THINK", "false")
    asyncio.run(ask())

    assert [body["think"] for body in captured] == [False, True, False]


def test_departure_sighting_is_replaced_when_met_again() -> None:
    from app.models.schemas import Position
    from app.simulation.poi import POIS

    prompts: list[str] = []
    leave = {"ready": False}
    left = "你最後看到 Mina 從 park（公園）離開，往 office（辦公室）去。"
    met = "你最後看到 Mina 是在 office（辦公室）。"

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        actor = _actor_id(messages)
        if actor == "alex":
            prompts.append(_user_text(messages))
        if actor == "mina" and leave["ready"]:
            leave["ready"] = False
            return _decision("move_to", "office", say="", thought="換去辦公室")
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    assert world.llm is not None
    world.tick()
    _drain(world)
    world.tick()

    park = POIS["park"]
    for agent_id in ("mina", "alex"):
        resident = world.llm.by_id[agent_id]
        resident.location = "park"
        resident.target_location = "park"
        resident.state = "idle"
        resident.position = Position(x=park.x, y=park.y)
    leave["ready"] = True
    world.llm.waiting.discard("mina")
    world.llm._request(
        world.llm.by_id["mina"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    world.tick()

    world.llm.waiting.discard("alex")
    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    assert left in prompts[-1]

    office = POIS["office"]
    alex = world.llm.by_id["alex"]
    alex.location = "office"
    alex.target_location = "office"
    alex.state = "idle"
    alex.position = Position(x=office.x, y=office.y)
    arrived = False
    for _ in range(30):
        world.tick()
        _drain(world)
        mina = world.llm.by_id["mina"]
        if mina.state == "idle" and mina.location == "office":
            arrived = True
            break
    assert arrived

    world.llm.waiting.discard("alex")
    world.llm._request(
        world.llm.by_id["alex"],
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    assert met in prompts[-1]
    assert left not in prompts[-1]
    sight = alex.last_seen["mina"]
    assert sight.place == "office"
    assert not sight.destination


def test_opening_can_leave_but_arrival_stays_for_twenty_minutes() -> None:
    from app.config import INITIAL_DAY, INITIAL_TIME, LLM_MIN_STAY_MINUTES
    from app.simulation.clock import advance_clock

    phase = {"name": "opening"}
    soon_calls: list[list[dict[str, str]]] = []
    leave_thought = "坐不住想去公園"

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        if _actor_id(messages) != "alex":
            return SILENT
        name = phase["name"]
        if name == "opening":
            return _decision("move_to", "cafe", say="", thought="先去咖啡廳")
        if name == "soon":
            soon_calls.append(messages)
            return _decision("move_to", "park", say="", thought=leave_thought)
        if name == "later":
            return _decision("move_to", "park", say="", thought="待夠了再走")
        return SILENT

    world = World(brain_mode="llm", decider=fake)
    assert world.llm is not None
    world.tick()
    _drain(world)
    opened = world.tick()
    alex = world.llm.by_id["alex"]
    assert alex.state == "walking"
    assert alex.target_location == "cafe"
    assert any(
        event.event == "left" and event.agent_id == "alex" for event in opened.events
    )

    phase["name"] = "soon"
    arrived = False
    for _ in range(40):
        world.tick()
        _drain(world)
        if alex.state == "idle" and alex.location == "cafe":
            arrived = True
            break
    assert arrived
    assert len(soon_calls) == 1
    assert "上次的決定無效" not in soon_calls[0][-1]["content"]
    assert alex.stay_until_minute == world.llm.now_minutes - 1 + LLM_MIN_STAY_MINUTES
    _day, until = advance_clock(INITIAL_DAY, INITIAL_TIME, alex.stay_until_minute or 0)
    prompt = _user_text(soon_calls[0])
    assert f"你剛到 cafe（咖啡廳），至少會待到 {until}" in prompt

    held = world.tick()
    assert alex.state == "idle"
    assert alex.location == "cafe"
    assert alex.target_location != "park"
    thoughts = [
        event.content
        for event in held.events
        if event.event == "thought" and event.agent_id == "alex"
    ]
    assert thoughts == [leave_thought]
    assert [event for event in held.events if event.event == "left"] == []

    phase["name"] = "quiet"
    while world.llm.now_minutes < (alex.stay_until_minute or 0):
        world.tick()
        _drain(world)
    world.llm.inbox.clear()
    world.llm.waiting.discard("alex")
    assert alex.state == "idle"
    assert world.llm.now_minutes >= (alex.stay_until_minute or 0)

    phase["name"] = "later"
    world.llm._request(
        alex,
        world.time,
        is_reply=False,
        partner=None,
    )
    _drain(world)
    left = world.tick()
    assert alex.state == "walking"
    assert alex.target_location == "park"
    assert any(
        event.event == "left" and event.agent_id == "alex" for event in left.events
    )


def test_repeat_prompts_and_thought_threshold() -> None:
    near_a = "窗外的人越走越慢"
    near_b = "窗外的人越走越遠"
    say_calls: list[list[dict[str, str]]] = []

    async def fake_say(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        if _actor_id(messages) != "alex":
            return SILENT
        say_calls.append(messages)
        utterance = near_a if len(say_calls) == 1 else near_b
        thought = f"第{len(say_calls)}次"
        return _decision("stay", say=utterance, thought=thought)

    say_world = World(brain_mode="llm", decider=fake_say)
    assert say_world.llm is not None
    say_world.tick()
    _drain(say_world)
    say_world.tick()
    say_world.llm._request(
        say_world.llm.by_id["alex"],
        say_world.time,
        is_reply=False,
        partner=None,
    )
    _drain(say_world)
    say_world.tick()
    assert len(say_calls) == 3
    retry = say_calls[2][-1]["content"]
    assert REPEAT_REASON in retry
    assert "或結束對話去做別的事" not in retry

    thought_calls: list[list[dict[str, str]]] = []

    async def fake_thought(messages: list[dict[str, str]], _schema: dict) -> str:
        planned = _maybe_plan(messages)
        if planned is not None:
            return planned
        if _actor_id(messages) != "alex":
            return SILENT
        thought_calls.append(messages)
        thought = near_a if len(thought_calls) == 1 else near_b
        return _decision("stay", say="", thought=thought)

    thought_world = World(brain_mode="llm", decider=fake_thought)
    assert thought_world.llm is not None
    thought_world.tick()
    _drain(thought_world)
    thought_world.tick()
    thought_world.llm._request(
        thought_world.llm.by_id["alex"],
        thought_world.time,
        is_reply=False,
        partner=None,
    )
    _drain(thought_world)
    result = thought_world.tick()
    assert len(thought_calls) == 2
    assert "上次的決定無效" not in thought_calls[1][-1]["content"]
    thoughts = [
        event.content
        for event in result.events
        if event.event == "thought" and event.agent_id == "alex"
    ]
    assert thoughts == [near_b]
    assert "離開" not in "請換個角度想想現在的處境"
