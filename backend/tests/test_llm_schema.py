"""Schemas sent to Ollama stay flat. Pairing is checked on the server."""

from app.simulation.llm_session import (
    decision_schema,
    plan_schema,
    review_schema,
)
from app.simulation.world import World

_ALLOWED = {
    "type",
    "properties",
    "required",
    "enum",
    "items",
    "minItems",
    "maxItems",
}
_FORBIDDEN = {
    "oneOf",
    "anyOf",
    "allOf",
    "const",
    "pattern",
    "minLength",
    "$ref",
    "$defs",
}


def _keys(node: object, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key == "properties" and isinstance(value, dict):
                for child in value.values():
                    _keys(child, found)
                continue
            _keys(value, found)
    elif isinstance(node, list):
        for item in node:
            _keys(item, found)


def test_ollama_schemas_omit_keywords_ollama_drops() -> None:
    world = World(brain_mode="llm", decider=lambda _messages, _schema: "")
    assert world.llm is not None
    residents = world.llm.residents
    schemas = [
        decision_schema("mina", residents),
        decision_schema("alex", residents),
        decision_schema("rin", residents),
        plan_schema("mina"),
        plan_schema("alex"),
        plan_schema("rin"),
        review_schema(),
    ]
    for schema in schemas:
        found: set[str] = set()
        _keys(schema, found)
        assert found <= _ALLOWED
        assert not found & _FORBIDDEN

    decision = schemas[0]
    assert decision["required"] == ["action", "target", "say", "thought"]
    assert "thought" in decision["required"]
    assert "say" in decision["required"]
