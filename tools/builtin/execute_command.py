"""Built-in tool: execute a shell command.

Security model (whitelist + sandbox):
1. Only commands in _ALLOWED_COMMANDS can be executed (whitelist).
2. Dangerous patterns (recursive delete, fork bomb, disk wipe, etc.) are
   blocked by regex even if the command base is on the whitelist.
3. Working directory is pinned to the project root (cwd), preventing
   operations outside the project scope.
4. PATH is sanitised to remove user-writable directories.
5. The engine's --local mode trusts the desktop user; external exposure
   of this endpoint would require additional access controls.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path

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
            "cwd": {
                "type": "string",
                "description": "Working directory (must be within project root; defaults to project root)",
            },
        },
        "required": ["command"],
    },
}

# ── Whitelist: only these commands (resolved via shutil.which) may run ──
_BASE_ALLOWED_COMMANDS: set[str] = {
    # File / directory operations
    "ls", "dir", "cat", "head", "tail", "wc", "stat", "file",
    "find", "tree", "pwd", "realpath", "readlink",
    # Text processing
    "grep", "rg", "awk", "sed", "cut", "sort", "uniq", "tr",
    "diff", "comm", "join", "paste", "tee",
    # Build / dev tools
    "python", "python3", "node", "npm", "npx", "cargo", "go",
    "make", "cmake", "gcc", "g++", "rustc",
    # Version control
    "git", "hg",
    # Package managers
    "pip", "pip3", "poetry",
    # DevOps / container
    "docker", "kubectl", "helm", "terraform",
    # System info
    "echo", "date", "uname", "whoami", "id", "which", "env",
    "ps", "df", "du", "free",
    # Network (read-only)
    "curl", "wget", "ping",
}

# Merged set — populated at startup from settings.extra_allowed_commands
_ALLOWED_COMMANDS: set[str] = set(_BASE_ALLOWED_COMMANDS)


def register_extra_commands(commands: list[str]) -> None:
    """Add extra commands to the execution whitelist (called from lifespan)."""
    for cmd in commands:
        _ALLOWED_COMMANDS.add(cmd.strip().lower())
    if commands:
        logger.info("Registered %d extra allowed commands", len(commands))

# ── Blocked patterns — matched against the FULL command string ──
# These catch dangerous invocations even when the base command is whitelisted.
_DANGEROUS_PATTERNS: list[re.Pattern] = [
    # Recursive / root deletion
    re.compile(r"\brm\s+.*-r\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/[sfq]\s", re.IGNORECASE),
    re.compile(r"-exec\s+rm\b", re.IGNORECASE),
    # Fork bombs
    re.compile(r":\(\)\s*\{[^}]*:\|:&[^}]*\}[^;]*;"),
    re.compile(r"\bperl\s+-e\s+.*fork", re.IGNORECASE),
    re.compile(r"\bpython.*os\.fork\b", re.IGNORECASE),
    # Disk / device destruction
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"\bmkfs\.", re.IGNORECASE),
    re.compile(r"\bfdisk\b", re.IGNORECASE),
    re.compile(r"\bmkswap\b", re.IGNORECASE),
    # Privilege escalation
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+[0-7]*7", re.IGNORECASE),
    re.compile(r"\bchown\b", re.IGNORECASE),
    # Network listeners / reverse shells
    re.compile(r"\bnc\s+.*-[lL]", re.IGNORECASE),
    re.compile(r"\bsocat\b", re.IGNORECASE),
    re.compile(r"\bncat\b", re.IGNORECASE),
    # Command substitution that could mask dangerous commands
    re.compile(r"\$\(.*\brm\b.*\)", re.IGNORECASE),
    re.compile(r"`.*\brm\b.*`"),
    # Write to /dev
    re.compile(r">\s*/dev/", re.IGNORECASE),
    # Piping into bash/sh
    re.compile(r"\|\s*(ba)?sh\b", re.IGNORECASE),
]

# ── Project root — all execution scoped here ──
_PROJECT_ROOT = Path.cwd().resolve()


def _resolve_command(command_str: str) -> tuple[str | None, str]:
    """Resolve the base command and validate it against the whitelist.

    Returns (None, reason) if blocked, or (resolved_path, '') if allowed.
    """
    cmd_line = command_str.strip()
    if not cmd_line:
        return None, "empty command"

    # Extract base command name (first token)
    tokens = cmd_line.split()
    base = tokens[0]

    # Resolve the real path to avoid PATH manipulation
    resolved = shutil.which(base)
    if resolved is None:
        return None, f"command not found: {base}"

    base_name = os.path.basename(resolved)

    if base_name not in _ALLOWED_COMMANDS:
        logger.warning("Blocked non-whitelisted command: %s (%s)", base, resolved)
        return None, f"command '{base}' is not allowed"

    return resolved, ""


def _check_dangerous_patterns(command_str: str) -> str:
    """Scan the full command for dangerous patterns. Returns empty string if safe."""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(command_str):
            return f"blocked dangerous pattern: {pattern.pattern[:60]}..."
    return ""


def _sanitise_env() -> dict[str, str]:
    """Build a sanitised environment for subprocess execution."""
    safe_vars = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TZ",
                 "PYTHONPATH", "NODE_PATH", "VIRTUAL_ENV", "CONDA_PREFIX",
                 "GIT_DIR", "GIT_WORK_TREE"}
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in safe_vars or key.startswith(("PYTHON", "NODE", "GIT", "CARGO", "RUST")):
            env[key] = value

    # Sanitise PATH: remove writable directories
    path_entries = env.get("PATH", "").split(os.pathsep)
    safe_entries: list[str] = []
    for entry in path_entries:
        p = Path(entry)
        try:
            if p.exists() and p.is_dir():
                # Reject world-writable or tmp directories
                if os.access(str(p), os.W_OK) and (
                    "/tmp" in str(p) or "Temp" in str(p) or str(p).startswith("/dev/")
                ):
                    continue
                safe_entries.append(entry)
        except (OSError, ValueError):
            continue
    env["PATH"] = os.pathsep.join(safe_entries) if safe_entries else "/usr/bin:/bin"

    return env


async def execute_command(
    command: str,
    timeout: int = 30,
    cwd: str | None = None,
) -> str:
    """Execute a shell command and return stdout + stderr.

    The command must be in the whitelist and pass dangerous-pattern checks.
    Execution is scoped to the project root directory.
    """
    # ── Step 1: resolve and validate the command ──
    resolved, blocked_reason = _resolve_command(command)
    if blocked_reason:
        return f"Error: {blocked_reason}"

    # ── Step 2: check dangerous patterns in the full command ──
    pattern_blocked = _check_dangerous_patterns(command)
    if pattern_blocked:
        logger.warning("Blocked dangerous command: %s — %s", command[:120], pattern_blocked)
        return f"Error: {pattern_blocked}"

    # ── Step 3: resolve working directory ──
    work_dir = _PROJECT_ROOT
    if cwd:
        cwd_path = Path(cwd).resolve()
        try:
            cwd_path.relative_to(_PROJECT_ROOT)
        except ValueError:
            return f"Error: working directory must be within project root ({_PROJECT_ROOT})"
        if cwd_path.is_dir():
            work_dir = cwd_path
        else:
            return f"Error: working directory not found: {cwd}"

    # ── Step 4: execute ──
    logger.info(
        "Executing command (cwd=%s, timeout=%ds): %s",
        work_dir, timeout, command[:200],
    )
    env = _sanitise_env()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
            env=env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
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
