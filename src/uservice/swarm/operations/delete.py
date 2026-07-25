"""Swarm draining and termination logic."""

import logging
import uuid

logger = logging.getLogger(__name__)


async def drain_swarm(swarm_id: uuid.UUID) -> dict:
    """Initiate graceful termination of a swarm.

    Transitions the swarm to 'draining' state, waits for pending
    orders to complete, then stops the container.
    """
    from src.uservice.swarm.operations.create import _swarms

    record = _swarms.get(str(swarm_id))
    if record is None:
        raise KeyError(f"Swarm {swarm_id} not found")

    record["status"] = "draining"
    logger.info("Swarm %s transitioning to draining", swarm_id)

    # In production: wait for pending orders, then stop container
    # For MVP: immediately transition to terminated
    record["status"] = "terminated"
    logger.info("Swarm %s terminated", swarm_id)

    return record
