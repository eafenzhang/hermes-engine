"""Built-in tool: write content to a file (path-traversal safe).

File access is restricted to the project root and registered workspace
directories (see ``tools/builtin/_shared.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ._shared import is_path_allowed

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


async def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    fpath = Path(path).resolve(strict=False)
    if not is_path_allowed(fpath):
        return "Error: access denied — path outside allowed directories"
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as exc:
        return f"Error writing file: {exc}"
