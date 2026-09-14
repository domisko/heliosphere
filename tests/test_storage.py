from datetime import UTC, datetime

import fakeredis

from src.config import settings
from src.storage.duckdb_client import DuckDBClient
from src.storage.redis_client import RedisClient
from tests.factories import make_record


async def test_insert_and_query_history_roundtrip(tmp_path):
    client = DuckDBClient(tmp_path / "test.duckdb")
    try:
        await client.insert_record(make_record(timestamp=datetime.now(UTC).replace(tzinfo=None)))
        results = await client.query_history(hours=24)
        assert len(results) == 1
        assert results[0]["bz"] == -3.0
        assert results[0]["storm_tier"] == "G0 (Nominal)"
    finally:
        client.close()


async def test_query_history_excludes_records_older_than_the_window(tmp_path):
    client = DuckDBClient(tmp_path / "test.duckdb")
    try:
        await client.insert_record(make_record(timestamp=datetime(2000, 1, 1)))
        results = await client.query_history(hours=24)
        assert results == []
    finally:
        client.close()


async def test_insert_upserts_on_duplicate_timestamp(tmp_path):
    client = DuckDBClient(tmp_path / "test.duckdb")
    try:
        ts = datetime.now(UTC).replace(tzinfo=None)
        await client.insert_record(make_record(timestamp=ts, speed=400.0))
        await client.insert_record(make_record(timestamp=ts, speed=999.0))
        results = await client.query_history(hours=24)
        assert len(results) == 1
        assert results[0]["speed"] == 999.0
    finally:
        client.close()


async def test_redis_rolling_window_trims_to_configured_size(monkeypatch):
    monkeypatch.setattr(settings, "redis_history_minutes", 3)
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = RedisClient(client=fake)

    for i in range(5):
        await client.push_latest(make_record(speed=300.0 + i))

    recent = await client.get_recent()
    assert len(recent) == 3
    assert [r["speed"] for r in recent] == [302.0, 303.0, 304.0]


async def test_redis_get_latest_returns_most_recent_push(monkeypatch):
    monkeypatch.setattr(settings, "redis_history_minutes", 120)
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = RedisClient(client=fake)

    await client.push_latest(make_record(speed=400.0))
    await client.push_latest(make_record(speed=410.0))

    latest = await client.get_latest()
    assert latest["speed"] == 410.0


async def test_redis_get_latest_is_none_before_any_push():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = RedisClient(client=fake)
    assert await client.get_latest() is None
