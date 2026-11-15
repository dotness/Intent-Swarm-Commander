"""Guardian Critic Temporal Activity."""

from temporalio import activity
from src.uservice.swarm.operations.swarm_agents import verify_command

@activity.defn(name="safety_check_activity")
async def safety_check_activity(command: dict) -> list[dict]:
    """Execute Guardian Critic safety verification for a proposed command."""
    # Ensure altitude and duration are passed correctly if they exist
    altitude = command.get("altitude_m") or command.get("altitude")
    duration = command.get("duration_s") or command.get("duration")
    
    # Try converting to appropriate types in case they are strings
    if altitude is not None:
        altitude = float(altitude)
    if duration is not None:
        duration = int(duration)
        
    violations = verify_command(
        altitude_m=altitude,
        duration_s=duration,
        target_area=command.get("target_area", ""),
        drone_count=command.get("drone_count"),
    )
    
    # Return violations as dictionaries for Temporal serialization
    results = [
        {
            "rule_id": v.rule_id,
            "rule_description": v.rule_description,
            "severity": v.severity,
            "actual_value": v.actual_value,
            "allowed_range": v.allowed_range,
            "remediation": v.remediation,
        }
        for v in violations
    ]

    from src.uservice.threat.facade.threat import ThreatFacade

    threat_facade = ThreatFacade(
        session=None,
        user={"sub": "temporal-safety-activity", "scope": "threat:read"},
    )
    eval_res = await threat_facade.evaluate_route_threats(
        project_id=str(command.get("project_id", "default-theater")),
        target_area=command.get("target_area"),
        altitude_m=altitude,
    )
    for conflict in eval_res.conflicts:
        results.append(
            {
                "rule_id": f"THREAT:{conflict.threat_id}",
                "rule_description": (
                    f"Route intersects {conflict.threat_type} zone '{conflict.name}' "
                    f"(severity={conflict.severity}, source={conflict.source})"
                ),
                "severity": "threat_override_required",
                "threat_id": conflict.threat_id,
                "remediation": "Submit HITL override with explicit operational justification.",
            }
        )
    return results
