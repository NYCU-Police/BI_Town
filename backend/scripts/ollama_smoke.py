"""Send the three live schemas to Ollama, then run one simulated hour.

Usage (from backend/):

    OLLAMA_URL=http://100.76.54.51:11434 LLM_MODEL=qwen3:14b \\
        .venv/bin/python scripts/ollama_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.simulation.llm_session import (  # noqa: E402
    OllamaDecider,
    build_messages,
    decision_schema,
    parse_decision,
    plan_schema,
    review_schema,
    service_pending,
)
from app.simulation.world import World  # noqa: E402

SIMULATED_MINUTES = 60


async def _post(
    decider: OllamaDecider,
    label: str,
    messages: list[dict[str, str]],
    schema: dict,
) -> str:
    try:
        raw = await decider(messages, schema)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:400]
        print(f"{label} HTTP {exc.response.status_code} {body}", flush=True)
        raise
    print(f"{label} HTTP 200", flush=True)
    json.loads(raw)
    return raw


class _CountingDecider:
    def __init__(self, inner: OllamaDecider) -> None:
        self.inner = inner
        self.http_400 = 0

    async def __call__(
        self,
        messages: list[dict[str, str]],
        schema: dict,
    ) -> str:
        try:
            return await self.inner(messages, schema)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                self.http_400 += 1
                print(f"session HTTP 400 {exc.response.text[:300]}", flush=True)
            raise


async def main() -> None:
    decider = OllamaDecider.from_env()
    probe = World(brain_mode="llm", decider=decider)
    assert probe.llm is not None
    mina = probe.llm.by_id["mina"]
    residents = probe.llm.residents

    decision_raw = await _post(
        decider,
        "decision",
        build_messages(mina, "08:00", residents),
        decision_schema(mina.id, residents),
    )
    decision = parse_decision(decision_raw)
    print(f"decision thought: {decision.thought}", flush=True)
    if not decision.thought.strip():
        raise SystemExit("decision thought is empty")

    await _post(
        decider,
        "plan",
        probe.llm._plan_messages(mina, "08:00"),
        plan_schema(mina.id),
    )
    await _post(
        decider,
        "review",
        probe.llm._review_messages(mina, "22:00"),
        review_schema(),
    )

    guard = _CountingDecider(decider)
    world = World(brain_mode="llm", decider=guard)
    assert world.llm is not None
    counts: Counter[str] = Counter()
    for _ in range(SIMULATED_MINUTES):
        result = world.tick()
        counts.update(event.event for event in result.events)
        if world.llm.queue.qsize():
            await service_pending(world.llm)
    flushed = world.tick()
    counts.update(event.event for event in flushed.events)

    print(
        "60min"
        f" thought={counts['thought']}"
        f" said={counts['said']}"
        f" activity={counts['activity']}"
        f" failed={guard.http_400}"
        f" time={world.time}",
        flush=True,
    )
    if counts["thought"] == 0 or guard.http_400:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
