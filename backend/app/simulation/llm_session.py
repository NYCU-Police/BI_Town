"""LLM residents for BRAIN_MODE=llm. Not imported by the rules world.

Decision text is ported from the POC. This module does not import poc.
Calls go through one async worker so World.tick() never waits on the model.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_OLLAMA_URL,
    GAME_MINUTES_PER_TICK,
    INITIAL_DAY,
    INITIAL_TIME,
    LLM_DIALOGUE_COOLDOWN_MINUTES,
    LLM_IDLE_DECISION_MINUTES,
    LLM_MAX_CONSECUTIVE_DIALOGUE,
    LLM_MEMORY_PROMPT_LIMIT,
    LLM_MEMORY_STORE_LIMIT,
    LLM_MIN_STAY_MINUTES,
    LLM_RECENT_SAY_LIMIT,
    LLM_RECENT_SAY_PROMPT_LIMIT,
    LLM_RECENT_THOUGHT_LIMIT,
    LLM_SAY_SIMILARITY,
    LLM_TEMPERATURE,
    LLM_THOUGHT_SIMILARITY,
    LLM_UNANSWERED_MINUTES,
    current_llm_think,
)
from app.models.schemas import Agent, Position, WorldEvent
from app.simulation.clock import advance_clock
from app.simulation.fake_agent import move_agent
from app.simulation.poi import POIS, home_for

logger = logging.getLogger(__name__)

Decider = Callable[[list[dict[str, str]], dict[str, Any]], Awaitable[str]]

SYSTEM_PROMPT = """\
你是小鎮居民。只輸出一個 JSON 物件，不要加其他文字。
想法（thought）與對話（say）必須使用繁體中文。
action 只能是 move_to、stay、talk_to。
move_to 的 target 只能是 home（家）、cafe（咖啡廳）、office（辦公室）、park（公園）。
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
    action: Literal["move_to", "stay", "talk_to"] = Field(
        description="move_to、stay 或 talk_to"
    )
    target: str = Field(default="", description="POI id、居民 id，或空字串")
    say: str = Field(default="", description="說出口的繁體中文；不說則空字串")
    thought: str = Field(default="", description="一句繁體中文內心話")


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

    def remember(self, time_str: str, item: str) -> None:
        self.memories.append(f"[{time_str}] {item}")

    def as_agent(self) -> Agent:
        state: Literal["idle", "walking"] = (
            "walking" if self.state == "walking" else "idle"
        )
        return Agent(
            id=self.id,
            name=self.name,
            position=self.position,
            location=self.location,
            target_location=self.target_location,
            state=state,
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
            "你重視安靜與工作進度，覺得沒目的的閒聊是打擾。"
            "你習慣把一天排好，遲到會讓你焦慮。"
            "你害怕被排除，但不會先承認。",
        ),
        _at_home(
            "alex",
            "Alex",
            "你怕無聊，想拉別人去公園走走。"
            "你對規矩沒耐性，覺得 Mina 太緊繃，但又忍不住邀她。"
            "被追問真正的想法時，你會用玩笑帶過。",
        ),
        _at_home(
            "rin",
            "Rin",
            "你剛搬來這個小鎮，話不多，但會記住別人說過的話，並在之後提起。"
            "你不喜歡被敷衍。"
            "Mina 的效率讓你覺得被推開，Alex 的熱絡讓你想看他什麼時候會收回去。",
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
    return Decision.model_validate_json(text)


def target_enum(actor_id: str, residents: list[Resident]) -> list[str]:
    choices = [poi_id for poi_id in POIS if poi_id != actor_id]
    others = sorted(resident.id for resident in residents if resident.id != actor_id)
    for other_id in others:
        if other_id not in choices:
            choices.append(other_id)
    choices.append("")
    return choices


def decision_schema(actor_id: str, residents: list[Resident]) -> dict[str, Any]:
    schema = Decision.model_json_schema()
    target = schema["properties"]["target"]
    target["enum"] = target_enum(actor_id, residents)
    return schema


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
        and other.state == "idle"
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
    user = (
        f"目前狀況：\n{situation}\n\n"
        f"你是 {actor.name}（id: {actor.id}）。\n"
        f"{actor.persona}\n\n"
        f"現在是 {time_str}，你在 {here_label}。\n"
        f"其他居民：{roster}\n"
        f"同地點、沒有在移動的人：{here}\n"
        f"地點：{places}\n"
        f"上一次的想法：{actor.last_thought or '（還沒有）'}\n"
        f"你已經在 {here_label} 待了 {actor.minutes_here} 分鐘。\n"
        f"你最近說過的話：\n{spoken_text}\n"
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
    if decision.action == "move_to" and decision.target not in POIS:
        return f"未知地點 {decision.target}"
    if decision.action != "talk_to":
        return None
    if decision.target == actor.id or decision.target not in by_id:
        return f"無法對話的對象 {decision.target}"
    other = by_id[decision.target]
    if other.location != actor.location or other.state != "idle":
        return f"{other.name} 不在同地點或正在移動"
    return None


@dataclass
class DecisionJob:
    agent_id: str
    messages: list[dict[str, str]]
    is_reply: bool
    partner: str | None


@dataclass
class ReadyDecision:
    job: DecisionJob
    decision: Decision


class LlmSession:
    def __init__(self, decider: Decider | None = None) -> None:
        self.residents = spawn_residents()
        self.by_id = {resident.id: resident for resident in self.residents}
        self.dialogue = DialogueTracker()
        self.opening = True
        self.queue: asyncio.Queue[DecisionJob] = asyncio.Queue()
        self.inbox: list[ReadyDecision] = []
        self.waiting: set[str] = set()
        self.decider = decider
        self.now_minutes = 0

    def advance(self, time_str: str) -> tuple[list[WorldEvent], set[str]]:
        """Apply finished thoughts, walk, and enqueue. Does not call the model."""
        events: list[WorldEvent] = []
        changed: set[str] = set()
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

    def _apply(
        self,
        item: ReadyDecision,
        time_str: str,
    ) -> tuple[list[WorldEvent], set[str]]:
        actor = self.by_id.get(item.job.agent_id)
        if actor is None:
            return [], set()
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
                other.remember(time_str, f"聽到 {actor.name} 說：{say}")

        if decision.action == "move_to" and decision.target == actor.location:
            actor.state = "idle"
            actor.idle_minutes = 0
            if job.is_reply:
                self.dialogue.abandon(actor.id, job.partner)
            return events
        if decision.action == "move_to":
            company = people_here(actor, self.residents)
            destination = decision.target
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
                actor.remember(time_str, f"我對 {other.name} 說：{say}")
            else:
                actor.remember(time_str, f"想跟 {other.name} 說話，但沒說出內容")
            actor.state = "idle"
            actor.idle_minutes = 0
            self.dialogue.finish_talk(actor.id, other.id)
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
        actor.stay_until_minute = self.now_minutes + LLM_MIN_STAY_MINUTES
        actor.remember(time_str, f"抵達 {actor.location}，看到 {seen}")
        for other in company:
            other.remember(time_str, f"看到 {actor.name} 抵達 {actor.location}")

    def _enqueue(
        self,
        time_str: str,
        reply_now: dict[str, str],
        arrivals: set[str],
    ) -> None:
        forced: set[str] = set()
        if self.opening:
            forced.update(resident.id for resident in self.residents)
            self.opening = False
        forced.update(arrivals)
        for resident in self.residents:
            if (
                resident.state == "idle"
                and resident.idle_minutes >= LLM_IDLE_DECISION_MINUTES
            ):
                forced.add(resident.id)
        for resident_id, speaker_id in reply_now.items():
            resident = self.by_id.get(resident_id)
            if resident is not None and resident.state == "idle":
                forced.add(resident_id)
            elif resident is not None:
                self.dialogue.drop_pair(resident_id, speaker_id)
        for resident in sorted(self.residents, key=lambda item: item.id):
            if resident.id not in forced:
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
        if resident.state != "idle":
            return
        if resident.id in self.waiting:
            if is_reply and partner:
                self.dialogue.reply_next[resident.id] = partner
            return
        self.waiting.add(resident.id)
        self.queue.put_nowait(
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


async def complete_job(session: LlmSession, job: DecisionJob) -> None:
    decider = session.decider
    if decider is None:
        decider = OllamaDecider.from_env()
    actor = session.by_id.get(job.agent_id)
    if actor is None:
        logger.warning("LLM decision skipped for unknown agent %s", job.agent_id)
        _enqueue_decision(session, job, _stay())
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
