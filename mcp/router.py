"""MCP REST router."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from mcp.schemas import MCPServerCreate, MCPToolCall
from shared.dependencies import get_mcp_service
from shared.errors import NotFoundError
from shared.models import ApiResponse

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/servers")
async def list_servers(service=Depends(get_mcp_service)):
    return ApiResponse(data=service.list_servers())


@router.post("/servers")
async def add_server(body: MCPServerCreate, service=Depends(get_mcp_service)):
    result = service.add_server(body.name, body.url, body.headers)
    return ApiResponse(data=result, message="MCP server added")


@router.delete("/servers/{name}")
async def remove_server(name: str, service=Depends(get_mcp_service)):
    if not service.remove_server(name):
        raise NotFoundError(f"MCP server '{name}' not found")
    return ApiResponse(message="MCP server removed")


@router.get("/servers/{name}/health")
async def server_health(name: str, service=Depends(get_mcp_service)):
    result = await service.check_server(name)
    if result is None:
        raise NotFoundError(f"MCP server '{name}' not found")
    return ApiResponse(data=result)


@router.get("/health")
async def all_servers_health(service=Depends(get_mcp_service)):
    result = await service.check_all_servers()
    return ApiResponse(data=result)


@router.get("/tools")
async def list_mcp_tools(service=Depends(get_mcp_service)):
    tools = await service.list_all_tools()
    return ApiResponse(data=tools)


@router.post("/call")
async def call_mcp_tool(body: MCPToolCall, service=Depends(get_mcp_service)):
    result = await service.call_tool(body.server, body.tool, body.arguments)
    return ApiResponse(data=result)
