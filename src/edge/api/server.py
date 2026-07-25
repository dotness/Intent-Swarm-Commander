"""Edge communication API — receives target commands from the Swarm backend.

This lightweight HTTP server runs on the Raspberry Pi 5 and accepts
target_object_class assignments from the central Command Post.
"""

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# FastAPI imported conditionally for the edge server
try:
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
    import uvicorn

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("FastAPI not available on edge — using stub")


@dataclass
class TargetAssignment:
    """A target assignment received from the swarm backend."""

    target_object_class: str
    command_id: str
    confidence_threshold: float = 0.5


# Global state — current assignment
_current_assignment: TargetAssignment | None = None


def get_current_assignment() -> TargetAssignment | None:
    """Return the current target assignment, if any."""
    return _current_assignment


def create_edge_app() -> "FastAPI":
    """Create the edge node FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for the edge server")

    app = FastAPI(title="ISC Edge Node", version="0.1.0")

    class TargetRequest(BaseModel):
        target_object_class: str = Field(description="YOLO-E class to identify")
        command_id: str = Field(description="Originating swarm command ID")
        confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    @app.post("/target")
    async def assign_target(body: TargetRequest):
        """Receive a target assignment from the swarm backend."""
        global _current_assignment
        _current_assignment = TargetAssignment(
            target_object_class=body.target_object_class,
            command_id=body.command_id,
            confidence_threshold=body.confidence_threshold,
        )
        logger.info(
            "Target assigned: class='%s' command=%s threshold=%.2f",
            body.target_object_class, body.command_id, body.confidence_threshold,
        )
        return {"status": "accepted", "target": body.target_object_class}

    @app.get("/target")
    async def get_target():
        """Get the current target assignment."""
        if _current_assignment is None:
            return {"status": "idle", "target": None}
        return {
            "status": "active",
            "target": _current_assignment.target_object_class,
            "command_id": _current_assignment.command_id,
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "node": "edge"}

    return app


def run_edge_server(host: str = "0.0.0.0", port: int = 8090) -> None:
    """Start the edge server (blocking)."""
    app = create_edge_app()
    logger.info("Starting edge server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
