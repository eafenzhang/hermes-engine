"""Conversation service — business logic decoupled from FastAPI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.store import SQLiteStore


class ConversationService:
    """High-level conversation operations."""

    def __init__(self, db_path: Path) -> None:
        self.store = SQLiteStore(db_path)

    def create(self, title: str = "New Conversation", metadata: dict | None = None) -> dict[str, Any]:
        return self.store.create_conversation(title, metadata)

    def get(self, conv_id: str) -> dict[str, Any] | None:
        return self.store.get_conversation(conv_id)

    def list(self, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.list_conversations(limit, offset)

    def add_message(self, conv_id: str, role: str, content: str, metadata: dict | None = None) -> dict[str, Any]:
        return self.store.add_message(conv_id, role, content, metadata)

    def get_messages(self, conv_id: str, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.get_messages(conv_id, limit, offset)

    def delete(self, conv_id: str) -> bool:
        return self.store.delete_conversation(conv_id)
