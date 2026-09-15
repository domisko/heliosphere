"""Guards route wiring itself (prefixes, paths) without running the app's
lifespan — which needs live NOAA/Redis access and is exercised manually/in
Docker instead. This is what would have caught /health being accidentally
nested under the /api/v1 prefix."""

from unittest.mock import AsyncMock

from src.api.main import _reject_if_origin_disallowed, app
from src.config import settings


def _all_paths(routes) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(path)
        # A mounted sub-app (StaticFiles) exposes .routes directly; an
        # APIRouter included via app.include_router() is wrapped in a private
        # _IncludedRouter that holds the real router as .original_router.
        sub_routes = getattr(route, "routes", None)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            sub_routes = original_router.routes
        if sub_routes:
            paths |= _all_paths(sub_routes)
    return paths


def test_expected_routes_are_registered_at_the_correct_paths():
    paths = _all_paths(app.routes)
    assert "/health" in paths
    assert "/api/v1/telemetry/history" in paths
    assert "/api/v1/telemetry/status" in paths
    assert "/ws/live" in paths
    assert "/" in paths


async def test_ws_live_closes_a_connection_from_a_disallowed_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example"])
    websocket = AsyncMock()
    websocket.headers = {"origin": "https://evil.example"}

    rejected = await _reject_if_origin_disallowed(websocket)

    assert rejected is True
    websocket.close.assert_awaited_once_with(code=1008)


async def test_ws_live_admits_a_matching_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example"])
    websocket = AsyncMock()
    websocket.headers = {"origin": "https://app.example"}

    rejected = await _reject_if_origin_disallowed(websocket)

    assert rejected is False
    websocket.close.assert_not_awaited()


async def test_ws_live_admits_any_origin_when_unrestricted(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", [])  # the shipped default
    websocket = AsyncMock()
    websocket.headers = {"origin": "https://anything.example"}

    assert await _reject_if_origin_disallowed(websocket) is False
