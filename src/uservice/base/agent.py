"""Base agent abstraction for pydantic-ai multi-agent pipelines.

All ISC agents (SMEAC Parser, Guardian Critic, Executor) inherit from
this base to share common configuration, logging, and audit hooks.
"""

import logging
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Shared runtime context injected into every agent run."""

    commander_id: str
    swarm_instance_id: str | None = None
    correlation_id: str | None = None


def create_agent(
    name: str,
    *,
    model: str = "openai:gpt-4o",
    system_prompt: str = "",
    result_type: type | None = None,
    deps_type: type | None = None,
) -> Agent:
    """Factory that creates a pydantic-ai Agent with ISC defaults.

    Parameters
    ----------
    name:
        Human-readable agent name used in logs and audit events.
    model:
        LLM backend identifier (e.g. ``"openai:gpt-4o"``).
    system_prompt:
        Base system prompt for the agent.
    result_type:
        Pydantic model the agent must return.
    deps_type:
        Type of the dependency context object.
    """
    logger.info("Creating agent '%s' with model=%s", name, model)

    kwargs: dict[str, Any] = {
        "model": model,
        "system_prompt": system_prompt,
    }
    if result_type is not None:
        kwargs["result_type"] = result_type
    if deps_type is not None:
        kwargs["deps_type"] = deps_type

    return Agent(**kwargs)
