"""Model cache — TTL-based cache for provider model lists.

Avoids calling the upstream ``/models`` endpoint on every API request.
Cache entries expire after *ttl* seconds (configurable via
``HERMES_MODEL_CACHE_TTL``, default 300 s).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class ModelCache:
    """TTL-based cache for per-provider model lists.

    Usage::

        cache = ModelCache(ttl=300)
        models = cache.get("openai")
        if models is None:
            provider = registry.get("openai")
            models = await provider.list_models()
            cache.set("openai", models)
    """

    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def get(self, provider_name: str) -> list[dict[str, Any]] | None:
        """Return cached models for *provider_name*, or None if stale / absent."""
        entry = self._cache.get(provider_name)
        if entry is None:
            return None
        stored_at, models = entry
        if time.time() - stored_at >= self._ttl:
            self._cache.pop(provider_name, None)
            return None
        return models

    def set(self, provider_name: str, models: list[dict[str, Any]]) -> None:
        """Store *models* in the cache for *provider_name*."""
        self._cache[provider_name] = (time.time(), models)
        logger.debug("ModelCache: stored %d model(s) for '%s'", len(models), provider_name)

    def clear(self, provider_name: str | None = None) -> int:
        """Clear cached models.

        If *provider_name* is omitted, clears the entire cache. Returns
        the number of provider entries removed.
        """
        if provider_name is not None:
            existed = self._cache.pop(provider_name, None) is not None
            return 1 if existed else 0
        count = len(self._cache)
        self._cache.clear()
        logger.debug("ModelCache: cleared %d provider entry/entries", count)
        return count

    @property
    def ttl(self) -> float:
        return self._ttl


# Module-level singleton
model_cache: ModelCache = ModelCache()
