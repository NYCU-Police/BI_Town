"""Fast-forward three residents who decide through a local Ollama model.

This script does not start the server simulation loop and does not import
app.main. The public site keeps its existing rules until something else wires
a brain into the server.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.config import AGENT_SPEED_PER_TICK, ARRIVAL_DISTANCE_THRESHOLD
from app.models.schemas import Position
from app.simulation.clock import advance_clock, parse_time
from app.simulation.fake_agent import distance, step_towards
from app.simulation.poi import POIS, home_for

IDLE_DECISION_MINUTES = 15
MAX_CONSECUTIVE_DIALOGUE = 6
MEMORY_PROMPT_LIMIT = 10
MEMORY_STORE_LIMIT = 50
DEFAULT_START = "08:00"
DEFAULT_END = "20:00"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_TIMEOUT_SECONDS = 60.0
TEMPERATURE = 0.8
REPO_ROOT = Path(__file__).resolve().parents[2]

ChatFn = Callable[[list[dict[str, str]]], str]

SYSTEM_PROMPT = """\
你是小鎮居民。只輸出一個 JSON 物件，不要加其他文字。
想法（thought）與對話（say）必須使用繁體中文。
action 只能是 move_to、stay、talk_to。
move_to 的 target 只能是已知地點 id。
talk_to 的 target 必須是同地點、且沒有在移動的另一位居民 id。
stay 的 target 必須是空字串。
沒有要說的話時，say 必須是空字串。
thought 只寫一句內心話。
想見的人不在這裡時，可以根據記憶去他可能在的地方找他。
不要重複上一次的想法，想法要反映現在的處境。
"""


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
    last_thought: str = ""
    memories: deque[str] = field(
        default_factory=lambda: deque(maxlen=MEMORY_STORE_LIMIT)
    )

    def remember(self, time_str: str, item: str) -> None:
        self.memories.append(f"[{time_str}] {item}")


@dataclass
class RunStats:
    calls: int = 0
    failures: int = 0
    total_seconds: float = 0.0
    memories: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def average_seconds(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.total_seconds / self.calls


def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    if left_id < right_id:
        return (left_id, right_id)
    return (right_id, left_id)


@dataclass
class DialogueTracker:
    """Consecutive talk_to lines between a pair. Six ends the exchange."""

    counts: dict[tuple[str, str], int] = field(default_factory=dict)
    ended: set[tuple[str, str]] = field(default_factory=set)
    reply_next: dict[str, str] = field(default_factory=dict)

    def blocked(self, actor_id: str, other_id: str) -> str | None:
        if pair_key(actor_id, other_id) in self.ended:
            return "連續對話已達 6 句，結束"
        return None

    def finish_talk(self, actor_id: str, other_id: str) -> str | None:
        key = pair_key(actor_id, other_id)
        for other_key in list(self.counts):
            if actor_id in other_key and other_key != key:
                del self.counts[other_key]
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        self.reply_next.pop(actor_id, None)
        if count >= MAX_CONSECUTIVE_DIALOGUE:
            self.ended.add(key)
            del self.counts[key]
            self._clear_replies(key)
            return "連續對話已達 6 句，結束"
        self.reply_next[other_id] = actor_id
        return None

    def abandon(self, actor_id: str, partner_id: str | None) -> None:
        if partner_id is None:
            return
        self.counts.pop(pair_key(actor_id, partner_id), None)
        self.reply_next.pop(actor_id, None)

    def drop_pair(self, actor_id: str, partner_id: str) -> None:
        self.counts.pop(pair_key(actor_id, partner_id), None)

    def _clear_replies(self, key: tuple[str, str]) -> None:
        self.reply_next = {
            listener: speaker
            for listener, speaker in self.reply_next.items()
            if pair_key(listener, speaker) != key
        }


def _persona(resident_id: str, name: str, text: str) -> Resident:
    home = home_for(resident_id)
    return Resident(
        id=resident_id,
        name=name,
        persona=text,
        location=home.id,
        position=home.position,
        target_location=home.id,
    )


def spawn_residents() -> list[Resident]:
    """Three personalities with friction: duty, restlessness, and memory."""
    return [
        _persona(
            "mina",
            "Mina",
            "你重視安靜與工作進度，覺得沒目的的閒聊是打擾。"
            "你習慣把一天排好，遲到會讓你焦慮。"
            "你害怕被排除，但不會先承認。",
        ),
        _persona(
            "alex",
            "Alex",
            "你怕無聊，想拉別人去公園走走。"
            "你對規矩沒耐性，覺得 Mina 太緊繃，但又忍不住邀她。"
            "被追問真正的想法時，你會用玩笑帶過。",
        ),
        _persona(
            "rin",
            "Rin",
            "你剛搬來這個小鎮，話不多，但會記住別人說過的話，並在之後提起。"
            "你不喜歡被敷衍。"
            "Mina 的效率讓你覺得被推開，Alex 的熱絡讓你想看他什麼時候會收回去。",
        ),
    ]


class OllamaChatClient:
    """One local /api/chat call at a time. The loop is also single-threaded."""

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._timeout = timeout
        self._schema = Decision.model_json_schema()

    @classmethod
    def from_env(cls) -> OllamaChatClient:
        raw_timeout = os.environ.get("LLM_TIMEOUT", "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        if timeout <= 0:
            timeout = DEFAULT_TIMEOUT_SECONDS
        base_url = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL).strip()
        model = os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip()
        return cls(
            base_url=base_url or DEFAULT_OLLAMA_URL,
            model=model or DEFAULT_MODEL,
            timeout=timeout,
        )

    def __call__(self, messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            self._url,
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": self._schema,
                "options": {"temperature": TEMPERATURE},
            },
            timeout=self._timeout,
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


def clock_minutes(time_str: str) -> int:
    hours, minutes = parse_time(time_str)
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        raise ValueError(time_str)
    return hours * 60 + minutes


def parse_decision(raw: str) -> Decision:
    text = raw.strip()
    if text.startswith("```"):
        lines = [
            line for line in text.splitlines() if not line.strip().startswith("```")
        ]
        text = "\n".join(lines).strip()
    return Decision.model_validate_json(text)


def _failure_thought(exc: Exception) -> str:
    detail = str(exc).strip().replace("\n", " ")
    if len(detail) > 80:
        detail = detail[:77] + "..."
    if detail:
        return f"（LLM 失敗：{exc.__class__.__name__}：{detail}）"
    return f"（LLM 失敗：{exc.__class__.__name__}）"


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


def build_messages(
    actor: Resident,
    time_str: str,
    residents: list[Resident],
) -> list[dict[str, str]]:
    roster = "、".join(
        f"{other.id}（{other.name}）"
        for other in residents
        if other.id != actor.id
    )
    company = people_here(actor, residents)
    if company:
        here = "、".join(f"{other.id}（{other.name}）" for other in company)
    else:
        here = "沒有其他人"
    recent = list(actor.memories)[-MEMORY_PROMPT_LIMIT:]
    if recent:
        memory_text = "\n".join(f"- {item}" for item in recent)
    else:
        memory_text = "- （還沒有記憶）"
    user = (
        f"你是 {actor.name}（id: {actor.id}）。\n"
        f"{actor.persona}\n\n"
        f"現在是 {time_str}，你在 {actor.location}。\n"
        f"其他居民：{roster}\n"
        f"同地點、沒有在移動的人：{here}\n"
        f"地點 id：{'、'.join(POIS)}\n"
        f"上一次的想法：{actor.last_thought or '（還沒有）'}\n"
        f"你已經在 {actor.location} 待了 {actor.minutes_here} 分鐘。\n"
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


def request_decision(
    client: ChatFn,
    messages: list[dict[str, str]],
    stats: RunStats,
) -> tuple[Decision, bool]:
    stats.calls += 1
    started = time.perf_counter()
    try:
        return parse_decision(client(messages)), False
    except Exception as exc:
        failed = Decision(action="stay", thought=_failure_thought(exc))
        return failed, True
    finally:
        stats.total_seconds += time.perf_counter() - started


def _overhear(
    actor: Resident,
    by_id: dict[str, Resident],
    time_str: str,
    say: str,
) -> None:
    utterance = say.strip()
    if not utterance:
        return
    for other in people_here(actor, list(by_id.values())):
        other.remember(time_str, f"聽到 {actor.name} 說：{utterance}")


def apply_decision(
    actor: Resident,
    decision: Decision,
    by_id: dict[str, Resident],
    time_str: str,
    dialogue: DialogueTracker,
    *,
    is_reply: bool,
    partner: str | None,
) -> str | None:
    actor.last_thought = decision.thought.strip()
    # Speak while still present, then leave. Non-talk say does not schedule a reply.
    _overhear(actor, by_id, time_str, decision.say)
    if decision.action == "move_to" and decision.target == actor.location:
        actor.state = "idle"
        actor.idle_minutes = 0
        if is_reply:
            dialogue.abandon(actor.id, partner)
        return "已在當地，改為停留"
    if decision.action == "move_to":
        company = people_here(actor, list(by_id.values()))
        destination = decision.target
        actor.target_location = destination
        actor.state = "walking"
        actor.idle_minutes = 0
        actor.remember(time_str, f"決定前往 {destination}")
        for other in company:
            other.remember(time_str, f"看到 {actor.name} 離開，往 {destination} 去")
        if is_reply:
            dialogue.abandon(actor.id, partner)
        return None
    if decision.action == "talk_to":
        other = by_id[decision.target]
        utterance = decision.say.strip()
        if utterance:
            actor.remember(time_str, f"我對 {other.name} 說：{utterance}")
        else:
            actor.remember(time_str, f"想跟 {other.name} 說話，但沒說出內容")
        actor.state = "idle"
        actor.idle_minutes = 0
        return dialogue.finish_talk(actor.id, other.id)
    actor.state = "idle"
    actor.target_location = actor.location
    actor.idle_minutes = 0
    if is_reply:
        dialogue.abandon(actor.id, partner)
    return None


def format_decision_line(
    time_str: str,
    actor: Resident,
    decision: Decision,
    by_id: dict[str, Resident],
    note: str | None,
) -> str:
    thought = decision.thought.strip() or "（無）"
    parts = [f"[{time_str}] {actor.name} 在 {actor.location}｜想：{thought}"]
    say = decision.say.strip()
    if decision.action == "talk_to":
        other = by_id.get(decision.target)
        target_name = other.name if other is not None else decision.target
        parts.append(f"說（對 {target_name}）：{say or '（無）'}")
    elif say:
        parts.append(f"說：{say}")
    action = decision.action
    if decision.action != "stay" and decision.target:
        action = f"{decision.action} {decision.target}"
    if note:
        action = f"{action}（{note}）"
    parts.append(f"動作：{action}")
    return "｜".join(parts)


def note_arrival(
    actor: Resident,
    residents: list[Resident],
    time_str: str,
) -> None:
    company = people_here(actor, residents)
    if company:
        seen = "、".join(other.name for other in company)
    else:
        seen = "沒有別人"
    actor.remember(time_str, f"抵達 {actor.location}，看到 {seen}")
    for other in company:
        other.remember(time_str, f"看到 {actor.name} 抵達 {actor.location}")


def step_resident(resident: Resident) -> bool:
    target = POIS[resident.target_location]
    dist = distance(resident.position, target.position)
    if dist <= ARRIVAL_DISTANCE_THRESHOLD or dist <= AGENT_SPEED_PER_TICK:
        resident.position = target.position
        resident.location = resident.target_location
        resident.state = "idle"
        resident.idle_minutes = 0
        resident.minutes_here = 0
        return True
    resident.position = step_towards(
        resident.position,
        target.position,
        AGENT_SPEED_PER_TICK,
    )
    return False


def format_stats(stats: RunStats) -> str:
    return "\n".join(
        (
            "",
            "## 統計",
            f"- LLM 呼叫次數：{stats.calls}",
            f"- 失敗次數：{stats.failures}",
            f"- 平均回應秒數：{stats.average_seconds:.2f}",
            "",
        )
    )


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return REPO_ROOT / "poc_output" / f"{stamp}.md"


def run_town(
    *,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    client: ChatFn | None = None,
    output_path: Path | None = None,
    model_label: str = "fake",
    echo: bool = True,
    meet: str | None = None,
) -> RunStats:
    """Advance game minutes with no sleep. LLM errors become stay."""
    if clock_minutes(start) >= clock_minutes(end):
        raise ValueError("結束時間必須晚於開始時間，且不跨日")
    residents = spawn_residents()
    if meet is not None:
        meeting = POIS[meet]
        for resident in residents:
            resident.location = meeting.id
            resident.target_location = meeting.id
            resident.position = meeting.position
            resident.state = "idle"
    by_id = {resident.id: resident for resident in residents}
    chat = client if client is not None else OllamaChatClient.from_env()
    destination = output_path or default_output_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    stats = RunStats()
    time_str = start
    opening = True
    dialogue = DialogueTracker()
    reply_now: dict[str, str] = {}

    def emit(line: str, handle: object) -> None:
        if echo:
            print(line, flush=True)
        handle.write(line + "\n")
        handle.flush()

    with destination.open("w", encoding="utf-8") as handle:
        emit("# LLM Town POC", handle)
        emit("", handle)
        emit(f"遊戲時間 {start} → {end}。模型：{model_label}。", handle)
        emit("此腳本不接入伺服器模擬迴圈。", handle)
        emit("", handle)
        while clock_minutes(time_str) < clock_minutes(end):
            arrivals: list[Resident] = []
            for resident in residents:
                if resident.state == "walking" and step_resident(resident):
                    arrivals.append(resident)
            for resident in arrivals:
                note_arrival(resident, residents, time_str)
            arrived_ids = {resident.id for resident in arrivals}
            if opening:
                decider_ids = {resident.id for resident in residents}
                opening = False
            else:
                decider_ids = set()
            decider_ids.update(arrived_ids)
            decider_ids.update(
                resident.id
                for resident in residents
                if resident.state == "idle"
                and resident.idle_minutes >= IDLE_DECISION_MINUTES
            )
            for resident_id, speaker_id in reply_now.items():
                resident = by_id[resident_id]
                if resident.state == "idle":
                    decider_ids.add(resident_id)
                else:
                    dialogue.drop_pair(resident_id, speaker_id)
            deciders = [
                resident for resident in residents if resident.id in decider_ids
            ]
            deciders.sort(key=lambda resident: resident.id)
            decided: set[str] = set()
            for resident in deciders:
                messages = build_messages(resident, time_str, residents)
                decision, failed = request_decision(chat, messages, stats)
                cap_note: str | None = None
                if failed:
                    stats.failures += 1
                else:
                    problem = validate_decision(decision, resident, by_id)
                    if problem is not None:
                        stats.failures += 1
                        decision = Decision(
                            action="stay",
                            thought=f"（LLM 失敗：{problem}）",
                        )
                    elif decision.action == "talk_to":
                        cap_note = dialogue.blocked(resident.id, decision.target)
                        if cap_note is not None:
                            decision = Decision(
                                action="stay",
                                thought=decision.thought,
                            )
                is_reply = resident.id in reply_now
                note = apply_decision(
                    resident,
                    decision,
                    by_id,
                    time_str,
                    dialogue,
                    is_reply=is_reply,
                    partner=reply_now.get(resident.id),
                )
                if cap_note is not None:
                    note = cap_note
                emit(
                    format_decision_line(
                        time_str, resident, decision, by_id, note
                    ),
                    handle,
                )
                decided.add(resident.id)
            reply_now = dialogue.reply_next
            dialogue.reply_next = {}
            dialogue.ended.clear()
            for resident in residents:
                if resident.state != "idle":
                    continue
                resident.minutes_here += 1
                if resident.id not in decided:
                    resident.idle_minutes += 1
            _day, time_str = advance_clock(1, time_str, 1)
        stats.memories = {
            resident.id: tuple(resident.memories) for resident in residents
        }
        emit(format_stats(stats), handle)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="快轉觀察三個本地 LLM 居民")
    parser.add_argument("--start", default=DEFAULT_START, help="遊戲開始時間 HH:MM")
    parser.add_argument("--end", default=DEFAULT_END, help="遊戲結束時間 HH:MM")
    parser.add_argument("--output", type=Path, default=None, help="劇本輸出路徑")
    args = parser.parse_args(argv)
    try:
        clock_minutes(args.start)
        clock_minutes(args.end)
    except ValueError:
        parser.error("時間格式須為 HH:MM，且小時 0–23、分鐘 0–59")
    if clock_minutes(args.start) >= clock_minutes(args.end):
        parser.error("結束時間必須晚於開始時間，且不跨日")
    client = OllamaChatClient.from_env()
    output = args.output or default_output_path()
    run_town(
        start=args.start,
        end=args.end,
        client=client,
        output_path=output,
        model_label=client.model,
        echo=True,
    )
    print(f"寫入 {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
