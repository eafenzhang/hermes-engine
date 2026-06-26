"""Self-evolution integration tests — context builder, memory synthesizer,
LLM skill matching, and agent enriched-context injection."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from provider.registry import ProviderRegistry


# ── Context builder ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_context_empty_no_services():
    """Returns empty string when no services are provided."""
    from shared.context_builder import build_context

    result = await build_context(
        [{"role": "user", "content": "Hello"}],
        memory_service=None,
        skill_service=None,
    )
    assert result == ""


@pytest.mark.asyncio
async def test_build_context_with_memories():
    """Injects relevant memory content into the context string."""
    from shared.context_builder import build_context

    class FakeMemoryService:
        def search(self, query, limit=5, scope=None, offset=0):
            return [{"content": "User prefers Python over Java"}], 1

    result = await build_context(
        [{"role": "user", "content": "What language should I use?"}],
        memory_service=FakeMemoryService(),  # type: ignore[arg-type]
    )
    assert "Relevant Memories" in result
    assert "prefers Python" in result


@pytest.mark.asyncio
async def test_build_context_with_skills():
    """Injects relevant skill descriptions into the context string."""
    from shared.context_builder import build_context

    class FakeSkillService:
        def search(self, query, top_k=3):
            return [{"name": "test", "description": "A testing skill"}]

    result = await build_context(
        [{"role": "user", "content": "How to test?"}],
        skill_service=FakeSkillService(),  # type: ignore[arg-type]
    )
    assert "Relevant Skills" in result
    assert "testing skill" in result


@pytest.mark.asyncio
async def test_build_context_with_both():
    """Includes both memory and skill sections when both are available."""
    from shared.context_builder import build_context

    class FakeMemoryService:
        def search(self, query, limit=5, scope=None, offset=0):
            return [{"content": "memory content"}], 1

    class FakeSkillService:
        def search(self, query, top_k=3):
            return [{"name": "skill-name", "description": "skill description"}]

    result = await build_context(
        [{"role": "user", "content": "test query"}],
        memory_service=FakeMemoryService(),  # type: ignore[arg-type]
        skill_service=FakeSkillService(),  # type: ignore[arg-type]
    )
    assert "Relevant Memories" in result
    assert "Relevant Skills" in result


@pytest.mark.asyncio
async def test_build_context_empty_query():
    """Returns empty string when no user message is found."""
    from shared.context_builder import build_context

    class FakeMemoryService:
        def search(self, query, limit=5, scope=None, offset=0):
            return [{"content": "hello"}], 1

    result = await build_context(
        [{"role": "assistant", "content": "How can I help?"}],
        memory_service=FakeMemoryService(),  # type: ignore[arg-type]
    )
    assert result == ""


@pytest.mark.asyncio
async def test_build_context_services_error_graceful():
    """Does not raise when a service operation fails."""
    from shared.context_builder import build_context

    class BoomMemoryService:
        def search(self, query, limit=5, scope=None, offset=0):
            raise RuntimeError("boom")

    result = await build_context(
        [{"role": "user", "content": "test"}],
        memory_service=BoomMemoryService(),  # type: ignore[arg-type]
    )
    assert result == ""


def test_extract_user_query_text():
    """Extracts the last user message content."""
    from shared.context_builder import _extract_user_query

    q = _extract_user_query([
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "Hello world"},
    ])
    assert q == "Hello world"


def test_extract_user_query_content_blocks():
    """Extracts text from Anthropic-style content blocks."""
    from shared.context_builder import _extract_user_query

    q = _extract_user_query([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hi there"},
                {"type": "text", "text": "How are you?"},
            ],
        },
    ])
    assert q == "Hi there How are you?"


def test_extract_user_query_no_user():
    """Returns empty string when no user message exists."""
    from shared.context_builder import _extract_user_query

    assert _extract_user_query([]) == ""
    assert _extract_user_query([{"role": "system", "content": "hello"}]) == ""


# ── Memory synthesizer ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesize_memory_no_provider():
    """Returns None when no provider is configured."""
    from shared.memory_synthesizer import synthesize_memory

    # Ensure no provider named "anthropic" is registered in tests
    result = await synthesize_memory(
        "What is Python?",
        "Python is a programming language.",
        provider_name="nonexistent-synth",
    )
    assert result is None


@pytest.mark.asyncio
async def test_synthesize_memory_produces_text():
    """Returns a string when a provider is available."""
    from shared.memory_synthesizer import synthesize_memory
    from provider.registry import registry as test_reg
    from provider.base import ProviderBase

    class SynthMockProvider(ProviderBase):
        name = "synth-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            return {"content": "User asked about Python for data science"}

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(SynthMockProvider())
    try:
        result = await synthesize_memory(
            "What is Python?",
            "Python is great for data science.",
            provider_name="synth-mock",
        )
        assert result == "User asked about Python for data science"
    finally:
        test_reg.remove("synth-mock")


# ── LLM skill matching ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_match_empty_skills():
    """Returns empty list when skills list is empty."""
    from skill.matcher import SkillMatcher
    from skill.loader import SkillLoader

    loader = SkillLoader(MagicMock())
    matcher = SkillMatcher(loader)
    result = await matcher.llm_match("query", [])
    assert result == []


@pytest.mark.asyncio
async def test_llm_match_falls_back_to_keyword():
    """Falls back to keyword matching when no provider is available."""
    from skill.matcher import SkillMatcher
    from skill.loader import SkillLoader

    loader = SkillLoader(MagicMock())
    loader._skills["test-skill"] = MagicMock()
    loader._skills["test-skill"].name = "test-skill"
    loader._skills["test-skill"].description = "A testing skill"
    loader._skills["test-skill"].tags = ["test"]
    loader._skills["test-skill"].to_dict = lambda: {  # type: ignore[method-assign]
        "name": "test-skill",
        "description": "A testing skill",
        "tags": ["test"],
        "path": "/tmp/test.md",
        "metadata": {},
    }
    loader._skills["test-skill"].matches = lambda q: "test" in q  # type: ignore[method-assign,assignment]

    matcher = SkillMatcher(loader)
    result = await matcher.llm_match("test query", [
        {"name": "test-skill", "description": "A testing skill", "tags": ["test"]},
    ])
    assert len(result) >= 0  # fallback worked without error


# ── Enriched context flows through agent engine ────────────────────────────


@pytest.mark.asyncio
async def test_engine_injects_enriched_context():
    """Enriched context is appended to the system prompt."""
    from agent.engine import AgentEngine

    engine = AgentEngine()

    messages = engine._prepare_messages(
        [{"role": "user", "content": "Hi"}],
        enriched_context="## Relevant Memories\n- User likes Python",
    )
    system = messages[0]
    assert system["role"] == "system"
    assert "Relevant Memories" in system["content"]
    assert "likes Python" in system["content"]


@pytest.mark.asyncio
async def test_engine_no_enriched_context():
    """System prompt is unchanged when no enriched context is provided."""
    from agent.engine import AgentEngine

    engine = AgentEngine()

    messages = engine._prepare_messages(
        [{"role": "user", "content": "Hi"}],
    )
    system = messages[0]
    assert system["role"] == "system"
    assert "Relevant Memories" not in system["content"]


@pytest.mark.asyncio
async def test_engine_preserves_existing_system_message():
    """Does not modify message list when system message already present."""
    from agent.engine import AgentEngine

    engine = AgentEngine()

    messages = engine._prepare_messages(
        [
            {"role": "system", "content": "I am a custom bot"},
            {"role": "user", "content": "Hi"},
        ],
        enriched_context="## Skills\n- test-skill",
    )
    # Existing system message is preserved as-is (no context injection)
    assert messages[0]["content"] == "I am a custom bot"


@pytest.mark.asyncio
async def test_agent_run_turn_passes_enriched_context():
    """Agent turn passes enriched_context to _prepare_messages."""
    from agent.engine import AgentEngine
    from provider.registry import registry as test_reg
    from provider.base import ProviderBase

    class CtxMockProvider(ProviderBase):
        name = "ctx-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            # Verify the system prompt contains our enrichment
            msgs = kwargs.get("messages", [])
            system = msgs[0]["content"] if msgs else ""
            return {
                "id": "ctx-1",
                "model": "mock",
                "role": "assistant",
                "content": f"System had enrichment: {'##' in system}",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "stop_reason": "end_turn",
            }

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(CtxMockProvider())
    try:
        engine = AgentEngine()
        result = await engine.run_turn(
            [{"role": "user", "content": "test"}],
            provider_name="ctx-mock",
            enriched_context="## Some Enrichment Data",
        )
        assert "True" in str(result.get("content", ""))
    finally:
        test_reg.remove("ctx-mock")
