"""SMEAC Domain Facade."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.facade.analytics import AnalyticsFacade
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.facade.base import DomainFacade
from src.uservice.hitl.facade.hitl import HitlFacade
import src.uservice.operation.facade as operation_facade
from src.uservice.smeac.models.contract.schemas import (
    SmeacDraftData,
    SmeacDraftRequest,
    SmeacOrderCreateRequest,
)
from src.uservice.smeac.models.storage.smeac import SmeacOrder
from src.uservice.smeac.operations.copilot import SmeacCopilot
from src.uservice.smeac.operations.process import ProcessSmeacInput, ProcessSmeacWorkflow
from src.uservice.threat.facade.threat import ThreatFacade, get_default_graph_client
from src.uservice.threat.operations.graph_client import MemgraphClient

logger = logging.getLogger(__name__)


class SmeacFacade(DomainFacade):
    """Facade for SMEAC intent ingestion and processing."""

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
    ) -> "SmeacFacade":
        return cls(session=session, user=user, graph_client=graph_client)

    async def submit_smeac_order(self, swarm_id: uuid.UUID, body: SmeacOrderCreateRequest) -> dict[str, Any]:
        """Submit a SMEAC order and launch the Temporal workflow."""
        # 1. Enforce RBAC
        self.require_scope("smeac:create")
        
        order_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        project_id = getattr(body, "project_id", None) or "default-theater"

        parsed_fields = {
            "situation": "parsed" if body.situation else "missing",
            "mission": "parsed" if body.mission else "missing",
            "execution": "parsed" if body.execution else "missing",
            "admin_logistics": "parsed" if body.admin_logistics else "not_provided",
            "command_signal": "parsed" if body.command_signal else "not_provided",
        }

        draft_source_refs_json = (
            json.dumps(body.draft_source_refs) if body.draft_source_refs is not None else None
        )
        order_record = SmeacOrder(
            id=order_id,
            project_id=project_id,
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=swarm_id,
            situation=body.situation,
            mission=body.mission,
            execution=body.execution,
            admin_logistics=body.admin_logistics,
            command_signal=body.command_signal,
            draft_source_refs=draft_source_refs_json,
        )
        self.session.add(order_record)
        await self.session.flush()

        # 2. Translate SMEAC intent via Gemini LLM agent (no regex fallback)
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required to parse SMEAC orders")

        formatted_cmds: list[dict[str, Any]] = []
        reasoning_out: str | None = None

        from src.uservice.base.agent import AgentContext
        from src.uservice.smeac.operations import smeac_agents
        from src.uservice.smeac.models.contract.command import (
            SwarmCommand,
            MissionType,
            FormationType,
            CommandPriority,
            HIGH_IMPACT_MISSIONS,
        )

        ctx = AgentContext(
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=str(swarm_id),
            correlation_id=str(order_id),
        )
        parse_result = await asyncio.wait_for(
            smeac_agents.parse_smeac_order(
                situation=body.situation,
                mission=body.mission,
                execution=body.execution,
                admin_logistics=body.admin_logistics,
                command_signal=body.command_signal,
                context=ctx,
            ),
            timeout=20.0,
        )

        reasoning_out = parse_result.reasoning
        for cmd_dto in parse_result.commands:
            m_str = cmd_dto.mission_type.lower()
            f_str = cmd_dto.formation_type.lower()
            p_str = cmd_dto.priority.lower()

            m_type = MissionType(m_str) if m_str in [m.value for m in MissionType] else MissionType.PATROL
            f_type = FormationType(f_str) if f_str in [f.value for f in FormationType] else FormationType.LINE
            prio = CommandPriority(p_str) if p_str in [p.value for p in CommandPriority] else CommandPriority.NORMAL

            target_geo = cmd_dto.target_area if isinstance(cmd_dto.target_area, dict) else {"raw": cmd_dto.target_area}

            cmd_record = SwarmCommand(
                smeac_order_id=order_id,
                mission_type=m_type,
                formation_type=f_type,
                target_area=json.dumps(target_geo),
                target_object_class=cmd_dto.target_object_class,
                drone_count=cmd_dto.drone_count,
                altitude_m=cmd_dto.altitude_m,
                speed_ms=cmd_dto.speed_ms,
                duration_s=cmd_dto.duration_s,
                priority=prio,
                is_high_impact=m_type in HIGH_IMPACT_MISSIONS,
            )
            self.session.add(cmd_record)
            await self.session.flush()

            formatted_cmds.append({
                "id": cmd_record.id,
                "mission_type": m_type.value,
                "formation_type": f_type.value,
                "target_area": target_geo,
                "target_object_class": cmd_dto.target_object_class,
                "drone_count": cmd_dto.drone_count,
                "altitude_m": cmd_dto.altitude_m,
                "is_high_impact": m_type in HIGH_IMPACT_MISSIONS,
                "verification_status": "verified",
            })

        if not formatted_cmds:
            raise RuntimeError(f"Gemini SMEAC parser returned zero commands for order {order_id}")

        order_record.status = "translated"
        await self.session.flush()
        logger.info("Parsed %d swarm commands via Gemini for order %s", len(parse_result.commands), order_id)

        # 3. Spatial-temporal Threat Gating (Memgraph dynamic threats)
        threat_facade = ThreatFacade(
            session=self.session,
            user=self.user,
            graph_client=self.graph_client,
        )
        all_conflicts: list[dict[str, Any]] = []
        seen_threat_ids: set[str] = set()

        for cmd_dict in formatted_cmds:
            eval_res = await threat_facade.evaluate_route_threats(
                project_id=project_id,
                target_area=cmd_dict.get("target_area"),
                altitude_m=cmd_dict.get("altitude_m"),
            )
            if eval_res.conflicts:
                cmd_dict["verification_status"] = "threat_conflict_hitl"
                for c in eval_res.conflicts:
                    c_dict = c.model_dump()
                    if c.threat_id not in seen_threat_ids:
                        seen_threat_ids.add(c.threat_id)
                        all_conflicts.append(c_dict)

        pending_hitl_id: uuid.UUID | None = None
        if all_conflicts:
            zone_names = ", ".join(c["name"] for c in all_conflicts[:3])
            hitl_facade = HitlFacade(
                session=self.session,
                user=self.user,
                graph_client=self.graph_client,
            )
            hitl_res = await hitl_facade.create_hitl_request(
                command_id=formatted_cmds[0]["id"],
                action_summary=f"Route intersects active threat zone(s): {zone_names}",
                timeout_seconds=600,
                project_id=project_id,
                workflow_id=f"smeac-{order_id}",
                is_threat_override=True,
                threat_zone_ids=[c["threat_id"] for c in all_conflicts],
            )
            pending_hitl_id = uuid.UUID(str(hitl_res["decision_id"]))
            order_record.status = "pending_hitl"

        await self.session.flush()

        # 4. Schedule workflow via Operation wrapper (no graceful bypass)
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
        await asyncio.wait_for(
            operation_facade.start_workflow(
                ProcessSmeacWorkflow,
                wf_input,
                task_queue=os.getenv("ISC_TASK_QUEUE", "isc-smeac-queue"),
                workflow_id=f"smeac-{order_id}",
            ),
            timeout=5.0,
        )
        logger.info("Launched Temporal workflow smeac-%s for user %s", order_id, self.user.get("sub"))

        return {
            "order_id": order_id,
            "project_id": project_id,
            "status": order_record.status,
            "swarm_instance_id": swarm_id,
            "parsed_fields": parsed_fields,
            "created_at": now,
            "commands": formatted_cmds,
            "reasoning": reasoning_out,
            "threat_conflicts": all_conflicts,
            "pending_hitl_decision_id": pending_hitl_id,
            "draft_source_refs": body.draft_source_refs,
        }

    async def get_order_status(self, swarm_id: uuid.UUID, order_id: uuid.UUID) -> dict[str, Any]:
        """Get the status of a submitted SMEAC order."""
        # 1. Enforce RBAC
        self.require_scope("smeac:read")
        
        # 2. Fetch from DB
        record = await self.session.get(SmeacOrder, order_id)
        if not record:
            raise ResourceDoesNotExist(f"Order {order_id} not found")
        
        from src.uservice.smeac.models.contract.command import SwarmCommand

        formatted_cmds = []
        command_ids: list[uuid.UUID] = []
        cmds_stmt = select(SwarmCommand).where(SwarmCommand.smeac_order_id == order_id)
        cmds_res = await self.session.execute(cmds_stmt)
        commands = cmds_res.scalars().all()

        for cmd in commands:
            command_ids.append(cmd.id)
            area = cmd.target_area
            if isinstance(area, str) and (area.startswith("{") or area.startswith("[")):
                area = json.loads(area)
            formatted_cmds.append({
                "id": cmd.id,
                "mission_type": cmd.mission_type.value if hasattr(cmd.mission_type, "value") else str(cmd.mission_type),
                "formation_type": cmd.formation_type.value if hasattr(cmd.formation_type, "value") else str(cmd.formation_type),
                "target_area": area if isinstance(area, dict) else {"raw": area},
                "target_object_class": cmd.target_object_class,
                "drone_count": cmd.drone_count,
                "altitude_m": cmd.altitude_m,
                "is_high_impact": cmd.is_high_impact,
                "verification_status": "verified",
            })

        pending_hitl_id: uuid.UUID | None = None
        threat_conflicts: list[dict[str, Any]] = []
        if command_ids:
            hitl_facade = HitlFacade(
                session=self.session,
                user=self.user,
                graph_client=self.graph_client,
            )
            pending_meta = await hitl_facade.get_pending_for_commands(command_ids)
            if pending_meta is not None:
                pending_hitl_id = pending_meta["decision_id"]
                threat_conflicts = pending_meta["threat_conflicts"]

        draft_source_refs: list[str] | None = None
        if getattr(record, "draft_source_refs", None):
            decoded = json.loads(record.draft_source_refs)
            if isinstance(decoded, list):
                draft_source_refs = [str(item) for item in decoded]

        return {
            "order_id": record.id,
            "project_id": record.project_id,
            "status": record.status,
            "commands": formatted_cmds,
            "constraint_violations": [],
            "threat_conflicts": threat_conflicts,
            "pending_hitl_decision_id": pending_hitl_id,
            "draft_source_refs": draft_source_refs,
        }

    async def generate_smeac_draft(
        self,
        body: SmeacDraftRequest,
        minio_store: Any = None,
    ) -> tuple[SmeacDraftData, dict[str, Any]]:
        """Read-only RAG drafting for commander review (never persists or starts Temporal)."""
        self.require_scope("smeac:create")

        read_user = {
            **self.user,
            "scope": f"{self.user.get('scope', '')} threat:read analytics:read".strip(),
        }
        threats_data = None
        targets_data = None
        aar_summary = None

        if body.include_threat_context:
            t_facade = ThreatFacade(
                session=self.session,
                user=read_user,
                graph_client=self.graph_client,
            )
            threats_data = await t_facade.list_threats(project_id=body.project_id)
            targets_data = await t_facade.list_targets(project_id=body.project_id)

        if body.include_aar_context:
            a_facade = AnalyticsFacade(
                session=self.session,
                user=read_user,
                minio_store=minio_store,
                graph_client=self.graph_client,
            )
            aar_summary = await a_facade.run_aar(project_id=body.project_id, query_type="summary")

        copilot = SmeacCopilot()
        return await copilot.generate_draft(
            body,
            threats_data=threats_data,
            targets_data=targets_data,
            aar_summary=aar_summary,
        )
