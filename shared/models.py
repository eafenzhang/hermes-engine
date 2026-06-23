"""Shared data models — unified API response format."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Generic successful API response envelope."""

    success: bool = True
    data: T | None = None
    message: str = ""


class ErrorResponse(BaseModel):
    """Error API response envelope."""

    success: bool = False
    error: str
    code: str = "INTERNAL_ERROR"
    details: dict[str, Any] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    success: bool = True
    data: list[T]
    total: int
    page: int = 1
    page_size: int = 20


class HealthResponse(BaseModel):
    """Health-check payload."""

    status: str = "ok"
    version: str = "0.1.0"
    providers: int = 0
    skills: int = 0
    conversations: int = 0
    memories: int = 0
