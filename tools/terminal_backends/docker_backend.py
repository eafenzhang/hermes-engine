"""Docker container terminal backend — isolated command execution."""

from __future__ import annotations

import asyncio
import logging
import shutil

from tools.terminal_backends import TerminalBackend

logger = logging.getLogger(__name__)


class DockerBackend(TerminalBackend):
    """Executes commands inside an ephemeral Docker container.

    Requires Docker to be installed and accessible.  The container is
    removed after execution (``--rm``).  The current working directory
    is bind-mounted at ``/workspace`` inside the container.
    """

    name = "docker"

    def __init__(self, image: str = "python:3.12-slim") -> None:
        self._image = image
        if not shutil.which("docker"):
            logger.warning(
                "DockerBackend configured but 'docker' not found in PATH — "
                "commands will fail at runtime"
            )

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str = "",
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        work_dir = cwd or "."
        env_args: list[str] = []
        if env:
            for k, v in env.items():
                env_args.extend(["-e", f"{k}={v}"])

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{work_dir}:/workspace",
            "-w", "/workspace",
            *env_args,
            self._image,
            "sh", "-c", command,
        ]

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
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
            return -1, "", f"Command timed out after {timeout}s"

        return (
            proc.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
            stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "",
        )
