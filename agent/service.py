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
    ) -> dict[str, Any]:
        return await self.engine.run_turn(
            messages=messages,
            provider_name=provider,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        async for chunk in self.engine.run_turn_stream(
            messages=messages,
            provider_name=provider,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk
