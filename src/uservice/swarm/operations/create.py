"""Swarm provisioning — Docker container lifecycle management."""

import logging
import uuid
from datetime import datetime, timezone
import docker
import docker.errors

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.uservice.swarm.models.storage.instance import SwarmInstance


import os

async def provision_swarm(
    session: AsyncSession,
    name: str,
    drone_count: int,
    created_by: str,
    project_id: str = "default-theater",
) -> dict:
    """Provision a new swarm instance.

    In production this would call Docker SDK to spawn a container.
    """
    swarm_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    container_name = f"isc-swarm-{swarm_id.hex[:8]}"
    
    try:
        client = docker.from_env()
        container = client.containers.run(
            image="isc-edge:latest",
            name=container_name,
            detach=True,
            labels={"isc-swarm": "true", "swarm_id": str(swarm_id)},
        )
        container_id = container.id
        endpoint_url = f"http://{container_name}:8090"
        status = "ready"
    except Exception as e:
        logger.warning("Docker provisioning unavailable (%s); registering swarm without Docker container", e)
        container_id = None
        endpoint_url = os.getenv("SWARM_DEFAULT_ENDPOINT")
        status = "ready"

    record = SwarmInstance(
        id=swarm_id,
        name=name,
        project_id=project_id,
        container_id=container_id,
        endpoint_url=endpoint_url,
        status=status,
        drone_count=drone_count,
        created_by=created_by,
    )
    session.add(record)
    await session.flush()

    logger.info("Swarm '%s' provisioned: id=%s project=%s drones=%d", name, swarm_id, project_id, drone_count)
    return {
        "id": str(record.id),
        "name": record.name,
        "project_id": record.project_id,
        "container_id": record.container_id,
        "endpoint_url": record.endpoint_url,
        "status": record.status,
        "drone_count": record.drone_count,
        "created_by": record.created_by,
        "created_at": record.created_at or now,
    }


async def get_swarm(session: AsyncSession, swarm_id: uuid.UUID) -> dict | None:
    """Look up a swarm instance by ID."""
    record = await session.get(SwarmInstance, swarm_id)
    if not record:
        return None
    return {
        "id": str(record.id),
        "name": record.name,
        "project_id": getattr(record, "project_id", "default-theater"),
        "container_id": record.container_id,
        "endpoint_url": record.endpoint_url,
        "status": record.status,
        "drone_count": record.drone_count,
        "created_by": record.created_by,
        "created_at": record.created_at,
    }


async def list_swarms(session: AsyncSession, project_id: str | None = None) -> list[dict]:
    """Return swarm instances, optionally filtered by tactical project_id."""
    stmt = select(SwarmInstance)
    if project_id:
        stmt = stmt.where(SwarmInstance.project_id == project_id)
    result = await session.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "project_id": getattr(r, "project_id", "default-theater"),
            "container_id": r.container_id,
            "endpoint_url": r.endpoint_url,
            "status": r.status,
            "drone_count": r.drone_count,
            "created_by": r.created_by,
            "created_at": r.created_at,
        }
        for r in records
    ]
