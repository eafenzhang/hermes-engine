"""MCP schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class MCPServerCreate(BaseModel):
    name: str
    url: str
    headers: dict[str, str] = {}


class MCPToolCall(BaseModel):
    server: str
    tool: str
    arguments: dict = {}
