"""SQLite persistence primitives for the SDD task ledger."""

import os
import sqlite3
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
from urllib.parse import quote

from .newdb_paths import open_database_path, verify_database_path
from .schema_checks import validate_schema


@dataclass(frozen=True)
class TaskRun:
    run_id: str
    task_id: str
    attempt: int
    state: str
    ide: str
    executor_id: str
    owner: Dict[str, Any]
    agent_role: str
    model: Optional[str]
    worktree: str
    branch: str
    base_commit: str
    task_hash: str
    prompt_hash: str
    claimed_at: str
    started_at: Optional[str]
    ended_at: Optional[str]
    duration_ms: Optional[int]
    result_doc: Optional[str]
    error_code: Optional[str]
    error_summary: Optional[str]


_SCHEMA = (
    """CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
    )""",
    """CREATE TABLE tasks (
        task_id TEXT PRIMARY KEY, source_path TEXT NOT NULL,
        status TEXT NOT NULL, priority INTEGER NOT NULL, created_at TEXT NOT NULL,
        task_hash TEXT NOT NULL, prompt_hash TEXT NOT NULL,
        definition_json TEXT NOT NULL
    )""",
    """CREATE TABLE dependencies (
        task_id TEXT NOT NULL REFERENCES tasks(task_id),
        depends_on TEXT NOT NULL REFERENCES tasks(task_id),
        UNIQUE(task_id, depends_on)
    )""",
    """CREATE TABLE runs (
        run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
        attempt INTEGER NOT NULL, state TEXT NOT NULL, ide TEXT NOT NULL,
        executor_id TEXT NOT NULL, owner_json TEXT NOT NULL,
        agent_role TEXT NOT NULL, model TEXT, worktree TEXT NOT NULL,
        branch TEXT NOT NULL, base_commit TEXT NOT NULL,
        task_hash TEXT NOT NULL, prompt_hash TEXT NOT NULL,
        claimed_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
        duration_ms INTEGER, result_doc TEXT, error_code TEXT, error_summary TEXT
    )""",
    """CREATE UNIQUE INDEX uq_runs_active_task
        ON runs(task_id) WHERE state IN ('claimed', 'running')""",
    """CREATE TABLE events (
        run_id TEXT NOT NULL REFERENCES runs(run_id), sequence INTEGER NOT NULL,
        timestamp TEXT NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
        PRIMARY KEY(run_id, sequence)
    )""",
    """CREATE TABLE artifacts (
        run_id TEXT NOT NULL REFERENCES runs(run_id), path TEXT NOT NULL,
        kind TEXT NOT NULL, sha256 TEXT NOT NULL, git_status TEXT NOT NULL,
        included_in_commit INTEGER, PRIMARY KEY(run_id, path)
    )""",
    """CREATE TABLE leases (
        task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
        run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
        owner_token TEXT NOT NULL, claimed_at TEXT NOT NULL,
        refreshed_at TEXT NOT NULL, expires_at TEXT NOT NULL
    )""",
)
def connect(db_path: Path) -> sqlite3.Connection:
    """Open a configured, symlink-checked database and enable its required WAL mode."""
    try:
        sqlite_path, target, parent_fd, pin_fd, identity = open_database_path(db_path)
    except OSError as exc:
        raise ValueError("database_path_unsafe: could not securely open ledger path") from exc
    conn = None
    try:
        uri = "file:" + quote(sqlite_path, safe="/") + "?mode=ro"
        probe = sqlite3.connect(uri, timeout=30, isolation_level=None, uri=True)
        try:
            probe_path = _main_path(probe)
            verify_database_path(target, probe_path, parent_fd, pin_fd, identity)
            _validate_before_wal(probe)
            verify_database_path(target, _main_path(probe), parent_fd, pin_fd, identity)
        finally:
            probe.close()

        uri = "file:" + quote(sqlite_path, safe="/") + "?mode=rw"
        conn = sqlite3.connect(
            uri, timeout=30, isolation_level=None, uri=True, factory=_PinnedConnection,
        )
        conn._retain_path_fds(target, parent_fd, pin_fd, identity)
        parent_fd, pin_fd = -1, None
        conn.row_factory = sqlite3.Row
        verify_database_path(target, _main_path(conn), *conn._path_identity_args)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        _validate_before_wal(conn)
        verify_database_path(target, _main_path(conn), *conn._path_identity_args)
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise ValueError("journal_mode_unavailable: SQLite did not enable WAL")
        verify_database_path(target, _main_path(conn), *conn._path_identity_args)
        return conn
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        if parent_fd >= 0:
            os.close(parent_fd)
        if pin_fd is not None:
            os.close(pin_fd)
        raise ValueError("database_open_failed: SQLite could not open or inspect ledger") from exc
    except BaseException:
        if conn is not None:
            conn.close()
        if parent_fd >= 0:
            os.close(parent_fd)
        if pin_fd is not None:
            os.close(pin_fd)
        raise


class _PinnedConnection(sqlite3.Connection):
    """Keep path identity descriptors alive without an extra ordinary DB fd."""

    def _retain_path_fds(
        self, target: Path, parent_fd: int, pin_fd: Optional[int], identity: Tuple[int, int]
    ) -> None:
        self._target_path = target
        self._path_identity_args = (parent_fd, pin_fd, identity)
        self._path_fds = tuple(fd for fd in (parent_fd, pin_fd) if fd is not None)

    def close(self) -> None:
        fds = getattr(self, "_path_fds", ())
        self._path_fds = ()
        try:
            super().close()
        finally:
            for descriptor in fds:
                with suppress(OSError):
                    os.close(descriptor)

    def __del__(self) -> None:
        with suppress(BaseException):
            self.close()


def _main_path(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        raise ValueError("database_path_invalid: SQLite main path is unavailable")
    return row[2]


def _validate_before_wal(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}
    if not tables:
        return
    if "schema_migrations" not in tables:
        raise ValueError("unknown_schema_version: migration table missing")
    validate_schema(conn, _SCHEMA)
    versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    if versions != {1}:
        raise ValueError(f"unknown_schema_version: {sorted(versions)}")


@contextmanager
def transaction(
    conn: sqlite3.Connection, *, immediate: bool = False
) -> Iterator[sqlite3.Connection]:
    """Run an explicit transaction and roll it back on every failed exit."""
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise


def initialize(conn: sqlite3.Connection) -> None:
    """Create schema v1 once; refuse unknown or incomplete database versions."""
    with transaction(conn, immediate=True):
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )}
        if "schema_migrations" not in tables:
            if tables:
                raise ValueError("unknown_schema_version: migration table missing")
            for statement in _SCHEMA:
                conn.execute(statement)
            applied_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (1, applied_at),
            )
            validate_schema(conn, _SCHEMA)
            return
        validate_schema(conn, _SCHEMA)
        versions = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations")
        }
        if versions != {1}:
            raise ValueError(f"unknown_schema_version: {sorted(versions)}")
