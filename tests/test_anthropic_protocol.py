"""Anthropic protocol tests — settings, base_url, connectivity, registration, routing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import Settings
from provider.registry import ProviderRegistry
from provider.base import ProviderBase


# ── Settings: anthropic_base_url and anthropic_compat fields ──────────────


def test_settings_anthropic_base_url_default_empty():
    """anthropic_base_url defaults to empty string (official API)."""
    settings = Settings(anthropic_api_key="sk-ant-test")
    assert settings.anthropic_base_url == ""


def test_settings_anthropic_base_url_custom():
    """anthropic_base_url can be set via HERMES_ANTHROPIC_BASE_URL."""
    settings = Settings(anthropic_base_url="https://proxy.example.com")
    assert settings.anthropic_base_url == "https://proxy.example.com"


def test_settings_anthropic_compat_defaults():
    """anthropic_compat fields have sensible defaults."""
    settings = Settings()
    assert settings.anthropic_compat_api_key == ""
    assert settings.anthropic_compat_base_url == ""
    assert settings.anthropic_compat_model == "claude-sonnet-4-20250514"


def test_settings_anthropic_compat_configured():
    """anthropic_compat fields can be set."""
    settings = Settings(
        anthropic_compat_api_key="sk-ant-compat",
        anthropic_compat_base_url="https://gateway.example.com",
        anthropic_compat_model="claude-opus-4",
    )
    assert settings.anthropic_compat_api_key == "sk-ant-compat"
    assert settings.anthropic_compat_base_url == "https://gateway.example.com"
    assert settings.anthropic_compat_model == "claude-opus-4"


# ── AnthropicAdapter: base_url and connectivity model ─────────────────────


class FakeAsyncAnthropic:
    """Minimal fake for AsyncAnthropic — only needs the messages namespace."""

    class messages:
        create = AsyncMock()
        stream = MagicMock()


def test_anthropic_adapter_accepts_base_url():
    """AnthropicAdapter forwards base_url to the SDK client."""
    from provider.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(
        api_key="sk-ant-test",
        base_url="https://custom-proxy.example.com",
    )
    assert adapter.base_url == "https://custom-proxy.example.com"
    assert adapter._connectivity_model == "claude-sonnet-4-20250514"


def test_anthropic_adapter_connectivity_model_override():
    """connectivity_model instance attr is used by check_connectivity."""
    from provider.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="sk-ant-test")
    adapter._connectivity_model = "claude-opus-4"

    mock_client: Any = FakeAsyncAnthropic()
    mock_client.messages.create = AsyncMock(return_value=MagicMock())
    adapter._client = mock_client

    import asyncio
    result = asyncio.run(adapter.check_connectivity())
    assert result is True
    # Verify the overridden model was used
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs is not None
    assert call_kwargs[1]["model"] == "claude-opus-4"


def test_anthropic_adapter_connectivity_returns_false_on_error():
    """check_connectivity returns False when API call fails."""
    from provider.anthropic_adapter import AnthropicAdapter

    adapter = AnthropicAdapter(api_key="sk-ant-test")
    mock_client: Any = FakeAsyncAnthropic()
    mock_client.messages.create = AsyncMock(side_effect=Exception("timeout"))
    adapter._client = mock_client

    import asyncio
    result = asyncio.run(adapter.check_connectivity())
    assert result is False


# ── Provider registration ──────────────────────────────────────────────────


class FakeAnthropicAdapter(ProviderBase):
    """Fake Anthropic adapter for registration testing."""

    name = "anthropic"
    _connectivity_model = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(api_key, base_url)

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
    """Build Settings with provider keys empty except those in *overrides*."""
    kwargs: dict = {
        "anthropic_api_key": "",
        "anthropic_base_url": "",
        "openai_api_key": "",
        "gemini_api_key": "",
        "deepseek_api_key": "",
        "moonshot_api_key": "",
        "zhipu_api_key": "",
        "qwen_api_key": "",
        "xiaomi_api_key": "",
        "minimax_api_key": "",
        "anthropic_compat_api_key": "",
        "anthropic_compat_base_url": "",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


@pytest.mark.asyncio
async def test_anthropic_registered_with_base_url(clean_registry):
    """Anthropic provider passes base_url to adapter when configured."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(
            anthropic_api_key="sk-ant-test",
            anthropic_base_url="https://proxy.example.com",
        )
        with patch("provider.anthropic_adapter.AnthropicAdapter", FakeAnthropicAdapter):
            init_providers(settings)

    provider = clean_registry.get("anthropic")
    assert provider is not None
    assert provider.base_url == "https://proxy.example.com"


@pytest.mark.asyncio
async def test_anthropic_compat_registered(clean_registry):
    """Anthropic-compat provider registers with custom name/base_url/model."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(
            anthropic_compat_api_key="sk-ant-compat",
            anthropic_compat_base_url="https://gateway.example.com",
            anthropic_compat_model="claude-opus-4",
        )
        with patch("provider.anthropic_adapter.AnthropicAdapter", FakeAnthropicAdapter):
            init_providers(settings)

    provider = clean_registry.get("anthropic_compat")
    assert provider is not None
    assert provider.name == "anthropic_compat"
    assert provider.base_url == "https://gateway.example.com"
    assert provider._connectivity_model == "claude-opus-4"


@pytest.mark.asyncio
async def test_anthropic_compat_skipped_without_base_url(clean_registry):
    """Anthropic-compat provider is NOT registered when base_url is empty."""
    from provider.service import init_providers

    with patch("provider.service.registry", clean_registry):
        settings = _make_settings(
            anthropic_compat_api_key="sk-ant-compat",
            anthropic_compat_base_url="",  # missing
        )
        with patch("provider.anthropic_adapter.AnthropicAdapter", FakeAnthropicAdapter):
            init_providers(settings)

    assert clean_registry.get("anthropic_compat") is None


# ── Model routing ──────────────────────────────────────────────────────────


def test_resolve_anthropic_compat_models():
    """ac- prefixed models route to anthropic_compat provider."""
    from api_compat.router import _resolve_provider

    for model in ("ac-claude-sonnet-4", "ac-claude-opus-4", "ac-haiku"):
        prov, resolved = _resolve_provider(model)
        assert prov == "anthropic_compat", f"{model} → {prov}"
        assert resolved == model


def test_resolve_claude_still_anthropic():
    """claude- prefix still routes to 'anthropic' (not compat)."""
    from api_compat.router import _resolve_provider

    prov, _ = _resolve_provider("claude-sonnet-4-20250514")
    assert prov == "anthropic"
