import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from src.analytics.classifier import classify_storm_level
from src.analytics.coupling import calculate_clock_angle, calculate_coupling
from src.analytics.sliding_window import RollingWindow
from src.config import settings
from src.ingestion.client import NOAAClient
from src.models import EnrichedTelemetry, RawMagRecord, RawWindRecord
from src.storage.duckdb_client import DuckDBClient
from src.storage.redis_client import RedisClient

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[EnrichedTelemetry], Awaitable[None]]


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
        fields = (wind.speed, wind.density, wind.temperature, mag.bx_gsm, mag.by_gsm, mag.bz_gsm, mag.bt)
        if any(f is None for f in fields):
            continue
        return wind.time_tag, {
            "speed": wind.speed,
            "density": wind.density,
            "temperature": wind.temperature,
            "bx": mag.bx_gsm,
            "by": mag.by_gsm,
            "bz": mag.bz_gsm,
            "bt": mag.bt,
        }
    return None


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

    async def poll_once(self) -> EnrichedTelemetry | None:
        wind_records, mag_records = await self._client.fetch_wind_and_mag()
        joined = join_latest(wind_records, mag_records)
        if joined is None:
            logger.warning("No complete wind+mag sample available this cycle")
            return None

        timestamp, fields = joined
        if timestamp == self._last_timestamp:
            return None  # NOAA hasn't published a new minute yet

        clock_angle = calculate_clock_angle(fields["by"], fields["bz"])
        coupling = calculate_coupling(fields["speed"], fields["by"], fields["bz"])
        storm_tier = classify_storm_level(fields["bz"], fields["speed"], coupling)
        bz_derivative = self._window.push_and_get_derivative(timestamp, fields["bz"])

        record = EnrichedTelemetry(
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
        )

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
