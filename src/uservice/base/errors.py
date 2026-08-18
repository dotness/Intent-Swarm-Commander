"""Centralised exception handlers for FastAPI."""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ISCError(Exception):
    """Base exception for Intent Swarm Commander domain errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(ISCError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} '{resource_id}' not found", status_code=404)


class ConflictError(ISCError):
    def __init__(self, message: str):
        super().__init__(message, status_code=409)


class ValidationError(ISCError):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class GatewayUnavailableError(ISCError):
    """Raised when the MCP Gateway or Safety Layer is unreachable — fail closed."""

    def __init__(self):
        super().__init__(
            "Security gateway unavailable — system is failing closed. No commands can be processed.",
            status_code=503,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI application."""

    @app.exception_handler(ISCError)
    async def isc_error_handler(_request: Request, exc: ISCError) -> JSONResponse:
        error_id = str(uuid4())
        logger.error("ISCError [%s] %s (status=%d)", error_id, exc.message, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "error_id": error_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        error_id = str(uuid4())
        logger.exception("Unhandled error [%s]: %s", error_id, exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "error_id": error_id},
        )
