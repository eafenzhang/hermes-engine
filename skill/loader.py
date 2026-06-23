"""File-system skill loader — discovers and loads skills from .md files.

Adapted from Hermes Agent's skill_utils.py
Copyright (c) NousResearch — used under Apache 2.0 license.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = frozenset({
    ".git", ".github", ".archive", "node_modules", "__pycache__",
    ".venv", "venv", ".tox", ".pytest_cache",
})


class SkillDoc:
    """A single skill loaded from a .md file."""

    def __init__(
        self,
        name: str,
        path: Path,
        description: str,
        content: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.path = path
        self.description = description
        self.content = content
        self.tags = tags or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "description": self.description,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    def matches(self, query: str) -> bool:
        """Keyword match against name, description, tags, and content."""
        q = query.lower()
        if q in self.name.lower():
            return True
        if q in self.description.lower():
            return True
        if any(q in t.lower() for t in self.tags):
            return True
        return False


class SkillLoader:
    """Discovers and loads skills from a file-system directory."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir
        self._skills: dict[str, SkillDoc] = {}

    def scan(self) -> list[SkillDoc]:
        """Scan the skills directory and load all skill .md files."""
        self._skills.clear()
        if not self.skills_dir.exists():
            logger.warning("Skills directory does not exist: %s", self.skills_dir)
            return []

        for fpath in self.skills_dir.rglob("*.md"):
            if any(excl in fpath.parts for excl in EXCLUDED_DIRS):
                continue
            try:
                skill = self._load_file(fpath)
                if skill:
                    self._skills[skill.name] = skill
            except Exception:
                logger.exception("Failed to load skill %s", fpath)

        logger.info("Loaded %d skills from %s", len(self._skills), self.skills_dir)
        return list(self._skills.values())

    def _load_file(self, fpath: Path) -> SkillDoc | None:
        content = fpath.read_text(encoding="utf-8")
        name = fpath.stem

        # Parse frontmatter-style description from first line
        description = ""
        tags: list[str] = []
        lines = content.split("\n")
        for line in lines[:10]:
            if line.startswith("# ") and not description:
                description = line[2:].strip()
            m = re.match(r"^tags?:\s*(.+)$", line, re.IGNORECASE)
            if m:
                tags = [t.strip() for t in m.group(1).split(",")]

        if not description and content.strip():
            # Fallback: first non-empty line
            for line in lines:
                stripped = line.strip().strip("#").strip()
                if stripped:
                    description = stripped[:120]
                    break

        return SkillDoc(
            name=name,
            path=fpath,
            description=description,
            content=content,
            tags=tags,
        )

    def get(self, name: str) -> SkillDoc | None:
        # Check cache first
        cached = self._skills.get(name)
        if cached:
            return cached
        # Fallback: try loading from disk
        fpath = self.skills_dir / f"{name}.md"
        if fpath.exists():
            skill = self._load_file(fpath)
            if skill:
                self._skills[name] = skill
                return skill
        return None

    def search(self, query: str) -> list[SkillDoc]:
        """Search loaded skills by keyword match."""
        q = query.lower()
        return [s for s in self._skills.values() if s.matches(q)]

    @property
    def count(self) -> int:
        return len(self._skills)
