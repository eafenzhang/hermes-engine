"""Memory schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class MemoryItem(BaseModel):
    id: str
    content: str
    summary: str | None = None
    source: str = "user"
    scope: str = "general"
    importance: int = 1
    tags: list[str] = []
    created_at: float
    updated_at: float
    access_count: int = 0
    last_accessed_at: float | None = None


class MemoryCreate(BaseModel):
    content: str
    summary: str | None = None
    source: str = "user"
    scope: str = "general"
    importance: int = 1
    tags: list[str] = []


class MemoryUpdate(BaseModel):
    content: str | None = None
    summary: str | None = None
    source: str | None = None
    scope: str | None = None
    importance: int | None = None
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
