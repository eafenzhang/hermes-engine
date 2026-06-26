"""Agent service — business logic for agent operations."""

from __future__ import annotations

from typing import Any, AsyncIterator

from agent.engine import AgentEngine


class AgentService:
    """High-level agent operations, wrapping the engine."""

    def __init__(self, engine: AgentEngine) -> None:
        self.engine = engine

    async def chat(
        self,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        enriched_context: str | None = None,
        compress_context: bool = False,
        compression_max_chars: int = 60000,
        compression_keep_last: int = 6,
    ) -> dict[str, Any]:
        return await self.engine.run_turn(
            messages=messages,
            provider_name=provider,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            enriched_context=enriched_context,
            compress_context=compress_context,
            compression_max_chars=compression_max_chars,
            compression_keep_last=compression_keep_last,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        enriched_context: str | None = None,
        compress_context: bool = False,
        compression_max_chars: int = 60000,
        compression_keep_last: int = 6,
    ) -> AsyncIterator[str]:
        async for chunk in self.engine.run_turn_stream(
            messages=messages,
            provider_name=provider,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            enriched_context=enriched_context,
            compress_context=compress_context,
            compression_max_chars=compression_max_chars,
            compression_keep_last=compression_keep_last,
        ):
            yield chunk
