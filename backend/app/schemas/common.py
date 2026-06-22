"""
Shared/reusable Pydantic schemas — the standard API response envelope
used by every endpoint in HireFlow AI (matches the dict shape already
returned by app/main.py's health check and app/api/auth.py's _envelope()).
"""
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata attached to every API response."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "3.0.0"


class APIResponse(BaseModel, Generic[T]):
    """
    Standard envelope wrapping every HireFlow AI API response.

    success -> True if the request succeeded
    message -> human-readable summary
    data    -> the actual payload (typed per-endpoint via APIResponse[SomeSchema])
    error   -> error detail string, only populated when success is False
    meta    -> timestamp + version info
    """
    success: bool
    message: str
    data: Optional[T] = None
    error: Optional[str] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "Success") -> "APIResponse[T]":
        return cls(success=True, message=message, data=data, error=None)

    @classmethod
    def fail(cls, error: str, message: str = "Request failed") -> "APIResponse[T]":
        return cls(success=False, message=message, data=None, error=error)


class PaginationMeta(ResponseMeta):
    """Extended meta for paginated list endpoints."""
    total: int = 0
    page: int = 1
    page_size: int = 20


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope for list endpoints — data is always a list of T."""
    success: bool = True
    message: str = "Success"
    data: list[T] = Field(default_factory=list)
    error: Optional[str] = None
    meta: PaginationMeta = Field(default_factory=PaginationMeta)