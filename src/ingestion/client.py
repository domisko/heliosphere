import asyncio
import logging
from typing import TypeVar

import httpx
from pydantic import ValidationError

from src.config import settings
from src.models import RawKpRecord, RawMagRecord, RawWindRecord

logger = logging.getLogger(__name__)

T = TypeVar("T", RawWindRecord, RawMagRecord, RawKpRecord)


class NOAAClient:
    """Async client for NOAA SWPC real-time solar wind (RTSW) feeds.

    DSCOVR drops individual minutes during instrument calibration flips, so
    parsing is defensive: a malformed row is logged and skipped rather than
    failing the whole fetch.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_json(self, url: str) -> list[dict]:
        last_exc: Exception | None = None
        for attempt in range(settings.max_retries):
            try:
                response = await self._client.get(url)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                delay = settings.retry_backoff_seconds * (2 ** attempt)
                logger.warning(
                    "Fetch failed for %s (attempt %d/%d): %s. Retrying in %.1fs",
                    url, attempt + 1, settings.max_retries, exc, delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError(f"Exhausted retries fetching {url}") from last_exc

    async def fetch_wind(self) -> list[RawWindRecord]:
        raw = await self._get_json(settings.noaa_wind_url)
        return _parse_records(raw, RawWindRecord)

    async def fetch_mag(self) -> list[RawMagRecord]:
        raw = await self._get_json(settings.noaa_mag_url)
        return _parse_records(raw, RawMagRecord)

    async def fetch_wind_and_mag(self) -> tuple[list[RawWindRecord], list[RawMagRecord]]:
        return await asyncio.gather(self.fetch_wind(), self.fetch_mag())

    async def fetch_kp(self) -> list[RawKpRecord]:
        raw = await self._get_json(settings.noaa_kp_url)
        return _parse_records(raw, RawKpRecord)


def _parse_records(raw: list[dict], model: type[T]) -> list[T]:
    """Parse rows and keep only NOAA's currently active source per minute.

    The wind/mag feeds carry redundant rows from multiple L1 spacecraft
    (ACE, IMAP, DSCOVR) for the same minute; only the row flagged `active` is
    authoritative. The Kp feed has no such redundancy (no `active` field),
    so it passes through unfiltered.
    """
    records: list[T] = []
    for row in raw:
        try:
            record = model.model_validate(row)
        except ValidationError as exc:
            logger.debug("Skipping malformed %s row: %s", model.__name__, exc)
            continue
        if getattr(record, "active", True):
            records.append(record)
    return records
