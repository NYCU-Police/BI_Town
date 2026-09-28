"""Daily plans, needs, and night reviews. The decider never touches the network."""

import asyncio

import pytest

from app.config import (
    CAFE_HUNGER_RESTORE_PER_MINUTE,
    EAT_FULLNESS_RESTORE,
    FULLNESS_DECAY_PER_MINUTE,
    HOME_ENERGY_RESTORE_PER_MINUTE,
    REST_ENERGY_PER_MINUTE,
    SLEEP_ENERGY_PER_MINUTE,
    SOCIAL_COMPANY_PER_MINUTE,
    SOCIAL_DECAY_PER_MINUTE,
    TALK_SOCIAL_RESTORE,
)
from app.simulation.llm_session import (
    Decision,
    DecisionJob,
    ReadyDecision,
    build_messages,
    parse_plan,
    plan_schema,
    service_pending,
)
from app.simulation.poi import POIS, home_for
from app.simulation.world import World

STAY = '{"action":"stay","target":"","say":"","thought":""}'
_PLAN = (
    '{"items":['
    '{"time":"07:00","place":"cafe","activity":"order_coffee","reason":"早起喝一杯"},'
    '{"time":"09:00","place":"office","activity":"write_report","reason":"寫預算"},'
    '{"time":"12:00","place":"park","activity":"stroll","reason":"透氣"},'
    '{"time":"18:00","place":"library","activity":"study","reason":"安靜一下"}'
    "]}"
)


def _user(messages: list[dict[str, str]]) -> str:
    return next(item["content"] for item in messages if item["role"] == "user")


def _drain(world: World) -> None:
    assert world.llm is not None
    if world.llm.queue.qsize():
        asyncio.run(service_pending(world.llm))


def _at(world: World, agent_id: str, poi_id: str) -> None:
    assert world.llm is not None
    resident = world.llm.by_id[agent_id]
    place = POIS[poi_id]
    resident.location = poi_id
    resident.target_location = poi_id
    resident.position = place.position
    resident.state = "idle"


def test_plan_schema_limits_place_and_count() -> None:
    schema = plan_schema("mina")
    items = schema["properties"]["items"]
    assert items["minItems"] == 4
    assert items["maxItems"] == 6
    item = items["items"]
    assert item["required"] == ["time", "place", "activity", "reason"]
    assert "mina_home" in item["properties"]["place"]["enum"]
    assert "alex_home" not in item["properties"]["place"]["enum"]
    assert item["properties"]["activity"]["enum"][:3] == ["cook", "rest", "sleep"]
    for activity_id in ("order_coffee", "write_report"):
        assert activity_id in item["properties"]["activity"]["enum"]
    mismatch, problem = parse_plan(
        '{"items":['
        '{"time":"09:00","place":"cafe","activity":"cook","reason":"想煮飯"},'
        '{"time":"10:00","place":"office","activity":"write_report","reason":"寫報告"},'
        '{"time":"12:00","place":"park","activity":"stroll","reason":"透氣"},'
        '{"time":"18:00","place":"library","activity":"study","reason":"安靜"}'
        "]}",
        "mina",
    )
    assert mismatch == []
    assert problem is not None

    short = _PLAN.replace(
        '{"time":"18:00","place":"library","activity":"study","reason":"安靜一下"}',
        "",
    ).replace(",]}", "]}")
    _items, problem = parse_plan(short, "mina")
    assert problem is not None

    stolen = _PLAN.replace(
        '"place":"cafe","activity":"order_coffee"',
        '"place":"alex_home","activity":"cook"',
    )
    _items, problem = parse_plan(stolen, "mina")
    assert problem is not None
    assert "alex_home" in problem

    ok, problem = parse_plan(_PLAN, "mina")
    assert problem is None
    assert len(ok) == 4


