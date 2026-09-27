import json
import re
from pathlib import Path

from poc.llm_town import MAX_CONSECUTIVE_DIALOGUE, run_town

_CLOCK = re.compile(r"現在是 (\d{2}:\d{2})")
_MEMORY_STAMP = re.compile(r"^\[\d{2}:\d{2}\] ")


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


def _actor_and_time(messages: list[dict[str, str]]) -> tuple[str, str]:
    user = messages[-1]["content"]
    if "你是 Mina" in user:
        name = "Mina"
    elif "你是 Alex" in user:
        name = "Alex"
    else:
        name = "Rin"
    match = _CLOCK.search(user)
    assert match is not None
    return name, match.group(1)


def test_fake_llm_runs_one_game_hour_without_network(tmp_path: Path) -> None:
    calls = {"n": 0}
    targets = ("cafe", "office", "park", "home")

    def fake(_messages: list[dict[str, str]]) -> str:
        calls["n"] += 1
        target = targets[calls["n"] % len(targets)]
        return json.dumps(
            {
                "action": "move_to",
                "target": target,
                "say": "",
                "thought": "換個地方看看",
            },
            ensure_ascii=False,
        )

    output = tmp_path / "hour.md"
    stats = run_town(
        start="08:00",
        end="09:00",
        client=fake,
        output_path=output,
        model_label="fake",
        echo=False,
    )

    text = output.read_text(encoding="utf-8")
    assert stats.calls == calls["n"]
    assert stats.calls >= 1
    assert stats.failures == 0
    assert "Mina" in text
    assert "Alex" in text
    assert "Rin" in text
    assert "LLM 呼叫次數" in text
    assert "失敗次數：0" in text


def test_talk_to_someone_elsewhere_becomes_stay(tmp_path: Path) -> None:
    def fake(messages: list[dict[str, str]]) -> str:
        name, _clock = _actor_and_time(messages)
        user = messages[-1]["content"]
        if name == "Alex" and "你在 cafe" in user:
            return _decision("talk_to", "mina", "你在嗎", "人怎麼不在")
        if name == "Alex":
            return _decision("move_to", "cafe", thought="去咖啡店")
        return _decision("stay")

    output = tmp_path / "apart.md"
    stats = run_town(
        start="08:00",
        end="08:10",
        client=fake,
        output_path=output,
        echo=False,
    )
    text = output.read_text(encoding="utf-8")
    assert stats.failures == 1
    assert "Mina 不在同地點或正在移動" in text
    rejected = "Alex 在 cafe｜想：（LLM 失敗：Mina 不在同地點或正在移動）｜動作：stay"
    assert rejected in text


def test_listener_decides_on_the_next_minute(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []

    def fake(messages: list[dict[str, str]]) -> str:
        name, clock = _actor_and_time(messages)
        seen.append((name, clock))
        if name == "Alex" and clock == "08:00":
            return _decision("talk_to", "mina", "早", "先打聲招呼")
        return _decision("stay")

    run_town(
        start="08:00",
        end="08:04",
        client=fake,
        output_path=tmp_path / "reply.md",
        echo=False,
    )
    mina_times = [clock for name, clock in seen if name == "Mina"]
    assert mina_times == ["08:00", "08:01"]


def test_consecutive_dialogue_stops_at_six(tmp_path: Path) -> None:
    def fake(messages: list[dict[str, str]]) -> str:
        name, clock = _actor_and_time(messages)
        if name == "Alex":
            return _decision("talk_to", "mina", "還在嗎", "想再問一句")
        if name == "Mina" and clock != "08:00":
            return _decision("talk_to", "alex", "在", "回他一句")
        return _decision("stay")

    output = tmp_path / "cap.md"
    stats = run_town(
        start="08:00",
        end="08:12",
        client=fake,
        output_path=output,
        echo=False,
    )
    text = output.read_text(encoding="utf-8")
    assert text.count("動作：talk_to") == MAX_CONSECUTIVE_DIALOGUE
    assert stats.failures == 0
    assert "連續對話已達 6 句，結束" in text


def test_memories_start_with_game_time(tmp_path: Path) -> None:
    def fake(_messages: list[dict[str, str]]) -> str:
        return _decision("stay", thought="先留下")

    stats = run_town(
        start="08:00",
        end="08:01",
        client=fake,
        output_path=tmp_path / "memory.md",
        echo=False,
    )
    assert stats.memories["mina"]
    assert stats.memories["alex"]
    assert stats.memories["rin"]
    for items in stats.memories.values():
        assert items
        for item in items:
            assert _MEMORY_STAMP.match(item)
    assert any(item.startswith("[08:00] ") for item in stats.memories["mina"])
