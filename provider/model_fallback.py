"""Model fallback — try models within the same provider on failure."""

from __future__ import annotations

import logging
from typing import Any

from provider.registry import registry
from shared.errors import ServiceError

logger = logging.getLogger(__name__)


async def try_model_fallback(
    messages: list[dict[str, Any]],
    provider_name: str,
    model_chain: list[str],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Try each model on the same provider, return first success."""
    provider = registry.get(provider_name)
    if provider is None:
        raise ServiceError(
            f"Provider '{provider_name}' not available",
            code="PROVIDER_UNAVAILABLE",
        )

    last_error: Exception | None = None
    for i, model in enumerate(model_chain):
        try:
            result = await provider.chat_completion(
                messages=messages,
                model=model.strip(),
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.info("Model fallback: %s succeeded (attempt %d)", model, i + 1)
            return result
        except ServiceError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("Model fallback: %s failed (attempt %d): %s", model, i + 1, exc)

    raise ServiceError(
        f"All models failed. Last: {last_error}", code="PROVIDER_ERROR",
    )
