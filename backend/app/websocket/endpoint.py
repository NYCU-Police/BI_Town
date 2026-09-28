import json
import logging
import time
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app import config, state
from app.models.schemas import (
    Intent,
    IntentResultMessage,
    SessionMessage,
    WorldEvent,
    WorldSnapshotMessage,
)
from app.simulation.player_talk import history_payload, note_ids, note_texts, open_token
from app.websocket.broadcast import broadcast_changes
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _result(client_seq: int, ok: bool, reason: str | None) -> dict[str, object]:
    return IntentResultMessage(
        client_seq=client_seq,
        ok=ok,
        reason=reason,
    ).model_dump()


def _client_seq(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    seq = payload.get("client_seq", 0)
    if type(seq) is not int:
        return 0
    return seq


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    player_id = await manager.connect(websocket)
    recent: deque[float] = deque()
    try:
        token: str | None = None
        old_id: str | None = None
        old_events: list[WorldEvent] = []
        if player_id is not None:
            token = open_token(state.world, websocket.query_params.get("player_token"))
            previous = manager.claim_token(websocket, token)
            if previous is not None:
                old_id = manager.players.pop(previous, None)
                manager.retired.add(previous)
                if old_id is not None:
                    ended = state.world.remove_player(old_id)
                    if ended is not None:
                        old_events = ended
            state.world.player_tokens[player_id] = token
            await websocket.send_json(SessionMessage(player_token=token).model_dump())
            entered = state.world.add_player(player_id)
        else:
            entered = None
        snapshot = state.world.snapshot()
        snapshot.you = player_id
        snapshot.dialogue_history = history_payload(state.world, token)
        snapshot.notes = note_texts(state.world, token)
        snapshot.note_ids = note_ids(state.world, token)
        message = WorldSnapshotMessage(data=snapshot)
        await websocket.send_json(message.model_dump(exclude_none=True))
        if entered is not None or old_id is not None:
            await broadcast_changes(
                old_events,
                [entered] if entered is not None else [],
                removed=[old_id] if old_id is not None else None,
                exclude=websocket,
            )
        while True:
            text = await websocket.receive_text()
            await _handle_text(websocket, player_id, text, recent)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        removed_id = manager.disconnect(websocket)
        ended = None if removed_id is None else state.world.remove_player(removed_id)
        if ended is not None:
            await broadcast_changes(ended, [], removed=[removed_id])


async def _handle_text(
    websocket: WebSocket,
    player_id: str | None,
    text: str,
    recent: deque[float],
) -> None:
    if len(text.encode("utf-8")) > config.INTENT_MAX_BYTES:
        await websocket.send_json(_result(0, False, "too_large"))
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        await websocket.send_json(_result(0, False, "bad_json"))
        return
    if not isinstance(payload, dict) or payload.get("type") != "intent":
        return
    client_seq = _client_seq(payload)
    if client_seq == 0 and payload.get("client_seq") != 0:
        await websocket.send_json(_result(0, False, "bad_intent"))
        return
    now = time.monotonic()
    while recent and now - recent[0] >= 1.0:
        recent.popleft()
    if len(recent) >= config.INTENT_RATE_LIMIT_PER_SEC:
        await websocket.send_json(_result(client_seq, False, "rate_limited"))
        return
    recent.append(now)
    if not config.PLAYER_ENABLED or player_id is None:
        await websocket.send_json(_result(client_seq, False, "players_disabled"))
        return
    raw_intent = payload.get("intent")
    if isinstance(raw_intent, dict):
        target = raw_intent.get("target")
        if isinstance(target, dict) and target.get("type") not in {"agent", "poi"}:
            await websocket.send_json(_result(client_seq, False, "unsupported_target"))
            return
    try:
        intent = Intent.model_validate(raw_intent)
    except ValidationError:
        await websocket.send_json(_result(client_seq, False, "bad_intent"))
        return
    outcome = state.world.apply_intent(player_id, intent, client_seq)
    if outcome.superseded_seq is not None:
        await websocket.send_json(
            _result(outcome.superseded_seq, False, "superseded")
        )
    await websocket.send_json(_result(client_seq, outcome.ok, outcome.reason))
    if outcome.ok and (outcome.events or outcome.changed_agents):
        await broadcast_changes(outcome.events, outcome.changed_agents)
