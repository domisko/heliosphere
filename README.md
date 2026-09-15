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
- On startup, backfills DuckDB and Redis from the ~24h of history NOAA's own
  feeds already return, so the dashboard has populated sparklines and history
  immediately instead of waiting ~2 hours to fill up from a cold start.
- Physics engine: IMF clock angle, Newell coupling function, 15-minute
  Bz rate-of-change, and a real-time solar-wind-driven storm heuristic —
  shown alongside NOAA's actual official G-scale (derived from the 3-hourly
  Kp index), so the dashboard is honest about which one is the live estimate
  and which is authoritative.
- DuckDB for durable historical telemetry; Redis for the last two hours of
  rolling state.
- FastAPI REST history endpoint plus a `/ws/live` WebSocket broadcasting
  every enriched frame to connected dashboards, with backlog replay for
  clients that connect mid-stream.
- Dark, terminal-styled dashboard, responsive down to phone width: IMF
  vector dial, live readouts, labeled time-series charts (gridlines + hover
  crosshair/tooltip) for speed and density, and a storm-tier banner that
  escalates color with severity. Every readout has a tap/click-to-expand
  explanation (works on touch, not just hover), and a "How This Works"
  section at the bottom explains the physics with cited sources.
- Optional storm alerting: fires a webhook whenever the live heuristic tier
  changes (escalates or subsides), compatible with Slack/Mattermost/
  Rocket.Chat and Discord incoming webhooks out of the box. Off by default;
  never fires during the startup backfill replay.

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
| `HELIOSPHERE_NOAA_KP_URL` | NOAA planetary K-index | Official 3-hourly Kp feed, used to compute NOAA's real G-scale |
| `HELIOSPHERE_POLL_INTERVAL_SECONDS` | `60.0` | How often to poll NOAA |
| `HELIOSPHERE_HTTP_TIMEOUT_SECONDS` | `10.0` | Per-request HTTP timeout |
| `HELIOSPHERE_MAX_RETRIES` | `4` | Retry attempts per NOAA fetch before giving up |
| `HELIOSPHERE_RETRY_BACKOFF_SECONDS` | `2.0` | Base for exponential backoff between retries |
| `HELIOSPHERE_DUCKDB_PATH` | `data/heliosphere.duckdb` | Path to the DuckDB file |
| `HELIOSPHERE_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `HELIOSPHERE_REDIS_HISTORY_MINUTES` | `120` | Rolling window kept in Redis |
| `HELIOSPHERE_CORS_ORIGINS` | `[]` (same-origin only) | Cross-origin allowlist — see [Security & Exposure](#security--exposure) |
| `HELIOSPHERE_LOG_LEVEL` | `INFO` | Python logging level |
| `HELIOSPHERE_ALERT_WEBHOOK_URL` | unset (alerting off) | Webhook to notify on storm tier changes — see [Storm Alerting](#storm-alerting) |

## Security & Exposure

This app has **no built-in authentication**. Anyone who can reach the port
can view the dashboard, read `/api/v1/telemetry/*`, and open `/ws/live` — the
data itself is public NOAA space weather, so that's a low-stakes default,
but it's worth being deliberate about, especially if you fork this for your
own setup:

- **CORS is locked down by default.** `HELIOSPHERE_CORS_ORIGINS` defaults to
  `[]` — no cross-origin access at all. The bundled dashboard doesn't need
  it (it's served same-origin by this same app), so the default costs
  nothing. Only set it if you're building a *separate* frontend that calls
  this API from another origin, e.g.
  `HELIOSPHERE_CORS_ORIGINS='["https://your-frontend.example"]'` (JSON array
  syntax, since it's a list). `'["*"]'` reopens it fully if you explicitly
  want that.
- **The WebSocket honors the same allowlist.** Starlette's CORS middleware
  only inspects regular HTTP requests — it silently never runs for a
  WebSocket upgrade. `/ws/live` re-checks the `Origin` header itself
  ([src/api/websocket.py](src/api/websocket.py)`::is_origin_allowed`), so
  setting `HELIOSPHERE_CORS_ORIGINS` restricts both consistently instead of
  leaving the socket as a silent bypass.
- **Docker Compose doesn't publish Redis to the host.** The `heliosphere`
  service reaches it over the internal compose network; Redis itself has no
  auth configured, so there's no reason to expose it. Don't add a `ports:`
  entry back for it unless you bind it to localhost specifically for
  debugging (`"127.0.0.1:6379:6379"`).
- **If you're exposing this beyond your LAN** (a public demo link, a
  port-forward, a public homelab domain), put a reverse proxy in front
  (Caddy, Traefik, nginx) and add your own access control there — basic
  auth, an OAuth2 proxy, or a private overlay network like Tailscale/
  Cloudflare Tunnel are all standard homelab patterns for this. This app
  intentionally doesn't attempt to build that itself.

## Storm Alerting

Set `HELIOSPHERE_ALERT_WEBHOOK_URL` to get a notification whenever the live
heuristic storm tier changes — escalates *or* subsides. Each request posts a
JSON body with both a `text` field (Slack, Mattermost, Rocket.Chat) and a
`content` field (Discord) carrying the same message, so it works with any of
those out of the box with zero extra configuration:

```bash
export HELIOSPHERE_ALERT_WEBHOOK_URL="https://hooks.slack.com/services/T000/B000/XXXX"
```

The message includes the tier transition, Bz, dBz/dt, speed, and NOAA's
official Kp/G-scale for context:

```
⚡ Heliosphere: live storm tier escalated — G1 (Minor) → G2 (Moderate)
Bz -11.20 nT | dBz/dt -1.80 nT/min | speed 560 km/s
NOAA official: G1 (Minor) (Kp 5.00)
2026-09-14T14:02:00Z
```

Notes:
- Off by default — no webhook, no requests, no failures possible.
- Never fires during the startup backfill replay (only on genuine live
  transitions), so restarting the app doesn't spam your channel with the
  last 24h of historical tier changes.
- A delivery failure is logged and swallowed, never crashes the poller.
- For a service that needs a different payload shape (e.g. ntfy.sh, which
  expects a plain-text body, or Home Assistant's webhook automations), adapt
  [src/alerts.py](src/alerts.py) — it's a single, self-contained function.
- Check whether it's currently active via `GET /api/v1/telemetry/status`
  (`alerting_enabled`).

## Testing

```bash
pytest -v --cov=src --cov-report=term-missing
```

82 tests, ~89% statement coverage. All tests are self-contained — NOAA and
webhook calls are mocked with `respx`, Redis is faked with `fakeredis`, and
DuckDB runs against a temp file — so the suite needs no network access or
running infra.

What's covered: the physics functions (clock angle, coupling, storm
classification, NOAA's official Kp→G-scale mapping) including boundary/edge
cases; the ingest→join→enrich pipeline, including the "active source"
filtering and field-name-aliasing bugs that only showed up against NOAA's
real (undocumented) response shape; startup backfill (`join_all`) and its
interaction with the live incremental path; the official-Kp lookup and its
resilience when the Kp feed fails independently of wind/mag; storm alert
delivery and its escalate/subside wording, plus the guarantee that backfill
never fires one despite replaying changing historical tiers; the
rolling-window derivative math; DuckDB upsert/history-window semantics; the
Redis rolling cache and trim behavior; the WebSocket connection manager
(broadcast, dead-connection cleanup) and its Origin allowlist enforcement;
and the REST route handlers.

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
| `GET /api/v1/telemetry/status` | Latest snapshot, connected client count, and whether alerting is enabled |
| `GET /health` | Liveness check |
| `WS /ws/live` | Streams each enriched frame as JSON on arrival; sends a `{"type": "backlog", "records": [...]}` frame on connect |
