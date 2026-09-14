"""Fire-and-forget webhook notification when the live storm tier changes.

Sends a JSON body with both `text` and `content` keys, which covers Slack,
Mattermost, and Rocket.Chat incoming webhooks (they read `text`) as well as
Discord webhooks (`content`) with a single request and no per-service
configuration. Disabled entirely unless HELIOSPHERE_ALERT_WEBHOOK_URL is set.
"""

import logging

import httpx

from src.config import settings
from src.models import EnrichedTelemetry

logger = logging.getLogger(__name__)

_TIER_RANK = {
    "G0 (Nominal)": 0,
    "G1 (Minor)": 1,
    "G2 (Moderate)": 2,
    "G3 (Strong)": 3,
    "G4-G5 (Extreme)": 4,
}


def _rank(tier: str) -> int:
    return _TIER_RANK.get(tier, 0)


def _format_message(previous_tier: str, record: EnrichedTelemetry) -> str:
    direction = "escalated" if _rank(record.storm_tier) > _rank(previous_tier) else "subsided"
    kp = f"{record.official_kp:.2f}" if record.official_kp is not None else "n/a"
    return (
        f"⚡ Heliosphere: live storm tier {direction} — {previous_tier} → {record.storm_tier}\n"
        f"Bz {record.bz:.2f} nT | dBz/dt {record.bz_derivative_15m:.2f} nT/min | speed {record.speed:.0f} km/s\n"
        f"NOAA official: {record.official_g_scale or 'n/a'} (Kp {kp})\n"
        f"{record.timestamp.isoformat()}Z"
    )


async def notify_storm_tier_change(
    client: httpx.AsyncClient, previous_tier: str, record: EnrichedTelemetry
) -> None:
    if not settings.alert_webhook_url:
        return

    message = _format_message(previous_tier, record)
    try:
        response = await client.post(
            settings.alert_webhook_url,
            json={"text": message, "content": message},
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Storm alert webhook delivery failed")
