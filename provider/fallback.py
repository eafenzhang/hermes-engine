"""Provider fallback — try providers in order on failure or circuit open."""

from __future__ import annotations

import logging
from typing import Any

from provider.registry import registry
from shared.circuit_breaker import circuits
from shared.errors import ServiceError

logger = logging.getLogger(__name__)


async def try_with_fallback(
    messages: list[dict[str, Any]],
    fallback_chain: list[tuple[str, str]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[dict[str, Any], str, str]:
    """Try each (provider, model) in chain, return first successful result.

    Raises ServiceError with code PROVIDER_UNAVAILABLE when all fail.

    Returns: (result, provider_name, model)
    """
    last_error: Exception | None = None

    for i, (provider_name, model) in enumerate(fallback_chain):
        breaker = circuits.get(provider_name)

        if not breaker.allow_request():
            logger.warning(
                "Fallback chain: skipping %s (circuit OPEN)", provider_name,
            )
            continue

        provider = registry.get(provider_name)
        if provider is None:
            logger.debug("Fallback: %s not registered, skipping", provider_name)
            continue

        try:
            result = await provider.chat_completion(
                messages=messages,
                model=model,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            breaker.record_success()
            logger.info("Fallback: %s/%s succeeded (attempt %d)", provider_name, model, i + 1)
            return result, provider_name, model
        except ServiceError:
            raise  # domain errors propagate
        except Exception as exc:
            breaker.record_failure()
            last_error = exc
            logger.warning(
                "Fallback: %s/%s failed (attempt %d): %s",
                provider_name, model, i + 1, exc,
            )

    raise ServiceError(
        f"All providers in fallback chain failed. Last error: {last_error}",
        code="PROVIDER_UNAVAILABLE",
    )


def build_fallback_chain(chain_str: str, default_model: str = "") -> list[tuple[str, str]]:
    """Parse fallback chain from comma-separated config string.

    Formats:
        "anthropic:claude-sonnet-4,openai:gpt-4o"  → explicit models
        "anthropic,openai" → uses default_model
    """
    chain: list[tuple[str, str]] = []
    for item in chain_str.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            prov, model = item.split(":", 1)
            chain.append((prov.strip(), model.strip()))
        else:
            chain.append((item, default_model or "claude-sonnet-4-20250514"))
    return chain
