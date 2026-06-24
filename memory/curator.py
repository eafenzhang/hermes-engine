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

    Two curation strategies are available:

    * **Deterministic** (default, always runs) — archives stale, low-importance
      memories based on age/importance rules.
    * **LLM-assisted** (``run(use_llm=True)``) — on top of the deterministic
      pass, asks an LLM to cluster a batch of active memories into concise
      summaries and de-duplicated tags. Falls back to deterministic-only on
      any error (no provider configured, API failure, unparseable output).
    """

    # Cap on the number of memories handed to the LLM per consolidation batch.
    _LLM_BATCH_SIZE = 25

    def __init__(
        self,
        store: SQLiteStore,
        interval_messages: int = 10,
        enabled: bool = True,
        llm_provider: str = "anthropic",
        llm_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.store = store
        self.interval_messages = interval_messages
        self.enabled = enabled
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self._message_count = 0
        self._last_run_at: float | None = None

    def should_run(self) -> bool:
        if not self.enabled:
            return False
        return self._message_count >= self.interval_messages

    def record_message(self) -> None:
        self._message_count += 1

    async def run(self, use_llm: bool = False) -> dict[str, Any]:
        """Execute one curation pass.

        The deterministic archival phase always runs. When ``use_llm`` is
        true and a provider is available, an LLM-assisted consolidation phase
        follows; any failure there is logged and silently skipped so the
        deterministic result remains valid.
        """
        self._message_count = 0
        self._last_run_at = time.time()
        report: dict[str, Any] = {
            "ran_at": self._last_run_at,
            "archived": 0,
            "consolidated": 0,
            "tagged": 0,
            "use_llm": use_llm,
        }

        # ── Phase 1: deterministic archival (always runs) ────────────────
        archived, total = self._archive_stale_memories()
        report["archived"] = archived
        report["total_memories"] = total

        # ── Phase 2: LLM-assisted consolidation (optional) ───────────────
        if use_llm:
            try:
                consolidated, tagged = await self._consolidate_with_llm()
                report["consolidated"] = consolidated
                report["tagged"] = tagged
            except Exception as exc:
                # Any LLM failure degrades gracefully to deterministic-only.
                report["llm_error"] = str(exc)
                logger.warning("LLM consolidation skipped: %s", exc)

        logger.info(
            "Curator run complete — archived=%d consolidated=%d total=%d use_llm=%s",
            report["archived"], report["consolidated"], total, use_llm,
        )
        return report

    # ── Deterministic phase ──────────────────────────────────────────────

    def _archive_stale_memories(self) -> tuple[int, int]:
        """Archive old, low-importance memories. Returns (archived, total)."""
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
        return archived, total

    # ── LLM-assisted phase ───────────────────────────────────────────────

    def _build_consolidation_prompt(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build the message list asking the LLM to cluster & summarise memories."""
        catalogue = [
            {
                "id": m["id"],
                "content": m["content"],
                "tags": m.get("tags", []),
            }
            for m in memories
        ]
        instructions = (
            "You are a memory curator. Given a list of memories (each with an id, "
            "content, and tags), produce a consolidation plan.\n\n"
            "1. Group memories that are about the same topic into clusters.\n"
            "2. For each cluster, write a single concise summary sentence.\n"
            "3. Produce a de-duplicated, normalised tag list for the cluster "
            "(lowercase, no duplicates, max 5 tags).\n\n"
            "Respond with STRICT JSON only, no prose, in this shape:\n"
            '{"clusters": [{"summary": str, "tags": [str], "memory_ids": [str]}]}\n\n'
            f"Memories:\n{json.dumps(catalogue, ensure_ascii=False)}"
        )
        return [{"role": "user", "content": instructions}]

    def _parse_consolidation(self, raw: Any) -> list[dict[str, Any]]:
        """Extract the clusters list from the provider response.

        Tolerates either a pre-parsed dict or a JSON string (some providers
        return text content). Returns an empty list when nothing parses.
        """
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, list) and raw:
            # Anthropic-style content blocks — join text parts.
            text = " ".join(
                b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text"
            )
            data = self._extract_json(text)
        elif isinstance(raw, str):
            data = self._extract_json(raw)
        else:
            return []

        clusters = data.get("clusters", []) if isinstance(data, dict) else []
        return clusters if isinstance(clusters, list) else []

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Parse JSON from text, tolerating surrounding ``` fences or prose."""
        fenced = text
        if "```" in text:
            parts = text.split("```")
            # The fenced block is typically the middle element.
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    fenced = part
                    break
        try:
            result: dict[str, Any] = json.loads(fenced)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    async def _consolidate_with_llm(self) -> tuple[int, int]:
        """Run one LLM consolidation batch over active memories.

        Returns (memories_summarised, memories_retagged). Raises on any
        unrecoverable error so ``run`` can record it and degrade.
        """
        from provider.registry import registry

        provider = registry.get(self.llm_provider)
        if provider is None:
            raise RuntimeError(
                f"LLM provider '{self.llm_provider}' is not configured"
            )

        # Only consolidate active (non-archived) memories that lack a summary.
        active, _ = self.store.list_memories(limit=self._LLM_BATCH_SIZE, offset=0)
        candidates = [m for m in active if m.get("scope") != "archived" and not m.get("summary")]
        if not candidates:
            return 0, 0

        messages = self._build_consolidation_prompt(candidates)
        result = await provider.chat_completion(
            messages=messages,
            model=self.llm_model,
            temperature=0.2,
            max_tokens=1024,
        )

        clusters = self._parse_consolidation(result.get("content"))
        consolidated = 0
        tagged = 0
        for cluster in clusters:
            summary = cluster.get("summary")
            tags = cluster.get("tags") or []
            ids = cluster.get("memory_ids") or []
            if not isinstance(ids, list):
                continue
            for mem_id in ids:
                updates: dict[str, Any] = {}
                if isinstance(summary, str) and summary:
                    updates["summary"] = summary
                if isinstance(tags, list) and tags:
                    updates["tags"] = [str(t) for t in tags][:5]
                if updates:
                    updated = self.store.update_memory(str(mem_id), **updates)
                    if updated is not None:
                        if "summary" in updates:
                            consolidated += 1
                        if "tags" in updates:
                            tagged += 1

        return consolidated, tagged

    def get_state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_messages": self.interval_messages,
            "message_count": self._message_count,
            "last_run_at": self._last_run_at,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
        }
