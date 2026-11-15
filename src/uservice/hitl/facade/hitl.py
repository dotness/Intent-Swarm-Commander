"""HITL approval facade — domain service for managing approval gates and threat overrides."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.facade.base import DomainFacade
from src.uservice.hitl.models.storage.decision import HitlDecision
from src.uservice.operation.facade import signal_workflow
from src.uservice.threat.facade.threat import ThreatFacade, get_default_graph_client
from src.uservice.threat.operations.graph_client import MemgraphClient

logger = logging.getLogger(__name__)


class HitlFacade(DomainFacade):
    """Facade for managing HITL approval gates."""

    def __init__(
        self,
        session: AsyncSession,
        user: dict[str, Any],
        graph_client: MemgraphClient | None = None,
    ) -> None:
        super().__init__(session=session, user=user)
        self.graph_client = graph_client or get_default_graph_client()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        user: dict[str, Any],
        graph_client: MemgraphClient | None = None,
    ) -> "HitlFacade":
        return cls(session=session, user=user, graph_client=graph_client)

    async def create_hitl_request(
        self,
        command_id: uuid.UUID,
        action_summary: str,
        timeout_seconds: int = 120,
        project_id: str = "default-theater",
        workflow_id: str | None = None,
        is_threat_override: bool = False,
        threat_zone_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new HITL approval request for a high-impact or threat-conflicting action."""
        decision_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        record = HitlDecision(
            id=decision_id,
            project_id=project_id,
            swarm_command_id=command_id,
            commander_id=self.user.get("sub") or "unknown",
            decision="pending",
            action_summary=action_summary,
            timeout_seconds=timeout_seconds,
            status="pending",
            workflow_id=workflow_id,
            is_threat_override=is_threat_override,
            threat_zone_ids=json.dumps(threat_zone_ids) if threat_zone_ids else None,
        )
        self.session.add(record)
        await self.session.flush()

        logger.info(
            "HITL request %s created for command %s — timeout=%ds, threat_override=%s",
            decision_id,
            command_id,
            timeout_seconds,
            is_threat_override,
        )
        return {
            "decision_id": str(decision_id),
            "command_id": str(command_id),
            "action_summary": action_summary,
            "timeout_seconds": timeout_seconds,
            "requested_at": now,
            "status": "pending",
            "is_threat_override": is_threat_override,
        }

    async def submit_decision(
        self,
        decision_id: uuid.UUID,
        decision: str,
        rationale: str | None = None,
        override_justification: str | None = None,
    ) -> dict[str, Any]:
        """Record a commander's approval or rejection, enforcing override rationale."""
        self.require_scope("hitl:decide")
        
        record = await self.session.get(HitlDecision, decision_id)
        if record is None:
            raise ResourceDoesNotExist(f"Decision {decision_id} not found")

        effective_justification = (override_justification or "").strip() or (rationale or "").strip()
        normalized_decision = decision.strip().lower()
        if record.is_threat_override and normalized_decision == "approved" and not effective_justification:
            raise ValueError(
                "Commander override justification is required to approve a route intersecting an active ThreatZone."
            )

        record.decision = decision
        record.rationale = rationale if (rationale and rationale.strip()) else effective_justification or rationale
        record.override_justification = effective_justification or None
        record.commander_id = self.user.get("sub") or "unknown"
        record.status = "decided"
        await self.session.flush()

        logger.info(
            "HITL decision %s: %s by %s (threat_override=%s)",
            decision_id,
            decision,
            record.commander_id,
            record.is_threat_override,
        )

        decided_at = datetime.now(timezone.utc).isoformat()
        decision_data = {
            "decision_id": str(record.id),
            "decision": record.decision,
            "rationale": record.rationale,
            "status": record.status,
            "commander_id": record.commander_id,
            "decided_at": decided_at,
            "is_threat_override": bool(record.is_threat_override),
            "override_justification": record.override_justification,
        }

        if record.is_threat_override and normalized_decision == "approved" and record.threat_zone_ids:
            threat_ids = json.loads(record.threat_zone_ids)
            if isinstance(threat_ids, list) and threat_ids:
                threat_facade = ThreatFacade(
                    session=self.session,
                    user=self.user,
                    graph_client=self.graph_client,
                )
                await threat_facade.record_threat_override(
                    project_id=record.project_id or "default-theater",
                    command_id=str(record.swarm_command_id),
                    threat_ids=[str(t) for t in threat_ids],
                    hitl_decision_id=str(record.id),
                    override_rationale=effective_justification,
                    overridden=True,
                )

        # Send Temporal signal if workflow_id is present
        if record.workflow_id:
            await signal_workflow(
                workflow_id=record.workflow_id,
                signal_name="hitl_decision",
                arg=decision_data,
            )
            logger.info("Sent HITL decision signal to workflow %s", record.workflow_id)

        return decision_data

    async def get_pending_decisions(self, swarm_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        """Return all pending HITL decisions enriched with threat override details."""
        self.require_scope("hitl:read")
        
        stmt = select(HitlDecision).where(HitlDecision.status == "pending")
        result = await self.session.execute(stmt)
        records = result.scalars().all()
        
        items: list[dict[str, Any]] = []
        for d in records:
            conflicts: list[dict[str, Any]] = []
            if d.threat_zone_ids:
                raw_ids = json.loads(d.threat_zone_ids)
                if isinstance(raw_ids, list):
                    conflicts = [{"threat_id": str(tid)} for tid in raw_ids]
            items.append(
                {
                    "decision_id": str(d.id),
                    "command_id": str(d.swarm_command_id),
                    "action_summary": d.action_summary,
                    "timeout_seconds": d.timeout_seconds,
                    "status": d.status,
                    "is_threat_override": bool(d.is_threat_override),
                    "requires_override_justification": bool(d.is_threat_override),
                    "threat_conflicts": conflicts,
                }
            )
        return items

    async def get_pending_for_commands(self, command_ids: list[uuid.UUID]) -> dict[str, Any] | None:
        """Return pending HITL decision metadata matching any of the supplied command IDs."""
        if not command_ids:
            return None

        stmt = select(HitlDecision).where(
            HitlDecision.swarm_command_id.in_(command_ids),
            HitlDecision.status == "pending",
        )
        result = await self.session.execute(stmt)
        hitl_row = result.scalars().first()
        if hitl_row is None:
            return None

        threat_conflicts: list[dict[str, Any]] = []
        if hitl_row.threat_zone_ids:
            zone_ids = json.loads(hitl_row.threat_zone_ids)
            if isinstance(zone_ids, list):
                threat_conflicts = [{"threat_id": str(tid)} for tid in zone_ids]

        return {
            "decision_id": hitl_row.id,
            "threat_conflicts": threat_conflicts,
        }
