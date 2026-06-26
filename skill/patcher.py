"""Skill patcher — surgical skill editing via old_string/new_string.

Allows the agent (or an external caller) to make precise edits to an
existing SKILL.md file without rewriting the entire document.  The patch
operation searches for *old_string* in the file content and replaces it
with *new_string* — identical to how ``skill_manage patch`` works in
the original Hermes Agent.

This is a key enabler of skill self-improvement: skills can be refined
during use without losing their accumulated knowledge.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


class SkillPatcher:
    """Handles exact-string patches on skill markdown files."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir

    def patch(self, name: str, old_string: str, new_string: str) -> dict:
        """Apply a surgical patch to the skill named *name*.

        Reads the skill file, replaces the first occurrence of *old_string*
        with *new_string*, and writes the result back.

        Raises:
            NotFoundError: The skill does not exist.
            ValidationError: *old_string* is not found in the file.
        """
        # Sanitise name (same as creator)
        safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        file_path = self.skills_dir / f"{safe_name}.md"

        if not file_path.exists():
            raise NotFoundError(f"Skill '{name}' not found at {file_path}")

        content = file_path.read_text(encoding="utf-8")

        if old_string not in content:
            raise ValidationError(
                f"old_string not found in skill '{name}'",
                code="PATCH_NOT_FOUND",
                details={"name": name},
            )

        # Replace first occurrence only (like Hermes `skill_manage patch`)
        new_content = content.replace(old_string, new_string, 1)
        file_path.write_text(new_content, encoding="utf-8")

        logger.info(
            "Patched skill '%s': %d → %d chars",
            name, len(content), len(new_content),
        )

        return {
            "name": safe_name,
            "path": str(file_path),
            "old_length": len(content),
            "new_length": len(new_content),
        }

    def patch_all(self, name: str, old_string: str, new_string: str) -> dict:
        """Replace ALL occurrences of *old_string* in the skill file.

        Like :meth:`patch` but replaces every match rather than just the first.
        """
        safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        file_path = self.skills_dir / f"{safe_name}.md"

        if not file_path.exists():
            raise NotFoundError(f"Skill '{name}' not found at {file_path}")

        content = file_path.read_text(encoding="utf-8")

        if old_string not in content:
            raise ValidationError(
                f"old_string not found in skill '{name}'",
                code="PATCH_NOT_FOUND",
                details={"name": name},
            )

        count = content.count(old_string)
        new_content = content.replace(old_string, new_string)
        file_path.write_text(new_content, encoding="utf-8")

        logger.info(
            "Patched skill '%s' (×%d): %d → %d chars",
            name, count, len(content), len(new_content),
        )

        return {
            "name": safe_name,
            "path": str(file_path),
            "replacements": count,
            "old_length": len(content),
            "new_length": len(new_content),
        }
