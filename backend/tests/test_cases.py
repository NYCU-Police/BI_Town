"""Builtin cases, trust, and the allow list."""

import asyncio
import json
import logging

import pytest

from app.config import INITIAL_DAY, TRUST_GIFT_BREAD, TRUST_GIFT_OTHER, TRUST_START
from app.models.schemas import Intent, TargetRef
from app.simulation.cases import (
    allowed_facts,
    case_for_day,
    public_fact_ids,
    solvable,
    structure_errors,
)
from app.simulation.llm_session import service_pending
from app.simulation.player_talk import (
    Dossier,
    note_texts,
    open_token,
    talk_schema,
    talk_system,
)
from app.simulation.poi import POIS
from app.simulation.world import World
from app.websocket.manager import manager

_PUBLIC = "今天開店前，咖啡廳櫃檯的錢盒是空的。"
_MINA = "Mina 說昨天打烊時錢盒是滿的，鎖只有打烊的人會碰。"


def _place(world: World, agent_id: str, poi_id: str) -> None:
    agent = world.agents[agent_id]
    place = POIS[poi_id]
    agent.location = poi_id
    agent.target_location = poi_id
    agent.position = place.position
    agent.state = "idle"


def test_three_builtins_rotate_and_solve() -> None:
    ids = []
    for day in (1, 2, 3, 4):
        case = case_for_day(day)
        assert structure_errors(case) == []
        ids.append(case["id"])
        if day < 4:
            assert solvable(case)
    assert ids == [
        "builtin_cashbox",
        "builtin_torn_notice",
        "builtin_unsigned_letter",
        "builtin_cashbox",
    ]


def test_implicating_fact_without_the_unlock_fails() -> None:
    case = case_for_day(1)
    for fact in case["facts"]:
        if isinstance(fact, dict) and fact.get("implicates") == case["culprit_id"]:
            fact["requires_trust"] = 70
            fact.pop("unlocked_by", None)
    assert solvable(case) is False


def test_evidence_pointing_at_an_unreachable_fact_fails() -> None:
    case = case_for_day(1)
    facts = case["facts"]
    assert isinstance(facts, list)
    by_id = {fact["id"]: fact for fact in facts if isinstance(fact, dict)}
    by_id["alex_left_home"]["requires_trust"] = 70
    by_id["alex_left_home"].pop("unlocked_by", None)
    by_id["rin_saw_alex"]["requires_evidence"] = ["alex_left_home"]
    assert "alex_left_home" in {fact["id"] for fact in facts if isinstance(fact, dict)}
    assert solvable(case) is False


def test_notices_do_not_name_the_culprit() -> None:
    for day in (1, 2, 3):
        case = case_for_day(day)
        brief = str(case["public_brief"])
        culprit = str(case["culprit_id"])
        assert culprit.capitalize() not in brief
        assert culprit not in brief


def test_day_rollover_replaces_the_notebook() -> None:
    world = World()
    token = open_token(world, None)
    dossier = world.dossiers[token]
    assert isinstance(dossier, Dossier)
    dossier.notes.append("mina_closed_full")
    world.time = "23:59"
    world.tick()
    assert world.day == INITIAL_DAY + 1
    assert world.notice_text() == "廣場公告欄今天被人撕了一角。"
    assert dossier.notes == ["board_torn"]
    assert note_texts(world, token) == ["廣場公告欄今天被人撕了一角。"]
    other = open_token(world, None)
    assert world.dossiers[other].notes == ["board_torn"]


def test_notes_stay_private() -> None:
    world = World()
    first = open_token(world, None)
    second = open_token(world, None)
    kept = world.dossiers[first]
    assert isinstance(kept, Dossier)
    kept.remember_facts(["mina_closed_full"])
    assert "mina_closed_full" not in world.dossiers[second].notes
    assert note_texts(world, first) == [_PUBLIC, _MINA]
    assert note_texts(world, second) == [_PUBLIC]


def _give(world: World, item: str) -> None:
    result = world.apply_intent(
        "player_test",
        Intent(
            action="give",
            target=TargetRef(type="agent", id="mina"),
            item=item,
        ),
    )
    assert result.ok is True


