"""Provider service — register, list, and dispatch chat requests."""

from __future__ import annotations

import logging

from provider.registry import registry
from config.settings import Settings

logger = logging.getLogger(__name__)


def init_providers(settings: Settings) -> None:
    """Register all configured providers at startup (lazy imports)."""
    if settings.anthropic_api_key:
        try:
            from provider.anthropic_adapter import AnthropicAdapter
            registry.register(AnthropicAdapter(api_key=settings.anthropic_api_key))
        except ImportError:
            logger.warning("anthropic SDK not installed; skipping Anthropic provider")

    if settings.openai_api_key:
        try:
            from provider.openai_adapter import OpenAIAdapter
            registry.register(
                OpenAIAdapter(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                )
            )
        except ImportError:
            logger.warning("openai SDK not installed; skipping OpenAI provider")

    if settings.gemini_api_key:
        try:
            from provider.gemini_adapter import GeminiAdapter
            registry.register(GeminiAdapter(api_key=settings.gemini_api_key))
        except ImportError:
            logger.warning("google-genai SDK not installed; skipping Gemini provider")
