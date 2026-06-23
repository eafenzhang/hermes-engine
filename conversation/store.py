"""Conversation SQLite storage — independent from memory/store.py.

Owns the `conversations` and `messages` tables in the shared SQLite database.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Number of retries on SQLITE_BUSY
_BUSY_RETRIES = 3
_BUSY_DELAY_S = 0.05


class ConversationStore:
    """SQLite storage for conversations and messages."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    # ── Connection management ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.execute("PRAGMA busy_timeout=3000")
        return self._local.conn

    def _execute_retry(self, sql: str, params: list[Any] = None) -> sqlite3.Cursor:
        """Execute with retry on SQLITE_BUSY."""
        for attempt in range(_BUSY_RETRIES):
            try:
                conn = self._get_conn()
                if params:
                    return conn.execute(sql, params)
                return conn.execute(sql)
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc) and attempt < _BUSY_RETRIES - 1:
                    time.sleep(_BUSY_DELAY_S * (attempt + 1))
                    continue
                raise

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

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(self, title: str = "New Conversation", metadata: dict | None = None) -> dict[str, Any]:
        conn = self._get_conn()
        now = time.time()
        conv_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO conversations (id, title, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (conv_id, title, json.dumps(metadata or {}), now, now),
        )
        conn.commit()
        return self.get(conv_id)

    def get(self, conv_id: str) -> dict[str, Any] | None:
        row = self._execute_retry(
            "SELECT rowid, * FROM conversations WHERE id = ?", [conv_id]
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = self._execute_retry(
            "SELECT rowid, * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
        count_row = self._execute_retry(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()
        return [self._row_to_dict(r) for r in rows], (count_row[0] if count_row else 0)

    def update(self, conv_id: str, title: str | None = None, metadata: dict | None = None) -> dict[str, Any] | None:
        conn = self._get_conn()
        now = time.time()
        existing = self.get(conv_id)
        if not existing:
            return None
        if title is not None:
            conn.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, now, conv_id))
        if metadata is not None:
            conn.execute("UPDATE conversations SET metadata = ?, updated_at = ? WHERE id = ?",
                          (json.dumps(metadata), now, conv_id))
        if title is None and metadata is None:
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        conn.commit()
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
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, conv_id, role, content, json.dumps(metadata or {}), now),
        )
        conn.execute("UPDATE conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
                      (now, conv_id))
        conn.commit()
        return {"id": msg_id, "conversation_id": conv_id, "role": role, "content": content, "created_at": now}

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

    # ── Helpers ──────────────────────────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        d.pop("rowid", None)
        return d
