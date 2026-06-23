"""Provider service — register, list, and dispatch chat requests."""

from __future__ import annotations

from provider.anthropic_adapter import AnthropicAdapter
from provider.openai_adapter import OpenAIAdapter
from provider.gemini_adapter import GeminiAdapter
from provider.registry import registry
from config.settings import Settings


def init_providers(settings: Settings) -> None:
    """Register all configured providers at startup."""
    if settings.anthropic_api_key:
        registry.register(
            AnthropicAdapter(api_key=settings.anthropic_api_key)
        )

    if settings.openai_api_key:
        registry.register(
            OpenAIAdapter(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        )

    if settings.gemini_api_key:
        registry.register(
            GeminiAdapter(api_key=settings.gemini_api_key)
        )
