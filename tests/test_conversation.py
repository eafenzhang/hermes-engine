"""Conversation CRUD + message tests."""


def test_create_conversation(client):
    """POST /api/conversations → 200 with conversation."""
    resp = client.post("/api/conversations", json={
        "title": "Test Conversation",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"]
    assert data["title"] == "Test Conversation"
    assert data["message_count"] == 0


def test_list_conversations_empty(client):
    """GET /api/conversations initially empty."""
    resp = client.get("/api/conversations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


def test_list_conversations_with_data(client):
    """After creating conversations, list returns them."""
    client.post("/api/conversations", json={"title": "Chat 1"})
    client.post("/api/conversations", json={"title": "Chat 2"})

    resp = client.get("/api/conversations")
    assert resp.json()["total"] == 2


def test_get_conversation(client):
    """GET /api/conversations/{id} returns the conversation."""
    create = client.post("/api/conversations", json={"title": "Specific Chat"})
    cid = create.json()["data"]["id"]

    resp = client.get(f"/api/conversations/{cid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Specific Chat"


def test_get_conversation_not_found(client):
    """GET /api/conversations/{nonexistent} → 404."""
    resp = client.get("/api/conversations/nonexistent")
    assert resp.status_code == 404


def test_add_message(client):
    """POST /api/conversations/{id}/messages adds a message."""
    create = client.post("/api/conversations", json={"title": "Chat"})
    cid = create.json()["data"]["id"]

    resp = client.post(f"/api/conversations/{cid}/messages", json={
        "role": "user",
        "content": "Hello, Agent!",
    })
    assert resp.status_code == 200
    msg = resp.json()["data"]
    assert msg["role"] == "user"
    assert msg["content"] == "Hello, Agent!"
    assert msg["conversation_id"] == cid


def test_get_messages(client):
    """GET /api/conversations/{id}/messages returns messages in order."""
    create = client.post("/api/conversations", json={"title": "Chat"})
    cid = create.json()["data"]["id"]

    client.post(f"/api/conversations/{cid}/messages", json={"role": "user", "content": "Hi"})
    client.post(f"/api/conversations/{cid}/messages", json={"role": "assistant", "content": "Hello!"})

    resp = client.get(f"/api/conversations/{cid}/messages")
    body = resp.json()
    assert body["total"] == 2
    assert body["data"][0]["role"] == "user"
    assert body["data"][1]["role"] == "assistant"


def test_message_increments_count(client):
    """Adding messages increments conversation message_count."""
    create = client.post("/api/conversations", json={"title": "Chat"})
    cid = create.json()["data"]["id"]

    assert create.json()["data"]["message_count"] == 0
    client.post(f"/api/conversations/{cid}/messages", json={"role": "user", "content": "A"})
    client.post(f"/api/conversations/{cid}/messages", json={"role": "assistant", "content": "B"})

    get = client.get(f"/api/conversations/{cid}")
    assert get.json()["data"]["message_count"] == 2


def test_delete_conversation(client):
    """DELETE /api/conversations/{id} removes conversation and messages."""
    create = client.post("/api/conversations", json={"title": "To Delete"})
    cid = create.json()["data"]["id"]
    client.post(f"/api/conversations/{cid}/messages", json={"role": "user", "content": "X"})

    del_resp = client.delete(f"/api/conversations/{cid}")
    assert del_resp.status_code == 200

    get_resp = client.get(f"/api/conversations/{cid}")
    assert get_resp.status_code == 404
