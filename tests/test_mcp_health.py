"""MCP bridge health / timeout / error-normalisation tests.

Uses ``httpx`` request mocks via ``unittest.mock.AsyncMock`` to simulate
unreachable, slow, and failing MCP servers without real network calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from mcp.bridge import MCPBridge, MCPServerConnection

# ── Health check ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_server_health_unknown():
    """MCPBridge.check_server returns None for unknown servers."""
    b = MCPBridge()
    assert await b.check_server("nope") is None


@pytest.mark.asyncio
async def test_server_health_when_reachable():
    """A responsive server is reported healthy."""
    conn = MCPServerConnection("ok", "http://localhost:9000", timeout=2.0)

    mock_client = AsyncMock()
    mock_client.get.return_value = httpx.Response(200, request=httpx.Request("GET", "http://x/"))
    conn._client = mock_client

    result = await conn.check_health()
    assert result["healthy"] is True
    assert conn.healthy is True


@pytest.mark.asyncio
async def test_server_health_when_timeout():
    """A server that times out is reported unhealthy with error code."""
    conn = MCPServerConnection("slow", "http://localhost:9001", timeout=2.0)

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectTimeout("timed out")
    mock_client.post.side_effect = httpx.ConnectTimeout("timed out")
    conn._client = mock_client

    result = await conn.check_health()
    assert result["healthy"] is False
    assert result["error"] == "timeout"
    assert conn.healthy is False


@pytest.mark.asyncio
async def test_server_health_connect_error():
    """A connection-refused server is reported unhealthy."""
    conn = MCPServerConnection("dead", "http://localhost:9999", timeout=2.0)

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("connection refused")
    mock_client.post.side_effect = httpx.ConnectError("connection refused")
    conn._client = mock_client

    result = await conn.check_health()
    assert result["healthy"] is False
    assert "connect" in result.get("error", "").lower() \
        or "refused" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_check_all_servers():
    """check_all_servers returns health for every registered server."""
    b = MCPBridge()

    c1 = MCPServerConnection("a", "http://a")
    c1._healthy = True
    c1._client = AsyncMock()
    c1._client.get.return_value = httpx.Response(200, request=httpx.Request("GET", "http://x/"))

    c2 = MCPServerConnection("b", "http://b")
    c2._client = AsyncMock()
    c2._client.get.side_effect = httpx.ConnectError("refused")
    c2._client.post.side_effect = httpx.ConnectError("refused")

    b._servers = {"a": c1, "b": c2}

    results = await b.check_all_servers()
    assert len(results) == 2
    by_name = {r["name"]: r for r in results}
    assert by_name["a"]["healthy"] is True
    assert by_name["b"]["healthy"] is False


# ── Timeout / error normalisation ───────────────────────────────────────


@pytest.mark.asyncio
async def test_call_tool_timeout():
    """Tool call that times out returns {error, code: timeout}."""
    conn = MCPServerConnection("slow", "http://slow", timeout=1.0)
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ReadTimeout("read timed out")
    conn._client = mock_client

    result = await conn.call_tool("do_thing", {})
    assert result.get("code") == "timeout"
    assert "timed out" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_call_tool_connect_error():
    """Tool call with connection failure returns {error, code: connect_error}."""
    conn = MCPServerConnection("dead", "http://dead", timeout=1.0)
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("refused")
    conn._client = mock_client

    result = await conn.call_tool("do_thing", {})
    assert result.get("code") == "connect_error"


@pytest.mark.asyncio
async def test_call_tool_http_error():
    """Tool call with HTTP 500 returns {error, code: http_error}."""
    mock_resp = httpx.Response(
        500, text="Internal Server Error",
        request=httpx.Request("POST", "http://x/tools/call"),
    )
    conn = MCPServerConnection("bad", "http://bad", timeout=1.0)
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    conn._client = mock_client

    result = await conn.call_tool("do_thing", {})
    assert result.get("code") == "http_error"
    assert "500" in result.get("error", "")


@pytest.mark.asyncio
async def test_call_tool_server_not_found():
    """Calling a tool on a non-existent server returns code server_not_found."""
    b = MCPBridge()
    result = await b.call_tool("ghost", "tool", {})
    assert result.get("code") == "server_not_found"


@pytest.mark.asyncio
async def test_call_tool_success_returns_content():
    """Successful call extracts nested content/result correctly."""
    for payload in [
        {"content": [{"type": "text", "text": "hello"}]},
        {"result": "value"},
        {"raw": "data"},
    ]:
        mock_resp = httpx.Response(
            200, json=payload,
            request=httpx.Request("POST", "http://x/tools/call"),
        )
        conn = MCPServerConnection("ok", "http://ok", timeout=1.0)
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        conn._client = mock_client

        result = await conn.call_tool("t", {})
        assert "error" not in result


# ── Unhealthy servers skipped in list_all_tools ─────────────────────────


@pytest.mark.asyncio
async def test_list_tools_skips_unhealthy():
    """Unhealthy servers are silently excluded from the tools aggregate."""
    b = MCPBridge()

    healthy_conn = MCPServerConnection("h", "http://h", timeout=1.0)
    healthy_conn._healthy = True
    healthy_conn._tools = [{"name": "tool_h"}]

    dead_conn = MCPServerConnection("d", "http://d", timeout=1.0)
    dead_conn._healthy = False

    b._servers = {"h": healthy_conn, "d": dead_conn}

    tools = await b.list_all_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "tool_h"
    assert tools[0]["_mcp_server"] == "h"


# ── to_dict includes health ─────────────────────────────────────────────


def test_server_to_dict_includes_healthy():
    """Server serialisation includes the health flag."""
    conn = MCPServerConnection("x", "http://x")
    conn._healthy = True
    d = conn.to_dict()
    assert d["healthy"] is True

    conn._healthy = False
    d = conn.to_dict()
    assert d["healthy"] is False

    conn._healthy = None
    d = conn.to_dict()
    assert d["healthy"] is None
