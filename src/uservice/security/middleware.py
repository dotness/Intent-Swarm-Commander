"""MCP Auth Gateway middleware — validates agent identity on every request."""

import logging
from typing import Any, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from src.uservice.security.jwt import TokenValidationError, decode_token, extract_scopes, verify_scope

logger = logging.getLogger(__name__)

# Routes that bypass auth (health checks, public endpoints, login)
PUBLIC_PATHS = frozenset({"/", "/health", "/docs", "/openapi.json", "/redoc", "/api/v1/auth/login"})


async def auth_gateway_middleware(request: Request, call_next: Callable) -> Response:
    """FastAPI middleware that enforces OAuth 2.1 token validation.

    Every request must carry a valid Bearer token in the Authorization header
    unless the path is in PUBLIC_PATHS. Invalid or missing tokens result in
    401/403 responses — the system fails closed per FR-009.
    """
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    # Allow public paths through
    if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
        return await call_next(request)

    # Extract Bearer token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("Missing or malformed Authorization header for %s", path)
        return JSONResponse(
            status_code=401,
            content={"error": "Missing or invalid Authorization header"},
        )

    token = auth_header[7:]  # Strip "Bearer "

    try:
        payload = decode_token(token)
    except TokenValidationError as e:
        logger.warning("Auth rejected for %s: %s", path, e.reason)
        return JSONResponse(
            status_code=401,
            content={"error": e.reason},
        )

    # Attach decoded claims to request state for downstream use
    request.state.auth_claims = payload
    request.state.auth_scopes = extract_scopes(payload)
    request.state.agent_id = payload.get("sub", "unknown")

    return await call_next(request)


def require_scopes(required: list[str]) -> Callable[[Request], Any]:
    """FastAPI dependency enforcing required OAuth 2.1 scopes on route handlers."""

    async def _dependency(request: Request) -> dict[str, Any]:
        claims = getattr(request.state, "auth_claims", None)
        if not claims:
            raise HTTPException(status_code=401, detail="Missing authentication claims")
        for scope in required:
            if not verify_scope(claims, scope):
                raise HTTPException(status_code=403, detail=f"Missing required scope: {scope}")
        return claims

    return _dependency
