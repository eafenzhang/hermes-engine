"""OpenAI / compatible API adapter for Hermes Engine."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from provider.base import ProviderBase

logger = logging.getLogger(__name__)


class OpenAIAdapter(ProviderBase):
    """Provider adapter for OpenAI / compatible Chat Completions API."""

    name = "openai"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(api_key, base_url)
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url or "https://api.openai.com/v1",
            )
        return self._client

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = self._get_client()
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools

        response = await client.chat.completions.create(**params)  # type: ignore[arg-type]
        choice = response.choices[0]

        return {
            "id": response.id,
            "model": response.model,
            "role": "assistant",
            "content": choice.message.content or "",
            "tool_calls": [
                tc.model_dump() for tc in choice.message.tool_calls or []
            ],
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            "stop_reason": choice.finish_reason,
        }

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            params["tools"] = tools

        stream = await client.chat.completions.create(**params)  # type: ignore[arg-type]
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield f"data: {json.dumps({'type': 'text', 'content': delta.content})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    async def check_connectivity(self) -> bool:
        client = self._get_client()
        try:
            await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
