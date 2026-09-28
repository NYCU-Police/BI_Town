"""LLM residents for BRAIN_MODE=llm. Not imported by the rules world.

Decision text is ported from the POC. This module does not import poc.
Calls go through one async worker so World.tick() never waits on the model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Literal

import httpx
import opencc
from pydantic import BaseModel, Field

from app import config as app_config
from app.config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_OLLAMA_URL,
    EAT_FULLNESS_RESTORE,
    EATING_ACTIVITIES,
    GAME_MINUTES_PER_TICK,
    INITIAL_DAY,
    INITIAL_TIME,
    LLM_BACKGROUND_TIMEOUT_SECONDS,
    LLM_DECISION_MAX_PER_ROUND,
    LLM_DIALOGUE_COOLDOWN_MINUTES,
    LLM_IDLE_DECISION_MINUTES,
    LLM_IDLE_DECISION_MINUTES_BUSY,
    LLM_MAX_CONSECUTIVE_DIALOGUE,
    LLM_MEMORY_PROMPT_LIMIT,
    LLM_MEMORY_STORE_LIMIT,
    LLM_MIN_STAY_MINUTES,
    LLM_QUEUE_MAX,
    LLM_RECENT_SAY_LIMIT,
    LLM_RECENT_SAY_PROMPT_LIMIT,
    LLM_RECENT_THOUGHT_LIMIT,
    LLM_SAY_SIMILARITY,
    LLM_TEMPERATURE,
    LLM_THOUGHT_SIMILARITY,
    LLM_UNANSWERED_MINUTES,
    NEED_EXHAUSTED,
    NEED_HUNGRY,
    NEED_LONELY,
    NEED_LONELY_HINT,
    NEED_MAX,
    NEED_PECKISH,
    NEED_START_ENERGY,
    NEED_START_FULLNESS,
    NEED_START_SOCIAL,
    NEED_TIRED,
    PLAN_MAX_ITEMS,
    PLAN_MIN_ITEMS,
    RESTING_ACTIVITIES,
    REVIEW_HISTORY_DAYS,
    SLEEP_HOUR,
    SLEEPING_ACTIVITIES,
    TALK_SOCIAL_RESTORE,
    WAKE_HOUR,
    current_llm_think,
)
from app.models.schemas import Agent, Position, WorldEvent
from app.simulation.clock import advance_clock
from app.simulation.fake_agent import move_agent
from app.simulation.job_queue import JobQueue
from app.simulation.needs import NeedValues, is_collapsed, tick_need_values
from app.simulation.poi import POIS, activities_for, home_for

logger = logging.getLogger(__name__)

# s2twp: simplified to Taiwan traditional, including phrase-level words.
_TO_TRADITIONAL = opencc.OpenCC("s2twp")

Decider = Callable[[list[dict[str, str]], dict[str, Any]], Awaitable[str]]


def to_traditional(text: str) -> str:
    if text == "":
        return ""
    return _TO_TRADITIONAL.convert(text)

SYSTEM_PROMPT = """\
你是小鎮居民。只輸出一個 JSON 物件，不要加其他文字。
想法（thought）與對話（say）必須使用繁體中文。
action 只能是 move_to、stay、talk_to、do。
move_to 的 target 必須是使用者訊息裡列出的地點 id。
do 的 target 必須是你目前地點可以做的活動 id。
talk_to 的 target 必須是同地點、且沒有在移動的另一位居民 id。
stay 的 target 必須是空字串。
沒有要說的話時，say 必須是空字串。
thought 只寫一句內心話。
想見的人不在這裡時，可以根據記憶去他可能在的地方找他。
不要重複上一次的想法，想法要反映現在的處境。
對話沒有新內容、或對方重複同樣的話時，就結束對話：去別的地方或做自己的事。
不要重複自己說過的話，也不要照搬別人說過的話。
你已經在某地點時，不要邀請別人去同一個地點。
有人對你說話而你還沒回應時，優先回應對方，除非你的個性讓你刻意不理。
這個世界沒有手機或訊息，只能當面說話。
你的想法只反映你自己的立場與處境，不要把別人說過的話當成自己的想法。
"""

REPEAT_SAY = "你已經說過類似的話，請說新的內容"
REPEAT_THOUGHT = "請換個角度想想現在的處境"


@dataclass
class DirectedLine:
    speaker_id: str
    text: str
    minute: int


@dataclass
class Sighting:
    place: str
    destination: str = ""


class Decision(BaseModel):
    action: Literal["move_to", "stay", "talk_to", "do"] = Field(
        description="move_to、stay、talk_to 或 do"
    )
    target: str = Field(default="", description="POI id、居民 id，或空字串")
    say: str = Field(default="", description="說出口的繁體中文；不說則空字串")
    thought: str = Field(default="", description="一句繁體中文內心話")


class PlanItem(BaseModel):
    time: str
    place: str
    activity: str
    reason: str


class DailyPlan(BaseModel):
    items: list[PlanItem]


class DayReview(BaseModel):
    sentences: list[str]


@dataclass
class Resident:
    id: str
    name: str
    persona: str
    location: str
    position: Position
    state: str = "idle"
    target_location: str = ""
    idle_minutes: int = 0
    minutes_here: int = 0
    stay_until_minute: int | None = None
    last_thought: str = ""
    memories: deque[str] = field(
        default_factory=lambda: deque(maxlen=LLM_MEMORY_STORE_LIMIT)
    )
    recent_says: deque[str] = field(
        default_factory=lambda: deque(maxlen=LLM_RECENT_SAY_LIMIT)
    )
    recent_thoughts: deque[str] = field(
        default_factory=lambda: deque(maxlen=LLM_RECENT_THOUGHT_LIMIT)
    )
    heard: list[DirectedLine] = field(default_factory=list)
    last_seen: dict[str, Sighting] = field(default_factory=dict)
    activity_id: str = ""
    activity_name: str = ""
    activity_remaining: int = 0
    energy: float = NEED_START_ENERGY
    fullness: float = NEED_START_FULLNESS
    social: float = NEED_START_SOCIAL
    plan: list[PlanItem] = field(default_factory=list)
    reviews: list[tuple[int, str]] = field(default_factory=list)
    pending_opening_decision: bool = False
    reviewed_today: bool = False
    review_pending: bool = False
    collapsed: bool = False

    def remember(self, time_str: str, item: str) -> None:
        self.memories.append(f"[{time_str}] {item}")

    def as_agent(self) -> Agent:
        if self.state == "walking":
            state: Literal["idle", "walking", "doing"] = "walking"
        elif self.state == "doing":
            state = "doing"
        elif self.state == "sleeping":
            state = "doing"
        else:
            state = "idle"
        if self.state == "sleeping":
            activity = "睡覺"
        elif state == "doing":
            activity = self.activity_name
        else:
            activity = ""
        return Agent(
            id=self.id,
            name=self.name,
            position=self.position,
            location=self.location,
            target_location=self.target_location,
            state=state,
            activity=activity,
        )


def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    if left_id < right_id:
        return (left_id, right_id)
    return (right_id, left_id)


@dataclass
class DialogueTracker:
    counts: dict[tuple[str, str], int] = field(default_factory=dict)
    remaining: dict[tuple[str, str], int] = field(default_factory=dict)
    fresh: set[tuple[str, str]] = field(default_factory=set)
    reply_next: dict[str, str] = field(default_factory=dict)

    def blocked(self, actor_id: str, other_id: str) -> str | None:
        if pair_key(actor_id, other_id) not in self.remaining:
            return None
        return (
            f"連續對話已達 {LLM_MAX_CONSECUTIVE_DIALOGUE} 句，"
            f"{LLM_DIALOGUE_COOLDOWN_MINUTES} 分鐘內不能再對話"
        )

    def tick_cooldowns(self) -> None:
        for key in list(self.remaining):
            if key in self.fresh:
                continue
            self.remaining[key] -= GAME_MINUTES_PER_TICK
            if self.remaining[key] <= 0:
                del self.remaining[key]
        self.fresh.clear()

    def finish_talk(self, actor_id: str, other_id: str) -> None:
        key = pair_key(actor_id, other_id)
        for other_key in list(self.counts):
            if actor_id in other_key and other_key != key:
                del self.counts[other_key]
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        self.reply_next.pop(actor_id, None)
        if count >= LLM_MAX_CONSECUTIVE_DIALOGUE:
            self.remaining[key] = LLM_DIALOGUE_COOLDOWN_MINUTES
            self.fresh.add(key)
            del self.counts[key]
            self.reply_next = {
                listener: speaker
                for listener, speaker in self.reply_next.items()
                if pair_key(listener, speaker) != key
            }
            return
        self.reply_next[other_id] = actor_id

    def abandon(self, actor_id: str, partner_id: str | None) -> None:
        if partner_id is None:
            return
        self.counts.pop(pair_key(actor_id, partner_id), None)
        self.reply_next.pop(actor_id, None)

    def drop_pair(self, actor_id: str, partner_id: str) -> None:
        if not partner_id:
            return
        self.counts.pop(pair_key(actor_id, partner_id), None)


def _at_home(resident_id: str, name: str, persona: str) -> Resident:
    home = home_for(resident_id)
    return Resident(
        id=resident_id,
        name=name,
        persona=persona,
        location=home.id,
        position=home.position,
        target_location=home.id,
    )


def spawn_residents() -> list[Resident]:
    return [
        _at_home(
            "mina",
            "Mina",
            "你是辦公室的會計，負責小鎮的年度預算報告，星期五截止。"
            "你做事有計畫，每天早上習慣到咖啡廳買咖啡。"
            "你害怕被排除在外，但不會先承認。",
        ),
        _at_home(
            "alex",
            "Alex",
            "你是自由攝影師，想拍一組「小鎮人物」照片，需要說服別人當模特兒。"
            "你怕無聊，愛拉人出門。"
            "你對 Mina 有好感，但總用玩笑掩飾。",
        ),
        _at_home(
            "rin",
            "Rin",
            "你剛搬來，在圖書館找到兼職。"
            "你話不多，會記住別人說過的話，並在之後提起。"
            "你不喜歡被敷衍，正在觀察誰值得信任。",
        ),
    ]


class OllamaDecider:
    """One Ollama /api/chat call. The worker never runs two of these at once."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        *,
        think: bool = False,
    ) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._timeout = timeout
        self._think = think

    @classmethod
    def from_env(cls) -> OllamaDecider:
        raw_timeout = os.environ.get("LLM_TIMEOUT", "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_LLM_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_LLM_TIMEOUT_SECONDS
        if timeout <= 0:
            timeout = DEFAULT_LLM_TIMEOUT_SECONDS
        base_url = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL).strip()
        model = os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL).strip()
        return cls(
            base_url=base_url or DEFAULT_OLLAMA_URL,
            model=model or DEFAULT_LLM_MODEL,
            timeout=timeout,
            think=current_llm_think(),
        )

    async def __call__(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
    ) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url,
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "think": self._think,
                    "format": schema,
                    "options": {"temperature": LLM_TEMPERATURE},
                },
            )
            response.raise_for_status()
            body = response.json()
        message = body.get("message")
        if not isinstance(message, dict):
            raise ValueError("Ollama 回應缺少 message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama 回應缺少 content")
        return content


def parse_decision(raw: str) -> Decision:
    text = raw.strip()
    if text.startswith("```"):
        lines = [
            line for line in text.splitlines() if not line.strip().startswith("```")
        ]
        text = "\n".join(lines).strip()
    decision = Decision.model_validate_json(text)
    return decision.model_copy(
        update={
            "say": to_traditional(decision.say),
            "thought": to_traditional(decision.thought),
        }
    )


def target_enum(actor_id: str, residents: list[Resident]) -> list[str]:
    choices = [poi_id for poi_id in POIS if poi_id != actor_id]
    others = sorted(resident.id for resident in residents if resident.id != actor_id)
    for other_id in others:
        if other_id not in choices:
            choices.append(other_id)
    choices.append("")
    return choices


def _actor(actor_id: str, residents: list[Resident]) -> Resident:
    for resident in residents:
        if resident.id == actor_id:
            return resident
    raise KeyError(actor_id)


def decision_schema(actor_id: str, residents: list[Resident]) -> dict[str, Any]:
    """Flat schema. Ollama drops fields when the schema uses oneOf or const."""
    actor = _actor(actor_id, residents)
    places = [poi_id for poi_id in POIS]
    people = sorted(
        resident.id for resident in residents if resident.id != actor_id
    )
    local = [activity.id for activity in activities_for(actor.location, actor.id)]
    actions = ["move_to", "stay", "talk_to"]
    if local:
        actions.append("do")
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": actions},
            "target": {"type": "string", "enum": [*places, *people, *local, ""]},
            "say": {"type": "string"},
            "thought": {"type": "string"},
        },
        "required": ["action", "target", "say", "thought"],
    }


