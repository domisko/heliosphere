import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.rate_limit import RateLimitMiddleware
from src.config import settings


def build_app(requests: int, window_seconds: float) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests=requests, window_seconds=window_seconds)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


def test_requests_under_the_limit_all_succeed():
    client = TestClient(build_app(requests=3, window_seconds=60.0))
    for _ in range(3):
        assert client.get("/ping").status_code == 200


def test_requests_over_the_limit_get_429_with_retry_after():
    client = TestClient(build_app(requests=2, window_seconds=60.0))
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200

    response = client.get("/ping")

    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_the_window_resets_after_it_elapses():
    client = TestClient(build_app(requests=1, window_seconds=0.05))
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429

    time.sleep(0.1)

    assert client.get("/ping").status_code == 200


def test_trust_proxy_headers_off_by_default_ignores_x_forwarded_for(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    client = TestClient(build_app(requests=1, window_seconds=60.0))

    assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    # Same underlying test-client connection, so it's still one IP's budget,
    # regardless of the (ignored) forwarded header claiming otherwise.
    assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


def test_trust_proxy_headers_tracks_forwarded_ips_independently(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    client = TestClient(build_app(requests=1, window_seconds=60.0))

    assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    # A different forwarded client gets its own, separate budget.
    assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
