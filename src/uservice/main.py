"""Intent Swarm Commander — MVP Backend Service.

FastAPI application that translates SMEAC military intents into
coordinated drone-swarm commands using pydantic-ai multi-agent pipelines
and Temporal durable workflows.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.uservice.database.engine import init_db
from src.uservice.smeac.api.routes import router as smeac_router
from src.uservice.hitl.api.routes import router as hitl_router
from src.uservice.swarm.api.routes import router as swarm_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB tables and Temporal client on startup."""
    logger.info("Starting Intent Swarm Commander…")
    await init_db()
    yield
    logger.info("Shutting down Intent Swarm Commander.")


app = FastAPI(
    title="Intent Swarm Commander",
    version="0.1.0",
    description="SMEAC → Swarm Command translation service",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.uservice.security.middleware import auth_gateway_middleware
from src.uservice.security.proxy import swarm_proxy_middleware
from starlette.middleware.base import BaseHTTPMiddleware

# Middlewares are executed bottom-up.
# Proxy first, then Auth Gateway
app.add_middleware(BaseHTTPMiddleware, dispatch=swarm_proxy_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=auth_gateway_middleware)


app.include_router(smeac_router, prefix="/api/v1")
app.include_router(hitl_router, prefix="/api/v1")
app.include_router(swarm_router, prefix="/api/v1")
