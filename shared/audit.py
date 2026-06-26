"""Audit log — structured activity logging for compliance."""

from __future__ import annotations

import json
import logging
import sqlite3
import time

logger = logging.getLogger(__name__)


def _init_audit_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            tenant_id TEXT NOT NULL DEFAULT 'default',
            resource TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT DEFAULT '{}',
            ip TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs(tenant_id)")
    conn.commit()
    conn.close()


class AuditLogger:
    """Structured audit logger backed by SQLite."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        _init_audit_db(db_path)

    def log(
        self,
        resource: str,
        action: str,
        actor: str = "system",
        tenant_id: str = "default",
        details: dict | None = None,
        ip: str = "",
    ) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO audit_logs (timestamp, actor, tenant_id, resource, action, details, ip) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), actor, tenant_id, resource, action, json.dumps(details or {}), ip),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.debug("Audit log write failed", exc_info=True)

    def query(self, tenant_id: str | None = None, resource: str | None = None, limit: int = 100) -> list[dict]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM audit_logs WHERE 1=1"
        params: list = []
        if tenant_id:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        if resource:
            sql += " AND resource = ?"
            params.append(resource)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# Lazy singleton
_audit: AuditLogger | None = None


def get_audit(db_path: str = "") -> AuditLogger:
    global _audit
    if _audit is None:
        from pathlib import Path
        path = db_path or str(Path.home() / ".hermes-engine" / "audit.db")
        _audit = AuditLogger(path)
    return _audit
