"""Intent Swarm Commander — MVP Backend Service.

FastAPI application that translates SMEAC military intents into
coordinated drone-swarm commands using pydantic-ai multi-agent pipelines
and Temporal durable workflows.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os

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
        if getattr(event, "flight_status", None) == "approaching" and getattr(event, "snapshot_uri", None):
            import uuid
            from sqlalchemy import select
            from src.uservice.hitl.models.storage.decision import HitlDecision

            try:
                cmd_uuid = uuid.UUID(str(event.mission_id))
            except (ValueError, TypeError):
                cmd_uuid = uuid.UUID(str(event.swarm_id))

            async with async_session() as session:
                existing = await session.execute(
                    select(HitlDecision.id).where(
                        HitlDecision.status == "pending",
                        HitlDecision.drone_id == event.drone_id,
                        HitlDecision.swarm_command_id == cmd_uuid,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    snap_url = (
                        f"/api/v1/analytics/detections/{event.event_id}/snapshot"
                        f"?project_id={event.project_id}"
                    )
                    session.add(
                        HitlDecision(
                            id=uuid.uuid4(),
                            project_id=event.project_id,
                            swarm_command_id=cmd_uuid,
                            commander_id="system-vision",
                            decision="pending",
                            action_summary=(
                                f"Target '{event.target_class}' detected by {event.drone_id} "
                                f"(conf={float(event.confidence or 0.0):.2f}) — confirm engagement"
                            ),
                            timeout_seconds=120,
                            status="pending",
                            is_threat_override=False,
                            drone_id=event.drone_id,
                            detection_event_id=str(event.event_id),
                            snapshot_url=snap_url,
                            target_class=event.target_class,
                            confidence=event.confidence,
                        )
                    )
                    await session.commit()

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

    temporal_worker_task: asyncio.Task | None = None

    async def _run_temporal_worker() -> None:
        from temporalio.client import Client as TemporalClient
        from temporalio.worker import Worker
        from src.uservice.smeac.operations.process import (
            ProcessSmeacWorkflow,
            dispatch_edge_mission_activity,
            parse_smeac_activity,
            safety_check_activity,
        )

        temporal_url = os.getenv("TEMPORAL_URL", "temporal:7233")
        task_queue = os.getenv("ISC_TASK_QUEUE", "isc-smeac-queue")
        for attempt in range(1, 16):
            try:
                client = await TemporalClient.connect(temporal_url)
                worker = Worker(
                    client,
                    task_queue=task_queue,
                    workflows=[ProcessSmeacWorkflow],
                    activities=[
                        parse_smeac_activity,
                        safety_check_activity,
                        dispatch_edge_mission_activity,
                    ],
                )
                logger.info("Temporal worker started on queue '%s' (%s)", task_queue, temporal_url)
                await worker.run()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Temporal worker connect attempt %d failed: %s", attempt, exc)
                await asyncio.sleep(2.0)

    temporal_worker_task = asyncio.create_task(_run_temporal_worker())

    yield

    if temporal_worker_task is not None:
        temporal_worker_task.cancel()
        try:
            await temporal_worker_task
        except asyncio.CancelledError:
            pass
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
