"""API Key store — create, validate, and manage API keys with scopes."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCOPES = frozenset({
    "*", "agent:chat", "agent:chat:stream",
    "memory:read", "memory:write",
    "conversation:read", "conversation:write",
    "skill:read", "skill:write",
    "mcp:read", "mcp:write",
    "admin:read", "admin:write",
})


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_key() -> str:
    return "hm-" + secrets.token_hex(32)


def _init_api_keys_db(db_path: str) -> None:
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            key_hash TEXT UNIQUE NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            name TEXT NOT NULL DEFAULT '',
            scopes TEXT NOT NULL DEFAULT '["*"]',
            created_at REAL NOT NULL,
            expires_at REAL
        )
    """)
    conn.commit()
    conn.close()


class APIKeyStore:
    """SQLite-backed API key CRUD."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _init_api_keys_db(db_path)

    def _conn(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, tenant_id: str = "default", name: str = "", scopes: list[str] | None = None, expires_at: float | None = None) -> dict[str, Any]:
        raw = generate_key()
        key_hash = hash_key(raw)
        scopes_json = __import__("json").dumps(scopes or ["*"])
        conn = self._conn()
        conn.execute(
            "INSERT INTO api_keys (id, key_hash, tenant_id, name, scopes, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (raw[:16], key_hash, tenant_id, name, scopes_json, time.time(), expires_at),
        )
        conn.commit()
        conn.close()
        return {"key": raw, "key_hash": key_hash, "tenant_id": tenant_id, "name": name, "scopes": scopes or ["*"]}

    def validate(self, raw_key: str) -> dict[str, Any] | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (hash_key(raw_key),)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        data = dict(row)
        if data.get("expires_at") and time.time() > data["expires_at"]:
            return None
        data["scopes"] = __import__("json").loads(data.get("scopes", '["*"]'))
        return data

    def list(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        conn = self._conn()
        if tenant_id:
            rows = conn.execute("SELECT id, tenant_id, name, scopes, created_at, expires_at FROM api_keys WHERE tenant_id = ?", (tenant_id,)).fetchall()
        else:
            rows = conn.execute("SELECT id, tenant_id, name, scopes, created_at, expires_at FROM api_keys").fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["scopes"] = __import__("json").loads(d.get("scopes", '["*"]'))
            results.append(d)
        return results

    def delete(self, key_id: str) -> bool:
        conn = self._conn()
        c = conn.execute("DELETE FROM api_keys WHERE id = ? OR key_hash = ?", (key_id, key_id))
        conn.commit()
        conn.close()
        return bool(c.rowcount > 0)


# Module-level singleton
api_key_store: APIKeyStore | None = None


def get_key_store(db_path: str = "") -> APIKeyStore:
    global api_key_store
    if api_key_store is None:
        path = db_path or str(Path.home() / ".hermes-engine" / "keys.db")
        api_key_store = APIKeyStore(path)
    return api_key_store
