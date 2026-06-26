"""Sub-agent delegation — lightweight isolated sub-agent execution.

Spawns a fresh AgentEngine for one-turn task execution with configurable
timeout and concurrency limits.  Suitable for decomposing complex tasks
into parallel sub-tasks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent.engine import AgentEngine
from provider.registry import registry

logger = logging.getLogger(__name__)

# Simple semaphore for concurrency limiting
_subagent_semaphore: asyncio.Semaphore | None = None


def _get_semaphore(max_concurrent: int = 3) -> asyncio.Semaphore:
    global _subagent_semaphore
    if _subagent_semaphore is None:
        _subagent_semaphore = asyncio.Semaphore(max_concurrent)
    return _subagent_semaphore


async def run_subagent(
    task: str,
    provider_name: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
    tools: list[dict[str, Any]] | None = None,
    timeout: float = 300.0,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Run an isolated sub-agent for a single task.

    Creates a fresh AgentEngine, executes one turn with *task* as the
    user message, and returns the provider's response dict.

    *timeout* prevents runaway sub-agents — an ``asyncio.TimeoutError``
    is raised if the sub-agent exceeds the deadline.

    A semaphore caps concurrent sub-agents (configured via
    ``HERMES_SUBAGENT_MAX_CONCURRENT``, default 3).
    """
    sem = _get_semaphore()

    async with sem:
        provider = registry.get(provider_name)
        if provider is None:
            raise ValueError(
                f"Sub-agent: provider '{provider_name}' not available"
            )

        engine = AgentEngine(
            default_provider=provider_name,
            default_model=model,
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": task},
        ]

        try:
            result = await asyncio.wait_for(
                engine.run_turn(
                    messages=messages,
                    provider_name=provider_name,
                    model=model,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )
            logger.info(
                "Sub-agent completed (provider=%s, model=%s, timeout=%ds)",
                provider_name, model, timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "Sub-agent timed out after %ds (provider=%s, model=%s)",
                timeout, provider_name, model,
            )
            raise


async def run_subagents_parallel(
    tasks: list[str],
    provider_name: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
    timeout: float = 300.0,
    **kwargs: Any,
) -> list[dict[str, Any] | None]:
    """Run multiple sub-agents in parallel for a set of tasks.

    Each task gets its own sub-agent.  Individual failures (timeout,
    provider error) produce ``None`` in the result list — the caller
    should filter after.
    """
    async def _one(task: str) -> dict[str, Any] | None:
        try:
            return await run_subagent(
                task=task,
                provider_name=provider_name,
                model=model,
                timeout=timeout,
                **kwargs,
            )
        except Exception:
            logger.debug("Sub-agent failed for task: %s", task[:60], exc_info=True)
            return None

    return list(await asyncio.gather(*(_one(t) for t in tasks)))
