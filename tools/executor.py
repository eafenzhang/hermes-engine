"""Tool executor — dispatches tool calls to built-in or MCP tools.

Adapted from Hermes Agent's tool_executor.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

from shared.errors import ServiceError

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Dispatches tool-call requests to registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._builtin_tools: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        schema: dict[str, Any],
    ) -> None:
        """Register a tool by name with its handler and JSON schema."""
        self._handlers[name] = handler
        self._builtin_tools[name] = {
            "name": name,
            "description": schema.get("description", ""),
            "input_schema": schema.get("input_schema", schema),
        }
        logger.info("Registered tool '%s'", name)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute a single tool call and return the result."""
        handler = self._handlers.get(tool_name)
        if not handler:
            raise ServiceError(f"Unknown tool: '{tool_name}'", code="TOOL_NOT_FOUND", http_status=404)
        try:
            result = await handler(**arguments)
            return result
        except Exception as exc:
            logger.exception("Tool '%s' failed", tool_name)
            return {"error": str(exc)}

    async def execute_multiple(
        self,
        calls: list[dict[str, Any]],
        concurrent: bool = False,
    ) -> list[dict[str, Any]]:
        """Execute multiple tool calls sequentially or concurrently."""
        if concurrent:
            tasks = [self.execute(c["name"], c.get("arguments", {})) for c in calls]
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            return [
                {"tool": c["name"], "result": r if not isinstance(r, Exception) else str(r)}
                for c, r in zip(calls, gathered)
            ]
        else:
            results: list[dict[str, Any]] = []
            for call in calls:
                r = await self.execute(call["name"], call.get("arguments", {}))
                results.append({"tool": call["name"], "result": r})
            return results

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._builtin_tools.values())

    def get_openai_tool_schemas(self) -> list[dict[str, Any]]:
        """Return tool schemas in OpenAI-compatible format for provider calls."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in self._builtin_tools.values()
        ]


# Module-level singleton
executor: ToolExecutor = ToolExecutor()
