"""Context builder — enriches agent system prompt with relevant memories and skills.

This is the key integration point for self-evolution: every agent turn
automatically retrieves relevant long-term memories and matching skills,
injecting them into the system prompt so the agent can draw on past
knowledge without the caller having to manage it manually.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_MEMORIES = 5
_MAX_SKILLS = 3


def _extract_user_query(messages: list[dict[str, Any]]) -> str:
    """Extract the last user message from the message list as the search query."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # Anthropic-style content blocks — join text parts
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return " ".join(parts)
    return ""


async def build_context(
    messages: list[dict[str, Any]],
    memory_service: Any = None,
    skill_service: Any = None,
    data_dir: Any = None,
    conversation_service: Any = None,
    max_memories: int = _MAX_MEMORIES,
    max_skills: int = _MAX_SKILLS,
) -> str:
    """Build enriched context from relevant memories, skills, and user files.

    Returns an empty string when no relevant memories or skills are found.
    The result is intended to be appended to the agent's system prompt.

    When *data_dir* is provided, MEMORY.md and USER.md are loaded as the
    first context section (stable, persistent user/environment facts).
    """
    query = _extract_user_query(messages)
    parts: list[str] = []

    # ── User context files (MEMORY.md / USER.md) ───────────────────────
    if data_dir is not None:
        try:
            from shared.user_context import load_user_context
            user_ctx = load_user_context(data_dir)
            if user_ctx:
                parts.append(user_ctx)
        except Exception:
            logger.debug("User context loading failed", exc_info=True)

    if not query:
        return "\n\n".join(parts)

    # ── Cross-session recall (search past conversations) ─────────────
    if conversation_service is not None and query:
        try:
            past = await recall_conversations(
                query, conversation_service, max_results=3,
            )
            if past:
                lines = [f"- {p}" for p in past]
                parts.append(
                    "## Past Conversations\n"
                    "The following snippets from previous conversations may be relevant:\n"
                    + "\n".join(lines)
                )
        except Exception:
            logger.debug("Cross-session recall failed", exc_info=True)

    # ── Relevant memories (FTS5 full-text search) ──────────────────────
    if memory_service is not None:
        try:
            memories, _ = memory_service.search(query, limit=max_memories)
            if memories:
                lines = [f"- {m['content']}" for m in memories]
                parts.append(
                    "## Relevant Memories\n"
                    "The following memories may be relevant to the current conversation:\n"
                    + "\n".join(lines)
                )
        except Exception:
            logger.debug("Memory search failed for context builder", exc_info=True)

    # ── Relevant skills (keyword match) ───────────────────────────────
    if skill_service is not None:
        try:
            skills = skill_service.search(query, top_k=max_skills)
            if skills:
                lines = []
                for s in skills:
                    name = s.get("name", "")
                    desc = s.get("description", "")
                    lines.append(f"- **{name}**: {desc}")
                parts.append(
                    "## Relevant Skills\n"
                    "The following skills may help answer this query:\n"
                    + "\n".join(lines)
                )
        except Exception:
            logger.debug("Skill search failed for context builder", exc_info=True)

    return "\n\n".join(parts)


async def recall_conversations(
    query: str,
    conversation_service: Any,
    max_results: int = 3,
) -> list[str]:
    """Search past conversations for cross-session context.

    Returns a list of short text snippets from past conversations
    that are relevant to *query*.
    """
    try:
        convs, _ = conversation_service.list_conversations(limit=50)
        results: list[tuple[str, float]] = []
        query_tokens = set(query.lower().split())

        for c in convs:
            title = c.get("title", "")
            token_overlap = sum(1 for t in query_tokens if t in title.lower())
            if token_overlap > 0:
                results.append((title, token_overlap / max(len(query_tokens), 1)))

        if hasattr(conversation_service, "get_messages"):
            for c in convs[:10]:
                cid = c.get("id", "")
                if not cid:
                    continue
                try:
                    msgs, _ = conversation_service.get_messages(cid, limit=10)
                    for m in msgs:
                        content = m.get("content", "")
                        if isinstance(content, str) and len(content) < 200:
                            token_overlap = sum(
                                1 for t in query_tokens if t in content.lower()
                            )
                            if token_overlap >= 2:
                                results.append(
                                    (content[:150], token_overlap / max(len(query_tokens), 1))
                                )
                except Exception:
                    pass

        results.sort(key=lambda x: -x[1])
        return [r[0] for r in results[:max_results]]
    except Exception:
        return []
