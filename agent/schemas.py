"""Agent schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class AgentTurnRequest(BaseModel):
    messages: list[dict]
    provider: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    tools: list[dict] | None = None


class AgentTurnResponse(BaseModel):
    success: bool = True
    id: str | None = None
    role: str = "assistant"
    content: str | list | None = None
    model: str | None = None
    usage: dict | None = None
