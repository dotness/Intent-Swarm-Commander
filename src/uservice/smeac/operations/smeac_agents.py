"""Pydantic-AI agents for SMEAC → Swarm Command translation.

Pipeline: SMEAC text → SmeacParserAgent → list[SwarmCommandDTO]
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.uservice.base.agent import AgentContext, create_agent

logger = logging.getLogger(__name__)


# ── Agent output schemas ──────────────────────────────────────────────────

class SwarmCommandDTO(BaseModel):
    """Structured output from the SMEAC parser agent."""

    mission_type: str = Field(description="One of: recon, patrol, strike, transport, escort, abort")
    formation_type: str = Field(description="One of: line, wedge, diamond, spread, stack")
    target_area: dict[str, Any] = Field(description="GeoJSON object for the target area")
    target_object_class: str | None = Field(
        default=None, description="Object class to identify via YOLO-E (e.g. 'vehicle')"
    )
    drone_count: int = Field(ge=1, description="Number of drones to assign")
    altitude_m: float | None = Field(default=None, ge=0, description="Operational altitude in meters")
    speed_ms: float | None = Field(default=None, ge=0, description="Operational speed in m/s")
    duration_s: int | None = Field(default=None, ge=0, description="Estimated mission duration in seconds")
    priority: str = Field(default="normal", description="One of: critical, high, normal, low")


class SmeacParseResult(BaseModel):
    """Complete result from parsing a SMEAC order."""

    commands: list[SwarmCommandDTO] = Field(
        min_length=1,
        description="One or more swarm commands derived from the SMEAC order",
    )
    reasoning: str = Field(description="Brief explanation of how the SMEAC was decomposed")


# ── Agent definitions ─────────────────────────────────────────────────────

SMEAC_SYSTEM_PROMPT = """\
You are a military SMEAC Order parser for an autonomous drone swarm system.

Your task is to translate a structured SMEAC order (Situation, Mission,
Execution, Admin/Logistics, Command/Signal) into one or more concrete
Swarm Commands.

Rules:
- Each command MUST specify mission_type, formation_type, target_area (GeoJSON),
  drone_count, and priority.
- If the Execution field mentions a specific formation, use it. Otherwise infer
  the best formation for the mission type.
- If the mission is "strike" or "abort", flag it as high-impact.
- Extract altitude, speed, and duration when mentioned explicitly.
- If a target object class is mentioned (e.g., "find vehicles"), set
  target_object_class accordingly.
- Provide brief reasoning for your decomposition.
"""

smeac_parser_agent = create_agent(
    name="SmeacParser",
    system_prompt=SMEAC_SYSTEM_PROMPT,
    result_type=SmeacParseResult,
)


async def parse_smeac_order(
    situation: str,
    mission: str,
    execution: str,
    admin_logistics: str | None,
    command_signal: str | None,
    context: AgentContext,
) -> SmeacParseResult:
    """Run the SMEAC parser agent and return structured commands.

    Parameters
    ----------
    situation, mission, execution, admin_logistics, command_signal:
        The five SMEAC fields from the commander's order.
    context:
        Runtime context with commander identity and correlation ID.

    Returns
    -------
    SmeacParseResult with one or more SwarmCommandDTO objects.
    """
    prompt = (
        f"Parse the following SMEAC order into Swarm Commands.\n\n"
        f"**Situation**: {situation}\n"
        f"**Mission**: {mission}\n"
        f"**Execution**: {execution}\n"
    )
    if admin_logistics:
        prompt += f"**Admin/Logistics**: {admin_logistics}\n"
    if command_signal:
        prompt += f"**Command/Signal**: {command_signal}\n"

    logger.info(
        "Running SmeacParser for commander=%s correlation=%s",
        context.commander_id,
        context.correlation_id,
    )

    result = await smeac_parser_agent.run(prompt)
    logger.info("SmeacParser produced %d commands", len(result.data.commands))
    return result.data
