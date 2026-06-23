"""MCP bridge — connects to external MCP servers as a client.

Allows Hermes Engine to use tools exposed by MCP servers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Represents a connection to a single MCP server."""

    def __init__(self, name: str, url: str, headers: dict[str, str] | None = None) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None
        self._tools: list[dict[str, Any]] | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)
        return self._client

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch available tools from the MCP server."""
        if self._tools is not None:
            return self._tools

        client = await self._get_client()
        try:
            resp = await client.post(f"{self.url}/tools/list")
            resp.raise_for_status()
            data = resp.json()
            self._tools = data.get("tools", data.get("result", {}).get("tools", []))
            return self._tools or []
        except Exception as exc:
            logger.warning("Failed to list MCP tools from %s: %s", self.url, exc)
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.url}/tools/call",
                json={"name": name, "arguments": arguments},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"error": str(exc)}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "tool_count": len(self._tools) if self._tools else 0,
        }


class MCPBridge:
    """Manages multiple MCP server connections."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConnection] = {}
        # Track pending close tasks so they can be awaited in close_all().
        self._pending_closes: list[asyncio.Task[None]] = []

    def add_server(self, name: str, url: str, headers: dict[str, str] | None = None) -> MCPServerConnection:
        conn = MCPServerConnection(name, url, headers)
        self._servers[name] = conn
        logger.info("Added MCP server '%s' at %s", name, url)
        return conn

    def remove_server(self, name: str) -> bool:
        conn = self._servers.pop(name, None)
        if conn:
            # Prune already-completed tasks before appending
            self._pending_closes = [t for t in self._pending_closes if not t.done()]
            task = asyncio.create_task(self._close_connection(conn))
            self._pending_closes.append(task)
            return True
        return False

    async def _close_connection(self, conn: MCPServerConnection) -> None:
        try:
            await conn.close()
        except Exception:
            logger.exception("Error closing MCP connection %s", conn.name)

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """Aggregate tools from all connected MCP servers."""
        all_tools: list[dict[str, Any]] = []
        for name, conn in self._servers.items():
            tools = await conn.list_tools()
            for t in tools:
                t["_mcp_server"] = name
            all_tools.extend(tools)
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        conn = self._servers.get(server_name)
        if not conn:
            return {"error": f"MCP server '{server_name}' not found"}
        return await conn.call_tool(tool_name, arguments)

    def list_servers(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._servers.values()]

    async def close_all(self) -> None:
        # Await any pending closes from remove_server() calls first.
        if self._pending_closes:
            await asyncio.gather(*self._pending_closes, return_exceptions=True)
            self._pending_closes.clear()
        for conn in self._servers.values():
            try:
                await conn.close()
            except Exception:
                logger.exception("Error closing MCP connection %s", conn.name)
        self._servers.clear()


# Module-level singleton
bridge: MCPBridge = MCPBridge()
