"""Local subprocess terminal backend."""

from __future__ import annotations

import asyncio
import logging

from tools.terminal_backends import TerminalBackend

logger = logging.getLogger(__name__)


class LocalBackend(TerminalBackend):
    """Executes commands via local ``asyncio.create_subprocess_shell``."""

    name = "local"

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str = "",
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or None,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", f"Command timed out after {timeout}s"

        return (
            proc.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
            stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "",
        )
