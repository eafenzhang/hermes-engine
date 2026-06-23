"""WebSocket event bus — domain.actionName event broadcast."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
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


class EventBus:
    """Simple in-memory pub/sub event bus for WebSocket broadcast."""

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
        """Dispatch event to local callbacks and all WebSocket clients."""
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

    async def publish_domain(
        self,
        domain: str,
        action: str,
        data: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> None:
        await self.publish(DomainEvent(domain, action, data, actor_id))


# Module-level singleton
bus: EventBus = EventBus()
