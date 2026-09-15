from unittest.mock import AsyncMock

import pytest

from src.api.websocket import ConnectionManager, is_origin_allowed


async def test_broadcasts_to_all_connected_clients():
    manager = ConnectionManager()
    ws1, ws2 = AsyncMock(), AsyncMock()
    await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.broadcast("hello")

    ws1.send_text.assert_awaited_once_with("hello")
    ws2.send_text.assert_awaited_once_with("hello")
    assert manager.connection_count == 2


async def test_drops_dead_connections_encountered_during_broadcast():
    manager = ConnectionManager()
    alive, dead = AsyncMock(), AsyncMock()
    dead.send_text.side_effect = RuntimeError("connection already closed")
    await manager.connect(alive)
    await manager.connect(dead)

    await manager.broadcast("hello")

    assert manager.connection_count == 1
    alive.send_text.assert_awaited_once_with("hello")


async def test_disconnect_removes_the_client():
    manager = ConnectionManager()
    ws = AsyncMock()
    await manager.connect(ws)

    manager.disconnect(ws)

    assert manager.connection_count == 0


@pytest.mark.parametrize(
    "origin,allowed,expected",
    [
        (None, [], True),  # default: no restriction configured, same-origin app keeps working
        ("https://evil.example", [], True),  # still true: an empty list means "not configured", not "deny all"
        ("https://app.example", ["https://app.example"], True),
        ("https://evil.example", ["https://app.example"], False),
        (None, ["https://app.example"], False),  # a browser cross-origin request always sends Origin
        ("https://anything.example", ["*"], True),  # explicit opt-in to fully open
    ],
)
def test_is_origin_allowed(origin, allowed, expected):
    assert is_origin_allowed(origin, allowed) is expected
