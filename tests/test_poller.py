from datetime import datetime
from unittest.mock import AsyncMock

from src.analytics.sliding_window import RollingWindow
from src.ingestion.poller import Poller
from src.models import RawKpRecord, RawMagRecord, RawWindRecord

T0 = datetime(2026, 1, 1, 0, 0)
T1 = datetime(2026, 1, 1, 0, 1)
T2 = datetime(2026, 1, 1, 0, 2)


class FakeNOAAClient:
    def __init__(self, wind, mag, kp=None):
        self._wind = wind
        self._mag = mag
        self._kp = kp or []

    async def fetch_wind_and_mag(self):
        return self._wind, self._mag

    async def fetch_kp(self):
        return self._kp


def make_poller(wind, mag, kp=None, on_update=None):
    client = FakeNOAAClient(wind, mag, kp)
    duckdb_client = AsyncMock()
    redis_client = AsyncMock()
    poller = Poller(client, RollingWindow(), duckdb_client, redis_client, on_update=on_update)
    return poller, duckdb_client, redis_client


async def test_poll_once_enriches_persists_and_broadcasts():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    on_update = AsyncMock()

    poller, duckdb_client, redis_client = make_poller(wind, mag, on_update=on_update)
    record = await poller.poll_once()

    assert record is not None
    assert record.timestamp == T0
    assert record.bz == -10.0
    assert record.clock_angle == 180.0  # by=0, bz<0 -> due south
    assert record.official_kp is None  # no Kp feed configured for this test
    duckdb_client.insert_record.assert_awaited_once_with(record)
    redis_client.push_latest.assert_awaited_once_with(record)
    on_update.assert_awaited_once_with(record)


async def test_poll_once_skips_a_minute_already_processed():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    on_update = AsyncMock()
    poller, duckdb_client, redis_client = make_poller(wind, mag, on_update=on_update)

    first = await poller.poll_once()
    second = await poller.poll_once()  # NOAA hasn't published a new minute yet

    assert first is not None
    assert second is None
    duckdb_client.insert_record.assert_awaited_once()
    on_update.assert_awaited_once()


async def test_poll_once_returns_none_when_feeds_dont_overlap():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    poller, duckdb_client, redis_client = make_poller(wind, mag)

    result = await poller.poll_once()

    assert result is None
    duckdb_client.insert_record.assert_not_awaited()
    redis_client.push_latest.assert_not_awaited()


async def test_poll_once_advances_across_consecutive_minutes():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    poller, duckdb_client, _ = make_poller(wind, mag)
    await poller.poll_once()

    # Next cycle, NOAA has published a new minute
    poller._client = FakeNOAAClient(
        [RawWindRecord(time_tag=T1, speed=410.0, density=5.0, temperature=1e5)],
        [RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-12.0, bt=12.0)],
    )
    second = await poller.poll_once()

    assert second is not None
    assert second.timestamp == T1
    assert duckdb_client.insert_record.await_count == 2


async def test_poll_once_attaches_the_official_kp_and_g_scale():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    kp = [RawKpRecord(time_tag=datetime(2025, 12, 31, 21, 0), kp=6.33)]  # 3h before T0

    poller, _, _ = make_poller(wind, mag, kp=kp)
    record = await poller.poll_once()

    assert record.official_kp == 6.33
    assert record.official_g_scale == "G2 (Moderate)"


async def test_kp_fetch_failure_does_not_block_wind_mag_processing(monkeypatch):
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    poller, duckdb_client, _ = make_poller(wind, mag)

    async def failing_fetch_kp():
        raise RuntimeError("Exhausted retries fetching kp feed")

    monkeypatch.setattr(poller._client, "fetch_kp", failing_fetch_kp)

    record = await poller.poll_once()

    assert record is not None
    assert record.official_kp is None
    duckdb_client.insert_record.assert_awaited_once()


async def test_kp_reading_carries_forward_when_a_later_fetch_fails(monkeypatch):
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    kp = [RawKpRecord(time_tag=datetime(2025, 12, 31, 21, 0), kp=6.33)]
    poller, _, _ = make_poller(wind, mag, kp=kp)
    await poller.poll_once()

    poller._client = FakeNOAAClient(
        [RawWindRecord(time_tag=T1, speed=410.0, density=5.0, temperature=1e5)],
        [RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-12.0, bt=12.0)],
    )

    async def failing_fetch_kp():
        raise RuntimeError("boom")

    monkeypatch.setattr(poller._client, "fetch_kp", failing_fetch_kp)
    second = await poller.poll_once()

    assert second.official_kp == 6.33  # carried forward from the first cycle's cache


async def test_backfill_replays_all_overlapping_history_oldest_first():
    wind = [
        RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5),
        RawWindRecord(time_tag=T1, speed=410.0, density=5.0, temperature=1e5),
        RawWindRecord(time_tag=T2, speed=420.0, density=5.0, temperature=1e5),
    ]
    mag = [
        RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-5.0, bt=5.0),
        RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-6.0, bt=6.0),
        RawMagRecord(time_tag=T2, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-7.0, bt=7.0),
    ]
    poller, duckdb_client, redis_client = make_poller(wind, mag)

    count = await poller.backfill()

    assert count == 3
    assert duckdb_client.insert_record.await_count == 3
    assert redis_client.push_latest.await_count == 3
    # backfill primes dedup state, so a subsequent live poll of the same latest minute is a no-op
    assert await poller.poll_once() is None


async def test_backfill_does_not_broadcast_to_live_clients():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-5.0, bt=5.0)]
    on_update = AsyncMock()
    poller, _, _ = make_poller(wind, mag, on_update=on_update)

    await poller.backfill()

    on_update.assert_not_awaited()
