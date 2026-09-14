"""Read-only cross-store snapshot provider for legacy task cleanup.

The ResearchStore cleanup transaction only mutates its own database.  Before
deleting legacy rows it also needs a verified, owner-scoped snapshot of the
conversation store, paper catalog, and knowledge-base manifest.  This module
keeps that maintenance seam small and dependency-free: it opens existing
stores read-only and returns stable counts.  Missing/corrupt stores are
reported as ``unverified`` so the caller remains fail-closed.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Callable

from backend.app.platform.config import BASE_DIR, KB_META_PATH
from backend.app.platform.settings.settings_repository import load_article_settings


def _read_only_connection(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without creating or mutating it."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return sqlite3.connect(f"file:{resolved}?mode=ro", uri=True, timeout=5.0)


def _table_count(path: Path, table: str, *, owner_id: str | None = None) -> int:
    with _read_only_connection(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists is None:
            raise RuntimeError(f"required snapshot table is missing: {table}")
        if owner_id is None:
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        else:
            row = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE owner_id=?", (owner_id,)
            ).fetchone()
    return int(row[0])


def _catalog_count(path: Path) -> int:
    """Count persisted catalog records without initializing the catalog DB."""
    with _read_only_connection(path) as connection:
        for table in ("catalog_papers", "paper_candidates"):
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if exists is not None:
                return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    raise RuntimeError("required catalog table is missing")


def _kb_count(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("knowledge-base manifest is not a list")
    return len(value)


def build_cross_store_snapshot_provider(
    *,
    owner_id: str,
    memory_database_path: Path | str | None = None,
    catalog_database_path: Path | str | None = None,
    kb_metadata_path: Path | str | None = None,
) -> Callable[[], dict]:
    """Build a provider that measures the three external stores on each call.

    Paths are resolved once so dry-run and execute use the same configured
    stores, while values are read afresh to detect a cross-store change during
    the cleanup transaction.  The provider never creates a missing database.
    """
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("owner_id must be a non-empty string")
    memory_path = Path(
        memory_database_path
        or os.getenv("MEMORY_DB_PATH", "")
        or BASE_DIR / "data" / "memory" / "memory.sqlite3"
    )
    if catalog_database_path is None:
        configured = getattr(load_article_settings(), "paper_discovery_db_path", None)
        catalog_path = Path(configured or BASE_DIR / "data" / "paper_search" / "state.sqlite3")
    else:
        catalog_path = Path(catalog_database_path)
    if not catalog_path.is_absolute():
        catalog_path = BASE_DIR / catalog_path
    kb_path = Path(kb_metadata_path or os.getenv("KB_META_PATH", "") or KB_META_PATH)
    if not kb_path.is_absolute():
        kb_path = BASE_DIR / kb_path

    def snapshot() -> dict:
        try:
            return {
                # Session ownership is represented by the existing memory
                # conversation store; the ResearchStore itself is not an
                # external store and is intentionally excluded here.
                "sessions": _table_count(memory_path, "conversations", owner_id=owner_id),
                "catalog": _catalog_count(catalog_path),
                "kb": _kb_count(kb_path),
                "status": "measured",
            }
        except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
            # Do not guess zero for an unavailable store.  ResearchStore will
            # turn this complete-but-unverified shape into a hard execute
            # failure while retaining the audit evidence.
            return {
                "sessions": None,
                "catalog": None,
                "kb": None,
                "status": "unverified",
                "reason": "cross-store snapshot provider unavailable",
            }

    return snapshot


__all__ = ["build_cross_store_snapshot_provider"]
