"""In-process WebSocket fan-out for live enriched telemetry frames."""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def is_origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    """Whether a WebSocket handshake's Origin header should be accepted.

    Starlette's CORSMiddleware only inspects regular HTTP requests; it never
    runs for a WebSocket upgrade, so /ws/live would otherwise ignore
    HELIOSPHERE_CORS_ORIGINS entirely. An empty `allowed` list (the default)
    means no explicit restriction has been configured, so every origin is let
    through - same as a same-origin dashboard needs, and how this behaved
    before CORS was tightened. Once `allowed` is non-empty, it's enforced here
    exactly like the HTTP CORS policy is enforced by the middleware.
    """
    if not allowed:
        return True
    if "*" in allowed:
        return True
    return origin in allowed


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