def plan_schema(actor_id: str) -> dict[str, Any]:
    places: list[str] = []
    activities: list[str] = []
    for poi_id in POIS:
        local = [activity.id for activity in activities_for(poi_id, actor_id)]
        if not local:
            continue
        places.append(poi_id)
        for activity_id in local:
            if activity_id not in activities:
                activities.append(activity_id)
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": PLAN_MIN_ITEMS,
                "maxItems": PLAN_MAX_ITEMS,
                "items": {
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                        "place": {"type": "string", "enum": places},
                        "activity": {"type": "string", "enum": activities},
                        "reason": {"type": "string"},
                    },
                    "required": ["time", "place", "activity", "reason"],
                },
            }
        },
        "required": ["items"],
    }


def review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "sentences": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"type": "string"},
            }
        },
        "required": ["sentences"],
    }


def _load_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = [
            line for line in text.splitlines() if not line.strip().startswith("```")
        ]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def parse_plan(raw: str, actor_id: str) -> tuple[list[PlanItem], str | None]:
    data = _load_json(raw)
    if data is None or "action" in data:
        return [], "這不是今天的計畫"
    try:
        plan = DailyPlan.model_validate(data)
    except Exception:
        return [], "計畫格式不對"
    if not PLAN_MIN_ITEMS <= len(plan.items) <= PLAN_MAX_ITEMS:
        return [], f"計畫要有 {PLAN_MIN_ITEMS} 到 {PLAN_MAX_ITEMS} 項"
    for item in plan.items:
        if _clock_minutes(item.time) is None:
            return [], f"時間格式不對 {item.time}"
        allowed = {activity.id for activity in activities_for(item.place, actor_id)}
        if item.place not in POIS or item.activity not in allowed:
            return [], f"{item.place} 不能做 {item.activity}"
        if not item.reason.strip():
            return [], "每一項都要有理由"
    return plan.items, None


def parse_review(raw: str) -> tuple[str, str | None]:
    data = _load_json(raw)
    if data is None or "action" in data:
        return "", "這不是今日回顧"
    sentences = data.get("sentences")
    if not isinstance(sentences, list) or not 1 <= len(sentences) <= 3:
        return "", "回顧要有 1 到 3 句"
    parts: list[str] = []
    for sentence in sentences:
        if not isinstance(sentence, str) or not sentence.strip():
            return "", "回顧要有 1 到 3 句"
        text = sentence.strip()
        if text[-1] not in "。！？":
            text += "。"
        parts.append(text)
    return "".join(parts), None


def coerce_target(
    decision: Decision,
    actor: Resident,
    residents: list[Resident],
) -> Decision:
    allowed = set(target_enum(actor.id, residents))
    target = decision.target.strip()
    if target in allowed:
        if target == decision.target:
            return decision
        return decision.model_copy(update={"target": target})
    folded = target.casefold()
    matches = [
        resident
        for resident in residents
        if resident.id != actor.id and resident.name.casefold() == folded
    ]
    if len(matches) == 1:
        return decision.model_copy(update={"target": matches[0].id})
    return decision


def place_name(poi_id: str) -> str:
    poi = POIS.get(poi_id)
    if poi is None:
        return poi_id
    return f"{poi_id}（{poi.name}）"


def label_places(text: str) -> str:
    labeled = text
    for poi_id, poi in POIS.items():
        token = f"{poi_id}（{poi.name}）"
        labeled = labeled.replace(token, f"\x00{poi_id}\x00")
    for poi_id in sorted(POIS, key=len, reverse=True):
        labeled = labeled.replace(poi_id, place_name(poi_id))
    for poi_id, poi in POIS.items():
        labeled = labeled.replace(f"\x00{poi_id}\x00", f"{poi_id}（{poi.name}）")
    return labeled


def _too_similar(
    text: str,
    previous: list[str],
    reason: str,
    threshold: float,
) -> str | None:
    utterance = text.strip()
    if not utterance:
        return None
    for earlier in previous:
        ratio = SequenceMatcher(None, utterance, earlier).ratio()
        if ratio >= threshold:
            return reason
    return None


def repeated_say(actor: Resident, say: str) -> str | None:
    return _too_similar(say, list(actor.recent_says), REPEAT_SAY, LLM_SAY_SIMILARITY)


def repeated_thought(actor: Resident, thought: str) -> str | None:
    return _too_similar(
        thought,
        list(actor.recent_thoughts),
        REPEAT_THOUGHT,
        LLM_THOUGHT_SIMILARITY,
    )


def must_stay(actor: Resident, now_minutes: int) -> bool:
    until = actor.stay_until_minute
    return until is not None and now_minutes < until


def hold_departure(decision: Decision, actor: Resident, now_minutes: int) -> Decision:
    """Arrival lock is not a failure: keep the thought and do not retry."""
    if decision.action != "move_to" or not must_stay(actor, now_minutes):
        return decision
    return decision.model_copy(update={"action": "stay", "target": ""})


def stay_until_clock(until_minute: int) -> str:
    _day, clock = advance_clock(INITIAL_DAY, INITIAL_TIME, until_minute)
    return clock


def people_here(actor: Resident, residents: list[Resident]) -> list[Resident]:
    others = [
        other
        for other in residents
        if other.id != actor.id
        and other.state in {"idle", "doing"}
        and other.location == actor.location
    ]
    others.sort(key=lambda other: other.id)
    return others


def situation_text(
    actor: Resident,
    residents: list[Resident],
    now_minutes: int,
) -> str:
    lines = [
        f"你在 {place_name(actor.location)}，已經待了 {actor.minutes_here} 分鐘。",
    ]
    until = actor.stay_until_minute
    if until is not None and now_minutes < until:
        lines.append(
            f"你剛到 {place_name(actor.location)}，至少會待到 {stay_until_clock(until)}"
        )
    company = people_here(actor, residents)
    if company:
        for other in company:
            lines.append(f"{other.name} 就在你身邊。")
    else:
        lines.append("這裡只有你。")
    names = {resident.id: resident.name for resident in residents}
    pending = [
        line
        for line in actor.heard
        if now_minutes - line.minute <= LLM_UNANSWERED_MINUTES
    ]
    if pending:
        for line in pending:
            speaker = names.get(line.speaker_id, line.speaker_id)
            lines.append(f"{speaker} 對你說：『{line.text}』（你還沒回應）")
    else:
        lines.append("沒有人在等你回應。")
    company_ids = {other.id for other in company}
    others = [resident for resident in residents if resident.id != actor.id]
    others.sort(key=lambda resident: resident.id)
    for other in others:
        if other.id in company_ids:
            lines.append(f"你最後看到 {other.name} 是在 {place_name(actor.location)}。")
            continue
        seen = actor.last_seen.get(other.id)
        if seen is None:
            lines.append(f"你還沒看到 {other.name}。")
        elif seen.destination:
            origin = place_name(seen.place)
            dest = place_name(seen.destination)
            lines.append(
                f"你最後看到 {other.name} 從 {origin}離開，往 {dest}去。"
            )
        else:
            lines.append(f"你最後看到 {other.name} 是在 {place_name(seen.place)}。")
    return "\n".join(f"- {line}" for line in lines)


