"""HITL approval facade — domain service for managing approval gates."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.uservice.base.facade.base import DomainFacade
from src.uservice.base.errors import ResourceDoesNotExist
from sqlalchemy import select
from src.uservice.operation.facade import signal_workflow
from src.uservice.hitl.models.storage.decision import HitlDecision
import logging

logger = logging.getLogger(__name__)


class HitlFacade(DomainFacade):
    """Facade for managing HITL approval gates."""

    async def create_hitl_request(
        self,
        command_id: uuid.UUID,
        action_summary: str,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        """Create a new HITL approval request for a high-impact command."""
        decision_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        record = HitlDecision(
            id=decision_id,
            swarm_command_id=command_id,
            commander_id=self.user.get("sub", "commander-default"),
            decision="pending",
            action_summary=action_summary,
            timeout_seconds=timeout_seconds,
            status="pending",
        )
        self.session.add(record)
        await self.session.flush()

        logger.info(
            "HITL request %s created for command %s — timeout=%ds",
            decision_id, command_id, timeout_seconds,
        )
        return {
            "decision_id": str(decision_id),
            "command_id": str(command_id),
            "action_summary": action_summary,
            "timeout_seconds": timeout_seconds,
            "requested_at": now,
            "status": "pending",
        }

    async def submit_decision(
        self,
        decision_id: uuid.UUID,
        decision: str,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        """Record a commander's approval or rejection."""
        self.require_scope("hitl:decide")
        
        record = await self.session.get(HitlDecision, decision_id)
        if record is None:
            raise ResourceDoesNotExist(f"Decision {decision_id} not found")

        record.decision = decision
        record.rationale = rationale
        record.commander_id = self.user.get("sub", "commander-default")
        record.status = "decided"
        await self.session.flush()

        logger.info(
            "HITL decision %s: %s by %s", decision_id, decision, record.commander_id,
        )

        decision_data = {
            "decision_id": str(record.id),
            "decision": record.decision,
            "rationale": record.rationale,
            "status": record.status,
            "commander_id": record.commander_id,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }

        # Send Temporal signal if workflow_id is present
        if record.workflow_id:
            try:
                await signal_workflow(
                    workflow_id=record.workflow_id,
                    signal_name="hitl_decision",
                    signal_input=decision_data
                )
                logger.info("Sent HITL decision signal to workflow %s", record.workflow_id)
            except Exception as e:
                logger.error("Failed to signal workflow %s: %s", record.workflow_id, e)

        return decision_data

    async def get_pending_decisions(self, swarm_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        """Return all pending HITL decisions, optionally filtered by swarm."""
        self.require_scope("hitl:read")
        
        stmt = select(HitlDecision).where(HitlDecision.status == "pending")
        # Skipping swarm filter for MVP since swarm is indirectly related via command
        result = await self.session.execute(stmt)
        records = result.scalars().all()
        
        return [
            {
                "decision_id": str(d.id),
                "command_id": str(d.swarm_command_id),
                "action_summary": d.action_summary,
                "timeout_seconds": d.timeout_seconds,
                "status": d.status,
            }
            for d in records
        ]
