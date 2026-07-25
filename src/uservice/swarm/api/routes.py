"""Central Provisioning API routes.

Implements the provisioning-api.md contract.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.models.api.response import Response
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.database.engine import get_db
from src.uservice.swarm.models.contract.schemas import CreateSwarmRequest, SwarmResponse
from src.uservice.swarm.facade.swarm import SwarmFacade

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Swarm Provisioning"])


@router.post("/swarms", response_model=Response[SwarmResponse], status_code=201)
async def create_swarm(
    request: Request,
    body: CreateSwarmRequest,
    session: AsyncSession = Depends(get_db),
):
    """Create a new swarm instance."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await SwarmFacade.create(session=session, user=user_context)

    record = await facade.create_swarm(body=body)

    return Response[SwarmResponse].create(
        data=SwarmResponse(
            id=record["id"],
            name=record["name"],
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
    session: AsyncSession = Depends(get_db),
):
    """List all swarm instances."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await SwarmFacade.create(session=session, user=user_context)

    swarms = await facade.get_all_swarms()
    
    return {
        "data": [
            {
                "id": s["id"],
                "name": s["name"],
                "status": s["status"],
                "drone_count": s["drone_count"],
                "endpoint_url": s["endpoint_url"],
                "created_at": s["created_at"].isoformat() if not isinstance(s["created_at"], str) else s["created_at"],
            }
            for s in swarms
        ]
    }


@router.get("/swarms/{swarm_id}", response_model=Response[SwarmResponse])
async def get_swarm_details(
    request: Request,
    swarm_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get details of a specific swarm instance."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await SwarmFacade.create(session=session, user=user_context)

    try:
        record = await facade.get_swarm_details(swarm_id=swarm_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response[SwarmResponse].create(
        data=SwarmResponse(
            id=record["id"],
            name=record["name"],
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
    session: AsyncSession = Depends(get_db),
):
    """Initiate graceful termination of a swarm instance."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await SwarmFacade.create(session=session, user=user_context)

    try:
        record = await facade.delete_swarm(swarm_id=swarm_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "id": record["id"],
        "status": record["status"],
        "message": "Swarm termination initiated. Pending orders will complete before shutdown.",
    }
