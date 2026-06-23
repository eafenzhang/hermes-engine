"""WebSocket event bus tests."""

from __future__ import annotations

import json


def test_websocket_ping_pong(client):
    """WS ping → pong round-trip."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping")
        response = ws.receive_text()
        assert response == "pong"


def test_websocket_receives_memory_event(client):
    """Creating a memory should broadcast a memory.created event."""
    with client.websocket_connect("/ws") as ws:
        client.post("/api/memories", json={
            "content": "Event test memory",
        })

        response = ws.receive_text()
        event = json.loads(response)
        assert event["event"] == "memory.created"
        assert event["data"]["memory_id"]


def test_websocket_receives_conversation_event(client):
    """Creating a conversation should broadcast a conversation.created event."""
    with client.websocket_connect("/ws") as ws:
        client.post("/api/conversations", json={"title": "WS Test"})

        response = ws.receive_text()
        event = json.loads(response)
        assert event["event"] == "conversation.created"


def test_websocket_receives_skill_event(client):
    """Creating a skill should broadcast a skill.created event."""
    with client.websocket_connect("/ws") as ws:
        client.post("/api/skills", json={
            "name": "ws-skill",
            "description": "WS test skill",
            "content": "test",
        })

        response = ws.receive_text()
        event = json.loads(response)
        assert event["event"] == "skill.created"


def test_websocket_multiple_events(client):
    """Multiple REST actions produce multiple WS events in order."""
    with client.websocket_connect("/ws") as ws:
        client.post("/api/memories", json={"content": "First"})
        e1 = json.loads(ws.receive_text())
        assert e1["event"] == "memory.created"

        client.post("/api/conversations", json={"title": "Second"})
        e2 = json.loads(ws.receive_text())
        assert e2["event"] == "conversation.created"

        client.post("/api/memories", json={"content": "Third"})
        e3 = json.loads(ws.receive_text())
        assert e3["event"] == "memory.created"
