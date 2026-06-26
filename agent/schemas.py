"""Agent schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTurnRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1)
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    stream: bool = False
    tools: list[dict] | None = None
    conversation_id: str | None = None  # for multi-turn session persistence


class AgentTurnResponse(BaseModel):
    success: bool = True
    id: str | None = None
    role: str = "assistant"
    content: str | list | None = None
    model: str | None = None
    usage: dict | None = None
