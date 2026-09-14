import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.analytics.sliding_window import RollingWindow
from src.api.routes import router
from src.api.websocket import ConnectionManager
from src.config import settings
from src.ingestion.client import NOAAClient
from src.ingestion.poller import Poller
from src.models import EnrichedTelemetry
from src.storage.duckdb_client import DuckDBClient
from src.storage.redis_client import RedisClient

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.noaa_client = NOAAClient()
    app.state.duckdb_client = DuckDBClient(settings.duckdb_path)
    app.state.redis_client = RedisClient()
    app.state.connection_manager = ConnectionManager()

    async def broadcast(record: EnrichedTelemetry) -> None:
        await app.state.connection_manager.broadcast(record.model_dump_json())

    app.state.poller = Poller(
        client=app.state.noaa_client,
        window=RollingWindow(),
        duckdb_client=app.state.duckdb_client,
        redis_client=app.state.redis_client,
        on_update=broadcast,
    )

    try:
        backfilled = await app.state.poller.backfill()
        logger.info("Backfilled %d historical records from NOAA's rolling feed window", backfilled)
    except Exception:
        logger.exception("Startup backfill failed; continuing with live polling only")

    app.state.poller_task = asyncio.create_task(app.state.poller.run_forever())

    yield

    app.state.poller_task.cancel()
    try:
        await app.state.poller_task
    except asyncio.CancelledError:
        pass
    await app.state.noaa_client.aclose()
    await app.state.redis_client.aclose()
    app.state.duckdb_client.close()


app = FastAPI(title="Heliosphere Mission Control", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR / "static"), name="static")


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    manager: ConnectionManager = websocket.app.state.connection_manager
    redis_client: RedisClient = websocket.app.state.redis_client

    await manager.connect(websocket)
    try:
        backlog = await redis_client.get_recent(minutes=30)
        if backlog:
            await websocket.send_text(json.dumps({"type": "backlog", "records": backlog}))
        while True:
            await websocket.receive_text()  # client is passive; drain to detect disconnects
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
