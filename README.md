# Heliosphere

Real-time geomagnetic storm mission control terminal, built on NOAA SWPC's
public DSCOVR (L1) real-time solar wind feeds.

```
NOAA SWPC ──▶ Ingestion (httpx/Pydantic) ──▶ Analytics (Polars physics) ──▶ DuckDB + Redis ──▶ FastAPI/WebSocket ──▶ Dashboard
```

## Features

- Async polling of NOAA's `rtsw_wind_1m` and `rtsw_mag_1m` feeds, tolerant of
  the dropped/null minutes DSCOVR produces during instrument calibration.
- Physics engine: IMF clock angle, Newell coupling function, 15-minute
  Bz rate-of-change, and NOAA G-scale storm classification.
- DuckDB for durable historical telemetry; Redis for the last two hours of
  rolling state.
- FastAPI REST history endpoint plus a `/ws/live` WebSocket broadcasting
  every enriched frame to connected dashboards.
- Dark, terminal-styled dashboard: IMF vector dial, live readouts,
  sparklines, and a storm-tier banner that escalates color with severity.

## Running locally

Requires Python 3.11+ and a Redis instance.

```bash
pip install -e ".[dev]"
redis-server &
uvicorn src.api.main:app --reload
```

Then open http://localhost:8000.

## Running with Docker Compose

```bash
docker compose up --build
```

## Configuration

All settings are environment variables prefixed `HELIOSPHERE_` (see
[src/config.py](src/config.py)), e.g. `HELIOSPHERE_REDIS_URL`,
`HELIOSPHERE_POLL_INTERVAL_SECONDS`, `HELIOSPHERE_DUCKDB_PATH`.

## Tests

```bash
pytest
```

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/v1/telemetry/history?hours=24` | Historical enriched telemetry from DuckDB |
| `GET /api/v1/telemetry/status` | Latest snapshot + connected client count |
| `GET /health` | Liveness check |
| `WS /ws/live` | Streams each enriched frame as JSON on arrival |