_CLOCK = re.compile(r"^(\d{2}):(\d{2})$")


def _clock_minutes(time_str: str) -> int | None:
    match = _CLOCK.match(time_str.strip())
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _is_night(time_str: str) -> bool:
    minutes = _clock_minutes(time_str)
    if minutes is None:
        return False
    return minutes >= SLEEP_HOUR * 60 or minutes < WAKE_HOUR * 60


def _clamp_need(value: float) -> float:
    return min(NEED_MAX, max(0.0, value))


def _share_company(actor: Resident, other: Resident) -> None:
    actor.social = _clamp_need(actor.social + TALK_SOCIAL_RESTORE)
    other.social = _clamp_need(other.social + TALK_SOCIAL_RESTORE)


def _activity_label(activity_id: str) -> str:
    for poi in POIS.values():
        for activity in poi.activities:
            if activity.id == activity_id:
                return activity.name
    return activity_id


def _body_line(actor: Resident) -> str:
    phrases: list[str] = []
    if actor.energy < NEED_EXHAUSTED:
        phrases.append("你很累")
    elif actor.energy < NEED_TIRED:
        phrases.append("你有點累")
    if actor.fullness < NEED_HUNGRY:
        phrases.append("你很餓")
    elif actor.fullness < NEED_PECKISH:
        phrases.append("你有點餓了")
    if actor.social < NEED_LONELY:
        phrases.append("你很想找人說話")
    elif actor.social < NEED_LONELY_HINT:
        phrases.append("你有點想找人聊聊")
    if not phrases:
        return ""
    return "身體：" + "，".join(phrases) + "。"


def _plan_block(actor: Resident, time_str: str) -> str:
    if not actor.plan:
        return "今天的計畫：還沒排。"
    now = _clock_minutes(time_str)
    current = None
    if now is not None:
        for index, item in enumerate(actor.plan):
            item_minutes = _clock_minutes(item.time)
            if item_minutes is not None and item_minutes <= now:
                current = index
    rows: list[str] = []
    for index, item in enumerate(actor.plan):
        place = POIS[item.place].name if item.place in POIS else item.place
        mark = " ← 現在這項" if index == current else ""
        label = _activity_label(item.activity)
        rows.append(f"- {item.time} {place} {label}：{item.reason}{mark}")
    return "今天的計畫：\n" + "\n".join(rows)


def _memory_text(actor: Resident) -> str:
    recent = list(actor.memories)[-LLM_MEMORY_PROMPT_LIMIT:]
    if not recent:
        return "- （還沒有記憶）"
    return "\n".join(f"- {item}" for item in recent)


def _review_block(actor: Resident) -> str:
    recent = actor.reviews[-REVIEW_HISTORY_DAYS:]
    if not recent:
        return "- （還沒有）"
    return "\n".join(f"- 第 {day} 天：{text}" for day, text in recent)


def _activity_prompt(actor: Resident) -> str:
    available = activities_for(actor.location, actor.id)
    if not available:
        return "這裡沒有你可以做的活動。"
    listed = "、".join(
        f"{activity.name}（{activity.id}）" for activity in available
    )
    return f"這裡可以做：{listed}。"


def build_messages(
    actor: Resident,
    time_str: str,
    residents: list[Resident],
    now_minutes: int = 0,
) -> list[dict[str, str]]:
    roster = "、".join(
        f"{other.id}（{other.name}）" for other in residents if other.id != actor.id
    )
    company = people_here(actor, residents)
    if company:
        here = "、".join(f"{other.id}（{other.name}）" for other in company)
    else:
        here = "沒有其他人"
    recent = list(actor.memories)[-LLM_MEMORY_PROMPT_LIMIT:]
    if recent:
        memory_text = "\n".join(f"- {label_places(item)}" for item in recent)
    else:
        memory_text = "- （還沒有記憶）"
    spoken = list(actor.recent_says)[-LLM_RECENT_SAY_PROMPT_LIMIT:]
    if spoken:
        spoken_text = "\n".join(f"- {line}" for line in spoken)
    else:
        spoken_text = "- （還沒說過）"
    places = "、".join(place_name(poi_id) for poi_id in POIS)
    here_label = place_name(actor.location)
    situation = situation_text(actor, residents, now_minutes)
    body = _body_line(actor)
    body_line = f"{body}\n" if body else ""
    user = (
        f"目前狀況：\n{situation}\n{body_line}{_plan_block(actor, time_str)}\n\n"
        f"你是 {actor.name}（id: {actor.id}）。\n"
        f"{actor.persona}\n\n"
        f"現在是 {time_str}，你在 {here_label}。\n"
        f"其他居民：{roster}\n"
        f"同地點、沒有在移動的人：{here}\n"
        f"地點：{places}\n"
        f"{_activity_prompt(actor)}\n"
        f"上一次的想法：{actor.last_thought or '（還沒有）'}\n"
        f"你已經在 {here_label} 待了 {actor.minutes_here} 分鐘。\n"
        f"你最近說過的話：\n{spoken_text}\n"
        f"最近的回顧：\n{_review_block(actor)}\n"
        f"最近的記憶：\n{memory_text}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def validate_decision(
    decision: Decision,
    actor: Resident,
    by_id: dict[str, Resident],
) -> str | None:
    echo = repeated_say(actor, decision.say)
    if echo is not None:
        return echo
    echo = repeated_thought(actor, decision.thought)
    if echo is not None:
        return echo
    if decision.action == "stay":
        if decision.target != "":
            return "stay 的 target 必須是空字串"
        return None
    if decision.action == "move_to" and decision.target not in POIS:
        return f"未知地點 {decision.target}"
    if decision.action == "do":
        allowed = {
            activity.id for activity in activities_for(actor.location, actor.id)
        }
        if decision.target not in allowed:
            return f"這裡不能做 {decision.target}"
        return None
    if decision.action != "talk_to":
        return None
    if decision.target == actor.id or decision.target not in by_id:
        return f"無法對話的對象 {decision.target}"
    other = by_id[decision.target]
    if other.location != actor.location or other.state == "walking":
        return f"{other.name} 不在同地點或正在移動"
    if other.state == "sleeping":
        return f"{other.name} 正在睡覺"
    return None


