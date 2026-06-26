"""Chinese AI provider tests — settings, registration, and model routing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import Settings
from provider.registry import ProviderRegistry
from provider.base import ProviderBase


# ── Settings: API key and base URL fields ──────────────────────────────────


def test_settings_loads_deepseek_fields():
    """DeepSeek API key and base URL are loaded from environment."""
    settings = Settings(
        deepseek_api_key="sk-deepseek-test",
        deepseek_base_url="https://api.deepseek.com/v1",
    )
    assert settings.deepseek_api_key == "sk-deepseek-test"
    assert settings.deepseek_base_url == "https://api.deepseek.com/v1"


def test_settings_loads_moonshot_fields():
    """Moonshot API key and base URL are loaded from environment."""
    settings = Settings(
        moonshot_api_key="sk-moonshot-test",
        moonshot_base_url="https://api.moonshot.cn/v1",
    )
    assert settings.moonshot_api_key == "sk-moonshot-test"
    assert settings.moonshot_base_url == "https://api.moonshot.cn/v1"


def test_settings_loads_zhipu_fields():
    """Zhipu API key and base URL are loaded from environment."""
    settings = Settings(
        zhipu_api_key="zhipu-test-key",
        zhipu_base_url="https://open.bigmodel.cn/api/paas/v4",
    )
    assert settings.zhipu_api_key == "zhipu-test-key"
    assert settings.zhipu_base_url == "https://open.bigmodel.cn/api/paas/v4"


def test_settings_loads_qwen_fields():
    """Qwen API key and base URL are loaded from environment."""
    settings = Settings(
        qwen_api_key="sk-qwen-test",
        qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert settings.qwen_api_key == "sk-qwen-test"
    assert settings.qwen_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_settings_loads_xiaomi_fields():
    """Xiaomi API key is loaded; base URL defaults to empty string."""
    settings = Settings(xiaomi_api_key="sk-xiaomi-test")
    assert settings.xiaomi_api_key == "sk-xiaomi-test"
    assert settings.xiaomi_base_url == ""


def test_settings_loads_minimax_fields():
    """MiniMax API key and base URL are loaded from environment."""
    settings = Settings(
        minimax_api_key="sk-minimax-test",
        minimax_base_url="https://api.minimax.chat/v1",
    )
    assert settings.minimax_api_key == "sk-minimax-test"
    assert settings.minimax_base_url == "https://api.minimax.chat/v1"


def test_settings_all_providers_empty_by_default():
    """All Chinese provider fields are empty strings by default."""
    settings = Settings()
    assert settings.deepseek_api_key == ""
    assert settings.moonshot_api_key == ""
    assert settings.zhipu_api_key == ""
    assert settings.qwen_api_key == ""
    assert settings.xiaomi_api_key == ""
    assert settings.minimax_api_key == ""
    # Base URLs have sensible defaults except Xiaomi
    assert settings.deepseek_base_url == "https://api.deepseek.com/v1"
    assert settings.moonshot_base_url == "https://api.moonshot.cn/v1"
    assert settings.qwen_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert settings.xiaomi_base_url == ""
    assert settings.minimax_base_url == "https://api.minimax.chat/v1"


def test_settings_chinese_providers_are_frozen():
    """Settings with Chinese providers respect frozen=True."""
    settings = Settings(deepseek_api_key="sk-test")
    with pytest.raises(Exception):
        settings.deepseek_api_key = "sk-modified"  # type: ignore[misc]


# ── Provider registration ──────────────────────────────────────────────────


class FakeOpenAIAdapter(ProviderBase):
    """Fake OpenAI adapter for registration testing."""

    name = "openai"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(api_key, base_url)
        self._client = None

    async def chat_completion(self, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def chat_completion_stream(self, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def check_connectivity(self) -> bool:
        return True

    async def list_models(self) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def clean_registry():
    """A fresh ProviderRegistry so tests don't leak state."""
    return ProviderRegistry()


