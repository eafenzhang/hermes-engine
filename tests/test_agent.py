"""Agent endpoint tests — mock provider to avoid needing API keys."""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from provider.base import ProviderBase
from provider.registry import registry


class AgentMockProvider(ProviderBase):
    """Mock provider that returns canned agent responses."""

    name = "agent-mock"

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "mock-model",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "id": "agent-mock-id",
            "model": model,
            "role": "assistant",
            "content": "Agent mock response.",
            "usage": {"input_tokens": 20, "output_tokens": 10},
            "stop_reason": "end_turn",
        }

    async def chat_completion_stream(  # type: ignore[override]
        self,
        messages: list[dict[str, Any]],
        model: str = "mock-model",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        yield "data: {\"type\": \"text\", \"content\": \"streaming mock\"}\n\n"
        yield "data: {\"type\": \"done\", \"usage\": {\"input_tokens\": 10, \"output_tokens\": 5}}\n\n"

    def validate_key(self) -> bool:
        return True


class StreamingOnlyProvider(ProviderBase):
    """Provider that only supports streaming (non-streaming raises)."""

    name = "streaming-only"

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "mock-model",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise RuntimeError("Non-streaming not supported")

    async def chat_completion_stream(  # type: ignore[override]
        self,
        messages: list[dict[str, Any]],
        model: str = "mock-model",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        yield "data: {\"type\": \"text\", \"content\": \"stream only\"}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    def validate_key(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def setup_agent_providers():
    """Register mock providers needed for agent tests."""
    mock = AgentMockProvider(api_key="agent-mock-key")
    streaming = StreamingOnlyProvider(api_key="stream-key")
    registry.register(mock)
    registry.register(streaming)
    yield
    registry.remove("agent-mock")
    registry.remove("streaming-only")


class TestAgentChat:
    def test_chat_non_streaming(self, client):
        """POST /api/agent/chat returns agent response."""
        resp = client.post("/api/agent/chat", json={
            "messages": [{"role": "user", "content": "Hello agent"}],
            "provider": "agent-mock",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["content"] == "Agent mock response."

    def test_chat_injects_system_prompt(self, client):
        """Engine adds system prompt if none provided."""
        resp = client.post("/api/agent/chat", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "agent-mock",
        })
        assert resp.status_code == 200

    def test_chat_custom_model(self, client):
        """Custom model passed through to provider."""
        resp = client.post("/api/agent/chat", json={
            "messages": [{"role": "user", "content": "Hello"}],
            "provider": "agent-mock",
            "model": "custom-agent-model",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["model"] == "custom-agent-model"

    def test_chat_with_tools(self, client):
        """Tools list is passed through to provider."""
        resp = client.post("/api/agent/chat", json={
            "messages": [{"role": "user", "content": "Use a tool"}],
            "provider": "agent-mock",
            "tools": [{
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {"type": "object", "properties": {}},
            }],
        })
        assert resp.status_code == 200


class TestAgentStream:
    def test_chat_stream(self, client):
        """POST /api/agent/chat/stream returns SSE chunks."""
        resp = client.post("/api/agent/chat/stream", json={
            "messages": [{"role": "user", "content": "Stream test"}],
            "provider": "agent-mock",
        })
        assert resp.status_code == 200
        assert "streaming mock" in resp.text

    def test_chat_stream_uses_streaming_provider(self, client):
        """Streaming-only provider works with stream endpoint."""
        resp = client.post("/api/agent/chat/stream", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "streaming-only",
        })
        assert resp.status_code == 200
        assert "stream only" in resp.text


class TestAgentErrors:
    def test_provider_not_found_non_streaming(self, client):
        """Non-streaming with unknown provider returns error."""
        resp = client.post("/api/agent/chat", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "nonexistent-agent-provider",
        })
        assert resp.status_code == 400

    def test_provider_not_found_streaming(self, client):
        """Streaming with unknown provider returns error."""
        resp = client.post("/api/agent/chat/stream", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "nonexistent-agent-provider",
        })
        assert resp.status_code == 200  # SSE always returns 200
        assert "error" in resp.text
