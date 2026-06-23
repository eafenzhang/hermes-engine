"""Skill matcher — automatically selects relevant skills for a given context.

In v1 this uses keyword matching; future versions can add LLM-based matching.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from skill.loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillMatcher:
    """Matches user input to relevant skills."""

    def __init__(self, loader: SkillLoader) -> None:
        self.loader = loader

    def find_relevant(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Find skills relevant to the given query."""
        results = self.loader.search(query)
        # Score by counting keyword occurrences
        scored = []
        q = query.lower()
        for skill in results:
            score = 0
            if skill.name.lower() in q or q in skill.name.lower():
                score += 3
            for tag in skill.tags:
                if tag.lower() in q:
                    score += 2
            if skill.description.lower().startswith(q) or q in skill.description.lower():
                score += 1
            scored.append((score, skill))

        scored.sort(key=lambda x: -x[0])
        return [s.to_dict() for _, s in scored[:top_k]]

    async def llm_match(
        self,
        query: str,
        skills: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Placeholder for LLM-based skill matching (v2)."""
        logger.warning("llm_match is not yet implemented — falling back to keyword top-3")
        return self.find_relevant(query, top_k=3)
