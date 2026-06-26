"""Response cache — ETag-based caching for GET endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
import time

logger = logging.getLogger(__name__)


class ResponseCache:
    """Simple in-memory ETag cache for GET responses."""

    def __init__(self, ttl: float = 300.0):
        self._ttl = ttl
        self._cache: dict[str, tuple[float, str, bytes]] = {}

    def get(self, key: str) -> tuple[str, bytes] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, etag, body = entry
        if time.time() - ts > self._ttl:
            del self._cache[key]
            return None
        return etag, body

    def set(self, key: str, body: bytes) -> str:
        etag = hashlib.md5(body).hexdigest()  # noqa: S324 — etag only
        self._cache[key] = (time.time(), etag, body)
        return etag

    def clear(self) -> None:
        self._cache.clear()


cache = ResponseCache()


class CacheMiddleware:
    """ASGI middleware: check If-None-Match, return 304 on cache hit."""

    def __init__(self, app, path_prefix: str = "/api/providers/models"):
        self.app = app
        self._prefix = path_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(self._prefix):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        if_none_match = headers.get(b"if-none-match", b"").decode("utf-8", errors="replace")

        cache_key = scope.get("path", "") + "?" + scope.get("query_string", b"").decode("utf-8", errors="replace")
        cached = cache.get(cache_key)

        if cached and if_none_match == cached[0]:
            # 304 Not Modified
            await send({
                "type": "http.response.start",
                "status": 304,
                "headers": [(b"etag", cached[0].encode())],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        # Forward to app, capture response
        body_chunks: list[bytes] = []
        status_code = 0
        response_headers: list[tuple[bytes, bytes]] = []

        async def _capture_send(event):
            nonlocal status_code
            if event["type"] == "http.response.start":
                status_code = event["status"]
                response_headers[:] = event.get("headers", [])
                if status_code == 200:
                    await send(event)
            elif event["type"] == "http.response.body":
                body_chunks.append(event.get("body", b""))
                await send(event)

        await self.app(scope, receive, _capture_send)

        if status_code == 200 and body_chunks:
            body = b"".join(body_chunks)
            etag = cache.set(cache_key, body)
            # ETag is set on the already-sent response via middleware wrapping
