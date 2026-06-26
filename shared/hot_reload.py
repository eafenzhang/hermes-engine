"""Hot reload — watch .env and reload settings on change."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def watch_env(reload_callback, interval: float = 5.0) -> None:
    """Poll .env file for changes and call reload_callback when modified.

    Falls back to polling when watchfiles is not installed.
    """
    env_file = os.environ.get("HERMES_ENV_FILE", ".env")
    try:
        import watchfiles
        async for _ in watchfiles.awatch(env_file):
            logger.info("Detected .env change, reloading settings")
            reload_callback()
    except ImportError:
        logger.debug("watchfiles not installed; using polling for .env changes")
        last_mtime = 0.0
        while True:
            try:
                mtime = os.path.getmtime(env_file)
                if mtime > last_mtime and last_mtime > 0:
                    logger.info("Detected .env change (poll), reloading settings")
                    reload_callback()
                last_mtime = mtime
            except OSError:
                pass
            await asyncio.sleep(interval)
