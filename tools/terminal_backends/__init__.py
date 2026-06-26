"""Terminal backends — pluggable command execution backends.

Supports local subprocess (default) and Docker container isolation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TerminalBackend(ABC):
    """Abstract backend for executing shell commands."""

    name: str = "base"

    @abstractmethod
    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str = "",
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Execute *command*, return ``(returncode, stdout, stderr)``."""
        ...


def get_backend(name: str = "local", **kwargs: str) -> TerminalBackend:
    """Factory: return a terminal backend by name."""
    if name == "docker":
        from tools.terminal_backends.docker_backend import DockerBackend
        return DockerBackend(image=kwargs.get("docker_image", "python:3.12-slim"))
    if name == "ssh":
        from tools.terminal_backends.ssh_backend import SSHBackend
        return SSHBackend(
            host=kwargs.get("ssh_host", ""),
            user=kwargs.get("ssh_user", ""),
            key_path=kwargs.get("ssh_key_path", ""),
            port=int(kwargs.get("ssh_port", "22")),
        )
    from tools.terminal_backends.local_backend import LocalBackend
    return LocalBackend()
