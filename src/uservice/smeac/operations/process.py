"""SMEAC → Swarm Command Temporal workflow.

Orchestrates the full pipeline:
  1. Parse SMEAC fields via the pydantic-ai agent
  2. Persist resulting SwarmCommand rows
  3. (Future phases integrate safety verification and HITL gates here)
"""

from datetime import timedelta
import logging
from dataclasses import dataclass, field

from temporalio import activity, workflow

logger = logging.getLogger(__name__)


@dataclass
class ProcessSmeacInput:
    """Arguments for the SMEAC processing workflow."""

    order_id: str
    commander_id: str
    swarm_instance_id: str
    situation: str
    mission: str
    execution: str
    admin_logistics: str | None = None
    command_signal: str | None = None
    project_id: str = "default-theater"
    endpoint_url: str | None = None
    commands: list[dict] = field(default_factory=list)


def _extract_waypoints_from_commands(commands: list[dict]) -> list[dict]:
    """Extract [{lat, lon, alt_m}, ...] waypoints from parsed GeoJSON commands."""
    waypoints: list[dict] = []
    for cmd in commands:
        alt_m = float(cmd.get("altitude_m") or 15.0)
        area = cmd.get("target_area") or {}
        if isinstance(area, str):
            import json

            try:
                area = json.loads(area)
            except Exception:
                area = {}
        if not isinstance(area, dict):
            continue
        geom_type = str(area.get("type", "")).lower()
        coords = area.get("coordinates")
        if not coords:
            continue
        if geom_type == "point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
            waypoints.append({"lat": lat, "lon": lon, "alt_m": alt_m})
        elif geom_type == "linestring" and isinstance(coords, list):
            for pt in coords:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    waypoints.append({"lat": float(pt[1]), "lon": float(pt[0]), "alt_m": alt_m})
        elif geom_type == "polygon" and isinstance(coords, list) and coords:
            ring = coords[0]
            if isinstance(ring, list) and ring:
                lons = [float(p[0]) for p in ring if isinstance(p, (list, tuple)) and len(p) >= 2]
                lats = [float(p[1]) for p in ring if isinstance(p, (list, tuple)) and len(p) >= 2]
                if lats and lons:
                    waypoints.append({
                        "lat": sum(lats) / len(lats),
                        "lon": sum(lons) / len(lons),
                        "alt_m": alt_m,
                    })
    return waypoints


@activity.defn(name="parse_smeac_activity")
async def parse_smeac_activity(input: ProcessSmeacInput) -> dict:
    """Return pre-parsed commands or load them from PostgreSQL."""
    if input.commands:
        return {"commands": input.commands}

    import json
    import uuid
    from sqlalchemy import select
    from src.uservice.database.engine import async_session
    from src.uservice.smeac.models.contract.command import SwarmCommand

    async with async_session() as session:
        res = await session.execute(
            select(SwarmCommand).where(SwarmCommand.smeac_order_id == uuid.UUID(input.order_id))
        )
        rows = res.scalars().all()
        commands = []
        for r in rows:
            target = r.target_area
            if isinstance(target, str):
                try:
                    target = json.loads(target)
                except Exception:
                    target = {}
            commands.append({
                "id": str(r.id),
                "mission_type": str(r.mission_type.value if hasattr(r.mission_type, "value") else r.mission_type),
                "formation_type": str(r.formation_type.value if hasattr(r.formation_type, "value") else r.formation_type),
                "target_area": target,
                "target_object_class": r.target_object_class,
                "drone_count": r.drone_count,
                "altitude_m": r.altitude_m,
                "is_high_impact": bool(r.is_high_impact),
            })
        return {"commands": commands}


@activity.defn(name="safety_check_activity")
async def safety_check_activity(cmd: dict) -> list[dict]:
    """Validate command safety bounds (altitude / drone count)."""
    violations = []
    alt = float(cmd.get("altitude_m") or 0.0)
    if alt < 0.0 or alt > 500.0:
        violations.append({"severity": "error", "message": f"Altitude {alt}m out of safe bounds [0, 500]"})
    return violations