def _make_settings(**overrides) -> Settings:
    """Build Settings with all keys empty except those in *overrides*."""
    kwargs: dict = {
        "anthropic_api_key": "",
        "openai_api_key": "",
        "gemini_api_key": "",
        "deepseek_api_key": "",
        "moonshot_api_key": "",
        "zhipu_api_key": "",
        "qwen_api_key": "",
        "xiaomi_api_key": "",
        "minimax_api_key": "",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


@pytest.mark.asyncio
async def test_deepseek_registered_when_key_present(clean_registry):
    """DeepSeek is registered when API key is configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(deepseek_api_key="sk-deepseek")
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    provider = clean_registry.get("deepseek")
    assert provider is not None
    assert provider.name == "deepseek"
    assert provider.base_url == "https://api.deepseek.com/v1"


@pytest.mark.asyncio
async def test_moonshot_registered_when_key_present(clean_registry):
    """Moonshot is registered when API key is configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(moonshot_api_key="sk-moonshot")
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    provider = clean_registry.get("moonshot")
    assert provider is not None
    assert provider.name == "moonshot"
    assert provider.base_url == "https://api.moonshot.cn/v1"


@pytest.mark.asyncio
async def test_zhipu_registered_when_key_present(clean_registry):
    """Zhipu is registered when API key is configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(zhipu_api_key="zhipu-key")
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    provider = clean_registry.get("zhipu")
    assert provider is not None
    assert provider.name == "zhipu"


@pytest.mark.asyncio
async def test_qwen_registered_when_key_present(clean_registry):
    """Qwen is registered when API key is configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(qwen_api_key="sk-qwen")
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    provider = clean_registry.get("qwen")
    assert provider is not None
    assert provider.name == "qwen"


@pytest.mark.asyncio
async def test_xiaomi_skipped_when_no_base_url(clean_registry):
    """Xiaomi is NOT registered when base_url is empty (avoids OpenAI fallback)."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(xiaomi_api_key="sk-xiaomi")
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    assert clean_registry.get("xiaomi") is None


@pytest.mark.asyncio
async def test_xiaomi_registered_when_base_url_set(clean_registry):
    """Xiaomi IS registered when both API key and base_url are configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(
            xiaomi_api_key="sk-xiaomi",
            xiaomi_base_url="https://api.xiaomi.com/v1",
        )
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    provider = clean_registry.get("xiaomi")
    assert provider is not None
    assert provider.name == "xiaomi"
    assert provider.base_url == "https://api.xiaomi.com/v1"


@pytest.mark.asyncio
async def test_minimax_registered_when_key_present(clean_registry):
    """MiniMax is registered when API key is configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(minimax_api_key="sk-minimax")
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    provider = clean_registry.get("minimax")
    assert provider is not None
    assert provider.name == "minimax"


@pytest.mark.asyncio
async def test_provider_not_registered_without_key(clean_registry):
    """No Chinese provider is registered when no API keys are set."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings()
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    assert clean_registry.count == 0


@pytest.mark.asyncio
async def test_multiple_chinese_providers_registered_together(clean_registry):
    """Multiple Chinese providers can be registered simultaneously."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(
            deepseek_api_key="sk-ds",
            moonshot_api_key="sk-ms",
            qwen_api_key="sk-qw",
        )
        with patch("provider.openai_adapter.OpenAIAdapter", FakeOpenAIAdapter):
            init_providers(settings)

    assert clean_registry.count == 3
    assert clean_registry.get("deepseek") is not None
    assert clean_registry.get("moonshot") is not None
    assert clean_registry.get("qwen") is not None


# ── Model routing for Chinese providers ────────────────────────────────────


def test_resolve_deepseek_models():
    """DeepSeek-prefixed models are routed to the deepseek provider."""
    from api_compat.router import _resolve_provider

    for model in ("deepseek-chat", "deepseek-reasoner", "deepseek-coder"):
        prov, resolved = _resolve_provider(model)
        assert prov == "deepseek", f"{model} → {prov}"
        assert resolved == model


def test_resolve_moonshot_kimi_models():
    """Moonshot and Kimi models route to the moonshot provider."""
    from api_compat.router import _resolve_provider

    for model in ("moonshot-v1-8k", "moonshot-v1-32k", "kimi-latest"):
        prov, _ = _resolve_provider(model)
        assert prov == "moonshot", f"{model} → {prov}"


def test_resolve_zhipu_glm_models():
    """GLM, ChatGLM, and Zhipu models route to the zhipu provider."""
    from api_compat.router import _resolve_provider

    for model in ("glm-4", "glm-4-flash", "chatglm-turbo", "zhipu-glm"):
        prov, _ = _resolve_provider(model)
        assert prov == "zhipu", f"{model} → {prov}"


def test_resolve_qwen_models():
    """Qwen models route to the qwen provider."""
    from api_compat.router import _resolve_provider

    for model in ("qwen-turbo", "qwen-plus", "qwen-max", "qwen2.5-72b"):
        prov, _ = _resolve_provider(model)
        assert prov == "qwen", f"{model} → {prov}"


def test_resolve_xiaomi_mimo_models():
    """Mimo models route to the xiaomi provider."""
    from api_compat.router import _resolve_provider

    for model in ("mimo-pro", "mimo-lite", "mimo-v1"):
        prov, _ = _resolve_provider(model)
        assert prov == "xiaomi", f"{model} → {prov}"


def test_resolve_minimax_models():
    """MiniMax and ABAB models route to the minimax provider."""
    from api_compat.router import _resolve_provider

    for model in ("abab6.5s-chat", "minimax-text-01", "abab6-pro"):
        prov, _ = _resolve_provider(model)
        assert prov == "minimax", f"{model} → {prov}"


# ── Connectivity check ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_connectivity_uses_models_list():
    """OpenAIAdapter.check_connectivity calls models.list(), not chat completions."""
    from provider.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="sk-test", base_url="https://test.local/v1")

    # Mock the internal client so it doesn't hit a real HTTP endpoint
    mock_client = MagicMock()
    mock_client.models = MagicMock()
    mock_client.models.list = AsyncMock(return_value=MagicMock(data=[]))

    adapter._client = mock_client
    assert await adapter.check_connectivity()

    mock_client.models.list.assert_awaited_once()
    # chat.completions.create should never be called in connectivity check
    mock_client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_check_connectivity_returns_false_on_error():
    """OpenAIAdapter.check_connectivity returns False when models.list() fails."""
    from provider.openai_adapter import OpenAIAdapter

    adapter = OpenAIAdapter(api_key="sk-test", base_url="https://test.local/v1")

    mock_client = MagicMock()
    mock_client.models = MagicMock()
    mock_client.models.list = AsyncMock(side_effect=Exception("Connection refused"))

    adapter._client = mock_client
    assert not await adapter.check_connectivity()