def test_needs_decay_and_recover_without_numbers_in_the_prompt() -> None:
    world = World(brain_mode="llm", decider=_stay)
    assert world.llm is not None
    session = world.llm
    session.opening = False
    mina = session.by_id["mina"]
    alex = session.by_id["alex"]
    energy = mina.energy
    fullness = mina.fullness
    social = mina.social

    world.tick()
    assert mina.energy == pytest.approx(energy + HOME_ENERGY_RESTORE_PER_MINUTE)
    assert mina.fullness == pytest.approx(fullness - FULLNESS_DECAY_PER_MINUTE)
    assert mina.social == pytest.approx(social - SOCIAL_DECAY_PER_MINUTE)

    _at(world, "mina", "cafe")
    _at(world, "alex", "cafe")
    mina.fullness = 40
    mina.energy = 20
    mina.social = 40
    alex.social = 40
    session.inbox.append(
        ReadyDecision(
            job=DecisionJob(agent_id="mina", messages=[]),
            decision=Decision(
                action="do",
                target="order_coffee",
                thought="先買咖啡",
            ),
        )
    )
    world.tick()
    assert mina.fullness == pytest.approx(
        40 + EAT_FULLNESS_RESTORE + CAFE_HUNGER_RESTORE_PER_MINUTE
    )
    assert mina.state == "doing"
    assert mina.activity_id == "order_coffee"

    mina.activity_id = "rest"
    mina.activity_remaining = 10
    mina.energy = 50
    world.tick()
    assert mina.energy == pytest.approx(50 + REST_ENERGY_PER_MINUTE)

    mina.state = "doing"
    mina.activity_id = "sleep"
    mina.activity_remaining = 10
    mina.energy = 10
    world.tick()
    assert mina.energy == pytest.approx(10 + SLEEP_ENERGY_PER_MINUTE)

    mina.state = "idle"
    mina.activity_id = ""
    session.inbox.append(
        ReadyDecision(
            job=DecisionJob(agent_id="alex", messages=[]),
            decision=Decision(
                action="talk_to",
                target="mina",
                say="一起拍照",
                thought="想約她",
            ),
        )
    )
    alex.social = 40
    mina.social = 40
    world.tick()
    assert alex.social == pytest.approx(
        40 + TALK_SOCIAL_RESTORE + SOCIAL_COMPANY_PER_MINUTE
    )
    assert mina.social == pytest.approx(
        40 + TALK_SOCIAL_RESTORE + SOCIAL_COMPANY_PER_MINUTE
    )
    assert any("（我說）對 Mina：一起拍照" in item for item in alex.memories)
    assert any("（Alex 說）一起拍照" in item for item in mina.memories)

    mina.energy = 20
    mina.fullness = 40
    mina.social = 40
    prompt = _user(
        build_messages(mina, world.time, session.residents, session.now_minutes)
    )
    body = next(line for line in prompt.splitlines() if line.startswith("身體："))
    assert "你很累" in body
    assert "你有點餓了" in body
    assert "你有點想找人聊聊" in body
    assert not any(char.isdigit() for char in body)


def test_today_plan_is_marked_in_the_situation() -> None:
    world = World(brain_mode="llm", decider=_stay)
    assert world.llm is not None
    mina = world.llm.by_id["mina"]
    mina.plan, problem = parse_plan(_PLAN, "mina")
    assert problem is None
    prompt = _user(build_messages(mina, "09:10", world.llm.residents, 0))
    assert "今天的計畫：" in prompt
    assert "07:00 咖啡廳 點咖啡：早起喝一杯" in prompt
    assert "09:00 辦公室 寫報告：寫預算 ← 現在這項" in prompt
    assert "12:00 公園 散步：透氣" in prompt
    assert "← 現在這項" not in prompt.split("09:00")[0]


