"""Pydantic models for the OpenAI-compatible /v1/chat/completions endpoint.

Enables desktop agents (CodePilot, LobeChat, etc.) to use Hermes Engine
as a drop-in backend.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Request ──────────────────────────────────────────────────────────────


class FunctionCall(BaseModel):
    name: str
    arguments: str  # JSON-encoded string


class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    role: str  # system / user / assistant / tool
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # for role="tool"
    name: str | None = None


class FunctionDef(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = {}


class ToolDef(BaseModel):
    type: str = "function"
    function: FunctionDef


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[ToolDef] | None = None


# ── Response (non-streaming) ────────────────────────────────────────────


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ResponseMessage(BaseModel):
    role: str = "assistant"
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: str | None = None
    logprobs: Any = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: UsageInfo


# ── Response (streaming chunk) ──────────────────────────────────────────


class Delta(BaseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: Delta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]
