"""User context — persistent MEMORY.md / USER.md files for long-term personalisation.

Mirrors Hermes Agent's two-layer memory system:
- MEMORY.md: environment facts, conventions, project context
- USER.md: user preferences, style, personal information

Both are loaded once at session start (frozen snapshot) and updated
programmatically as the agent learns new facts.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_user_context(data_dir: Path) -> str:
    """Load MEMORY.md and USER.md into a combined context string.

    Returns an empty string when neither file exists.
    """
    parts: list[str] = []

    memory_file = data_dir / "MEMORY.md"
    if memory_file.exists():
        content = memory_file.read_text(encoding="utf-8").strip()
        if content:
            parts.append("## Memory (Environment Facts)\n" + content)

    user_file = data_dir / "USER.md"
    if user_file.exists():
        content = user_file.read_text(encoding="utf-8").strip()
        if content:
            parts.append("## User Profile\n" + content)

    return "\n\n".join(parts)


def update_memory_file(data_dir: Path, content: str, mode: str = "append") -> None:
    """Update MEMORY.md — append or overwrite."""
    memory_file = data_dir / "MEMORY.md"
    if mode == "overwrite" or not memory_file.exists():
        memory_file.write_text(content, encoding="utf-8")
    else:
        existing = memory_file.read_text(encoding="utf-8")
        memory_file.write_text(existing + "\n" + content, encoding="utf-8")
    logger.info("Updated MEMORY.md (%d chars)", len(memory_file.read_text()))


def update_user_file(data_dir: Path, content: str, mode: str = "append") -> None:
    """Update USER.md — append or overwrite."""
    user_file = data_dir / "USER.md"
    if mode == "overwrite" or not user_file.exists():
        user_file.write_text(content, encoding="utf-8")
    else:
        existing = user_file.read_text(encoding="utf-8")
        user_file.write_text(existing + "\n" + content, encoding="utf-8")
    logger.info("Updated USER.md (%d chars)", len(user_file.read_text()))
