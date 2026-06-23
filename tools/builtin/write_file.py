"""Built-in tool: write content to a file (path-traversal safe)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = {
    "description": "Write text content to a file on the local filesystem.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path of the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
}

_ALLOWED_BASES = [
    Path.home().resolve(),
    Path.cwd().resolve(),
]


def _is_path_allowed(fpath: Path) -> bool:
    try:
        fpath = fpath.resolve()
        return any(
            str(fpath).startswith(str(base))
            for base in _ALLOWED_BASES
        )
    except (ValueError, OSError, RuntimeError):
        return False


async def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    fpath = Path(path).resolve()
    if not _is_path_allowed(fpath):
        return f"Error: access denied — path outside allowed directories"
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as exc:
        return f"Error writing file: {exc}"