@dataclass
class DecisionJob:
    agent_id: str
    messages: list[dict[str, str]]
    is_reply: bool = False
    partner: str | None = None
    kind: str = "decision"
    time_str: str = ""
    token: str = ""
    client_seq: int = 0
    player_id: str = ""
    enqueued_at: float = 0.0
    allowed_fact_ids: tuple[str, ...] = ()


@dataclass
class ReadyDecision:
    job: DecisionJob
    decision: Decision | None = None
    review: str = ""


class LlmSession:
    def __init__(self, decider: Decider | None = None) -> None:
        self.residents = spawn_residents()
        self.by_id = {resident.id: resident for resident in self.residents}
        self.dialogue = DialogueTracker()
        self.opening = True
        self.queue = JobQueue(LLM_QUEUE_MAX)
        self.inbox: list[ReadyDecision] = []
        self.waiting: set[str] = set()
        self.planning: set[str] = set()
        self.decider = decider
        self.now_minutes = 0
        self.day = INITIAL_DAY
        self.plans_due = False
        self._extra_places: list[tuple[str, str]] = []
        self.players_present = False
        self.player_talk_running = False
        self.decision_counts: dict[str, int] = {}
        self.talk_world: Any = None
        self.talk_log: deque[dict[str, Any]] = deque(maxlen=app_config.TALK_LOG_LIMIT)

    def advance(
        self,
        time_str: str,
        day: int | None = None,
        company: list[tuple[str, str]] | None = None,
    ) -> tuple[list[WorldEvent], set[str]]:
        """Apply finished thoughts, walk, and enqueue. Does not call the model."""
        if day is not None:
            self.day = day
        self._extra_places = company or []
        events: list[WorldEvent] = []
        changed: set[str] = set()
        changed.update(self._stop_collapsed())
        reply_now = dict(self.dialogue.reply_next)
        self.dialogue.reply_next = {}
        applied: set[str] = set()

        ready = self.inbox
        self.inbox = []
        for item in ready:
            self.waiting.discard(item.job.agent_id)
            item_events, item_changed = self._apply(item, time_str)
            events.extend(item_events)
            changed.update(item_changed)
            applied.add(item.job.agent_id)

        arrivals = self._step(time_str, events, changed)
        self._tick_activities()
        self._tick_needs()
        changed.update(self._stop_collapsed())
        self._apply_schedule_clock(time_str, events, changed)
        self._enqueue(time_str, reply_now, arrivals)
        for resident in self.residents:
            if resident.state != "idle":
                continue
            resident.minutes_here += 1
            if resident.id not in applied:
                resident.idle_minutes += 1
        self.dialogue.tick_cooldowns()
        self.now_minutes += GAME_MINUTES_PER_TICK
        return events, changed

    def step_motion(
        self,
        time_str: str,
    ) -> tuple[list[WorldEvent], set[str]]:
        """Walk only. Needs and the decision clock stay on whole minutes."""
        events: list[WorldEvent] = []
        changed: set[str] = set()
        changed.update(self._stop_collapsed())
        self._step(time_str, events, changed)
        return events, changed

    def _apply(
        self,
        item: ReadyDecision,
        time_str: str,
    ) -> tuple[list[WorldEvent], set[str]]:
        actor = self.by_id.get(item.job.agent_id)
        if actor is None or item.decision is None and item.job.kind != "review":
            return [], set()
        if item.job.kind == "review":
            return self._apply_review(actor, item.review, time_str)
        assert item.decision is not None
        decision = coerce_target(item.decision, actor, self.residents)
        problem = validate_decision(decision, actor, self.by_id)
        if problem is not None:
            logger.warning("LLM decision rejected for %s: %s", actor.id, problem)
            decision = Decision(action="stay")
        elif decision.action == "talk_to" and self.dialogue.blocked(
            actor.id, decision.target
        ):
            decision = Decision(action="stay", thought=decision.thought)
        else:
            decision = hold_departure(decision, actor, self.now_minutes)
        before = (actor.state, actor.location, actor.position.x, actor.position.y)
        events = self._commit(actor, decision, time_str, item.job)
        after = (actor.state, actor.location, actor.position.x, actor.position.y)
        changed = {actor.id} if after != before else set()
        return events, changed

    def _commit(
        self,
        actor: Resident,
        decision: Decision,
        time_str: str,
        job: DecisionJob,
    ) -> list[WorldEvent]:
        events: list[WorldEvent] = []
        self._observe(actor)
        actor.last_thought = decision.thought.strip()
        thought = actor.last_thought
        if thought:
            actor.recent_thoughts.append(thought)
            events.append(
                WorldEvent(
                    timestamp=time_str,
                    agent_id=actor.id,
                    event="thought",
                    location=actor.location,
                    content=thought,
                )
            )
        say = decision.say.strip()
        if say:
            actor.recent_says.append(say)
            events.append(
                WorldEvent(
                    timestamp=time_str,
                    agent_id=actor.id,
                    event="said",
                    location=actor.location,
                    target_agent_id=(
                        decision.target if decision.action == "talk_to" else None
                    ),
                    content=say,
                )
            )
            for other in people_here(actor, self.residents):
                other.remember(time_str, f"（{actor.name} 說）{say}")

        if actor.state == "doing" and job.is_reply:
            if decision.action == "talk_to" and decision.target in self.by_id:
                other = self.by_id[decision.target]
                actor.heard = [
                    line for line in actor.heard if line.speaker_id != other.id
                ]
                if say:
                    other.heard.append(
                        DirectedLine(
                            speaker_id=actor.id,
                            text=say,
                            minute=self.now_minutes,
                        )
                    )
                    actor.remember(time_str, f"（我說）對 {other.name}：{say}")
                self.dialogue.finish_talk(actor.id, other.id)
                _share_company(actor, other)
            else:
                self.dialogue.abandon(actor.id, job.partner)
            return events
        if decision.action == "do":
            chosen = next(
                activity
                for activity in activities_for(actor.location, actor.id)
                if activity.id == decision.target
            )
            place = POIS[actor.location]
            actor.state = "doing"
            actor.activity_id = chosen.id
            actor.activity_name = chosen.name
            actor.activity_remaining = chosen.minutes
            actor.idle_minutes = 0
            actor.target_location = actor.location
            actor.remember(time_str, f"在{place.name}{chosen.name}")
            if chosen.id in EATING_ACTIVITIES:
                actor.fullness = _clamp_need(actor.fullness + EAT_FULLNESS_RESTORE)
            events.append(
                WorldEvent(
                    timestamp=time_str,
                    agent_id=actor.id,
                    event="activity",
                    location=actor.location,
                    content=chosen.name,
                    duration_minutes=chosen.minutes,
                )
            )
            if job.is_reply:
                self.dialogue.abandon(actor.id, job.partner)
            return events
        if decision.action == "move_to" and actor.collapsed:
            actor.state = "idle"
            actor.target_location = actor.location
            actor.idle_minutes = 0
            if job.is_reply:
                self.dialogue.abandon(actor.id, job.partner)
            return events
        if decision.action == "move_to" and decision.target == actor.location:
            actor.state = "idle"
            actor.idle_minutes = 0
            if job.is_reply:
                self.dialogue.abandon(actor.id, job.partner)
            return events
        if decision.action == "move_to":
            company = people_here(actor, self.residents)
            destination = decision.target
            actor.activity_id = ""
            actor.activity_name = ""
            actor.activity_remaining = 0
            events.append(
                WorldEvent(
                    timestamp=time_str,
                    agent_id=actor.id,
                    event="left",
                    location=actor.location,
                )
            )
            actor.target_location = destination
            actor.state = "walking"
            actor.idle_minutes = 0
            actor.remember(time_str, f"決定前往 {destination}")
            for other in company:
                other.last_seen[actor.id] = Sighting(actor.location, destination)
                other.remember(
                    time_str, f"看到 {actor.name} 離開，往 {destination} 去"
                )
            if job.is_reply:
                self.dialogue.abandon(actor.id, job.partner)
            return events
        if decision.action == "talk_to":
            other = self.by_id[decision.target]
            actor.heard = [
                line for line in actor.heard if line.speaker_id != other.id
            ]
            if say:
                other.heard.append(
                    DirectedLine(
                        speaker_id=actor.id,
                        text=say,
                        minute=self.now_minutes,
                    )
                )
            if say:
                actor.remember(time_str, f"（我說）對 {other.name}：{say}")
            else:
                actor.remember(time_str, f"想跟 {other.name} 說話，但沒說出內容")
            actor.state = "idle"
            actor.idle_minutes = 0
            self.dialogue.finish_talk(actor.id, other.id)
            _share_company(actor, other)
            return events
        actor.state = "idle"
        actor.target_location = actor.location
        actor.idle_minutes = 0
        if job.is_reply:
            self.dialogue.abandon(actor.id, job.partner)
        return events

    def _step(
        self,
        time_str: str,
        events: list[WorldEvent],
        changed: set[str],
    ) -> set[str]:
        arrivals: set[str] = set()
        for resident in self.residents:
            if resident.state != "walking":
                continue
            agent = resident.as_agent()
            before = (
                agent.state,
                agent.location,
                agent.position.x,
                agent.position.y,
            )
            event = move_agent(agent, time_str)
            resident.position = agent.position
            resident.location = agent.location
            resident.state = agent.state
            resident.target_location = agent.target_location
            after = (
                resident.state,
                resident.location,
                resident.position.x,
                resident.position.y,
            )
            if after != before:
                changed.add(resident.id)
            if event is None:
                continue
            events.append(event)
            resident.idle_minutes = 0
            resident.minutes_here = 0
            self._note_arrival(resident, time_str)
            arrivals.add(resident.id)
        return arrivals

    def _observe(self, actor: Resident) -> None:
        for other in people_here(actor, self.residents):
            actor.last_seen[other.id] = Sighting(actor.location)
            other.last_seen[actor.id] = Sighting(actor.location)

    def _note_arrival(self, actor: Resident, time_str: str) -> None:
        self._observe(actor)
        company = people_here(actor, self.residents)
        if company:
            seen = "、".join(other.name for other in company)
        else:
            seen = "沒有別人"
        actor.remember(time_str, f"抵達 {actor.location}，看到 {seen}")
        for other in company:
            other.remember(time_str, f"看到 {actor.name} 抵達 {actor.location}")
        if _is_night(time_str):
            actor.stay_until_minute = None
            self._queue_review(actor, time_str)
            return
        actor.stay_until_minute = self.now_minutes + LLM_MIN_STAY_MINUTES

    def _has_company(self, resident: Resident) -> bool:
        for other in self.residents:
            if other.id != resident.id and other.location == resident.location:
                return True
        return any(place == resident.location for _id, place in self._extra_places)

    def _stop_collapsed(self) -> set[str]:
        changed: set[str] = set()
        for resident in self.residents:
            was = resident.state
            resident.collapsed = is_collapsed(resident.fullness, resident.energy)
            if resident.collapsed and resident.state == "walking":
                resident.state = "idle"
                resident.target_location = resident.location
            if resident.state != was:
                changed.add(resident.id)
        return changed

    def _tick_needs(self) -> None:
        for resident in self.residents:
            asleep = resident.state == "sleeping" or (
                resident.state == "doing"
                and resident.activity_id in SLEEPING_ACTIVITIES
            )
            resting = (
                resident.state == "doing"
                and resident.activity_id in RESTING_ACTIVITIES
            )
            values = NeedValues(resident.fullness, resident.energy, resident.social)
            tick_need_values(
                values,
                location=resident.location,
                state=resident.state,
                company=self._has_company(resident),
                asleep=asleep,
                resting=resting,
            )
            resident.fullness = values.hunger
            resident.energy = values.energy
            resident.social = values.social
            resident.collapsed = is_collapsed(resident.fullness, resident.energy)

    def _apply_review(
        self,
        actor: Resident,
        text: str,
        time_str: str,
    ) -> tuple[list[WorldEvent], set[str]]:
        actor.review_pending = False
        actor.reviewed_today = True
        if text:
            actor.reviews.append((self.day, text))
            actor.remember(time_str, f"今日回顧：{text}")
        self._begin_sleep(actor)
        return [], {actor.id}

    def _begin_sleep(self, actor: Resident) -> None:
        actor.state = "sleeping"
        actor.activity_id = ""
        actor.activity_name = ""
        actor.activity_remaining = 0
        actor.target_location = actor.location
        actor.idle_minutes = 0

    def _queue_review(self, actor: Resident, time_str: str) -> None:
        if actor.reviewed_today or actor.review_pending or actor.id in self.waiting:
            return
        if actor.state == "sleeping":
            return
        actor.review_pending = True
        queued = self._put_resident(
            DecisionJob(
                agent_id=actor.id,
                messages=self._review_messages(actor, time_str),
                kind="review",
                time_str=time_str,
            )
        )
        if queued:
            self.waiting.add(actor.id)

    def _review_messages(
        self,
        actor: Resident,
        time_str: str,
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"你是 {actor.name}（id: {actor.id}）。\n"
                    f"{actor.persona}\n\n"
                    f"現在是第 {self.day} 天 {time_str}，你要睡了。\n"
                    "用 1 到 3 句繁體中文寫今日回顧，只放在 sentences。"
                    "回顧是你自己的看法，不要把別人的話寫成你的想法。\n"
                    f"最近的記憶：\n{_memory_text(actor)}"
                ),
            },
        ]

    def _queue_plan(self, actor: Resident, time_str: str) -> None:
        if actor.id in self.planning or actor.state == "sleeping":
            return
        self.planning.add(actor.id)
        self._put_resident(
            DecisionJob(
                agent_id=actor.id,
                messages=self._plan_messages(actor, time_str),
                kind="plan",
                time_str=time_str,
            )
        )

    def _plan_messages(
        self,
        actor: Resident,
        time_str: str,
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"請安排今天的計畫。你是 {actor.name}（id: {actor.id}）。\n"
                    f"{actor.persona}\n\n"
                    f"現在是第 {self.day} 天 {time_str}。\n"
                    f"寫 {PLAN_MIN_ITEMS} 到 {PLAN_MAX_ITEMS} 項，"
                    "每項有時間（HH:MM）、地點 id、活動 id、一句理由。\n"
                    f"最近的回顧：\n{_review_block(actor)}"
                ),
            },
        ]

    def _send_home(
        self,
        actor: Resident,
        time_str: str,
        events: list[WorldEvent],
        changed: set[str],
    ) -> None:
        home = home_for(actor.id)
        if actor.state == "walking" and actor.target_location == home.id:
            return
        if actor.location == home.id and actor.state != "walking":
            return
        if actor.state in {"idle", "doing"}:
            events.append(
                WorldEvent(
                    timestamp=time_str,
                    agent_id=actor.id,
                    event="left",
                    location=actor.location,
                )
            )
        actor.activity_id = ""
        actor.activity_name = ""
        actor.activity_remaining = 0
        actor.state = "walking"
        actor.target_location = home.id
        actor.idle_minutes = 0
        changed.add(actor.id)

    def _apply_schedule_clock(
        self,
        time_str: str,
        events: list[WorldEvent],
        changed: set[str],
    ) -> None:
        if _clock_minutes(time_str) == WAKE_HOUR * 60:
            for resident in self.residents:
                if resident.state != "sleeping":
                    continue
                resident.state = "idle"
                resident.activity_id = ""
                resident.activity_name = ""
                resident.reviewed_today = False
                resident.review_pending = False
                resident.pending_opening_decision = True
                resident.idle_minutes = 0
                changed.add(resident.id)
                self._queue_plan(resident, time_str)
            return
        if not _is_night(time_str):
            return
        for resident in self.residents:
            if resident.state == "sleeping" or resident.collapsed:
                continue
            home = home_for(resident.id)
            away = resident.location != home.id or resident.state == "walking"
            if away:
                self._send_home(resident, time_str, events, changed)
                continue
            self._queue_review(resident, time_str)

    def _tick_activities(self) -> None:
        for resident in self.residents:
            if resident.state != "doing":
                continue
            resident.activity_remaining -= GAME_MINUTES_PER_TICK
            if resident.activity_remaining > 0:
                continue
            resident.activity_remaining = 0
            resident.activity_id = ""
            resident.activity_name = ""
            resident.state = "idle"
            resident.idle_minutes = 0

    def _enqueue(
        self,
        time_str: str,
        reply_now: dict[str, str],
        arrivals: set[str],
    ) -> None:
        if self.opening:
            forced_ids = {resident.id for resident in self.residents}
            self.opening = False
            self.plans_due = True
        else:
            forced_ids = set()
            if self.plans_due and not _is_night(time_str):
                for resident in self.residents:
                    if resident.state != "sleeping":
                        self._queue_plan(resident, time_str)
                self.plans_due = False
        if _is_night(time_str):
            return
        forced: set[str] = forced_ids
        forced.update(arrivals)
        idle_after = (
            LLM_IDLE_DECISION_MINUTES_BUSY
            if self.players_present
            else LLM_IDLE_DECISION_MINUTES
        )
        player_busy = self.player_talk_running or self.queue.player_count() > 0
        for resident in self.residents:
            if (
                resident.state == "idle"
                and resident.idle_minutes >= idle_after
                and not player_busy
            ):
                forced.add(resident.id)
        for resident_id, speaker_id in reply_now.items():
            resident = self.by_id.get(resident_id)
            if resident is not None and resident.state in {"idle", "doing"}:
                forced.add(resident_id)
            elif resident is not None:
                self.dialogue.drop_pair(resident_id, speaker_id)
        for resident in sorted(self.residents, key=lambda item: item.id):
            if resident.id not in forced:
                continue
            if resident.state == "sleeping":
                continue
            if resident.state == "doing" and resident.id not in reply_now:
                continue
            self._request(
                resident,
                time_str,
                is_reply=resident.id in reply_now,
                partner=reply_now.get(resident.id),
            )

    def _request(
        self,
        resident: Resident,
        time_str: str,
        *,
        is_reply: bool,
        partner: str | None,
    ) -> None:
        if resident.state in {"walking", "sleeping"}:
            return
        if resident.state == "doing" and not is_reply:
            return
        if (
            self.players_present
            and self.decision_counts.get(resident.id, 0) >= LLM_DECISION_MAX_PER_ROUND
        ):
            return
        if resident.id in self.waiting:
            if is_reply and partner:
                self.dialogue.reply_next[resident.id] = partner
            return
        queued = self._put_resident(
            DecisionJob(
                agent_id=resident.id,
                messages=build_messages(
                    resident,
                    time_str,
                    self.residents,
                    self.now_minutes,
                ),
                is_reply=is_reply,
                partner=partner,
            )
        )
        if not queued:
            return
        self.waiting.add(resident.id)
        if self.players_present:
            count = self.decision_counts.get(resident.id, 0)
            self.decision_counts[resident.id] = count + 1

    def _put_resident(self, job: DecisionJob) -> bool:
        if self.queue.put_nowait(job):
            return True
        self.drop_resident_job(job)
        return False

    def drop_resident_job(self, job: DecisionJob) -> None:
        """A resident job that will not run becomes a quiet stay."""
        self.waiting.discard(job.agent_id)
        self.planning.discard(job.agent_id)
        actor = self.by_id.get(job.agent_id)
        if actor is not None:
            actor.review_pending = False
        if job.kind != "decision":
            return
        self.inbox.append(ReadyDecision(job=job, decision=_stay()))


