"""Lightweight database migration system for SQLite stores.

Each store registers its migrations as (version, sql) tuples.  On startup
the system creates a ``_schema_version`` table (if missing), applies any
pending migrations in version order, and records the result.

Usage:
    from shared.migrations import MigrationRunner

    migrations = [
        (1, "CREATE TABLE IF NOT EXISTS ..."),
        (2, "ALTER TABLE ... ADD COLUMN ..."),
    ]
    MigrationRunner(db_path).apply("my-store", migrations)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from sqlite3 import Connection

logger = logging.getLogger(__name__)

_V_TABLE = "_schema_version"


def _ensure_version_table(conn: Connection) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_V_TABLE} (
            store_name TEXT PRIMARY KEY,
            version   INTEGER NOT NULL DEFAULT 0,
            applied_at REAL NOT NULL
        )
    """)


def _current_version(conn: Connection, store_name: str) -> int:
    row = conn.execute(
        f"SELECT version FROM {_V_TABLE} WHERE store_name = ?", (store_name,)
    ).fetchone()
    return row[0] if row else 0


def _set_version(conn: Connection, store_name: str, version: int) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO {_V_TABLE} (store_name, version, applied_at) VALUES (?, ?, unixepoch())",
        (store_name, version),
    )


class MigrationRunner:
    """Applies pending migrations for a named store inside a SQLite database."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)

    def apply(self, store_name: str, migrations: list[tuple[int, str]]) -> int:
        """Apply all *migrations* that have not yet been applied.

        Returns the number of migrations applied.
        """
        if not migrations:
            return 0

        sorted_migrations = sorted(migrations, key=lambda m: m[0])
        conn = None
        applied = 0
        try:
            conn = sqlite3.connect(self._db_path)
            _ensure_version_table(conn)
            current = _current_version(conn, store_name)

            for version, sql in sorted_migrations:
                if version <= current:
                    continue
                logger.info(
                    "Migrating %s: applying v%d (was v%d)", store_name, version, current,
                )
                conn.executescript(sql)
                _set_version(conn, store_name, version)
                conn.commit()
                current = version
                applied += 1
        finally:
            if conn:
                conn.close()

        if applied:
            logger.info("Migrated %s: %d migration(s) applied", store_name, applied)
        return applied
