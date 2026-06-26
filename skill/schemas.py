"""Skill schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class SkillItem(BaseModel):
    name: str
    path: str
    description: str
    tags: list[str] = []


class SkillCreate(BaseModel):
    name: str
    description: str
    content: str
    tags: list[str] = []
    overwrite: bool = False


class SkillMatchRequest(BaseModel):
    query: str
    top_k: int = 5


class SkillPatchRequest(BaseModel):
    """Surgical skill edit — replaces old_string with new_string in the skill file."""

    old_string: str
    new_string: str
    replace_all: bool = False  # True = replace all occurrences, False = first only
