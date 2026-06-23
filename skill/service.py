"""Skill service — business logic decoupled from FastAPI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skill.loader import SkillLoader
from skill.creator import SkillCreator
from skill.matcher import SkillMatcher


class SkillService:
    """High-level skill operations."""

    def __init__(self, skills_dir: Path) -> None:
        self.loader = SkillLoader(skills_dir)
        self.creator = SkillCreator(skills_dir)
        self.matcher = SkillMatcher(self.loader)

    def scan(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.loader.scan()]

    def list(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.loader._skills.values()]

    def get(self, name: str) -> dict[str, Any] | None:
        skill = self.loader.get(name)
        return skill.to_dict() if skill else None

    def create(self, name: str, description: str, content: str, tags: list[str] | None = None, overwrite: bool = False) -> dict[str, Any]:
        self.creator.create(name, description, content, tags, overwrite)
        # Re-scan to pick up the new skill in the in-memory cache
        self.scan()
        skill = self.loader.get(name)
        return skill.to_dict() if skill else {"name": name}

    def delete(self, name: str) -> bool:
        removed = self.creator.delete(name)
        self.loader._skills.pop(name, None)
        return removed

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.matcher.find_relevant(query, top_k)
