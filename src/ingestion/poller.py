import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from src.analytics.classifier import classify_g_scale_from_kp, classify_storm_level
from src.analytics.coupling import calculate_clock_angle, calculate_coupling
from src.analytics.sliding_window import RollingWindow
from src.config import settings
from src.ingestion.client import NOAAClient
from src.models import EnrichedTelemetry, RawKpRecord, RawMagRecord, RawWindRecord
from src.storage.duckdb_client import DuckDBClient
from src.storage.redis_client import RedisClient

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[EnrichedTelemetry], Awaitable[None]]


def _merge_fields(wind: RawWindRecord, mag: RawMagRecord) -> dict | None:
    fields = (wind.speed, wind.density, wind.temperature, mag.bx_gsm, mag.by_gsm, mag.bz_gsm, mag.bt)
    if any(f is None for f in fields):
        return None
    return {
        "speed": wind.speed,
        "density": wind.density,
        "temperature": wind.temperature,
        "bx": mag.bx_gsm,
        "by": mag.by_gsm,
        "bz": mag.bz_gsm,
        "bt": mag.bt,
    }


def join_latest(
    wind_records: list[RawWindRecord], mag_records: list[RawMagRecord]
) -> tuple[datetime, dict] | None:
    """Inner-join the most recent minute for which both feeds report complete data.

    Walks backward from the newest sample because DSCOVR frequently drops one
    side of a minute during calibration; older minutes are more likely complete.
    """
    mag_by_time = {record.time_tag: record for record in mag_records}
    for wind in sorted(wind_records, key=lambda r: r.time_tag, reverse=True):
        mag = mag_by_time.get(wind.time_tag)
        if mag is None:
            continue
        fields = _merge_fields(wind, mag)
        if fields is None:
            continue
        return wind.time_tag, fields
    return None


def join_all(
    wind_records: list[RawWindRecord], mag_records: list[RawMagRecord]
) -> list[tuple[datetime, dict]]:
    """All complete overlapping minutes, oldest first.

    NOAA's rtsw feeds each return roughly the last 24h of samples, not just
    the latest minute — this is what lets a fresh start backfill history
    instead of beginning with empty sparklines.
    """
    mag_by_time = {record.time_tag: record for record in mag_records}
    joined: list[tuple[datetime, dict]] = []
    for wind in sorted(wind_records, key=lambda r: r.time_tag):
        mag = mag_by_time.get(wind.time_tag)
        if mag is None:
            continue
        fields = _merge_fields(wind, mag)
        if fields is None:
            continue
        joined.append((wind.time_tag, fields))
    return joined


class Poller:
    def __init__(
        self,
        client: NOAAClient,
        window: RollingWindow,
        duckdb_client: DuckDBClient,
        redis_client: RedisClient,
        on_update: UpdateCallback | None = None,
    ) -> None:
        self._client = client
        self._window = window
        self._duckdb = duckdb_client
        self._redis = redis_client
        self._on_update = on_update
        self._last_timestamp: datetime | None = None
        self._kp_records: list[RawKpRecord] = []

    async def _refresh_kp(self) -> None:
        """Best-effort refresh of the cached Kp history. Kept separate from
        the wind/mag path so a Kp outage never blocks the higher-value
        per-minute solar wind update — we just keep showing the last known
        official reading until the feed recovers."""
        try:
            records = await self._client.fetch_kp()
        except Exception:
            logger.warning("Kp fetch failed this cycle; keeping last known reading", exc_info=True)
            return
        if records:
            self._kp_records = records

    def _kp_asof(self, timestamp: datetime) -> RawKpRecord | None:
        """Most recent Kp reading at or before `timestamp` (NOAA publishes it
        3-hourly, far coarser than the per-minute solar wind cadence)."""
        candidates = [r for r in self._kp_records if r.time_tag <= timestamp]
        return max(candidates, key=lambda r: r.time_tag) if candidates else None

    def _enrich(self, timestamp: datetime, fields: dict) -> EnrichedTelemetry:
        clock_angle = calculate_clock_angle(fields["by"], fields["bz"])
        coupling = calculate_coupling(fields["speed"], fields["by"], fields["bz"])
        storm_tier = classify_storm_level(fields["bz"], fields["speed"], coupling)
        bz_derivative = self._window.push_and_get_derivative(timestamp, fields["bz"])

        kp_record = self._kp_asof(timestamp)
        official_kp = kp_record.kp if kp_record else None
        official_g_scale = classify_g_scale_from_kp(official_kp) if official_kp is not None else None

        return EnrichedTelemetry(
            timestamp=timestamp,
            speed=fields["speed"],
            density=fields["density"],
            temperature=fields["temperature"],
            bx=fields["bx"],
            by=fields["by"],
            bz=fields["bz"],
            bt=fields["bt"],
            clock_angle=clock_angle,
            coupling_index=coupling,
            storm_tier=storm_tier,
            bz_derivative_15m=bz_derivative,
            official_kp=official_kp,
            official_g_scale=official_g_scale,
        )

    async def backfill(self) -> int:
        """Replay every complete minute NOAA currently returns (~24h) so a
        fresh start doesn't begin with empty history. Safe to call once at
        startup, before the live polling loop begins; records are processed
        oldest-first so the rolling-window derivative and `_last_timestamp`
        dedup state come out primed correctly for the live path that follows.
        """
        wind_records, mag_records = await self._client.fetch_wind_and_mag()
        await self._refresh_kp()

        joined = join_all(wind_records, mag_records)
        count = 0
        for timestamp, fields in joined:
            record = self._enrich(timestamp, fields)
            await self._duckdb.insert_record(record)
            await self._redis.push_latest(record)
            self._last_timestamp = timestamp
            count += 1
        return count

    async def poll_once(self) -> EnrichedTelemetry | None:
        wind_records, mag_records = await self._client.fetch_wind_and_mag()
        await self._refresh_kp()

        joined = join_latest(wind_records, mag_records)
        if joined is None:
            logger.warning("No complete wind+mag sample available this cycle")
            return None

        timestamp, fields = joined
        if timestamp == self._last_timestamp:
            return None  # NOAA hasn't published a new minute yet

        record = self._enrich(timestamp, fields)

        await self._duckdb.insert_record(record)
        await self._redis.push_latest(record)
        if self._on_update is not None:
            await self._on_update(record)

        self._last_timestamp = timestamp
        return record

    async def run_forever(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Poll cycle failed; will retry next interval")
            await asyncio.sleep(settings.poll_interval_seconds)
