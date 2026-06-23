"""Agent REST router — streaming chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.schemas import AgentTurnRequest
from shared.event import bus
from shared.models import ApiResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])

agent_service: "AgentService | None" = None  # noqa: F821


def _get_service():
    assert agent_service is not None, "agent_service not initialized"
    return agent_service


@router.post("/chat")
async def chat(body: AgentTurnRequest):
    """Execute an agent turn — returns response content (non-streaming)."""
    svc = _get_service()
    result = await svc.chat(
        messages=body.messages,
        provider=body.provider,
        model=body.model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        tools=body.tools,
    )
    await bus.publish_domain("agent", "turn.completed", data={"model": result.get("model")})
    return ApiResponse(data=result)


@router.post("/chat/stream")
async def chat_stream(body: AgentTurnRequest):
    """Execute an agent turn with SSE streaming."""
    svc = _get_service()
    return StreamingResponse(
        svc.chat_stream(
            messages=body.messages,
            provider=body.provider,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            tools=body.tools,
        ),
        media_type="text/event-stream",
    )
