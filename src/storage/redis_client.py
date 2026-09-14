"""Rolling in-memory state cache: last N minutes of enriched telemetry."""

import json

import redis.asyncio as redis

from src.config import settings
from src.models import EnrichedTelemetry

ROLLING_KEY = "heliosphere:telemetry:rolling"
LATEST_KEY = "heliosphere:telemetry:latest"


class RedisClient:
    def __init__(self, url: str | None = None) -> None:
        self._redis = redis.from_url(url or settings.redis_url, decode_responses=True)

    async def push_latest(self, record: EnrichedTelemetry) -> None:
        payload = record.model_dump_json()
        async with self._redis.pipeline() as pipe:
            pipe.rpush(ROLLING_KEY, payload)
            pipe.ltrim(ROLLING_KEY, -settings.redis_history_minutes, -1)
            pipe.set(LATEST_KEY, payload)
            await pipe.execute()

    async def get_recent(self, minutes: int | None = None) -> list[dict]:
        count = minutes or settings.redis_history_minutes
        raw = await self._redis.lrange(ROLLING_KEY, -count, -1)
        return [json.loads(item) for item in raw]

    async def get_latest(self) -> dict | None:
        raw = await self._redis.get(LATEST_KEY)
        return json.loads(raw) if raw else None

    async def ping(self) -> bool:
        return await self._redis.ping()

    async def aclose(self) -> None:
        await self._redis.aclose()
