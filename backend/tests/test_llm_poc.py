import json
from pathlib import Path

from poc.llm_town import run_town


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
