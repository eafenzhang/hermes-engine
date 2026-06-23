"""Error handling tests — 404, validation, unhandled exceptions."""


def test_404_nonexistent_route(client):
    """GET on unknown route returns JSON error."""
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404


def test_memory_not_found(client):
    """Non-existent memory ID returns 404 with error code."""
    resp = client.get("/api/memories/no-such-id")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert "error" in body


def test_conversation_not_found(client):
    """Non-existent conversation ID returns 404."""
    resp = client.get("/api/conversations/no-such-id")
    assert resp.status_code == 404


def test_skill_not_found(client):
    """Non-existent skill name returns 404."""
    resp = client.get("/api/skills/no-such-skill")
    assert resp.status_code == 404


def test_tool_not_found(client):
    """Unknown tool call returns 404."""
    resp = client.post("/api/tools/execute", json={
        "name": "unknown_tool",
        "arguments": {},
    })
    assert resp.status_code == 404


def test_mcp_server_not_found(client):
    """Removing unknown MCP server returns 404."""
    resp = client.delete("/api/mcp/servers/ghost-server")
    assert resp.status_code == 404
