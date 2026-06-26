"""Memory schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    id: str
    content: str
    summary: str | None = None
    source: str = "user"
    scope: str = "general"
    importance: int = Field(default=1, ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=10)
    created_at: float
    updated_at: float
    access_count: int = 0
    last_accessed_at: float | None = None


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    summary: str | None = None
    source: str = "user"
    scope: str = "general"
    importance: int = Field(default=1, ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=10)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    source: str | None = None
    scope: str | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = None


class MemorySearchResult(BaseModel):
    success: bool = True
    data: list[MemoryItem]
    total: int
    query: str


class CuratorState(BaseModel):
    enabled: bool
    interval_messages: int
    message_count: int
    last_run_at: float | None = None
