"""P0 capability tests — context compressor, skill patcher, subagent, skill auto-create."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from provider.registry import ProviderRegistry
from provider.base import ProviderBase


# ── Context compressor ──────────────────────────────────────────────────────


def test_message_char_count():
    """_message_char_count sums character counts of all messages."""
    from shared.context_compressor import _message_char_count

    assert _message_char_count([{"role": "user", "content": "hello"}]) > 0
    assert _message_char_count([
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "bb"},
    ]) > 2


@pytest.mark.asyncio
async def test_compress_messages_under_threshold():
    """Returns original messages when under max_chars."""
    from shared.context_compressor import compress_messages

    msgs = [{"role": "user", "content": "short msg"}]
    # total chars < 60000 default
    result = await compress_messages(msgs, "anthropic", "claude-sonnet-4", max_chars=60000)
    assert result is msgs  # same list reference


@pytest.mark.asyncio
async def test_compress_messages_too_few():
    """Returns original messages when there aren't enough to compress."""
    from shared.context_compressor import compress_messages

    msgs = [{"role": "user", "content": "x" * 100}] * 7
    # keep_last=6 → middle is only 1 message, not worth compressing
    result = await compress_messages(msgs, "anthropic", "claude", max_chars=1, keep_last=6)
    assert len(result) == len(msgs)


@pytest.mark.asyncio
async def test_compress_messages_triggers():
    """Compresses when messages exceed threshold and there are enough to compress."""
    from shared.context_compressor import compress_messages
    from provider.registry import registry as test_reg

    class CompMockProvider(ProviderBase):
        name = "comp-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            return {"content": "This is a compressed summary of the middle turns."}

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(CompMockProvider())
    try:
        msgs = [
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "y" * 2000},
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "y" * 2000},
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "y" * 2000},
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "y" * 2000},
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "keep me"},
        ]
        result = await compress_messages(
            msgs, "comp-mock", "mock-model",
            max_chars=500, keep_last=4,
        )
        # Should have fewer messages than original
        assert len(result) < len(msgs)
        # Last message should be preserved
        assert result[-1]["content"] == "keep me"
    finally:
        test_reg.remove("comp-mock")


@pytest.mark.asyncio
async def test_compress_messages_no_provider_returns_original():
    """Returns original messages when provider is unavailable."""
    from shared.context_compressor import compress_messages

    msgs = [{"role": "user", "content": "x" * 2000}] * 20
    result = await compress_messages(
        msgs, "nonexistent", "mock", max_chars=1, keep_last=4,
    )
    assert len(result) == len(msgs)


# ── Skill patcher ───────────────────────────────────────────────────────────


def test_skill_patcher_first_occurrence():
    """Patch replaces the first occurrence of old_string."""
    from skill.patcher import SkillPatcher

    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp)
        file = skill_dir / "test-skill.md"
        file.write_text("Hello world. Hello again.")
        patcher = SkillPatcher(skill_dir)
        result = patcher.patch("test-skill", "Hello", "Hi")
        # "Hello world" → "Hi world" + "Hello again" stays
        assert "Hi world" in file.read_text()
        assert "Hello again" in file.read_text()
        assert result["old_length"] == 25
        assert result["new_length"] == 22


def test_skill_patcher_not_found_raises():
    """NotFoundError when skill file does not exist."""
    from skill.patcher import SkillPatcher
    from shared.errors import NotFoundError

    with tempfile.TemporaryDirectory() as tmp:
        patcher = SkillPatcher(Path(tmp))
        with pytest.raises(NotFoundError):
            patcher.patch("nonexistent", "a", "b")


def test_skill_patcher_old_string_not_found_raises():
    """ValidationError when old_string is not in the file."""
    from skill.patcher import SkillPatcher
    from shared.errors import ValidationError

    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp)
        (skill_dir / "test.md").write_text("abc def")
        patcher = SkillPatcher(skill_dir)
        with pytest.raises(ValidationError):
            patcher.patch("test", "xyz", "123")


def test_skill_patcher_replace_all():
    """patch_all replaces every occurrence."""
    from skill.patcher import SkillPatcher

    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp)
        (skill_dir / "test.md").write_text("foo bar foo baz foo")
        patcher = SkillPatcher(skill_dir)
        result = patcher.patch_all("test", "foo", "qux")
        content = (skill_dir / "test.md").read_text()
        assert "foo" not in content
        assert content.count("qux") == 3
        assert result["replacements"] == 3


# ── Sub-agent ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_subagent_succeeds():
    """Sub-agent executes a task and returns the result."""
    from shared.subagent import run_subagent
    from provider.registry import registry as test_reg

    class SubMockProvider(ProviderBase):
        name = "sub-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            return {
                "id": "sub-1",
                "model": "mock",
                "role": "assistant",
                "content": "Task completed",
                "usage": {"input_tokens": 5, "output_tokens": 3},
                "stop_reason": "end_turn",
            }

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(SubMockProvider())
    try:
        result = await run_subagent(
            "Count to 3",
            provider_name="sub-mock",
            model="mock",
            timeout=10.0,
        )
        assert result["content"] == "Task completed"
    finally:
        test_reg.remove("sub-mock")


