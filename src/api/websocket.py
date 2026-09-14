"""In-process WebSocket fan-out for live enriched telemetry frames."""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, payload: str) -> None:
        dead: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
