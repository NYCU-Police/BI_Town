import logging
import uuid

from fastapi import WebSocket

from app import config

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self.players: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket) -> str | None:
        await websocket.accept()
        self._connections.append(websocket)
        player_id: str | None = None
        if config.PLAYER_ENABLED:
            player_id = f"player_{uuid.uuid4().hex[:8]}"
            self.players[websocket] = player_id
        logger.info("WebSocket client connected (%s total)", len(self._connections))
        return player_id

    def disconnect(self, websocket: WebSocket) -> str | None:
        player_id = self.players.pop(websocket, None)
        try:
            self._connections.remove(websocket)
        except ValueError:
            return player_id
        logger.info("WebSocket client removed (%s remaining)", len(self._connections))
        return player_id

    async def broadcast(
        self,
        message: dict[str, object],
        exclude: WebSocket | None = None,
    ) -> None:
        for websocket in list(self._connections):
            if websocket is exclude:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                logger.exception("Failed to broadcast to a WebSocket client")
                self.disconnect(websocket)


manager = ConnectionManager()
