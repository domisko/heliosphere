from datetime import datetime, timezone

import httpx
import pytest
import respx

from src.config import settings
from src.ingestion.client import NOAAClient
from src.ingestion.poller import join_all, join_latest
from src.models import RawKpRecord, RawMagRecord, RawWindRecord

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


async def test_fetch_raises_after_exhausting_all_retries(monkeypatch):
    monkeypatch.setattr(settings, "max_retries", 2)
    monkeypatch.setattr(settings, "retry_backoff_seconds", 0.01)

    with respx.mock:
        respx.get(settings.noaa_wind_url).mock(return_value=httpx.Response(503))
        client = NOAAClient()
        try:
            with pytest.raises(RuntimeError, match="Exhausted retries"):
                await client.fetch_wind()
        finally:
            await client.aclose()


async def test_fetch_wind_and_mag_fetches_both_feeds_concurrently():
    wind_payload = [
        {"time_tag": "2026-01-01T00:00:00", "proton_speed": 400.0, "proton_density": 5.0, "proton_temperature": 1e5}
    ]
    mag_payload = [{"time_tag": "2026-01-01T00:00:00", "bx_gsm": 1.0, "by_gsm": 2.0, "bz_gsm": -3.0, "bt": 3.7}]

    with respx.mock:
        respx.get(settings.noaa_wind_url).mock(return_value=httpx.Response(200, json=wind_payload))
        respx.get(settings.noaa_mag_url).mock(return_value=httpx.Response(200, json=mag_payload))
        client = NOAAClient()
        try:
            wind, mag = await client.fetch_wind_and_mag()
        finally:
            await client.aclose()

    assert len(wind) == 1
    assert wind[0].speed == 400.0
    assert len(mag) == 1
    assert mag[0].bz_gsm == -3.0


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


def test_raw_wind_record_maps_noaas_actual_proton_field_names():
    # NOAA's live rtsw_wind_1m feed uses proton_speed/proton_density/proton_temperature,
    # not the bare speed/density/temperature names — this guards against that mismatch.
    record = RawWindRecord.model_validate(
        {
            "time_tag": "2026-01-01T00:00:00",
            "proton_speed": 450.5,
            "proton_density": 6.1,
            "proton_temperature": 90000.0,
        }
    )
    assert record.speed == 450.5
    assert record.density == 6.1
    assert record.temperature == 90000.0


async def test_fetch_wind_keeps_only_the_noaa_flagged_active_source():
    # Each feed carries redundant rows per minute from multiple L1 spacecraft
    # (ACE/IMAP/DSCOVR); only the row NOAA flags `active` is authoritative.
    active = {
        "time_tag": "2026-01-01T00:00:00",
        "active": True,
        "proton_speed": 400.0,
        "proton_density": 5.0,
        "proton_temperature": 1e5,
    }
    inactive_backup = {
        "time_tag": "2026-01-01T00:00:00",
        "active": False,
        "proton_speed": 999.0,
        "proton_density": 999.0,
        "proton_temperature": 999.0,
    }

    with respx.mock:
        respx.get(settings.noaa_wind_url).mock(
            return_value=httpx.Response(200, json=[active, inactive_backup])
        )
        client = NOAAClient()
        try:
            records = await client.fetch_wind()
        finally:
            await client.aclose()

    assert len(records) == 1
    assert records[0].speed == 400.0


def test_raw_kp_record_maps_noaas_capitalized_kp_field():
    # NOAA's planetary K-index feed uses the JSON key "Kp" (capital K).
    record = RawKpRecord.model_validate({"time_tag": "2026-09-07T00:00:00", "Kp": 6.33})
    assert record.kp == 6.33


async def test_fetch_kp_parses_the_live_feed_shape():
    payload = [{"time_tag": "2026-09-07T00:00:00", "Kp": 1.33, "a_running": 5, "station_count": 8}]

    with respx.mock:
        respx.get(settings.noaa_kp_url).mock(return_value=httpx.Response(200, json=payload))
        client = NOAAClient()
        try:
            records = await client.fetch_kp()
        finally:
            await client.aclose()

    assert len(records) == 1
    assert records[0].kp == 1.33


def test_join_all_returns_every_complete_minute_oldest_first():
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)
    wind = [
        RawWindRecord(time_tag=t2, speed=420.0, density=5.0, temperature=1e5),
        RawWindRecord(time_tag=T0, speed=400.0, density=5.0, temperature=1e5),
        RawWindRecord(time_tag=T1, speed=None, density=5.0, temperature=1e5),  # incomplete, excluded
    ]
    mag = [
        RawMagRecord(time_tag=t2, bx_gsm=1.0, by_gsm=2.0, bz_gsm=-7.0, bt=7.3),
        RawMagRecord(time_tag=T0, bx_gsm=1.0, by_gsm=2.0, bz_gsm=-3.0, bt=3.5),
        RawMagRecord(time_tag=T1, bx_gsm=1.0, by_gsm=2.0, bz_gsm=-5.0, bt=5.4),
    ]

    result = join_all(wind, mag)

    assert [timestamp for timestamp, _ in result] == [T0, t2]
    assert result[0][1]["bz"] == -3.0
    assert result[1][1]["bz"] == -7.0
