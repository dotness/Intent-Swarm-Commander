"""Base classes for Domain Facades."""

from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.security.jwt import verify_scope

class DomainFacade:
    """Base class for all Domain Facades.
    
    Encapsulates business logic, data access, and operations.
    Requires an AsyncSession and a User context to instantiate.
    """
    
    def __init__(self, session: AsyncSession, user: dict[str, Any]):
        self.session = session
        self.user = user

    @classmethod
    async def create(cls, session: AsyncSession, user: dict[str, Any]) -> "DomainFacade":
        """Factory method for creating a facade instance."""
        return cls(session=session, user=user)

    def require_scope(self, scope: str) -> None:
        """Validate that the user context has the required JWT scope."""
        if not verify_scope(self.user, scope):
            raise PermissionError(f"Missing required scope: {scope}")
