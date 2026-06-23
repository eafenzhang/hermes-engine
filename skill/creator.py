"""Skill creator — programmatic skill generation for self-evolution.

Adapted from Hermes Agent's skill_commands.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkillCreator:
    """Creates and manages skill .md files — key enabler of self-evolution."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        name: str,
        description: str,
        content: str,
        tags: list[str] | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Create a new skill .md file in the skills directory."""
        safe_name = self._sanitize_name(name)
        fpath = self.skills_dir / f"{safe_name}.md"

        if fpath.exists() and not overwrite:
            raise FileExistsError(f"Skill '{safe_name}' already exists at {fpath}")

        tags_str = ", ".join(tags) if tags else ""

        full_content = f"""# {description}

> tags: {tags_str}

{content}
"""
        fpath.write_text(full_content, encoding="utf-8")
        logger.info("Created skill '%s' at %s", safe_name, fpath)
        return fpath

    def delete(self, name: str) -> bool:
        """Delete a skill file by name."""
        safe_name = self._sanitize_name(name)
        fpath = self.skills_dir / f"{safe_name}.md"
        if fpath.exists():
            fpath.unlink()
            logger.info("Deleted skill '%s'", safe_name)
            return True
        return False

    def list_files(self) -> list[Path]:
        """List all .md files in the skills directory."""
        if not self.skills_dir.exists():
            return []
        return sorted(self.skills_dir.glob("*.md"))

    def _sanitize_name(self, name: str) -> str:
        """Convert a skill name to a safe filename slug."""
        name = name.strip().lower()
        name = re.sub(r"[^a-z0-9]+", "-", name)
        name = name.strip("-")
        return name or "untitled-skill"
