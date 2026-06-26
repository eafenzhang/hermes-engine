"""Conversation service — business logic decoupled from FastAPI.

Uses its own ConversationStore instead of depending on memory/store.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conversation.store import ConversationStore


class ConversationService:
    """High-level conversation operations."""

    def __init__(self, db_path: Path) -> None:
        self.store = ConversationStore(db_path)

    def create(self, title: str = "New Conversation", metadata: dict | None = None, conv_id: str | None = None) -> dict[str, Any]:
        return self.store.create(title, metadata, conv_id)

    def get(self, conv_id: str) -> dict[str, Any] | None:
        return self.store.get(conv_id)

    def update(self, conv_id: str, title: str | None = None, metadata: dict | None = None) -> dict[str, Any] | None:
        return self.store.update(conv_id, title, metadata)

    def list_conversations(self, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.list_conversations(limit, offset)

    def add_message(self, conv_id: str, role: str, content: str, metadata: dict | None = None) -> dict[str, Any]:
        return self.store.add_message(conv_id, role, content, metadata)

    def get_messages(self, conv_id: str, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.get_messages(conv_id, limit, offset)

    def delete(self, conv_id: str) -> bool:
        return self.store.delete(conv_id)
