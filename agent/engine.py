"""Agent Engine — orchestrates conversation loop + context engine.

Adapted from Hermes Agent's conversation_loop.py and context_engine.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator

from provider.registry import registry
from shared.errors import ServiceError

logger = logging.getLogger(__name__)

# Exceptions that are safe to catch and convert to SSE error events in the
# streaming path.  Deliberately excludes asyncio.CancelledError, KeyboardInterrupt,
# SystemExit, and GeneratorExit — those must propagate so the event loop and
# process can shut down cleanly.
try:
    import httpx
    _STREAMABLE_ERRORS: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        httpx.HTTPError,
    )
except ImportError:
    _STREAMABLE_ERRORS = (
        ConnectionError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
    )


class AgentEngine:
    """Core agent runtime — manages conversation turns, context, and streaming.

    Combines the Hermes conversation_loop (turn management) with context_engine
    (prompt construction) into a single orchestrator.
    """

    def __init__(
        self,
        default_provider: str = "anthropic",
        default_model: str = "claude-sonnet-4-20250514",
        system_prompt: str | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.system_prompt = system_prompt or self._build_default_system_prompt()

    @staticmethod
    def _build_default_system_prompt() -> str:
        """Build the default system prompt for the agent."""
        return (
            "You are Hermes Engine, a helpful AI assistant with self-evolution capabilities. "
            "You can use tools, manage memories, create skills, and maintain context across conversations. "
            "When given a task, think step by step and use available tools to accomplish it."
        )

    _build_system_prompt = _build_default_system_prompt  # back-compat alias

    async def run_turn(
        self,
        messages: list[dict[str, Any]],
        provider_name: str | None = None,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        enriched_context: str | None = None,
        compress_context: bool = False,
        compression_max_chars: int = 60000,
        compression_keep_last: int = 6,
    ) -> dict[str, Any]:
        """Execute a single conversation turn (non-streaming).

        *enriched_context* is optional extra content injected into the system
        prompt (e.g. relevant memories and skills built by the router layer).

        When *compress_context* is True and the message list exceeds
        *compression_max_chars* characters, middle turns are lossy-summarised
        via an LLM call before this turn executes.

        Raises ServiceError when the provider is unavailable or the call fails.
        """
        provider_name = provider_name or self.default_provider
        model = model or self.default_model

        provider = registry.get(provider_name)
        if not provider:
            raise ServiceError(
                f"Provider '{provider_name}' not available",
                code="PROVIDER_UNAVAILABLE",
            )

        # ── Context compression (before enrichment) ──────────────────────
        if compress_context:
            from shared.context_compressor import compress_messages
            messages = await compress_messages(
                messages,
                provider_name=provider_name,
                model=model,
                max_chars=compression_max_chars,
                keep_last=compression_keep_last,
            )

        full_messages = self._prepare_messages(messages, enriched_context)

        # ── Circuit breaker check ────────────────────────────────────────
        from shared.circuit_breaker import circuits
        breaker = circuits.get(provider_name)
        if not breaker.allow_request():
            # Try fallback chain
            fallback_chain_str = os.environ.get("HERMES_FALLBACK_CHAIN", "")
            if fallback_chain_str:
                from provider.fallback import try_with_fallback, build_fallback_chain
                chain = build_fallback_chain(fallback_chain_str, model or "")
                logger.info(
                    "Circuit %s OPEN, trying fallback chain: %s",
                    provider_name, chain,
                )
                return (await try_with_fallback(
                    full_messages, chain, tools, temperature, max_tokens,
                ))[0]
            raise ServiceError(
                f"Provider '{provider_name}' circuit is OPEN and no fallback configured",
                code="CIRCUIT_OPEN",
            )

        try:
            result = await provider.chat_completion(
                messages=full_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
            breaker.record_success()
        except ServiceError:
            breaker.record_failure()
            raise
        except Exception as exc:
            breaker.record_failure()
            logger.exception("Provider '%s' call failed", provider_name)
            # Try model fallback
            model_fallback_str = os.environ.get("HERMES_MODEL_FALLBACK_CHAIN", "")
            if model_fallback_str:
                from provider.model_fallback import try_model_fallback
                try:
                    return await try_model_fallback(
                        full_messages, provider_name,
                        model_fallback_str.split(","), tools, temperature, max_tokens,
                    )
                except Exception:
                    pass
            raise ServiceError(
                f"Provider call failed: {exc}",
                code="PROVIDER_ERROR",
            ) from exc

        return result

    async def run_turn_stream(
        self,
        messages: list[dict[str, Any]],
        provider_name: str | None = None,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        enriched_context: str | None = None,
        compress_context: bool = False,
        compression_max_chars: int = 60000,
        compression_keep_last: int = 6,
    ) -> AsyncIterator[str]:
        """Execute a single conversation turn (SSE streaming).

        Errors are yielded as SSE error events rather than raised, so the
        stream remains consumable by the client.
        """
        provider_name = provider_name or self.default_provider
        model = model or self.default_model

        provider = registry.get(provider_name)
        if not provider:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Provider {provider_name} not available'})}\n\n"
            return

        # ── Context compression (before enrichment) ──────────────────────
        if compress_context:
            from shared.context_compressor import compress_messages
            messages = await compress_messages(
                messages,
                provider_name=provider_name,
                model=model,
                max_chars=compression_max_chars,
                keep_last=compression_keep_last,
            )

        full_messages = self._prepare_messages(messages, enriched_context)

        try:
            async for chunk in provider.chat_completion_stream(  # type: ignore[attr-defined]
                messages=full_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            ):
                yield chunk
        except (ServiceError,) + _STREAMABLE_ERRORS as exc:
            logger.exception("Provider '%s' stream call failed", provider_name)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Provider error: {exc}'})}\n\n"

    def _prepare_messages(
        self,
        messages: list[dict[str, Any]],
        enriched_context: str | None = None,
    ) -> list[dict[str, Any]]:
        """Ensure system prompt is present, with optional enriched context.

        When *enriched_context* is provided, it is appended to the system
        prompt so the agent can draw on relevant memories and skills.
        """
        system = self.system_prompt
        if enriched_context:
            system = system + "\n\n" + enriched_context
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            return [{"role": "system", "content": system}, *messages]
        return messages
