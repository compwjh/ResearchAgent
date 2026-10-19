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
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from backend.app.literature_maps.domain.import_diagnostics import normalize_import_diagnostics
from backend.app.literature_maps.domain.models import (
    LiteratureMap,
    MapEdge,
    MapEvent,
    MapJob,
    MapPaper,
    MapPreview,
    iso_now,
)
from backend.app.platform.config import BASE_DIR

SCHEMA_VERSION = 3
_WRITE_LOCK = threading.RLock()
_UNSET = object()
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_IMPORT_DIAGNOSTICS_KEY = "import_diagnostics"
_TERMINAL_JOB_STATES = {"completed", "failed", "partial", "stopped"}
_MAX_MAP_NODES = 200


class LiteratureMapStoreError(RuntimeError):
    """Stable store error that routes can map to a 503."""


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
        # runs; keep schema DDL outside ``transaction()`` and make the version
        # marker idempotent. Runtime writes still use BEGIN IMMEDIATE.
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
                """
            )
            node_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(literature_map_nodes)").fetchall()}
            if "removed_at" not in node_columns:
                db.execute("ALTER TABLE literature_map_nodes ADD COLUMN removed_at TEXT")
            if "removed_edges_json" not in node_columns:
                db.execute("ALTER TABLE literature_map_nodes ADD COLUMN removed_edges_json TEXT")
            preview_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(literature_map_previews)").fetchall()}
            if "node_id" not in preview_columns:
                db.execute("ALTER TABLE literature_map_previews ADD COLUMN node_id TEXT")
            if "query_text" not in preview_columns:
                db.execute("ALTER TABLE literature_map_previews ADD COLUMN query_text TEXT")
            db.execute("BEGIN IMMEDIATE")
            try:
                self._repair_legacy_idempotency_bindings(db)
                db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_literature_map_idempotency_owner_key "
                    "ON literature_map_idempotencies(owner_id, idempotency_key)"
                )
                db.execute("COMMIT")
            except Exception:
                with contextlib.suppress(sqlite3.Error):
                    db.execute("ROLLBACK")
                raise
            db.execute("INSERT OR IGNORE INTO literature_map_schema(version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, iso_now()))

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
        item = LiteratureMap(uuid.uuid4().hex, owner_id, (name or topic).strip()[:200], topic.strip(), project_id, filters or {}, int(requested_count), 0, "generating", {"viewport": {"x": 0, "y": 0, "scale": 1}, "layers": {"citation": True, "similarity": True}}, now, now)
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
                {"viewport": {"x": 0, "y": 0, "scale": 1}, "layers": {"citation": True, "similarity": True}},
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

    def update_view(self, map_id: str, owner_id: str, *, expected_revision: int, positions: list[dict[str, Any]], viewport: dict[str, Any] | None, filters: dict[str, Any] | None, layers: dict[str, Any] | None) -> LiteratureMap:
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
            db.execute("DELETE FROM literature_map_jobs WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_edges WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_nodes WHERE map_id=?", (map_id,))
            db.execute("DELETE FROM literature_map_idempotencies WHERE map_id=?", (map_id,))
            return True

    def add_nodes(self, map_id: str, owner_id: str, nodes: Iterable[MapPaper], job_id: str | None = None) -> list[MapPaper]:
        values = list(nodes)
        with self.transaction() as db:
            self._assert_writable(db, map_id, owner_id, job_id=job_id)
            for node in values:
                db.execute(
                    "INSERT INTO literature_map_nodes(node_id,map_id,identity_key,external_ids_json,title,authors_json,year,venue,abstract,keywords_json,citation_count,source_url,provenance_json,catalog_paper_id,document_id,download_status,position_json,group_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(map_id,identity_key) DO UPDATE SET title=excluded.title,authors_json=excluded.authors_json,year=excluded.year,venue=excluded.venue,abstract=excluded.abstract,keywords_json=excluded.keywords_json,citation_count=excluded.citation_count,source_url=excluded.source_url,provenance_json=excluded.provenance_json,catalog_paper_id=excluded.catalog_paper_id,document_id=excluded.document_id,download_status=excluded.download_status",
                    (node.node_id, map_id, node.identity_key or uuid.uuid4().hex, _dump(node.external_ids), node.title, _dump(list(node.authors)), node.year, node.venue, node.abstract, _dump(list(node.keywords)), node.citation_count, node.source_url, _dump(node.provenance), node.catalog_paper_id, node.document_id, node.download_status, _dump(node.position) if node.position else None, node.group_id),
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
            job = MapJob(
                uuid.uuid4().hex,
                map_id,
                f"preview:{kind}",
                status,
                "preview",
                {"preview_id": ""},
                {"candidate_count": len(candidates), "provider_request_count": max(0, int(provider_request_count))},
                [],
                None,
                now,
                now,
            )
            preview_id = uuid.uuid4().hex
            job.cursor = {"preview_id": preview_id}
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
            )
            db.execute(
                "INSERT INTO literature_map_previews(preview_id,map_id,job_id,kind,status,base_revision,candidates_json,diff_json,warnings_json,node_id,query_text,idempotency_key,params_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (preview.preview_id, map_id, job.job_id, kind, preview.status, preview.base_revision, _dump(preview.candidates), _dump(preview.diff), _dump(preview.warnings), node_id, query, idempotency_key, params_hash, now, now),
            )
            self._append_event(db, job, event_type="preview_completed" if preview.status == "completed" else "preview_queued")
            return preview, job, True

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
            db.execute("UPDATE literature_map_previews SET status=?,candidates_json=?,diff_json=?,warnings_json=?,updated_at=? WHERE map_id=? AND preview_id=?", (status, _dump(candidates), _dump(diff or []), _dump(warnings or []), now, map_id, preview_id))
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
            db.execute("UPDATE literature_map_previews SET status='applied',updated_at=? WHERE preview_id=? AND map_id=?", (now, preview_id, map_id))
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
                    db.execute("INSERT OR IGNORE INTO literature_map_edges(edge_id,map_id,kind,source_id,target_id,provenance_json,score,basis,model_version,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)", (edge.edge_id, map_id, edge.kind, edge.source_id, edge.target_id, _dump(edge.provenance), edge.score, edge.basis, edge.model_version, edge.content_hash))
            else:
                edges = db.execute("SELECT * FROM literature_map_edges WHERE map_id=? AND (source_id=? OR target_id=?)", (map_id, node_id, node_id)).fetchall()
                saved_edges = [{"edge_id": row["edge_id"], "kind": row["kind"], "source_id": row["source_id"], "target_id": row["target_id"], "provenance": _load(row["provenance_json"], {}), "score": row["score"], "basis": row["basis"], "model_version": row["model_version"], "content_hash": row["content_hash"]} for row in edges]
                db.execute("UPDATE literature_map_nodes SET removed_at=?,removed_edges_json=? WHERE map_id=? AND node_id=?", (iso_now(), _dump(saved_edges), map_id, node_id))
                db.execute("DELETE FROM literature_map_edges WHERE map_id=? AND (source_id=? OR target_id=?)", (map_id, node_id, node_id))
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
            row = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL ORDER BY j.updated_at DESC LIMIT 1", (map_id, owner_id)).fetchone()
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

    def recover_jobs(self, owner_id: str | None = None) -> list[MapJob]:
        with self.connection() as db:
            clause = " WHERE j.status IN ('queued','running') AND m.deleted_at IS NULL"
            params: tuple[Any, ...] = ()
            if owner_id is not None:
                clause += " AND m.owner_id=?"
                params = (owner_id,)
            rows = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id" + clause, params).fetchall()
        return [_job(row) for row in rows]

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
        db.execute(
            "INSERT INTO literature_map_nodes(node_id,map_id,identity_key,external_ids_json,title,authors_json,year,venue,abstract,keywords_json,citation_count,source_url,provenance_json,catalog_paper_id,document_id,download_status,position_json,group_id,removed_at,removed_edges_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (node.node_id, node.map_id, node.identity_key or uuid.uuid4().hex, _dump(node.external_ids), node.title, _dump(list(node.authors)), node.year, node.venue, node.abstract, _dump(list(node.keywords)), node.citation_count, node.source_url, _dump(node.provenance), node.catalog_paper_id, node.document_id, node.download_status, _dump(node.position) if node.position else None, node.group_id, None, None),
        )

    def _touch(self, db: sqlite3.Connection, map_id: str, owner_id: str) -> None:
        db.execute("UPDATE literature_maps SET updated_at=? WHERE map_id=? AND owner_id=? AND deleted_at IS NULL", (iso_now(), map_id, owner_id))

    @staticmethod
    def _append_event(db: sqlite3.Connection, job: MapJob, *, event_type: str = "progress", error_code: str | None = None) -> None:
        row = db.execute("SELECT COALESCE(MAX(event_seq),0)+1 FROM literature_map_events WHERE map_id=?", (job.map_id,)).fetchone()
        db.execute("INSERT INTO literature_map_events(map_id,event_seq,job_id,type,status,step,counts_json,error_code,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (job.map_id, int(row[0]), job.job_id, event_type, job.status, job.step, _dump(job.counts), _safe_error_code(error_code), iso_now()))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _map(row: sqlite3.Row) -> LiteratureMap:
    return LiteratureMap(row["map_id"], row["owner_id"], row["name"], row["topic"], row["project_id"], _load(row["filters_json"], {}), int(row["requested_count"]), int(row["revision"]), row["status"], _load(row["view_json"], {}), row["created_at"], row["updated_at"])


def _node(row: sqlite3.Row) -> MapPaper:
    return MapPaper(row["node_id"], row["map_id"], _load(row["external_ids_json"], {}), row["title"], tuple(_load(row["authors_json"], [])), row["year"], row["venue"], row["abstract"], tuple(_load(row["keywords_json"], [])), row["citation_count"], row["source_url"], _load(row["provenance_json"], {}), row["catalog_paper_id"], row["document_id"], row["download_status"], _load(row["position_json"], None), row["group_id"], row["identity_key"], bool(row["removed_at"]))


def _edge(row: sqlite3.Row) -> MapEdge:
    return MapEdge(row["edge_id"], row["map_id"], row["kind"], row["source_id"], row["target_id"], _load(row["provenance_json"], {}), row["score"], row["basis"], row["model_version"], row["content_hash"])


def _job(row: sqlite3.Row) -> MapJob:
    return MapJob(row["job_id"], row["map_id"], row["operation"], row["status"], row["step"], _load(row["cursor_json"], {}), _load(row["counts_json"], {}), _load(row["failed_units_json"], []), row["idempotency_key"], row["created_at"], row["updated_at"])


def _preview(row: sqlite3.Row) -> MapPreview:
    return MapPreview(row["preview_id"], row["map_id"], row["job_id"], row["kind"], row["status"], int(row["base_revision"]), _load(row["candidates_json"], []), _load(row["diff_json"], []), _load(row["warnings_json"], []), row["idempotency_key"], row["created_at"], row["updated_at"])


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


__all__ = ["LiteratureMapStore", "LiteratureMapStoreError", "default_database_path"]
