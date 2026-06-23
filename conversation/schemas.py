"""Conversation schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class Conversation(BaseModel):
    id: str
    title: str
    metadata: dict = {}
    message_count: int = 0
    created_at: float
    updated_at: float


class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    metadata: dict = {}


class ConversationUpdate(BaseModel):
    title: str | None = None
    metadata: dict | None = None


class MessageItem(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict = {}
    created_at: float


class MessageCreate(BaseModel):
    role: str
    content: str
    metadata: dict = {}
