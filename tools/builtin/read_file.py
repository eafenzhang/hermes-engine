"""Built-in tool: read a file from disk."""

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


async def read_file(path: str, max_chars: int = 50000) -> str:
    """Read a file and return its contents."""
    fpath = Path(path).resolve()
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