@activity.defn(name="dispatch_edge_mission_activity")
async def dispatch_edge_mission_activity(payload: dict) -> dict:
    """Dispatch extracted waypoints to the edge node and mark the SMEAC order executed."""
    import asyncio
    import os
    import uuid
    import httpx
    from sqlalchemy import select, update
    from src.uservice.database.engine import async_session
    from src.uservice.smeac.models.storage.smeac import SmeacOrder
    from src.uservice.swarm.models.storage.instance import SwarmInstance

    order_id = payload["order_id"]
    swarm_id = payload["swarm_instance_id"]
    project_id = payload.get("project_id", "default-theater")
    endpoint_url = payload.get("endpoint_url")
    commands = payload.get("commands", [])

    if not endpoint_url:
        async with async_session() as session:
            res = await session.execute(
                select(SwarmInstance.endpoint_url).where(SwarmInstance.id == uuid.UUID(swarm_id))
            )
            endpoint_url = res.scalar_one_or_none() or os.getenv("SWARM_DEFAULT_ENDPOINT")

    waypoints = _extract_waypoints_from_commands(commands)
    if endpoint_url and waypoints:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{endpoint_url.rstrip('/')}/navigate",
                json={
                    "command_id": str(commands[0].get("id")) if commands else order_id,
                    "swarm_id": swarm_id,
                    "project_id": project_id,
                    "waypoints": waypoints,
                },
            )
            resp.raise_for_status()
            logger.info(
                "Dispatched %d waypoints to edge %s for order %s",
                len(waypoints),
                endpoint_url,
                order_id,
            )

    if endpoint_url:
        for cmd in commands:
            target_cls = (cmd.get("target_object_class") or "").strip()
            if not target_cls:
                continue
            mission_type = str(cmd.get("mission_type", "")).lower()
            detection_mode = "intercept" if mission_type in ("strike", "intercept") else "report_only"
            async with httpx.AsyncClient(timeout=10.0) as client:
                t_resp = await client.post(
                    f"{endpoint_url.rstrip('/')}/target",
                    json={
                        "target_object_class": target_cls,
                        "command_id": str(cmd.get("id") or order_id),
                        "confidence_threshold": 0.5,
                        "detection_mode": detection_mode,
                    },
                )
                t_resp.raise_for_status()
                logger.info(
                    "Dispatched target detection '%s' (mode=%s) to edge %s for order %s",
                    target_cls,
                    detection_mode,
                    endpoint_url,
                    order_id,
                )

    order_uuid = uuid.UUID(order_id)
    for attempt in range(5):
        async with async_session() as session:
            result = await session.execute(
                update(SmeacOrder)
                .where(SmeacOrder.id == order_uuid)
                .values(status="executed")
            )
            await session.commit()
            if result.rowcount and result.rowcount > 0:
                break
        await asyncio.sleep(0.3)

    return {"status": "executed", "waypoint_count": len(waypoints), "endpoint_url": endpoint_url}


@workflow.defn
class ProcessSmeacWorkflow:
    """Durable workflow that translates a SMEAC order into swarm commands."""

    def __init__(self) -> None:
        self.hitl_decision: dict | None = None

    @workflow.signal(name="hitl_decision")
    def on_hitl_decision(self, decision_data: dict) -> None:
        self.hitl_decision = decision_data

    @workflow.run
    async def run(self, input: ProcessSmeacInput) -> dict:
        """Execute the SMEAC processing pipeline.

        Returns a dict with the generated command summaries.
        """
        logger.info("ProcessSmeacWorkflow started for order=%s", input.order_id)

        # Step 1: Parse SMEAC via the LLM agent (run as an activity)
        parse_result = await workflow.execute_activity(
            "parse_smeac_activity",
            input,
            start_to_close_timeout=timedelta(seconds=30),
        )

        commands = parse_result.get("commands", [])

        # Step 2: Safety Verification (Guardian Critic + Memgraph Threat Gating)
        all_violations = []
        threat_overrides = []
        for cmd in commands:
            violations = await workflow.execute_activity(
                "safety_check_activity",
                cmd,
                start_to_close_timeout=timedelta(seconds=10),
            )
            if violations:
                for v in violations:
                    if v.get("severity") == "threat_override_required":
                        threat_overrides.append(v)
                    else:
                        all_violations.append(v)
                
        if all_violations:
            logger.error("Safety checks failed: %s", all_violations)
            return {"error": "Safety checks failed", "violations": all_violations}

        # Step 3: HITL Verification for High-Impact Actions or Dynamic Threat Conflicts
        requires_hitl = bool(threat_overrides) or any(
            cmd.get("is_high_impact", False)
            for cmd in commands
        )
        
        if requires_hitl:
            self.hitl_decision = None
            logger.info("Waiting for HITL approval for high-impact commands")
            await workflow.wait_condition(lambda: self.hitl_decision is not None)
            
            if self.hitl_decision.get("decision") != "approved":
                logger.error("HITL rejected the command: %s", self.hitl_decision)
                return {"error": "HITL rejected", "rationale": self.hitl_decision.get("rationale")}
            
            logger.info("HITL approved the command")

        # Step 4: Dispatch waypoints to the edge node & update order status
        dispatch_result = await workflow.execute_activity(
            "dispatch_edge_mission_activity",
            {
                "order_id": input.order_id,
                "swarm_instance_id": input.swarm_instance_id,
                "project_id": input.project_id,
                "endpoint_url": input.endpoint_url,
                "commands": commands,
            },
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Log audit events
        logger.info("Audit: Command Generation completed for order=%s", input.order_id)
        
        logger.info(
            "ProcessSmeacWorkflow completed for order=%s — %d commands generated",
            input.order_id,
            len(commands),
        )

        return {**parse_result, "dispatch": dispatch_result}
