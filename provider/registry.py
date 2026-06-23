"""Provider registry — discover, register, and retrieve providers."""

from __future__ import annotations

import logging
from typing import Any

from provider.base import ProviderBase

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Singleton registry mapping provider names to their instances."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderBase] = {}

    def register(self, provider: ProviderBase) -> None:
        if provider.name in self._providers:
            logger.warning("Overwriting existing provider '%s'", provider.name)
        self._providers[provider.name] = provider
        logger.info("Registered provider '%s' (%s)", provider.name, type(provider).__name__)

    def get(self, name: str) -> ProviderBase | None:
        return self._providers.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "type": type(p).__name__,
                "connected": p.validate_key(),
            }
            for p in self._providers.values()
        ]

    def remove(self, name: str) -> bool:
        return self._providers.pop(name, None) is not None

    @property
    def count(self) -> int:
        return len(self._providers)


# Module-level singleton
registry: ProviderRegistry = ProviderRegistry()
