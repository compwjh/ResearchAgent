"""Independent WAL SQLite store for literature maps.

The store intentionally does not share the knowledge-base or memory database.
All public methods take an owner and apply that owner in the SQL predicate so
an accidental cross-owner identifier can only look like a missing resource.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.literature_maps.domain.analysis import MapAnalysis, MapConversationBinding
from backend.app.literature_maps.domain.errors import LiteratureMapStoreError
from backend.app.literature_maps.domain.identity import deterministic_identity_key
from backend.app.literature_maps.domain.import_diagnostics import normalize_import_diagnostics
from backend.app.literature_maps.domain.models import (
    LiteratureMap,
    MapEdge,
    MapEvent,
    MapGroup,
    MapJob,
    MapPaper,
    MapPreview,
    iso_now,
    validate_edge_metadata,
)
from backend.app.platform.config import BASE_DIR

SCHEMA_VERSION = 8
_WRITE_LOCK = threading.RLock()
_UNSET = object()
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_IMPORT_DIAGNOSTICS_KEY = "import_diagnostics"
_TERMINAL_JOB_STATES = {"completed", "failed", "partial", "stopped"}
_MAX_MAP_NODES = 200
_ANALYSIS_QUEUE_OPERATION = "analysis_queue"
_ANALYSIS_QUEUE_IDEMPOTENCY = "__analysis_queue__"
_ANALYSIS_LEASE_SECONDS = 300
_ANALYSIS_MAX_ATTEMPTS = 3
_AUXILIARY_OPERATIONS = {"preview_page", "expand_batch"}
_AUXILIARY_LEASE_SECONDS = 300
_AUXILIARY_MAX_CLAIMS = 4


def default_database_path() -> Path:
    configured = os.getenv("LITERATURE_MAP_DB_PATH", "").strip()
    return Path(configured) if configured else BASE_DIR / "data" / "literature_maps" / "literature_maps.sqlite3"


class LiteratureMapStore:
    def __init__(self, database_path: Path | str | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @property
    def schema_version(self) -> int:
        with self.connection() as db:
            row = db.execute("SELECT version FROM literature_map_schema ORDER BY version DESC LIMIT 1").fetchone()
        return int(row[0]) if row else 0

    @property
    def journal_mode(self) -> str:
        with self.connection() as db:
            return str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    @contextlib.contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database_path), timeout=10, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with _WRITE_LOCK, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except Exception:
                with contextlib.suppress(sqlite3.Error):
                    db.execute("ROLLBACK")
                raise

    def initialize(self) -> None:
        # ``executescript`` commits any active sqlite transaction before it
        # runs.  It is used only for the idempotent base bootstrap below;
        # every incremental DDL, repair, index, and version marker is
        # applied by the explicit transaction that follows. Runtime writes
        # also use BEGIN IMMEDIATE.
        with _WRITE_LOCK, self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS literature_map_schema(
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS literature_maps(
                    map_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    project_id TEXT,
                    filters_json TEXT NOT NULL,
                    requested_count INTEGER NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    view_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_literature_maps_owner_updated
                    ON literature_maps(owner_id, deleted_at, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_literature_maps_project_owner
                    ON literature_maps(owner_id, project_id, deleted_at);
                CREATE TABLE IF NOT EXISTS literature_map_groups(
                    group_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    name TEXT NOT NULL,
                    color TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_groups_map
                    ON literature_map_groups(map_id, created_at, group_id);
                CREATE TABLE IF NOT EXISTS literature_map_nodes(
                    node_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    identity_key TEXT NOT NULL,
                    external_ids_json TEXT NOT NULL,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    year INTEGER,
                    venue TEXT,
                    abstract TEXT,
                    keywords_json TEXT NOT NULL,
                    citation_count INTEGER,
                    source_url TEXT,
                    provenance_json TEXT NOT NULL,
                    catalog_paper_id TEXT,
                    document_id TEXT,
                    download_status TEXT,
                    position_json TEXT,
                    group_id TEXT,
                    removed_at TEXT,
                    removed_edges_json TEXT,
                    UNIQUE(map_id, identity_key)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_nodes_map ON literature_map_nodes(map_id);
                CREATE TABLE IF NOT EXISTS literature_map_edges(
                    edge_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    kind TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    score REAL,
                    basis TEXT,
                    model_version TEXT,
                    content_hash TEXT,
                    UNIQUE(map_id, kind, source_id, target_id)
                );
                CREATE TABLE IF NOT EXISTS literature_map_jobs(
                    job_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT NOT NULL,
                    cursor_json TEXT NOT NULL,
                    counts_json TEXT NOT NULL,
                    failed_units_json TEXT NOT NULL,
                    idempotency_key TEXT,
                    params_hash TEXT,
                    worker_token TEXT,
                    lease_expires_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(map_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_jobs_map ON literature_map_jobs(map_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS literature_map_events(
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    event_seq INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT NOT NULL,
                    counts_json TEXT NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(map_id, event_seq)
                );
                CREATE TABLE IF NOT EXISTS literature_map_idempotencies(
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    owner_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    PRIMARY KEY(map_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS literature_map_idempotency_migration_log(
                    migration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_version INTEGER NOT NULL,
                    owner_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    canonical_map_id TEXT NOT NULL,
                    canonical_job_id TEXT NOT NULL,
                    duplicate_map_id TEXT NOT NULL,
                    duplicate_job_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    migrated_at TEXT NOT NULL,
                    UNIQUE(owner_id, idempotency_key, duplicate_map_id, duplicate_job_id)
                );
                CREATE TABLE IF NOT EXISTS literature_map_embedding_cache(
                    cache_key TEXT PRIMARY KEY,
                    model_version TEXT NOT NULL,
                    basis TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS literature_map_request_cache(
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    filters_json TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    fields_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_json TEXT,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_request_cache_expiry
                    ON literature_map_request_cache(expires_at);
                CREATE TABLE IF NOT EXISTS literature_map_checkpoints(
                    job_id TEXT NOT NULL,
                    map_id TEXT NOT NULL,
                    unit_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    error_code TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(job_id, unit_key)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_checkpoints_map
                    ON literature_map_checkpoints(map_id, job_id, status);
                CREATE TABLE IF NOT EXISTS literature_map_previews(
                    preview_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    job_id TEXT NOT NULL REFERENCES literature_map_jobs(job_id),
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    base_revision INTEGER NOT NULL,
                    candidates_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    preview_revision INTEGER NOT NULL DEFAULT 1,
                    pagination_json TEXT,
                    node_id TEXT,
                    query_text TEXT,
                    idempotency_key TEXT,
                    params_hash TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(map_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_previews_map
                    ON literature_map_previews(map_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS literature_map_mutation_idempotencies(
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    owner_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(map_id, operation, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS literature_map_analyses(
                    analysis_id TEXT PRIMARY KEY,
                    map_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(map_id, node_id, version),
                    UNIQUE(map_id, node_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_analyses_node
                    ON literature_map_analyses(map_id, node_id, version DESC);
                CREATE TABLE IF NOT EXISTS literature_map_conversation_bindings(
                    binding_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    map_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    project_id_snapshot TEXT,
                    evidence_level TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(map_id, node_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_bindings_conversation
                    ON literature_map_conversation_bindings(owner_id, conversation_id, status);
                CREATE TABLE IF NOT EXISTS literature_map_tags(
                    tag_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    color TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_tags_owner
                    ON literature_map_tags(owner_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_literature_map_tags_owner_name
                    ON literature_map_tags(owner_id, name COLLATE NOCASE);
                CREATE TABLE IF NOT EXISTS literature_map_tag_bindings(
                    map_id TEXT NOT NULL REFERENCES literature_maps(map_id),
                    tag_id TEXT NOT NULL REFERENCES literature_map_tags(tag_id),
                    UNIQUE(map_id, tag_id)
                );
                CREATE INDEX IF NOT EXISTS idx_literature_map_tag_bindings_tag
                    ON literature_map_tag_bindings(tag_id);
                """
            )
            db.execute("BEGIN IMMEDIATE")
            try:
                node_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(literature_map_nodes)").fetchall()}
                if "removed_at" not in node_columns:
                    db.execute("ALTER TABLE literature_map_nodes ADD COLUMN removed_at TEXT")
                if "removed_edges_json" not in node_columns:
                    db.execute("ALTER TABLE literature_map_nodes ADD COLUMN removed_edges_json TEXT")
                if "color_override" not in node_columns:
                    # v6 -> v7 is deliberately additive.  ALTER TABLE is
                    # transactional under the explicit BEGIN IMMEDIATE above,
                    # so a later repair/index/version failure rolls it back.
                    db.execute("ALTER TABLE literature_map_nodes ADD COLUMN color_override TEXT")
                # Normalize legacy references that cannot resolve to a group in
                # the same map. The paper rows themselves remain intact.
                db.execute(
                    "UPDATE literature_map_nodes SET group_id=NULL "
                    "WHERE group_id IS NOT NULL AND NOT EXISTS ("
                    "SELECT 1 FROM literature_map_groups g "
                    "WHERE g.map_id=literature_map_nodes.map_id AND g.group_id=literature_map_nodes.group_id"
                    ")"
                )
                preview_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(literature_map_previews)").fetchall()}
                if "preview_revision" not in preview_columns:
                    # v7 -> v8 is additive: existing preview rows keep their
                    # candidates and receive the frozen revision default.
                    db.execute("ALTER TABLE literature_map_previews ADD COLUMN preview_revision INTEGER NOT NULL DEFAULT 1")
                    preview_columns.add("preview_revision")
                if "pagination_json" not in preview_columns:
                    db.execute("ALTER TABLE literature_map_previews ADD COLUMN pagination_json TEXT")
                    preview_columns.add("pagination_json")
                if "node_id" not in preview_columns:
                    db.execute("ALTER TABLE literature_map_previews ADD COLUMN node_id TEXT")
                if "query_text" not in preview_columns:
                    db.execute("ALTER TABLE literature_map_previews ADD COLUMN query_text TEXT")
                job_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(literature_map_jobs)").fetchall()}
                if "worker_token" not in job_columns:
                    db.execute("ALTER TABLE literature_map_jobs ADD COLUMN worker_token TEXT")
                if "lease_expires_at" not in job_columns:
                    db.execute("ALTER TABLE literature_map_jobs ADD COLUMN lease_expires_at TEXT")
                if "attempts" not in job_columns:
                    db.execute("ALTER TABLE literature_map_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
                if "next_retry_at" not in job_columns:
                    db.execute("ALTER TABLE literature_map_jobs ADD COLUMN next_retry_at TEXT")
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_literature_map_jobs_analysis_claim "
                    "ON literature_map_jobs(map_id, operation, status, next_retry_at)"
                )
                self._repair_legacy_idempotency_bindings(db)
                db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_literature_map_idempotency_owner_key "
                    "ON literature_map_idempotencies(owner_id, idempotency_key)"
                )
                db.execute("INSERT OR IGNORE INTO literature_map_schema(version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, iso_now()))
                db.execute("COMMIT")
            except Exception:
                with contextlib.suppress(sqlite3.Error):
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _repair_legacy_idempotency_bindings(db: sqlite3.Connection) -> None:
        duplicate_keys = db.execute(
            "SELECT owner_id,idempotency_key FROM literature_map_idempotencies "
            "GROUP BY owner_id,idempotency_key HAVING COUNT(*) > 1 ORDER BY owner_id,idempotency_key"
        ).fetchall()
        for duplicate_key in duplicate_keys:
            rows = db.execute(
                "SELECT i.map_id,i.job_id,i.owner_id,i.idempotency_key,"
                "COALESCE(m.deleted_at,'') AS deleted_at,COALESCE(j.created_at,m.created_at,'') AS created_at "
                "FROM literature_map_idempotencies i "
                "LEFT JOIN literature_maps m ON m.map_id=i.map_id "
                "LEFT JOIN literature_map_jobs j ON j.job_id=i.job_id "
                "WHERE i.owner_id=? AND i.idempotency_key=? "
                "ORDER BY CASE WHEN m.deleted_at IS NULL THEN 0 ELSE 1 END, created_at, i.job_id, i.map_id",
                (duplicate_key["owner_id"], duplicate_key["idempotency_key"]),
            ).fetchall()
            if len(rows) < 2:
                continue
            canonical = rows[0]
            for duplicate in rows[1:]:
                db.execute(
                    "INSERT OR IGNORE INTO literature_map_idempotency_migration_log "
                    "(migration_version,owner_id,idempotency_key,canonical_map_id,canonical_job_id,duplicate_map_id,duplicate_job_id,reason,migrated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        SCHEMA_VERSION,
                        duplicate["owner_id"],
                        duplicate["idempotency_key"],
                        canonical["map_id"],
                        canonical["job_id"],
                        duplicate["map_id"],
                        duplicate["job_id"],
                        "duplicate idempotency binding; canonical oldest active job retained",
                        iso_now(),
                    ),
                )
                db.execute(
                    "DELETE FROM literature_map_idempotencies WHERE owner_id=? AND idempotency_key=? AND map_id=? AND job_id=?",
                    (duplicate["owner_id"], duplicate["idempotency_key"], duplicate["map_id"], duplicate["job_id"]),
                )

    def create_map(self, owner_id: str, *, topic: str, name: str | None = None, project_id: str | None = None, filters: dict[str, Any] | None = None, requested_count: int = 30, idempotency_key: str | None = None, params_hash: str | None = None) -> LiteratureMap:
        now = iso_now()
        item = LiteratureMap(uuid.uuid4().hex, owner_id, (name or topic).strip()[:200], topic.strip(), project_id, filters or {}, int(requested_count), 0, "generating", {"viewport": {"x": 0, "y": 0, "scale": 1}, "layers": {"citation": True, "similarity": True}, "label_mode": "all", "node_style": {"fill_mode": "filled", "fill_opacity": 0.3}}, now, now)
        with self.transaction() as db:
            db.execute(
                "INSERT INTO literature_maps(map_id,owner_id,name,topic,project_id,filters_json,requested_count,revision,status,view_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.map_id, owner_id, item.name, item.topic, project_id, _dump(item.filters), item.requested_count, 0, item.status, _dump(item.view_settings), now, now),
            )
        return item

    def create_map_with_job(
        self,
        owner_id: str,
        *,
        topic: str,
        name: str | None = None,
        project_id: str | None = None,
        filters: dict[str, Any] | None = None,
        requested_count: int = 30,
        operation: str = "create",
        idempotency_key: str | None = None,
        params_hash: str | None = None,
    ) -> tuple[LiteratureMap, MapJob, bool]:
        """Create a map and its first job under one write transaction.

        The owner/key unique index is deliberately backed by a separate table:
        the map remains a tombstone after deletion, while the idempotency row is
        removed with the map and cannot be used by a late worker callback.
        """

        now = iso_now()
        filters_value = dict(filters or {})
        params_hash = params_hash or hashlib.sha256(
            _dump(
                {
                    "topic": topic,
                    "name": name,
                    "project_id": project_id,
                    "filters": filters_value,
                    "requested_count": int(requested_count),
                    "operation": operation,
                }
            ).encode("utf-8")
        ).hexdigest()
        with self.transaction() as db:
            if idempotency_key:
                prior = db.execute(
                    "SELECT i.map_id,i.job_id,i.params_hash FROM literature_map_idempotencies i "
                    "JOIN literature_maps m ON m.map_id=i.map_id "
                    "JOIN literature_map_jobs j ON j.job_id=i.job_id "
                    "WHERE i.owner_id=? AND i.idempotency_key=? AND m.deleted_at IS NULL",
                    (owner_id, idempotency_key),
                ).fetchone()
                if prior:
                    if prior["params_hash"] != params_hash:
                        raise ValueError("idempotency conflict")
                    map_row = db.execute("SELECT * FROM literature_maps WHERE map_id=?", (prior["map_id"],)).fetchone()
                    job_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (prior["job_id"],)).fetchone()
                    if map_row is None or job_row is None:
                        raise LiteratureMapStoreError("idempotency state invalid")
                    return _map(map_row), _job(job_row), False
            map_item = LiteratureMap(
                uuid.uuid4().hex,
                owner_id,
                (name or topic).strip()[:200],
                topic.strip(),
                project_id,
                filters_value,
                int(requested_count),
                0,
                "generating",
                {
                    "viewport": {"x": 0, "y": 0, "scale": 1},
                    "layers": {"citation": True, "similarity": True},
                    "label_mode": "all",
                    "node_style": {"fill_mode": "filled", "fill_opacity": 0.3},
                },
                now,
                now,
            )
            db.execute(
                "INSERT INTO literature_maps(map_id,owner_id,name,topic,project_id,filters_json,requested_count,revision,status,view_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (map_item.map_id, owner_id, map_item.name, map_item.topic, project_id, _dump(filters_value), map_item.requested_count, 0, map_item.status, _dump(map_item.view_settings), now, now),
            )
            job = MapJob(
                uuid.uuid4().hex,
                map_item.map_id,
                operation,
                "queued",
                "discover",
                {},
                {"provider_count": 0, "accepted_count": 0, "node_count": 0, "citation_edge_count": 0, "similarity_edge_count": 0, "provider_request_count": 0},
                [],
                None,
                now,
                now,
            )
            db.execute(
                "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.job_id, map_item.map_id, operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), idempotency_key, params_hash, now, now),
            )
            if idempotency_key:
                db.execute(
                    "INSERT INTO literature_map_idempotencies(map_id,owner_id,idempotency_key,params_hash,job_id) VALUES(?,?,?,?,?)",
                    (map_item.map_id, owner_id, idempotency_key, params_hash, job.job_id),
                )
            self._append_event(db, job)
            return map_item, job, True

    def find_idempotent_map(self, owner_id: str, idempotency_key: str, params_hash: str) -> LiteratureMap | None:
        with self.connection() as db:
            row = db.execute("SELECT m.*, i.params_hash FROM literature_map_idempotencies i JOIN literature_maps m ON m.map_id=i.map_id WHERE i.owner_id=? AND i.idempotency_key=? AND m.deleted_at IS NULL", (owner_id, idempotency_key)).fetchone()
        if not row:
            return None
        if row["params_hash"] != params_hash:
            raise ValueError("idempotency conflict")
        return _map(row)

    def bind_map_idempotency(self, map_id: str, owner_id: str, idempotency_key: str, params_hash: str, job_id: str) -> None:
        with self.transaction() as db:
            db.execute("INSERT INTO literature_map_idempotencies(map_id,owner_id,idempotency_key,params_hash,job_id) VALUES(?,?,?,?,?)", (map_id, owner_id, idempotency_key, params_hash, job_id))

    def get_map(self, map_id: str, owner_id: str) -> LiteratureMap | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
        return _map(row) if row else None

    def list_maps(self, owner_id: str, *, limit: int = 100) -> list[LiteratureMap]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM literature_maps WHERE owner_id=? AND deleted_at IS NULL ORDER BY updated_at DESC, map_id DESC LIMIT ?", (owner_id, max(1, min(int(limit), 100)))).fetchall()
        return [_map(row) for row in rows]

    def active_node_counts(self, owner_id: str, map_ids: Iterable[str]) -> dict[str, int]:
        """Count live nodes per map in one statement.

        Uses the same active-node predicate as the rest of the store
        (``removed_at IS NULL`` tombstone exclusion) and keeps counts
        owner-scoped, so a list request never degrades into N+1 queries.
        """
        ids = [str(map_id) for map_id in dict.fromkeys(map_ids)]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self.connection() as db:
            rows = db.execute(
                "SELECT n.map_id, COUNT(*) FROM literature_map_nodes n "
                "JOIN literature_maps m ON m.map_id=n.map_id "
                "WHERE n.map_id IN ("
                + placeholders
                + ") AND n.removed_at IS NULL AND m.owner_id=? AND m.deleted_at IS NULL GROUP BY n.map_id",
                (*ids, owner_id),
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def set_map_status(self, map_id: str, owner_id: str, status: str, *, job_id: str | None = None) -> LiteratureMap | None:
        """Guard map state changes by a currently running job.

        Terminal transitions should use :meth:`finish_job`, which updates the
        job, map and event in one transaction.  This compatibility seam keeps
        older callers from freely rewriting a stopped or completed map.
        """

        now = iso_now()
        with self.transaction() as db:
            if job_id is None:
                job_row = db.execute(
                    "SELECT j.job_id FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
                    "WHERE j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL AND j.status='running' "
                    "ORDER BY j.updated_at DESC LIMIT 1",
                    (map_id, owner_id),
                ).fetchone()
                if job_row is None:
                    return None
                job_id = str(job_row[0])
            result = db.execute(
                "UPDATE literature_maps SET status=?,updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL "
                "AND EXISTS (SELECT 1 FROM literature_map_jobs j WHERE j.job_id=? AND j.map_id=? AND j.status='running')",
                (status, now, map_id, owner_id, job_id, map_id),
            )
            if result.rowcount == 0:
                return None
        return self.get_map(map_id, owner_id)

    def update_map_details(self, map_id: str, owner_id: str, *, expected_revision: int, name: str | None = None, project_id: str | None | object = _UNSET) -> LiteratureMap:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
            if not row:
                raise LookupError("map not found")
            if int(row["revision"]) != int(expected_revision):
                raise ValueError("revision conflict")
            next_name = str(name).strip()[:200] if name is not None else row["name"]
            next_project = row["project_id"] if project_id is _UNSET else project_id
            db.execute("UPDATE literature_maps SET name=?,project_id=?,revision=revision+1,updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (next_name, next_project, iso_now(), map_id, owner_id))
        result = self.get_map(map_id, owner_id)
        if result is None:
            raise LookupError("map not found")
        return result

    def update_view(self, map_id: str, owner_id: str, *, expected_revision: int, positions: list[dict[str, Any]], viewport: dict[str, Any] | None, filters: dict[str, Any] | None, layers: dict[str, Any] | None, label_mode: str | None = None, node_style: Mapping[str, Any] | None = None) -> LiteratureMap:
        if label_mode is not None and label_mode not in {"all", "neighbors", "hidden"}:
            raise ValueError("INVALID_LABEL_MODE")
        if isinstance(filters, Mapping) and "node_style" in filters:
            raise ValueError("INVALID_NODE_STYLE")
        validated_node_style = _validate_node_style(node_style) if node_style is not None else None
        with self.transaction() as db:
            row = db.execute("SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
            if not row:
                raise LookupError("map not found")
            if int(row["revision"]) != int(expected_revision):
                raise ValueError("revision conflict")
            node_ids = {item[0] for item in db.execute("SELECT node_id FROM literature_map_nodes WHERE map_id=?", (map_id,)).fetchall()}
            if any(position.get("node_id") not in node_ids for position in positions):
                raise ValueError("invalid node")
            view = _load(row["view_json"], {})
            if viewport is not None:
                view["viewport"] = viewport
            if filters is not None:
                view["filters"] = filters
            if layers is not None:
                view["layers"] = layers
            if label_mode is not None:
                view["label_mode"] = label_mode
            if validated_node_style is not None:
                view["node_style"] = validated_node_style
            # Internal evidence that the user explicitly saved a view at least
            # once; the revision counter cannot serve as that evidence.
            view["view_initialized"] = True
            for position in positions:
                db.execute("UPDATE literature_map_nodes SET position_json=? WHERE map_id=? AND node_id=?", (_dump({"x": float(position["x"]), "y": float(position["y"])}), map_id, position["node_id"]))
            now = iso_now()
            db.execute("UPDATE literature_maps SET view_json=?,revision=revision+1,updated_at=? WHERE map_id=? AND owner_id=?", (_dump(view), now, map_id, owner_id))
        result = self.get_map(map_id, owner_id)
        if result is None:
            raise LookupError("map not found")
        return result

    def detach_project(self, project_id: str, owner_id: str) -> int:
        with self.transaction() as db:
            result = db.execute("UPDATE literature_maps SET project_id=NULL,revision=revision+1,updated_at=? WHERE project_id=? AND owner_id=? AND deleted_at IS NULL", (iso_now(), project_id, owner_id))
            return result.rowcount

    def delete_map(self, map_id: str, owner_id: str) -> bool:
        with self.transaction() as db:
            row = db.execute("SELECT map_id FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
            if not row:
                return False
            # Mark first; job writers check deleted_at in the same owner scope.
            db.execute("UPDATE literature_maps SET deleted_at=?,status='stopped',updated_at=? WHERE map_id=? AND owner_id=?", (iso_now(), iso_now(), map_id, owner_id))
            db.execute("DELETE FROM literature_map_events WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_checkpoints WHERE map_id=?", (map_id,))
            # Previews reference their worker job.  Remove the child rows
            # before jobs so SQLite's foreign-key guard cannot reject a
            # normal map deletion with an outstanding preview.
            db.execute("DELETE FROM literature_map_previews WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_analyses WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_jobs WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_edges WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_groups WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_nodes WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_idempotencies WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_tag_bindings WHERE map_id=?", (map_id,))
            return True

    def add_nodes(self, map_id: str, owner_id: str, nodes: Iterable[MapPaper], job_id: str | None = None) -> list[MapPaper]:
        values = list(nodes)
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id, job_id=job_id)
            for node in values:
                self._assert_group_reference(db, map_id, node.group_id)
                normalized_color = _validate_color_override(node.color_override)
                db.execute(
                    "INSERT INTO literature_map_nodes(node_id,map_id,identity_key,external_ids_json,title,authors_json,year,venue,abstract,keywords_json,citation_count,source_url,provenance_json,catalog_paper_id,document_id,download_status,position_json,group_id,color_override) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(map_id,identity_key) DO UPDATE SET title=excluded.title,authors_json=excluded.authors_json,year=excluded.year,venue=excluded.venue,abstract=excluded.abstract,keywords_json=excluded.keywords_json,citation_count=excluded.citation_count,source_url=excluded.source_url,provenance_json=excluded.provenance_json,catalog_paper_id=excluded.catalog_paper_id,document_id=excluded.document_id,download_status=excluded.download_status",
                    (node.node_id, map_id, node.identity_key or uuid.uuid4().hex, _dump(node.external_ids), node.title, _dump(list(node.authors)), node.year, node.venue, node.abstract, _dump(list(node.keywords)), node.citation_count, node.source_url, _dump(node.provenance), node.catalog_paper_id, node.document_id, node.download_status, _dump(node.position) if node.position else None, node.group_id, normalized_color),
                )
            self._touch(db, map_id, owner_id)
        return self.list_nodes(map_id, owner_id)

    def list_nodes(self, map_id: str, owner_id: str) -> list[MapPaper]:
        with self.connection() as db:
            rows = db.execute("SELECT n.* FROM literature_map_nodes n JOIN literature_maps m ON m.map_id=n.map_id WHERE n.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY n.rowid", (map_id, owner_id)).fetchall()
        return [_node(row) for row in rows]

    def get_node(self, map_id: str, node_id: str, owner_id: str) -> MapPaper | None:
        with self.connection() as db:
            row = db.execute("SELECT n.* FROM literature_map_nodes n JOIN literature_maps m ON m.map_id=n.map_id WHERE n.map_id=? AND n.node_id=? AND m.owner_id=? AND m.deleted_at IS NULL", (map_id, node_id, owner_id)).fetchone()
        return _node(row) if row else None

    def update_node_styles(
        self,
        map_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        node_ids: Iterable[str],
        color_override: str | None,
    ) -> list[MapPaper]:
        """Atomically assign one optional color override to selected nodes.

        All validation happens before the first UPDATE.  The surrounding
        transaction therefore guarantees that an unknown or removed node can
        never leave a partial batch behind.
        """

        selected = [str(node_id) for node_id in node_ids]
        if not selected or len(selected) > _MAX_MAP_NODES or len(set(selected)) != len(selected):
            raise ValueError("INVALID_NODE_IDS")
        normalized_color = _validate_color_override(color_override)
        with self.transaction() as db:
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            _assert_revision(map_row, expected_revision)
            placeholders = ",".join("?" for _ in selected)
            rows = db.execute(
                f"SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id IN ({placeholders})",
                (map_id, *selected),
            ).fetchall()
            by_id = {str(row["node_id"]): row for row in rows}
            if len(by_id) != len(selected):
                raise LookupError("node not found")
            if any(row["removed_at"] is not None for row in rows):
                raise ValueError("MAP_NODE_REMOVED")
            now = iso_now()
            for node_id in selected:
                db.execute(
                    "UPDATE literature_map_nodes SET color_override=? WHERE map_id=? AND node_id=? AND removed_at IS NULL",
                    (normalized_color, map_id, node_id),
                )
            _increment_map_revision(db, map_id, owner_id, now)
            fresh_rows = db.execute(
                f"SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id IN ({placeholders})",
                (map_id, *selected),
            ).fetchall()
        fresh_by_id = {str(row["node_id"]): _node(row) for row in fresh_rows}
        return [fresh_by_id[node_id] for node_id in selected]

    # ------------------------------------------------------------------
    # Map groups and node presentation membership

    def list_groups(self, map_id: str, owner_id: str) -> list[MapGroup]:
        with self.connection() as db:
            map_row = db.execute(
                "SELECT 1 FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            rows = db.execute(
                "SELECT * FROM literature_map_groups WHERE map_id=? ORDER BY created_at,group_id",
                (map_id,),
            ).fetchall()
        return [_group(row) for row in rows]

    def create_group(
        self,
        map_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        name: str,
        color: str,
    ) -> MapGroup:
        group_name = _validate_group_name(name)
        group_color = _validate_group_color(color)
        with self.transaction() as db:
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            _assert_revision(map_row, expected_revision)
            group_count = int(
                db.execute("SELECT COUNT(*) FROM literature_map_groups WHERE map_id=?", (map_id,)).fetchone()[0]
            )
            if group_count >= 200:
                raise ValueError("GROUP_LIMIT")
            now = iso_now()
            group = MapGroup(uuid.uuid4().hex, map_id, group_name, group_color, now, now)
            db.execute(
                "INSERT INTO literature_map_groups(group_id,map_id,name,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (group.group_id, map_id, group.name, group.color, now, now),
            )
            _increment_map_revision(db, map_id, owner_id, now)
            return group

    def update_group(
        self,
        map_id: str,
        group_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        name: str | None = None,
        color: str | None = None,
    ) -> MapGroup:
        group_key = _validate_group_id(group_id)
        next_name = _validate_group_name(name) if name is not None else None
        next_color = _validate_group_color(color) if color is not None else None
        with self.transaction() as db:
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            _assert_revision(map_row, expected_revision)
            row = db.execute(
                "SELECT * FROM literature_map_groups WHERE map_id=? AND group_id=?",
                (map_id, group_key),
            ).fetchone()
            if row is None:
                raise LookupError("group not found")
            current_name = str(row["name"])
            current_color = str(row["color"])
            if (next_name is None or next_name == current_name) and (next_color is None or next_color == current_color):
                return _group(row)
            updated_name = next_name if next_name is not None else current_name
            updated_color = next_color if next_color is not None else current_color
            now = iso_now()
            db.execute(
                "UPDATE literature_map_groups SET name=?,color=?,updated_at=? WHERE map_id=? AND group_id=?",
                (updated_name, updated_color, now, map_id, group_key),
            )
            _increment_map_revision(db, map_id, owner_id, now)
            fresh = db.execute(
                "SELECT * FROM literature_map_groups WHERE map_id=? AND group_id=?",
                (map_id, group_key),
            ).fetchone()
            return _group(fresh)

    def delete_group(self, map_id: str, group_id: str, owner_id: str, *, expected_revision: int) -> None:
        group_key = _validate_group_id(group_id)
        with self.transaction() as db:
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            _assert_revision(map_row, expected_revision)
            group_row = db.execute(
                "SELECT 1 FROM literature_map_groups WHERE map_id=? AND group_id=?",
                (map_id, group_key),
            ).fetchone()
            if group_row is None:
                raise LookupError("group not found")
            db.execute("UPDATE literature_map_nodes SET group_id=NULL WHERE map_id=? AND group_id=?", (map_id, group_key))
            db.execute("DELETE FROM literature_map_groups WHERE map_id=? AND group_id=?", (map_id, group_key))
            _increment_map_revision(db, map_id, owner_id, iso_now())

    def assign_node_group(
        self,
        map_id: str,
        owner_id: str,
        *,
        node_id: str,
        expected_revision: int,
        group_id: str | None,
    ) -> MapPaper:
        group_key = _validate_group_id(group_id) if group_id is not None else None
        with self.transaction() as db:
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            _assert_revision(map_row, expected_revision)
            node_row = db.execute(
                "SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                (map_id, node_id),
            ).fetchone()
            if node_row is None:
                raise LookupError("node not found")
            if node_row["removed_at"] is not None:
                raise ValueError("MAP_NODE_REMOVED")
            if group_key is not None:
                group_row = db.execute(
                    "SELECT 1 FROM literature_map_groups WHERE map_id=? AND group_id=?",
                    (map_id, group_key),
                ).fetchone()
                if group_row is None:
                    raise LookupError("group not found")
            if node_row["group_id"] == group_key:
                return _node(node_row)
            now = iso_now()
            db.execute(
                "UPDATE literature_map_nodes SET group_id=? WHERE map_id=? AND node_id=? AND removed_at IS NULL",
                (group_key, map_id, node_id),
            )
            _increment_map_revision(db, map_id, owner_id, now)
            fresh = db.execute(
                "SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                (map_id, node_id),
            ).fetchone()
            return _node(fresh)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Map-level tag classification (Spec043).  Tags are owner-scoped and
    # entirely independent from node groups.  Critically, none of these
    # writes ever touch ``literature_maps.revision`` (no
    # ``_increment_map_revision`` call), so tag activity cannot collide with
    # the ``PATCH /view`` optimistic-lock path.
    # ------------------------------------------------------------------
    def list_tags(self, owner_id: str) -> list[MapTag]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM literature_map_tags WHERE owner_id=? ORDER BY created_at, tag_id",
                (owner_id,),
            ).fetchall()
        return [_tag(row) for row in rows]

    def create_tag(self, owner_id: str, name: str, color: str | None = None) -> MapTag:
        tag_name = _validate_tag_name(name)
        tag_color = _validate_tag_color(color)
        tag_id = uuid.uuid4().hex
        now = iso_now()
        with self.transaction() as db:
            try:
                db.execute(
                    "INSERT INTO literature_map_tags(tag_id,owner_id,name,color,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (tag_id, owner_id, tag_name, tag_color, now, now),
                )
            except sqlite3.IntegrityError:
                # UNIQUE(owner_id, name COLLATE NOCASE) violation.
                raise ValueError("TAG_NAME_CONFLICT") from None
        return MapTag(tag_id, owner_id, tag_name, tag_color, now, now)

    def update_tag(
        self,
        owner_id: str,
        tag_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
    ) -> MapTag:
        tag_key = _validate_tag_id(tag_id)
        next_name = _validate_tag_name(name) if name is not None else None
        next_color = _validate_tag_color(color) if color is not None else None
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM literature_map_tags WHERE tag_id=? AND owner_id=?",
                (tag_key, owner_id),
            ).fetchone()
            if row is None:
                raise LookupError("tag not found")
            current_name = str(row["name"])
            current_color = str(row["color"])
            if (next_name is None or next_name == current_name) and (next_color is None or next_color == current_color):
                return _tag(row)
            updated_name = next_name if next_name is not None else current_name
            updated_color = next_color if next_color is not None else current_color
            now = iso_now()
            try:
                db.execute(
                    "UPDATE literature_map_tags SET name=?,color=?,updated_at=? WHERE tag_id=? AND owner_id=?",
                    (updated_name, updated_color, now, tag_key, owner_id),
                )
            except sqlite3.IntegrityError:
                raise ValueError("TAG_NAME_CONFLICT") from None
            fresh = db.execute(
                "SELECT * FROM literature_map_tags WHERE tag_id=? AND owner_id=?",
                (tag_key, owner_id),
            ).fetchone()
        return _tag(fresh)

    def delete_tag(self, owner_id: str, tag_id: str) -> int:
        tag_key = _validate_tag_id(tag_id)
        with self.transaction() as db:
            row = db.execute(
                "SELECT 1 FROM literature_map_tags WHERE tag_id=? AND owner_id=?",
                (tag_key, owner_id),
            ).fetchone()
            if row is None:
                raise LookupError("tag not found")
            # Unbind every map from this tag atomically, then drop the tag.
            # Bindings are deleted first so the FK on tag_id is never violated.
            unbound = db.execute(
                "DELETE FROM literature_map_tag_bindings WHERE tag_id=?", (tag_key,)
            ).rowcount
            db.execute(
                "DELETE FROM literature_map_tags WHERE tag_id=? AND owner_id=?",
                (tag_key, owner_id),
            )
        return unbound

    def set_map_tags(self, map_id: str, owner_id: str, tag_ids: Iterable[str]) -> list[dict[str, Any]]:
        requested = [str(tag_id).strip() for tag_id in (tag_ids or [])]
        requested = [tag_id for tag_id in requested if tag_id]
        if len(requested) > 20:
            raise ValueError("TAG_LIMIT")
        # De-duplicate while preserving first-seen order.
        seen: set[str] = set()
        ordered: list[str] = []
        for tag_id in requested:
            if tag_id not in seen:
                seen.add(tag_id)
                ordered.append(tag_id)
        with self.transaction() as db:
            map_row = db.execute(
                "SELECT 1 FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            placeholders = ",".join("?" for _ in ordered) or "?"
            rows = db.execute(
                f"SELECT tag_id,name,color FROM literature_map_tags WHERE owner_id=? AND tag_id IN ({placeholders})",
                (owner_id, *ordered),
            ).fetchall()
            found = {str(row["tag_id"]): row for row in rows}
            if any(tag_id not in found for tag_id in ordered):
                # Non-existent or cross-owner tag_id: same error, no leak.
                raise ValueError("TAG_NOT_FOUND")
            # Replace the full binding set so PUT semantics stay idempotent.
            db.execute("DELETE FROM literature_map_tag_bindings WHERE map_id=?", (map_id,))
            for tag_id in ordered:
                db.execute(
                    "INSERT OR IGNORE INTO literature_map_tag_bindings(map_id,tag_id) VALUES(?,?)",
                    (map_id, tag_id),
                )
            return [
                {"tag_id": tag_id, "name": str(found[tag_id]["name"]), "color": str(found[tag_id]["color"])}
                for tag_id in ordered
            ]

    def list_map_tags(self, map_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            map_row = db.execute(
                "SELECT 1 FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            rows = db.execute(
                "SELECT t.tag_id,t.name,t.color FROM literature_map_tag_bindings b "
                "JOIN literature_map_tags t ON t.tag_id=b.tag_id "
                "WHERE b.map_id=? AND t.owner_id=? ORDER BY t.created_at, t.tag_id",
                (map_id, owner_id),
            ).fetchall()
        return [{"tag_id": str(row["tag_id"]), "name": str(row["name"]), "color": str(row["color"])} for row in rows]

    # ------------------------------------------------------------------
    # Map analysis and conversation bridge.  These rows intentionally live
    # beside map jobs but never update ``literature_maps.status``: an
    # analysis is an auxiliary user action, not a graph-building job.
    def create_analysis(
        self,
        map_id: str,
        node_id: str,
        owner_id: str,
        *,
        evidence_level: str,
        source_version: str,
        model_id: str,
        idempotency_key: str,
        params_hash: str | None = None,
        queue_job_id: str | None = None,
    ) -> tuple[MapAnalysis, MapJob, bool]:
        if evidence_level not in {"abstract", "full"}:
            raise ValueError("INVALID_EVIDENCE_LEVEL")
        if not str(idempotency_key or "").strip():
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        with self.transaction() as db:
            return self._create_analysis_tx(
                db,
                map_id,
                node_id,
                owner_id,
                evidence_level=evidence_level,
                source_version=source_version,
                model_id=model_id,
                idempotency_key=idempotency_key,
                params_hash=params_hash,
                queue_job_id=queue_job_id,
            )

    def _create_analysis_tx(
        self,
        db: sqlite3.Connection,
        map_id: str,
        node_id: str,
        owner_id: str,
        *,
        evidence_level: str,
        source_version: str,
        model_id: str,
        idempotency_key: str,
        params_hash: str | None = None,
        queue_job_id: str | None = None,
    ) -> tuple[MapAnalysis, MapJob, bool]:
        map_row = db.execute(
            "SELECT map_id FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
            (map_id, owner_id),
        ).fetchone()
        node_row = db.execute(
            "SELECT node_id FROM literature_map_nodes WHERE map_id=? AND node_id=? AND removed_at IS NULL",
            (map_id, node_id),
        ).fetchone()
        if map_row is None or node_row is None:
            raise LookupError("map or node not found")
        prior = db.execute(
            "SELECT * FROM literature_map_analyses WHERE map_id=? AND node_id=? AND idempotency_key=?",
            (map_id, node_id, idempotency_key),
        ).fetchone()
        if prior is not None:
            if (
                prior["evidence_level"] != evidence_level
                or prior["source_version"] != source_version
                or prior["model_id"] != model_id
            ):
                raise ValueError("idempotency conflict")
            job_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (prior["job_id"],)).fetchone()
            if job_row is None:
                raise LiteratureMapStoreError("MAP_ANALYSIS_STATE_INVALID")
            return _analysis(prior), _job(job_row), False
        now = iso_now()
        version_row = db.execute(
            "SELECT COALESCE(MAX(version), 0) AS latest FROM literature_map_analyses WHERE map_id=? AND node_id=?",
            (map_id, node_id),
        ).fetchone()
        version = int(version_row["latest"] or 0) + 1
        analysis_id = uuid.uuid4().hex
        # Prefix the key so an analysis cannot accidentally reuse a map
        # creation key in the shared legacy jobs table.
        job_key = f"analysis:{idempotency_key}"
        cursor = {"analysis_id": analysis_id, "node_id": node_id, "evidence_level": evidence_level}
        if queue_job_id:
            cursor["queue_job_id"] = queue_job_id
        job = MapJob(
            uuid.uuid4().hex,
            map_id,
            "analysis",
            "queued",
            "analysis",
            cursor,
            {"analysis_version": version},
            [],
            job_key,
            now,
            now,
        )
        db.execute(
            "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (job.job_id, map_id, job.operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), job_key, params_hash, now, now),
        )
        db.execute(
            "INSERT INTO literature_map_analyses(analysis_id,map_id,node_id,version,status,evidence_level,source_version,model_id,job_id,idempotency_key,result_json,error_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (analysis_id, map_id, node_id, version, "pending", evidence_level, source_version, model_id, job.job_id, idempotency_key, None, None, now, now),
        )
        self._append_event(db, job)
        analysis = MapAnalysis(analysis_id, map_id, node_id, version, "pending", evidence_level, source_version, model_id, job.job_id, None, None, idempotency_key, now, now)
        return analysis, job, True

    def get_analysis(self, analysis_id: str, map_id: str, owner_id: str) -> MapAnalysis | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT a.* FROM literature_map_analyses a JOIN literature_maps m ON m.map_id=a.map_id WHERE a.analysis_id=? AND a.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (analysis_id, map_id, owner_id),
            ).fetchone()
        return _analysis(row) if row else None

    def list_analyses(self, map_id: str, node_id: str, owner_id: str) -> list[MapAnalysis]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT a.* FROM literature_map_analyses a JOIN literature_maps m ON m.map_id=a.map_id WHERE a.map_id=? AND a.node_id=? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY a.version DESC",
                (map_id, node_id, owner_id),
            ).fetchall()
        return [_analysis(row) for row in rows]

    def get_analysis_job(self, analysis_id: str, map_id: str, owner_id: str) -> MapJob | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT j.* FROM literature_map_jobs j JOIN literature_map_analyses a ON a.job_id=j.job_id JOIN literature_maps m ON m.map_id=a.map_id WHERE a.analysis_id=? AND a.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (analysis_id, map_id, owner_id),
            ).fetchone()
        return _job(row) if row else None

    # ------------------------------------------------------------------
    # Persistent abstract-analysis queue.  The aggregate is one ordinary
    # MapJob row; child rows remain the existing analysis jobs.  Queue state
    # and item metadata live in the aggregate cursor so no second scheduler
    # or result table is introduced.
    def ensure_analysis_queue(
        self,
        map_id: str,
        owner_id: str,
        *,
        idempotency_key: str,
        candidates: Iterable[Mapping[str, Any]] = (),
        params_hash: str | None = None,
    ) -> dict[str, Any]:
        if not str(idempotency_key or "").strip():
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        candidate_values = [dict(item) for item in candidates]
        effective_hash = params_hash or hashlib.sha256(_dump(candidate_values).encode("utf-8")).hexdigest()
        with self.transaction() as db:
            self._assert_map_exists(db, map_id, owner_id)
            replay = self._queue_command_replay(db, map_id, owner_id, "analysis_queue:ensure", idempotency_key, effective_hash)
            if replay is not None:
                queue_id = str(replay.get("queue_job_id") or "")
            else:
                row = self._queue_row(db, map_id, owner_id)
                now = iso_now()
                if row is None:
                    queue_id = uuid.uuid4().hex
                    job = MapJob(
                        queue_id,
                        map_id,
                        _ANALYSIS_QUEUE_OPERATION,
                        "active",
                        "analysis_queue",
                        {"queue_version": 1, "pause_reason": None, "items": {}},
                        {"total": 0, "completed": 0, "queued": 0, "running": 0, "failed": 0, "skipped": 0},
                        [],
                        _ANALYSIS_QUEUE_IDEMPOTENCY,
                        now,
                        now,
                    )
                    db.execute(
                        "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (job.job_id, map_id, job.operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), job.idempotency_key, effective_hash, now, now),
                    )
                    self._append_event(db, job, event_type="queued")
                    row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (queue_id,)).fetchone()
                else:
                    queue_id = str(row["job_id"])
                if candidate_values:
                    self._update_queue_items_tx(db, row, owner_id, candidate_values)
                elif row is not None and not candidate_values:
                    # An explicit ensure with an empty candidate set is still
                    # a durable no-op; do not erase a previously populated
                    # queue when a caller is only replaying the handle.
                    pass
                self._remember_queue_command(db, map_id, owner_id, "analysis_queue:ensure", idempotency_key, effective_hash, {"queue_job_id": queue_id})
        return self.get_analysis_queue(map_id, owner_id)

    def get_analysis_queue(self, map_id: str, owner_id: str) -> dict[str, Any]:
        with self.connection() as db:
            self._assert_map_exists_readonly(db, map_id, owner_id)
            row = self._queue_row(db, map_id, owner_id)
            if row is None:
                return {
                    "map_id": map_id,
                    "queue_job_id": None,
                    "state": "completed",
                    "pause_reason": None,
                    "counts": {"total": 0, "completed": 0, "queued": 0, "running": 0, "failed": 0, "skipped": 0},
                    "current": None,
                    "failed_items": [],
                    "skipped_items": [],
                }
            return self._queue_projection_tx(db, row)

    def pause_analysis_queue(self, map_id: str, owner_id: str, *, idempotency_key: str) -> dict[str, Any]:
        return self._set_analysis_queue_state(map_id, owner_id, state="paused", pause_reason="user", idempotency_key=idempotency_key)

    def resume_analysis_queue(self, map_id: str, owner_id: str, *, idempotency_key: str) -> dict[str, Any]:
        return self._set_analysis_queue_state(map_id, owner_id, state="active", pause_reason=None, idempotency_key=idempotency_key)

    def retry_analysis_queue(
        self,
        map_id: str,
        owner_id: str,
        *,
        idempotency_key: str,
        analysis_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        requested = sorted({str(item) for item in (analysis_ids or ()) if str(item).strip()})
        params_hash = hashlib.sha256(_dump({"analysis_ids": requested}).encode("utf-8")).hexdigest()
        with self.transaction() as db:
            row = self._queue_row(db, map_id, owner_id)
            if row is None:
                raise LookupError("analysis queue not found")
            replay = self._queue_command_replay(db, map_id, owner_id, "analysis_queue:retry", idempotency_key, params_hash)
            if replay is None:
                cursor = _load(row["cursor_json"], {})
                items = cursor.get("items", {}) if isinstance(cursor, Mapping) else {}
                if not isinstance(items, dict):
                    items = {}
                selected = set(requested)
                retryable = []
                for item in items.values():
                    if not isinstance(item, Mapping):
                        continue
                    if selected and str(item.get("analysis_id")) not in selected:
                        continue
                    job_id = str(item.get("job_id") or "")
                    child = db.execute(
                        "SELECT status FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='analysis'",
                        (job_id, map_id),
                    ).fetchone()
                    analysis_row = db.execute(
                        "SELECT error_json FROM literature_map_analyses WHERE analysis_id=? AND map_id=?",
                        (str(item.get("analysis_id") or ""), map_id),
                    ).fetchone()
                    error = _safe_analysis_error(_load(analysis_row["error_json"], None) if analysis_row else None) or {}
                    if child is None or child["status"] != "failed":
                        continue
                    if bool(error.get("retryable", item.get("retryable", False))) is not True:
                        continue
                    retryable.append(item)
                if not retryable:
                    raise ValueError("MAP_NO_RETRYABLE_UNITS")
                now = iso_now()
                for item in retryable:
                    job_id = str(item.get("job_id") or "")
                    changed = db.execute(
                        "UPDATE literature_map_jobs SET status='queued',worker_token=NULL,lease_expires_at=NULL,attempts=0,next_retry_at=NULL,updated_at=? WHERE job_id=? AND map_id=? AND operation='analysis' AND status='failed'",
                        (now, job_id, map_id),
                    )
                    if changed.rowcount != 1:
                        continue
                    db.execute(
                        "UPDATE literature_map_analyses SET status='pending',error_json=NULL,updated_at=? WHERE job_id=? AND map_id=? AND status='failed'",
                        (now, job_id, map_id),
                    )
                    refreshed = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (job_id,)).fetchone()
                    if refreshed is not None:
                        self._append_event(db, _job(refreshed), event_type="retry")
                queue_state = str(row["status"])
                if queue_state != "paused":
                    queue_state = "active"
                cursor["pause_reason"] = cursor.get("pause_reason") if queue_state == "paused" else None
                counts = self._queue_counts_tx(db, map_id, cursor)
                db.execute(
                    "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=?",
                    (queue_state, _dump(cursor), _dump(counts), now, row["job_id"], map_id, _ANALYSIS_QUEUE_OPERATION),
                )
                self._remember_queue_command(db, map_id, owner_id, "analysis_queue:retry", idempotency_key, params_hash, {"queue_job_id": row["job_id"]})
            self._refresh_expansion_batch_projections_tx(db, map_id, owner_id)
        return self.get_analysis_queue(map_id, owner_id)

    def pause_analysis_queue_for_failure(self, map_id: str, owner_id: str, *, pause_reason: str) -> dict[str, Any]:
        """Persist a safe configuration/auth pause caused by a child worker."""

        with self.transaction() as db:
            row = self._queue_row(db, map_id, owner_id)
            if row is None:
                pass
            else:
                cursor = _load(row["cursor_json"], {})
                if not isinstance(cursor, dict):
                    cursor = {}
                cursor["pause_reason"] = str(pause_reason)[:80]
                counts = self._queue_counts_tx(db, map_id, cursor)
                now = iso_now()
                changed = db.execute(
                    "UPDATE literature_map_jobs SET status='paused',cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=? AND status IN ('active','partial','completed')",
                    (_dump(cursor), _dump(counts), now, row["job_id"], map_id, _ANALYSIS_QUEUE_OPERATION),
                )
                fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                if changed.rowcount == 1 and fresh is not None:
                    self._append_event(db, _job(fresh), event_type="paused", error_code="MAP_ANALYSIS_CONFIG_REQUIRED")
        return self.get_analysis_queue(map_id, owner_id)

    def requeue_due_analysis_jobs(self, map_id: str, owner_id: str) -> list[MapJob]:
        """Atomically promote due retryable queue children back to ``queued``.

        The retry timestamp and attempt cap are durable, so a scheduler can
        call this method repeatedly without creating duplicate attempts. A
        user-paused queue is never promoted; a partial queue becomes active
        only when at least one child was actually promoted.
        """

        promoted: list[MapJob] = []
        with self.transaction() as db:
            queue_row = self._queue_row(db, map_id, owner_id)
            if queue_row is None or str(queue_row["status"]) == "paused":
                return promoted
            now = iso_now()
            rows = db.execute(
                "SELECT j.* FROM literature_map_jobs j "
                "JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.map_id=? AND j.operation='analysis' AND j.status='failed' "
                "AND j.next_retry_at IS NOT NULL AND j.next_retry_at<=? "
                "AND j.attempts < ? AND m.owner_id=? AND m.deleted_at IS NULL "
                "ORDER BY j.next_retry_at,j.updated_at,j.created_at",
                (map_id, now, _ANALYSIS_MAX_ATTEMPTS, owner_id),
            ).fetchall()
            queue_job_id = str(queue_row["job_id"])
            for row in rows:
                cursor = _load(row["cursor_json"], {})
                if not isinstance(cursor, Mapping) or str(cursor.get("queue_job_id") or "") != queue_job_id:
                    continue
                changed = db.execute(
                    "UPDATE literature_map_jobs SET status='queued',worker_token=NULL,lease_expires_at=NULL,next_retry_at=NULL,updated_at=? "
                    "WHERE job_id=? AND map_id=? AND operation='analysis' AND status='failed' "
                    "AND next_retry_at IS NOT NULL AND next_retry_at<=? AND attempts < ?",
                    (now, row["job_id"], map_id, now, _ANALYSIS_MAX_ATTEMPTS),
                )
                if changed.rowcount != 1:
                    continue
                db.execute(
                    "UPDATE literature_map_analyses SET status='pending',error_json=NULL,updated_at=? "
                    "WHERE job_id=? AND map_id=? AND status='failed'",
                    (now, row["job_id"], map_id),
                )
                fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                if fresh is not None:
                    child = _job(fresh)
                    self._append_event(db, child, event_type="retry")
                    promoted.append(child)
            if promoted:
                queue_cursor = _load(queue_row["cursor_json"], {})
                if not isinstance(queue_cursor, dict):
                    queue_cursor = {}
                counts = self._queue_counts_tx(db, map_id, queue_cursor)
                db.execute(
                    "UPDATE literature_map_jobs SET status='active',counts_json=?,updated_at=? "
                    "WHERE job_id=? AND map_id=? AND operation=? AND status!='paused'",
                    (_dump(counts), now, queue_job_id, map_id, _ANALYSIS_QUEUE_OPERATION),
                )
        return promoted

    def next_queued_analysis_job(self, map_id: str, owner_id: str) -> str | None:
        """Return one due child id; its claim remains a separate atomic CAS."""

        with self.connection() as db:
            row = self._queue_row(db, map_id, owner_id)
            if row is None or row["status"] != "active":
                return None
            running = db.execute(
                "SELECT 1 FROM literature_map_jobs WHERE map_id=? AND operation='analysis' AND status='running' LIMIT 1",
                (map_id,),
            ).fetchone()
            if running is not None:
                return None
            cursor = _load(row["cursor_json"], {})
            items = cursor.get("items", {}) if isinstance(cursor, Mapping) else {}
            if not isinstance(items, Mapping):
                return None
            now = iso_now()
            for item in items.values():
                if not isinstance(item, Mapping) or item.get("status") not in {"queued", "pending"}:
                    continue
                job_id = str(item.get("job_id") or "")
                child = db.execute(
                    "SELECT job_id,next_retry_at FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='analysis' AND status='queued'",
                    (job_id, map_id),
                ).fetchone()
                if child is not None and (child["next_retry_at"] is None or str(child["next_retry_at"]) <= now):
                    return job_id
        return None

    def has_running_analysis_job(self, map_id: str, owner_id: str) -> bool:
        """Return whether any owner-scoped analysis currently holds the map slot."""

        with self.connection() as db:
            row = db.execute(
                "SELECT 1 FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.map_id=? AND j.operation='analysis' AND j.status='running' "
                "AND m.owner_id=? AND m.deleted_at IS NULL LIMIT 1",
                (map_id, owner_id),
            ).fetchone()
        return row is not None

    def running_analysis_jobs(self, owner_id: str | None = None) -> list[tuple[str, str, str | None]]:
        """Return running analysis leases for in-process deadline wakeups.

        The lease deadline is internal scheduler state; callers use the owner
        and map identifiers only to dispatch a bounded recovery callback.
        Deleted maps are excluded so an old worker cannot resurrect removed
        work during a runtime reset.
        """

        with self.connection() as db:
            clause = [
                "j.operation='analysis'",
                "j.status='running'",
                "m.deleted_at IS NULL",
            ]
            params: list[Any] = []
            if owner_id is not None:
                clause.append("m.owner_id=?")
                params.append(owner_id)
            rows = db.execute(
                "SELECT j.map_id,m.owner_id,j.lease_expires_at "
                "FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE " + " AND ".join(clause) + " ORDER BY j.updated_at",
                tuple(params),
            ).fetchall()
        return [
            (str(row["map_id"]), str(row["owner_id"]), row["lease_expires_at"])
            for row in rows
        ]

    def recover_analysis_jobs(self, owner_id: str | None = None) -> list[MapJob]:
        """Requeue orphan analysis workers once; paused queues remain paused."""

        recovered: list[MapJob] = []
        with self.transaction() as db:
            now = iso_now()
            clause = "j.operation='analysis' AND j.status='running' AND m.deleted_at IS NULL AND (j.lease_expires_at IS NULL OR j.lease_expires_at<=?)"
            params: list[Any] = [now]
            if owner_id is not None:
                clause += " AND m.owner_id=?"
                params.append(owner_id)
            rows = db.execute(
                "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE " + clause,
                tuple(params),
            ).fetchall()
            for row in rows:
                # Owner is already constrained by the join; a narrow owner
                # lookup keeps recovery fail-closed without exposing it in the
                # child job projection.
                owner_row = db.execute("SELECT owner_id FROM literature_maps WHERE map_id=?", (row["map_id"],)).fetchone()
                resolved_owner = str(owner_row["owner_id"]) if owner_row else owner_id
                queue_row = self._queue_row(db, row["map_id"], resolved_owner) if resolved_owner else None
                if int(row["attempts"] or 0) >= _ANALYSIS_MAX_ATTEMPTS:
                    changed = db.execute(
                        "UPDATE literature_map_jobs SET status='failed',step='finished',worker_token=NULL,lease_expires_at=NULL,next_retry_at=NULL,updated_at=? "
                        "WHERE job_id=? AND status='running' AND (lease_expires_at IS NULL OR lease_expires_at<=?)",
                        (now, row["job_id"], now),
                    )
                    if changed.rowcount != 1:
                        continue
                    safe_error = {
                        "code": "MAP_ANALYSIS_LEASE_EXPIRED",
                        "message": "分析租约已过期，已停止自动重试",
                        "retryable": False,
                    }
                    db.execute(
                        "UPDATE literature_map_analyses SET status='failed',result_json=NULL,error_json=?,updated_at=? WHERE job_id=? AND status='running'",
                        (_dump(safe_error), now, row["job_id"]),
                    )
                    fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                    if fresh is not None:
                        terminal = _job(fresh)
                        self._append_event(db, terminal, event_type="failed", error_code=safe_error["code"])
                    if queue_row is not None:
                        queue_cursor = _load(queue_row["cursor_json"], {})
                        if not isinstance(queue_cursor, dict):
                            queue_cursor = {}
                        queue_counts = self._queue_counts_tx(db, row["map_id"], queue_cursor)
                        queue_state = str(queue_row["status"])
                        if queue_state != "paused":
                            queue_state = "active" if queue_counts["queued"] or queue_counts["running"] else ("partial" if queue_counts["failed"] else "completed")
                        db.execute(
                            "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND operation=?",
                            (queue_state, _dump(queue_cursor), _dump(queue_counts), now, queue_row["job_id"], _ANALYSIS_QUEUE_OPERATION),
                        )
                    continue
                changed = db.execute(
                    "UPDATE literature_map_jobs SET status='queued',worker_token=NULL,lease_expires_at=NULL,next_retry_at=NULL,updated_at=? "
                    "WHERE job_id=? AND status='running' AND (lease_expires_at IS NULL OR lease_expires_at<=?)",
                    (now, row["job_id"], now),
                )
                if changed.rowcount != 1:
                    continue
                db.execute(
                    "UPDATE literature_map_analyses SET status='pending',updated_at=? WHERE job_id=? AND status='running'",
                    (now, row["job_id"]),
                )
                fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                if fresh is not None:
                    child = _job(fresh)
                    recovered.append(child)
                    if queue_row is not None:
                        queue_cursor = _load(queue_row["cursor_json"], {})
                        if not isinstance(queue_cursor, dict):
                            queue_cursor = {}
                        queue_counts = self._queue_counts_tx(db, row["map_id"], queue_cursor)
                        queue_state = str(queue_row["status"])
                        if queue_state != "paused":
                            queue_state = "active" if queue_counts["queued"] or queue_counts["running"] else ("partial" if queue_counts["failed"] else "completed")
                        db.execute(
                            "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND operation=?",
                            (queue_state, _dump(queue_cursor), _dump(queue_counts), now, queue_row["job_id"], _ANALYSIS_QUEUE_OPERATION),
                        )
        return recovered

    def active_analysis_queues(self, owner_id: str | None = None) -> list[tuple[str, str]]:
        """List active queues with unfinished children for restart scheduling."""

        with self.connection() as db:
            clause = [
                "q.operation=?",
                "q.status='active'",
                "m.deleted_at IS NULL",
                "EXISTS (SELECT 1 FROM literature_map_jobs c WHERE c.map_id=q.map_id AND c.operation='analysis' AND c.status IN ('queued','running'))",
            ]
            params: list[Any] = [_ANALYSIS_QUEUE_OPERATION]
            if owner_id is not None:
                clause.append("m.owner_id=?")
                params.append(owner_id)
            rows = db.execute(
                "SELECT q.map_id,m.owner_id FROM literature_map_jobs q JOIN literature_maps m ON m.map_id=q.map_id WHERE "
                + " AND ".join(clause)
                + " ORDER BY q.updated_at",
                tuple(params),
            ).fetchall()
        return [(str(row["map_id"]), str(row["owner_id"])) for row in rows]

    def retryable_analysis_queues(self, owner_id: str | None = None) -> list[tuple[str, str]]:
        """List non-paused queues with a persisted, bounded retry deadline."""

        with self.connection() as db:
            clause = [
                "q.operation=?",
                "q.status!='paused'",
                "m.deleted_at IS NULL",
                "c.operation='analysis'",
                "c.status='failed'",
                "c.next_retry_at IS NOT NULL",
                "c.attempts < ?",
            ]
            params: list[Any] = [_ANALYSIS_QUEUE_OPERATION, _ANALYSIS_MAX_ATTEMPTS]
            if owner_id is not None:
                clause.append("m.owner_id=?")
                params.append(owner_id)
            rows = db.execute(
                "SELECT DISTINCT q.map_id,m.owner_id FROM literature_map_jobs q "
                "JOIN literature_maps m ON m.map_id=q.map_id "
                "JOIN literature_map_jobs c ON c.map_id=q.map_id "
                "WHERE " + " AND ".join(clause) + " ORDER BY q.updated_at",
                tuple(params),
            ).fetchall()
        return [(str(row["map_id"]), str(row["owner_id"])) for row in rows]

    def queued_analysis_jobs(self, owner_id: str | None = None) -> list[MapJob]:
        """List durable queued analysis children for restart scheduling."""

        with self.connection() as db:
            clause = [
                "j.operation='analysis'",
                "j.status='queued'",
                "m.deleted_at IS NULL",
            ]
            params: list[Any] = []
            if owner_id is not None:
                clause.append("m.owner_id=?")
                params.append(owner_id)
            rows = db.execute(
                "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE "
                + " AND ".join(clause)
                + " ORDER BY j.updated_at,j.created_at",
                tuple(params),
            ).fetchall()
        return [_job(row) for row in rows]

    def refresh_analysis_queue(self, map_id: str, owner_id: str) -> dict[str, Any]:
        with self.transaction() as db:
            row = self._queue_row(db, map_id, owner_id)
            if row is None:
                return self.get_analysis_queue(map_id, owner_id)
            cursor = _load(row["cursor_json"], {})
            counts = self._queue_counts_tx(db, map_id, cursor)
            current_state = str(row["status"])
            if current_state != "paused":
                current_state = "active" if counts["queued"] or counts["running"] else ("partial" if counts["failed"] else "completed")
            db.execute(
                "UPDATE literature_map_jobs SET status=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=?",
                (current_state, _dump(counts), iso_now(), row["job_id"], map_id, _ANALYSIS_QUEUE_OPERATION),
            )
        return self.get_analysis_queue(map_id, owner_id)

    def _set_analysis_queue_state(self, map_id: str, owner_id: str, *, state: str, pause_reason: str | None, idempotency_key: str) -> dict[str, Any]:
        if not str(idempotency_key or "").strip():
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        params_hash = hashlib.sha256(_dump({"state": state, "pause_reason": pause_reason}).encode("utf-8")).hexdigest()
        with self.transaction() as db:
            row = self._queue_row(db, map_id, owner_id)
            if row is None:
                raise LookupError("analysis queue not found")
            replay = self._queue_command_replay(db, map_id, owner_id, f"analysis_queue:{state}", idempotency_key, params_hash)
            if replay is None:
                cursor = _load(row["cursor_json"], {})
                if not isinstance(cursor, dict):
                    cursor = {}
                cursor["pause_reason"] = pause_reason
                counts = self._queue_counts_tx(db, map_id, cursor)
                next_state = state
                if state == "active" and not counts["queued"] and not counts["running"]:
                    next_state = "partial" if counts["failed"] else "completed"
                now = iso_now()
                db.execute(
                    "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=?",
                    (next_state, _dump(cursor), _dump(counts), now, row["job_id"], map_id, _ANALYSIS_QUEUE_OPERATION),
                )
                fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                if fresh is not None:
                    self._append_event(db, _job(fresh), event_type="paused" if state == "paused" else "resumed")
                self._remember_queue_command(db, map_id, owner_id, f"analysis_queue:{state}", idempotency_key, params_hash, {"queue_job_id": row["job_id"]})
            self._refresh_expansion_batch_projections_tx(db, map_id, owner_id)
        return self.get_analysis_queue(map_id, owner_id)

    def _update_queue_items_tx(self, db: sqlite3.Connection, queue_row: sqlite3.Row, owner_id: str, candidates: list[dict[str, Any]]) -> None:
        cursor = _load(queue_row["cursor_json"], {})
        if not isinstance(cursor, dict):
            cursor = {}
        old_items = cursor.get("items", {})
        if not isinstance(old_items, Mapping):
            old_items = {}
        next_items: dict[str, Any] = {}
        for candidate in candidates:
            node_id = str(candidate.get("node_id") or "")
            if not node_id:
                continue
            if not bool(candidate.get("abstract_available", bool(str(candidate.get("source_version") or "").strip()))):
                next_items[node_id] = {
                    "node_id": node_id,
                    "status": "skipped",
                    "skip_reason": "MAP_ABSTRACT_UNAVAILABLE",
                    "retryable": False,
                }
                continue
            source_version = str(candidate.get("source_version") or "")
            model_id = str(candidate.get("model_id") or "")
            stable_key = str(candidate.get("idempotency_key") or f"auto:{node_id}:{source_version}:{model_id}")
            analysis, child, _created = self._create_analysis_tx(
                db,
                str(queue_row["map_id"]),
                node_id,
                owner_id,
                evidence_level="abstract",
                source_version=source_version,
                model_id=model_id,
                idempotency_key=stable_key,
                params_hash=str(candidate.get("params_hash") or ""),
                queue_job_id=str(queue_row["job_id"]),
            )
            error = analysis.error or {}
            next_items[node_id] = {
                "node_id": node_id,
                "analysis_id": analysis.analysis_id,
                "job_id": child.job_id,
                "source_version": source_version,
                "model_id": model_id,
                "status": _queue_item_status(analysis.status),
                "retryable": bool(error.get("retryable", False)),
                "error_code": error.get("code"),
                "next_retry_at": _job_retry_at(db, child.job_id),
            }
        cursor["items"] = next_items
        counts = self._queue_counts_tx(db, str(queue_row["map_id"]), cursor)
        current_state = str(queue_row["status"])
        if current_state != "paused":
            current_state = "active" if counts["queued"] or counts["running"] else ("partial" if counts["failed"] else "completed")
        cursor.setdefault("pause_reason", None)
        db.execute(
            "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=?",
            (current_state, _dump(cursor), _dump(counts), iso_now(), queue_row["job_id"], queue_row["map_id"], _ANALYSIS_QUEUE_OPERATION),
        )

    def _queue_counts_tx(self, db: sqlite3.Connection, map_id: str, cursor: Mapping[str, Any]) -> dict[str, int]:
        items = cursor.get("items", {}) if isinstance(cursor, Mapping) else {}
        counts = {"total": 0, "completed": 0, "queued": 0, "running": 0, "failed": 0, "skipped": 0}
        if not isinstance(items, Mapping):
            return counts
        for item in items.values():
            if not isinstance(item, Mapping):
                continue
            counts["total"] += 1
            status = str(item.get("status") or "queued")
            if status == "skipped":
                counts["skipped"] += 1
                continue
            job_id = str(item.get("job_id") or "")
            child = db.execute("SELECT status FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='analysis'", (job_id, map_id)).fetchone()
            analysis_status = str(child["status"] if child else status)
            if analysis_status == "stopped":
                analysis_status = "failed"
            if analysis_status == "completed":
                counts["completed"] += 1
            elif analysis_status == "running":
                counts["running"] += 1
            elif analysis_status == "failed":
                counts["failed"] += 1
            else:
                counts["queued"] += 1
        return counts

    def _expansion_batch_projection_tx(
        self,
        db: sqlite3.Connection,
        map_id: str,
        cursor: Mapping[str, Any],
        *,
        prior_counts: Mapping[str, Any] | None = None,
        queue_paused: bool,
    ) -> tuple[str, str, dict[str, int], list[dict[str, Any]], dict[str, Any]]:
        projected_cursor = dict(cursor) if isinstance(cursor, Mapping) else {}
        raw_items = projected_cursor.get("items")
        if not isinstance(raw_items, Mapping):
            raw_items = {}
        items = {str(key): dict(value) for key, value in raw_items.items() if isinstance(value, Mapping)}
        projected_cursor["items"] = items
        previous = prior_counts if isinstance(prior_counts, Mapping) else {}
        counts = {
            "added_count": max(0, int(previous.get("added_count") or len(projected_cursor.get("new_node_ids") or ()))),
            "existing_count": max(0, int(previous.get("existing_count") or 0)),
            "total": max(0, int(previous.get("total") or len(items))),
            "metadata_pending": 0,
            "metadata_failed": 0,
            "identity_unresolved": 0,
            "skipped_no_abstract": 0,
            "skipped_removed": 0,
            "analysis_queued": 0,
            "completed": 0,
            "failed": 0,
        }
        failed_units: list[dict[str, Any]] = []
        active_analysis = 0
        for node_id, item in items.items():
            status = str(item.get("status") or "")
            analysis_id = str(item.get("analysis_id") or "")
            if analysis_id:
                analysis_row = db.execute(
                    "SELECT a.status,a.error_json,n.removed_at FROM literature_map_analyses a "
                    "LEFT JOIN literature_map_nodes n ON n.map_id=a.map_id AND n.node_id=a.node_id "
                    "WHERE a.analysis_id=? AND a.map_id=?",
                    (analysis_id, map_id),
                ).fetchone()
                if analysis_row is None:
                    status = "analysis_failed"
                    item["error_code"] = "MAP_ANALYSIS_STATE_INVALID"
                    item["retryable"] = False
                elif analysis_row["removed_at"] is not None:
                    status = "skipped_removed"
                    item.pop("error_code", None)
                    item["retryable"] = False
                else:
                    analysis_status = str(analysis_row["status"])
                    if analysis_status == "completed":
                        status = "completed"
                        item.pop("error_code", None)
                        item["retryable"] = False
                    elif analysis_status == "failed":
                        status = "analysis_failed"
                        error = _load(analysis_row["error_json"], {})
                        error = error if isinstance(error, Mapping) else {}
                        item["error_code"] = _safe_error_code(error.get("code")) or "MAP_ANALYSIS_FAILED"
                        item["retryable"] = bool(error.get("retryable"))
                    elif analysis_status == "running":
                        status = "analysis_running"
                    else:
                        status = "analysis_queued"
                item["status"] = status

            if status in {"metadata_pending", "metadata_retry"}:
                counts["metadata_pending"] += 1
            elif status == "metadata_failed":
                counts["metadata_failed"] += 1
                counts["failed"] += 1
                failed_units.append(
                    {
                        "unit": node_id,
                        "error_code": _safe_error_code(item.get("error_code")) or "SEMANTIC_SCHOLAR_UNAVAILABLE",
                        "retryable": bool(item.get("retryable")),
                    }
                )
            elif status == "identity_unresolved":
                counts["identity_unresolved"] += 1
                counts["failed"] += 1
                failed_units.append(
                    {
                        "unit": node_id,
                        "error_code": "MAP_METADATA_IDENTITY_UNRESOLVED",
                        "retryable": False,
                    }
                )
            elif status == "analysis_failed":
                counts["failed"] += 1
                failed_units.append(
                    {
                        "unit": node_id,
                        "error_code": _safe_error_code(item.get("error_code")) or "MAP_ANALYSIS_FAILED",
                        "retryable": bool(item.get("retryable")),
                    }
                )
            elif status == "skipped_no_abstract":
                counts["skipped_no_abstract"] += 1
            elif status == "skipped_removed":
                counts["skipped_removed"] += 1
            elif status == "completed":
                counts["completed"] += 1
            elif status in {"analysis_running", "analysis_queued"}:
                counts["analysis_queued"] += 1
                active_analysis += 1

        if counts["metadata_pending"]:
            status, step = ("paused", "metadata") if queue_paused else ("queued", "metadata")
        elif active_analysis:
            status, step = ("paused", "analysis_wait") if queue_paused else ("analysis_wait", "analysis_wait")
        elif counts["failed"]:
            status, step = "partial", "finished"
        else:
            status, step = "completed", "finished"
        return status, step, counts, failed_units, projected_cursor

    def _refresh_expansion_batch_projections_tx(self, db: sqlite3.Connection, map_id: str, owner_id: str) -> int:
        queue_row = self._queue_row(db, map_id, owner_id)
        queue_paused = queue_row is not None and str(queue_row["status"]) == "paused"
        rows = db.execute(
            "SELECT * FROM literature_map_jobs WHERE map_id=? AND operation='expand_batch'",
            (map_id,),
        ).fetchall()
        changed_count = 0
        now = iso_now()
        for row in rows:
            current = _job(row)
            if current.status == "failed" and any(
                isinstance(unit, Mapping) and unit.get("error_code") == "MAP_JOB_LEASE_EXHAUSTED"
                for unit in current.failed_units
            ):
                continue
            status, step, counts, failed_units, cursor = self._expansion_batch_projection_tx(
                db,
                map_id,
                current.cursor,
                prior_counts=current.counts,
                queue_paused=queue_paused,
            )
            release_expired_lease = (
                current.status == "running"
                and not _lease_is_active(current.lease_expires_at, now)
                and counts["metadata_pending"] == 0
            )
            if current.status == "running" and not release_expired_lease:
                status, step = current.status, current.step
            if (
                status == current.status
                and step == current.step
                and cursor == current.cursor
                and counts == current.counts
                and failed_units == current.failed_units
                and not release_expired_lease
            ):
                continue
            changed = db.execute(
                "UPDATE literature_map_jobs SET status=?,step=?,cursor_json=?,counts_json=?,failed_units_json=?,"
                "worker_token=CASE WHEN ? THEN NULL ELSE worker_token END,"
                "lease_expires_at=CASE WHEN ? THEN NULL ELSE lease_expires_at END,updated_at=? "
                "WHERE job_id=? AND map_id=? AND operation='expand_batch'",
                (
                    status,
                    step,
                    _dump(cursor),
                    _dump(counts),
                    _dump(_safe_failed_units(failed_units)),
                    int(release_expired_lease),
                    int(release_expired_lease),
                    now,
                    current.job_id,
                    map_id,
                ),
            )
            if changed.rowcount:
                fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (current.job_id,)).fetchone()
                if fresh is not None:
                    event_type = (
                        "paused"
                        if status == "paused"
                        else "resumed"
                        if current.status == "paused" and status != "paused"
                        else "failed"
                        if status == "partial"
                        else "completed"
                        if status == "completed"
                        else "progress"
                    )
                    self._append_event(
                        db,
                        _job(fresh),
                        event_type=event_type,
                        error_code=(failed_units[0].get("error_code") if status == "partial" and failed_units else None),
                    )
                changed_count += 1
        return changed_count

    def _queue_projection_tx(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        cursor = _load(row["cursor_json"], {})
        if not isinstance(cursor, dict):
            cursor = {}
        items = cursor.get("items", {})
        if not isinstance(items, Mapping):
            items = {}
        counts = self._queue_counts_tx(db, str(row["map_id"]), cursor)
        current: dict[str, Any] | None = None
        failed_items: list[dict[str, Any]] = []
        for item in items.values():
            if not isinstance(item, Mapping):
                continue
            job_id = str(item.get("job_id") or "")
            analysis_id = str(item.get("analysis_id") or "")
            child = db.execute("SELECT status,next_retry_at FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='analysis'", (job_id, row["map_id"])).fetchone() if job_id else None
            status = str(child["status"] if child else item.get("status") or "queued")
            if status == "running":
                current = {"node_id": str(item.get("node_id") or ""), "analysis_id": analysis_id, "job_id": job_id, "status": status}
            if status in {"failed", "stopped"}:
                analysis_row = db.execute("SELECT error_json FROM literature_map_analyses WHERE analysis_id=? AND map_id=?", (analysis_id, row["map_id"])).fetchone() if analysis_id else None
                error = _safe_analysis_error(_load(analysis_row["error_json"], None) if analysis_row else None) or {}
                failed_items.append({
                    "node_id": str(item.get("node_id") or ""),
                    "analysis_id": analysis_id,
                    "job_id": job_id,
                    "error_code": error.get("code") or item.get("error_code") or ("MAP_ANALYSIS_STOPPED" if status == "stopped" else "MAP_ANALYSIS_FAILED"),
                    "retryable": bool(error.get("retryable", item.get("retryable", False))) if status != "stopped" else False,
                    "next_retry_at": child["next_retry_at"] if child else item.get("next_retry_at"),
                })
        # Projection-only addition (Spec043): surface skipped units from the
        # cursor so the UI can show why papers were skipped. This never alters
        # ``counts`` or ``failed_items`` semantics.
        skipped_items: list[dict[str, Any]] = []
        for item in items.values():
            if not isinstance(item, Mapping):
                continue
            if str(item.get("status") or "") != "skipped":
                continue
            node_id = str(item.get("node_id") or "")
            entry: dict[str, Any] = {
                "node_id": node_id,
                "skip_reason": str(item.get("skip_reason") or ""),
                "retryable": bool(item.get("retryable", False)),
            }
            if node_id:
                node_row = db.execute(
                    "SELECT title FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                    (row["map_id"], node_id),
                ).fetchone()
                if node_row is not None:
                    entry["title"] = node_row["title"]
            skipped_items.append(entry)
        state = str(row["status"])
        if state not in {"paused", "active", "completed", "partial"}:
            state = "active"
        if state == "active" and not counts["queued"] and not counts["running"]:
            state = "partial" if counts["failed"] else "completed"
        return {
            "map_id": str(row["map_id"]),
            "queue_job_id": str(row["job_id"]),
            "state": state,
            "pause_reason": cursor.get("pause_reason"),
            "counts": counts,
            "current": current,
            "failed_items": failed_items,
            "skipped_items": skipped_items,
        }

    @staticmethod
    def _assert_map_exists(db: sqlite3.Connection, map_id: str, owner_id: str) -> None:
        row = db.execute("SELECT 1 FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
        if row is None:
            raise LookupError("map not found")

    @staticmethod
    def _assert_map_exists_readonly(db: sqlite3.Connection, map_id: str, owner_id: str) -> None:
        LiteratureMapStore._assert_map_exists(db, map_id, owner_id)

    @staticmethod
    def _queue_row(db: sqlite3.Connection, map_id: str, owner_id: str) -> sqlite3.Row | None:
        return db.execute(
            "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.map_id=? AND j.operation=? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY j.created_at LIMIT 1",
            (map_id, _ANALYSIS_QUEUE_OPERATION, owner_id),
        ).fetchone()

    @staticmethod
    def _queue_command_replay(db: sqlite3.Connection, map_id: str, owner_id: str, operation: str, key: str, params_hash: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT params_hash,result_json FROM literature_map_mutation_idempotencies WHERE map_id=? AND owner_id=? AND operation=? AND idempotency_key=?",
            (map_id, owner_id, operation, key),
        ).fetchone()
        if row is None:
            return None
        if row["params_hash"] != params_hash:
            raise ValueError("idempotency conflict")
        value = _load(row["result_json"], {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _remember_queue_command(db: sqlite3.Connection, map_id: str, owner_id: str, operation: str, key: str, params_hash: str, result: Mapping[str, Any]) -> None:
        db.execute(
            "INSERT INTO literature_map_mutation_idempotencies(map_id,owner_id,operation,idempotency_key,params_hash,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (map_id, owner_id, operation, key, params_hash, _dump(dict(result)), iso_now()),
        )

    def claim_analysis_job(self, job_id: str, map_id: str, owner_id: str) -> MapJob | None:
        """Atomically claim one queued analysis with a durable lease token.

        A running child is never returned to a second caller.  The map-wide
        running guard keeps explicit and automatic analysis jobs from
        occupying the same map concurrently.
        """

        with self.transaction() as db:
            now = iso_now()
            worker_token = uuid.uuid4().hex
            lease_expires_at = _iso_after_seconds(_ANALYSIS_LEASE_SECONDS)
            queued_row = db.execute(
                "SELECT j.cursor_json,j.attempts,j.next_retry_at FROM literature_map_jobs j "
                "JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.job_id=? AND j.map_id=? AND j.operation='analysis' AND j.status='queued' "
                "AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, owner_id),
            ).fetchone()
            if queued_row is None or int(queued_row["attempts"] or 0) >= _ANALYSIS_MAX_ATTEMPTS:
                return None
            retry_at = queued_row["next_retry_at"]
            if retry_at is not None and str(retry_at) > now:
                return None
            changed = db.execute(
                "UPDATE literature_map_jobs SET status='running',worker_token=?,lease_expires_at=?,attempts=attempts+1,updated_at=? "
                "WHERE job_id=? AND map_id=? AND operation='analysis' AND status='queued' "
                "AND (next_retry_at IS NULL OR next_retry_at<=?) AND attempts < ? "
                "AND EXISTS (SELECT 1 FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL) "
                "AND NOT EXISTS (SELECT 1 FROM literature_map_jobs other WHERE other.map_id=? AND other.operation='analysis' AND other.status='running')",
                (worker_token, lease_expires_at, now, job_id, map_id, now, _ANALYSIS_MAX_ATTEMPTS, map_id, owner_id, map_id),
            )
            if changed.rowcount != 1:
                return None
            analysis_changed = db.execute("UPDATE literature_map_analyses SET status='running',updated_at=? WHERE job_id=? AND status='pending'", (now, job_id))
            if analysis_changed.rowcount != 1:
                db.execute("UPDATE literature_map_jobs SET status='queued',worker_token=NULL,lease_expires_at=NULL,attempts=MAX(0,attempts-1),updated_at=? WHERE job_id=?", (now, job_id))
                return None
            row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return None
            job = _job(row)
            self._append_event(db, job, event_type="started")
            return job

    def finish_analysis(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        status: str,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        worker_token: str | None = None,
        queue_pause_reason: str | None = None,
    ) -> MapAnalysis | None:
        if status not in {"completed", "failed"}:
            raise ValueError("invalid analysis status")
        with self.transaction() as db:
            now = iso_now()
            row = db.execute(
                "SELECT a.*,n.removed_at,j.status AS job_status,j.step,j.counts_json,j.failed_units_json,j.cursor_json,j.operation,j.idempotency_key,j.created_at AS job_created_at,j.worker_token,j.lease_expires_at,j.attempts FROM literature_map_analyses a JOIN literature_map_jobs j ON j.job_id=a.job_id JOIN literature_maps m ON m.map_id=a.map_id JOIN literature_map_nodes n ON n.map_id=a.map_id AND n.node_id=a.node_id WHERE a.job_id=? AND a.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, owner_id),
            ).fetchone()
            if (
                row is None
                or row["job_status"] != "running"
                or row["removed_at"] is not None
                or not worker_token
                or row["worker_token"] != worker_token
                or not _lease_is_active(row["lease_expires_at"], now)
            ):
                return None
            safe_error = _safe_analysis_error(error)
            retryable = status == "failed" and bool((safe_error or {}).get("retryable"))
            retry_at = (
                _iso_after_seconds(_retry_delay_seconds(int(row["attempts"])))
                if retryable and int(row["attempts"]) < _ANALYSIS_MAX_ATTEMPTS
                else None
            )
            job_changed = db.execute(
                "UPDATE literature_map_jobs SET status=?,step='finished',worker_token=NULL,lease_expires_at=NULL,next_retry_at=?,updated_at=? WHERE job_id=? AND status='running' AND worker_token=? AND lease_expires_at>?",
                (status, retry_at, now, job_id, worker_token, now),
            )
            if job_changed.rowcount != 1:
                return None
            analysis_changed = db.execute(
                "UPDATE literature_map_analyses SET status=?,result_json=?,error_json=?,updated_at=? WHERE job_id=? AND status='running'",
                (status, _dump(result) if status == "completed" else None, _dump(safe_error) if safe_error else None, now, job_id),
            )
            if analysis_changed.rowcount != 1:
                raise LiteratureMapStoreError("analysis finish CAS failed")
            job = MapJob(job_id, map_id, "analysis", status, "finished", _load(row["cursor_json"], {}), _load(row["counts_json"], {}), _load(row["failed_units_json"], []), row["idempotency_key"], row["job_created_at"], now)
            self._append_event(db, job, event_type="completed" if status == "completed" else "failed", error_code=(safe_error or {}).get("code"))
            queue_id = _load(row["cursor_json"], {}).get("queue_job_id")
            if queue_id:
                queue_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation=?", (queue_id, map_id, _ANALYSIS_QUEUE_OPERATION)).fetchone()
                if queue_row is not None:
                    queue_cursor = _load(queue_row["cursor_json"], {})
                    queue_counts = self._queue_counts_tx(db, map_id, queue_cursor)
                    queue_state = str(queue_row["status"])
                    if queue_pause_reason and queue_state != "paused":
                        queue_state = "paused"
                        if not isinstance(queue_cursor, dict):
                            queue_cursor = {}
                        queue_cursor["pause_reason"] = str(queue_pause_reason)[:80]
                    elif queue_state != "paused":
                        queue_state = "active" if queue_counts["queued"] or queue_counts["running"] else ("partial" if queue_counts["failed"] else "completed")
                    db.execute(
                        "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND status != 'paused'",
                        (queue_state, _dump(queue_cursor), _dump(queue_counts), now, queue_id),
                    )
                    if queue_pause_reason and queue_state == "paused":
                        fresh_queue = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (queue_id,)).fetchone()
                        if fresh_queue is not None and str(queue_row["status"]) != "paused":
                            self._append_event(db, _job(fresh_queue), event_type="paused", error_code=str(queue_pause_reason))
            self._refresh_expansion_batch_projections_tx(db, map_id, owner_id)
            fresh = db.execute("SELECT * FROM literature_map_analyses WHERE job_id=?", (job_id,)).fetchone()
        return _analysis(fresh) if fresh else None

    def reserve_conversation_binding(
        self,
        map_id: str,
        node_id: str,
        owner_id: str,
        *,
        project_id_snapshot: str | None,
        evidence_level: str,
        source_version: str,
        context: Mapping[str, Any],
        idempotency_key: str,
        params_hash: str | None = None,
    ) -> tuple[MapConversationBinding, bool]:
        if not str(idempotency_key or "").strip():
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        now = iso_now()
        with self.transaction() as db:
            valid = db.execute(
                "SELECT m.map_id,n.node_id FROM literature_maps m JOIN literature_map_nodes n ON n.map_id=m.map_id WHERE m.map_id=? AND n.node_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (map_id, node_id, owner_id),
            ).fetchone()
            if valid is None:
                raise LookupError("map or node not found")
            prior = db.execute(
                "SELECT * FROM literature_map_conversation_bindings WHERE map_id=? AND node_id=? AND idempotency_key=?",
                (map_id, node_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["evidence_level"] != evidence_level or prior["source_version"] != source_version or prior["project_id_snapshot"] != project_id_snapshot:
                    raise ValueError("idempotency conflict")
                return _binding(prior), False
            conversation_id = uuid.uuid4().hex
            binding_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO literature_map_conversation_bindings(binding_id,owner_id,map_id,node_id,conversation_id,project_id_snapshot,evidence_level,source_version,context_json,status,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (binding_id, owner_id, map_id, node_id, conversation_id, project_id_snapshot, evidence_level, source_version, _dump(dict(context)), "reserved", idempotency_key, now, now),
            )
            return MapConversationBinding(binding_id, owner_id, map_id, node_id, conversation_id, project_id_snapshot, evidence_level, source_version, dict(context), "reserved", idempotency_key, now, now), True

    def get_conversation_binding_for_request(
        self, map_id: str, node_id: str, owner_id: str, idempotency_key: str
    ) -> MapConversationBinding | None:
        """Return any historical reservation for stale-session recovery.

        Unlike ``get_conversation_binding`` this includes reserved and
        superseded rows, but remains owner-scoped and never exposes another
        user's idempotency history.
        """
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM literature_map_conversation_bindings WHERE map_id=? AND node_id=? AND owner_id=? AND idempotency_key=? ORDER BY updated_at DESC LIMIT 1",
                (map_id, node_id, owner_id, idempotency_key),
            ).fetchone()
        return _binding(row) if row else None

    def retire_conversation_binding(self, binding_id: str, owner_id: str) -> bool:
        """Preserve an archived/deleted binding while freeing its request key."""
        with self.transaction() as db:
            row = db.execute(
                "SELECT idempotency_key,status FROM literature_map_conversation_bindings WHERE binding_id=? AND owner_id=?",
                (binding_id, owner_id),
            ).fetchone()
            if row is None or row["status"] == "superseded":
                return False
            old_key = str(row["idempotency_key"] or "")
            retired_key = f"{old_key}:superseded:{binding_id}"
            db.execute(
                "UPDATE literature_map_conversation_bindings SET status='superseded',idempotency_key=?,updated_at=? WHERE binding_id=? AND owner_id=?",
                (retired_key, iso_now(), binding_id, owner_id),
            )
            return True

    def confirm_conversation_binding(self, binding_id: str, owner_id: str, *, conversation_id: str, context: Mapping[str, Any] | None = None) -> MapConversationBinding | None:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM literature_map_conversation_bindings WHERE binding_id=? AND owner_id=?", (binding_id, owner_id)).fetchone()
            if row is None:
                return None
            if row["conversation_id"] != conversation_id:
                raise ValueError("conversation binding conflict")
            db.execute("UPDATE literature_map_conversation_bindings SET status='confirmed',context_json=?,updated_at=? WHERE binding_id=? AND owner_id=?", (_dump(dict(context or _load(row["context_json"], {}))), iso_now(), binding_id, owner_id))
            fresh = db.execute("SELECT * FROM literature_map_conversation_bindings WHERE binding_id=?", (binding_id,)).fetchone()
        return _binding(fresh) if fresh else None

    def get_conversation_binding(self, conversation_id: str, owner_id: str) -> MapConversationBinding | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM literature_map_conversation_bindings WHERE conversation_id=? AND owner_id=? AND status='confirmed' ORDER BY updated_at DESC LIMIT 1", (conversation_id, owner_id)).fetchone()
        return _binding(row) if row else None

    def clear_conversation_bindings(self, conversation_id: str, owner_id: str) -> int:
        with self.transaction() as db:
            changed = db.execute("DELETE FROM literature_map_conversation_bindings WHERE conversation_id=? AND owner_id=?", (conversation_id, owner_id))
            return changed.rowcount

    def create_preview(
        self,
        map_id: str,
        owner_id: str,
        *,
        kind: str,
        base_revision: int,
        candidates: list[dict[str, Any]],
        diff: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        node_id: str | None = None,
        query: str | None = None,
        status: str = "completed",
        idempotency_key: str | None = None,
        params_hash: str | None = None,
        provider_request_count: int = 0,
        pagination: Mapping[str, Any] | None = None,
        seed_identity_key: str | None = None,
    ) -> tuple[MapPreview, MapJob, bool]:
        """Persist a preview and its completed calculation atomically.

        Preview calculation happens in the application layer; this method is
        only the owner-scoped durable boundary.  Keeping the candidate JSON
        here makes a preview safe to re-open after a process restart.
        """
        if kind not in {"topic", "references", "citations", "refresh"}:
            raise ValueError("INVALID_PREVIEW_KIND")
        if status not in {"queued", "completed"}:
            raise ValueError("invalid preview status")
        paginated = pagination is not None
        if paginated:
            if kind not in {"references", "citations"}:
                raise ValueError("PREVIEW_PAGINATION_KIND_REQUIRED")
            frozen_pagination = {"version": 1, "page_size": 50, "max_candidates": 500}
            supplied_pagination = dict(pagination) if isinstance(pagination, Mapping) else {}
            if (
                supplied_pagination != frozen_pagination
                or any(type(value) is not int for value in supplied_pagination.values())
                or set(supplied_pagination) != set(frozen_pagination)
            ):
                raise ValueError("INVALID_PREVIEW_PAGINATION")
            if status != "queued" or not node_id or not seed_identity_key or not idempotency_key:
                raise ValueError("INVALID_PREVIEW_PAGINATION")
        now = iso_now()
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            if idempotency_key:
                prior = db.execute(
                    "SELECT * FROM literature_map_previews WHERE map_id=? AND idempotency_key=?",
                    (map_id, idempotency_key),
                ).fetchone()
                if prior:
                    if params_hash is not None and prior["params_hash"] != params_hash:
                        raise ValueError("idempotency conflict")
                    job_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (prior["job_id"],)).fetchone()
                    if job_row is None:
                        raise LiteratureMapStoreError("preview state invalid")
                    return _preview(prior), _job(job_row), False
            job_operation = "preview_page" if paginated else f"preview:{kind}"
            job_step = "preview_page" if paginated else "preview"
            job = MapJob(
                uuid.uuid4().hex,
                map_id,
                job_operation,
                status,
                job_step,
                {"preview_id": ""},
                {"candidate_count": len(candidates), "provider_request_count": max(0, int(provider_request_count))},
                [],
                None,
                now,
                now,
            )
            preview_id = uuid.uuid4().hex
            job.cursor = {"preview_id": preview_id}
            if paginated:
                job.cursor.update({"target_cursor": 0, "cursor_history": [], "preview_revision": 1})
            db.execute(
                "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.job_id, map_id, job.operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), None, params_hash, now, now),
            )
            preview = MapPreview(
                preview_id,
                map_id,
                job.job_id,
                kind,
                status,
                int(base_revision),
                list(candidates),
                list(diff or []),
                list(warnings or []),
                idempotency_key,
                now,
                now,
                1,
                ({
                    "version": 1,
                    "page_size": 50,
                    "max_candidates": 500,
                    "next_cursor": 0,
                    "loaded_count": 0,
                    "total": None,
                    "has_more": None,
                    "limit_reached": False,
                    "state": "loading",
                    "failed_cursor": None,
                    "last_error": None,
                    "page_job_id": job.job_id,
                    "seed_identity_key": seed_identity_key,
                } if paginated else None),
            )
            db.execute(
                "INSERT INTO literature_map_previews(preview_id,map_id,job_id,kind,status,base_revision,candidates_json,diff_json,warnings_json,node_id,query_text,idempotency_key,params_hash,created_at,updated_at,preview_revision,pagination_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (preview.preview_id, map_id, job.job_id, kind, preview.status, preview.base_revision, _dump(preview.candidates), _dump(preview.diff), _dump(preview.warnings), node_id, query, idempotency_key, params_hash, now, now, preview.preview_revision, _dump(preview.pagination) if preview.pagination is not None else None),
            )
            self._append_event(db, job, event_type="preview_page_queued" if paginated else "preview_completed" if preview.status == "completed" else "preview_queued")
            return preview, job, True

    def queue_preview_page(
        self,
        map_id: str,
        preview_id: str,
        owner_id: str,
        *,
        expected_preview_revision: int,
        retry_failed: bool,
        idempotency_key: str,
        params_hash: str,
        failed_page_cache_key: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Queue one page under owner, preview revision and command-idempotency CAS."""

        if not str(idempotency_key or "").strip():
            raise ValueError("PREVIEW_IDEMPOTENCY_KEY_REQUIRED")
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            preview_row = db.execute(
                "SELECT * FROM literature_map_previews WHERE map_id=? AND preview_id=?",
                (map_id, preview_id),
            ).fetchone()
            if preview_row is None:
                raise LookupError("preview not found")
            pagination = _load(preview_row["pagination_json"], None)
            if not isinstance(pagination, Mapping) or type(pagination.get("version")) is not int or pagination.get("version") != 1:
                raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
            seed_row = db.execute(
                "SELECT identity_key,removed_at FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                (map_id, preview_row["node_id"]),
            ).fetchone()
            if (
                seed_row is None
                or seed_row["removed_at"] is not None
                or not seed_row["identity_key"]
                or seed_row["identity_key"] != pagination.get("seed_identity_key")
            ):
                raise ValueError("MAP_SEED_UNAVAILABLE")

            # A command replay is returned before checking the preview revision.
            replay = self._queue_command_replay(
                db, map_id, owner_id, "preview_load_more", idempotency_key, params_hash
            )
            if replay is not None:
                return replay, False
            if str(pagination.get("state")) == "loading":
                raise ValueError("MAP_PREVIEW_BUSY")
            if int(preview_row["preview_revision"]) != int(expected_preview_revision):
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            if bool(pagination.get("limit_reached")) or str(pagination.get("state")) == "capped":
                raise ValueError("MAP_PREVIEW_LIMIT_REACHED")
            if retry_failed:
                if str(pagination.get("state")) != "failed" or pagination.get("failed_cursor") is None:
                    raise ValueError("MAP_PREVIEW_RETRY_REQUIRED")
                target_cursor = pagination.get("failed_cursor")
            else:
                if str(pagination.get("state")) == "failed":
                    raise ValueError("MAP_PREVIEW_RETRY_REQUIRED")
                if str(pagination.get("state")) == "exhausted" or pagination.get("next_cursor") is None:
                    raise ValueError("MAP_PREVIEW_EXHAUSTED")
                if str(pagination.get("state")) != "ready":
                    raise ValueError("MAP_PREVIEW_EXHAUSTED")
                target_cursor = pagination.get("next_cursor")
            if isinstance(target_cursor, bool) or not isinstance(target_cursor, int) or target_cursor < 0:
                raise ValueError("MAP_PREVIEW_PAGINATION_INVALID")
            if retry_failed and failed_page_cache_key:
                # Re-fetch exactly the explicitly failed source page. Keep all
                # other successful page and map caches intact.
                db.execute(
                    "DELETE FROM literature_map_request_cache WHERE cache_key=?",
                    (failed_page_cache_key,),
                )

            prior_job_row = db.execute(
                "SELECT cursor_json FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='preview_page'",
                (preview_row["job_id"], map_id),
            ).fetchone()
            previous_cursor = _load(prior_job_row["cursor_json"], {}) if prior_job_row else {}
            history = list(previous_cursor.get("cursor_history", [])) if isinstance(previous_cursor, Mapping) else []
            now = iso_now()
            new_revision = int(preview_row["preview_revision"]) + 1
            job_id = uuid.uuid4().hex
            job = MapJob(
                job_id,
                map_id,
                "preview_page",
                "queued",
                "preview_page",
                {
                    "preview_id": preview_id,
                    "target_cursor": target_cursor,
                    "cursor_history": history,
                    "preview_revision": new_revision,
                },
                {"candidate_count": len(_load(preview_row["candidates_json"], [])), "provider_request_count": 0},
                [],
                f"preview-page:{preview_id}:{new_revision}",
                now,
                now,
            )
            db.execute(
                "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.job_id, map_id, job.operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), job.idempotency_key, params_hash, now, now),
            )
            updated_pagination = dict(pagination)
            updated_pagination.update({"state": "loading", "page_job_id": job_id})
            changed = db.execute(
                "UPDATE literature_map_previews SET job_id=?,status='queued',preview_revision=?,pagination_json=?,updated_at=? "
                "WHERE map_id=? AND preview_id=? AND preview_revision=? AND pagination_json IS NOT NULL",
                (job_id, new_revision, _dump(updated_pagination), now, map_id, preview_id, expected_preview_revision),
            )
            if changed.rowcount != 1:
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            self._append_event(db, job, event_type="preview_page_queued")
            result = {
                "preview_id": preview_id,
                "map_id": map_id,
                "job_id": job_id,
                "preview_revision": new_revision,
                "status": "loading",
            }
            self._remember_queue_command(
                db, map_id, owner_id, "preview_load_more", idempotency_key, params_hash, result
            )
            return result, True

    def finish_preview_page(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        worker_token: str,
        preview_id: str,
        expected_preview_revision: int,
        target_cursor: int,
        candidates: list[dict[str, Any]],
        pagination: Mapping[str, Any],
        status: str,
        cursor: Mapping[str, Any],
        provider_request_count: int = 1,
        error_code: str | None = None,
    ) -> tuple[MapPreview, MapJob] | None:
        """Commit one page snapshot and release its lease in the same transaction."""

        if status not in {"completed", "failed"}:
            raise ValueError("invalid preview page status")
        with self.auxiliary_job_transaction(
            job_id,
            map_id,
            owner_id,
            operation="preview_page",
            worker_token=worker_token,
        ) as db:
            row = db.execute(
                "SELECT p.* FROM literature_map_previews p JOIN literature_map_jobs j ON j.job_id=p.job_id "
                "JOIN literature_maps m ON m.map_id=p.map_id WHERE p.preview_id=? AND p.map_id=? "
                "AND p.job_id=? AND p.preview_revision=? AND j.cursor_json IS NOT NULL "
                "AND m.owner_id=? AND m.deleted_at IS NULL AND m.status!='stopped'",
                (preview_id, map_id, job_id, expected_preview_revision, owner_id),
            ).fetchone()
            if row is None:
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            stored_pagination = _load(row["pagination_json"], None)
            if (
                not isinstance(stored_pagination, Mapping)
                or stored_pagination.get("state") != "loading"
                or stored_pagination.get("page_job_id") != job_id
            ):
                raise ValueError("MAP_PREVIEW_BUSY")
            if status == "completed":
                seed_row = db.execute(
                    "SELECT identity_key,removed_at FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                    (map_id, row["node_id"]),
                ).fetchone()
                if (
                    seed_row is None
                    or seed_row["removed_at"] is not None
                    or seed_row["identity_key"] != stored_pagination.get("seed_identity_key")
                ):
                    raise ValueError("MAP_SEED_UNAVAILABLE")
            current_job = db.execute("SELECT cursor_json FROM literature_map_jobs WHERE job_id=?", (job_id,)).fetchone()
            current_cursor = _load(current_job["cursor_json"], {}) if current_job else {}
            if status == "completed" and (
                not isinstance(current_cursor, Mapping) or current_cursor.get("target_cursor") != target_cursor
            ):
                raise ValueError("MAP_PREVIEW_PAGINATION_INVALID")
            now = iso_now()
            new_revision = int(row["preview_revision"]) + 1
            changed = db.execute(
                "UPDATE literature_map_previews SET status=?,candidates_json=?,pagination_json=?,preview_revision=?,updated_at=? "
                "WHERE map_id=? AND preview_id=? AND job_id=? AND preview_revision=?",
                (
                    "completed" if status == "completed" else "failed",
                    _dump(candidates),
                    _dump(dict(pagination)),
                    new_revision,
                    now,
                    map_id,
                    preview_id,
                    job_id,
                    expected_preview_revision,
                ),
            )
            if changed.rowcount != 1:
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            counts = {"candidate_count": len(candidates), "provider_request_count": max(0, int(provider_request_count))}
            failed_units = []
            if status == "failed":
                failed_units = [{"unit": f"preview_page:{target_cursor}", "error_code": error_code or "SEMANTIC_SCHOLAR_UNAVAILABLE", "retryable": True}]
            finished = self.finish_auxiliary_job_tx(
                db,
                job_id,
                map_id,
                owner_id,
                operation="preview_page",
                worker_token=worker_token,
                status="completed" if status == "completed" else "failed",
                step="finished",
                cursor=dict(cursor),
                counts=counts,
                failed_units=failed_units,
                error_code=error_code,
                event_type="preview_page_completed" if status == "completed" else "preview_page_failed",
            )
            if finished is None:
                raise ValueError("auxiliary job lease invalid")
            fresh_preview = db.execute("SELECT * FROM literature_map_previews WHERE preview_id=?", (preview_id,)).fetchone()
            return _preview(fresh_preview), finished

    def complete_preview(
        self,
        map_id: str,
        preview_id: str,
        owner_id: str,
        *,
        status: str,
        candidates: list[dict[str, Any]],
        diff: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        provider_request_count: int = 0,
    ) -> tuple[MapPreview, MapJob] | None:
        if status not in {"completed", "failed"}:
            raise ValueError("invalid preview status")
        with self.transaction() as db:
            row = db.execute(
                "SELECT p.*,j.* FROM literature_map_previews p JOIN literature_map_jobs j ON j.job_id=p.job_id WHERE p.map_id=? AND p.preview_id=? AND EXISTS (SELECT 1 FROM literature_maps m WHERE m.map_id=p.map_id AND m.owner_id=? AND m.deleted_at IS NULL AND m.status != 'stopped')",
                (map_id, preview_id, owner_id),
            ).fetchone()
            if row is None or row["status"] not in {"queued", "running"}:
                return None
            now = iso_now()
            db.execute("UPDATE literature_map_previews SET status=?,candidates_json=?,diff_json=?,warnings_json=?,preview_revision=preview_revision+1,updated_at=? WHERE map_id=? AND preview_id=?", (status, _dump(candidates), _dump(diff or []), _dump(warnings or []), now, map_id, preview_id))
            db.execute("UPDATE literature_map_jobs SET status=?,step='preview',counts_json=?,updated_at=? WHERE job_id=? AND map_id=?", ("completed" if status == "completed" else "failed", _dump({"candidate_count": len(candidates), "provider_request_count": max(0, int(provider_request_count))}), now, row["job_id"], map_id))
            fresh_job_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            fresh_preview_row = db.execute("SELECT * FROM literature_map_previews WHERE preview_id=?", (preview_id,)).fetchone()
            job = _job(fresh_job_row)
            self._append_event(db, job, event_type="preview_completed" if status == "completed" else "preview_failed")
            return _preview(fresh_preview_row), job

    def get_preview_request(self, map_id: str, preview_id: str, owner_id: str) -> tuple[str | None, str | None] | None:
        with self.connection() as db:
            row = db.execute("SELECT node_id,query_text FROM literature_map_previews p JOIN literature_maps m ON m.map_id=p.map_id WHERE p.map_id=? AND p.preview_id=? AND m.owner_id=? AND m.deleted_at IS NULL", (map_id, preview_id, owner_id)).fetchone()
        return (row["node_id"], row["query_text"]) if row else None

    def get_preview(self, map_id: str, preview_id: str, owner_id: str) -> tuple[MapPreview, MapJob] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT p.*,j.* FROM literature_map_previews p JOIN literature_map_jobs j ON j.job_id=p.job_id JOIN literature_maps m ON m.map_id=p.map_id WHERE p.map_id=? AND p.preview_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (map_id, preview_id, owner_id),
            ).fetchone()
        if row is None:
            return None
        # Duplicate column names in the join are avoided by reading the
        # preview columns from a second narrow query for predictable mapping.
        with self.connection() as db:
            preview_row = db.execute("SELECT * FROM literature_map_previews WHERE map_id=? AND preview_id=?", (map_id, preview_id)).fetchone()
            job_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (preview_row["job_id"],)).fetchone() if preview_row else None
        return (_preview(preview_row), _job(job_row)) if preview_row and job_row else None

    def revalidate_previews(
        self,
        map_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        selections: list[dict[str, Any]],
        idempotency_key: str,
        params_hash: str,
    ) -> dict[str, Any]:
        """Refresh selected preview snapshots against the current local graph."""
        if not idempotency_key:
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            try:
                replay = self._queue_command_replay(
                    db, map_id, owner_id, "preview_revalidate", idempotency_key, params_hash
                )
            except ValueError as error:
                if str(error) == "idempotency conflict":
                    raise ValueError("MAP_IDEMPOTENCY_CONFLICT") from error
                raise
            if replay is not None:
                return replay
            if int(map_row["revision"]) != expected_revision:
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            records, seed_id, seed_identity = self._expansion_selection_rows_tx(
                db,
                map_id,
                owner_id,
                expected_revision=expected_revision,
                selections=selections,
                require_current_base=False,
            )
            active_count = int(
                db.execute(
                    "SELECT COUNT(*) FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL",
                    (map_id,),
                ).fetchone()[0]
            )
            selected_identities: list[tuple[dict[str, Any], str, bool]] = []
            candidate_updates: dict[str, list[dict[str, Any]]] = {}
            changes_by_preview: dict[str, dict[str, int]] = {}
            invalid: list[dict[str, str]] = []
            selected_set = {
                (str(selection["preview_id"]), str(candidate_id))
                for selection in selections
                for candidate_id in selection["selected_candidate_ids"]
            }
            for preview_row, _job_row, candidates, _pagination in records:
                preview_id = str(preview_row["preview_id"])
                changes = {"already_present": 0, "removed": 0}
                refreshed: list[dict[str, Any]] = []
                for raw_candidate in candidates:
                    candidate = dict(raw_candidate)
                    candidate_id = str(candidate.get("candidate_id") or "")
                    identity = _verified_preview_identity(candidate)
                    row = (
                        db.execute(
                            "SELECT node_id,removed_at FROM literature_map_nodes WHERE map_id=? AND identity_key=?",
                            (map_id, identity),
                        ).fetchone()
                        if identity
                        else None
                    )
                    present = bool(row and row["removed_at"] is None)
                    removed = bool(row and row["removed_at"] is not None)
                    if bool(candidate.get("already_present")) != present:
                        changes["already_present"] += 1
                    if bool(candidate.get("removed")) != removed:
                        changes["removed"] += 1
                    candidate["already_present"] = present
                    candidate["removed"] = removed
                    if (preview_id, candidate_id) in selected_set:
                        reason = None
                        if not identity:
                            reason = "INVALID_PREVIEW_CANDIDATE"
                        elif identity == seed_identity:
                            reason = "INVALID_PREVIEW_CANDIDATE"
                        elif removed:
                            reason = "MAP_NODE_REMOVED"
                        if reason:
                            invalid.append({"preview_id": preview_id, "candidate_id": candidate_id, "reason": reason})
                        else:
                            selected_identities.append((candidate, identity, present))
                    refreshed.append(candidate)
                candidate_updates[preview_id] = refreshed
                changes_by_preview[preview_id] = changes

            new_identities: list[str] = []
            seen = set()
            for _candidate, identity, present in selected_identities:
                if not present and identity not in seen:
                    seen.add(identity)
                    new_identities.append(identity)
            capacity = max(0, 200 - active_count)
            overflow = set(new_identities[capacity:])
            if overflow:
                known_invalid = {(item["preview_id"], item["candidate_id"]) for item in invalid}
                for selection in selections:
                    preview_id = str(selection["preview_id"])
                    candidates = candidate_updates.get(preview_id, [])
                    by_id = {str(item.get("candidate_id")): item for item in candidates}
                    for candidate_id in selection["selected_candidate_ids"]:
                        candidate = by_id.get(str(candidate_id))
                        if candidate and candidate.get("identity_key") in overflow and (preview_id, str(candidate_id)) not in known_invalid:
                            invalid.append({"preview_id": preview_id, "candidate_id": str(candidate_id), "reason": "MAP_NODE_LIMIT"})

            now = iso_now()
            preview_results: list[dict[str, Any]] = []
            for preview_row, job_row, _candidates, _pagination in records:
                preview_id = str(preview_row["preview_id"])
                next_revision = int(preview_row["preview_revision"]) + 1
                changed = db.execute(
                    "UPDATE literature_map_previews SET candidates_json=?,base_revision=?,preview_revision=?,updated_at=? "
                    "WHERE map_id=? AND preview_id=? AND preview_revision=?",
                    (
                        _dump(candidate_updates[preview_id]),
                        expected_revision,
                        next_revision,
                        now,
                        map_id,
                        preview_id,
                        int(preview_row["preview_revision"]),
                    ),
                )
                if changed.rowcount != 1:
                    raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
                preview_results.append(
                    {
                        "preview_id": preview_id,
                        "preview_revision": next_revision,
                        "base_revision": expected_revision,
                    }
                )
                self._append_event(db, _job(job_row), event_type="preview_revalidated")
            valid_selections: list[dict[str, Any]] = []
            invalid_keys = {(item["preview_id"], item["candidate_id"]) for item in invalid}
            for selection in selections:
                preview_id = str(selection["preview_id"])
                valid_selections.append(
                    {
                        "preview_id": preview_id,
                        "candidate_ids": [
                            str(candidate_id)
                            for candidate_id in selection["selected_candidate_ids"]
                            if (preview_id, str(candidate_id)) not in invalid_keys
                        ],
                    }
                )
            result = {
                "map_id": map_id,
                "revision": expected_revision,
                "previews": preview_results,
                "valid_selections": valid_selections,
                "invalid_selections": invalid,
                "changes": changes_by_preview,
            }
            self._remember_queue_command(
                db, map_id, owner_id, "preview_revalidate", idempotency_key, params_hash, result
            )
            return result

    def batch_apply_previews(
        self,
        map_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        selections: list[dict[str, Any]],
        idempotency_key: str,
        params_hash: str,
        candidate_nodes: Mapping[tuple[str, str], MapPaper],
        analysis_specs: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Apply cross-direction preview selections, outbox and queue in one transaction."""
        if not idempotency_key:
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            map_row = db.execute(
                "SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                (map_id, owner_id),
            ).fetchone()
            if map_row is None:
                raise LookupError("map not found")
            try:
                replay = self._queue_command_replay(
                    db, map_id, owner_id, "preview_batch_apply", idempotency_key, params_hash
                )
            except ValueError as error:
                if str(error) == "idempotency conflict":
                    raise ValueError("MAP_IDEMPOTENCY_CONFLICT") from error
                raise
            if replay is not None:
                return replay
            if int(map_row["revision"]) != expected_revision:
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            records, seed_id, seed_identity = self._expansion_selection_rows_tx(
                db,
                map_id,
                owner_id,
                expected_revision=expected_revision,
                selections=selections,
                require_current_base=True,
            )
            active_count = int(
                db.execute(
                    "SELECT COUNT(*) FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL",
                    (map_id,),
                ).fetchone()[0]
            )
            record_by_id = {str(row["preview_id"]): (row, job, candidates, pagination) for row, job, candidates, pagination in records}
            new_by_identity: dict[str, MapPaper] = {}
            active_by_identity: dict[str, str] = {
                str(row["identity_key"]): str(row["node_id"])
                for row in db.execute(
                    "SELECT identity_key,node_id FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL",
                    (map_id,),
                ).fetchall()
            }
            selected_by_identity: dict[str, list[tuple[str, str, str]]] = {}
            existing_identities: set[str] = set()
            for selection in selections:
                preview_id = str(selection["preview_id"])
                preview_row, _job_row, candidates, _pagination = record_by_id[preview_id]
                candidate_by_id = {str(item.get("candidate_id")): item for item in candidates if isinstance(item, Mapping)}
                kind = str(preview_row["kind"])
                for candidate_id in selection["selected_candidate_ids"]:
                    candidate_id = str(candidate_id)
                    candidate = candidate_by_id.get(candidate_id)
                    if candidate is None:
                        raise ValueError("INVALID_PREVIEW_CANDIDATE")
                    identity = _verified_preview_identity(candidate)
                    if not identity or identity == seed_identity:
                        raise ValueError("INVALID_PREVIEW_CANDIDATE")
                    candidate_node = candidate_nodes.get((preview_id, candidate_id))
                    if candidate_node is None or candidate_node.map_id != map_id or candidate_node.identity_key != identity:
                        raise ValueError("INVALID_PREVIEW_CANDIDATE")
                    if deterministic_identity_key(candidate_node.external_ids) != identity:
                        raise ValueError("INVALID_PREVIEW_CANDIDATE")
                    current_row = db.execute(
                        "SELECT node_id,removed_at FROM literature_map_nodes WHERE map_id=? AND identity_key=?",
                        (map_id, identity),
                    ).fetchone()
                    if current_row is not None and current_row["removed_at"] is not None:
                        raise ValueError("MAP_NODE_REMOVED")
                    if current_row is None:
                        if bool(candidate.get("already_present")) or bool(candidate.get("removed")):
                            raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
                        new_by_identity.setdefault(identity, candidate_node)
                    else:
                        if bool(candidate.get("removed")) or not bool(candidate.get("already_present")):
                            raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
                        existing_identities.add(identity)
                    selected_by_identity.setdefault(identity, []).append((preview_id, candidate_id, kind))
            if len(new_by_identity) > 20:
                raise ValueError("PREVIEW_BATCH_LIMIT")
            if active_count + len(new_by_identity) > _MAX_MAP_NODES:
                raise ValueError("MAP_NODE_LIMIT")

            now = iso_now()
            for identity, node in new_by_identity.items():
                self._insert_node(db, node)
                active_by_identity[identity] = node.node_id

            inserted_edges = 0
            seed_node_id = str(seed_id)
            for identity, sources in selected_by_identity.items():
                target_node_id = active_by_identity.get(identity)
                if not target_node_id or target_node_id == seed_node_id:
                    raise ValueError("INVALID_PREVIEW_CANDIDATE")
                for preview_id, _candidate_id, kind in sources:
                    source_id, target_id = (
                        (seed_node_id, target_node_id)
                        if kind == "references"
                        else (target_node_id, seed_node_id)
                    )
                    edge = MapEdge.new(
                        map_id,
                        "citation",
                        source_id,
                        target_id,
                        provenance={"source": "preview", "preview_id": preview_id},
                    )
                    changed = db.execute(
                        "INSERT OR IGNORE INTO literature_map_edges(edge_id,map_id,kind,source_id,target_id,provenance_json,score,basis,model_version,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (edge.edge_id, map_id, edge.kind, edge.source_id, edge.target_id, _dump(edge.provenance), edge.score, edge.basis, edge.model_version, edge.content_hash),
                    )
                    inserted_edges += max(0, changed.rowcount)
            graph_changed = bool(new_by_identity or inserted_edges)
            if graph_changed:
                db.execute(
                    "UPDATE literature_maps SET revision=revision+1,updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
                    (now, map_id, owner_id),
                )
            final_revision = expected_revision + (1 if graph_changed else 0)

            abstract_nodes = [node for node in new_by_identity.values() if str(node.abstract or "").strip()]
            queue_items: dict[str, dict[str, Any]] = {}
            queue_row = self._queue_row(db, map_id, owner_id)
            queue_job_id: str | None = str(queue_row["job_id"]) if queue_row is not None else None
            if abstract_nodes:
                candidates_for_queue: list[dict[str, Any]] = []
                for node in abstract_nodes:
                    spec = analysis_specs.get(str(node.identity_key or ""))
                    if not isinstance(spec, Mapping):
                        raise ValueError("MAP_ANALYSIS_STATE_INVALID")
                    source_version = str(spec.get("source_version") or "")
                    model_id = str(spec.get("model_id") or "")
                    if not source_version or not model_id:
                        raise ValueError("MAP_ANALYSIS_STATE_INVALID")
                    candidates_for_queue.append(
                        {
                            "node_id": node.node_id,
                            "abstract_available": True,
                            "source_version": source_version,
                            "model_id": model_id,
                            "idempotency_key": f"auto:{node.node_id}:{source_version}:{model_id}",
                            "params_hash": str(spec.get("params_hash") or ""),
                        }
                    )
                queue_job_id, queue_items = self._merge_analysis_queue_items_tx(
                    db, map_id, owner_id, candidates_for_queue
                )

            outbox_items: dict[str, dict[str, Any]] = {}
            metadata_pending = 0
            analysis_queued = 0
            for node in new_by_identity.values():
                if str(node.abstract or "").strip():
                    item = dict(queue_items.get(node.node_id) or {})
                    outbox_items[node.node_id] = {
                        "node_id": node.node_id,
                        "status": "analysis_queued",
                        "metadata_status": "complete",
                        "analysis_id": item.get("analysis_id"),
                        "source_version": item.get("source_version"),
                        "attempts": 0,
                        "error_code": None,
                    }
                    analysis_queued += 1
                else:
                    outbox_items[node.node_id] = {
                        "node_id": node.node_id,
                        "status": "metadata_pending",
                        "metadata_status": "pending",
                        "attempts": 0,
                        "error_code": None,
                    }
                    metadata_pending += 1

            batch_job_id = uuid.uuid4().hex
            if metadata_pending:
                batch_status, batch_step = "queued", "metadata"
            elif analysis_queued:
                batch_status, batch_step = "analysis_wait", "analysis_wait"
            else:
                batch_status, batch_step = "completed", "finished"
            counts = {
                "added_count": len(new_by_identity),
                "existing_count": len(existing_identities),
                "total": len(new_by_identity),
                "metadata_pending": metadata_pending,
                "analysis_queued": analysis_queued,
                "completed": 0,
                "failed": 0,
            }
            cursor = {
                "version": 1,
                "seed_node_id": seed_node_id,
                "preview_ids": [str(row["preview_id"]) for row, _job, _candidates, _pagination in records],
                "new_node_ids": [node.node_id for node in new_by_identity.values()],
                "items": outbox_items,
            }
            batch_job = MapJob(
                batch_job_id,
                map_id,
                "expand_batch",
                batch_status,
                batch_step,
                cursor,
                counts,
                [],
                f"expand-batch:{idempotency_key}",
                now,
                now,
            )
            db.execute(
                "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (batch_job.job_id, map_id, batch_job.operation, batch_job.status, batch_job.step, _dump(batch_job.cursor), _dump(batch_job.counts), _dump(batch_job.failed_units), batch_job.idempotency_key, params_hash, now, now),
            )

            preview_results: list[dict[str, Any]] = []
            for preview_row, _job_row, candidates, _pagination in records:
                preview_id = str(preview_row["preview_id"])
                selected_ids = {
                    str(candidate_id)
                    for selection in selections
                    if str(selection["preview_id"]) == preview_id
                    for candidate_id in selection["selected_candidate_ids"]
                }
                refreshed: list[dict[str, Any]] = []
                for raw_candidate in candidates:
                    candidate = dict(raw_candidate)
                    identity = _verified_preview_identity(candidate)
                    current = db.execute(
                        "SELECT removed_at FROM literature_map_nodes WHERE map_id=? AND identity_key=?",
                        (map_id, identity),
                    ).fetchone() if identity else None
                    candidate["already_present"] = bool(current and current["removed_at"] is None)
                    candidate["removed"] = bool(current and current["removed_at"] is not None)
                    if str(candidate.get("candidate_id") or "") in selected_ids:
                        candidate["added"] = True
                    refreshed.append(candidate)
                next_preview_revision = int(preview_row["preview_revision"]) + 1
                changed = db.execute(
                    "UPDATE literature_map_previews SET candidates_json=?,base_revision=?,preview_revision=?,updated_at=? "
                    "WHERE map_id=? AND preview_id=? AND preview_revision=?",
                    (_dump(refreshed), final_revision, next_preview_revision, now, map_id, preview_id, int(preview_row["preview_revision"])),
                )
                if changed.rowcount != 1:
                    raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
                preview_results.append(
                    {"preview_id": preview_id, "preview_revision": next_preview_revision, "base_revision": final_revision}
                )

            added_node_ids = [node.node_id for node in new_by_identity.values()]
            result = {
                "map_id": map_id,
                "revision": final_revision,
                "added_count": len(added_node_ids),
                "existing_count": len(existing_identities),
                "node_ids": added_node_ids,
                "batch_job_id": batch_job_id,
                "queue_job_id": queue_job_id,
                "previews": preview_results,
            }
            self._remember_queue_command(
                db, map_id, owner_id, "preview_batch_apply", idempotency_key, params_hash, result
            )
            self._append_event(db, batch_job, event_type="expansion_batch_queued")
            return result

    def _expansion_selection_rows_tx(
        self,
        db: sqlite3.Connection,
        map_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        selections: list[dict[str, Any]],
        require_current_base: bool,
    ) -> tuple[list[tuple[sqlite3.Row, sqlite3.Row, list[Any], dict[str, Any]]], str, str]:
        if not 1 <= len(selections) <= 2:
            raise ValueError("PREVIEW_SELECTIONS_INVALID")
        preview_ids: set[str] = set()
        kinds: set[str] = set()
        records: list[tuple[sqlite3.Row, sqlite3.Row, list[Any], dict[str, Any]]] = []
        seed_id: str | None = None
        seed_identity: str | None = None
        for selection in selections:
            preview_id = str(selection.get("preview_id") or "")
            candidate_ids = selection.get("selected_candidate_ids")
            if not preview_id or preview_id in preview_ids:
                raise ValueError("PREVIEW_SELECTIONS_INVALID")
            preview_ids.add(preview_id)
            if not isinstance(candidate_ids, list) or not 1 <= len(candidate_ids) <= 20:
                raise ValueError("PREVIEW_BATCH_LIMIT")
            candidate_ids = [str(item) for item in candidate_ids]
            if len(candidate_ids) != len(set(candidate_ids)):
                raise ValueError("INVALID_PREVIEW_CANDIDATE")
            preview_row = db.execute(
                "SELECT * FROM literature_map_previews WHERE map_id=? AND preview_id=?",
                (map_id, preview_id),
            ).fetchone()
            if preview_row is None:
                raise LookupError("preview not found")
            kind = str(preview_row["kind"])
            if kind not in {"references", "citations"} or kind in kinds:
                raise ValueError("PREVIEW_SELECTIONS_INVALID")
            kinds.add(kind)
            job_row = db.execute(
                "SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=?",
                (preview_row["job_id"], map_id),
            ).fetchone()
            pagination = _load(preview_row["pagination_json"], None)
            if not isinstance(pagination, Mapping) or pagination.get("version") != 1:
                raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
            if pagination.get("state") == "loading" or preview_row["status"] in {"queued", "running"}:
                raise ValueError("MAP_PREVIEW_BUSY")
            if pagination.get("state") not in {"ready", "exhausted", "capped", "failed"} or preview_row["status"] not in {"completed", "failed"}:
                raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
            if job_row is None or job_row["status"] in {"queued", "running"}:
                raise ValueError("MAP_PREVIEW_BUSY")
            if int(preview_row["preview_revision"]) != int(selection.get("expected_preview_revision", -1)):
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            if require_current_base and int(preview_row["base_revision"]) != expected_revision:
                raise ValueError("MAP_PREVIEW_VERSION_CONFLICT")
            current_seed_id = str(preview_row["node_id"] or "")
            seed_row = db.execute(
                "SELECT node_id,identity_key,removed_at FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                (map_id, current_seed_id),
            ).fetchone()
            if (
                seed_row is None
                or seed_row["removed_at"] is not None
                or not str(seed_row["identity_key"] or "")
                or str(seed_row["identity_key"]) != str(pagination.get("seed_identity_key") or "")
            ):
                raise ValueError("MAP_SEED_UNAVAILABLE")
            if seed_id is None:
                seed_id = current_seed_id
                seed_identity = str(seed_row["identity_key"])
            elif seed_id != current_seed_id or seed_identity != str(seed_row["identity_key"]):
                raise ValueError("MAP_SEED_UNAVAILABLE")
            candidates = _load(preview_row["candidates_json"], [])
            if not isinstance(candidates, list):
                raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
            candidate_map = {
                str(item.get("candidate_id")): item
                for item in candidates
                if isinstance(item, Mapping) and item.get("candidate_id")
            }
            if any(candidate_id not in candidate_map for candidate_id in candidate_ids):
                raise ValueError("INVALID_PREVIEW_CANDIDATE")
            records.append((preview_row, job_row, candidates, dict(pagination)))
        assert seed_id is not None and seed_identity is not None
        return records, seed_id, seed_identity

    def _merge_analysis_queue_items_tx(
        self,
        db: sqlite3.Connection,
        map_id: str,
        owner_id: str,
        candidates: list[dict[str, Any]],
    ) -> tuple[str, dict[str, dict[str, Any]]]:
        """Append just the supplied new nodes while retaining every old queue item."""
        queue_row = self._queue_row(db, map_id, owner_id)
        now = iso_now()
        if queue_row is None:
            queue_id = uuid.uuid4().hex
            queue_job = MapJob(
                queue_id,
                map_id,
                _ANALYSIS_QUEUE_OPERATION,
                "active",
                "analysis_queue",
                {"queue_version": 1, "pause_reason": None, "items": {}},
                {"total": 0, "completed": 0, "queued": 0, "running": 0, "failed": 0, "skipped": 0},
                [],
                _ANALYSIS_QUEUE_IDEMPOTENCY,
                now,
                now,
            )
            db.execute(
                "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (queue_job.job_id, map_id, queue_job.operation, queue_job.status, queue_job.step, _dump(queue_job.cursor), _dump(queue_job.counts), _dump(queue_job.failed_units), queue_job.idempotency_key, None, now, now),
            )
            self._append_event(db, queue_job, event_type="queued")
            queue_row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (queue_id,)).fetchone()
        queue_id = str(queue_row["job_id"])
        cursor = _load(queue_row["cursor_json"], {})
        if not isinstance(cursor, dict):
            cursor = {}
        old_items = cursor.get("items", {})
        if not isinstance(old_items, Mapping):
            old_items = {}
        merged_items = dict(old_items)
        new_items: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            node_id = str(candidate.get("node_id") or "")
            if not node_id:
                raise ValueError("MAP_ANALYSIS_STATE_INVALID")
            existing = merged_items.get(node_id)
            if isinstance(existing, Mapping):
                if not (
                    existing.get("status") == "skipped"
                    and existing.get("skip_reason") == "MAP_ABSTRACT_UNAVAILABLE"
                ):
                    new_items[node_id] = dict(existing)
                    continue
            source_version = str(candidate.get("source_version") or "")
            model_id = str(candidate.get("model_id") or "")
            stable_key = str(candidate.get("idempotency_key") or f"auto:{node_id}:{source_version}:{model_id}")
            analysis, child, _created = self._create_analysis_tx(
                db,
                map_id,
                node_id,
                owner_id,
                evidence_level="abstract",
                source_version=source_version,
                model_id=model_id,
                idempotency_key=stable_key,
                params_hash=str(candidate.get("params_hash") or ""),
                queue_job_id=queue_id,
            )
            error = analysis.error or {}
            item = {
                "node_id": node_id,
                "analysis_id": analysis.analysis_id,
                "job_id": child.job_id,
                "source_version": source_version,
                "model_id": model_id,
                "status": _queue_item_status(analysis.status),
                "retryable": bool(error.get("retryable", False)),
                "error_code": error.get("code"),
                "next_retry_at": _job_retry_at(db, child.job_id),
            }
            merged_items[node_id] = item
            new_items[node_id] = item
        cursor["items"] = merged_items
        cursor.setdefault("pause_reason", None)
        counts = self._queue_counts_tx(db, map_id, cursor)
        current_state = str(queue_row["status"])
        if current_state != "paused":
            current_state = "active" if counts["queued"] or counts["running"] else ("partial" if counts["failed"] else "completed")
        db.execute(
            "UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=?",
            (current_state, _dump(cursor), _dump(counts), now, queue_id, map_id, _ANALYSIS_QUEUE_OPERATION),
        )
        return queue_id, new_items

    def apply_preview(
        self,
        map_id: str,
        owner_id: str,
        *,
        preview_id: str,
        expected_revision: int,
        selected_candidate_ids: list[str],
        nodes: list[MapPaper],
        relations: list[tuple[str, str, str]] | None = None,
        updates: list[MapPaper] | None = None,
        idempotency_key: str | None = None,
        params_hash: str | None = None,
    ) -> dict[str, Any]:
        """Apply verified preview data under one revision-CAS transaction."""
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            if idempotency_key:
                prior = db.execute(
                    "SELECT params_hash,result_json FROM literature_map_mutation_idempotencies WHERE map_id=? AND owner_id=? AND operation='preview_apply' AND idempotency_key=?",
                    (map_id, owner_id, idempotency_key),
                ).fetchone()
                if prior:
                    if params_hash is not None and prior["params_hash"] != params_hash:
                        raise ValueError("idempotency conflict")
                    return _load(prior["result_json"], {})
            preview_row = db.execute("SELECT * FROM literature_map_previews WHERE map_id=? AND preview_id=?", (map_id, preview_id)).fetchone()
            map_row = db.execute("SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
            if preview_row is None or map_row is None:
                raise LookupError("preview not found")
            if preview_row["pagination_json"] is not None:
                raise ValueError("MAP_PREVIEW_REVALIDATION_REQUIRED")
            if preview_row["status"] not in {"completed", "applied"}:
                raise ValueError("PREVIEW_NOT_READY")
            if int(map_row["revision"]) != int(expected_revision) or int(preview_row["base_revision"]) != int(expected_revision):
                raise ValueError("revision conflict")
            if len(nodes) > 20:
                raise ValueError("PREVIEW_BATCH_LIMIT")
            active_count = int(db.execute("SELECT COUNT(*) FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL", (map_id,)).fetchone()[0])
            if active_count + len(nodes) > _MAX_MAP_NODES:
                raise ValueError("MAP_NODE_LIMIT")
            existing_ids = {str(item.get("candidate_id")) for item in _load(preview_row["candidates_json"], []) if isinstance(item, Mapping)}
            if any(candidate_id not in existing_ids for candidate_id in selected_candidate_ids):
                raise ValueError("INVALID_PREVIEW_CANDIDATE")
            for node in nodes:
                self._insert_node(db, node)
            for update in updates or []:
                db.execute(
                    # Refreshes may update provider metadata only.  Identity,
                    # source/import provenance, document state and layout are
                    # server-owned and must survive a partial provider result.
                    "UPDATE literature_map_nodes SET title=?,authors_json=?,year=?,venue=?,abstract=?,keywords_json=?,citation_count=? WHERE map_id=? AND node_id=? AND removed_at IS NULL",
                    (update.title, _dump(list(update.authors)), update.year, update.venue, update.abstract, _dump(list(update.keywords)), update.citation_count, map_id, update.node_id),
                )
            identity_to_node = {str(row["identity_key"]): str(row["node_id"]) for row in db.execute("SELECT identity_key,node_id FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL", (map_id,)).fetchall()}
            identity_to_node.update({node.identity_key: node.node_id for node in nodes if node.identity_key})
            for update in updates or []:
                identity_to_node[update.identity_key] = update.node_id
            node_by_id = {node.node_id: node.node_id for node in nodes}
            for kind, source_ref, target_ref in relations or []:
                source_id = identity_to_node.get(source_ref, node_by_id.get(source_ref, source_ref))
                target_id = identity_to_node.get(target_ref, node_by_id.get(target_ref, target_ref))
                if source_id == target_id:
                    continue
                if db.execute("SELECT 1 FROM literature_map_nodes WHERE map_id=? AND node_id=? AND removed_at IS NULL", (map_id, source_id)).fetchone() is None:
                    continue
                if db.execute("SELECT 1 FROM literature_map_nodes WHERE map_id=? AND node_id=? AND removed_at IS NULL", (map_id, target_id)).fetchone() is None:
                    continue
                edge = MapEdge.new(map_id, kind, source_id, target_id, provenance={"source": "preview", "preview_id": preview_id})
                db.execute(
                    "INSERT OR IGNORE INTO literature_map_edges(edge_id,map_id,kind,source_id,target_id,provenance_json,score,basis,model_version,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (edge.edge_id, map_id, edge.kind, edge.source_id, edge.target_id, _dump(edge.provenance), edge.score, edge.basis, edge.model_version, edge.content_hash),
                )
            now = iso_now()
            changed_map = bool(nodes or (updates or []) or (relations or []))
            if changed_map:
                db.execute("UPDATE literature_maps SET revision=revision+1,updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (now, map_id, owner_id))
            fresh_map = db.execute("SELECT * FROM literature_maps WHERE map_id=?", (map_id,)).fetchone()
            job = MapJob(
                uuid.uuid4().hex,
                map_id,
                "preview_apply",
                "completed",
                "apply",
                {"preview_id": preview_id},
                {"added_count": len(nodes), "updated_count": len(updates or []), "relation_count": len(relations or [])},
                [],
                None,
                now,
                now,
            )
            db.execute(
                "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.job_id, map_id, job.operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), None, params_hash, now, now),
            )
            db.execute("UPDATE literature_map_previews SET status='applied',preview_revision=preview_revision+1,updated_at=? WHERE preview_id=? AND map_id=?", (now, preview_id, map_id))
            added_node_ids = [node.node_id for node in nodes]
            result = {"map": _map(fresh_map).to_dict(), "job": job.to_dict(), "preview_id": preview_id, "added_node_ids": added_node_ids}
            if idempotency_key:
                db.execute(
                    "INSERT INTO literature_map_mutation_idempotencies(map_id,owner_id,operation,idempotency_key,params_hash,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (map_id, owner_id, "preview_apply", idempotency_key, params_hash or "", _dump(result), now),
                )
            self._append_event(db, job, event_type="preview_applied")
            return result

    def remove_node(self, map_id: str, node_id: str, owner_id: str, *, expected_revision: int, idempotency_key: str | None = None, params_hash: str | None = None) -> dict[str, Any]:
        return self._mutate_node_tombstone(map_id, node_id, owner_id, expected_revision=expected_revision, restore=False, idempotency_key=idempotency_key, params_hash=params_hash)

    def restore_node(self, map_id: str, node_id: str, owner_id: str, *, expected_revision: int, idempotency_key: str | None = None, params_hash: str | None = None) -> dict[str, Any]:
        return self._mutate_node_tombstone(map_id, node_id, owner_id, expected_revision=expected_revision, restore=True, idempotency_key=idempotency_key, params_hash=params_hash)

    def _mutate_node_tombstone(self, map_id: str, node_id: str, owner_id: str, *, expected_revision: int, restore: bool, idempotency_key: str | None, params_hash: str | None) -> dict[str, Any]:
        operation = "restore_node" if restore else "remove_node"
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            if idempotency_key:
                prior = db.execute("SELECT params_hash,result_json FROM literature_map_mutation_idempotencies WHERE map_id=? AND owner_id=? AND operation=? AND idempotency_key=?", (map_id, owner_id, operation, idempotency_key)).fetchone()
                if prior:
                    if params_hash is not None and prior["params_hash"] != params_hash:
                        raise ValueError("idempotency conflict")
                    return _load(prior["result_json"], {})
            map_row = db.execute("SELECT * FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
            node_row = db.execute("SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id=?", (map_id, node_id)).fetchone()
            if map_row is None or node_row is None:
                raise LookupError("node not found")
            if int(map_row["revision"]) != int(expected_revision):
                raise ValueError("revision conflict")
            removed = node_row["removed_at"] is not None
            if restore and not removed:
                raise ValueError("NODE_NOT_REMOVED")
            if not restore and removed:
                raise ValueError("NODE_ALREADY_REMOVED")
            if restore:
                active_count = int(db.execute("SELECT COUNT(*) FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL", (map_id,)).fetchone()[0])
                if active_count >= _MAX_MAP_NODES:
                    raise ValueError("MAP_NODE_LIMIT")
                # Keep the saved edge tombstone.  If the opposite endpoint is
                # still removed, its own tombstone (or this one) must remain
                # available for the later explicit restore of that endpoint.
                db.execute("UPDATE literature_map_nodes SET removed_at=NULL WHERE map_id=? AND node_id=?", (map_id, node_id))
                saved_edges: list[Mapping[str, Any]] = []
                for saved_row in db.execute("SELECT removed_edges_json FROM literature_map_nodes WHERE map_id=?", (map_id,)).fetchall():
                    for saved in _load(saved_row["removed_edges_json"], []):
                        if isinstance(saved, Mapping) and (saved.get("source_id") == node_id or saved.get("target_id") == node_id):
                            saved_edges.append(saved)
                active_node_ids = {str(row[0]) for row in db.execute("SELECT node_id FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL", (map_id,)).fetchall()}
                for saved in saved_edges:
                    source_id = str(saved.get("source_id") or "")
                    target_id = str(saved.get("target_id") or "")
                    if source_id not in active_node_ids or target_id not in active_node_ids or source_id == target_id:
                        continue
                    edge = MapEdge(str(saved.get("edge_id") or uuid.uuid4().hex), map_id, str(saved.get("kind") or "citation"), source_id, target_id, dict(saved.get("provenance") or {}), saved.get("score"), saved.get("basis"), saved.get("model_version"), saved.get("content_hash"))
                    try:
                        validate_edge_metadata(
                            basis=edge.basis,
                            model_version=edge.model_version,
                            content_hash=edge.content_hash,
                        )
                    except ValueError:
                        # Do not resurrect a legacy polluted edge while
                        # restoring its endpoint.
                        continue
                    db.execute("INSERT OR IGNORE INTO literature_map_edges(edge_id,map_id,kind,source_id,target_id,provenance_json,score,basis,model_version,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)", (edge.edge_id, map_id, edge.kind, edge.source_id, edge.target_id, _dump(edge.provenance), edge.score, edge.basis, edge.model_version, edge.content_hash))
            else:
                edges = db.execute("SELECT * FROM literature_map_edges WHERE map_id=? AND (source_id=? OR target_id=?)", (map_id, node_id, node_id)).fetchall()
                saved_edges = [{"edge_id": row["edge_id"], "kind": row["kind"], "source_id": row["source_id"], "target_id": row["target_id"], "provenance": _load(row["provenance_json"], {}), "score": row["score"], "basis": row["basis"], "model_version": row["model_version"], "content_hash": row["content_hash"]} for row in edges]
                db.execute("UPDATE literature_map_nodes SET removed_at=?,removed_edges_json=? WHERE map_id=? AND node_id=?", (iso_now(), _dump(saved_edges), map_id, node_id))
                db.execute("DELETE FROM literature_map_edges WHERE map_id=? AND (source_id=? OR target_id=?)", (map_id, node_id, node_id))
                removed_error = _dump({"code": "MAP_NODE_REMOVED", "message": "论文节点已移除", "retryable": False})
                child_rows = db.execute(
                    "SELECT j.job_id FROM literature_map_jobs j JOIN literature_map_analyses a ON a.job_id=j.job_id WHERE j.map_id=? AND a.node_id=? AND j.operation='analysis' AND j.status IN ('queued','running')",
                    (map_id, node_id),
                ).fetchall()
                for child in child_rows:
                    db.execute("UPDATE literature_map_jobs SET status='failed',step='finished',worker_token=NULL,lease_expires_at=NULL,next_retry_at=NULL,updated_at=? WHERE job_id=? AND status IN ('queued','running')", (iso_now(), child["job_id"]))
                    db.execute("UPDATE literature_map_analyses SET status='failed',error_json=?,updated_at=? WHERE job_id=? AND status IN ('pending','running')", (removed_error, iso_now(), child["job_id"]))
                queue_row = self._queue_row(db, map_id, owner_id)
                if queue_row is not None:
                    queue_cursor = _load(queue_row["cursor_json"], {})
                    if isinstance(queue_cursor, dict) and isinstance(queue_cursor.get("items"), dict):
                        queue_cursor["items"].pop(node_id, None)
                        queue_counts = self._queue_counts_tx(db, map_id, queue_cursor)
                        queue_state = str(queue_row["status"])
                        if queue_state != "paused":
                            queue_state = "active" if queue_counts["queued"] or queue_counts["running"] else ("partial" if queue_counts["failed"] else "completed")
                        db.execute("UPDATE literature_map_jobs SET status=?,cursor_json=?,counts_json=?,updated_at=? WHERE job_id=? AND map_id=? AND operation=?", (queue_state, _dump(queue_cursor), _dump(queue_counts), iso_now(), queue_row["job_id"], map_id, _ANALYSIS_QUEUE_OPERATION))
            now = iso_now()
            db.execute("UPDATE literature_maps SET revision=revision+1,updated_at=? WHERE map_id=? AND owner_id=?", (now, map_id, owner_id))
            fresh_map = db.execute("SELECT * FROM literature_maps WHERE map_id=?", (map_id,)).fetchone()
            restore_job = None
            if restore:
                restore_job = MapJob(uuid.uuid4().hex, map_id, "restore", "completed", "restore", {"node_id": node_id}, {}, [], None, now, now)
                db.execute(
                    "INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (restore_job.job_id, map_id, restore_job.operation, restore_job.status, restore_job.step, _dump(restore_job.cursor), _dump(restore_job.counts), _dump(restore_job.failed_units), None, None, now, now),
                )
            result = {"map": _map(fresh_map).to_dict(), ("restored_node_id" if restore else "removed_node_id"): node_id}
            if restore_job is not None:
                result["job"] = restore_job.to_dict()
            if idempotency_key:
                db.execute("INSERT INTO literature_map_mutation_idempotencies(map_id,owner_id,operation,idempotency_key,params_hash,result_json,created_at) VALUES(?,?,?,?,?,?,?)", (map_id, owner_id, operation, idempotency_key, params_hash or "", _dump(result), now))
            if restore_job is not None:
                self._append_event(db, restore_job, event_type="restored")
            return result

    def add_edges(self, map_id: str, owner_id: str, edges: Iterable[MapEdge], job_id: str | None = None) -> list[MapEdge]:
        values = list(edges)
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id, job_id=job_id)
            node_ids = {row[0] for row in db.execute("SELECT node_id FROM literature_map_nodes WHERE map_id=?", (map_id,)).fetchall()}
            for edge in values:
                if edge.source_id == edge.target_id:
                    raise ValueError("self edge is not allowed")
                validate_edge_metadata(
                    basis=edge.basis,
                    model_version=edge.model_version,
                    content_hash=edge.content_hash,
                )
                if edge.source_id not in node_ids or edge.target_id not in node_ids:
                    continue
                db.execute("INSERT INTO literature_map_edges(edge_id,map_id,kind,source_id,target_id,provenance_json,score,basis,model_version,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(map_id,kind,source_id,target_id) DO UPDATE SET provenance_json=excluded.provenance_json,score=excluded.score,basis=excluded.basis,model_version=excluded.model_version,content_hash=excluded.content_hash", (edge.edge_id, map_id, edge.kind, edge.source_id, edge.target_id, _dump(edge.provenance), edge.score, edge.basis, edge.model_version, edge.content_hash))
            self._touch(db, map_id, owner_id)
        return self.list_edges(map_id, owner_id)

    def list_edges(self, map_id: str, owner_id: str) -> list[MapEdge]:
        with self.connection() as db:
            rows = db.execute("SELECT e.* FROM literature_map_edges e JOIN literature_maps m ON m.map_id=e.map_id WHERE e.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY e.kind,e.edge_id", (map_id, owner_id)).fetchall()
        return [_edge(row) for row in rows]

    def get_embedding(self, *, model_version: str, basis: str, content_hash: str) -> list[float] | None:
        key = f"{model_version}:{basis}:{content_hash}"
        with self.connection() as db:
            row = db.execute("SELECT vector_json FROM literature_map_embedding_cache WHERE cache_key=?", (key,)).fetchone()
        value = _load(row[0], None) if row else None
        if not isinstance(value, list):
            return None
        try:
            values = [float(item) for item in value]
            _validate_embedding(values)
        except (TypeError, ValueError):
            return None
        return values

    def put_embedding(self, *, model_version: str, basis: str, content_hash: str, vector: list[float], dimension: int | None = None, expected_dimension: int | None = None) -> None:
        if dimension is not None and expected_dimension is not None and int(dimension) != int(expected_dimension):
            raise ValueError("embedding dimension mismatch")
        dimension = expected_dimension if expected_dimension is not None else dimension
        try:
            values = [float(item) for item in vector]
        except (TypeError, ValueError) as error:
            raise ValueError("embedding contains invalid value") from error
        _validate_embedding(values, dimension=dimension)
        key = f"{model_version}:{basis}:{content_hash}"
        with self.transaction() as db:
            prior = db.execute(
                "SELECT vector_json FROM literature_map_embedding_cache WHERE model_version=? AND basis=? LIMIT 1",
                (model_version, basis),
            ).fetchone()
            prior_vector = _load(prior[0], None) if prior else None
            if isinstance(prior_vector, list) and len(prior_vector) != len(values):
                raise ValueError("embedding dimension mismatch")
            db.execute("INSERT INTO literature_map_embedding_cache(cache_key,model_version,basis,content_hash,vector_json,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET vector_json=excluded.vector_json,created_at=excluded.created_at", (key, model_version, basis, content_hash, _dump(values), iso_now()))

    @staticmethod
    def request_cache_key(
        *,
        provider: str,
        operation: str,
        query: str = "",
        identifier: str = "",
        filters: Mapping[str, Any] | None = None,
        page: int = 0,
        fields: Iterable[str] | str = (),
        version: str = "literature-map-v1",
    ) -> str:
        field_values = [fields] if isinstance(fields, str) else sorted(str(item) for item in fields)
        return _dump(
            {
                "provider": str(provider),
                "operation": str(operation),
                "query": str(query),
                "identifier": str(identifier),
                "filters": dict(filters or {}),
                "page": int(page),
                "fields": field_values,
                "version": str(version),
            }
        )

    def put_request_cache(
        self,
        cache_key: str,
        payload: Any,
        *,
        ttl_seconds: int | float = 86400,
        status: str = "success",
        provider: str = "",
        operation: str = "",
        query: str = "",
        identifier: str = "",
        filters: Mapping[str, Any] | None = None,
        page: int = 0,
        fields: Iterable[str] | str = (),
        version: str = "literature-map-v1",
    ) -> bool:
        """Persist only successful provider responses for bounded reuse."""

        if status != "success":
            return False
        now = time.time()
        field_values = [fields] if isinstance(fields, str) else sorted(str(item) for item in fields)
        with self.transaction() as db:
            db.execute(
                "INSERT INTO literature_map_request_cache(cache_key,provider,operation,query_text,identifier,filters_json,page,fields_json,schema_version,status,response_json,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(cache_key) DO UPDATE SET provider=excluded.provider,operation=excluded.operation,query_text=excluded.query_text,identifier=excluded.identifier,filters_json=excluded.filters_json,page=excluded.page,fields_json=excluded.fields_json,schema_version=excluded.schema_version,status=excluded.status,response_json=excluded.response_json,expires_at=excluded.expires_at,created_at=excluded.created_at",
                (cache_key, provider, operation, query, identifier, _dump(dict(filters or {})), int(page), _dump(field_values), version, status, _dump(payload), now + max(0.0, float(ttl_seconds)), now),
            )
        return True

    def get_request_cache(self, cache_key: str | None = None, **parts: Any) -> Any | None:
        if cache_key is None:
            cache_key = self.request_cache_key(**parts)
        with self.connection() as db:
            row = db.execute(
                "SELECT response_json,status,expires_at FROM literature_map_request_cache WHERE cache_key=?",
                (cache_key,),
            ).fetchone()
        if not row or row["status"] != "success" or float(row["expires_at"]) <= time.time():
            return None
        return _load(row["response_json"], None)

    def create_job(self, map_id: str, owner_id: str, *, operation: str, idempotency_key: str | None = None, params_hash: str | None = None) -> MapJob:
        now = iso_now()
        job = MapJob(uuid.uuid4().hex, map_id, operation, "queued", "discover", {}, {"provider_count": 0, "accepted_count": 0, "node_count": 0, "citation_edge_count": 0, "similarity_edge_count": 0, "provider_request_count": 0}, [])
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id)
            if idempotency_key:
                prior = db.execute("SELECT job_id,params_hash FROM literature_map_jobs WHERE map_id=? AND idempotency_key=?", (map_id, idempotency_key)).fetchone()
                if prior:
                    if params_hash is not None and prior["params_hash"] != params_hash:
                        raise ValueError("idempotency conflict")
                    existing = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (prior["job_id"],)).fetchone()
                    return _job(existing)
            db.execute("INSERT INTO literature_map_jobs(job_id,map_id,operation,status,step,cursor_json,counts_json,failed_units_json,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (job.job_id, map_id, operation, job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), idempotency_key, params_hash, now, now))
            self._append_event(db, job)
        return job

    def claim_job(self, job_id: str, map_id: str, owner_id: str) -> MapJob | None:
        """Claim exactly one queued job while checking map ownership."""

        with self.transaction() as db:
            result = db.execute(
                "UPDATE literature_map_jobs SET status='running',updated_at=? WHERE job_id=? AND map_id=? "
                "AND status='queued' AND EXISTS (SELECT 1 FROM literature_maps m WHERE m.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL)",
                (iso_now(), job_id, map_id, map_id, owner_id),
            )
            if result.rowcount == 0:
                return None
            row = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=?", (job_id, map_id)).fetchone()
            if row is None:
                return None
            job = _job(row)
            self._append_event(db, job, event_type="started")
            return job

    @staticmethod
    def _auxiliary_job_qualified_tx(
        db: sqlite3.Connection,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        operation: str,
        worker_token: str,
        now: str,
    ) -> bool:
        row = db.execute(
            "SELECT j.status,j.worker_token,j.lease_expires_at,m.status AS map_status "
            "FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
            "WHERE j.job_id=? AND j.map_id=? AND j.operation=? AND m.owner_id=? AND m.deleted_at IS NULL",
            (job_id, map_id, operation, owner_id),
        ).fetchone()
        return bool(
            row
            and row["status"] == "running"
            and row["worker_token"] == worker_token
            and row["map_status"] != "stopped"
            and _lease_is_active(row["lease_expires_at"], now)
        )

    def claim_auxiliary_job(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        operation: str,
    ) -> tuple[MapJob, str] | None:
        """Claim a preview-page or expansion batch with a private lease token."""

        if operation not in _AUXILIARY_OPERATIONS:
            raise ValueError("MAP_AUXILIARY_OPERATION_REQUIRED")
        token = secrets.token_urlsafe(32)
        now = iso_now()
        lease_expires_at = _iso_after_seconds(_AUXILIARY_LEASE_SECONDS)
        with self.transaction() as db:
            row = db.execute(
                "SELECT j.cursor_json FROM literature_map_jobs j "
                "JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.job_id=? AND j.map_id=? AND j.operation=? AND j.status='queued' "
                "AND m.owner_id=? AND m.deleted_at IS NULL AND m.status!='stopped'",
                (job_id, map_id, operation, owner_id),
            ).fetchone()
            if row is None:
                return None
            if operation == "expand_batch":
                cursor = _load(row["cursor_json"], {})
                if not _auxiliary_batch_has_pending_metadata(cursor):
                    return None
                queue = self._queue_row(db, map_id, owner_id)
                if queue is not None and str(queue["status"]) == "paused":
                    return None
            claimed = db.execute(
                "UPDATE literature_map_jobs SET status='running',worker_token=?,lease_expires_at=?,"
                "attempts=attempts+1,next_retry_at=NULL,updated_at=? "
                "WHERE job_id=? AND map_id=? AND operation=? AND status='queued' AND attempts<? "
                "AND EXISTS (SELECT 1 FROM literature_maps m WHERE m.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL AND m.status!='stopped') "
                "RETURNING *",
                (
                    token,
                    lease_expires_at,
                    now,
                    job_id,
                    map_id,
                    operation,
                    _AUXILIARY_MAX_CLAIMS,
                    map_id,
                    owner_id,
                ),
            ).fetchone()
            if claimed is None:
                return None
            job = _job(claimed)
            self._append_event(db, job, event_type="started")
            return job, token

    def auxiliary_job_can_write(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        operation: str,
        worker_token: str,
    ) -> bool:
        """Check private auxiliary worker qualification without changing state."""

        if operation not in _AUXILIARY_OPERATIONS or not worker_token:
            return False
        with self.connection() as db:
            return self._auxiliary_job_qualified_tx(
                db,
                job_id,
                map_id,
                owner_id,
                operation=operation,
                worker_token=worker_token,
                now=iso_now(),
            )

    @contextlib.contextmanager
    def auxiliary_job_transaction(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        operation: str,
        worker_token: str,
    ) -> Iterator[sqlite3.Connection]:
        """Yield a write transaction only while an auxiliary lease is valid.

        Rechecking before commit ensures a short lease that expires during a
        domain write rolls the entire transaction back.
        """

        if operation not in _AUXILIARY_OPERATIONS or not worker_token:
            raise ValueError("auxiliary job lease invalid")
        with self.transaction() as db:
            if not self._auxiliary_job_qualified_tx(
                db,
                job_id,
                map_id,
                owner_id,
                operation=operation,
                worker_token=worker_token,
                now=iso_now(),
            ):
                raise ValueError("auxiliary job lease invalid")
            yield db
            row = db.execute(
                "SELECT status,worker_token,lease_expires_at FROM literature_map_jobs "
                "WHERE job_id=? AND map_id=? AND operation=?",
                (job_id, map_id, operation),
            ).fetchone()
            if row is None:
                raise ValueError("auxiliary job lease invalid")
            if row["status"] == "running" and row["worker_token"] == worker_token:
                if not _lease_is_active(row["lease_expires_at"], iso_now()):
                    raise ValueError("auxiliary job lease invalid")
            elif row["status"] not in {"queued", "active", "analysis_wait", "paused", "completed", "partial", "failed"} or row["worker_token"] is not None or row["lease_expires_at"] is not None:
                raise ValueError("auxiliary job lease invalid")

    def finish_expansion_batch_metadata(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        worker_token: str,
        results: Mapping[str, Mapping[str, Any]],
        model_id: str,
    ) -> MapJob | None:
        """Commit one metadata round, queue children, and release the lease atomically."""

        if not str(model_id or "").strip():
            raise ValueError("MAP_ANALYSIS_STATE_INVALID")
        with self.auxiliary_job_transaction(
            job_id,
            map_id,
            owner_id,
            operation="expand_batch",
            worker_token=worker_token,
        ) as db:
            row = db.execute(
                "SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='expand_batch'",
                (job_id, map_id),
            ).fetchone()
            if row is None:
                return None
            cursor = _load(row["cursor_json"], {})
            items = cursor.get("items") if isinstance(cursor, Mapping) else None
            if not isinstance(items, dict):
                raise ValueError("MAP_ANALYSIS_STATE_INVALID")
            queue_row = self._queue_row(db, map_id, owner_id)
            queue_paused = queue_row is not None and str(queue_row["status"]) == "paused"
            seed_id = str(cursor.get("seed_node_id") or "")
            seed_row = db.execute(
                "SELECT removed_at FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                (map_id, seed_id),
            ).fetchone() if seed_id else None
            seed_available = seed_row is not None and seed_row["removed_at"] is None
            queue_candidates: list[dict[str, Any]] = []
            ready_node_ids: list[str] = []

            for raw_node_id, result in results.items():
                node_id = str(raw_node_id)
                item = items.get(node_id)
                if not isinstance(item, dict) or not (
                    item.get("status") in {"metadata_pending", "metadata_retry"}
                    or item.get("metadata_status") in {"pending", "metadata_pending", "metadata_retry"}
                ):
                    continue
                item["attempts"] = max(0, int(item.get("attempts") or 0)) + 1
                if not seed_available:
                    _set_expansion_metadata_item(
                        item,
                        status="skipped_removed",
                        metadata_status="skipped_removed",
                        error_code=None,
                        retryable=False,
                    )
                    item.pop("metadata_refresh", None)
                    continue
                node_row = db.execute(
                    "SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id=?",
                    (map_id, node_id),
                ).fetchone()
                if node_row is None or node_row["removed_at"] is not None:
                    _set_expansion_metadata_item(
                        item,
                        status="skipped_removed",
                        metadata_status="skipped_removed",
                        error_code=None,
                        retryable=False,
                    )
                    item.pop("metadata_refresh", None)
                    continue

                node = _node(node_row)
                abstract = str(node.abstract or "").strip()
                result_status = str(result.get("status") or "")
                proof = result.get("source_proof")
                if not abstract and result_status == "metadata_ready":
                    supplied_identity = str(result.get("identity_key") or "")
                    supplied_abstract = str(result.get("abstract") or "").strip()
                    if supplied_identity != str(node.identity_key or "") or not supplied_abstract:
                        result_status = "identity_unresolved"
                    else:
                        provenance = dict(node.provenance or {})
                        if isinstance(proof, Mapping):
                            provenance["expansion_abstract_source"] = {
                                "provider": "semantic_scholar",
                                "paper_id": str(proof.get("paper_id") or "")[:200],
                                "identity_key": supplied_identity,
                            }
                        db.execute(
                            "UPDATE literature_map_nodes SET abstract=?,provenance_json=? "
                            "WHERE map_id=? AND node_id=? AND removed_at IS NULL AND (abstract IS NULL OR trim(abstract)='')",
                            (supplied_abstract, _dump(provenance), map_id, node_id),
                        )
                        refreshed = db.execute(
                            "SELECT * FROM literature_map_nodes WHERE map_id=? AND node_id=? AND removed_at IS NULL",
                            (map_id, node_id),
                        ).fetchone()
                        if refreshed is None:
                            result_status = "skipped_removed"
                        else:
                            node = _node(refreshed)
                            abstract = str(node.abstract or "").strip()

                if abstract:
                    source_version = hashlib.sha256(
                        _dump(
                            {
                                "title": node.title,
                                "abstract": node.abstract or "",
                                "external_ids": node.external_ids,
                            }
                        ).encode("utf-8")
                    ).hexdigest()
                    params_hash = hashlib.sha256(
                        _dump(
                            {
                                "evidence_level": "abstract",
                                "model": str(model_id),
                                "source_version": source_version,
                            }
                        ).encode("utf-8")
                    ).hexdigest()
                    queue_candidates.append(
                        {
                            "node_id": node_id,
                            "abstract_available": True,
                            "source_version": source_version,
                            "model_id": str(model_id),
                            "idempotency_key": f"auto:{node_id}:{source_version}:{model_id}",
                            "params_hash": params_hash,
                        }
                    )
                    ready_node_ids.append(node_id)
                    item["metadata_status"] = "complete"
                    item["metadata_refresh"] = False
                    item.pop("error_code", None)
                    item.pop("retryable", None)
                    continue

                if result_status == "skipped_no_abstract":
                    _set_expansion_metadata_item(
                        item,
                        status="skipped_no_abstract",
                        metadata_status="skipped_no_abstract",
                        error_code=None,
                        retryable=False,
                    )
                    item.pop("metadata_refresh", None)
                elif result_status == "identity_unresolved":
                    _set_expansion_metadata_item(
                        item,
                        status="identity_unresolved",
                        metadata_status="identity_unresolved",
                        error_code="MAP_METADATA_IDENTITY_UNRESOLVED",
                        retryable=False,
                    )
                    item.pop("metadata_refresh", None)
                elif result_status == "metadata_failed":
                    _set_expansion_metadata_item(
                        item,
                        status="metadata_failed",
                        metadata_status="failed",
                        error_code=_safe_error_code(result.get("error_code")) or "SEMANTIC_SCHOLAR_UNAVAILABLE",
                        retryable=bool(result.get("retryable")),
                    )
                elif result_status == "skipped_removed":
                    _set_expansion_metadata_item(
                        item,
                        status="skipped_removed",
                        metadata_status="skipped_removed",
                        error_code=None,
                        retryable=False,
                    )
                    item.pop("metadata_refresh", None)
                elif result_status == "metadata_ready":
                    _set_expansion_metadata_item(
                        item,
                        status="skipped_no_abstract",
                        metadata_status="skipped_no_abstract",
                        error_code=None,
                        retryable=False,
                    )
                    item.pop("metadata_refresh", None)
                else:
                    raise ValueError("MAP_ANALYSIS_STATE_INVALID")

            queue_items: dict[str, dict[str, Any]] = {}
            if queue_candidates:
                queue_id, queue_items = self._merge_analysis_queue_items_tx(
                    db, map_id, owner_id, queue_candidates
                )
                for node_id in ready_node_ids:
                    item = items[node_id]
                    queue_item = queue_items.get(node_id) or {}
                    if not queue_item.get("analysis_id"):
                        raise ValueError("MAP_ANALYSIS_STATE_INVALID")
                    item.update(
                        {
                            "status": "analysis_queued",
                            "metadata_status": "complete",
                            "analysis_id": queue_item.get("analysis_id"),
                            "source_version": queue_item.get("source_version"),
                            "error_code": None,
                            "retryable": False,
                        }
                    )
                queue_row = self._queue_row(db, map_id, owner_id)
                queue_paused = queue_row is not None and str(queue_row["status"]) == "paused"
                cursor["queue_job_id"] = queue_id

            status, step, counts, failed_units, projected_cursor = self._expansion_batch_projection_tx(
                db,
                map_id,
                cursor,
                prior_counts=_load(row["counts_json"], {}),
                queue_paused=queue_paused,
            )
            finished = self.finish_auxiliary_job_tx(
                db,
                job_id,
                map_id,
                owner_id,
                operation="expand_batch",
                worker_token=worker_token,
                status=status,
                step=step,
                cursor=projected_cursor,
                counts=counts,
                failed_units=failed_units,
                event_type="metadata_finished",
            )
            return finished

    def finish_auxiliary_job(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        operation: str,
        worker_token: str,
        status: str,
        step: str | None = None,
        cursor: dict[str, Any] | None = None,
        counts: dict[str, Any] | None = None,
        failed_units: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        event_type: str | None = None,
    ) -> MapJob | None:
        """Release a valid auxiliary lease with a token and deadline CAS."""

        if operation not in _AUXILIARY_OPERATIONS or not worker_token:
            return None
        if status not in {"queued", "active", "analysis_wait", "paused", "completed", "partial", "failed"}:
            raise ValueError("invalid auxiliary job status")
        with self.transaction() as db:
            return self.finish_auxiliary_job_tx(
                db,
                job_id,
                map_id,
                owner_id,
                operation=operation,
                worker_token=worker_token,
                status=status,
                step=step,
                cursor=cursor,
                counts=counts,
                failed_units=failed_units,
                error_code=error_code,
                event_type=event_type,
            )

    def finish_auxiliary_job_tx(
        self,
        db: sqlite3.Connection,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        operation: str,
        worker_token: str,
        status: str,
        step: str | None = None,
        cursor: dict[str, Any] | None = None,
        counts: dict[str, Any] | None = None,
        failed_units: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        event_type: str | None = None,
    ) -> MapJob | None:
        """Finish an auxiliary worker inside its domain-write transaction."""

        if operation not in _AUXILIARY_OPERATIONS or not worker_token:
            return None
        if status not in {"queued", "active", "analysis_wait", "paused", "completed", "partial", "failed"}:
            raise ValueError("invalid auxiliary job status")
        now = iso_now()
        row = db.execute(
            "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
            "WHERE j.job_id=? AND j.map_id=? AND j.operation=? AND j.status='running' "
            "AND j.worker_token=? AND j.lease_expires_at>? AND m.owner_id=? "
            "AND m.deleted_at IS NULL AND m.status!='stopped'",
            (job_id, map_id, operation, worker_token, now, owner_id),
        ).fetchone()
        if row is None:
            return None
        current = _job(row)
        safe_failed = _safe_failed_units(failed_units if failed_units is not None else current.failed_units)
        updated = db.execute(
            "UPDATE literature_map_jobs SET status=?,step=?,cursor_json=?,counts_json=?,failed_units_json=?,"
            "worker_token=NULL,lease_expires_at=NULL,updated_at=? WHERE job_id=? AND map_id=? "
            "AND operation=? AND status='running' AND worker_token=? AND lease_expires_at>? "
            "AND EXISTS (SELECT 1 FROM literature_maps m WHERE m.map_id=? AND m.owner_id=? "
            "AND m.deleted_at IS NULL AND m.status!='stopped') RETURNING *",
            (
                status,
                step if step is not None else current.step,
                _dump(cursor if cursor is not None else current.cursor),
                _dump(counts if counts is not None else current.counts),
                _dump(safe_failed),
                now,
                job_id,
                map_id,
                operation,
                worker_token,
                now,
                map_id,
                owner_id,
            ),
        ).fetchone()
        if updated is None:
            return None
        finished = _job(updated)
        self._append_event(
            db,
            finished,
            event_type=event_type or ("failed" if status == "failed" else "completed" if status == "completed" else "progress"),
            error_code=error_code,
        )
        return finished

    def fail_unsupported_job(self, job_id: str, map_id: str, owner_id: str, *, operation: str) -> MapJob | None:
        """Fail closed for an operation with no registered recovery handler."""

        if operation in _AUXILIARY_OPERATIONS or operation == "analysis_queue" or operation == "analysis" or operation.startswith("preview:") or operation == "create":
            return None
        now = iso_now()
        failed_units = [{"unit": operation[:80], "error_code": "MAP_JOB_OPERATION_UNSUPPORTED", "retryable": False}]
        with self.transaction() as db:
            updated = db.execute(
                "UPDATE literature_map_jobs SET status='failed',step='finished',worker_token=NULL,"
                "lease_expires_at=NULL,failed_units_json=?,updated_at=? WHERE job_id=? AND map_id=? "
                "AND operation=? AND status IN ('queued','running') AND EXISTS ("
                "SELECT 1 FROM literature_maps m WHERE m.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL) RETURNING *",
                (_dump(failed_units), now, job_id, map_id, operation, map_id, owner_id),
            ).fetchone()
            if updated is None:
                return None
            job = _job(updated)
            self._append_event(db, job, event_type="failed", error_code="MAP_JOB_OPERATION_UNSUPPORTED")
            return job

    claim_queued_job = claim_job

    def retry_job(self, job_id: str, map_id: str, owner_id: str) -> MapJob | None:
        """CAS requeue a terminal retryable job without resetting checkpoints."""

        with self.transaction() as db:
            row = db.execute(
                "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.job_id=? AND j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, owner_id),
            ).fetchone()
            if row is None or row["status"] not in {"failed", "partial", "stopped"}:
                return None
            if row["operation"] == "analysis":
                now = iso_now()
                db.execute(
                    "UPDATE literature_map_jobs SET status='queued',step='analysis',worker_token=NULL,lease_expires_at=NULL,attempts=0,next_retry_at=NULL,updated_at=? WHERE job_id=? AND map_id=? AND status IN ('failed','partial','stopped')",
                    (now, job_id, map_id),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    return None
                db.execute("UPDATE literature_map_analyses SET status='pending',result_json=NULL,error_json=NULL,updated_at=? WHERE job_id=?", (now, job_id))
                fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=?", (job_id,)).fetchone()
                job = _job(fresh)
                self._append_event(db, job, event_type="retry")
                return job
            failed_units = _load(row["failed_units_json"], [])
            if isinstance(failed_units, list) and failed_units and not any(isinstance(item, Mapping) and item.get("retryable") is True for item in failed_units):
                return None
            now = iso_now()
            db.execute(
                "UPDATE literature_map_jobs SET status='queued',updated_at=? WHERE job_id=? AND map_id=? AND status IN ('failed','partial','stopped')",
                (now, job_id, map_id),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                return None
            db.execute("UPDATE literature_maps SET status='generating',updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (now, map_id, owner_id))
            fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=?", (job_id, map_id)).fetchone()
            job = _job(fresh)
            self._append_event(db, job, event_type="retry")
            return job

    def stop_job(self, job_id: str, map_id: str, owner_id: str) -> MapJob | None:
        """Stop queued/running work; terminal states are idempotent no-ops."""

        with self.transaction() as db:
            row = db.execute(
                "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.job_id=? AND j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, owner_id),
            ).fetchone()
            if row is None:
                return None
            job = _job(row)
            if job.status in _TERMINAL_JOB_STATES:
                return job
            now = iso_now()
            db.execute("UPDATE literature_map_jobs SET status='stopped',updated_at=? WHERE job_id=? AND map_id=? AND status IN ('queued','running')", (now, job_id, map_id))
            if job.operation == "analysis":
                db.execute("UPDATE literature_map_analyses SET status='failed',error_json=?,updated_at=? WHERE job_id=? AND status IN ('pending','running')", (_dump({"code": "MAP_ANALYSIS_STOPPED", "message": "分析任务已停止", "retryable": True}), now, job_id))
            else:
                db.execute("UPDATE literature_maps SET status='stopped',updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (now, map_id, owner_id))
            fresh = db.execute("SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=?", (job_id, map_id)).fetchone()
            stopped = _job(fresh)
            self._append_event(db, stopped, event_type="stopped")
            return stopped

    def save_unit_checkpoint(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        unit_key: str,
        status: str,
        payload: Mapping[str, Any] | None = None,
        error_code: str | None = None,
        attempts: int | None = None,
    ) -> dict[str, Any]:
        if not unit_key.strip():
            raise ValueError("checkpoint unit required")
        if status not in {"queued", "running", "completed", "partial", "failed"}:
            raise ValueError("invalid checkpoint status")
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id, job_id=job_id)
            current = db.execute("SELECT attempts FROM literature_map_checkpoints WHERE job_id=? AND unit_key=?", (job_id, unit_key)).fetchone()
            next_attempts = int(attempts) if attempts is not None else (int(current[0]) if current else 0)
            if status in {"running", "queued"}:
                next_attempts = max(next_attempts, int(current[0]) + 1 if current else 1)
            now = iso_now()
            db.execute(
                "INSERT INTO literature_map_checkpoints(job_id,map_id,unit_key,status,attempts,payload_json,error_code,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(job_id,unit_key) DO UPDATE SET map_id=excluded.map_id,status=excluded.status,attempts=excluded.attempts,payload_json=excluded.payload_json,error_code=excluded.error_code,updated_at=excluded.updated_at",
                (job_id, map_id, unit_key, status, next_attempts, _dump(dict(payload or {})), _safe_error_code(error_code), now),
            )
            row = db.execute("SELECT * FROM literature_map_checkpoints WHERE job_id=? AND unit_key=?", (job_id, unit_key)).fetchone()
        return _checkpoint(row)

    def get_unit_checkpoint(self, job_id: str, map_id: str, owner_id: str, unit_key: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT c.* FROM literature_map_checkpoints c JOIN literature_maps m ON m.map_id=c.map_id "
                "WHERE c.job_id=? AND c.map_id=? AND c.unit_key=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, unit_key, owner_id),
            ).fetchone()
        return _checkpoint(row) if row else None

    def completed_units(self, job_id: str, map_id: str, owner_id: str) -> set[str]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT c.unit_key FROM literature_map_checkpoints c JOIN literature_maps m ON m.map_id=c.map_id "
                "WHERE c.job_id=? AND c.map_id=? AND c.status='completed' AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, owner_id),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def list_unit_checkpoints(self, job_id: str, map_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT c.* FROM literature_map_checkpoints c JOIN literature_maps m ON m.map_id=c.map_id "
                "WHERE c.job_id=? AND c.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY c.unit_key",
                (job_id, map_id, owner_id),
            ).fetchall()
        return [_checkpoint(row) for row in rows]

    record_unit_checkpoint = save_unit_checkpoint

    def update_node_import_result(
        self,
        map_id: str,
        node_id: str,
        owner_id: str,
        *,
        import_result: Mapping[str, Any] | None = None,
        document_id: str | None | object = _UNSET,
        download_status: str | None | object = _UNSET,
        catalog_paper_id: str | None | object = _UNSET,
    ) -> MapPaper:
        diagnostics = _UNSET
        if import_result is not None:
            if document_id is _UNSET:
                document_id = import_result.get("document_id", _UNSET)
            if download_status is _UNSET:
                download_status = import_result.get("download_status", import_result.get("status", _UNSET))
            if catalog_paper_id is _UNSET:
                catalog_paper_id = import_result.get("catalog_paper_id", _UNSET)
            diagnostics = normalize_import_diagnostics(import_result)
        updates: list[str] = []
        values: list[Any] = []
        for column, value in (("document_id", document_id), ("download_status", download_status), ("catalog_paper_id", catalog_paper_id)):
            if value is not _UNSET:
                updates.append(f"{column}=?")
                values.append(value)
        with self.transaction() as db:
            row = db.execute(
                "SELECT n.* FROM literature_map_nodes n JOIN literature_maps m ON m.map_id=n.map_id "
                "WHERE n.map_id=? AND n.node_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (map_id, node_id, owner_id),
            ).fetchone()
            if row is None:
                raise LookupError("node not found")
            if diagnostics is not _UNSET:
                provenance = _load(row["provenance_json"], {})
                if not isinstance(provenance, dict):
                    provenance = {}
                next_provenance = dict(provenance)
                if diagnostics is None:
                    next_provenance.pop(_IMPORT_DIAGNOSTICS_KEY, None)
                else:
                    next_provenance[_IMPORT_DIAGNOSTICS_KEY] = diagnostics
                if next_provenance != provenance:
                    updates.append("provenance_json=?")
                    values.append(_dump(next_provenance))
            if updates:
                db.execute("UPDATE literature_map_nodes SET " + ",".join(updates) + " WHERE map_id=? AND node_id=?", (*values, map_id, node_id))
                row = db.execute("SELECT n.* FROM literature_map_nodes n WHERE n.map_id=? AND n.node_id=?", (map_id, node_id)).fetchone()
        return _node(row)

    def get_job(self, job_id: str, map_id: str, owner_id: str) -> MapJob | None:
        with self.connection() as db:
            row = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.job_id=? AND j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL", (job_id, map_id, owner_id)).fetchone()
        return _job(row) if row else None

    def get_job_with_owner(self, job_id: str) -> tuple[MapJob, str] | None:
        with self.connection() as db:
            row = db.execute("SELECT j.*,m.owner_id FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.job_id=? AND m.deleted_at IS NULL", (job_id,)).fetchone()
        return (_job(row), str(row["owner_id"])) if row else None

    def latest_job(self, map_id: str, owner_id: str) -> MapJob | None:
        with self.connection() as db:
            row = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.map_id=? AND j.operation != ? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY j.updated_at DESC LIMIT 1", (map_id, _ANALYSIS_QUEUE_OPERATION, owner_id)).fetchone()
        return _job(row) if row else None

    def finish_job(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        status: str,
        map_status: str | None = None,
        step: str | None = None,
        cursor: dict[str, Any] | None = None,
        counts: dict[str, int] | None = None,
        failed_units: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        event_type: str = "completed",
    ) -> MapJob | None:
        """Atomically finalize a running job, map state and terminal event.

        A stop/delete that wins the same SQLite write lock makes this method a
        no-op, so a late worker cannot resurrect either the job or its map.
        """

        if status not in _TERMINAL_JOB_STATES - {"stopped"}:
            raise ValueError("invalid terminal job status")
        resolved_map_status = map_status or {"completed": "ready", "partial": "partial", "failed": "failed"}[status]
        safe_failed = _safe_failed_units(failed_units or [])
        with self.transaction() as db:
            row = db.execute(
                "SELECT j.*,m.owner_id,m.status AS map_status FROM literature_map_jobs j "
                "JOIN literature_maps m ON m.map_id=j.map_id "
                "WHERE j.job_id=? AND j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL",
                (job_id, map_id, owner_id),
            ).fetchone()
            if row is None or row["status"] != "running" or row["map_status"] == "stopped":
                return None
            job = _job(row)
            next_step = step if step is not None else job.step
            next_cursor = cursor if cursor is not None else job.cursor
            next_counts = counts if counts is not None else job.counts
            updated_at = iso_now()
            changed = db.execute(
                "UPDATE literature_map_jobs SET status=?,step=?,cursor_json=?,counts_json=?,failed_units_json=?,updated_at=? "
                "WHERE job_id=? AND map_id=? AND status='running'",
                (status, next_step, _dump(next_cursor), _dump(next_counts), _dump(safe_failed), updated_at, job_id, map_id),
            )
            if changed.rowcount != 1:
                return None
            map_changed = db.execute(
                "UPDATE literature_maps SET status=?,updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL AND status != 'stopped'",
                (resolved_map_status, updated_at, map_id, owner_id),
            )
            if map_changed.rowcount != 1:
                raise LiteratureMapStoreError("map state changed during job finish")
            final = MapJob(job.job_id, job.map_id, job.operation, status, next_step, next_cursor, next_counts, safe_failed, job.idempotency_key, job.created_at, updated_at)
            self._append_event(db, final, event_type=event_type, error_code=error_code or next((item.get("error_code") for item in safe_failed if item.get("error_code")), None))
            return final

    def update_job(self, job_id: str, map_id: str, owner_id: str, *, status: str | None = None, step: str | None = None, cursor: dict[str, Any] | None = None, counts: dict[str, int] | None = None, failed_units: list[dict[str, Any]] | None = None, error_code: str | None = None, event_type: str = "progress", expected_status: str | Iterable[str] = "running") -> MapJob | None:
        with self.transaction() as db:
            row = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.job_id=? AND j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL", (job_id, map_id, owner_id)).fetchone()
            if not row:
                return None
            job = _job(row)
            expected = {expected_status} if isinstance(expected_status, str) else {str(item) for item in expected_status}
            if not expected or job.status not in expected or status in {"queued", "stopped"}:
                return None
            if status is not None:
                job.status = status
            if step is not None:
                job.step = step
            if cursor is not None:
                job.cursor = cursor
            if counts is not None:
                job.counts = counts
            if failed_units is not None:
                job.failed_units = _safe_failed_units(failed_units)
            job.updated_at = iso_now()
            changed = db.execute("UPDATE literature_map_jobs SET status=?,step=?,cursor_json=?,counts_json=?,failed_units_json=?,updated_at=? WHERE job_id=? AND map_id=? AND status IN (" + ",".join("?" for _ in expected) + ")", (job.status, job.step, _dump(job.cursor), _dump(job.counts), _dump(job.failed_units), job.updated_at, job_id, map_id, *sorted(expected)))
            if changed.rowcount != 1:
                return None
            self._append_event(db, job, event_type=event_type, error_code=error_code)
        return self.get_job(job_id, map_id, owner_id)

    def list_events(self, map_id: str, owner_id: str, *, after_seq: int = 0, limit: int = 200) -> tuple[list[MapEvent], int]:
        with self.connection() as db:
            rows = db.execute("SELECT e.* FROM literature_map_events e JOIN literature_maps m ON m.map_id=e.map_id WHERE e.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL AND e.event_seq>? ORDER BY e.event_seq LIMIT ?", (map_id, owner_id, int(after_seq), max(1, min(int(limit), 200)))).fetchall()
        events = [_event(row) for row in rows]
        return events, (events[-1].event_seq if events else int(after_seq))

    def job_can_write(self, job_id: str, map_id: str, owner_id: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT j.job_id,j.status FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.job_id=? AND j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL", (job_id, map_id, owner_id)).fetchone()
        return bool(row and row["status"] == "running")

    def recover_auxiliary_jobs(self, owner_id: str | None = None, *, map_id: str | None = None) -> list[MapJob]:
        """Reap expired auxiliary leases and return only typed queued work."""

        recovered: list[MapJob] = []
        with self.transaction() as db:
            now = iso_now()
            batch_clause = "j.operation='expand_batch' AND m.deleted_at IS NULL"
            batch_params: list[Any] = []
            if owner_id is not None:
                batch_clause += " AND m.owner_id=?"
                batch_params.append(owner_id)
            if map_id is not None:
                batch_clause += " AND j.map_id=?"
                batch_params.append(map_id)
            batch_maps = db.execute(
                "SELECT DISTINCT j.map_id,m.owner_id FROM literature_map_jobs j "
                "JOIN literature_maps m ON m.map_id=j.map_id WHERE " + batch_clause,
                tuple(batch_params),
            ).fetchall()
            for batch_map in batch_maps:
                self._refresh_expansion_batch_projections_tx(
                    db,
                    str(batch_map["map_id"]),
                    str(batch_map["owner_id"]),
                )
            clause = "j.operation IN ('preview_page','expand_batch') AND j.status IN ('queued','running','paused') AND m.deleted_at IS NULL AND m.status!='stopped'"
            params: list[Any] = []
            if owner_id is not None:
                clause += " AND m.owner_id=?"
                params.append(owner_id)
            if map_id is not None:
                clause += " AND j.map_id=?"
                params.append(map_id)
            rows = db.execute(
                "SELECT j.*,m.owner_id FROM literature_map_jobs j "
                "JOIN literature_maps m ON m.map_id=j.map_id WHERE " + clause + " ORDER BY j.created_at,j.job_id",
                tuple(params),
            ).fetchall()
            for row in rows:
                operation = str(row["operation"])
                job_id = str(row["job_id"])
                job_map_id = str(row["map_id"])
                resolved_owner = str(row["owner_id"])
                batch_cursor = _load(row["cursor_json"], {})
                if operation == "expand_batch" and not _auxiliary_batch_has_pending_metadata(batch_cursor):
                    continue
                queue = self._queue_row(db, job_map_id, resolved_owner) if operation == "expand_batch" else None
                paused = queue is not None and str(queue["status"]) == "paused"
                status = str(row["status"])
                if status == "running":
                    if _lease_is_active(row["lease_expires_at"], now):
                        continue
                    if int(row["attempts"] or 0) >= _AUXILIARY_MAX_CLAIMS:
                        next_status = "failed"
                        error_code = "MAP_JOB_LEASE_EXHAUSTED"
                    elif paused:
                        next_status = "paused"
                        error_code = None
                    else:
                        next_status = "queued"
                        error_code = None
                    current = _job(row)
                    failed_units = list(current.failed_units)
                    if error_code:
                        failed_units.append({
                            "unit": operation,
                            "error_code": error_code,
                            "retryable": False,
                        })
                    changed = db.execute(
                        "UPDATE literature_map_jobs SET status=?,worker_token=NULL,lease_expires_at=NULL,"
                        "next_retry_at=NULL,step=?,failed_units_json=?,updated_at=? WHERE job_id=? AND map_id=? "
                        "AND operation=? AND status='running' AND (lease_expires_at IS NULL OR lease_expires_at<=?) RETURNING *",
                        (
                            next_status,
                            "finished" if error_code else current.step,
                            _dump(_safe_failed_units(failed_units)),
                            now,
                            job_id,
                            job_map_id,
                            operation,
                            now,
                        ),
                    ).fetchone()
                    if changed is None:
                        continue
                    terminal = _job(changed)
                    if operation == "preview_page" and error_code == "MAP_JOB_LEASE_EXHAUSTED":
                        preview_id = str(batch_cursor.get("preview_id") or "") if isinstance(batch_cursor, Mapping) else ""
                        target_cursor = batch_cursor.get("target_cursor") if isinstance(batch_cursor, Mapping) else None
                        preview_row = db.execute(
                            "SELECT * FROM literature_map_previews WHERE preview_id=? AND map_id=? AND job_id=?",
                            (preview_id, job_map_id, job_id),
                        ).fetchone() if preview_id else None
                        if preview_row is not None:
                            pagination = _load(preview_row["pagination_json"], None)
                            if isinstance(pagination, Mapping) and pagination.get("state") == "loading" and pagination.get("page_job_id") == job_id:
                                failed_pagination = dict(pagination)
                                failed_pagination.update({
                                    "state": "failed",
                                    "failed_cursor": target_cursor if isinstance(target_cursor, int) and not isinstance(target_cursor, bool) else None,
                                    "last_error": "MAP_JOB_LEASE_EXHAUSTED",
                                })
                                db.execute(
                                    "UPDATE literature_map_previews SET status='failed',pagination_json=?,preview_revision=preview_revision+1,updated_at=? "
                                    "WHERE preview_id=? AND map_id=? AND job_id=? AND preview_revision=?",
                                    (_dump(failed_pagination), now, preview_id, job_map_id, job_id, preview_row["preview_revision"]),
                                )
                    self._append_event(
                        db,
                        terminal,
                        event_type="failed" if error_code else "paused" if paused else "recovered",
                        error_code=error_code,
                    )
                elif status == "queued" and paused:
                    changed = db.execute(
                        "UPDATE literature_map_jobs SET status='paused',worker_token=NULL,lease_expires_at=NULL,updated_at=? "
                        "WHERE job_id=? AND map_id=? AND operation='expand_batch' AND status='queued' RETURNING *",
                        (now, job_id, job_map_id),
                    ).fetchone()
                    if changed is not None:
                        self._append_event(db, _job(changed), event_type="paused")
                elif status == "paused" and not paused:
                    changed = db.execute(
                        "UPDATE literature_map_jobs SET status='queued',worker_token=NULL,lease_expires_at=NULL,updated_at=? "
                        "WHERE job_id=? AND map_id=? AND operation='expand_batch' AND status='paused' RETURNING *",
                        (now, job_id, job_map_id),
                    ).fetchone()
                    if changed is not None:
                        self._append_event(db, _job(changed), event_type="resumed")

            queued_clause = "j.operation IN ('preview_page','expand_batch') AND j.status='queued' AND m.deleted_at IS NULL AND m.status!='stopped'"
            queued_params: list[Any] = []
            if owner_id is not None:
                queued_clause += " AND m.owner_id=?"
                queued_params.append(owner_id)
            if map_id is not None:
                queued_clause += " AND j.map_id=?"
                queued_params.append(map_id)
            queued_rows = db.execute(
                "SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE "
                + queued_clause + " ORDER BY j.created_at,j.job_id",
                tuple(queued_params),
            ).fetchall()
            recovered = [
                _job(row)
                for row in queued_rows
                if row["operation"] == "preview_page"
                or _auxiliary_batch_has_pending_metadata(_load(row["cursor_json"], {}))
            ]
        return recovered

    def recover_jobs(self, owner_id: str | None = None) -> list[MapJob]:
        with self.connection() as db:
            clause = " WHERE j.status IN ('queued','running') AND m.deleted_at IS NULL"
            params: tuple[Any, ...] = ()
            if owner_id is not None:
                clause += " AND m.owner_id=?"
                params = (owner_id,)
            rows = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id" + clause, params).fetchall()
        return [_job(row) for row in rows]

    def retry_expansion_batch_metadata(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        node_ids: Iterable[str],
        steps: Iterable[str],
        idempotency_key: str,
        params_hash: str,
    ) -> MapJob | None:
        selected = sorted({str(value).strip() for value in node_ids if str(value).strip()})
        selected_steps = list(steps)
        if not selected or len(selected) > 20 or selected_steps != ["metadata"]:
            raise ValueError("MAP_BATCH_METADATA_RETRY_INVALID")
        if not str(idempotency_key or "").strip() or len(idempotency_key) > 200:
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        operation = "expand_batch:retry_metadata"
        with self.transaction() as db:
            self._assert_map_exists(db, map_id, owner_id)
            try:
                replay = self._queue_command_replay(
                    db, map_id, owner_id, operation, idempotency_key, params_hash
                )
            except ValueError as error:
                if str(error) == "idempotency conflict":
                    raise ValueError("MAP_IDEMPOTENCY_CONFLICT") from error
                raise
            if replay is not None:
                fresh = db.execute(
                    "SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='expand_batch'",
                    (job_id, map_id),
                ).fetchone()
                return _job(fresh) if fresh is not None else None
            row = db.execute(
                "SELECT * FROM literature_map_jobs WHERE job_id=? AND map_id=? AND operation='expand_batch'",
                (job_id, map_id),
            ).fetchone()
            if row is None:
                return None
            current = _job(row)
            if current.status not in {"completed", "partial", "failed"}:
                raise ValueError("MAP_BATCH_METADATA_RETRY_INVALID")
            cursor = _load(row["cursor_json"], {})
            items = cursor.get("items") if isinstance(cursor, Mapping) else None
            if not isinstance(items, dict):
                raise ValueError("MAP_ANALYSIS_STATE_INVALID")
            for node_id in selected:
                item = items.get(node_id)
                if not isinstance(item, dict) or item.get("status") not in {
                    "metadata_failed",
                    "skipped_no_abstract",
                }:
                    raise ValueError("MAP_BATCH_METADATA_RETRY_INVALID")
            generation = max(0, int(cursor.get("metadata_retry_generation") or 0)) + 1
            cursor["metadata_retry_generation"] = generation
            for node_id in selected:
                item = items[node_id]
                item.update(
                    {
                        "status": "metadata_pending",
                        "metadata_status": "pending",
                        "metadata_refresh": True,
                        "retry_generation": generation,
                    }
                )
                item.pop("error_code", None)
                item.pop("retryable", None)
            queue_row = self._queue_row(db, map_id, owner_id)
            queue_paused = queue_row is not None and str(queue_row["status"]) == "paused"
            status, step, counts, failed_units, projected_cursor = self._expansion_batch_projection_tx(
                db,
                map_id,
                cursor,
                prior_counts=current.counts,
                queue_paused=queue_paused,
            )
            now = iso_now()
            changed = db.execute(
                "UPDATE literature_map_jobs SET status=?,step=?,cursor_json=?,counts_json=?,failed_units_json=?,"
                "worker_token=NULL,lease_expires_at=NULL,attempts=0,next_retry_at=NULL,updated_at=? "
                "WHERE job_id=? AND map_id=? AND operation='expand_batch' AND status IN ('completed','partial','failed') "
                "RETURNING *",
                (
                    status,
                    step,
                    _dump(projected_cursor),
                    _dump(counts),
                    _dump(_safe_failed_units(failed_units)),
                    now,
                    job_id,
                    map_id,
                ),
            ).fetchone()
            if changed is None:
                raise ValueError("MAP_BATCH_METADATA_RETRY_INVALID")
            updated = _job(changed)
            self._append_event(db, updated, event_type="metadata_retry")
            self._remember_queue_command(
                db,
                map_id,
                owner_id,
                operation,
                idempotency_key,
                params_hash,
                {"batch_job_id": job_id, "node_ids": selected, "generation": generation},
            )
            return updated

    def _assert_writable(self, db: sqlite3.Connection, map_id: str, owner_id: str, *, job_id: str | None = None) -> None:
        if job_id is not None:
            row = db.execute(
                "SELECT m.status,j.status AS job_status FROM literature_maps m JOIN literature_map_jobs j ON j.map_id=m.map_id "
                "WHERE m.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL AND j.job_id=?",
                (map_id, owner_id, job_id),
            ).fetchone()
            if not row:
                raise LookupError("map job not found")
            if row["job_status"] != "running":
                raise ValueError("job is not running")
        else:
            row = db.execute("SELECT status FROM literature_maps WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (map_id, owner_id)).fetchone()
        if not row:
            raise LookupError("map not found")
        if row["status"] == "stopped":
            raise ValueError("map stopped")

    @staticmethod
    def _insert_node(db: sqlite3.Connection, node: MapPaper) -> None:
        LiteratureMapStore._assert_group_reference(db, node.map_id, node.group_id)
        normalized_color = _validate_color_override(node.color_override)
        db.execute(
            "INSERT INTO literature_map_nodes(node_id,map_id,identity_key,external_ids_json,title,authors_json,year,venue,abstract,keywords_json,citation_count,source_url,provenance_json,catalog_paper_id,document_id,download_status,position_json,group_id,removed_at,removed_edges_json,color_override) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (node.node_id, node.map_id, node.identity_key or uuid.uuid4().hex, _dump(node.external_ids), node.title, _dump(list(node.authors)), node.year, node.venue, node.abstract, _dump(list(node.keywords)), node.citation_count, node.source_url, _dump(node.provenance), node.catalog_paper_id, node.document_id, node.download_status, _dump(node.position) if node.position else None, node.group_id, None, None, normalized_color),
        )

    @staticmethod
    def _assert_group_reference(db: sqlite3.Connection, map_id: str, group_id: str | None) -> None:
        if group_id is None:
            return
        group_key = _validate_group_id(group_id)
        row = db.execute(
            "SELECT 1 FROM literature_map_groups WHERE map_id=? AND group_id=?",
            (map_id, group_key),
        ).fetchone()
        if row is None:
            raise LookupError("group not found")

    def _touch(self, db: sqlite3.Connection, map_id: str, owner_id: str) -> None:
        db.execute("UPDATE literature_maps SET updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (iso_now(), map_id, owner_id))

    @staticmethod
    def _append_event(db: sqlite3.Connection, job: MapJob, *, event_type: str = "progress", error_code: str | None = None) -> None:
        row = db.execute("SELECT COALESCE(MAX(event_seq),0)+1 FROM literature_map_events WHERE map_id=?", (job.map_id,)).fetchone()
        db.execute("INSERT INTO literature_map_events(map_id,event_seq,job_id,type,status,step,counts_json,error_code,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (job.map_id, int(row[0]), job.job_id, event_type, job.status, job.step, _dump(job.counts), _safe_error_code(error_code), iso_now()))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
def _validate_group_name(value: object) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 80:
        raise ValueError("INVALID_GROUP_NAME")
    return name


def _validate_group_color(value: object) -> str:
    color = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("INVALID_GROUP_COLOR")
    return color.upper()


def _validate_color_override(value: object) -> str | None:
    if value is None:
        return None
    color = str(value).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("INVALID_COLOR_OVERRIDE")
    return color.upper()


def _validate_node_style(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("INVALID_NODE_STYLE")
    if set(value) != {"fill_mode", "fill_opacity"}:
        raise ValueError("INVALID_NODE_STYLE")
    fill_mode = value.get("fill_mode")
    opacity = value.get("fill_opacity")
    if fill_mode not in {"filled", "outline"}:
        raise ValueError("INVALID_NODE_STYLE")
    if isinstance(opacity, bool):
        raise ValueError("INVALID_NODE_STYLE")
    try:
        normalized_opacity = float(opacity)
    except (TypeError, ValueError):
        raise ValueError("INVALID_NODE_STYLE") from None
    if not math.isfinite(normalized_opacity) or not 0 <= normalized_opacity <= 1:
        raise ValueError("INVALID_NODE_STYLE")
    return {"fill_mode": fill_mode, "fill_opacity": normalized_opacity}


def _validate_group_id(value: object) -> str:
    group_id = str(value or "").strip()
    if not group_id or len(group_id) > 100:
        raise ValueError("INVALID_GROUP_ID")
    return group_id


def _validate_tag_id(value: object) -> str:
    tag_id = str(value or "").strip()
    if not tag_id or len(tag_id) > 100:
        raise ValueError("INVALID_TAG_ID")
    return tag_id


def _validate_tag_name(value: object) -> str:
    # Mirrors ``_validate_group_name``: non-empty after strip, <= 80 chars.
    name = str(value or "").strip()
    if not name or len(name) > 80:
        raise ValueError("INVALID_TAG_NAME")
    return name


def _validate_tag_color(value: object, default: str = "#8d80e6") -> str:
    # ``#RRGGBB`` only.  A truly absent color (``None``) falls back to the
    # default brand color; any explicit (even empty) value is validated.
    if value is None:
        return default.upper()
    color = str(value).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("INVALID_TAG_COLOR")
    return color.upper()


def _assert_revision(map_row: sqlite3.Row, expected_revision: int) -> None:
    if int(map_row["revision"]) != int(expected_revision):
        raise ValueError("revision conflict")


def _increment_map_revision(db: sqlite3.Connection, map_id: str, owner_id: str, now: str) -> None:
    changed = db.execute(
        "UPDATE literature_maps SET revision=revision+1,updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL",
        (now, map_id, owner_id),
    )
    if changed.rowcount != 1:
        raise LookupError("map not found")


def _load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _map(row: sqlite3.Row) -> LiteratureMap:
    view = _load(row["view_json"], {})
    if not isinstance(view, dict):
        view = {}
    view.setdefault("label_mode", "all")
    node_style = view.get("node_style")
    try:
        view["node_style"] = _validate_node_style(node_style) if node_style is not None else {"fill_mode": "filled", "fill_opacity": 0.3}
    except ValueError:
        view["node_style"] = {"fill_mode": "filled", "fill_opacity": 0.3}
    return LiteratureMap(row["map_id"], row["owner_id"], row["name"], row["topic"], row["project_id"], _load(row["filters_json"], {}), int(row["requested_count"]), int(row["revision"]), row["status"], view, row["created_at"], row["updated_at"])


def _node(row: sqlite3.Row) -> MapPaper:
    color_override = row["color_override"]
    return MapPaper(row["node_id"], row["map_id"], _load(row["external_ids_json"], {}), row["title"], tuple(_load(row["authors_json"], [])), row["year"], row["venue"], row["abstract"], tuple(_load(row["keywords_json"], [])), row["citation_count"], row["source_url"], _load(row["provenance_json"], {}), row["catalog_paper_id"], row["document_id"], row["download_status"], _load(row["position_json"], None), row["group_id"], row["identity_key"], bool(row["removed_at"]), color_override)


def _group(row: sqlite3.Row) -> MapGroup:
    return MapGroup(row["group_id"], row["map_id"], row["name"], row["color"], row["created_at"], row["updated_at"])


@dataclass(frozen=True)
class MapTag:
    tag_id: str
    owner_id: str
    name: str
    color: str
    created_at: str
    updated_at: str


def _tag(row: sqlite3.Row) -> MapTag:
    return MapTag(
        row["tag_id"],
        row["owner_id"],
        row["name"],
        row["color"],
        row["created_at"],
        row["updated_at"],
    )


def _edge(row: sqlite3.Row) -> MapEdge:
    return MapEdge(row["edge_id"], row["map_id"], row["kind"], row["source_id"], row["target_id"], _load(row["provenance_json"], {}), row["score"], row["basis"], row["model_version"], row["content_hash"])


def _job(row: sqlite3.Row) -> MapJob:
    worker_token = row["worker_token"]
    lease_expires_at = row["lease_expires_at"]
    return MapJob(
        row["job_id"],
        row["map_id"],
        row["operation"],
        row["status"],
        row["step"],
        _load(row["cursor_json"], {}),
        _load(row["counts_json"], {}),
        _load(row["failed_units_json"], []),
        row["idempotency_key"],
        row["created_at"],
        row["updated_at"],
        worker_token,
        lease_expires_at,
    )


def _preview(row: sqlite3.Row) -> MapPreview:
    columns = set(row.keys())
    pagination = _load(row["pagination_json"], None) if "pagination_json" in columns else None
    return MapPreview(
        row["preview_id"],
        row["map_id"],
        row["job_id"],
        row["kind"],
        row["status"],
        int(row["base_revision"]),
        _load(row["candidates_json"], []),
        _load(row["diff_json"], []),
        _load(row["warnings_json"], []),
        row["idempotency_key"],
        row["created_at"],
        row["updated_at"],
        int(row["preview_revision"]) if "preview_revision" in columns else 1,
        pagination if isinstance(pagination, dict) else None,
    )


def _event(row: sqlite3.Row) -> MapEvent:
    return MapEvent(int(row["event_seq"]), row["map_id"], row["job_id"], row["type"], row["status"], row["step"], _load(row["counts_json"], {}), row["error_code"], row["created_at"])


def _checkpoint(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "map_id": row["map_id"],
        "unit_key": row["unit_key"],
        "status": row["status"],
        "attempts": int(row["attempts"]),
        "payload": _load(row["payload_json"], {}),
        "error_code": row["error_code"],
        "updated_at": row["updated_at"],
    }


def _validate_embedding(values: list[float], *, dimension: int | None = None) -> None:
    if not values or (dimension is not None and len(values) != int(dimension)):
        raise ValueError("embedding invalid dimension")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("embedding contains non-finite value")
    if math.sqrt(sum(value * value for value in values)) <= 0.0:
        raise ValueError("embedding has empty norm")


def _safe_error_code(error_code: str | None) -> str | None:
    if error_code is None:
        return None
    value = str(error_code).strip()
    return value if _ERROR_CODE_RE.fullmatch(value) else "MAP_INTERNAL_ERROR"


def _safe_failed_units(failed_units: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for unit in failed_units:
        safe.append(
            {
                "unit": str(unit.get("unit", "unknown"))[:200],
                "error_code": _safe_error_code(unit.get("error_code")) or "MAP_INTERNAL_ERROR",
                "retryable": bool(unit.get("retryable", False)),
            }
        )
    return safe


def _analysis(row: sqlite3.Row) -> MapAnalysis:
    result = _load(row["result_json"], None)
    error = _load(row["error_json"], None)
    return MapAnalysis(
        str(row["analysis_id"]),
        str(row["map_id"]),
        str(row["node_id"]),
        int(row["version"]),
        str(row["status"]),
        str(row["evidence_level"]),
        str(row["source_version"]),
        str(row["model_id"]),
        str(row["job_id"]),
        result if isinstance(result, dict) else None,
        error if isinstance(error, dict) else None,
        row["idempotency_key"],
        str(row["created_at"]),
        str(row["updated_at"]),
    )


def _binding(row: sqlite3.Row) -> MapConversationBinding:
    context = _load(row["context_json"], {})
    return MapConversationBinding(
        str(row["binding_id"]),
        str(row["owner_id"]),
        str(row["map_id"]),
        str(row["node_id"]),
        str(row["conversation_id"]),
        row["project_id_snapshot"],
        str(row["evidence_level"]),
        str(row["source_version"]),
        context if isinstance(context, dict) else {},
        str(row["status"]),
        row["idempotency_key"],
        str(row["created_at"]),
        str(row["updated_at"]),
    )


def _safe_analysis_error(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    code = str(value.get("code") or "MAP_ANALYSIS_FAILED")
    if not _ERROR_CODE_RE.fullmatch(code):
        code = "MAP_ANALYSIS_FAILED"
    return {
        "code": code,
        "message": str(value.get("message") or "分析未完成")[:300],
        "retryable": bool(value.get("retryable", False)),
    }


def _queue_item_status(status: str) -> str:
    return {"pending": "queued", "running": "running", "completed": "completed", "failed": "failed"}.get(str(status), "queued")


def _job_retry_at(db: sqlite3.Connection, job_id: str) -> str | None:
    row = db.execute("SELECT next_retry_at FROM literature_map_jobs WHERE job_id=?", (job_id,)).fetchone()
    return str(row[0]) if row and row[0] else None


def _retry_delay_seconds(attempts: int) -> int:
    # Persist a bounded backoff marker.  User-triggered retry may clear it;
    # no worker sleeps or spins in-process.
    return min(60, 2 ** max(0, min(int(attempts) - 1, 6)))


def _iso_after_seconds(seconds: int | float) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, float(seconds)))).isoformat()


def _lease_is_active(value: Any, now: str) -> bool:
    if not value:
        return False
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value)) > datetime.fromisoformat(str(now))
    except (TypeError, ValueError):
        return False


def _auxiliary_batch_has_pending_metadata(cursor: Any) -> bool:
    if not isinstance(cursor, Mapping) or cursor.get("version") != 1:
        return False
    items = cursor.get("items")
    if not isinstance(items, Mapping):
        return False
    pending = {"pending", "metadata_pending", "metadata_retry"}
    return any(
        isinstance(item, Mapping)
        and (
            str(item.get("metadata_status") or "") in pending
            or str(item.get("status") or "") in pending
        )
        for item in items.values()
    )


def _set_expansion_metadata_item(
    item: dict[str, Any],
    *,
    status: str,
    metadata_status: str,
    error_code: str | None,
    retryable: bool,
) -> None:
    item.update(
        {
            "status": status,
            "metadata_status": metadata_status,
            "error_code": _safe_error_code(error_code),
            "retryable": bool(retryable),
        }
    )


def _verified_preview_identity(candidate: Mapping[str, Any]) -> str:
    external_ids = candidate.get("external_ids")
    if not isinstance(external_ids, Mapping):
        return ""
    try:
        identity = deterministic_identity_key(external_ids)
    except (TypeError, ValueError):
        return ""
    if not identity or str(candidate.get("identity_key") or "") != identity:
        return ""
    return identity


__all__ = ["LiteratureMapStore", "LiteratureMapStoreError", "default_database_path"]
