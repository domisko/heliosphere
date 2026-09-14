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

    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"


settings = Settings()
