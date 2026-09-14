import httpx
import respx

from src.alerts import notify_storm_tier_change
from src.config import settings
from tests.factories import make_record

WEBHOOK_URL = "https://hooks.example.com/services/T00/B00/XXXX"


async def test_no_request_is_made_when_webhook_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", None)

    with respx.mock:
        route = respx.post(WEBHOOK_URL)
        async with httpx.AsyncClient() as client:
            await notify_storm_tier_change(client, "G0 (Nominal)", make_record(storm_tier="G1 (Minor)"))

    assert route.call_count == 0


async def test_posts_a_slack_and_discord_compatible_payload_on_escalation(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", WEBHOOK_URL)
    record = make_record(storm_tier="G2 (Moderate)", bz=-12.5, official_kp=6.0, official_g_scale="G2 (Moderate)")

    with respx.mock:
        route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient() as client:
            await notify_storm_tier_change(client, "G1 (Minor)", record)

    assert route.call_count == 1
    body = route.calls[0].request.content.decode()
    assert "escalated" in body
    assert "G1 (Minor)" in body
    assert "G2 (Moderate)" in body
    assert '"text"' in body and '"content"' in body


async def test_describes_a_de_escalation_as_subsided(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", WEBHOOK_URL)
    record = make_record(storm_tier="G0 (Nominal)")

    with respx.mock:
        route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient() as client:
            await notify_storm_tier_change(client, "G1 (Minor)", record)

    body = route.calls[0].request.content.decode()
    assert "subsided" in body


async def test_webhook_failure_is_swallowed_not_raised(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", WEBHOOK_URL)
    record = make_record(storm_tier="G1 (Minor)")

    with respx.mock:
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            await notify_storm_tier_change(client, "G0 (Nominal)", record)  # must not raise