@pytest.mark.asyncio
async def test_run_subagent_timeout():
    """Sub-agent raises TimeoutError when it exceeds the deadline."""
    from shared.subagent import run_subagent
    from provider.registry import registry as test_reg

    class SlowProvider(ProviderBase):
        name = "slow-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            import asyncio
            await asyncio.sleep(5)
            return {"content": "too late"}

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(SlowProvider())
    try:
        with pytest.raises(TimeoutError):
            await run_subagent("task", provider_name="slow-mock", timeout=0.01)
    finally:
        test_reg.remove("slow-mock")


@pytest.mark.asyncio
async def test_run_subagent_provider_not_found():
    """Sub-agent raises ValueError when provider is not registered."""
    from shared.subagent import run_subagent

    with pytest.raises(ValueError, match="not available"):
        await run_subagent("test", provider_name="nonexistent-sub")


@pytest.mark.asyncio
async def test_run_subagents_parallel():
    """Multiple sub-agents run in parallel."""
    from shared.subagent import run_subagents_parallel
    from provider.registry import registry as test_reg

    class ParaProvider(ProviderBase):
        name = "para-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            return {"content": "done", "id": "p", "model": "m",
                    "role": "assistant", "usage": {}, "stop_reason": "end_turn"}

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(ParaProvider())
    try:
        results = await run_subagents_parallel(
            ["task A", "task B", "task C"],
            provider_name="para-mock",
            timeout=5.0,
        )
        assert len(results) == 3
        assert all(r is not None for r in results)
    finally:
        test_reg.remove("para-mock")


# ── Skill PATCH endpoint ────────────────────────────────────────────────────


def test_skill_patch_endpoint(client):
    """PATCH /api/skills/{name} patches a skill file."""
    # First create a skill
    client.post("/api/skills", json={
        "name": "patch-test",
        "description": "A test skill for patching",
        "content": "# Patch Test\n\nHello world. Some more text.",
        "tags": ["test"],
    })

    # Patch it
    resp = client.patch("/api/skills/patch-test", json={
        "old_string": "Hello world",
        "new_string": "Bonjour monde",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    # Verify via GET
    resp2 = client.get("/api/skills/patch-test")
    assert resp2.status_code == 200
    # Note: GET only returns metadata (name, description, tags, path) — not content
    # So just verify the patch didn't error


def test_skill_patch_not_found(client):
    """PATCH returns 404 for unknown skills."""
    resp = client.patch("/api/skills/nonexistent-patch", json={
        "old_string": "a",
        "new_string": "b",
    })
    assert resp.status_code == 404


def test_skill_patch_old_string_not_found(client):
    """PATCH returns 422 when old_string not in file."""
    client.post("/api/skills", json={
        "name": "patch-422",
        "description": "test",
        "content": "abc def",
        "tags": [],
    })
    resp = client.patch("/api/skills/patch-422", json={
        "old_string": "not-present",
        "new_string": "replacement",
    })
    assert resp.status_code == 422


# ── Skill auto-create (helper functions) ────────────────────────────────────


def test_count_tool_calls_zero():
    """Returns 0 when response has no tool_use blocks."""
    from agent.router import _count_tool_calls
    assert _count_tool_calls({"content": "plain text"}) == 0
    assert _count_tool_calls({"content": [{"type": "text", "text": "hi"}]}) == 0


def test_count_tool_calls_counts_correctly():
    """Counts tool_use blocks in the response content."""
    from agent.router import _count_tool_calls
    assert _count_tool_calls({"content": [
        {"type": "text", "text": "Let me check"},
        {"type": "tool_use", "name": "read_file", "id": "t1", "input": {}},
        {"type": "tool_use", "name": "write_file", "id": "t2", "input": {}},
        {"type": "text", "text": "Done"},
        {"type": "tool_use", "name": "execute", "id": "t3", "input": {}},
    ]}) == 3


# ── Settings defaults ────────────────────────────────────────────────────────


def test_settings_context_compression_defaults():
    """Context compression settings have sensible defaults."""
    from config.settings import Settings
    s = Settings()
    assert s.context_compression_enabled is True
    assert s.context_max_chars == 60000
    assert s.context_keep_last_messages == 6


def test_settings_skill_auto_create_defaults():
    """Skill auto-creation settings have sensible defaults."""
    from config.settings import Settings
    s = Settings()
    assert s.skill_auto_create_enabled is True
    assert s.skill_auto_create_min_tool_calls == 5


def test_settings_subagent_defaults():
    """Sub-agent settings have sensible defaults."""
    from config.settings import Settings
    s = Settings()
    assert s.subagent_timeout == 300.0
    assert s.subagent_max_concurrent == 3