def _stay() -> Decision:
    return Decision(action="stay")


def _retry_messages(
    messages: list[dict[str, str]],
    raw: str,
    problem: str,
) -> list[dict[str, str]]:
    note = f"上次的決定無效：{problem}。請修正 target 後重新輸出一個 JSON。"
    return [
        *messages,
        {"role": "assistant", "content": raw},
        {"role": "user", "content": note},
    ]


def _checked(
    session: LlmSession,
    agent_id: str,
    decision: Decision,
) -> tuple[Decision, str | None]:
    actor = session.by_id.get(agent_id)
    if actor is None:
        return _stay(), "居民已不存在"
    decision = coerce_target(decision, actor, session.residents)
    return decision, validate_decision(decision, actor, session.by_id)


async def _parse_reply(
    decider: Decider,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    agent_id: str,
) -> tuple[str, Decision] | None:
    try:
        raw = await decider(messages, schema)
        return raw, parse_decision(raw)
    except Exception as exc:
        logger.warning("LLM decision failed for %s", agent_id, exc_info=exc)
        return None


def _enqueue_decision(
    session: LlmSession,
    job: DecisionJob,
    decision: Decision,
) -> None:
    session.inbox.append(ReadyDecision(job=job, decision=decision))


async def _ask(
    decider: Decider,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    agent_id: str,
) -> str | None:
    try:
        return await decider(messages, schema)
    except Exception as exc:
        logger.warning("LLM decision failed for %s", agent_id, exc_info=exc)
        return None


