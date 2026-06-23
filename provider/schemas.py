"""Provider schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class ProviderInfo(BaseModel):
    name: str
    type: str
    connected: bool


class ProviderListResponse(BaseModel):
    success: bool = True
    data: list[ProviderInfo]


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str | None = None
    provider: str = "anthropic"
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    tools: list[dict] | None = None


class ChatResponse(BaseModel):
    success: bool = True
    content: str | None = None
    model: str | None = None
    usage: dict | None = None
