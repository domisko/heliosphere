from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router


class FakeDuckDB:
    async def query_history(self, hours: int):
        return [{"speed": 400.0, "hours_requested": hours}]


class FakeRedis:
    def __init__(self, latest=None):
        self._latest = latest

    async def get_latest(self):
        return self._latest


class FakeConnectionManager:
    connection_count = 3


def build_app(duckdb=None, redis=None, manager=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.duckdb_client = duckdb or FakeDuckDB()
    app.state.redis_client = redis or FakeRedis()
    app.state.connection_manager = manager or FakeConnectionManager()
    return app


def test_history_endpoint_passes_hours_through_and_wraps_records():
    client = TestClient(build_app())
    response = client.get("/api/v1/telemetry/history?hours=6")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["records"][0]["hours_requested"] == 6


def test_history_endpoint_defaults_to_24_hours():
    client = TestClient(build_app())
    response = client.get("/api/v1/telemetry/history")
    assert response.json()["records"][0]["hours_requested"] == 24


def test_history_endpoint_rejects_out_of_range_hours():
    client = TestClient(build_app())
    assert client.get("/api/v1/telemetry/history?hours=0").status_code == 422


def test_status_endpoint_reports_latest_and_connection_count():
    client = TestClient(build_app(redis=FakeRedis(latest={"speed": 500.0})))
    response = client.get("/api/v1/telemetry/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected_clients"] == 3
    assert body["latest"]["speed"] == 500.0


def test_status_endpoint_reports_alerting_disabled_by_default(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "alert_webhook_url", None)
    client = TestClient(build_app())
    assert client.get("/api/v1/telemetry/status").json()["alerting_enabled"] is False


def test_status_endpoint_reports_alerting_enabled_when_webhook_configured(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "alert_webhook_url", "https://example.com/webhook")
    client = TestClient(build_app())
    assert client.get("/api/v1/telemetry/status").json()["alerting_enabled"] is True
