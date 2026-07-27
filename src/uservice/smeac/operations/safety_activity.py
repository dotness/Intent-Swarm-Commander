"""Guardian Critic Temporal Activity."""

from temporalio import activity
from src.uservice.swarm.operations.swarm_agents import verify_command, Violation

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
    return [
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
