"""Agent REST router — streaming chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent.schemas import AgentTurnRequest
from shared.dependencies import get_agent_service
from shared.event import bus
from shared.models import ApiResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat")
async def chat(body: AgentTurnRequest, service=Depends(get_agent_service)):
    """Execute an agent turn — returns response content (non-streaming)."""
    result = await service.chat(
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
async def chat_stream(body: AgentTurnRequest, service=Depends(get_agent_service)):
    """Execute an agent turn with SSE streaming."""
    return StreamingResponse(
        service.chat_stream(
            messages=body.messages,
            provider=body.provider,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            tools=body.tools,
        ),
        media_type="text/event-stream",
    )
