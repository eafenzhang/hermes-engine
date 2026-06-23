"""Memory CRUD + FTS5 search + curator tests."""


def test_create_memory(client):
    """POST /api/memories → 200 + memory with id."""
    resp = client.post("/api/memories", json={
        "content": "The quick brown fox jumps over the lazy dog",
        "source": "test",
        "importance": 3,
        "tags": ["test", "example"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["id"]
    assert data["content"] == "The quick brown fox jumps over the lazy dog"
    assert data["importance"] == 3


def test_list_memories_empty(client):
    """GET /api/memories initially returns empty list."""
    resp = client.get("/api/memories")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []


def test_list_memories_with_data(client):
    """After creating memories, list should return them."""
    client.post("/api/memories", json={"content": "Memory A", "tags": ["a"]})
    client.post("/api/memories", json={"content": "Memory B", "tags": ["b"]})

    resp = client.get("/api/memories")
    body = resp.json()
    assert body["total"] == 2
    assert len(body["data"]) == 2


def test_get_memory_by_id(client):
    """GET /api/memories/{id} returns the correct memory."""
    create = client.post("/api/memories", json={"content": "Specific memory"})
    mid = create.json()["data"]["id"]

    resp = client.get(f"/api/memories/{mid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "Specific memory"


def test_get_memory_not_found(client):
    """GET /api/memories/{nonexistent} → 404."""
    resp = client.get("/api/memories/nonexistent-id")
    assert resp.status_code == 404


def test_update_memory(client):
    """PUT /api/memories/{id} updates fields."""
    create = client.post("/api/memories", json={"content": "Old content", "importance": 1})
    mid = create.json()["data"]["id"]

    resp = client.put(f"/api/memories/{mid}", json={"content": "Updated content", "importance": 5})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["content"] == "Updated content"
    assert data["importance"] == 5


def test_delete_memory(client):
    """DELETE /api/memories/{id} removes memory."""
    create = client.post("/api/memories", json={"content": "To delete"})
    mid = create.json()["data"]["id"]

    resp = client.delete(f"/api/memories/{mid}")
    assert resp.status_code == 200

    get_resp = client.get(f"/api/memories/{mid}")
    assert get_resp.status_code == 404


def test_search_memories_fts(client):
    """GET /api/memories/search?q=... returns FTS5 results."""
    client.post("/api/memories", json={
        "content": "Python is a programming language",
        "summary": "Python info",
        "tags": ["python"],
    })
    client.post("/api/memories", json={
        "content": "JavaScript is for web development",
        "tags": ["js"],
    })

    resp = client.get("/api/memories/search", params={"q": "python"})
    body = resp.json()
    assert body["total"] >= 1
    assert any("python" in m["content"].lower() for m in body["data"])


def test_search_memories_no_results(client):
    """FTS5 search with no match returns empty."""
    resp = client.get("/api/memories/search", params={"q": "zzzznotexist"})
    body = resp.json()
    assert body["total"] == 0


def test_memory_pagination(client):
    """List memories respects limit/offset pagination."""
    for i in range(10):
        client.post("/api/memories", json={"content": f"Memory {i}"})

    resp = client.get("/api/memories", params={"limit": 3, "offset": 0})
    body = resp.json()
    assert len(body["data"]) == 3
    assert body["total"] == 10
    assert body["page"] == 1


def test_curator_state(client):
    """GET /api/memories/curator/state returns curator config."""
    resp = client.get("/api/memories/curator/state")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "enabled" in data
    assert "interval_messages" in data
    assert "message_count" in data


def test_curator_run(client):
    """POST /api/memories/curator/run triggers curation cycle."""
    resp = client.post("/api/memories/curator/run")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "archived" in data
    assert "ran_at" in data
