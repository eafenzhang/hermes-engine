"""Shared SQLite connection / retry / helpers used by Memory and Conversation stores.

This module extracts the common boilerplate so that ``memory/store.py`` and
``conversation/store.py`` only need to define their domain-specific tables and
queries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BUSY_RETRIES = 3
_BUSY_DELAY_S = 0.05


class SQLiteBase:
    """Base class for domain-specific SQLite stores.

    Provides thread-local connection management, WAL mode, busy-timeout,
    exponential-backoff retry on SQLITE_BUSY, and a ``_row_to_dict`` helper.

    Each unique ``db_path`` gets at most one connection, tracked via
    ``_connection_paths`` for cleanup at shutdown.
    """

    _connection_paths: set[str] = set()

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()
        SQLiteBase._connection_paths.add(str(db_path))

    def _get_conn(self) -> "sqlite3.Connection":  # type: ignore[name-defined]
        """Return a thread-local SQLite connection (WAL + foreign keys on)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=3000")
            self._local.conn = conn
        return self._local.conn  # type: ignore[no-any-return]

    def _execute_retry(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> "sqlite3.Cursor":  # type: ignore[name-defined]
        """Execute *sql* with up to 3 retries on SQLITE_BUSY."""
        for attempt in range(_BUSY_RETRIES):
            try:
                conn = self._get_conn()
                return conn.execute(sql, params or [])
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc) and attempt < _BUSY_RETRIES - 1:
                    time.sleep(_BUSY_DELAY_S * (attempt + 1))
                    continue
                raise
        raise RuntimeError("_execute_retry: unreachable")

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict, decoding JSON fields."""
        d = dict(row)
        for key in ("tags", "metadata"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        d.pop("rowid", None)
        return d

    @classmethod
    def close_all(cls) -> list[str]:
        """Close connections for all tracked db_paths."""
        closed: list[str] = []
        for path in list(cls._connection_paths):
            try:
                conn = sqlite3.connect(path)
                conn.close()
                closed.append(path)
            except Exception:
                logger.debug("Could not close %s", path)
        cls._connection_paths.clear()
        if closed:
            logger.info("Closed %d SQLite connection path(s): %s", len(closed), closed)
        return closed
