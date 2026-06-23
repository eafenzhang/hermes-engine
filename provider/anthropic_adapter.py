"""Anthropic Messages API adapter for Hermes Engine.

Based on Hermes Agent's anthropic_adapter.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from anthropic import NOT_GIVEN
from anthropic import AsyncAnthropic

from provider.base import ProviderBase

logger = logging.getLogger(__name__)


class AnthropicAdapter(ProviderBase):
    """Provider adapter for Anthropic's Messages API."""

    name = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(api_key, base_url)
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = self._get_client()

        system_msg = None
        api_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_msg = m["content"]
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        params: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            params["system"] = system_msg
        if tools:
            params["tools"] = tools

        response = await client.messages.create(**params)  # type: ignore[arg-type]

        return {
            "id": response.id,
            "model": response.model,
            "role": "assistant",
            "content": [b.model_dump() for b in response.content],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "stop_reason": response.stop_reason,
        }

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()

        system_msg = None
        api_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_msg = m["content"]
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        params: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system_msg:
            params["system"] = system_msg
        if tools:
            params["tools"] = tools

        async with client.messages.stream(**params) as stream:  # type: ignore[arg-type]
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"

            final = await stream.get_final_message()
            # Emit usage info at the end
            yield f"data: {json.dumps({'type': 'done', 'usage': {'input_tokens': final.usage.input_tokens, 'output_tokens': final.usage.output_tokens}})}\n\n"

    async def check_connectivity(self) -> bool:
        client = self._get_client()
        try:
            await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
