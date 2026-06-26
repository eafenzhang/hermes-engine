"""Tool approval gate — require human approval for dangerous tools."""

from __future__ import annotations

import logging
import secrets
import time

logger = logging.getLogger(__name__)

_DEFAULT_DANGEROUS = frozenset({"write_file", "execute_command"})

_pending: dict[str, dict] = {}  # approval_token → {name, arguments, expires_at}


def requires_approval(tool_name: str, required_tools: list[str] | None = None) -> tuple[bool, str | None]:
    """Check if a tool requires approval.  Returns (needs_approval, approval_token)."""
    required = set(required_tools or _DEFAULT_DANGEROUS)
    if tool_name not in required:
        return False, None
    token = "apv-" + secrets.token_hex(16)
    _pending[token] = {
        "name": tool_name,
        "created_at": time.time(),
        "expires_at": time.time() + 300,  # 5 min TTL
    }
    return True, token


def approve(token: str, arguments: dict | None = None) -> dict | None:
    """Approve a pending tool execution.  Returns the pending entry or None."""
    entry = _pending.pop(token, None)
    if entry is None:
        return None
    if time.time() > entry["expires_at"]:
        return None
    entry["arguments"] = arguments or {}
    entry["approved"] = True
    return entry


def cleanup() -> int:
    now = time.time()
    stale = [k for k, v in _pending.items() if now > v["expires_at"]]
    for k in stale:
        del _pending[k]
    return len(stale)
