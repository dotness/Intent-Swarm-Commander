"""JWT decoding and validation for OAuth 2.1 tokens."""

import logging
import os
from typing import Any

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# Configuration — in production these come from the IdP's JWKS endpoint
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "isc-idp")


class TokenValidationError(Exception):
    """Raised when a JWT cannot be validated."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Returns the token claims if valid, otherwise raises TokenValidationError.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError as e:
        logger.warning("JWT validation failed: %s", e)
        raise TokenValidationError(f"Invalid token: {e}") from e

    # Validate issuer
    if payload.get("iss") != JWT_ISSUER:
        raise TokenValidationError(f"Invalid issuer: {payload.get('iss')}")

    return payload


def extract_scopes(payload: dict[str, Any]) -> set[str]:
    """Extract the set of granted scopes from a decoded JWT payload."""
    scope_str = payload.get("scope", "")
    if isinstance(scope_str, str):
        return set(scope_str.split()) if scope_str else set()
    return set(scope_str)


def verify_scope(payload: dict[str, Any], required_scope: str) -> bool:
    """Check whether the token grants the required scope."""
    granted = extract_scopes(payload)
    return required_scope in granted
