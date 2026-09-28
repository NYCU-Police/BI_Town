import logging
import uuid

from fastapi import WebSocket

from app import config

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self.players: dict[WebSocket, str] = {}
        self.socket_by_token: dict[str, WebSocket] = {}
        self.token_by_socket: dict[WebSocket, str] = {}
        self.retired: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> str | None:
        await websocket.accept()
        self._connections.append(websocket)
        player_id: str | None = None
        if config.PLAYER_ENABLED:
            player_id = f"player_{uuid.uuid4().hex[:8]}"
            self.players[websocket] = player_id
        logger.info("WebSocket client connected (%s total)", len(self._connections))
        return player_id

    def claim_token(self, websocket: WebSocket, token: str) -> WebSocket | None:
        previous = self.socket_by_token.get(token)
        self.socket_by_token[token] = websocket
        self.token_by_socket[websocket] = token
        if previous is None or previous is websocket:
            return None
        return previous

    def disconnect(self, websocket: WebSocket) -> str | None:
        token = self.token_by_socket.pop(websocket, None)
        if token is not None and self.socket_by_token.get(token) is websocket:
            del self.socket_by_token[token]
        self.retired.discard(websocket)
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
            if websocket is exclude or websocket in self.retired:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                logger.exception("Failed to broadcast to a WebSocket client")
                self.disconnect(websocket)


manager = ConnectionManager()
