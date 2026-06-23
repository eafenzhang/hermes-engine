"""MCP REST router."""

from __future__ import annotations

from fastapi import APIRouter

from mcp.schemas import MCPServerCreate, MCPToolCall
from shared.errors import NotFoundError
from shared.models import ApiResponse

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

mcp_service: "MCPService | None" = None  # noqa: F821


def _get_service():
    assert mcp_service is not None, "mcp_service not initialized"
    return mcp_service


@router.get("/servers")
async def list_servers():
    svc = _get_service()
    return ApiResponse(data=svc.list_servers())


@router.post("/servers")
async def add_server(body: MCPServerCreate):
    svc = _get_service()
    result = svc.add_server(body.name, body.url, body.headers)
    return ApiResponse(data=result, message="MCP server added")


@router.delete("/servers/{name}")
async def remove_server(name: str):
    svc = _get_service()
    if not svc.remove_server(name):
        raise NotFoundError(f"MCP server '{name}' not found")
    return ApiResponse(message="MCP server removed")


@router.get("/tools")
async def list_mcp_tools():
    svc = _get_service()
    tools = await svc.list_all_tools()
    return ApiResponse(data=tools)


@router.post("/call")
async def call_mcp_tool(body: MCPToolCall):
    svc = _get_service()
    result = await svc.call_tool(body.server, body.tool, body.arguments)
    return ApiResponse(data=result)
