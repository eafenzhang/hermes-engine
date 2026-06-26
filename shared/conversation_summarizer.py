"""Conversation summarizer — LLM-powered summary when closing a conversation."""

from __future__ import annotations

import logging
from typing import Any

from provider.registry import registry

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "Create a concise summary of this conversation. Include: "
    "1) key topics discussed, 2) decisions made, 3) action items. "
    "Return 3-5 sentences maximum.\n\n"
    "Conversation:\n"
    "{conversation_text}"
)


async def summarize_conversation(
    messages: list[dict[str, Any]],
    provider_name: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
) -> str | None:
    """Generate a brief summary of a full conversation via LLM."""
    provider = registry.get(provider_name)
    if provider is None:
        return None

    text = []
    for m in messages[-30:]:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            from shared.utils import flatten_content as fc
            content = fc(content)
        text.append(f"[{role}]: {str(content)[:300]}")
    conversation_text = "\n".join(text)

    try:
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": _SUMMARY_PROMPT.format(conversation_text=conversation_text)}],
            model=model,
            max_tokens=300,
            temperature=0.3,
        )
        summary = result.get("content", "")
        if isinstance(summary, list):
            summary = " ".join(b.get("text", "") for b in summary if isinstance(b, dict))
        return str(summary).strip() or None
    except Exception:
        return None
