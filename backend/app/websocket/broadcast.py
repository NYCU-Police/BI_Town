from fastapi import WebSocket

from app import state
from app.models.schemas import (
    Agent,
    AgentUpdateData,
    AgentUpdateMessage,
    WorldEvent,
    WorldEventMessage,
)
from app.websocket.manager import manager


async def broadcast_changes(
    events: list[WorldEvent],
    agents: list[Agent],
    *,
    removed: list[str] | None = None,
    exclude: WebSocket | None = None,
) -> None:
    message = AgentUpdateMessage(
        data=AgentUpdateData(
            day=state.world.day,
            time=state.world.time,
            agents=agents,
            removed=removed,
            notice=state.world.notice_text(),
        )
    )
    await manager.broadcast(message.model_dump(exclude_none=True), exclude=exclude)
    for event in events:
        payload = WorldEventMessage(data=event).model_dump(exclude_none=True)
        await manager.broadcast(payload, exclude=exclude)
