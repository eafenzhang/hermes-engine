"""Tools REST router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from shared.dependencies import get_tool_service
from shared.event import bus
from shared.models import ApiResponse
from tools.schemas import ToolCallRequest, ToolExecuteRequest

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(service=Depends(get_tool_service)):
    return ApiResponse(data=service.list_tools())


@router.post("/execute")
async def execute_tool(body: ToolCallRequest, request: Request, service=Depends(get_tool_service)):
    settings = request.app.state.settings

    # ── Tool approval gate ───────────────────────────────────────────────
    if settings.tool_approval_enabled and body.name in settings.tool_approval_required_tools:
        from tools.approval import requires_approval
        needs, token = requires_approval(body.name, settings.tool_approval_required_tools)
        if needs and token:
            return ApiResponse(
                data={"approval_token": token, "tool": body.name},
                message="Approval required. POST /api/tools/approve/{token} to proceed.",
            )

    result = await service.execute(name=body.name, arguments=body.arguments)
    await bus.publish_domain("tool", "executed", data={"tool": body.name})
    return ApiResponse(data=result)


@router.post("/approve/{token}")
async def approve_tool(token: str, body: dict | None = None):
    """Approve a pending tool execution."""
    from tools.approval import approve
    entry = approve(token)
    if entry is None:
        return ApiResponse(data=None, message="Token invalid or expired")
    # Execute the approved tool
    from tools.service import ToolService
    svc = ToolService()
    result = await svc.execute(name=entry["name"], arguments=body or {})
    return ApiResponse(data=result, message="Tool executed (approved)")


@router.post("/execute-multiple")
async def execute_multiple(body: ToolExecuteRequest, service=Depends(get_tool_service)):
    calls = [{"name": c.name, "arguments": c.arguments} for c in body.calls]
    results = await service.execute_multiple(calls, body.concurrent)
    return ApiResponse(data=results)
