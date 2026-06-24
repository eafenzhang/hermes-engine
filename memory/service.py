"""Memory service — business logic layer decoupled from FastAPI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.store import SQLiteStore
from memory.curator import Curator


class MemoryService:
    """High-level memory operations — wraps store + curator."""

    def __init__(
        self,
        db_path: Path,
        curator_enabled: bool = True,
        curator_interval_messages: int = 10,
        curator_provider: str = "anthropic",
        curator_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.store = SQLiteStore(db_path)
        self.curator = Curator(
            store=self.store,
            enabled=curator_enabled,
            interval_messages=curator_interval_messages,
            llm_provider=curator_provider,
            llm_model=curator_model,
        )

    # ── Memory operations ────────────────────────────────────────────────

    def create_memory(self, content: str, **kwargs: Any) -> dict[str, Any]:
        return self.store.add_memory(content, **kwargs)

    def get_memory(self, mem_id: str) -> dict[str, Any] | None:
        return self.store.get_memory(mem_id)

    def search(self, query: str, scope: str | None = None, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.search_memories(query, scope, limit, offset)

    def list_memories(self, scope: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.list_memories(scope, limit, offset)

    def update_memory(self, mem_id: str, **updates: Any) -> dict[str, Any] | None:
        return self.store.update_memory(mem_id, **updates)

    def delete_memory(self, mem_id: str) -> bool:
        return self.store.delete_memory(mem_id)

    def count(self, scope: str | None = None) -> int:
        return self.store.count(scope)

    # ── Curator ──────────────────────────────────────────────────────────

    async def run_curator(self, use_llm: bool = False) -> dict[str, Any]:
        return await self.curator.run(use_llm=use_llm)

    def get_curator_state(self) -> dict[str, Any]:
        return self.curator.get_state()
