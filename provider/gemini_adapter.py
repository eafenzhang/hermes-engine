"""Gemini API adapter for Hermes Engine.

Based on Hermes Agent's gemini_native_adapter.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import asyncio

from google import genai
from google.genai import types as genai_types

from provider.base import ProviderBase

logger = logging.getLogger(__name__)


class GeminiAdapter(ProviderBase):
    """Provider adapter for Google Gemini API."""

    name = "gemini"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(api_key, base_url)
        self._client: genai.aio.Client | None = None

    def _get_client(self) -> genai.aio.Client:
        if self._client is None:
            self._client = genai.aio.Client(api_key=self.api_key)
        return self._client

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str = "gemini-2.0-flash",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = self._get_client()

        contents = []
        system_instruction = None
        for m in messages:
            if m.get("role") == "system":
                system_instruction = m["content"]
            else:
                role = "user" if m["role"] in ("user", "tool") else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])}],
                })

        genai_config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        response = await client.models.generate_content(
            model=model,
            contents=contents,
            config=genai_config,
        )

        return {
            "id": "",
            "model": model,
            "role": "assistant",
            "content": response.text or "",
            "usage": {
                "input_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
            },
            "stop_reason": response.candidates[0].finish_reason.name if response.candidates else "unknown",
        }

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str = "gemini-2.0-flash",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()

        contents = []
        system_instruction = None
        for m in messages:
            if m.get("role") == "system":
                system_instruction = m["content"]
            else:
                role = "user" if m["role"] in ("user", "tool") else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])}],
                })

        genai_config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        async for chunk in await client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=genai_config,
        ):
            if chunk.text:
                yield f"data: {json.dumps({'type': 'text', 'content': chunk.text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    async def check_connectivity(self) -> bool:
        client = self._get_client()
        try:
            await client.models.generate_content(
                model="gemini-2.0-flash",
                contents="ping",
                config=genai_types.GenerateContentConfig(max_output_tokens=1),
            )
            return True
        except Exception as exc:
            logger.debug("Gemini connectivity check failed: %s", exc)
            return False
