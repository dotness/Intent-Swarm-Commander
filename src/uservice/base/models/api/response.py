"""API generic response envelopes."""

from typing import Generic, TypeVar, Optional, Any
from .base import BaseModel

T = TypeVar("T")

class Response(BaseModel, Generic[T]):
    """Generic response wrapper for single items."""
    data: T
    meta: Optional[dict[str, Any]] = None

    @classmethod
    def create(cls, data: T, meta: Optional[dict[str, Any]] = None) -> "Response[T]":
        return cls(data=data, meta=meta)

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic response wrapper for lists of items."""
    data: list[T]
    total: int
    page: int
    size: int

    @classmethod
    def create(cls, data: list[T], total: int, page: int, size: int) -> "PaginatedResponse[T]":
        return cls(data=data, total=total, page=page, size=size)
