"""Curator — background memory curation for Hermes Engine.

Adapted from Hermes Agent's curator.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from memory.store import SQLiteStore

logger = logging.getLogger(__name__)


class Curator:
    """Periodic memory curator — reviews memories and consolidates them.

    The curator runs after every N messages, reviewing recent memories to:
      - Tag and categorize new information
      - Consolidate related memories
      - Prune low-importance stale memories
      - Generate summaries for memory clusters
    """

    def __init__(
        self,
        store: SQLiteStore,
        interval_messages: int = 10,
        enabled: bool = True,
    ) -> None:
        self.store = store
        self.interval_messages = interval_messages
        self.enabled = enabled
        self._message_count = 0
        self._last_run_at: float | None = None

    def should_run(self) -> bool:
        if not self.enabled:
            return False
        return self._message_count >= self.interval_messages

    def record_message(self) -> None:
        self._message_count += 1

    async def run(self) -> dict[str, Any]:
        """Execute one curation pass.

        In v1 this is a deterministic review; future versions may use an
        LLM call to perform semantic consolidation.
        """
        self._message_count = 0
        self._last_run_at = time.time()
        report: dict[str, Any] = {
            "ran_at": self._last_run_at,
            "archived": 0,
            "consolidated": 0,
            "tagged": 0,
        }

        # Phase 1: Archive very old, low-importance memories
        # (soft-delete by setting scope to 'archived')
        now = time.time()
        archived = 0
        total = 0
        offset = 0
        page_size = 200
        while True:
            batch, _ = self.store.list_memories(limit=page_size, offset=offset)
            if not batch:
                break
            total += len(batch)
            for mem in batch:
                age_days = (now - mem["updated_at"]) / 86400
                if age_days > 90 and mem.get("importance", 1) <= 2 and mem.get("scope") != "archived":
                    self.store.update_memory(mem["id"], scope="archived")
                    archived += 1
                elif age_days > 30 and mem.get("importance", 1) <= 1:
                    self.store.update_memory(mem["id"], scope="archived")
                    archived += 1
            offset += page_size

        report["archived"] = archived
        report["total_memories"] = total

        logger.info(
            "Curator run complete — archived=%d total=%d",
            archived, total,
        )
        return report

    def get_state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_messages": self.interval_messages,
            "message_count": self._message_count,
            "last_run_at": self._last_run_at,
        }
