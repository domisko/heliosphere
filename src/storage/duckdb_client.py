"""Persistent historical telemetry storage via DuckDB, backed by a local file."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from src.models import EnrichedTelemetry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    timestamp TIMESTAMP PRIMARY KEY,
    date DATE,
    speed DOUBLE,
    density DOUBLE,
    temperature DOUBLE,
    bx DOUBLE,
    "by" DOUBLE,
    bz DOUBLE,
    bt DOUBLE,
    clock_angle DOUBLE,
    coupling_index DOUBLE,
    storm_tier VARCHAR,
    bz_derivative_15m DOUBLE
)
"""


class DuckDBClient:
    """Thin async wrapper around DuckDB's synchronous API via a thread executor."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(path))
        self._conn.execute(_SCHEMA)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_date ON telemetry(date)")

    async def insert_record(self, record: EnrichedTelemetry) -> None:
        await asyncio.to_thread(self._insert_sync, record)

    def _insert_sync(self, record: EnrichedTelemetry) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.timestamp,
                record.timestamp.date(),
                record.speed,
                record.density,
                record.temperature,
                record.bx,
                record.by,
                record.bz,
                record.bt,
                record.clock_angle,
                record.coupling_index,
                record.storm_tier,
                record.bz_derivative_15m,
            ],
        )

    async def query_history(self, hours: int) -> list[dict]:
        return await asyncio.to_thread(self._query_history_sync, hours)

    def _query_history_sync(self, hours: int) -> list[dict]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = self._conn.execute(
            "SELECT * EXCLUDE (date) FROM telemetry WHERE timestamp >= ? ORDER BY timestamp",
            [cutoff],
        )
        columns = [d[0] for d in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def close(self) -> None:
        self._conn.close()
