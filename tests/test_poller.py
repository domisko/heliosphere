from datetime import datetime
from unittest.mock import AsyncMock

from src.analytics.sliding_window import RollingWindow
from src.ingestion.poller import Poller
from src.models import RawMagRecord, RawWindRecord

T0 = datetime(2026, 1, 1, 0, 0)
T1 = datetime(2026, 1, 1, 0, 1)


class FakeNOAAClient:
    def __init__(self, wind, mag):
        self._wind = wind
        self._mag = mag

    async def fetch_wind_and_mag(self):
        return self._wind, self._mag


def make_poller(wind, mag, on_update=None):
    client = FakeNOAAClient(wind, mag)
    duckdb_client = AsyncMock()
    redis_client = AsyncMock()
    poller = Poller(client, RollingWindow(), duckdb_client, redis_client, on_update=on_update)
    return poller, duckdb_client, redis_client


async def test_poll_once_enriches_persists_and_broadcasts():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    on_update = AsyncMock()

    poller, duckdb_client, redis_client = make_poller(wind, mag, on_update)
    record = await poller.poll_once()

    assert record is not None
    assert record.timestamp == T0
    assert record.bz == -10.0
    assert record.clock_angle == 180.0  # by=0, bz<0 -> due south
    duckdb_client.insert_record.assert_awaited_once_with(record)
    redis_client.push_latest.assert_awaited_once_with(record)
    on_update.assert_awaited_once_with(record)


async def test_poll_once_skips_a_minute_already_processed():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=0.0, bz_gsm=-10.0, bt=10.0)]
    on_update = AsyncMock()
    poller, duckdb_client, redis_client = make_poller(wind, mag, on_update)

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
