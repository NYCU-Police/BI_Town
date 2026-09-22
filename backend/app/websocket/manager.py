import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (%s total)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        try:
            self._connections.remove(websocket)
        except ValueError:
            return
        logger.info("WebSocket client removed (%s remaining)", len(self._connections))

    async def broadcast(self, message: dict[str, object]) -> None:
        for websocket in list(self._connections):
            try:
                await websocket.send_json(message)
            except Exception:
                logger.exception("Failed to broadcast to a WebSocket client")
                self.disconnect(websocket)


manager = ConnectionManager()
