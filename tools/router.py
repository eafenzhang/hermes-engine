"""Tools REST router."""

from __future__ import annotations

from fastapi import APIRouter

from shared.event import bus
from shared.models import ApiResponse
from tools.schemas import ToolCallRequest, ToolExecuteRequest

router = APIRouter(prefix="/api/tools", tags=["tools"])

tool_service: "ToolService | None" = None  # noqa: F821


def _get_service():
    assert tool_service is not None, "tool_service not initialized"
    return tool_service


@router.get("")
async def list_tools():
    svc = _get_service()
    return ApiResponse(data=svc.list_tools())


@router.post("/execute")
async def execute_tool(body: ToolCallRequest):
    svc = _get_service()
    result = await svc.execute(name=body.name, arguments=body.arguments)
    await bus.publish_domain("tool", "executed", data={"tool": body.name})
    return ApiResponse(data=result)


@router.post("/execute-multiple")
async def execute_multiple(body: ToolExecuteRequest):
    svc = _get_service()
    calls = [{"name": c.name, "arguments": c.arguments} for c in body.calls]
    results = await svc.execute_multiple(calls, body.concurrent)
    return ApiResponse(data=results)
