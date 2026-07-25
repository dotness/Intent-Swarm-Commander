"""Base Pydantic models for API contracts."""

from pydantic import BaseModel as PydanticBaseModel, ConfigDict

class BaseModel(PydanticBaseModel):
    """Base model for all API requests and responses.
    
    Provides strict configuration and ORM attribute mapping.
    """
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
    )
