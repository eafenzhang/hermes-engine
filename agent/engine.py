"""Agent Engine — orchestrates conversation loop + context engine.

Adapted from Hermes Agent's conversation_loop.py and context_engine.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from provider.registry import registry
from shared.errors import ServiceError

logger = logging.getLogger(__name__)


class AgentEngine:
    """Core agent runtime — manages conversation turns, context, and streaming.

    Combines the Hermes conversation_loop (turn management) with context_engine
    (prompt construction) into a single orchestrator.
    """

    def __init__(
        self,
        default_provider: str = "anthropic",
        default_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the core system prompt for the agent."""
        return (
            "You are Hermes Engine, a helpful AI assistant with self-evolution capabilities. "
            "You can use tools, manage memories, create skills, and maintain context across conversations. "
            "When given a task, think step by step and use available tools to accomplish it."
        )

    async def run_turn(
        self,
        messages: list[dict[str, Any]],
        provider_name: str | None = None,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Execute a single conversation turn (non-streaming)."""
        provider_name = provider_name or self.default_provider
        model = model or self.default_model

        provider = registry.get(provider_name)
        if not provider:
            raise ServiceError(f"Provider '{provider_name}' not available")

        # Inject system prompt if not present
        full_messages = self._prepare_messages(messages)

        result = await provider.chat_completion(
            messages=full_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

        return result

    async def run_turn_stream(
        self,
        messages: list[dict[str, Any]],
        provider_name: str | None = None,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Execute a single conversation turn (SSE streaming)."""
        provider_name = provider_name or self.default_provider
        model = model or self.default_model

        provider = registry.get(provider_name)
        if not provider:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Provider {provider_name} not available'})}\n\n"
            return

        full_messages = self._prepare_messages(messages)

        async for chunk in provider.chat_completion_stream(
            messages=full_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        ):
            yield chunk

    def _prepare_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ensure system prompt is present in the message list."""
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            return [{"role": "system", "content": self.system_prompt}, *messages]
        return messages
