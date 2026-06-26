"""Conversation SQLite storage — independent from memory/store.py.

Owns the `conversations` and `messages` tables in the shared SQLite database.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from shared.sqlite_base import SQLiteBase
from shared.migrations import MigrationRunner

logger = logging.getLogger(__name__)


class ConversationStore(SQLiteBase):
    """SQLite storage for conversations and messages."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._init_db()
        self._run_migrations()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New Conversation',
                metadata TEXT DEFAULT '{}',
                message_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
        """)
        conn.commit()

    def _run_migrations(self) -> None:
        """Apply any pending schema migrations for the conversations store."""
        migrations: list[tuple[int, str]] = [
            # v1: initial schema (idempotent via IF NOT EXISTS above)
            (1, ""),
        ]
        MigrationRunner(self.db_path).apply("conversations", migrations)

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(self, title: str = "New Conversation", metadata: dict | None = None, conv_id: str | None = None) -> dict[str, Any]:
        conn = self._get_conn()
        now = time.time()
        if conv_id is None:
            conv_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO conversations (id, title, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (conv_id, title, json.dumps(metadata or {}), now, now),
        )
        conn.commit()
        result = self.get(conv_id)
        assert result is not None, f"create: just-inserted {conv_id} not found"
        return result

    def get(self, conv_id: str) -> dict[str, Any] | None:
        row = self._execute_retry(
            "SELECT rowid, * FROM conversations WHERE id = ?", [conv_id]
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_conversations(self, limit: int = 50, offset: int = 0) -> tuple["list[dict[str, Any]]", int]:
        rows = self._execute_retry(
            "SELECT rowid, * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
        count_row = self._execute_retry(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()
        return [self._row_to_dict(r) for r in rows], (count_row[0] if count_row else 0)

    def update(
        self,
        conv_id: str,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any] | None:
        """Update a conversation. Uses a single UPDATE statement to avoid TOCTOU races."""
        conn = self._get_conn()
        now = time.time()
        set_parts: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]

        if title is not None:
            set_parts.append("title = ?")
            params.append(title)
        if metadata is not None:
            set_parts.append("metadata = ?")
            params.append(json.dumps(metadata))

        params.append(conv_id)
        set_clause = ", ".join(set_parts)
        cursor = conn.execute(
            f"UPDATE conversations SET {set_clause} WHERE id = ?",
            params,
        )
        conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get(conv_id)

    def delete(self, conv_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()
        return cursor.rowcount > 0

    # ── Messages ─────────────────────────────────────────────────────────

    def add_message(self, conv_id: str, role: str, content: str, metadata: dict | None = None) -> dict[str, Any]:
        conn = self._get_conn()
        now = time.time()
        msg_id = str(uuid.uuid4())
        md_json = json.dumps(metadata or {})
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, conv_id, role, content[:65536], md_json, now),  # 64 KiB max content
        )
        conn.execute("UPDATE conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
                      (now, conv_id))
        conn.commit()

        # Return full record consistent with create() pattern
        row = conn.execute("SELECT rowid, * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        if row:
            return self._row_to_dict(row)
        return {"id": msg_id, "conversation_id": conv_id, "role": role, "content": content[:65536],
                "metadata": metadata or {}, "created_at": now}

    def get_messages(self, conv_id: str, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        conv = self.get(conv_id)
        if not conv:
            return [], 0
        rows = self._execute_retry(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
            [conv_id, limit, offset],
        ).fetchall()
        count_row = self._execute_retry(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", [conv_id]
        ).fetchone()
        return [self._row_to_dict(r) for r in rows], (count_row[0] if count_row else 0)
