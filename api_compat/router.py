"""OpenAI-compatible /v1/chat/completions adapter.

Translates between the OpenAI Chat Completions wire format and Hermes
Engine's internal provider-agnostic format, so desktop agents such as
CodePilot, LobeChat, and LibreChat can use this engine as a drop-in
backend.

Provider is auto-selected from the requested model name (e.g. ``gpt-4``
→ OpenAI, ``claude-*`` → Anthropic, ``gemini-*`` → Gemini) with a
configurable default fallback.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent.engine import AgentEngine
from shared.dependencies import get_agent_service

from .schemas import ChatCompletionRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai-compat"])

# ── Model → provider auto-routing ───────────────────────────────────────
# First match wins; request model is lowercased before matching.
_MODEL_PROVIDER_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^claude"), "anthropic"),
    (re.compile(r"^gpt"), "openai"),
    (re.compile(r"^o\d"), "openai"),      # o1, o3, o4-mini
    (re.compile(r"^gemini"), "gemini"),
    (re.compile(r"^deepseek"), "openai"),  # DeepSeek uses OpenAI-compatible API
]


def _resolve_provider(requested_model: str, default_provider: str = "anthropic") -> tuple[str, str]:
    """Return ``(provider_name, model_name)`` from the OpenAI model string.

    The model is passed through unchanged in the *response* so that the
    client sees what it requested; the *provider* is chosen solely for
    routing behind the scenes.
    """
    lower = requested_model.lower()
    for pattern, provider in _MODEL_PROVIDER_RULES:
        if pattern.search(lower):
            return provider, requested_model
    return default_provider, requested_model


# ── Format conversion helpers ───────────────────────────────────────────


def _engine_tools_from_openai(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Convert OpenAI ``tools`` array to Hermes Engine tool descriptors."""
    if not tools:
        return None
    result: list[dict[str, Any]] = []
    for t in tools:
        fn = t.get("function", t)  # tolerate flat or nested shape
        result.append({
            "name": fn.get("name", "unknown"),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {}),
        })
    return result


def _openai_messages_from_engine(engine_msg: dict[str, Any]) -> dict[str, Any]:
    """Convert a Hermes Engine assistant message into OpenAI format.

    The engine returns ``content`` as a list of content *blocks* (text,
    tool_use, etc.).  We flatten the blocks into a single text string and
    extract any tool calls.
    """
    content_blocks = engine_msg.get("content", [])
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    if isinstance(content_blocks, list):
        for block in content_blocks:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            kind = block.get("type", "")
            if kind == "text":
                text_parts.append(block.get("text", ""))
            elif kind == "tool_use":
                tool_calls.append({
                    "id": block.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                    "type": "function",
                    "function": {
                        "name": block.get("name", "unknown"),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })
    elif isinstance(content_blocks, str):
        text_parts.append(content_blocks)

    msg: dict[str, Any] = {"role": "assistant"}
    content = "".join(text_parts)
    if content:
        msg["content"] = content
    else:
        msg["content"] = None
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _build_usage(input_t: int, output_t: int) -> dict[str, int]:
    return {
        "prompt_tokens": input_t,
        "completion_tokens": output_t,
        "total_tokens": input_t + output_t,
    }


# ── Non-streaming handler ───────────────────────────────────────────────


async def _handle_non_stream(
    body: ChatCompletionRequest,
    engine: AgentEngine,
) -> dict[str, Any]:
    """Process a non-streaming chat completion request."""
    provider_name, model = _resolve_provider(body.model)

    messages_raw = [m.model_dump(exclude_none=True) for m in body.messages]
    tools_raw = _engine_tools_from_openai(
        [t.model_dump(exclude_none=True) for t in body.tools] if body.tools else None
    )

    result = await engine.run_turn(
        messages=messages_raw,
        provider_name=provider_name,
        model=model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        tools=tools_raw,
    )

    now = int(time.time())
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"

    assistant_msg = _openai_messages_from_engine(result)
    usage = _build_usage(
        result.get("usage", {}).get("input_tokens", 0),
        result.get("usage", {}).get("output_tokens", 0),
    )

    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": now,
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": assistant_msg,
                "finish_reason": result.get("stop_reason", "stop"),
                "logprobs": None,
            }
        ],
        "usage": usage,
    }


# ── Streaming handler ───────────────────────────────────────────────────


async def _handle_stream(
    body: ChatCompletionRequest,
    engine: AgentEngine,
) -> AsyncIterator[str]:
    """Process a streaming chat completion, yielding SSE events."""
    provider_name, model = _resolve_provider(body.model)

    messages_raw = [m.model_dump(exclude_none=True) for m in body.messages]
    tools_raw = _engine_tools_from_openai(
        [t.model_dump(exclude_none=True) for t in body.tools] if body.tools else None
    )

    now = int(time.time())
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"

    # Initial chunk with role
    initial = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": now,
        "model": body.model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": None}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(initial, ensure_ascii=False)}\n\n"

    # Stream content from engine
    text_buffer = ""
    async for chunk in engine.run_turn_stream(
        messages=messages_raw,
        provider_name=provider_name,
        model=model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        tools=tools_raw,
    ):
        if not chunk:
            continue

        # Chunks come as "data: {...}\n\n" or plain JSON strings
        raw = chunk
        if isinstance(raw, str) and raw.startswith("data: "):
            raw = raw[6:].strip()

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue

        content = ""
        if isinstance(data, dict):
            ctype = data.get("type", "")
            if ctype == "text":
                content = data.get("content", "")
            elif ctype == "error":
                content = data.get("content", "")
        elif isinstance(data, str):
            content = data

        if content:
            text_buffer += content
            chunk_data = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": now,
                "model": body.model,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

    # Final chunk
    final = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": now,
        "model": body.model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ── Endpoint ────────────────────────────────────────────────────────────


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    agent_service=Depends(get_agent_service),
):
    """OpenAI-compatible chat completions endpoint.

    Accepts the standard OpenAI request schema and returns either a
    ``ChatCompletionResponse`` (non-streaming) or an SSE stream
    (streaming).  Provider is auto-routed from the requested model name.
    """
    engine: AgentEngine = agent_service.engine

    if body.stream:
        return StreamingResponse(
            _handle_stream(body, engine),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    result = await _handle_non_stream(body, engine)
    return result
