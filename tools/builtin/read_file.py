"""Built-in tool: read a file from disk.

In --local mode the allowed base is the project root or home directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = {
    "description": "Read the contents of a text file from the local filesystem.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to read",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum number of characters to read (default 50000)",
            },
        },
        "required": ["path"],
    },
}

# Allowed base directories for file operations
_ALLOWED_BASES = [
    Path.home().resolve(),
    Path.cwd().resolve(),
]


def _is_path_allowed(fpath: Path) -> bool:
    """Check if the resolved path is within an allowed base directory."""
    try:
        fpath = fpath.resolve()
        return any(
            str(fpath).startswith(str(base))
            for base in _ALLOWED_BASES
        )
    except (ValueError, OSError, RuntimeError):
        return False


async def read_file(path: str, max_chars: int = 50000) -> str:
    """Read a file and return its contents."""
    fpath = Path(path).resolve()
    if not _is_path_allowed(fpath):
        return f"Error: access denied — path outside allowed directories"
    if not fpath.exists():
        return f"Error: file not found at {path}"
    if not fpath.is_file():
        return f"Error: {path} is not a file"
    try:
        content = fpath.read_text(encoding="utf-8")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (truncated at {max_chars} chars)"
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"
