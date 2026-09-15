from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELIOSPHERE_", env_file=".env")

    noaa_wind_url: str = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
    noaa_mag_url: str = "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json"
    noaa_kp_url: str = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

    poll_interval_seconds: float = 60.0
    http_timeout_seconds: float = 10.0
    max_retries: int = 4
    retry_backoff_seconds: float = 2.0

    duckdb_path: Path = Path("data/heliosphere.duckdb")

    redis_url: str = "redis://localhost:6379/0"
    redis_history_minutes: int = 120

    # Empty by default: the bundled dashboard is served same-origin, so it needs
    # no cross-origin grant at all. Only set this if you're calling the API from
    # a *different* origin (a separate frontend, another domain). "*" is
    # supported for an explicit fully-open choice, but isn't the default: this
    # app has no auth, so an open-source fork left at a permissive default is
    # an easy way to unknowingly expose a public NOAA-data API to any website.
    cors_origins: list[str] = []
    log_level: str = "INFO"

    alert_webhook_url: str | None = None

    # Per-IP fixed-window limit on the REST API (does not apply to WebSocket
    # handshakes, which use ws_max_connections instead). Generous enough for
    # a real visitor's page load + occasional history fetch; tight enough to
    # blunt a simple hammering loop.
    rate_limit_requests: int = 60
    rate_limit_window_seconds: float = 60.0

    # Hard cap on simultaneous /ws/live connections, so an unbounded number
    # of open sockets can't exhaust memory.
    ws_max_connections: int = 100

    # Off by default: only enable this when the app sits behind a reverse
    # proxy/CDN you control (Caddy, nginx, Cloudflare Tunnel, ...) that
    # overwrites X-Forwarded-For with the real client IP. If the app is
    # directly reachable on its own port, enabling this lets any client
    # spoof that header and bypass its own rate limit entirely.
    trust_proxy_headers: bool = False


settings = Settings()
