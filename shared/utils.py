"""Shared utilities — text processing helpers used across the codebase."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def flatten_content(content: Any) -> str:
    """Convert provider response content to a plain string.

    Handles both plain strings and lists of content blocks
    (Anthropic-style ``[{"type": "text", "text": "..."}]``).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


def extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from text, tolerating surrounding ``` fences or prose.

    Returns an empty dict when parsing fails.
    """
    fenced = text
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                fenced = part
                break
    try:
        result: dict[str, Any] = json.loads(fenced)
        return result
    except (json.JSONDecodeError, TypeError):
        return {}
