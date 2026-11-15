"""Central Provisioning API routes.

Implements the provisioning-api.md contract.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.models.api.response import Response
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.database.engine import get_db
from src.uservice.security.middleware import require_scopes
from src.uservice.swarm.models.contract.schemas import CreateSwarmRequest, SwarmResponse
from src.uservice.swarm.facade.swarm import SwarmFacade

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Swarm Provisioning"])


@router.post("/swarms", response_model=Response[SwarmResponse], status_code=201)
async def create_swarm(
    request: Request,
    body: CreateSwarmRequest,
    user: dict = Depends(require_scopes(["swarm:create"])),
    session: AsyncSession = Depends(get_db),
):
    """Create a new swarm instance."""
    facade = await SwarmFacade.create(session=session, user=user)

    record = await facade.create_swarm(body=body)

    return Response[SwarmResponse].create(
        data=SwarmResponse(
            id=record["id"],
            name=record["name"],
            project_id=record.get("project_id", "default-theater"),
            status=record["status"],
            drone_count=record["drone_count"],
            endpoint_url=record["endpoint_url"],
            created_at=record["created_at"].isoformat() if not isinstance(record["created_at"], str) else record["created_at"],
            created_by=record["created_by"],
        )
    )


@router.get("/swarms")
async def get_all_swarms(
    request: Request,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """List swarm instances filtered optionally by project_id."""
    facade = await SwarmFacade.create(session=session, user=user)

    swarms = await facade.get_all_swarms(project_id=project_id)

    swarm_list = [
        {
            "id": s["id"],
            "name": s["name"],
            "project_id": s.get("project_id", "default-theater"),
            "status": s["status"],
            "drone_count": s["drone_count"],
            "endpoint_url": s["endpoint_url"],
            "created_at": s["created_at"].isoformat() if s.get("created_at") and not isinstance(s["created_at"], str) else str(s.get("created_at") or ""),
        }
        for s in swarms
    ]
    return {
        "swarms": swarm_list,
        "data": swarm_list,
    }


@router.get("/swarms/{swarm_id}", response_model=Response[SwarmResponse])
async def get_swarm_details(
    request: Request,
    swarm_id: uuid.UUID,
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Get details of a specific swarm instance."""
    facade = await SwarmFacade.create(session=session, user=user)

    try:
        record = await facade.get_swarm_details(swarm_id=swarm_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response[SwarmResponse].create(
        data=SwarmResponse(
            id=record["id"],
            name=record["name"],
            project_id=record.get("project_id", "default-theater"),
            status=record["status"],
            drone_count=record["drone_count"],
            endpoint_url=record["endpoint_url"],
            created_at=record["created_at"].isoformat() if not isinstance(record["created_at"], str) else record["created_at"],
            created_by=record["created_by"],
        )
    )


@router.delete("/swarms/{swarm_id}", status_code=202)
async def delete_swarm(
    request: Request,
    swarm_id: uuid.UUID,
    user: dict = Depends(require_scopes(["swarm:delete"])),
    session: AsyncSession = Depends(get_db),
):
    """Initiate graceful termination of a swarm instance."""
    facade = await SwarmFacade.create(session=session, user=user)

    try:
        record = await facade.delete_swarm(swarm_id=swarm_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "id": record["id"],
        "status": record["status"],
        "message": "Swarm termination initiated. Pending orders will complete before shutdown.",
    }


@router.get("/swarms/{swarm_id}/telemetry")
async def get_swarm_telemetry(
    request: Request,
    swarm_id: uuid.UUID,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Read live pushed MQTT telemetry projection for a swarm via SwarmFacade."""
    live_store = getattr(request.app.state, "telemetry_store", None)
    facade = await SwarmFacade.create(session=session, user=user)

    try:
        projection = await facade.get_swarm_telemetry(
            swarm_id=swarm_id,
            project_id=project_id,
            live_store=live_store,
        )
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    return projection.model_dump()
