"""Webhook retry queue — exponential backoff for failed gateway deliveries."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _init_retry_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_retries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            payload TEXT NOT NULL,
            attempt INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 5,
            next_retry_at REAL NOT NULL,
            created_at REAL NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()


class RetryQueue:
    """SQLite-backed retry queue with exponential backoff."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        _init_retry_db(db_path)

    def enqueue(self, url: str, payload: str, max_attempts: int = 5) -> int:
        conn = sqlite3.connect(self._db_path)
        now = time.time()
        c = conn.execute(
            "INSERT INTO webhook_retries (url, payload, next_retry_at, created_at, max_attempts) VALUES (?, ?, ?, ?, ?)",
            (url, payload, now, now, max_attempts),
        )
        conn.commit()
        conn.close()
        return c.lastrowid or 0

    def status(self) -> list[dict]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM webhook_retries WHERE status='pending' ORDER BY next_retry_at ASC LIMIT 50"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    async def process(self) -> None:
        """Process pending retries with exponential backoff."""
        try:
            import httpx
        except ImportError:
            return

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM webhook_retries WHERE status='pending' AND next_retry_at <= ? LIMIT 10",
            (time.time(),),
        ).fetchall()

        for row in rows:
            r = dict(row)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(r["url"], content=r["payload"],
                                             headers={"Content-Type": "application/json"})
                    if resp.status_code < 500:
                        conn.execute("UPDATE webhook_retries SET status='delivered' WHERE id=?", (r["id"],))
                        conn.commit()
                    else:
                        raise ValueError(f"HTTP {resp.status_code}")
            except Exception:
                attempt = r["attempt"] + 1
                if attempt >= r["max_attempts"]:
                    conn.execute("UPDATE webhook_retries SET status='failed' WHERE id=?", (r["id"],))
                else:
                    delay = min(60 * 60, 2 ** attempt)  # max 1h
                    conn.execute(
                        "UPDATE webhook_retries SET attempt=?, next_retry_at=? WHERE id=?",
                        (attempt, time.time() + delay, r["id"]),
                    )
                conn.commit()

        conn.close()
