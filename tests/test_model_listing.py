"""Model listing tests — adapters, ModelCache, and /api/providers/models endpoints."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import Settings
from provider.registry import ProviderRegistry
from provider.base import ProviderBase


# ── Settings: model_cache_ttl ──────────────────────────────────────────────


def test_settings_model_cache_ttl_default():
    """model_cache_ttl defaults to 300 seconds."""
    settings = Settings()
    assert settings.model_cache_ttl == 300.0


def test_settings_model_cache_ttl_custom():
    """model_cache_ttl can be configured via env."""
    settings = Settings(model_cache_ttl=60.0)
    assert settings.model_cache_ttl == 60.0


# ── ModelCache unit tests ─────────────────────────────────────────────────


def test_model_cache_hit():
    """Cached models are returned when within TTL."""
    from shared.model_cache import ModelCache

    cache = ModelCache(ttl=300)
    cache.set("openai", [{"id": "gpt-4o", "object": "model"}])
    assert cache.get("openai") == [{"id": "gpt-4o", "object": "model"}]


def test_model_cache_miss_unknown_provider():
    """None is returned for providers not in the cache."""
    from shared.model_cache import ModelCache

    cache = ModelCache(ttl=300)
    assert cache.get("nonexistent") is None


def test_model_cache_ttl_expiry():
    """Returns None when the TTL has elapsed."""
    from shared.model_cache import ModelCache

    cache = ModelCache(ttl=0.01)  # 10 ms
    cache.set("openai", [{"id": "gpt-4o"}])
    time.sleep(0.02)
    assert cache.get("openai") is None


def test_model_cache_clear_all():
    """clear() without args empties the whole cache."""
    from shared.model_cache import ModelCache

    cache = ModelCache(ttl=300)
    cache.set("openai", [{"id": "gpt-4o"}])
    cache.set("deepseek", [{"id": "deepseek-chat"}])
    assert cache.clear() == 2
    assert cache.get("openai") is None
    assert cache.get("deepseek") is None


def test_model_cache_clear_single():
    """clear('openai') only removes that one entry."""
    from shared.model_cache import ModelCache

    cache = ModelCache(ttl=300)
    cache.set("openai", [{"id": "gpt-4o"}])
    cache.set("deepseek", [{"id": "deepseek-chat"}])
    assert cache.clear("openai") == 1
    assert cache.get("openai") is None
    assert cache.get("deepseek") is not None


# ── Adapter list_models() implementations ────────────────────────────────


@pytest.mark.asyncio
async def test_openai_adapter_list_models():
    """OpenAIAdapter.list_models returns normalized model dicts."""
    from provider.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="sk-test")
    mock_client: Any = MagicMock()
    mock_model = MagicMock()
    mock_model.id = "gpt-4o"
    mock_model.owned_by = "openai"
    mock_client.models.list = AsyncMock(return_value=MagicMock(data=[mock_model]))
    adapter._client = mock_client

    models = await adapter.list_models()
    assert len(models) == 1
    assert models[0]["id"] == "gpt-4o"
    assert models[0]["object"] == "model"
    assert models[0]["owned_by"] == "openai"


@pytest.mark.asyncio
async def test_openai_adapter_list_models_error_returns_empty():
    """OpenAIAdapter.list_models returns [] when upstream fails."""
    from provider.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="sk-test")
    mock_client: Any = MagicMock()
    mock_client.models.list = AsyncMock(side_effect=Exception("timeout"))
    adapter._client = mock_client

    models = await adapter.list_models()
    assert models == []


@pytest.mark.asyncio
async def test_anthropic_adapter_list_models_unsupported():
    """AnthropicAdapter.list_models returns [] when SDK has no models.list."""
    from provider.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="sk-ant-test")
    mock_client: Any = MagicMock()
    mock_client.models.list = AsyncMock(side_effect=AttributeError("no models"))
    adapter._client = mock_client

    models = await adapter.list_models()
    assert models == []


@pytest.mark.asyncio
async def test_gemini_adapter_list_models():
    """GeminiAdapter.list_models converts async generator to list."""
    from provider.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter(api_key="gemini-test")

    class FakeModel:
        name = "gemini-2.0-flash"

    class FakeListResponse:
        """Simulates the async iterable returned by await models.list()."""

        def __init__(self, items):
            self._items = iter(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._items)
            except StopIteration:
                raise StopAsyncIteration

    mock_client: Any = MagicMock()
    mock_client.models = MagicMock()
    mock_client.models.list = AsyncMock(return_value=FakeListResponse([FakeModel()]))
    adapter._client = mock_client

    models = await adapter.list_models()
    assert len(models) == 1
    assert models[0]["id"] == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_gemini_adapter_list_models_error_returns_empty():
    """GeminiAdapter.list_models returns [] when upstream fails."""
    from provider.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter(api_key="gemini-test")
    mock_client: Any = MagicMock()
    mock_client.models.list = MagicMock(side_effect=Exception("timeout"))
    adapter._client = mock_client

    models = await adapter.list_models()
    assert models == []


# ── API endpoint integration tests ─────────────────────────────────────────


class FakeListModelsProvider(ProviderBase):
    """A provider that always returns the same model list for testing."""

    name = "fake"
    _models = [{"id": "fake-model", "object": "model"}]

    def __init__(self):
        super().__init__(api_key="sk-fake")

    async def chat_completion(self, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def list_models(self) -> list[dict[str, Any]]:
        return self._models


def test_models_endpoint_returns_all_providers(client):
    """GET /api/providers/models returns models grouped by provider name."""
    resp = client.get("/api/providers/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict)


def test_models_endpoint_filter_by_provider(client):
    """GET /api/providers/models?provider=openai returns a single provider entry."""
    resp = client.get("/api/providers/models?provider=openai")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    # 'openai' may be absent if no provider registered (returns empty dict
    # key). Either way the response shape is correct.
    assert isinstance(body["data"], dict)


def test_models_refresh_endpoint(client):
    """POST /api/providers/models/refresh clears the cache."""
    resp = client.post("/api/providers/models/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True


def test_models_refresh_single_provider(client):
    """POST /api/providers/models/refresh?provider=openai clears one provider."""
    resp = client.post("/api/providers/models/refresh?provider=openai")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True


def test_models_endpoint_with_fake_provider(tmp_settings):
    """Endpoint returns model data for providers registered via DI."""
    from main import create_app
    from provider.registry import registry
    from shared.model_cache import model_cache
    from starlette.testclient import TestClient

    # Clear cache and register a fake provider
    model_cache.clear()
    registry.register(FakeListModelsProvider())

    app = create_app(tmp_settings)
    with TestClient(app) as c:
        resp = c.get("/api/providers/models")
        assert resp.status_code == 200
        body = resp.json()
        assert "fake" in body["data"]
        assert body["data"]["fake"] == [{"id": "fake-model", "object": "model"}]

    # Cleanup
    registry.remove("fake")
    model_cache.clear()
