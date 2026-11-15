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
        self.require_scope("swarm:create")

        record = await provision_swarm(
            session=self.session,
            name=body.name,
            drone_count=body.drone_count,
            created_by=self.user.get("sub") or "unknown",
            project_id=body.project_id,
        )
        return record

    async def get_all_swarms(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """List swarm instances scoped optionally by project_id."""
        self.require_scope("swarm:read")

        swarms = await list_swarms(self.session, project_id=project_id)
        return swarms

    async def get_swarm_details(self, swarm_id: uuid.UUID) -> dict[str, Any]:
        """Get details of a specific swarm instance."""
        self.require_scope("swarm:read")
        
        record = await get_swarm(self.session, swarm_id)
        if record is None:
            raise ResourceDoesNotExist("Swarm not found")
        return record

    async def get_swarm_telemetry(
        self,
        swarm_id: uuid.UUID,
        project_id: str | None = None,
        live_store: Any = None,
    ) -> Any:
        """Delegate live pushed MQTT telemetry projection lookup to TelemetryFacade."""
        from src.uservice.telemetry.facade.telemetry import TelemetryFacade

        telemetry_facade = await TelemetryFacade.create(
            session=self.session,
            user=self.user,
            live_store=live_store,
        )
        return await telemetry_facade.get_swarm_telemetry_projection(
            swarm_id=swarm_id,
            project_id=project_id,
        )

    async def delete_swarm(self, swarm_id: uuid.UUID) -> dict[str, Any]:
        """Initiate graceful termination of a swarm instance."""
        # await self.permissions.require_access("swarm:delete")
        
        try:
            record = await drain_swarm(self.session, swarm_id)
        except KeyError:
            raise ResourceDoesNotExist("Swarm not found")
        return record
