"""Swarm Domain Facade."""

import logging
import uuid
from typing import Any

from src.uservice.base.facade.base import DomainFacade
from src.uservice.swarm.models.contract.schemas import CreateSwarmRequest
from src.uservice.swarm.operations.create import get_swarm, list_swarms, provision_swarm
from src.uservice.swarm.operations.delete import drain_swarm
from src.uservice.base.errors import ResourceDoesNotExist

logger = logging.getLogger(__name__)

class SwarmFacade(DomainFacade):
    """Facade for Swarm lifecycle and provisioning."""

    async def create_swarm(self, body: CreateSwarmRequest) -> dict[str, Any]:
        """Create a new swarm instance."""
        # await self.permissions.require_access("swarm:create")
        
        record = await provision_swarm(
            session=self.session,
            name=body.name,
            drone_count=body.drone_count,
            created_by=self.user.get("sub", "commander-default"),
        )
        return record

    async def get_all_swarms(self) -> list[dict[str, Any]]:
        """List all swarm instances."""
        # await self.permissions.require_access("swarm:read")
        
        swarms = await list_swarms(self.session)
        return swarms

    async def get_swarm_details(self, swarm_id: uuid.UUID) -> dict[str, Any]:
        """Get details of a specific swarm instance."""
        # await self.permissions.require_access("swarm:read")
        
        record = await get_swarm(self.session, swarm_id)
        if record is None:
            raise ResourceDoesNotExist("Swarm not found")
        return record

    async def delete_swarm(self, swarm_id: uuid.UUID) -> dict[str, Any]:
        """Initiate graceful termination of a swarm instance."""
        # await self.permissions.require_access("swarm:delete")
        
        try:
            record = await drain_swarm(self.session, swarm_id)
        except KeyError:
            raise ResourceDoesNotExist("Swarm not found")
        return record
