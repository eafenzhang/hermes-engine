"""DB maintenance — VACUUM, backup, and repair utilities."""

from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def backup(db_path: str, backup_dir: str | None = None) -> dict:
    """Create a timestamped backup of the SQLite database."""
    src = Path(db_path)
    if not src.exists():
        return {"success": False, "error": "Database not found"}

    dest_dir = Path(backup_dir) if backup_dir else src.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    date_str = time.strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"hermes-{date_str}.db"

    # Use SQLite backup API for consistency
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dest))
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    logger.info("Database backed up to %s (%d bytes)", dest, dest.stat().st_size)
    return {"success": True, "path": str(dest), "size": dest.stat().st_size}


def vacuum(db_path: str) -> dict:
    """Run VACUUM to reclaim space and defragment."""
    conn = sqlite3.connect(db_path)
    before = Path(db_path).stat().st_size
    conn.execute("VACUUM")
    conn.close()
    after = Path(db_path).stat().st_size
    logger.info("VACUUM: %d → %d bytes (saved %d)", before, after, before - after)
    return {"before_bytes": before, "after_bytes": after, "saved_bytes": before - after}
