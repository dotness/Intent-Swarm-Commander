"""HITL approval facade — domain service for managing approval gates."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.uservice.base.facade.base import DomainFacade
from src.uservice.base.errors import ResourceDoesNotExist

logger = logging.getLogger(__name__)

# In-memory pending decisions (replaced by DB + Temporal signals in integration)
_pending_decisions: dict[str, dict] = {}


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

        record = {
            "decision_id": decision_id,
            "command_id": command_id,
            "action_summary": action_summary,
            "timeout_seconds": timeout_seconds,
            "requested_at": now,
            "status": "pending",
            "decision": None,
            "rationale": None,
        }
        _pending_decisions[str(decision_id)] = record

        logger.info(
            "HITL request %s created for command %s — timeout=%ds",
            decision_id, command_id, timeout_seconds,
        )
        return record

    async def submit_decision(
        self,
        decision_id: uuid.UUID,
        decision: str,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        """Record a commander's approval or rejection."""
        # await self.permissions.require_access("hitl:decide")
        
        record = _pending_decisions.get(str(decision_id))
        if record is None:
            raise ResourceDoesNotExist(f"Decision {decision_id} not found")

        record["decision"] = decision
        record["rationale"] = rationale
        record["commander_id"] = self.user.get("sub", "commander-default")
        record["status"] = "decided"
        record["decided_at"] = datetime.now(timezone.utc)

        logger.info(
            "HITL decision %s: %s by %s", decision_id, decision, record["commander_id"],
        )
        return record

    async def get_pending_decisions(self, swarm_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        """Return all pending HITL decisions, optionally filtered by swarm."""
        # await self.permissions.require_access("hitl:read")
        
        return [
            d for d in _pending_decisions.values()
            if d["status"] == "pending"
        ]
