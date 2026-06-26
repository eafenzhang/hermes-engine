"""Session router — stateful multi-turn conversation endpoint.

Combines conversation persistence with agent turns:
``POST /api/sessions/{session_id}/chat`` automatically loads history,
appends new messages, runs the agent, and persists responses.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agent.schemas import AgentTurnRequest
from config.settings import Settings
from memory.curator import Curator
from shared.context_builder import build_context
from shared.dependencies import (
    get_agent_service,
    get_conversation_service,
    get_memory_service,
    get_skill_service,
)
from shared.event import bus
from shared.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("/{session_id}/chat")
async def session_chat(
    session_id: str,
    body: AgentTurnRequest,
    request: Request,
    service=Depends(get_agent_service),
    memory_service=Depends(get_memory_service),
    skill_service=Depends(get_skill_service),
    conv_service=Depends(get_conversation_service),
):
    """Stateful multi-turn chat — auto-loads and persists conversation history."""
    settings: Settings = request.app.state.settings

    conv = _load_or_create(body, session_id, conv_service)
    history = _build_history(body, session_id, conv_service, conv)

    enriched = await build_context(
        messages=history,
        memory_service=memory_service,
        skill_service=skill_service,
        data_dir=settings.data_dir if settings.user_context_enabled else None,
        conversation_service=conv_service if settings.session_enabled else None,
    )

    result = await service.chat(
        messages=history,
        provider=body.provider,
        model=body.model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        tools=body.tools,
        enriched_context=enriched or None,
        compress_context=settings.context_compression_enabled,
        compression_max_chars=settings.context_max_chars,
        compression_keep_last=settings.context_keep_last_messages,
    )

    _save_response(body, session_id, conv_service, result)

    await bus.publish_domain("agent", "turn.completed", data={"model": result.get("model")})
    Curator.record_message()
    try:
        if memory_service.curator.should_run():
            await memory_service.curator.run(use_llm=False)
    except Exception:
        logger.debug("Curator run in session endpoint failed", exc_info=True)

    return ApiResponse(data={**result, "session_id": session_id})


@router.post("/{session_id}/chat/stream")
async def session_chat_stream(
    session_id: str,
    body: AgentTurnRequest,
    request: Request,
    service=Depends(get_agent_service),
    conv_service=Depends(get_conversation_service),
    memory_service=Depends(get_memory_service),
    skill_service=Depends(get_skill_service),
):
    """Stateful streaming chat."""
    settings: Settings = request.app.state.settings

    conv = _load_or_create(body, session_id, conv_service)
    history = _build_history(body, session_id, conv_service, conv)

    enriched = await build_context(
        messages=history,
        memory_service=memory_service,
        skill_service=skill_service,
        conversation_service=conv_service if settings.session_enabled else None,
    )

    Curator.record_message()

    return StreamingResponse(
        service.chat_stream(
            messages=history,
            provider=body.provider,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            tools=body.tools,
            enriched_context=enriched or None,
            compress_context=settings.context_compression_enabled,
            compression_max_chars=settings.context_max_chars,
            compression_keep_last=settings.context_keep_last_messages,
        ),
        media_type="text/event-stream",
    )


@router.get("")
async def list_sessions(conv_service=Depends(get_conversation_service)):
    sessions, total = conv_service.list_conversations()
    return ApiResponse(data={"sessions": sessions, "total": total})


# ── Helpers ──────────────────────────────────────────────────────────────


def _extract_title(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            content = str(m.get("content", ""))[:60]
            return content if content else "New Session"
    return "New Session"


def _load_or_create(body, session_id, conv_service):
    conv = conv_service.get(session_id)
    if not conv:
        conv = conv_service.create(
            title=_extract_title(list(body.messages)),
            conv_id=session_id,
        )
    return conv


def _build_history(body, session_id, conv_service, conv):
    msgs, _ = conv_service.get_messages(session_id, limit=200)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in reversed(msgs)
    ][::-1]
    seen = {str(m.get("content", ""))[:80] for m in history}
    for m in body.messages:
        if str(m.get("content", ""))[:80] not in seen:
            history.append(m)
    for m in body.messages:
        if m.get("role") == "user":
            conv_service.add_message(session_id, role="user", content=str(m.get("content", "")))
    return history


def _save_response(body, session_id, conv_service, result):
    resp = result.get("content", "")
    if isinstance(resp, list):
        resp = " ".join(b.get("text", "") for b in resp if isinstance(b, dict))
    if resp:
        conv_service.add_message(session_id, role="assistant", content=str(resp))
