"""Built-in tool: execute a shell command.

Security: commands are logged but NOT sandboxed — use with caution.
The engine's --local mode trusts the desktop user; external exposure
of this endpoint would require additional access controls.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "description": "Execute a shell command and return its output. Use with caution.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30)",
            },
        },
        "required": ["command"],
    },
}

# Commands that are never allowed, even in --local mode
_FORBIDDEN_PREFIXES = (
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf .",
    ":(){ :|:& };:",  # fork bomb
    "dd if=/dev/zero", "mkfs.", "fdisk", "format ",
)


async def execute_command(command: str, timeout: int = 30) -> str:
    """Execute a shell command and return stdout + stderr."""
    # Basic safety check
    stripped = command.strip().lower()
    for forbidden in _FORBIDDEN_PREFIXES:
        if stripped.startswith(forbidden):
            logger.warning("Blocked forbidden command: %s", command[:120])
            return f"Error: command blocked by safety policy"

    logger.info("Executing command (timeout=%ds): %s", timeout, command[:200])
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        output = ""
        if stdout_bytes:
            output += stdout_bytes.decode("utf-8", errors="replace")
        if stderr_bytes:
            output += "\n[stderr]\n" + stderr_bytes.decode("utf-8", errors="replace")
        return output or "(no output)"
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except Exception as exc:
        return f"Error executing command: {exc}"
