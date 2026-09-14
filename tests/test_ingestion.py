from datetime import datetime, timezone

import httpx
import pytest
import respx

from src.config import settings
from src.ingestion.client import NOAAClient
from src.ingestion.poller import join_latest
from src.models import RawMagRecord, RawWindRecord

T0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)


async def test_fetch_wind_skips_malformed_and_null_rows():
    good = {
        "time_tag": "2026-01-01T00:00:00Z",
        "speed": 400.0,
        "density": 5.0,
        "temperature": 100000.0,
    }
    malformed = {"time_tag": "not-a-timestamp", "speed": 400.0}

    with respx.mock:
        respx.get(settings.noaa_wind_url).mock(return_value=httpx.Response(200, json=[good, malformed]))
        client = NOAAClient()
        try:
            records = await client.fetch_wind()
        finally:
            await client.aclose()

    assert len(records) == 1
    assert records[0].speed == 400.0


async def test_fetch_retries_then_succeeds_after_transient_failure():
    with respx.mock:
        route = respx.get(settings.noaa_mag_url)
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=[{"time_tag": "2026-01-01T00:00:00Z", "bx_gsm": 1.0, "by_gsm": 2.0, "bz_gsm": -3.0, "bt": 3.7}]),
        ]
        client = NOAAClient()
        try:
            records = await client.fetch_mag()
        finally:
            await client.aclose()

    assert len(records) == 1
    assert records[0].bz_gsm == -3.0


def test_join_latest_picks_newest_minute_with_complete_data_on_both_feeds():
    wind = [
        RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5),
        RawWindRecord(time_tag=T1, speed=None, density=5.0, temperature=1e5),  # dropped mid-calibration
    ]
    mag = [
        RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=2.0, bz_gsm=-3.0, bt=3.5),
        RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=2.0, bz_gsm=-3.0, bt=3.5),
    ]

    result = join_latest(wind, mag)

    assert result is not None
    timestamp, fields = result
    assert timestamp == T0  # T1 is incomplete on the wind side, so it's skipped
    assert fields["bz"] == -3.0


def test_join_latest_returns_none_when_feeds_dont_overlap():
    wind = [RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5)]
    mag = [RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=2.0, bz_gsm=-3.0, bt=3.5)]

    assert join_latest(wind, mag) is None
