"""Provider abstraction — base class and common interfaces."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class ProviderBase(ABC):
    """Abstract base for a chat-completion provider."""

    name: str = "base"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Complete a chat (non‑streaming). Returns the final message dict."""
        ...

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat completion, yielding SSE‑friendly text chunks."""
        ...

    def validate_key(self) -> bool:
        """Return True if the configured API key looks valid."""
        return bool(self.api_key) and len(self.api_key) > 12

    async def check_connectivity(self) -> bool:
        """Lightweight connectivity check (e.g. list models or a trivial call)."""
        return self.validate_key()