async def _complete_plan(
    session: LlmSession,
    job: DecisionJob,
    decider: Decider,
    actor: Resident,
) -> None:
    messages = list(job.messages)
    schema = plan_schema(actor.id)
    raw = await _ask(decider, messages, schema, actor.id)
    items, problem = parse_plan(raw or "", actor.id)
    payload = _load_json(raw or "")
    if problem and not (payload and "action" in payload):
        retried = await _ask(
            decider,
            _retry_messages(messages, raw or "", problem),
            schema,
            actor.id,
        )
        if retried is not None:
            items, problem = parse_plan(retried, actor.id)
    if problem:
        logger.warning("LLM plan failed for %s: %s", actor.id, problem)
        items = []
    actor.plan = items
    session.planning.discard(actor.id)
    if actor.pending_opening_decision:
        actor.pending_opening_decision = False
        session._request(
            actor,
            job.time_str or "08:00",
            is_reply=False,
            partner=None,
        )


async def _complete_review(
    session: LlmSession,
    job: DecisionJob,
    decider: Decider,
    actor: Resident,
) -> None:
    messages = list(job.messages)
    schema = review_schema()
    raw = await _ask(decider, messages, schema, actor.id)
    text, problem = parse_review(raw or "")
    payload = _load_json(raw or "")
    if problem and not (payload and "action" in payload):
        retried = await _ask(
            decider,
            _retry_messages(messages, raw or "", problem),
            schema,
            actor.id,
        )
        if retried is not None:
            text, problem = parse_review(retried)
    if problem:
        logger.warning("LLM review failed for %s: %s", actor.id, problem)
        text = ""
    session.waiting.discard(actor.id)
    session.inbox.append(ReadyDecision(job=job, review=text))


