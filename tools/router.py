"""Tools REST router."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shared.dependencies import get_tool_service
from shared.event import bus
from shared.models import ApiResponse
from tools.schemas import ToolCallRequest, ToolExecuteRequest

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(service=Depends(get_tool_service)):
    return ApiResponse(data=service.list_tools())


@router.post("/execute")
async def execute_tool(body: ToolCallRequest, service=Depends(get_tool_service)):
    result = await service.execute(name=body.name, arguments=body.arguments)
    await bus.publish_domain("tool", "executed", data={"tool": body.name})
    return ApiResponse(data=result)


@router.post("/execute-multiple")
async def execute_multiple(body: ToolExecuteRequest, service=Depends(get_tool_service)):
    calls = [{"name": c.name, "arguments": c.arguments} for c in body.calls]
    results = await service.execute_multiple(calls, body.concurrent)
    return ApiResponse(data=results)
