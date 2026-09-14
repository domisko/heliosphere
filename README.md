# Heliosphere

Real-time geomagnetic storm mission control terminal, built on NOAA SWPC's
public real-time solar wind (RTSW) feeds.

```
NOAA SWPC ──▶ Ingestion (httpx/Pydantic) ──▶ Analytics (Polars physics) ──▶ DuckDB + Redis ──▶ FastAPI/WebSocket ──▶ Dashboard
```

## Features

- Async polling of NOAA's `rtsw_wind_1m` and `rtsw_mag_1m` feeds. NOAA reports
  redundant rows per minute from multiple L1 spacecraft (ACE, DSCOVR,
  SOLAR-1, IMAP); Heliosphere keeps only the row NOAA flags `active`, and
  skips any minute where the two feeds don't have a matching, complete pair.
- Physics engine: IMF clock angle, Newell coupling function, 15-minute
  Bz rate-of-change, and a NOAA G-scale-inspired storm classification.
- DuckDB for durable historical telemetry; Redis for the last two hours of
  rolling state.
- FastAPI REST history endpoint plus a `/ws/live` WebSocket broadcasting
  every enriched frame to connected dashboards, with backlog replay for
  clients that connect mid-stream.
- Dark, terminal-styled dashboard, responsive down to phone width: IMF
  vector dial, live readouts, sparklines, and a storm-tier banner that
  escalates color with severity. Every readout has a tap/click-to-expand
  explanation (works on touch, not just hover), and a "How This Works"
  section at the bottom explains the physics with cited sources.

## Prerequisites

- Python 3.11+ (developed and tested on 3.12)
- Redis (local install, Docker, or point `HELIOSPHERE_REDIS_URL` at a hosted instance)
- Docker + Docker Compose, if you'd rather not install Python/Redis locally

## Running locally

```bash
git clone <this-repo>
cd heliosphere
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Start Redis (pick one):

```bash
brew install redis && brew services start redis   # macOS
# or
docker run -p 6379:6379 redis:7-alpine
```

Then run the app:

```bash
uvicorn src.api.main:app --reload
```

Open http://localhost:8000 — the dashboard starts polling NOAA immediately
and the first live frame appears within one polling interval (60s).

## Running with Docker Compose

Bundles Redis for you; no local Python setup needed.

```bash
docker compose up --build
```

## Configuration

All settings are environment variables prefixed `HELIOSPHERE_`, read via
[src/config.py](src/config.py). Create a `.env` file (auto-loaded) or export
them directly.

| Variable | Default | Description |
| --- | --- | --- |
| `HELIOSPHERE_NOAA_WIND_URL` | NOAA `rtsw_wind_1m.json` | Solar wind plasma feed |
| `HELIOSPHERE_NOAA_MAG_URL` | NOAA `rtsw_mag_1m.json` | IMF magnetic field feed |
| `HELIOSPHERE_NOAA_KP_URL` | NOAA planetary K-index | Reserved for future use |
| `HELIOSPHERE_POLL_INTERVAL_SECONDS` | `60.0` | How often to poll NOAA |
| `HELIOSPHERE_HTTP_TIMEOUT_SECONDS` | `10.0` | Per-request HTTP timeout |
| `HELIOSPHERE_MAX_RETRIES` | `4` | Retry attempts per NOAA fetch before giving up |
| `HELIOSPHERE_RETRY_BACKOFF_SECONDS` | `2.0` | Base for exponential backoff between retries |
| `HELIOSPHERE_DUCKDB_PATH` | `data/heliosphere.duckdb` | Path to the DuckDB file |
| `HELIOSPHERE_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `HELIOSPHERE_REDIS_HISTORY_MINUTES` | `120` | Rolling window kept in Redis |
| `HELIOSPHERE_CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `HELIOSPHERE_LOG_LEVEL` | `INFO` | Python logging level |

## Testing

```bash
pytest -v --cov=src --cov-report=term-missing
```

47 tests, ~89% statement coverage. All tests are self-contained — NOAA calls
are mocked with `respx`, Redis is faked with `fakeredis`, and DuckDB runs
against a temp file — so the suite needs no network access or running infra.

What's covered: the physics functions (clock angle, coupling, storm
classification) including boundary/edge cases; the ingest→join→enrich
pipeline, including the "active source" filtering and field-name-aliasing
bugs that only showed up against NOAA's real (undocumented) response shape;
the rolling-window derivative math; DuckDB upsert/history-window semantics;
the Redis rolling cache and trim behavior; the WebSocket connection manager
(broadcast, dead-connection cleanup); and the REST route handlers.

What's intentionally not unit-tested: the FastAPI `lifespan` wiring in
[src/api/main.py](src/api/main.py) (it constructs real NOAA/DuckDB/Redis
clients and starts the poller loop — an integration concern exercised via
Docker Compose and manual verification, not mocked in isolation) and the
`Poller.run_forever` sleep loop itself, which is a thin wrapper around
`poll_once` (fully tested) plus `asyncio.sleep`.

## CI/CD

- **[.github/workflows/ci.yml](.github/workflows/ci.yml)** — runs the test
  suite with coverage and does a sanity-check Docker build on every push and
  pull request to `main`.
- **[.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml)**
  — on every push to `main` and on version tags (`v*.*.*`), runs the tests
  again and then builds and pushes a multi-tagged image to
  [GitHub Container Registry](https://ghcr.io) at
  `ghcr.io/<owner>/<repo>` (tags: `latest` on `main`, the semver on a version
  tag, and `sha-<commit>` always). Uses the repo's built-in `GITHUB_TOKEN` —
  no extra secrets to configure. If pushes fail with a permissions error,
  check Settings → Actions → General → Workflow permissions is set to
  "Read and write permissions".

Deploying the published image anywhere that runs containers:

```bash
docker run -p 8000:8000 \
  -e HELIOSPHERE_REDIS_URL=redis://<your-redis-host>:6379/0 \
  ghcr.io/<owner>/<repo>:latest
```

## API

| Endpoint | Description |
| --- | --- |
| `GET /` | The dashboard |
| `GET /api/v1/telemetry/history?hours=24` | Historical enriched telemetry from DuckDB |
| `GET /api/v1/telemetry/status` | Latest snapshot + connected client count |
| `GET /health` | Liveness check |
| `WS /ws/live` | Streams each enriched frame as JSON on arrival; sends a `{"type": "backlog", "records": [...]}` frame on connect |
