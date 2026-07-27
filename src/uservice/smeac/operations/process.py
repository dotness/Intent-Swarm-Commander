"""SMEAC → Swarm Command Temporal workflow.

Orchestrates the full pipeline:
  1. Parse SMEAC fields via the pydantic-ai agent
  2. Persist resulting SwarmCommand rows
  3. (Future phases integrate safety verification and HITL gates here)
"""

import json
import logging
import uuid
from dataclasses import dataclass

from temporalio import workflow

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
            start_to_close_timeout=workflow.timedelta(seconds=30),
        )

        commands = parse_result.get("commands", [])

        # Step 2: Safety Verification (Guardian Critic)
        all_violations = []
        for cmd in commands:
            violations = await workflow.execute_activity(
                "safety_check_activity",
                cmd,
                start_to_close_timeout=workflow.timedelta(seconds=10),
            )
            if violations:
                all_violations.extend(violations)
                
        if all_violations:
            logger.error("Safety checks failed: %s", all_violations)
            return {"error": "Safety checks failed", "violations": all_violations}

        # Step 3: HITL Verification for High-Impact Actions
        requires_hitl = any(cmd.get("is_high_impact", False) for cmd in commands)
        
        if requires_hitl:
            self.hitl_decision = None
            logger.info("Waiting for HITL approval for high-impact commands")
            await workflow.wait_condition(lambda: self.hitl_decision is not None)
            
            if self.hitl_decision.get("decision") != "approved":
                logger.error("HITL rejected the command: %s", self.hitl_decision)
                return {"error": "HITL rejected", "rationale": self.hitl_decision.get("rationale")}
            
            logger.info("HITL approved the command")

        # Log audit events
        logger.info("Audit: Command Generation completed for order=%s", input.order_id)
        
        logger.info(
            "ProcessSmeacWorkflow completed for order=%s — %d commands generated",
            input.order_id,
            len(commands),
        )

        return parse_result
