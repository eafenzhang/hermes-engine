"""Conversation schemas / DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    id: str
    title: str
    metadata: dict = Field(default_factory=dict)
    message_count: int = 0
    created_at: float
    updated_at: float


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", min_length=1)
    metadata: dict = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    metadata: dict | None = None


class MessageItem(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: float


class MessageCreate(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(..., min_length=1)
    metadata: dict = Field(default_factory=dict)