async def complete_job(session: LlmSession, job: DecisionJob) -> None:
    if job.kind == "talk":
        from app.simulation.player_talk import finish_player_talk

        await finish_player_talk(session, job)
        return
    if session.players_present:
        try:
            await asyncio.wait_for(
                _complete_resident(session, job),
                LLM_BACKGROUND_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            session.drop_resident_job(job)
        return
    await _complete_resident(session, job)


async def _complete_resident(session: LlmSession, job: DecisionJob) -> None:
    decider = session.decider
    if decider is None:
        decider = OllamaDecider.from_env()
    actor = session.by_id.get(job.agent_id)
    if actor is None:
        logger.warning("LLM decision skipped for unknown agent %s", job.agent_id)
        session.waiting.discard(job.agent_id)
        if job.kind == "decision":
            _enqueue_decision(session, job, _stay())
        return
    if job.kind == "plan":
        await _complete_plan(session, job, decider, actor)
        return
    if job.kind == "review":
        await _complete_review(session, job, decider, actor)
        return
    schema = decision_schema(actor.id, session.residents)
    messages = list(job.messages)
    asked = await _parse_reply(decider, messages, schema, job.agent_id)
    if asked is None:
        _enqueue_decision(session, job, _stay())
        return
    raw, decision = asked
    decision, problem = _checked(session, job.agent_id, decision)
    if problem is None:
        _enqueue_decision(session, job, decision)
        return
    logger.warning("LLM decision rejected for %s: %s", job.agent_id, problem)
    retried = await _parse_reply(
        decider,
        _retry_messages(messages, raw, problem),
        schema,
        job.agent_id,
    )
    if retried is None:
        _enqueue_decision(session, job, _stay())
        return
    _raw, decision = retried
    decision, problem = _checked(session, job.agent_id, decision)
    if problem is not None:
        logger.warning("LLM decision failed for %s: %s", job.agent_id, problem)
        decision = _stay()
    _enqueue_decision(session, job, decision)


async def service_pending(session: LlmSession) -> None:
    """Finish every queued request, one at a time. Tests inject a fake decider."""
    while True:
        try:
            job = session.queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        await complete_job(session, job)


async def decision_worker(session: LlmSession) -> None:
    while True:
        job = await session.queue.get()
        await complete_job(session, job)
