"""Provider endpoint tests — uses a mock provider to avoid needing API keys."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import pytest

from provider.base import ProviderBase
from provider.registry import registry


class MockProvider(ProviderBase):
    """A fake provider that returns canned responses."""

    name = "mock-provider"

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
            "id": "mock-id",
            "model": model,
            "role": "assistant",
            "content": "This is a mock response.",
            "usage": {"input_tokens": 10, "output_tokens": 5},
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
        yield "data: {\"type\": \"text\", \"content\": \"mock\"}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    def validate_key(self) -> bool:
        return True


class ErrorProvider(ProviderBase):
    """A fake provider that raises on every call."""

    name = "error-provider"

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "error-model",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise RuntimeError("Provider internal error")

    async def chat_completion_stream(  # type: ignore[override]
        self,
        messages: list[dict[str, Any]],
        model: str = "error-model",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        raise RuntimeError("Provider stream error")


@pytest.fixture(autouse=True)
def setup_providers():
    """Register mock providers before each test, clean up after."""
    mock = MockProvider(api_key="mock-key-12345")
    err = ErrorProvider(api_key="err-key-67890")
    registry.register(mock)
    registry.register(err)
    yield
    registry.remove("mock-provider")
    registry.remove("error-provider")


class TestProviderList:
    def test_list_providers(self, client):
        """GET /api/providers returns registered mock providers."""
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()["data"]
        names = [p["name"] for p in data]
        assert "mock-provider" in names
        assert "error-provider" in names

    def test_provider_list_shows_connected(self, client):
        """Each provider entry has a connected status."""
        resp = client.get("/api/providers")
        for p in resp.json()["data"]:
            assert "connected" in p
            assert p["connected"] is True


class TestProviderChat:
    def test_chat_non_streaming(self, client):
        """POST /api/providers/chat non-streaming returns ApiResponse."""
        resp = client.post("/api/providers/chat", json={
            "provider": "mock-provider",
            "model": "mock-model",
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["content"] == "This is a mock response."

    def test_chat_streaming(self, client):
        """POST /api/providers/chat streaming returns SSE chunks."""
        resp = client.post("/api/providers/chat", json={
            "provider": "mock-provider",
            "model": "mock-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        })
        assert resp.status_code == 200
        content = resp.text
        assert "data:" in content
        assert "mock" in content

    def test_chat_provider_not_found(self, client):
        """POST /api/providers/chat with unknown provider → 404."""
        resp = client.post("/api/providers/chat", json={
            "provider": "nonexistent",
            "messages": [{"role": "user", "content": "Hi"}],
        })
        assert resp.status_code == 404
        assert resp.json()["success"] is False

    def test_chat_provider_error(self, client):
        """When provider raises, API returns 502."""
        resp = client.post("/api/providers/chat", json={
            "provider": "error-provider",
            "messages": [{"role": "user", "content": "Hi"}],
        })
        assert resp.status_code == 502
        assert resp.json()["success"] is False

    def test_chat_custom_model(self, client):
        """Custom model name is passed through to provider."""
        resp = client.post("/api/providers/chat", json={
            "provider": "mock-provider",
            "model": "my-custom-model-v1",
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["model"] == "my-custom-model-v1"


class TestProviderRegistry:
    """Direct registry tests (no HTTP)."""

    def test_registry_count(self):
        """Registry tracks provider count."""
        assert registry.count >= 2

    def test_registry_remove(self):
        """Removing a provider returns True."""
        dummy = MockProvider(api_key="dummy-key")
        dummy.name = "dummy-for-remove"
        registry.register(dummy)
        assert registry.remove("dummy-for-remove") is True

    def test_registry_remove_missing(self):
        """Removing a non-existent provider returns False."""
        assert registry.remove("ghost-provider") is False
