"""Data TTL cleaner — auto-delete expired memories and conversations."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class DataCleaner:
    """Background task that periodically prunes old data."""

    def __init__(self, db_path: str, ttl_days: int = 90, interval_hours: float = 24.0):
        self._db_path = db_path
        self._ttl_days = ttl_days
        self._interval = interval_hours * 3600
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("Data cleaner started (TTL=%d days, interval=%dh)", self._ttl_days, int(self._interval / 3600))
        while self._running:
            await self._clean()
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    async def _clean(self) -> None:
        import sqlite3
        cutoff = time.time() - self._ttl_days * 86400
        try:
            conn = sqlite3.connect(self._db_path)
            # Delete old conversations + cascade messages
            c1 = conn.execute("DELETE FROM conversations WHERE updated_at < ?", (cutoff,))
            convs_deleted = c1.rowcount
            # Delete old memories
            c2 = conn.execute("DELETE FROM memories WHERE updated_at < ?", (cutoff,))
            mems_deleted = c2.rowcount
            conn.commit()
            conn.close()
            if convs_deleted or mems_deleted:
                logger.info("Data cleaner: removed %d conversations, %d memories", convs_deleted, mems_deleted)
        except Exception:
            logger.debug("Data cleaner run failed", exc_info=True)
