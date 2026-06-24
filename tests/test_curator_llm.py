"""LLM-assisted curator consolidation tests.

Uses a mock provider registered into the provider registry so no real API
key or network call is required. Covers the consolidation happy path, the
graceful degradation when no provider is available, and JSON-parsing
robustness.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory.curator import Curator
from memory.store import SQLiteStore
from provider.base import ProviderBase
from provider.registry import registry


class MockProvider(ProviderBase):
    """Minimal provider returning a canned consolidation response."""

    name = "mock"

    def __init__(self, response: Any) -> None:
        super().__init__(api_key="mock-key-for-testing")
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append({"messages": messages, "model": model})
        return {"content": self._response}

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        yield ""  # not used in curator tests

    def validate_key(self) -> bool:
        return True


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    return SQLiteStore(tmp_path / "curator.db")


@pytest.fixture
def curator(store: SQLiteStore) -> Curator:
    return Curator(store=store, llm_provider="mock")


def _seed(store: SQLiteStore, n: int = 3) -> list[str]:
    """Insert n memories about overlapping topics; return their ids."""
    ids = []
    for i in range(n):
        mem = store.add_memory(
            content=f"Note about Python testing with pytest case {i}",
            tags=["python", "test"],
        )
        ids.append(mem["id"])
    return ids


# ── Happy path: LLM consolidates memories ───────────────────────────────


@pytest.mark.asyncio
async def test_llm_consolidation_writes_summaries_and_tags(curator, store):
    """A registered mock provider consolidates memories into summaries+tags."""
    ids = _seed(store, 3)
    clusters = {
        "clusters": [
            {
                "summary": "Notes on Python testing with pytest",
                "tags": ["python", "testing", "pytest"],
                "memory_ids": ids,
            }
        ]
    }
    mock = MockProvider(response=clusters)
    registry.register(mock)

    report = await curator.run(use_llm=True)

    assert report["use_llm"] is True
    assert report["consolidated"] == 3
    assert report["tagged"] == 3
    # The memories should now carry the consolidated summary + tags.
    for mid in ids:
        mem = store.get_memory(mid)
        assert mem["summary"] == "Notes on Python testing with pytest"
        assert "pytest" in mem["tags"]


@pytest.mark.asyncio
async def test_llm_consolidation_handles_text_content_blocks(curator, store):
    """Anthropic-style content-block responses are parsed correctly."""
    ids = _seed(store, 2)
    clusters = {
        "clusters": [
            {
                "summary": "Consolidated note",
                "tags": ["topic"],
                "memory_ids": ids,
            }
        ]
    }
    mock = MockProvider(
        response=[{"type": "text", "text": json.dumps(clusters)}]
    )
    registry.register(mock)

    report = await curator.run(use_llm=True)
    assert report["consolidated"] == 2


@pytest.mark.asyncio
async def test_llm_consolidation_handles_fenced_json(curator, store):
    """JSON wrapped in ```fences``` is still parsed."""
    ids = _seed(store, 1)
    payload = (
        "Here is the plan:\n```json\n"
        + json.dumps({"clusters": [{"summary": "S", "tags": ["t"], "memory_ids": ids}]})
        + "\n```"
    )
    mock = MockProvider(response=[{"type": "text", "text": payload}])
    registry.register(mock)

    report = await curator.run(use_llm=True)
    assert report["consolidated"] == 1


# ── Graceful degradation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_degrades_when_no_provider(curator, store):
    """Without a configured provider, LLM phase is skipped with an error note."""
    _seed(store, 2)
    # Ensure 'mock' is not registered.
    registry.remove("mock")

    report = await curator.run(use_llm=True)

    # Deterministic archival still ran; LLM consolidation recorded its failure.
    assert report["archived"] >= 0
    assert report["consolidated"] == 0
    assert "llm_error" in report
    assert "not configured" in report["llm_error"]


@pytest.mark.asyncio
async def test_llm_degrades_when_provider_raises(curator, store):
    """A failing provider call degrades to deterministic-only."""
    _seed(store, 2)

    class _BoomProvider(MockProvider):
        async def chat_completion(
            self,
            messages: list[dict[str, Any]],
            model: str,
            temperature: float = 0.7,
            max_tokens: int = 4096,
            tools: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            raise RuntimeError("API exploded")

    registry.register(_BoomProvider(response=None))
    try:
        report = await curator.run(use_llm=True)
        assert report["consolidated"] == 0
        assert "llm_error" in report
        assert "API exploded" in report["llm_error"]
    finally:
        registry.remove("mock")


@pytest.mark.asyncio
async def test_llm_phase_skipped_without_candidates(curator, store):
    """When there are no active, unsummarised memories, the LLM phase is a no-op."""
    mock = MockProvider(response={"clusters": []})
    registry.register(mock)

    report = await curator.run(use_llm=True)
    assert report["consolidated"] == 0
    assert report["tagged"] == 0
    # Provider was never actually called for consolidation candidates.
    assert mock.calls == []


# ── Deterministic path unchanged ────────────────────────────────────────


@pytest.mark.asyncio
async def test_deterministic_run_unchanged_without_llm(curator, store):
    """use_llm=False behaves exactly like the original v1 curator."""
    _seed(store, 3)
    report = await curator.run(use_llm=False)

    assert report["use_llm"] is False
    assert "llm_error" not in report
    assert report["total_memories"] == 3