def test_night_goes_home_sleeps_and_review_is_in_the_next_plan() -> None:
    reviews = {
        "mina": "預算還沒寫完。",
        "alex": "想找 Mina 拍照。",
        "rin": "圖書館的人還不多。",
    }
    calls: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        user = _user(messages)
        calls.append(user)
        if user.startswith("請安排今天的計畫"):
            return _PLAN
        if "你要睡了" in user:
            for agent_id, sentence in reviews.items():
                if f"id: {agent_id}" in user:
                    return '{"sentences":["' + sentence + '"]}'
        return STAY

    world = World(brain_mode="llm", decider=fake)
    assert world.llm is not None
    session = world.llm
    session.opening = False
    session.plans_due = False
    world.time = "22:00"
    for resident in session.residents:
        _at(world, resident.id, home_for(resident.id).id)

    world.tick()
    assert session.queue.qsize() == 3
    _drain(world)
    assert calls
    assert all("你要睡了" in item for item in calls)
    assert all(not item.startswith("目前狀況") for item in calls)

    world.tick()
    assert all(resident.state == "sleeping" for resident in session.residents)
    assert world.agents["mina"].activity == "睡覺"
    assert world.agents["mina"].state == "doing"
    for agent_id, sentence in reviews.items():
        resident = session.by_id[agent_id]
        assert resident.reviews == [(1, sentence)]
        assert any(f"今日回顧：{sentence}" in item for item in resident.memories)

    calls.clear()
    while world.time != "07:00":
        world.tick()
        assert session.queue.qsize() == 0
        assert all(resident.state == "sleeping" for resident in session.residents)
    assert calls == []
    assert world.day == 2

    world.tick()
    assert all(resident.state == "idle" for resident in session.residents)
    _drain(world)
    plans = [item for item in calls if item.startswith("請安排今天的計畫")]
    decisions = [item for item in calls if item.startswith("目前狀況：")]
    assert len(plans) == 3
    assert len(decisions) == 3
    for agent_id, sentence in reviews.items():
        plan = next(item for item in plans if f"id: {agent_id}" in item)
        decision = next(item for item in decisions if f"id: {agent_id}" in item)
        assert f"第 1 天：{sentence}" in plan
        assert f"第 1 天：{sentence}" in decision
        assert "07:00 咖啡廳 點咖啡：早起喝一杯 ← 現在這項" in decision
    mina = session.by_id["mina"]
    mina.reviews = [
        (1, "舊的一天。"),
        (2, "第二天。"),
        (3, "第三天。"),
        (4, "第四天。"),
    ]
    kept = _user(session._plan_messages(mina, "07:00"))
    assert "第 1 天" not in kept
    assert "第 2 天：第二天。" in kept
    assert "第 4 天：第四天。" in kept


def test_night_away_from_home_walks_back_without_a_decision() -> None:
    calls: list[str] = []

    async def fake(messages: list[dict[str, str]], _schema: dict) -> str:
        calls.append(_user(messages))
        return '{"sentences":["今天就到這裡。"]}'

    world = World(brain_mode="llm", decider=fake)
    assert world.llm is not None
    session = world.llm
    session.opening = False
    session.plans_due = False
    world.time = "22:00"
    _at(world, "mina", "park")
    mina = session.by_id["mina"]
    mina.state = "doing"
    mina.activity_id = "stroll"
    mina.activity_name = "散步"
    mina.activity_remaining = 10

    world.tick()
    assert mina.state == "walking"
    assert mina.target_location == "mina_home"
    assert mina.activity_id == ""
    assert session.queue.qsize() == 2
    _drain(world)
    assert len(calls) == 2
    assert all("你要睡了" in item for item in calls)

    guard = 0
    while mina.state == "walking":
        assert session.queue.qsize() == 0
        world.tick()
        guard += 1
        assert guard < 40
    assert mina.location == "mina_home"
    assert session.queue.qsize() == 1
    _drain(world)
    assert len(calls) == 3
    assert "你要睡了" in calls[-1]
    assert all(not item.startswith("目前狀況") for item in calls)


def test_rules_mode_keeps_its_schedule_at_night() -> None:
    world = World()
    world.time = "18:00"
    result = world.tick()
    mina = world.agents["mina"]
    assert mina.state == "walking"
    assert mina.target_location == "park"
    assert any(
        event.event == "left" and event.agent_id == "mina" for event in result.events
    )

    world.time = "22:00"
    world.tick()
    assert mina.state == "walking"
    assert mina.target_location == "park"
    assert mina.activity == ""

    home = World()
    home.time = "22:00"
    home.tick()
    mina = home.agents["mina"]
    assert mina.state == "idle"
    assert mina.location == "mina_home"
    assert mina.activity == ""


async def _stay(_messages: list[dict[str, str]], _schema: dict) -> str:
    return STAY
