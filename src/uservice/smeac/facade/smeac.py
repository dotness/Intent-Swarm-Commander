"""SMEAC Domain Facade."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.uservice.base.facade.base import DomainFacade
from src.uservice.smeac.models.contract.schemas import SmeacOrderCreateRequest
from src.uservice.operation.facade import start_workflow
from src.uservice.smeac.operations.process import ProcessSmeacInput, ProcessSmeacWorkflow
from src.uservice.smeac.models.storage.smeac import SmeacOrder

logger = logging.getLogger(__name__)

class SmeacFacade(DomainFacade):
    """Facade for SMEAC intent ingestion and processing."""

    async def submit_smeac_order(self, swarm_id: uuid.UUID, body: SmeacOrderCreateRequest) -> dict[str, Any]:
        """Submit a SMEAC order and launch the Temporal workflow."""
        # 1. Enforce RBAC
        self.require_scope("smeac:create")
        
        order_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        parsed_fields = {
            "situation": "parsed" if body.situation else "missing",
            "mission": "parsed" if body.mission else "missing",
            "execution": "parsed" if body.execution else "missing",
            "admin_logistics": "parsed" if body.admin_logistics else "not_provided",
            "command_signal": "parsed" if body.command_signal else "not_provided",
        }

        order_record = SmeacOrder(
            id=order_id,
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=swarm_id,
            situation=body.situation,
            mission=body.mission,
            execution=body.execution,
            admin_logistics=body.admin_logistics,
            command_signal=body.command_signal,
        )
        self.session.add(order_record)
        await self.session.flush()
        
        # 2. Schedule workflow via Operation wrapper
        wf_input = ProcessSmeacInput(
            order_id=str(order_id),
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=str(swarm_id),
            situation=body.situation,
            mission=body.mission,
            execution=body.execution,
            admin_logistics=body.admin_logistics,
            command_signal=body.command_signal,
        )
        try:
            await start_workflow(
                ProcessSmeacWorkflow,
                wf_input,
                task_queue="smeac-queue",
                workflow_id=f"smeac-{order_id}",
            )
            logger.info("Launched Temporal workflow smeac-%s for user %s", order_id, self.user.get("sub"))
        except Exception as e:
            logger.error("Failed to start Temporal workflow: %s", e)
            raise e
        
        return {
            "order_id": order_id,
            "status": "submitted",
            "swarm_instance_id": swarm_id,
            "parsed_fields": parsed_fields,
            "created_at": now,
        }

    async def get_order_status(self, swarm_id: uuid.UUID, order_id: uuid.UUID) -> dict[str, Any]:
        """Get the status of a submitted SMEAC order."""
        # 1. Enforce RBAC
        self.require_scope("smeac:read")
        
        # 2. Fetch from DB
        record = await self.session.get(SmeacOrder, order_id)
        if not record:
            raise ValueError("Order not found")
        
        return {
            "order_id": record.id,
            "status": record.status,
            "commands": [],
            "constraint_violations": [],
        }
