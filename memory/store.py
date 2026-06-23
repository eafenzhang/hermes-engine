"""SQLite FTS5 storage for memory persistence.

Copyright (c) NousResearch — curator logic adapted from Hermes Agent under Apache 2.0.
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


class SQLiteStore(SQLiteBase):
    """SQLite + FTS5 store for memories."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._init_db()
        self._run_migrations()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create tables on first use."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                summary TEXT,
                source TEXT DEFAULT 'user',
                scope TEXT DEFAULT 'general',
                importance INTEGER DEFAULT 1,
                tags TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                last_accessed_at REAL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, summary, tags,
                content=memories, content_rowid=rowid
            );

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, summary, tags)
                VALUES (new.rowid, new.content, new.summary, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags)
                VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags)
                VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
                INSERT INTO memories_fts(rowid, content, summary, tags)
                VALUES (new.rowid, new.content, new.summary, new.tags);
            END;
        """)
        conn.commit()

    def _run_migrations(self) -> None:
        """Apply any pending schema migrations for the memories store."""
        migrations: list[tuple[int, str]] = [
            # v1: initial schema (idempotent via IF NOT EXISTS above)
            (1, ""),
        ]
        MigrationRunner(self.db_path).apply("memories", migrations)

    # ── Memory CRUD ──────────────────────────────────────────────────────

    def add_memory(
        self,
        content: str,
        summary: str | None = None,
        source: str = "user",
        scope: str = "general",
        importance: int = 1,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        conn = self._get_conn()
        now = time.time()
        mem_id = str(uuid.uuid4())
        tags_json = json.dumps(tags or [])
        conn.execute(
            """INSERT INTO memories (id, content, summary, source, scope, importance,
               tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mem_id, content, summary, source, scope, importance, tags_json, now, now),
        )
        conn.commit()
        result = self.get_memory(mem_id)
        assert result is not None, f"add_memory: just-inserted {mem_id} not found"
        return result

    def get_memory(self, mem_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute("SELECT rowid, * FROM memories WHERE id = ?", (mem_id,)).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                      (time.time(), mem_id))
        conn.commit()
        return self._row_to_dict(row)

    def search_memories(
        self,
        query: str,
        scope: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conn = self._get_conn()
        where = ""
        params: list[Any] = [query]
        if scope:
            where = " AND m.scope = ?"
            params.append(scope)

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM memories_fts f JOIN memories m ON f.rowid = m.rowid"
            f" WHERE memories_fts MATCH ?{where}",
            params,
        ).fetchone()
        total = count_row[0] if count_row else 0

        rows = conn.execute(
            f"SELECT m.rowid, m.* FROM memories_fts f JOIN memories m ON f.rowid = m.rowid"
            f" WHERE memories_fts MATCH ?{where}"
            f" ORDER BY m.importance DESC, rank LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        return [self._row_to_dict(r) for r in rows], total

    def list_memories(
        self,
        scope: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conn = self._get_conn()
        if scope:
            rows = conn.execute(
                "SELECT rowid, * FROM memories WHERE scope = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (scope, limit, offset),
            ).fetchall()
            count_row = conn.execute("SELECT COUNT(*) FROM memories WHERE scope = ?", (scope,)).fetchone()
        else:
            rows = conn.execute(
                "SELECT rowid, * FROM memories ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            count_row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        total = count_row[0] if count_row else 0
        return [self._row_to_dict(r) for r in rows], total

    def update_memory(self, mem_id: str, **updates: Any) -> dict[str, Any] | None:
        conn = self._get_conn()
        allowed = {"content", "summary", "source", "scope", "importance", "tags"}
        to_set = {k: v for k, v in updates.items() if k in allowed}
        if not to_set:
            return self.get_memory(mem_id)

        to_set["updated_at"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in to_set)
        conn.execute(f"UPDATE memories SET {set_clause} WHERE id = ?",
                      [*to_set.values(), mem_id])
        conn.commit()
        return self.get_memory(mem_id)

    def delete_memory(self, mem_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        conn.commit()
        return cursor.rowcount > 0

    def count(self, scope: str | None = None) -> int:
        conn = self._get_conn()
        if scope:
            row = conn.execute("SELECT COUNT(*) FROM memories WHERE scope = ?", (scope,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0] if row else 0
