"""MCP bridge — connects to external MCP servers as a client.

Allows Hermes Engine to use tools exposed by MCP servers.  Each server
connection has a configurable timeout, an automatic health status, and
structured error returns so callers can distinguish connect / timeout /
tool-not-found failures.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Represents a connection to a single MCP server."""

    def __init__(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._tools: list[dict[str, Any]] | None = None
        self._healthy: bool | None = None  # None = not yet checked

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    # ── Health check ──────────────────────────────────────────────────────

    async def check_health(self) -> dict[str, Any]:
        """Probe the server and return ``{healthy, url, error?}``.

        Attempts a lightweight ``GET /`` or falls back to ``POST /tools/list``
        if the root is not exposed.  The result is cached in ``_healthy``.
        """
        try:
            client = await self._get_client()
            try:
                resp = await client.get(f"{self.url}/")
                if resp.status_code < 500:
                    self._healthy = True
                    return {"healthy": True, "url": self.url}
            except httpx.HTTPError:
                pass

            # Root not exposed — try a minimal tools/list.
            resp = await client.post(
                f"{self.url}/tools/list", json={}, timeout=self.timeout
            )
            resp.raise_for_status()
            self._healthy = True
            return {"healthy": True, "url": self.url}
        except httpx.TimeoutException:
            self._healthy = False
            self._tools = None  # invalidate cached tools
            return {"healthy": False, "url": self.url, "error": "timeout"}
        except Exception as exc:
            self._healthy = False
            self._tools = None  # invalidate cached tools
            return {"healthy": False, "url": self.url, "error": str(exc)}

    @property
    def healthy(self) -> bool | None:
        return self._healthy

    # ── Tool operations ───────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch available tools from the MCP server."""
        if self._tools is not None and self._healthy is not False:
            return self._tools

        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.url}/tools/list", timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            self._tools = data.get("tools", data.get("result", {}).get("tools", []))
            self._healthy = True
            return self._tools or []
        except httpx.TimeoutException:
            self._healthy = False
            logger.warning("MCP server %s timed out listing tools", self.name)
            return []
        except httpx.HTTPStatusError as exc:
            self._healthy = False
            logger.warning(
                "MCP server %s returned %d listing tools", self.name, exc.response.status_code
            )
            return []
        except httpx.HTTPError as exc:
            self._healthy = False
            logger.warning("Failed to list MCP tools from %s: %s", self.url, exc)
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server.

        Returns a normalised result dict. On failure the dict contains an
        ``error`` key with a machine-readable ``code`` field so callers can
        distinguish error categories without string matching.
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.url}/tools/call",
                json={"name": name, "arguments": arguments},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            # Some MCP servers nest the result under "result" or "content".
            if "content" in data:
                return data
            if "result" in data:
                result = data["result"]
                return result if isinstance(result, dict) else {"result": result}
            return data
        except httpx.TimeoutException:
            return {"error": "Tool call timed out", "code": "timeout"}
        except httpx.ConnectError as exc:
            return {"error": f"Connection failed: {exc}", "code": "connect_error"}
        except httpx.HTTPStatusError as exc:
            body = ""
            with contextlib.suppress(Exception):
                body = exc.response.text[:200]
            return {
                "error": f"HTTP {exc.response.status_code}: {body}",
                "code": "http_error",
            }
        except httpx.HTTPError as exc:
            return {"error": f"Network error: {exc}", "code": "connect_error"}
        except Exception as exc:
            return {"error": str(exc), "code": "unknown_error"}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "healthy": self._healthy,
            "tool_count": len(self._tools) if self._tools else 0,
        }


class MCPBridge:
    """Manages multiple MCP server connections."""

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._servers: dict[str, MCPServerConnection] = {}
        self._pending_closes: list[asyncio.Task[None]] = []
        self.default_timeout = default_timeout

    def add_server(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> MCPServerConnection:
        conn = MCPServerConnection(
            name, url, headers, timeout=timeout or self.default_timeout
        )
        self._servers[name] = conn
        logger.info("Added MCP server '%s' at %s (timeout=%.1fs)", name, url, conn.timeout)
        return conn

    def remove_server(self, name: str) -> bool:
        conn = self._servers.pop(name, None)
        if conn:
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

    # ── Aggregate operations ───────────────────────────────────────────────

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """Aggregate tools from all connected MCP servers."""
        all_tools: list[dict[str, Any]] = []
        for name, conn in self._servers.items():
            # Skip unhealthy servers silently — they have no usable tools.
            if conn.healthy is False:
                continue
            tools = await conn.list_tools()
            for t in tools:
                t["_mcp_server"] = name
            all_tools.extend(tools)
        return all_tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        conn = self._servers.get(server_name)
        if not conn:
            return {"error": f"MCP server '{server_name}' not found", "code": "server_not_found"}
        return await conn.call_tool(tool_name, arguments)

    # ── Health ────────────────────────────────────────────────────────────

    async def check_server(self, name: str) -> dict[str, Any] | None:
        """Check a single server's health. Returns None if server unknown."""
        conn = self._servers.get(name)
        if not conn:
            return None
        return await conn.check_health()

    async def check_all_servers(self) -> list[dict[str, Any]]:
        """Probe every registered server and return health statuses."""
        results: list[dict[str, Any]] = []
        for name, conn in self._servers.items():
            health = await conn.check_health()
            health["name"] = name
            results.append(health)
        return results

    # ── Lifecycle ────────────────────────────────────────────────────────

    def list_servers(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._servers.values()]

    async def close_all(self) -> None:
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
