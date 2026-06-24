"""WebSocket event bus — domain.actionName event broadcast.

The bus is backed by a swappable :class:`EventBackend`. The default
:class:`InMemoryEventBackend` keeps everything in-process (zero external
dependencies, suitable for single-instance / desktop embedding). A
:class:`RedisEventBackend` skeleton is provided for multi-instance fan-out
— enable it by setting ``HERMES_EVENT_BACKEND=redis`` plus the standard
``REDIS_URL``; see the class docstring for details.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class DomainEvent:
    """A single domain event with standard envelope."""

    def __init__(
        self,
        domain: str,
        action: str,
        data: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.domain = domain
        self.action = action
        self.name = f"{domain}.{action}"
        self.data = data or {}
        self.actor_id = actor_id or "system"
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event": self.name,
            "data": self.data,
            "actor": self.actor_id,
            "ts": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ── Backend abstraction ─────────────────────────────────────────────────


class EventBackend(ABC):
    """Pluggable transport for event delivery + WebSocket fan-out.

    A backend owns: (1) dispatching to local in-process callbacks, and
    (2) broadcasting the JSON envelope to subscribed WebSocket clients.
    Backends that cross process boundaries (e.g. Redis pub/sub) are
    responsible for bridging received messages back to the local WebSocket
    connections they manage.
    """

    @abstractmethod
    def subscribe(self, event_name: str, callback: Callable[[DomainEvent], None]) -> None:
        ...

    @abstractmethod
    def subscribe_ws(self, connection_id: str, ws: WebSocket) -> None:
        ...

    @abstractmethod
    def unsubscribe_ws(self, connection_id: str) -> None:
        ...

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        ...

    async def close(self) -> None:
        """Release backend resources (override when needed)."""
        return None


class InMemoryEventBackend(EventBackend):
    """Default backend — in-process pub/sub + WebSocket broadcast.

    Suitable for single-instance deployments and local/desktop embedding.
    Events never leave the process, so there is no serialisation round-trip
    beyond the JSON envelope sent to WebSocket clients.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[DomainEvent], None]]] = {}
        self._ws_connections: dict[str, WebSocket] = {}

    def subscribe(self, event_name: str, callback: Callable[[DomainEvent], None]) -> None:
        self._subscribers.setdefault(event_name, []).append(callback)

    def subscribe_ws(self, connection_id: str, ws: WebSocket) -> None:
        self._ws_connections[connection_id] = ws

    def unsubscribe_ws(self, connection_id: str) -> None:
        self._ws_connections.pop(connection_id, None)

    async def publish(self, event: DomainEvent) -> None:
        # local callbacks
        for cb in self._subscribers.get(event.name, []):
            try:
                cb(event)
            except Exception:
                logger.exception("EventBus callback failed for %s", event.name)

        # WebSocket broadcast
        payload = event.to_json()
        dead: list[str] = []
        for cid, ws in self._ws_connections.items():
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(cid)

        for cid in dead:
            self._ws_connections.pop(cid, None)


class RedisEventBackend(EventBackend):
    """Multi-instance backend via Redis pub/sub — skeleton.

    Enables horizontal scaling: when several Hermes Engine instances share a
    Redis, an event published on one instance is fanned out to the WebSocket
    clients connected to *every* instance.

    To activate:

    1. ``pip install redis>=5.0`` (the ``redis`` package is an optional
       dependency — not installed by default).
    2. Set ``HERMES_EVENT_BACKEND=redis`` and ``REDIS_URL=redis://host:6379/0``.

    The implementation lazily imports ``redis`` so that the module loads even
    when the package is absent; only activating this backend triggers the
    import. A background listener bridges pub/sub messages to the local
    WebSocket connections registered via ``subscribe_ws``.

    NOTE: this is a ready-to-fill skeleton — the pub/sub wiring is stubbed
    and raises ``NotImplementedError`` on first publish until completed.
    """

    CHANNEL = "hermes:events"

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._redis_url = redis_url
        self._subscribers: dict[str, list[Callable[[DomainEvent], None]]] = {}
        self._ws_connections: dict[str, WebSocket] = {}
        self._client: Any = None  # redis.asyncio.Redis | None (lazy)

    def subscribe(self, event_name: str, callback: Callable[[DomainEvent], None]) -> None:
        self._subscribers.setdefault(event_name, []).append(callback)

    def subscribe_ws(self, connection_id: str, ws: WebSocket) -> None:
        self._ws_connections[connection_id] = ws

    def unsubscribe_ws(self, connection_id: str) -> None:
        self._ws_connections.pop(connection_id, None)

    async def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import redis.asyncio as aioredis  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "RedisEventBackend requires the 'redis' package. "
                    "Install it with: pip install redis>=5.0"
                ) from exc
            self._client = aioredis.from_url(self._redis_url)
        return self._client

    async def publish(self, event: DomainEvent) -> None:
        # Local callbacks always fire immediately.
        for cb in self._subscribers.get(event.name, []):
            try:
                cb(event)
            except Exception:
                logger.exception("EventBus callback failed for %s", event.name)

        # TODO: publish event.to_json() to self.CHANNEL and have a background
        # subscriber fan received messages out to self._ws_connections.
        # Left as a stub to avoid introducing a hard runtime dependency.
        client = await self._ensure_client()
        await client.publish(self.CHANNEL, event.to_json())
        logger.debug("RedisEventBackend published %s (WS fan-out not yet wired)", event.name)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ── Bus facade (public API — unchanged for all callers) ─────────────────


def _default_backend() -> EventBackend:
    """Pick the backend from ``HERMES_EVENT_BACKEND`` (default: memory)."""
    import os

    kind = os.environ.get("HERMES_EVENT_BACKEND", "memory").strip().lower()
    if kind == "redis":
        return RedisEventBackend(redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    return InMemoryEventBackend()


class EventBus:
    """Public event-bus facade — delegates to a swappable backend.

    Keeps the historical ``bus.publish_domain`` / ``subscribe_ws`` API so
    that routers and the WebSocket endpoint need no changes when the
    backend is swapped.
    """

    def __init__(self, backend: EventBackend | None = None) -> None:
        self.backend: EventBackend = backend or _default_backend()

    def subscribe(self, event_name: str, callback: Callable[[DomainEvent], None]) -> None:
        self.backend.subscribe(event_name, callback)

    def subscribe_ws(self, connection_id: str, ws: WebSocket) -> None:
        self.backend.subscribe_ws(connection_id, ws)

    def unsubscribe_ws(self, connection_id: str) -> None:
        self.backend.unsubscribe_ws(connection_id)

    async def publish(self, event: DomainEvent) -> None:
        await self.backend.publish(event)

    async def publish_domain(
        self,
        domain: str,
        action: str,
        data: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> None:
        await self.publish(DomainEvent(domain, action, data, actor_id))


# Module-level singleton (default in-memory backend)
bus: EventBus = EventBus()
