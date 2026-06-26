"""MCP schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)


class MCPToolCall(BaseModel):
    server: str = Field(..., min_length=1)
    tool: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)
