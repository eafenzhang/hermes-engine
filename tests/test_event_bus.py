"""EventBus backend abstraction tests.

Verifies the pluggable-backend design: the default in-memory backend fans
events out to multiple WebSocket clients, the bus can be constructed with an
explicit backend, and the Redis backend degrades gracefully when ``redis``
is not installed.
"""

from __future__ import annotations

import json

import pytest

from shared.event import (
    DomainEvent,
    EventBackend,
    EventBus,
    InMemoryEventBackend,
    RedisEventBackend,
)


class _FakeWS:
    """Minimal stand-in for fastapi.WebSocket — collects sent payloads."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


def test_default_bus_uses_in_memory_backend():
    """The module-level bus defaults to the in-memory backend."""
    from shared.event import bus

    assert isinstance(bus.backend, InMemoryEventBackend)


def test_bus_accepts_explicit_backend():
    """An EventBus can be wired with a custom backend."""
    backend = InMemoryEventBackend()
    eb = EventBus(backend=backend)
    assert eb.backend is backend


@pytest.mark.asyncio
async def test_inmemory_backend_broadcasts_to_multiple_clients():
    """One published event reaches every subscribed WebSocket client."""
    backend = InMemoryEventBackend()
    ws1, ws2 = _FakeWS(), _FakeWS()
    backend.subscribe_ws("c1", ws1)  # type: ignore[arg-type]
    backend.subscribe_ws("c2", ws2)  # type: ignore[arg-type]

    await backend.publish(DomainEvent("memory", "created", data={"memory_id": "x"}))

    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1
    evt = json.loads(ws1.sent[0])
    assert evt["event"] == "memory.created"
    assert evt["data"]["memory_id"] == "x"


@pytest.mark.asyncio
async def test_inmemory_backend_prunes_dead_connections():
    """A client whose send fails is dropped from the connection set."""
    backend = InMemoryEventBackend()

    class _DeadWS:
        async def send_text(self, payload: str) -> None:
            raise ConnectionError("client gone")

    backend.subscribe_ws("dead", _DeadWS())  # type: ignore[arg-type]
    await backend.publish(DomainEvent("memory", "created"))
    # The dead connection should have been pruned.
    assert "dead" not in backend._ws_connections


@pytest.mark.asyncio
async def test_inmemory_backend_invokes_local_callbacks():
    """Local (non-WS) subscribers receive the DomainEvent object directly."""
    backend = InMemoryEventBackend()
    received: list[DomainEvent] = []
    backend.subscribe("memory.created", received.append)

    evt = DomainEvent("memory", "created", data={"memory_id": "m1"})
    await backend.publish(evt)

    assert received == [evt]


@pytest.mark.asyncio
async def test_inmemory_backend_isolates_callback_failures():
    """A failing callback does not break the broadcast."""
    backend = InMemoryEventBackend()
    ws = _FakeWS()
    backend.subscribe_ws("c1", ws)  # type: ignore[arg-type]

    def _boom(_evt: DomainEvent) -> None:
        raise RuntimeError("callback exploded")

    backend.subscribe("memory.created", _boom)
    await backend.publish(DomainEvent("memory", "created"))

    # The WS client still received the event despite the callback error.
    assert len(ws.sent) == 1


@pytest.mark.asyncio
async def test_redis_backend_requires_redis_package(monkeypatch):
    """RedisEventBackend raises a clear error when ``redis`` is absent."""
    backend = RedisEventBackend()
    # Force the lazy import to fail.
    import builtins

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "redis.asyncio":
            raise ImportError("no redis")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    with pytest.raises(RuntimeError, match="requires the 'redis' package"):
        await backend.publish(DomainEvent("memory", "created"))


def test_event_backend_is_abstract():
    """EventBackend cannot be instantiated directly."""
    with pytest.raises(TypeError):
        EventBackend()  # type: ignore[abstract]
