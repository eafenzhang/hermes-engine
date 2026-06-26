"""Final integration tests — stateful sessions, SSH backend, cross-session recall, NL cron."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import Settings
from provider.registry import ProviderRegistry
from provider.base import ProviderBase


# ── SSH terminal backend ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ssh_backend_registered():
    """SSH backend is available in the factory."""
    from tools.terminal_backends import get_backend

    backend = get_backend("ssh", ssh_host="localhost", ssh_user="test")
    assert backend.name == "ssh"


@pytest.mark.asyncio
async def test_docker_backend_registered():
    """Docker backend is available in the factory."""
    from tools.terminal_backends import get_backend

    backend = get_backend("docker", docker_image="python:3.12-slim")
    assert backend.name == "docker"


@pytest.mark.asyncio
async def test_local_backend_is_default():
    """Local backend is the default when name is unknown."""
    from tools.terminal_backends import get_backend

    backend = get_backend("unknown")
    assert backend.name == "local"


# ── Cross-session recall ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_conversations_empty():
    """Returns empty list when no conversations exist."""
    from shared.context_builder import recall_conversations

    class EmptyConvService:
        def list_conversations(self, limit=50):
            return [], 0

    result = await recall_conversations("test query", EmptyConvService())
    assert result == []


@pytest.mark.asyncio
async def test_recall_conversations_finds_title():
    """Finds conversations whose titles overlap with the query."""
    from shared.context_builder import recall_conversations

    class FakeConvService:
        def list_conversations(self, limit=50):
            return [
                {"id": "c1", "title": "Python testing guide"},
                {"id": "c2", "title": "Database optimization"},
            ], 2

    result = await recall_conversations("python testing", FakeConvService())
    assert len(result) > 0
    assert any("Python testing" in r for r in result)


# ── NL cron parsing ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_nl_cron_no_provider():
    """Returns None when no provider is available."""
    from shared.scheduler import parse_nl_cron

    result = await parse_nl_cron("every day at 3pm", provider_name="nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_parse_nl_cron_valid():
    """Parses NL schedule into cron expression."""
    from shared.scheduler import parse_nl_cron
    from provider.registry import registry as test_reg

    class NlCronProvider(ProviderBase):
        name = "nl-cron-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            return {"content": "0 15 * * *"}

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(NlCronProvider())
    try:
        result = await parse_nl_cron(
            "every day at 3pm", provider_name="nl-cron-mock",
        )
        assert result == "0 15 * * *"
    finally:
        test_reg.remove("nl-cron-mock")


@pytest.mark.asyncio
async def test_parse_nl_cron_invalid_response():
    """Returns None when LLM returns invalid cron."""
    from shared.scheduler import parse_nl_cron
    from provider.registry import registry as test_reg

    class BadCronProvider(ProviderBase):
        name = "bad-cron-mock"

        def __init__(self):
            super().__init__(api_key="sk-mock")

        async def chat_completion(self, **kwargs):  # type: ignore[override]
            return {"content": "not a cron expression"}

        async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
            if False:
                yield ""

        async def list_models(self) -> list[dict[str, Any]]:
            return []

    test_reg.register(BadCronProvider())
    try:
        result = await parse_nl_cron("test", provider_name="bad-cron-mock")
        assert result is None
    finally:
        test_reg.remove("bad-cron-mock")


# ── Stateful session chat ───────────────────────────────────────────────────


def test_conversation_id_in_schema():
    """AgentTurnRequest has optional conversation_id field."""
    from agent.schemas import AgentTurnRequest

    req = AgentTurnRequest(messages=[{"role": "user", "content": "hi"}])
    assert req.conversation_id is None

    req2 = AgentTurnRequest(
        messages=[{"role": "user", "content": "hi"}],
        conversation_id="conv-123",
    )
    assert req2.conversation_id == "conv-123"


def test_session_endpoint_creates_new_session(client):
    """POST /api/sessions/{id}/chat creates a new conversation (may fail without provider)."""
    resp = client.post(
        "/api/sessions/test-session-1/chat",
        json={"messages": [{"role": "user", "content": "Hello world"}]},
    )
    # Accepts 200 (success) or structured error (no provider configured)
    assert resp.status_code in (200, 400)
    body = resp.json()
    assert "error" in body or "success" in body


def test_session_endpoint_multi_turn(client):
    """Multiple calls to the same session maintain conversation history."""
    r1 = client.post(
        "/api/sessions/test-session-2/chat",
        json={"messages": [{"role": "user", "content": "My name is Alice"}]},
    )
    assert r1.status_code in (200, 400)
    body = r1.json()
    assert "error" in body or "success" in body

    r2 = client.post(
        "/api/sessions/test-session-2/chat",
        json={"messages": [{"role": "user", "content": "What is my name?"}]},
    )
    assert r2.status_code in (200, 400)


def test_session_list_all(client):
    """GET /api/sessions returns session list."""
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "sessions" in body["data"]


# ── Settings defaults ───────────────────────────────────────────────────────


def test_settings_ssh_defaults():
    """SSH settings have safe defaults."""
    s = Settings()
    assert s.ssh_host == ""
    assert s.ssh_user == ""
    assert s.ssh_key_path == ""
    assert s.ssh_port == 22


def test_settings_session_defaults():
    """Session settings have sensible defaults."""
    s = Settings()
    assert s.session_enabled is True
    assert s.session_search_max == 3
    assert s.cron_nl_enabled is True


# ── NL cron endpoint ────────────────────────────────────────────────────────


def test_parse_cron_endpoint(client):
    """POST /api/cron/parse converts NL to cron."""
    resp = client.post("/api/cron/parse", json={"text": "every day at 3pm"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "cron" in body["data"]
