"""Base agent abstraction for pydantic-ai multi-agent pipelines.

All ISC agents (SMEAC Parser, Guardian Critic, Executor) inherit from
this base to share common configuration, logging, and audit hooks.
"""

import logging
import os
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
    model: str | None = None,
    system_prompt: str = "",
    result_type: type | None = None,
    deps_type: type | None = None,
) -> Agent:
    """Factory that creates a pydantic-ai Agent with ISC defaults.

    Defaults to Google Gemini (e.g. gemini-1.5-flash) using GEMINI_API_KEY
    or GOOGLE_API_KEY. Can be configured via the LLM_MODEL environment variable.

    Parameters
    ----------
    name:
        Human-readable agent name used in logs and audit events.
    model:
        LLM backend identifier (e.g. ``"gemini-1.5-flash"`` or ``"gemini-2.0-flash"``).
    system_prompt:
        Base system prompt for the agent.
    result_type:
        Pydantic model the agent must return.
    deps_type:
        Type of the dependency context object.
    """
    if model is None:
        model = os.getenv("LLM_MODEL", "gemini-1.5-flash")

    # Bridge GEMINI_API_KEY and GOOGLE_API_KEY for pydantic-ai / Google GenAI SDK
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        if not os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = gemini_key
        if not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = gemini_key
    elif "gemini" in model.lower() or "google" in model.lower():
        # Set placeholder to prevent initialization crash on module import if key not yet set
        logger.warning(
            "GEMINI_API_KEY / GOOGLE_API_KEY not configured. Initializing agent '%s' with placeholder.",
            name,
        )
        os.environ["GOOGLE_API_KEY"] = "placeholder_key"

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

