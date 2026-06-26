"""Idempotency — duplicate request detection via Idempotency-Key header."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class IdempotencyStore:
    """In-memory TTL store for idempotency keys → responses."""

    def __init__(self, ttl: float = 86400.0) -> None:  # 24h default
        self._ttl = ttl
        self._store: dict[str, tuple[float, bytes]] = {}

    def get(self, key: str) -> bytes | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        return data

    def set(self, key: str, data: bytes) -> None:
        self._store[key] = (time.time(), data)

    def cleanup(self) -> int:
        now = time.time()
        stale = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in stale:
            del self._store[k]
        return len(stale)


store = IdempotencyStore()


class IdempotencyMiddleware:
    """ASGI middleware: check Idempotency-Key, return cached response if duplicate."""

    _IDEMPOTENT_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        if method not in self._IDEMPOTENT_METHODS:
            await self.app(scope, receive, send)
            return

        # Extract header
        headers = dict(scope.get("headers", []))
        key_bytes = headers.get(b"idempotency-key", b"")
        if not key_bytes:
            await self.app(scope, receive, send)
            return

        key = key_bytes.decode("utf-8", errors="replace")
        cached = store.get(key)
        if cached is not None:
            # Replay cached response
            async def _replay(_receive):
                return {"type": "http.disconnect"}

            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-idempotency-key", key_bytes),
                    (b"x-cache", b"HIT"),
                ],
            })
            await send({"type": "http.response.body", "body": cached})
            return

        # First request — capture response body
        captured: list[bytes] = []

        async def _capture_send(event):
            if event["type"] == "http.response.body":
                captured.append(event.get("body", b""))
                store.set(key, b"".join(captured))
            await _orig_send(event)

        _orig_send = send
        await self.app(scope, receive, _capture_send)


# Starlette BaseHTTPMiddleware-style wrapper
class IdempotencyHTTPMiddleware:
    """Simpler ASGI approach for Starlette compatibility."""

    def __init__(self, app):
        self._inner = IdempotencyMiddleware(app)

    async def __call__(self, scope, receive, send):
        await self._inner(scope, receive, send)
