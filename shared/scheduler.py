"""Cron scheduler — periodic task execution with REST API.

Background asyncio task that checks registered cron expressions each
minute and fires due tasks through the agent engine.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class CronScheduler:
    """Minimal in-process cron scheduler.

    Supports standard 5-field cron expressions (minute hour dom month dow).
    Tasks fire as fire-and-forget coroutines.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._running = False

    def add_task(
        self,
        name: str,
        cron_expr: str,
        action: Callable[[], Awaitable[None]],
    ) -> dict[str, Any]:
        """Register a cron task. Returns the task descriptor."""
        self._tasks[name] = {
            "name": name,
            "cron": cron_expr,
            "action": action,
            "last_run": None,
            "run_count": 0,
        }
        logger.info("Cron task '%s' registered (%s)", name, cron_expr)
        return self._tasks[name]

    def remove_task(self, name: str) -> bool:
        """Remove a registered task."""
        return self._tasks.pop(name, None) is not None

    def list_tasks(self) -> list[dict[str, Any]]:
        """Return all registered tasks (without action callable)."""
        return [
            {k: v for k, v in t.items() if k != "action"}
            for t in self._tasks.values()
        ]

    async def start(self, interval: float = 60.0) -> None:
        """Start the scheduler loop (non-blocking)."""
        self._running = True
        logger.info("Cron scheduler started (interval=%ds)", interval)
        while self._running:
            await self._tick()
            await asyncio.sleep(interval)

    def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        logger.info("Cron scheduler stopped")

    async def _tick(self) -> None:
        """Check and fire due tasks."""
        now = time.time()
        for task in self._tasks.values():
            try:
                await task["action"]()
                task["last_run"] = now
                task["run_count"] += 1
            except Exception:
                logger.debug("Cron task '%s' failed", task["name"], exc_info=True)


# Module-level singleton for lifespan management
_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler


async def parse_nl_cron(
    human_text: str,
    provider_name: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
) -> str | None:
    """Parse a natural-language schedule into a 5-field cron expression.

    Examples:
        "every day at 3pm" → "0 15 * * *"
        "each Monday at 9am" → "0 9 * * 1"

    Returns the cron string, or ``None`` on failure.
    """
    try:
        from provider.registry import registry

        provider = registry.get(provider_name)
        if provider is None:
            return None

        result = await provider.chat_completion(
            messages=[{
                "role": "user",
                "content": (
                    "Convert the following natural language schedule into a "
                    "standard 5-field cron expression (minute hour day-of-month "
                    "month day-of-week). Return ONLY the cron expression, nothing else.\n\n"
                    f"Schedule: {human_text}"
                ),
            }],
            model=model,
            max_tokens=30,
            temperature=0.0,
        )

        content = result.get("content", "")
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))

        cron = str(content).strip().strip('"\x60').strip()
        # Validate: 5 space-separated fields
        parts = cron.split()
        if len(parts) == 5:
            return cron
        return None
    except Exception:
        return None
