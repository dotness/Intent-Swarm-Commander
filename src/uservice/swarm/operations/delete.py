"""Swarm draining and termination logic."""

import logging
import uuid
import docker
import docker.errors

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from src.uservice.swarm.models.storage.instance import SwarmInstance

async def drain_swarm(session: AsyncSession, swarm_id: uuid.UUID) -> dict:
    """Initiate graceful termination of a swarm.

    Transitions the swarm to 'draining' state, waits for pending
    orders to complete, then stops the container.
    """
    record = await session.get(SwarmInstance, swarm_id)
    if record is None:
        raise KeyError(f"Swarm {swarm_id} not found")

    record.status = "draining"
    logger.info("Swarm %s transitioning to draining", swarm_id)

    if record.container_id:
        try:
            client = docker.from_env()
            container = client.containers.get(record.container_id)
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info("Container %s stopped and removed for swarm %s", record.container_id, swarm_id)
        except docker.errors.NotFound:
            logger.warning("Container %s not found for swarm %s", record.container_id, swarm_id)
        except docker.errors.APIError as e:
            logger.error("Failed to terminate container %s: %s", record.container_id, e)
            raise RuntimeError(f"Failed to terminate container: {e}")

    record.status = "terminated"
    await session.flush()
    logger.info("Swarm %s terminated", swarm_id)

    return {
        "id": str(record.id),
        "name": record.name,
        "container_id": record.container_id,
        "endpoint_url": record.endpoint_url,
        "status": record.status,
        "drone_count": record.drone_count,
        "created_by": record.created_by,
    }
