from fastapi import APIRouter, Query, Request

from src.config import settings

router = APIRouter(prefix="/api/v1")


@router.get("/telemetry/history")
async def get_history(request: Request, hours: int = Query(24, ge=1, le=24 * 30)):
    records = await request.app.state.duckdb_client.query_history(hours)
    return {"count": len(records), "records": records}


@router.get("/telemetry/status")
async def get_status(request: Request):
    latest = await request.app.state.redis_client.get_latest()
    return {
        "connected_clients": request.app.state.connection_manager.connection_count,
        "alerting_enabled": settings.alert_webhook_url is not None,
        "latest": latest,
    }
