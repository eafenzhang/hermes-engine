"""Context compressor — lossy summarization of middle conversation turns.

When a conversation exceeds a configurable character threshold, the middle
turns (between the oldest system message and the most recent N messages) are
replaced with an LLM-generated summary.  This keeps the agent functional
during very long exchanges without token-overflow errors.

Adapted from Hermes Agent's context compression strategy.
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_COMPRESSION_PROMPT = (
    "Summarise the following conversation turns into a single paragraph that "
    "preserves key facts, decisions, tool outputs, and user preferences. "
    "Only return the summary paragraph, nothing else.\n\n"
    "Conversation:\n"
    "{conversation_text}"
)


def _message_char_count(messages: list[dict[str, Any]]) -> int:
    """Estimate total character count of a message list."""
    return sum(len(str(m)) for m in messages)


async def compress_messages(
    messages: list[dict[str, Any]],
    provider_name: str,
    model: str,
    max_chars: int = 60000,
    keep_last: int = 6,
) -> list[dict[str, Any]]:
    """Compress middle turns via LLM summarisation when over threshold.

    Returns the original *messages* unchanged when:
    - Total characters are under *max_chars*
    - There are too few messages to compress (<= keep_last + 2)
    - The provider is unavailable or the LLM call fails

    When compression is applied:
    1.  The system message (if present) stays at position 0
    2.  The oldest non-system messages are kept (context prefix)
    3.  The middle turns are replaced by a single ``[Conversation Summary]``
        synthetic system message
    4.  The most recent *keep_last* messages are kept intact

    The summary is generated via a cheap LLM call (low temperature, short
    output) so it adds minimal latency.
    """
    total_chars = _message_char_count(messages)
    if total_chars <= max_chars:
        return messages

    if len(messages) <= keep_last + 2:
        return messages  # not enough messages to compress meaningfully

    # Split: keep system + first few + last N
    has_system = messages[0].get("role") == "system"
    prefix_count = 1 if has_system else 0

    # Messages to compress: everything between prefix and the last keep_last
    middle_start = prefix_count
    middle_end = len(messages) - keep_last
    if middle_end <= middle_start:
        return messages

    middle_messages = messages[middle_start:middle_end]

    # Build a text representation of the middle conversation
    lines: list[str] = []
    for m in middle_messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )
        lines.append(f"[{role}]: {str(content)[:500]}")
    conversation_text = "\n".join(lines)

    # Try to summarise
    try:
        from provider.registry import registry

        provider = registry.get(provider_name)
        if provider is None:
            logger.debug("Compressor: provider '%s' not available, skipping", provider_name)
            return messages

        prompt = _COMPRESSION_PROMPT.format(conversation_text=conversation_text)
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=400,
            temperature=0.2,
        )

        summary_content = result.get("content", "")
        if isinstance(summary_content, list):
            summary_content = " ".join(
                b.get("text", "") for b in summary_content if isinstance(b, dict)
            )
        summary = str(summary_content).strip()

        if not summary or len(summary) < 10:
            logger.debug("Compressor: summary too short, keeping original messages")
            return messages

        # Build compressed message list
        compressed: list[dict[str, Any]] = []

        # System message (or first prefix messages) stay
        if prefix_count > 0:
            compressed.append(messages[0])

        # Inject summary as a synthetic message
        compressed.append({
            "role": "user",
            "content": f"[Conversation Summary]\n{summary}",
        })

        # Keep the last N messages
        compressed.extend(messages[middle_end:])

        new_chars = _message_char_count(compressed)
        logger.info(
            "Context compressed: %d → %d messages, %d → %d chars",
            len(messages), len(compressed), total_chars, new_chars,
        )
        return compressed

    except Exception:
        logger.debug("Compressor: summarisation call failed, keeping original", exc_info=True)
        return messages
