"""Skill matcher — automatically selects relevant skills for a given context.

Supports both keyword-based matching (fast, no LLM needed) and LLM-based
semantic matching (more accurate, requires a configured provider).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.utils import extract_json as _extract_json_shared

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
        """Find skills relevant to the given query via keyword scoring."""
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
        provider_name: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Use LLM to rank skills by semantic relevance to *query*.

        When a provider is available, the LLM receives the query plus the
        skill catalogue and returns the indices of the most relevant skills.
        Falls back to keyword matching on any failure or when no provider
        is configured.
        """
        if not skills:
            return []

        provider_name = provider_name or "anthropic"

        try:
            from provider.registry import registry

            provider = registry.get(provider_name)
            if provider is None:
                logger.debug(
                    "llm_match: provider '%s' not available, using keyword fallback",
                    provider_name,
                )
                return self.find_relevant(query, top_k=min(len(skills), 3))

            # Build a compact skill catalogue
            catalogue = [
                {
                    "idx": i,
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                }
                for i, s in enumerate(skills)
            ]
            prompt = (
                "Given a user query and a list of skills, select the most relevant "
                "skills by returning their indices.\n\n"
                f"Query: {query}\n\nSkills:\n"
                + json.dumps(catalogue, ensure_ascii=False)
                + "\n\nRespond with STRICT JSON only, no prose:\n"
                '{"indices": [int, ...]}  // max 3, ordered by relevance'
            )

            result = await provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model or "claude-sonnet-4-20250514",
                max_tokens=200,
                temperature=0.1,
            )

            content = result.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )

            data = SkillMatcher._extract_json(str(content))
            indices: list[int] = data.get("indices", []) if isinstance(data, dict) else []

            matched = []
            for idx in indices[:3]:
                if isinstance(idx, int) and 0 <= idx < len(skills):
                    matched.append(skills[idx])
            if matched:
                return matched
        except Exception:
            logger.debug("llm_match failed, using keyword fallback", exc_info=True)

        return self.find_relevant(query, top_k=min(len(skills), 3))

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Parse JSON from text, tolerating surrounding ``` fences or prose."""
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
