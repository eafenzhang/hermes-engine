"""Health-check endpoint tests."""


def test_health_returns_ok(client):
    """GET /api/health should return 200 with status 'ok'."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_health_has_expected_fields(client):
    """Health response should contain all expected fields."""
    resp = client.get("/api/health")
    data = resp.json()
    for field in ("status", "version", "providers", "skills", "conversations", "memories"):
        assert field in data, f"Missing field: {field}"
