"""Tools executor + built-in tools tests."""


def test_list_tools(client):
    """GET /api/tools returns registered built-in tools."""
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    tools = resp.json()["data"]
    tool_names = [t["name"] for t in tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "execute_command" in tool_names


def test_read_file_not_found(client):
    """POST /api/tools/execute with read_file on nonexistent path returns error."""
    resp = client.post("/api/tools/execute", json={
        "name": "read_file",
        "arguments": {"path": "/nonexistent/path.txt"},
    })
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert "error" in result.lower() or "not found" in result.lower()


def test_execute_unknown_tool(client):
    """Executing an unregistered tool returns 404."""
    resp = client.post("/api/tools/execute", json={
        "name": "nonexistent_tool",
        "arguments": {},
    })
    assert resp.status_code == 404


def test_execute_multiple_tools(client):
    """POST /api/tools/execute-multiple runs sequential calls."""
    resp = client.post("/api/tools/execute-multiple", json={
        "calls": [
            {"name": "read_file", "arguments": {"path": "/nonexistent/a.txt"}},
            {"name": "read_file", "arguments": {"path": "/nonexistent/b.txt"}},
        ],
        "concurrent": False,
    })
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert len(results) == 2
    assert results[0]["tool"] == "read_file"
    assert results[1]["tool"] == "read_file"
