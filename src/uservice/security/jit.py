"""JIT (Just-In-Time) ephemeral credential issuance and lifecycle management.

Provides time-bound agent identities to prevent credential sprawl (FR-010).
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from src.uservice.security.jwt import JWT_ALGORITHM, JWT_ISSUER, JWT_SECRET

logger = logging.getLogger(__name__)

# Default lifetime for JIT credentials
DEFAULT_LIFETIME_SECONDS = 300  # 5 minutes


async def issue_jit_credential(
    agent_name: str,
    scopes: list[str],
    lifetime_seconds: int = DEFAULT_LIFETIME_SECONDS,
) -> dict:
    """Issue a time-bound JWT credential for an agent.

    Parameters
    ----------
    agent_name:
        Human-readable name of the agent requesting credentials.
    scopes:
        List of scope strings the agent is granted.
    lifetime_seconds:
        How long the credential remains valid.

    Returns
    -------
    Dict with ``token``, ``expires_at``, and ``agent_id``.
    """
    agent_id = f"agent-{agent_name}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=lifetime_seconds)

    payload = {
        "sub": agent_id,
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "scope": " ".join(scopes),
        "jit": True,  # marker for JIT-issued credentials
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    logger.info(
        "JIT credential issued: agent=%s scopes=%s expires=%s",
        agent_id, scopes, expires_at.isoformat(),
    )

    return {
        "token": token,
        "agent_id": agent_id,
        "expires_at": expires_at.isoformat(),
        "lifetime_seconds": lifetime_seconds,
    }
