"""Tools service — delegates to the global executor."""

from __future__ import annotations

from typing import Any

from tools.executor import executor


class ToolService:
    """High-level tool operations."""

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        return await executor.execute(name, arguments)

    async def execute_multiple(self, calls: list[dict[str, Any]], concurrent: bool = False) -> list[dict[str, Any]]:
        return await executor.execute_multiple(calls, concurrent)

    def list_tools(self) -> list[dict[str, Any]]:
        return executor.list_tools()
