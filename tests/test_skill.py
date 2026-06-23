"""Skill CRUD + scan + match tests."""


def test_list_skills_empty(client):
    """GET /api/skills returns empty list initially."""
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_create_skill(client):
    """POST /api/skills creates a skill file."""
    resp = client.post("/api/skills", json={
        "name": "test-skill",
        "description": "A test skill",
        "content": "def hello():\n    return 'world'",
        "tags": ["python", "test"],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "test-skill"
    assert data["description"] == "A test skill"


def test_get_skill(client):
    """GET /api/skills/{name} returns the skill."""
    client.post("/api/skills", json={
        "name": "my-skill",
        "description": "My custom skill",
        "content": "print('hello')",
    })

    resp = client.get("/api/skills/my-skill")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "my-skill"


def test_get_skill_not_found(client):
    """GET /api/skills/{nonexistent} → 404."""
    resp = client.get("/api/skills/nonexistent")
    assert resp.status_code == 404


def test_delete_skill(client):
    """DELETE /api/skills/{name} removes the skill."""
    client.post("/api/skills", json={
        "name": "temp-skill",
        "description": "Temp",
        "content": "x = 1",
    })
    resp = client.delete("/api/skills/temp-skill")
    assert resp.status_code == 200

    get_resp = client.get("/api/skills/temp-skill")
    assert get_resp.status_code == 404


def test_scan_skills(client):
    """POST /api/skills/scan discovers skill files on disk."""
    client.post("/api/skills", json={
        "name": "scannable-skill",
        "description": "Will be scanned",
        "content": "test data",
    })

    resp = client.post("/api/skills/scan")
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [s["name"] for s in data]
    assert "scannable-skill" in names


def test_match_skills_keyword(client):
    """POST /api/skills/match returns relevant skills by keyword."""
    client.post("/api/skills", json={
        "name": "file-reader",
        "description": "Read files from the filesystem",
        "content": "read file tool",
        "tags": ["file", "read"],
    })
    client.post("/api/skills", json={
        "name": "web-search",
        "description": "Search the web",
        "content": "web search",
        "tags": ["web", "search"],
    })

    client.post("/api/skills/scan")

    resp = client.post("/api/skills/match", json={
        "query": "read file",
        "top_k": 5,
    })
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert len(results) >= 1
    matched_names = [r["name"] for r in results]
    assert "file-reader" in matched_names