def test_gifts_raise_trust_and_talk_points_cap() -> None:
    world = World()
    world.add_player("player_test")
    _place(world, "player_test", "mina_home")
    _place(world, "mina", "mina_home")
    token = open_token(world, None)
    world.player_tokens["player_test"] = token
    world._add_item("player_test", "bread", 1)
    _give(world, "bread")
    dossier = world.dossiers[token]
    assert isinstance(dossier, Dossier)
    assert dossier.trust_of("mina") == TRUST_START + TRUST_GIFT_BREAD

    other = World()
    other.add_player("player_test")
    _place(other, "player_test", "mina_home")
    _place(other, "mina", "mina_home")
    other_token = open_token(other, None)
    other.player_tokens["player_test"] = other_token
    other._add_item("player_test", "wood", 1)
    result = other.apply_intent(
        "player_test",
        Intent(
            action="give",
            target=TargetRef(type="agent", id="mina"),
            item="wood",
        ),
    )
    assert result.ok is True
    wood = other.dossiers[other_token]
    assert isinstance(wood, Dossier)
    assert wood.trust_of("mina") == TRUST_START + TRUST_GIFT_OTHER

    for _index in range(6):
        dossier.add_talk_trust("mina")
    assert dossier.talk_trust_points["mina"] == 10
    dossier.add_trust("mina", TRUST_GIFT_BREAD)
    assert dossier.trust_of("mina") == TRUST_START + TRUST_GIFT_BREAD * 2 + 10


def test_hunger_penalty_hides_the_trust_forty_fact() -> None:
    case = case_for_day(1)
    held = set(public_fact_ids(case))
    hungry = {fact["id"] for fact in allowed_facts(case, "mina", 20, held)}
    fed = {fact["id"] for fact in allowed_facts(case, "mina", 40, held)}
    assert "alex_owes" not in hungry
    assert "mina_closed_full" in hungry
    assert "alex_owes" in fed
    dossier = Dossier()
    dossier.add_trust("mina", 20)
    assert dossier.effective_trust("mina", 10) == 20
    assert dossier.effective_trust("mina", 80) == 40


def test_empty_allow_list_tells_the_model_to_return_nothing() -> None:
    text = talk_system([])
    assert "必須是空陣列" in text
    assert "沒有案件秘密" not in text
    assert talk_schema([])["properties"]["revealed_fact_ids"]["maxItems"] == 0
    enum_schema = talk_schema(["mina_closed_full"])
    revealed = enum_schema["properties"]["revealed_fact_ids"]
    assert revealed["items"]["enum"] == ["mina_closed_full"]
    assert "maxItems" not in revealed


def test_model_ids_outside_the_list_are_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[dict[str, object]] = []

    async def fake(_messages, schema):
        seen.append(schema)
        return json.dumps(
            {
                "reply": "打烊時是滿的。",
                "revealed_fact_ids": ["mina_closed_full", "secret"],
                "mood": "calm",
            }
        )

    world = World(brain_mode="llm", decider=fake)
    world.add_player("player_test")
    _place(world, "player_test", "mina_home")
    _place(world, "mina", "mina_home")
    token = open_token(world, None)
    world.player_tokens["player_test"] = token
    assert world.apply_intent(
        "player_test",
        Intent(
            action="talk",
            target=TargetRef(type="agent", id="mina"),
            text="錢盒呢",
        ),
    ).ok
    assert world.llm is not None

    class _Socket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []

        async def send_json(self, payload: dict[str, object]) -> None:
            self.sent.append(payload)

    manager.socket_by_token[token] = _Socket()  # type: ignore[assignment]
    with caplog.at_level(logging.WARNING):
        asyncio.run(service_pending(world.llm))
    revealed = seen[0]["properties"]["revealed_fact_ids"]
    assert revealed["items"]["enum"] == ["mina_closed_full"]
    assert "resident=mina" in caplog.text
    assert "secret" in caplog.text
    dossier = world.dossiers[token]
    assert isinstance(dossier, Dossier)
    assert dossier.notes == ["cash_missing", "mina_closed_full"]
    assert note_texts(world, token) == [_PUBLIC, _MINA]
    assert dossier.trust_of("mina") == TRUST_START + 2
    assert world.llm.talk_log[0]["revealed_fact_ids"] == ["mina_closed_full"]
