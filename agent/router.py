"""Agent REST router — chat endpoints with self-evolution integration.

Before each agent turn the router fetches relevant memories and skills,
building an enriched context that is injected into the system prompt.
After each turn it optionally synthesizes a memory from the exchange,
closing the self-evolution feedback loop.

Complex multi-tool tasks automatically generate reusable Skills —
the key self-evolution mechanism inherited from Hermes Agent.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agent.schemas import AgentTurnRequest
from config.settings import Settings
from memory.curator import Curator
from shared.context_builder import build_context
from shared.dependencies import get_agent_service, get_memory_service, get_skill_service, get_conversation_service
from shared.event import bus
from shared.memory_synthesizer import synthesize_memory
from shared.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

_SKILL_CREATE_PROMPT = (
    "Based on the following conversation where multiple tools were used, "
    "create a reusable Skill definition. Extract the workflow as clear "
    "step-by-step instructions.\n\n"
    "Respond with STRICT JSON only:\n"
    '{{"name": "kebab-case-name", "description": "one-liner", '
    '"content": "full markdown skill content", "tags": ["tag1", "tag2"]}}\n\n'
    "Conversation:\n{conversation_text}"
)


async def _maybe_auto_curate(memory_service) -> None:
    """Trigger curator after enough messages have accumulated.

    Runs as a fire-and-forget background task so the agent response is never
    delayed by curator work.  Failures are logged and silently swallowed —
    curation is advisory, not critical-path.
    """
    try:
        curator = memory_service.curator
        if curator.should_run():
            logger.info(
                "Auto-curator triggered after %d messages",
                Curator._global_message_count,
            )
            await curator.run(use_llm=curator.llm_provider is not None)
    except Exception:
        logger.exception("Auto-curator run failed — continuing")


async def _maybe_create_memory(
    messages: list,
    result: dict,
    memory_service,
) -> None:
    """Synthesize a memory from the turn and store it.

    Best-effort — failures are silently skipped.  Uses whichever provider
    answered the agent turn (falls back to the curator provider).
    """
    try:
        from shared.context_builder import _extract_user_query

        query = _extract_user_query(messages)
        response = result.get("content", "")
        if isinstance(response, list):
            response = " ".join(
                b.get("text", "") for b in response if isinstance(b, dict)
            )
        if not query or not str(response).strip():
            return

        model = result.get("model") or "claude-sonnet-4-20250514"
        # Guess provider from model name (simple heuristic)
        provider_name = "anthropic"
        if model.startswith("gpt") or model.startswith("o"):
            provider_name = "openai"
        elif model.startswith("gemini"):
            provider_name = "gemini"

        text = await synthesize_memory(
            query=query,
            response=str(response),
            provider_name=provider_name,
            model=model,
        )
        if text:
            memory_service.create_memory(
                content=text,
                source="agent-turn",
                scope="general",
                importance=1,
                tags=["auto", "conversation"],
            )
            logger.debug("Auto-created memory: %s", text[:80])
    except Exception:
        logger.debug("Memory synthesis skipped", exc_info=True)


def _count_tool_calls(result: dict) -> int:
    """Count tool_use blocks in the provider response content."""
    content = result.get("content", [])
    if not isinstance(content, list):
        return 0
    return sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")


async def _maybe_create_skill(
    messages: list,
    result: dict,
    skill_service,
    settings: Settings,
) -> None:
    """Auto-create a Skill after complex multi-tool tasks.

    When the agent used enough tools (>= min_tool_calls, default 5), the
    conversation + tool chain is sent to an LLM which extracts a reusable
    workflow as a SKILL.md file.  This is the primary self-evolution
    mechanism inherited from Hermes Agent.
    """
    if not settings.skill_auto_create_enabled:
        return

    tool_count = _count_tool_calls(result)
    if tool_count < settings.skill_auto_create_min_tool_calls:
        return

    try:
        # Build a text representation of the conversation
        lines: list[str] = []
        for m in messages[-20:]:  # last 20 messages max
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            lines.append(f"[{role}]: {str(content)[:300]}")
        conversation_text = "\n".join(lines)

        # Also include tool calls from the response
        response_content = result.get("content", [])
        if isinstance(response_content, list):
            for block in response_content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    lines.append(f"[tool_use:{tool_name}]: {str(tool_input)[:300]}")

        full_text = "\n".join(lines)

        # Use whichever provider answered the agent turn
        model = result.get("model") or "claude-sonnet-4-20250514"
        provider_name = "anthropic"
        if model.startswith("gpt") or model.startswith("o"):
            provider_name = "openai"
        elif model.startswith("gemini"):
            provider_name = "gemini"

        from provider.registry import registry

        provider = registry.get(provider_name)
        if provider is None:
            return

        prompt = _SKILL_CREATE_PROMPT.format(conversation_text=full_text)
        llm_result = await provider.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=1024,
            temperature=0.3,
        )

        content = llm_result.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )

        # Parse JSON response
        import json as _json
        data = _json.loads(str(content))

        skill_name = data.get("name", f"auto-skill-{tool_count}tools")
        skill_service.create(
            name=skill_name,
            description=data.get("description", "Auto-generated skill"),
            content=data.get("content", f"# {skill_name}\n\nAuto-generated from {tool_count} tool calls."),
            tags=data.get("tags", ["auto-generated"]),
            overwrite=True,
        )
        logger.info("Auto-created skill '%s' from %d tool calls", skill_name, tool_count)
        await bus.publish_domain("skill", "auto_created", data={"name": skill_name, "tool_calls": tool_count})

    except Exception:
        logger.debug("Skill auto-creation skipped", exc_info=True)


async def _maybe_patch_skill(
    result: dict,
    skill_service,
) -> None:
    """Auto-patch a Skill based on agent improvement suggestions.

    If the agent response explicitly suggests updating a skill (e.g.,
    "skill_manage patch skill-name"), this function extracts the old/new
    strings and applies the patch automatically.
    """
    try:
        import re

        content = result.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )
        text = str(content)

        # Match: "skill_manage patch <name>" followed by old/new blocks
        pattern = re.compile(
            r'skill_manage\s+patch\s+(\S+).*?'
            r'(?:old(?:[_:])?\s*["\x60]([^"\x60]+)["\x60]).*?'
            r'(?:new(?:[_:])?\s*["\x60]([^"\x60]+)["\x60])',
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            name = m.group(1)
            old_str = m.group(2)
            new_str = m.group(3)
            logger.info("Auto-patching skill '%s': %d → %d chars", name, len(old_str), len(new_str))
            from skill.patcher import SkillPatcher
            from pathlib import Path
            patcher = SkillPatcher(Path(skill_service.loader.skills_dir))
            try:
                patcher.patch(name, old_str, new_str)
            except Exception:
                logger.debug("Auto-patch failed for skill '%s'", name, exc_info=True)
    except Exception:
        logger.debug("Skill auto-patch skipped", exc_info=True)


@router.post("/chat")
async def chat(
    body: AgentTurnRequest,
    request: Request,
    service=Depends(get_agent_service),
    memory_service=Depends(get_memory_service),
    skill_service=Depends(get_skill_service),
    conv_service=Depends(get_conversation_service),
):
    """Execute an agent turn — returns response content (non-streaming).

    Relevant memories and skills are automatically injected into the
    system prompt, and key information from the exchange is persisted
    as a long-term memory after the turn completes.

    When ``conversation_id`` is set, the full conversation history is
    loaded from the database and merged with the incoming messages,
    enabling true multi-turn stateful chat.
    """
    settings: Settings = request.app.state.settings

    # ── Load conversation history if requested ──────────────────────────
    messages = list(body.messages)
    if body.conversation_id and settings.session_enabled:
        conv = conv_service.get(body.conversation_id)
        if conv:
            msgs, _ = conv_service.get_messages(body.conversation_id, limit=200)
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in reversed(msgs)
            ][::-1]
            seen = {str(m.get("content", ""))[:80] for m in history}
            for m in body.messages:
                if str(m.get("content", ""))[:80] not in seen:
                    history.append(m)
            messages = history
        else:
            title = str(body.messages[0].get("content", ""))[:60] if body.messages else "New"
            conv_service.create(title=title or "New Conversation", conv_id=body.conversation_id)

    # ── Build enriched context ──────────────────────────────────────────
    enriched = await build_context(
        messages=messages,
        memory_service=memory_service,
        skill_service=skill_service,
        data_dir=settings.data_dir if settings.user_context_enabled else None,
        conversation_service=conv_service if settings.session_enabled else None,
    )

    # ── Agent turn ──────────────────────────────────────────────────────
    result = await service.chat(
        messages=messages,
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

    # ── Persist messages if session is active ───────────────────────────
    if body.conversation_id and settings.session_enabled:
        for m in body.messages:
            if m.get("role") == "user":
                conv_service.add_message(
                    body.conversation_id, role="user",
                    content=str(m.get("content", "")),
                )
        resp = result.get("content", "")
        if isinstance(resp, list):
            resp = " ".join(b.get("text", "") for b in resp if isinstance(b, dict))
        if resp:
            conv_service.add_message(
                body.conversation_id, role="assistant", content=str(resp),
            )

    # ── Post-turn self-evolution ────────────────────────────────────────
    await bus.publish_domain("agent", "turn.completed", data={"model": result.get("model")})
    Curator.record_message()
    await _maybe_create_memory(messages, result, memory_service)
    await _maybe_create_skill(messages, result, skill_service, settings)
    await _maybe_patch_skill(result, skill_service)
    await _maybe_auto_curate(memory_service)

    return ApiResponse(data=result)


@router.post("/chat/stream")
async def chat_stream(
    body: AgentTurnRequest,
    request: Request,
    service=Depends(get_agent_service),
    memory_service=Depends(get_memory_service),
    skill_service=Depends(get_skill_service),
):
    """Execute an agent turn with SSE streaming.

    Relevant memories and skills are injected before the stream begins.
    Post-turn curation is scheduled but memory/skill synthesis is skipped
    for streaming turns (the full response text is not available ahead of
    time).
    """
    settings: Settings = request.app.state.settings

    enriched = await build_context(
        messages=body.messages,
        memory_service=memory_service,
        skill_service=skill_service,
        data_dir=settings.data_dir if settings.user_context_enabled else None,
    )

    Curator.record_message()
    await _maybe_auto_curate(memory_service)

    return StreamingResponse(
        service.chat_stream(
            messages=body.messages,
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
