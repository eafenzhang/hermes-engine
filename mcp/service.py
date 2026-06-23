"""MCP service — delegates to the global MCP bridge."""

from __future__ import annotations

from typing import Any

from mcp.bridge import bridge


class MCPService:
    """High-level MCP operations."""

    def add_server(self, name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        conn = bridge.add_server(name, url, headers)
        return conn.to_dict()

    def remove_server(self, name: str) -> bool:
        return bridge.remove_server(name)

    def list_servers(self) -> list[dict[str, Any]]:
        return bridge.list_servers()

    async def list_all_tools(self) -> list[dict[str, Any]]:
        return await bridge.list_all_tools()

    async def call_tool(self, server: str, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        return await bridge.call_tool(server, tool, arguments or {})
