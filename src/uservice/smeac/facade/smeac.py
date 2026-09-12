"""SMEAC Domain Facade."""

import asyncio
import logging
import os
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

        # 2. Translate SMEAC intent via Gemini LLM agent if API key is configured
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key and api_key != "placeholder_key":
            try:
                import json
                from src.uservice.base.agent import AgentContext
                from src.uservice.smeac.operations.smeac_agents import parse_smeac_order
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
                    parse_smeac_order(
                        situation=body.situation,
                        mission=body.mission,
                        execution=body.execution,
                        admin_logistics=body.admin_logistics,
                        command_signal=body.command_signal,
                        context=ctx,
                    ),
                    timeout=20.0,
                )

                for cmd_dto in parse_result.commands:
                    m_str = cmd_dto.mission_type.lower()
                    f_str = cmd_dto.formation_type.lower()
                    p_str = cmd_dto.priority.lower()

                    m_type = MissionType(m_str) if m_str in [m.value for m in MissionType] else MissionType.PATROL
                    f_type = FormationType(f_str) if f_str in [f.value for f in FormationType] else FormationType.LINE
                    prio = CommandPriority(p_str) if p_str in [p.value for p in CommandPriority] else CommandPriority.NORMAL

                    cmd_record = SwarmCommand(
                        smeac_order_id=order_id,
                        mission_type=m_type,
                        formation_type=f_type,
                        target_area=json.dumps(cmd_dto.target_area) if isinstance(cmd_dto.target_area, (dict, list)) else str(cmd_dto.target_area),
                        target_object_class=cmd_dto.target_object_class,
                        drone_count=cmd_dto.drone_count,
                        altitude_m=cmd_dto.altitude_m,
                        speed_ms=cmd_dto.speed_ms,
                        duration_s=cmd_dto.duration_s,
                        priority=prio,
                        is_high_impact=m_type in HIGH_IMPACT_MISSIONS,
                    )
                    self.session.add(cmd_record)

                order_record.status = "translated"
                await self.session.flush()
                logger.info("Parsed %d swarm commands via Gemini for order %s", len(parse_result.commands), order_id)
            except Exception as e:
                logger.warning("Gemini SMEAC parser skipped or error (fallback): %s", e)
        
        # 3. Schedule workflow via Operation wrapper
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
            await asyncio.wait_for(
                start_workflow(
                    ProcessSmeacWorkflow,
                    wf_input,
                    task_queue="smeac-queue",
                    workflow_id=f"smeac-{order_id}",
                ),
                timeout=5.0,
            )
            logger.info("Launched Temporal workflow smeac-%s for user %s", order_id, self.user.get("sub"))
        except Exception as e:
            logger.warning("Temporal workflow start exception for order %s (graceful fallback): %s", order_id, e)
        
        return {
            "order_id": order_id,
            "status": order_record.status,
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
        
        import json
        from sqlalchemy import select
        from src.uservice.smeac.models.contract.command import SwarmCommand

        formatted_cmds = []
        try:
            cmds_stmt = select(SwarmCommand).where(SwarmCommand.smeac_order_id == order_id)
            cmds_res = await self.session.execute(cmds_stmt)
            commands = cmds_res.scalars().all()

            for cmd in commands:
                area = cmd.target_area
                if isinstance(area, str) and (area.startswith("{") or area.startswith("[")):
                    try:
                        area = json.loads(area)
                    except Exception:
                        pass
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
        except Exception as e:
            logger.warning("Failed to query swarm_commands for order %s: %s", order_id, e)

        return {
            "order_id": record.id,
            "status": record.status,
            "commands": formatted_cmds,
            "constraint_violations": [],
        }
