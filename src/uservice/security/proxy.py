"""MCP Auth Gateway reverse proxy router."""

import logging
from typing import Callable

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def swarm_proxy_middleware(request: Request, call_next: Callable) -> Response:
    """FastAPI middleware that routes /api/v1/swarms/{swarm_id} requests to dedicated containers.

    Implements FR-016 dynamic routing.
    """
    path = request.url.path

    # Only proxy swarm-specific data endpoints, not the central provisioning API
    if not path.startswith("/api/v1/swarms/") or path == "/api/v1/swarms":
        return await call_next(request)

    # Pass through endpoints handled directly by the microservice application routers
    if any(endpoint in path for endpoint in ["/orders", "/hitl", "/telemetry"]):
        return await call_next(request)

    # Example path: /api/v1/swarms/1234/commands
    parts = path.split("/")
    if len(parts) < 6:
        return await call_next(request)

    swarm_id = parts[4]

    # In integration phase, we lookup the swarm's endpoint_url from the DB
    from src.uservice.database.engine import async_session
    from src.uservice.swarm.models.storage.instance import SwarmInstance
    import uuid

    try:
        swarm_uuid = uuid.UUID(swarm_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "Swarm not found or not available"})

    async with async_session() as session:
        swarm_record = await session.get(SwarmInstance, swarm_uuid)

    if not swarm_record or not swarm_record.endpoint_url:
        return JSONResponse(status_code=404, content={"error": "Swarm not found or not available"})

    target_url = swarm_record.endpoint_url
    # Reconstruct the proxied path
    # Example: target_url is http://swarm-1234:8000/api/v1/swarms/1234
    # We want to append the rest of the path, e.g., /orders
    remaining_path = "/" + "/".join(parts[5:])
    
    # Simple proxy implementation using httpx
    try:
        async with httpx.AsyncClient() as client:
            headers = dict(request.headers)
            headers.pop("host", None)
            
            # Read body if present
            body = await request.body()
            
            logger.info("Proxying request to dedicated swarm container: %s", target_url + remaining_path)
            
            proxy_res = await client.request(
                method=request.method,
                url=target_url + remaining_path,
                headers=headers,
                content=body,
                timeout=30.0
            )
            
            return Response(
                content=proxy_res.content,
                status_code=proxy_res.status_code,
                headers=dict(proxy_res.headers)
            )
    except httpx.RequestError as e:
        logger.error("Failed to proxy request to swarm %s: %s", swarm_id, e)
        return JSONResponse(status_code=502, content={"error": "Bad Gateway - Swarm container unreachable"})
