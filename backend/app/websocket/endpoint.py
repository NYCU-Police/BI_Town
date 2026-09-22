import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import state
from app.models.schemas import WorldSnapshotMessage
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        snapshot = WorldSnapshotMessage(data=state.world.snapshot())
        await websocket.send_json(snapshot.model_dump())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        manager.disconnect(websocket)
