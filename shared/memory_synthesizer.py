"""Memory synthesizer — extract long-term memories from conversation turns.

After each agent turn, the router can optionally call :func:`synthesize_memory`
to extract a concise one-sentence memory from the exchange.  This closes the
self-evolution loop: conversations feed back into the memory store, and the
context builder retrieves them for future turns.
"""

from __future__ import annotations

import logging
from typing import Any

from provider.registry import registry

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = (
    "Extract the key information from this conversation turn as a single "
    "concise sentence suitable for long-term memory. Include specific facts, "
    "decisions, preferences, or context that would be useful in future "
    "conversations. Return ONLY the sentence, no labels or prefixes.\n\n"
    "User query: {query}\n\nAssistant response: {response}"
)


async def synthesize_memory(
    query: str,
    response: str,
    provider_name: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
) -> str | None:
    """Use an LLM to extract a one-sentence memory from a conversation turn.

    Returns the memory text, or ``None`` when no provider is available or
    the call fails.  This is a best-effort operation — failures are logged
    and swallowed, never raising.
    """
    provider = registry.get(provider_name)
    if provider is None:
        logger.debug("Memory synthesis skipped — provider '%s' not available", provider_name)
        return None

    prompt = _SYNTHESIS_PROMPT.format(query=query, response=response[:1500])

    try:
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=200,
            temperature=0.3,
        )
    except Exception:
        logger.debug("Memory synthesis call failed", exc_info=True)
        return None

    # Handle both text and content-block response formats
    content: Any = result.get("content", "")
    if isinstance(content, list):
        content = " ".join(
            b.get("text", "") for b in content if isinstance(b, dict)
        )
    text = str(content).strip()

    if not text or len(text) < 3:
        return None

    return text
