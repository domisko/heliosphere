"""Per-IP fixed-window rate limiting for the REST API.

In-memory and single-instance: state resets on restart and isn't shared
across replicas. That's a deliberate simplification for a homelab
deployment, not an oversight - if this ever needs to scale horizontally,
the counters would need to move to Redis (already a dependency here) instead.

Starlette's BaseHTTPMiddleware only ever sees "http" scope requests, so a
WebSocket upgrade handshake passes through untouched; /ws/live's own
connection cap (see ConnectionManager) is what bounds it instead.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests: int, window_seconds: float) -> None:
        super().__init__(app)
        self._limit = requests
        self._window = window_seconds
        self._buckets: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
        self._last_sweep = time.monotonic()

    def _client_ip(self, request: Request) -> str:
        if settings.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _sweep_stale_buckets(self, now: float) -> None:
        # Bounds memory from the long tail of one-off visitor IPs on a
        # public demo; runs at most once per window, not on every request.
        if now - self._last_sweep < self._window:
            return
        stale = [ip for ip, (start, _) in self._buckets.items() if now - start >= self._window]
        for ip in stale:
            del self._buckets[ip]
        self._last_sweep = now

    async def dispatch(self, request: Request, call_next):
        now = time.monotonic()
        self._sweep_stale_buckets(now)

        ip = self._client_ip(request)
        window_start, count = self._buckets[ip]
        if now - window_start >= self._window:
            window_start, count = now, 0
        count += 1
        self._buckets[ip] = (window_start, count)

        if count > self._limit:
            retry_after = max(0.0, self._window - (now - window_start))
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        return await call_next(request)
