"""SSH terminal backend — remote command execution via SSH."""

from __future__ import annotations

import asyncio
import logging

from tools.terminal_backends import TerminalBackend

logger = logging.getLogger(__name__)


class SSHBackend(TerminalBackend):
    """Executes commands on a remote host via SSH.

    Uses the system ``ssh`` binary (``asyncio.create_subprocess_exec``)
    for zero additional Python dependencies.  SSH connection parameters
    are configured via settings: ``HERMES_SSH_HOST``, ``HERMES_SSH_USER``,
    ``HERMES_SSH_KEY_PATH``, ``HERMES_SSH_PORT``.
    """

    name = "ssh"

    def __init__(
        self,
        host: str = "",
        user: str = "",
        key_path: str = "",
        port: int = 22,
    ) -> None:
        self._host = host
        self._user = user
        self._key_path = key_path
        self._port = port

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str = "",
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        ssh_cmd = ["ssh"]
        if self._port != 22:
            ssh_cmd.extend(["-p", str(self._port)])
        if self._key_path:
            ssh_cmd.extend(["-i", self._key_path])
        ssh_cmd.extend([
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            f"{self._user}@{self._host}" if self._user else self._host,
            f"cd {cwd} 2>/dev/null; {command}" if cwd else command,
        ])

        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", f"SSH command timed out after {timeout}s"

        return (
            proc.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
            stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "",
        )
