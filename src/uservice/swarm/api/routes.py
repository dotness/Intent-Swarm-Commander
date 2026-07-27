"""Central Provisioning API routes.

Implements the provisioning-api.md contract.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

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


@router.get("/swarms/{swarm_id}/telemetry")
async def get_swarm_telemetry(
    request: Request,
    swarm_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """Aggregate telemetry data for a swarm."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await SwarmFacade.create(session=session, user=user_context)

    try:
        record = await facade.get_swarm_details(swarm_id=swarm_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    endpoint_url = record.get("endpoint_url")
    if not endpoint_url:
        return {"drones": []}

    try:
        async with httpx.AsyncClient() as client:
            # We assume a single drone container per swarm for MVP
            # and that endpoint_url points to it
            res = await client.get(f"{endpoint_url}/telemetry", timeout=5.0)
            res.raise_for_status()
            telemetry_data = res.json()
            
            # Reformat to match the dashboard's expected 'drones' array
            return {
                "drones": [
                    {
                        "id": f"{swarm_id}-drone-1",
                        "status": telemetry_data.get("status", "idle"),
                        "battery_pct": telemetry_data.get("battery", 100),
                        "position": {
                            "lat": telemetry_data.get("position", {}).get("lat", 0),
                            "lng": telemetry_data.get("position", {}).get("lon", 0),
                            "alt_m": telemetry_data.get("position", {}).get("alt", 0)
                        },
                        "heading": telemetry_data.get("heading", 0),
                        "speed": telemetry_data.get("speed", 0),
                        "current_mission": telemetry_data.get("status", "idle")
                    }
                ]
            }
    except Exception as e:
        logger.error("Failed to fetch telemetry for swarm %s: %s", swarm_id, e)
        # Return empty list if we can't reach the drone
        return {"drones": []}
