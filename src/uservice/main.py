"""Intent Swarm Commander — MVP Backend Service.

FastAPI application that translates SMEAC military intents into
coordinated drone-swarm commands using pydantic-ai multi-agent pipelines
and Temporal durable workflows.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.uservice.analytics.api.routes import router as analytics_router
from src.uservice.analytics.operations.minio_store import MinioStore, MinioUnavailableError
from src.uservice.database.engine import async_session, init_db
from src.uservice.smeac.api.routes import router as smeac_router
from src.uservice.hitl.api.routes import router as hitl_router
from src.uservice.swarm.api.routes import router as swarm_router
from src.uservice.security.routes import router as auth_router
from src.uservice.telemetry.api.routes import router as telemetry_router
from src.uservice.telemetry.facade.telemetry import get_default_live_store
from src.uservice.telemetry.operations.compactor import ParquetCompactor
from src.uservice.telemetry.operations.ingestor import TelemetryIngestor
from src.uservice.threat.api.routes import router as threat_router
from src.uservice.threat.operations.correlator import TargetCorrelator
from src.uservice.threat.operations.graph_client import MemgraphClient, MemgraphUnavailableError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB tables, telemetry ingestor/compactor, and service clients."""
    logger.info("Starting Intent Swarm Commander…")
    await init_db()

    live_store = getattr(app.state, "telemetry_store", None) or get_default_live_store()
    minio_store = getattr(app.state, "minio_store", None) or MinioStore()
    await minio_store.ensure_buckets()

    memgraph_client = getattr(app.state, "memgraph_client", None) or MemgraphClient()
    await memgraph_client.ensure_schema()

    correlator = TargetCorrelator(graph_client=memgraph_client)

    async def _handle_detection(event) -> None:
        await correlator.ingest_detection(event)

    compactor = getattr(app.state, "parquet_compactor", None) or ParquetCompactor(minio_store=minio_store)
    ingestor = getattr(app.state, "telemetry_ingestor", None) or TelemetryIngestor(
        live_store=live_store,
        compactor=compactor,
        detection_callback=_handle_detection,
        db_session_factory=async_session,
    )

    app.state.telemetry_store = live_store
    app.state.minio_store = minio_store
    app.state.memgraph_client = memgraph_client
    app.state.parquet_compactor = compactor
    app.state.telemetry_ingestor = ingestor

    compactor.start()
    ingestor.start()

    yield

    await ingestor.stop()
    await compactor.stop()
    await memgraph_client.close()
    logger.info("Shutting down Intent Swarm Commander.")


app = FastAPI(
    title="Intent Swarm Commander",
    version="0.2.0",
    description="SMEAC → Swarm Command translation service",
    lifespan=lifespan,
)

from src.uservice.security.middleware import auth_gateway_middleware
from src.uservice.security.proxy import swarm_proxy_middleware
from starlette.middleware.base import BaseHTTPMiddleware

# Middlewares are executed in reverse order of addition (LIFO).
# 1. CORS executes outermost (handles preflight OPTIONS and adds CORS headers to all responses)
# 2. Auth Gateway validates JWT tokens
# 3. Proxy routes swarm proxy requests
app.add_middleware(BaseHTTPMiddleware, dispatch=swarm_proxy_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=auth_gateway_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router, prefix="/api/v1")
app.include_router(smeac_router, prefix="/api/v1")
app.include_router(hitl_router, prefix="/api/v1")
app.include_router(swarm_router, prefix="/api/v1")
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(threat_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


@app.exception_handler(MemgraphUnavailableError)
async def _memgraph_unavailable_handler(request: Request, exc: MemgraphUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "memgraph_unavailable", "detail": str(exc)},
    )


@app.exception_handler(MinioUnavailableError)
async def _minio_unavailable_handler(request: Request, exc: MinioUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "minio_unavailable", "detail": str(exc)},
    )


@app.exception_handler(RuntimeError)
async def _runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": str(exc)},
    )


@app.get("/health")
async def health():
    """Service health endpoint."""
    return {"status": "ok", "service": "intent-swarm-commander"}
