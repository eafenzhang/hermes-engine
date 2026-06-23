"""MCP server management tests."""


def test_list_mcp_servers_empty(client):
    """GET /api/mcp/servers returns empty list."""
    resp = client.get("/api/mcp/servers")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_add_mcp_server(client):
    """POST /api/mcp/servers adds a new MCP server."""
    resp = client.post("/api/mcp/servers", json={
        "name": "test-mcp",
        "url": "http://localhost:9000",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "test-mcp"
    assert data["url"] == "http://localhost:9000"


def test_list_mcp_after_add(client):
    """After adding a server, list should include it."""
    client.post("/api/mcp/servers", json={
        "name": "my-server",
        "url": "http://localhost:9001",
    })
    resp = client.get("/api/mcp/servers")
    assert len(resp.json()["data"]) == 1


def test_remove_mcp_server(client):
    """DELETE /api/mcp/servers/{name} removes server."""
    client.post("/api/mcp/servers", json={"name": "temp", "url": "http://localhost:9002"})
    resp = client.delete("/api/mcp/servers/temp")
    assert resp.status_code == 200

    list_resp = client.get("/api/mcp/servers")
    assert len(list_resp.json()["data"]) == 0


def test_remove_nonexistent_server(client):
    """DELETE /api/mcp/servers/{nonexistent} → 404."""
    resp = client.delete("/api/mcp/servers/nonexistent")
    assert resp.status_code == 404


def test_list_mcp_tools_empty(client):
    """GET /api/mcp/tools returns empty when no servers connected."""
    resp = client.get("/api/mcp/tools")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
