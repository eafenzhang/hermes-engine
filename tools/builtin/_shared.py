"""Shared utilities for built-in file-system tools.

Provides consistent path-safety checks used by read_file, write_file, and
any future file-system tool.  All file access is scoped to the project root
(plus an optional workspace directory).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# The project root is the only allowed base directory for file I/O.
# Home directory is deliberately excluded — the agent must not access
# personal files (.ssh, .aws, Documents, Desktop, etc.).
_PROJECT_ROOT = Path.cwd().resolve()

# Optional additional workspace root (set by main.py lifespan)
_extra_allowed: Path | None = None


def set_allowed_root(root: Path) -> None:
    """Register an additional allowed root directory (e.g. a workspace)."""
    global _extra_allowed
    _extra_allowed = root.resolve()
    logger.info("Registered additional allowed root: %s", _extra_allowed)


def _allowed_bases() -> list[Path]:
    bases = [_PROJECT_ROOT]
    if _extra_allowed is not None:
        bases.append(_extra_allowed)
    return bases


def is_path_allowed(fpath: Path) -> bool:
    """Return True if *fpath* is inside an allowed base directory.

    Symlinks are resolved before the check so that a symlink pointing
    outside the allowed bases (e.g. ``/home/user/link -> /etc``) is
    rejected even when the link itself lives inside the base.
    """
    try:
        resolved = fpath.resolve(strict=False)
    except (ValueError, OSError, RuntimeError):
        return False

    for base in _allowed_bases():
        try:
            resolved.relative_to(base)
            # Double-verify via string prefix to guard against
            # edge cases in relative_to on Windows UNC paths.
            if str(resolved).startswith(str(base)):
                return True
        except ValueError:
            continue
    return False
