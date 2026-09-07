"""SQLite persistence for conference search sessions and paper candidates."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from backend.app.core.config import BASE_DIR
from backend.app.domain.paper_discovery import (
    CatalogPaper,
    CatalogSourceRecord,
    ConferenceSource,
    PaperCandidate,
    SearchEvent,
    SearchJob,
    SearchResult,
    SearchSession,
    SearchSourceProgress,
    SourceFetchUnit,
)
from backend.app.services.paper_discovery_normalization import normalize_doi, normalize_title

SCHEMA_VERSION = 2
BUILT_IN_CONFERENCES = (
    ("ccs", "ACM Conference on Computer and Communications Security", "CCS", "conf/ccs", ["ACM Conference on Computer and Communications Security"]),
    ("usenix-security", "USENIX Security Symposium", "USENIX Security", "conf/uss", ["USENIX Security Symposium", "USENIX Security"]),
    ("ieee-sp", "IEEE Symposium on Security and Privacy", "IEEE S&P", "conf/sp", ["IEEE Symposium on Security and Privacy"]),
    ("ndss", "Network and Distributed System Security Symposium", "NDSS", "conf/ndss", ["Network and Distributed System Security Symposium"]),
)
USENIX_DISCOVERY_ROUTES = [
    {
        "route_type": "usenix_accepted",
        "listing_url_template": "https://www.usenix.org/conference/usenixsecurity{yy}/cycle{cycle}-accepted-papers",
        "enabled": True,
        "rate_limit_seconds": 1.0,
    },
    {"route_type": "arxiv_fallback", "enabled": True, "rate_limit_seconds": 3.0},
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class PaperDiscoveryStore:
    """Store each candidate in the scope of its search session.

    ``candidate_id`` is a stable domain identifier and is intentionally not a
    global database key.  A paper can therefore occur in multiple searches
    without one search overwriting or rejecting another search's snapshot.
    """

    def __init__(self, database_path: Optional[Path] = None):
        self.database_path = Path(database_path or BASE_DIR / "data" / "paper_search" / "state.sqlite3")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL)")
            self._initialize_v1(connection)
            current = self._current_schema_version(connection)
            # C-1: v1 -> v2 migration runs in this single explicit transaction BEFORE the
            # version is bumped; it is idempotent and rolls back entirely on any failure.
            if (current or 1) < SCHEMA_VERSION:
                self._migrate_to_v2(connection)
            self._validate_schema_meta(connection)
            connection.commit()

    def _initialize_v1(self, connection: sqlite3.Connection) -> None:
        """Create/upgrade the v1 search-session schema (idempotent)."""
        connection.execute("""CREATE TABLE IF NOT EXISTS conference_sources(
            conference_id TEXT PRIMARY KEY, name TEXT NOT NULL, short_name TEXT NOT NULL,
            dblp_stream TEXT NOT NULL UNIQUE, venue_aliases TEXT NOT NULL, built_in INTEGER NOT NULL,
            enabled INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            discovery_routes TEXT NOT NULL DEFAULT '[]')""")
        connection.execute("""CREATE TABLE IF NOT EXISTS search_sessions(
            search_id TEXT PRIMARY KEY, query TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        connection.execute("""CREATE TABLE IF NOT EXISTS paper_candidates(
            candidate_id TEXT NOT NULL, search_id TEXT NOT NULL REFERENCES search_sessions(search_id) ON DELETE CASCADE,
            title TEXT NOT NULL, normalized_title TEXT NOT NULL, conference_id TEXT NOT NULL,
            conference_name TEXT NOT NULL, year INTEGER, authors TEXT NOT NULL, dblp_key TEXT, doi TEXT,
            abstract TEXT, article_url TEXT, pdf_url TEXT, pdf_access TEXT NOT NULL, retrieval_score REAL NOT NULL,
            rerank_score REAL, final_score REAL NOT NULL, rank INTEGER NOT NULL, existing_paper_id TEXT,
            initial_rank INTEGER NOT NULL DEFAULT 0, publication_stage TEXT NOT NULL DEFAULT 'published',
            source_kind TEXT NOT NULL DEFAULT 'dblp', source_page_url TEXT, arxiv_id TEXT,
            source_links TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY(search_id, candidate_id),
            UNIQUE(search_id, normalized_title, year, conference_id))""")
        self._migrate_global_candidate_key(connection)
        self._migrate_source_fields(connection)
        connection.execute("DROP INDEX IF EXISTS candidates_search_dblp_key")
        connection.execute("DROP INDEX IF EXISTS candidates_search_doi")
        self._normalize_persisted_titles(connection)
        connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS candidates_search_dblp_key
            ON paper_candidates(search_id, dblp_key) WHERE dblp_key IS NOT NULL""")
        connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS candidates_search_doi
            ON paper_candidates(search_id, doi) WHERE doi IS NOT NULL""")
        # A singleton expression index prevents accidental second metadata rows.
        # The check is best-effort here: a pre-existing multi-row schema_meta raises
        # IntegrityError which is intentionally surfaced by the subsequent row-count
        # check in _current_schema_version (rolled back by the caller's transaction).
        try:
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS schema_meta_singleton ON schema_meta((1))")
        except sqlite3.IntegrityError:
            pass
        self._seed(connection)

    @staticmethod
    def _current_schema_version(connection: sqlite3.Connection) -> Optional[int]:
        """Read the stored version, rejecting a structurally damaged/multi-row metadata.

        Mirrors the structural checks of ``_validate_schema_meta`` so that a corrupt
        ``schema_meta`` table is rejected here (and the transaction is rolled back)
        instead of being silently treated as a fresh database.  ``None`` means the
        metadata table exists but holds no row yet (a fresh database).
        """
        try:
            columns = connection.execute("PRAGMA table_info(schema_meta)").fetchall()
            if len(columns) != 1 or columns[0][1] != "version" or str(columns[0][2]).upper() != "INTEGER" or not columns[0][3]:
                raise RuntimeError("Invalid paper discovery schema metadata: malformed schema_meta table")
            rows = connection.execute("SELECT version, typeof(version) AS value_type FROM schema_meta").fetchall()
        except sqlite3.DatabaseError as error:
            raise RuntimeError("Invalid paper discovery schema metadata: malformed schema_meta table") from error
        if len(rows) > 1:
            raise RuntimeError("Invalid paper discovery schema metadata: expected exactly one row")
        if not rows:
            return None
        row = rows[0]
        if row[1] != "integer":
            raise RuntimeError(f"Unsupported or corrupt paper discovery schema version: {row[0]!r}")
        return int(row[0])

    @staticmethod
    def _migrate_to_v2(connection: sqlite3.Connection) -> None:
        """Create the seven catalog/search tables and bump schema_meta to 2.

        Runs inside the caller's explicit transaction so a failure rolls the whole
        migration back (C-1); every statement is ``IF NOT EXISTS`` for idempotency.
        New foreign keys use ON DELETE RESTRICT to preserve source evidence and
        frozen results (C-3); no CASCADE is added here.
        """
        connection.execute(
            """CREATE TABLE IF NOT EXISTS source_fetch_units(
                fetch_unit_id TEXT PRIMARY KEY,
                source_kind TEXT NOT NULL,
                conference_id TEXT NOT NULL,
                year INTEGER,
                unit_key TEXT NOT NULL,
                source_url TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN
                    ('pending','fetching','completed','partial','failed')),
                etag TEXT,
                last_modified TEXT,
                content_hash TEXT,
                paper_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                last_attempt_at TEXT,
                last_success_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_kind, conference_id, year, unit_key))""",
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS catalog_papers(
                catalog_paper_id TEXT PRIMARY KEY,
                conference_id TEXT NOT NULL,
                year INTEGER,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                authors_json TEXT NOT NULL DEFAULT '[]',
                abstract TEXT,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                doi TEXT,
                dblp_key TEXT,
                publication_stage TEXT NOT NULL DEFAULT 'published',
                official_page_url TEXT,
                official_pdf_url TEXT,
                prepublication_pdf_url TEXT,
                arxiv_id TEXT,
                metadata_hash TEXT NOT NULL,
                index_status TEXT NOT NULL DEFAULT 'pending' CHECK(index_status IN
                    ('pending','indexed','failed')),
                index_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)""",
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS catalog_source_records(
                source_record_id TEXT PRIMARY KEY,
                catalog_paper_id TEXT NOT NULL
                    REFERENCES catalog_papers(catalog_paper_id) ON DELETE RESTRICT,
                fetch_unit_id TEXT NOT NULL
                    REFERENCES source_fetch_units(fetch_unit_id) ON DELETE RESTRICT,
                source_kind TEXT NOT NULL,
                source_key TEXT NOT NULL,
                raw_metadata_json TEXT NOT NULL DEFAULT '{}',
                observed_at TEXT NOT NULL,
                UNIQUE(source_kind, source_key))""",
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS search_jobs(
                search_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                conference_ids_json TEXT NOT NULL DEFAULT '[]',
                years_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN
                    ('queued','running','completed','partial','failed')),
                graph_version TEXT,
                degraded INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                total_results INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)""",
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS search_source_progress(
                search_id TEXT NOT NULL
                    REFERENCES search_jobs(search_id) ON DELETE RESTRICT,
                source_kind TEXT NOT NULL CHECK(source_kind IN ('usenix','dblp')),
                status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN
                    ('queued','checking_cache','fetching','merging','completed','cached','failed')),
                cached_units_json TEXT NOT NULL DEFAULT '[]',
                fetching_units_json TEXT NOT NULL DEFAULT '[]',
                completed_units_json TEXT NOT NULL DEFAULT '[]',
                paper_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                message_code TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(search_id, source_kind))""",
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS search_events(
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id TEXT NOT NULL
                    REFERENCES search_jobs(search_id) ON DELETE RESTRICT,
                node_name TEXT NOT NULL,
                source_kind TEXT,
                event_type TEXT NOT NULL,
                status TEXT,
                safe_payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL)""",
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS search_results(
                search_id TEXT NOT NULL
                    REFERENCES search_jobs(search_id) ON DELETE RESTRICT,
                catalog_paper_id TEXT NOT NULL
                    REFERENCES catalog_papers(catalog_paper_id) ON DELETE RESTRICT,
                rank INTEGER NOT NULL,
                retrieval_score REAL NOT NULL DEFAULT 0,
                rerank_score REAL,
                final_score REAL NOT NULL DEFAULT 0,
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(search_id, catalog_paper_id),
                UNIQUE(search_id, rank))""",
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS catalog_papers_doi "
            "ON catalog_papers(doi) WHERE doi IS NOT NULL",
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS catalog_papers_identity "
            "ON catalog_papers(normalized_title, conference_id, year, authors_json)",
        )
        row = connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        if row is None:
            connection.execute("INSERT INTO schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
        else:
            connection.execute("UPDATE schema_meta SET version=?", (SCHEMA_VERSION,))

    @staticmethod
    def _validate_schema_meta(connection: sqlite3.Connection) -> None:
        try:
            columns = connection.execute("PRAGMA table_info(schema_meta)").fetchall()
            if len(columns) != 1 or columns[0][1] != "version" or str(columns[0][2]).upper() != "INTEGER" or not columns[0][3]:
                raise RuntimeError("Invalid paper discovery schema metadata: malformed schema_meta table")
            rows = connection.execute("SELECT version, typeof(version) AS value_type FROM schema_meta").fetchall()
        except sqlite3.DatabaseError as error:
            raise RuntimeError("Invalid paper discovery schema metadata: malformed schema_meta table") from error
        if len(rows) > 1:
            raise RuntimeError("Invalid paper discovery schema metadata: expected exactly one row")
        if not rows:
            connection.execute("INSERT INTO schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
            return
        row = rows[0]
        if row[1] != "integer" or row[0] != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported or corrupt paper discovery schema version: {row[0]!r}")

    @staticmethod
    def _migrate_source_fields(connection: sqlite3.Connection) -> None:
        """Add Task11 source metadata while retaining schema version 1."""
        tables = {
            "conference_sources": {"discovery_routes": "TEXT NOT NULL DEFAULT '[]'"},
            "paper_candidates": {
                "publication_stage": "TEXT NOT NULL DEFAULT 'published'",
                "source_kind": "TEXT NOT NULL DEFAULT 'dblp'",
                "source_page_url": "TEXT",
                "arxiv_id": "TEXT",
                "source_links": "TEXT NOT NULL DEFAULT '[]'",
            },
        }
        for table, fields in tables.items():
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for name, definition in fields.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _normalize_persisted_titles(connection: sqlite3.Connection) -> None:
        rows = connection.execute("SELECT search_id, candidate_id, title, normalized_title, doi FROM paper_candidates").fetchall()
        for row in rows:
            normalized = normalize_title(row[2])
            doi = normalize_doi(row[4]) or None
            if normalized != row[3] or doi != row[4]:
                connection.execute(
                    "UPDATE paper_candidates SET normalized_title=?, doi=? WHERE search_id=? AND candidate_id=?",
                    (normalized, doi, row[0], row[1]),
                )

    @staticmethod
    def _migrate_global_candidate_key(connection: sqlite3.Connection) -> None:
        """Upgrade the pre-task schema whose candidate_id was globally unique."""
        columns = connection.execute("PRAGMA table_info(paper_candidates)").fetchall()
        primary_keys = [row[1] for row in columns if row[5]]
        if primary_keys != ["candidate_id"]:
            return
        old_columns = {row[1] for row in columns}
        connection.execute("DROP INDEX IF EXISTS candidates_search_dblp_key")
        connection.execute("DROP INDEX IF EXISTS candidates_search_doi")
        connection.execute("ALTER TABLE paper_candidates RENAME TO paper_candidates_legacy")
        connection.execute("""CREATE TABLE paper_candidates(
              candidate_id TEXT NOT NULL, search_id TEXT NOT NULL REFERENCES search_sessions(search_id) ON DELETE CASCADE,
              title TEXT NOT NULL, normalized_title TEXT NOT NULL, conference_id TEXT NOT NULL,
              conference_name TEXT NOT NULL, year INTEGER, authors TEXT NOT NULL, dblp_key TEXT, doi TEXT,
              abstract TEXT, article_url TEXT, pdf_url TEXT, pdf_access TEXT NOT NULL, retrieval_score REAL NOT NULL,
              rerank_score REAL, final_score REAL NOT NULL, rank INTEGER NOT NULL, existing_paper_id TEXT,
              initial_rank INTEGER NOT NULL DEFAULT 0, publication_stage TEXT NOT NULL DEFAULT 'published',
              source_kind TEXT NOT NULL DEFAULT 'dblp', source_page_url TEXT, arxiv_id TEXT,
              source_links TEXT NOT NULL DEFAULT '[]',
              PRIMARY KEY(search_id, candidate_id),
              UNIQUE(search_id, normalized_title, year, conference_id))""")
        defaults = {
            "publication_stage": "'published'", "source_kind": "'dblp'",
            "source_page_url": "NULL", "arxiv_id": "NULL", "source_links": "'[]'",
        }
        select = [name if name in old_columns else defaults.get(name, "0") for name in (
            "candidate_id", "search_id", "title", "normalized_title", "conference_id", "conference_name",
            "year", "authors", "dblp_key", "doi", "abstract", "article_url", "pdf_url", "pdf_access",
            "retrieval_score", "rerank_score", "final_score", "rank", "existing_paper_id", "initial_rank",
            "publication_stage", "source_kind", "source_page_url", "arxiv_id", "source_links",
        )]
        connection.execute(
            "INSERT INTO paper_candidates (" + ",".join(
                ("initial_rank" if name == "initial_rank" else name) for name in (
                    "candidate_id", "search_id", "title", "normalized_title", "conference_id", "conference_name",
                    "year", "authors", "dblp_key", "doi", "abstract", "article_url", "pdf_url", "pdf_access",
                    "retrieval_score", "rerank_score", "final_score", "rank", "existing_paper_id", "initial_rank",
                    "publication_stage", "source_kind", "source_page_url", "arxiv_id", "source_links",
                )
            ) + ") SELECT " + ",".join(select) + " FROM paper_candidates_legacy"
        )
        connection.execute("DROP TABLE paper_candidates_legacy")

    @staticmethod
    def _seed(connection: sqlite3.Connection) -> None:
        now = _utcnow()
        connection.executemany(
            """INSERT INTO conference_sources VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(conference_id) DO NOTHING""",
            [
                (conference_id, name, short_name, stream, json.dumps(aliases), 1, 1, now, now,
                 json.dumps(USENIX_DISCOVERY_ROUTES if conference_id == "usenix-security" else []))
                for conference_id, name, short_name, stream, aliases in BUILT_IN_CONFERENCES
            ],
        )
        # Upgrade pre-Task11 databases without overwriting user-customized routes.
        connection.execute(
            """UPDATE conference_sources SET discovery_routes=?
               WHERE conference_id=? AND (discovery_routes IS NULL OR discovery_routes='[]')""",
            (json.dumps(USENIX_DISCOVERY_ROUTES), "usenix-security"),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def list_conferences(self) -> List[ConferenceSource]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM conference_sources ORDER BY built_in DESC, short_name").fetchall()
        return [
            ConferenceSource(
                row["conference_id"], row["name"], row["short_name"], row["dblp_stream"],
                json.loads(row["venue_aliases"]), bool(row["built_in"]), bool(row["enabled"]),
                row["created_at"], row["updated_at"], json.loads(row["discovery_routes"] or "[]"),
            )
            for row in rows
        ]

    def save_conference(self, source: ConferenceSource) -> None:
        now = _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO conference_sources VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(conference_id) DO UPDATE SET
                     name=excluded.name, short_name=excluded.short_name,
                     venue_aliases=excluded.venue_aliases, enabled=excluded.enabled,
                     discovery_routes=excluded.discovery_routes,
                     updated_at=excluded.updated_at""",
                (
                    source.conference_id, source.name, source.short_name, source.dblp_stream,
                    json.dumps(source.venue_aliases), int(source.built_in), int(source.enabled),
                    source.created_at or now, now, json.dumps(source.discovery_routes),
                ),
            )

    def save_search(self, session: SearchSession, candidates: Iterable[PaperCandidate]) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                "INSERT INTO search_sessions VALUES(?,?,?,?)",
                (session.search_id, session.query, session.expires_at, session.created_at or _utcnow()),
            )
            rows = []
            for item in candidates:
                normalized_title = normalize_title(item.title)
                # Keep the domain snapshot and the persisted snapshot identical.
                item.normalized_title = normalized_title
                item.doi = normalize_doi(item.doi) or None
                if item.pdf_access not in {"unknown", "public", "login_required", "unavailable"}:
                    item.pdf_access = "unknown"
                rows.append(
                    (
                        item.candidate_id, item.search_id, item.title, normalized_title, item.conference_id,
                        item.conference_name, item.year, json.dumps(item.authors), item.dblp_key, item.doi,
                        item.abstract, item.article_url, item.pdf_url, item.pdf_access, item.retrieval_score,
                        item.rerank_score, item.final_score, item.rank, item.existing_paper_id, item.initial_rank,
                        item.publication_stage, item.source_kind, item.source_page_url, item.arxiv_id,
                        json.dumps(item.source_links),
                    )
                )
            connection.executemany("INSERT INTO paper_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    @staticmethod
    def _candidate_from_row(row: sqlite3.Row) -> PaperCandidate:
        payload = {field: row[field] for field in PaperCandidate.__dataclass_fields__}
        payload["authors"] = json.loads(payload["authors"])
        payload["source_links"] = json.loads(payload["source_links"] or "[]")
        return PaperCandidate(**payload)

    def get_candidates(self, search_id: str) -> List[PaperCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_candidates WHERE search_id=? "
                "ORDER BY rank, initial_rank, year DESC, normalized_title, candidate_id",
                (search_id,),
            ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def get_search_session(self, search_id: str) -> Optional[SearchSession]:
        """Read one server-owned search session by its opaque identifier."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT search_id, query, expires_at, created_at FROM search_sessions WHERE search_id=?",
                (search_id,),
            ).fetchone()
        if row is None:
            return None
        return SearchSession(row["search_id"], row["query"], row["expires_at"], row["created_at"])

    def get_candidate(self, search_id: str, candidate_id: str) -> Optional[PaperCandidate]:
        """Read exactly one candidate from its search-session snapshot.

        The compound lookup is intentional: candidate IDs are scoped to a
        search session and must never be accepted as global client keys.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_candidates WHERE search_id=? AND candidate_id=?",
                (search_id, candidate_id),
            ).fetchone()
        return self._candidate_from_row(row) if row is not None else None

    def cleanup_expired_searches(self, now: Optional[str] = None) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN")
            # Task05 will add the import FK graph. Until then, if an import
            # table is present, retain any session containing a referenced
            # candidate; never make TTL cleanup the mechanism that erases an
            # imported paper's historical snapshot.
            import_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_import_items'"
            ).fetchone()
            if import_table:
                return connection.execute(
                    """DELETE FROM search_sessions AS s
                       WHERE s.expires_at <= ?
                         AND NOT EXISTS (
                           SELECT 1 FROM paper_candidates AS c
                           JOIN paper_import_items AS i ON i.candidate_id = c.candidate_id
                           WHERE c.search_id = s.search_id
                         )""",
                    (now or _utcnow(),),
                ).rowcount
            return connection.execute("DELETE FROM search_sessions WHERE expires_at <= ?", (now or _utcnow(),)).rowcount

    # --- schema v2: catalog / job / progress / event / result helpers ----------------------
    # These map the domain types to the seven new tables.  Concurrency, lease and frozen
    # paging behaviour belong to subtask C; here we only fix the persistence mapping.

    @staticmethod
    def _fetch_unit_from_row(row: sqlite3.Row) -> SourceFetchUnit:
        return SourceFetchUnit(
            row["fetch_unit_id"], row["source_kind"], row["conference_id"], row["year"], row["unit_key"],
            row["source_url"], row["status"], row["etag"], row["last_modified"], row["content_hash"],
            row["paper_count"], row["error_code"], row["lease_owner"], row["lease_expires_at"],
            row["last_attempt_at"], row["last_success_at"], row["created_at"], row["updated_at"],
        )

    @staticmethod
    def _catalog_paper_from_row(row: sqlite3.Row) -> CatalogPaper:
        return CatalogPaper(
            row["catalog_paper_id"], row["conference_id"], row["year"], row["title"], row["normalized_title"],
            json.loads(row["authors_json"] or "[]"), row["abstract"], json.loads(row["keywords_json"] or "[]"),
            row["doi"], row["dblp_key"], row["publication_stage"], row["official_page_url"], row["official_pdf_url"],
            row["prepublication_pdf_url"], row["arxiv_id"], row["metadata_hash"], row["index_status"],
            row["index_version"], row["created_at"], row["updated_at"],
        )

    def save_fetch_unit(self, unit: SourceFetchUnit, now: Optional[str] = None) -> None:
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO source_fetch_units
                     (fetch_unit_id, source_kind, conference_id, year, unit_key, source_url, status,
                      etag, last_modified, content_hash, paper_count, error_code, lease_owner,
                      lease_expires_at, last_attempt_at, last_success_at, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(fetch_unit_id) DO UPDATE SET
                     status=excluded.status, etag=excluded.etag, last_modified=excluded.last_modified,
                     content_hash=excluded.content_hash, paper_count=excluded.paper_count,
                     error_code=excluded.error_code, lease_owner=excluded.lease_owner,
                     lease_expires_at=excluded.lease_expires_at, last_attempt_at=excluded.last_attempt_at,
                     last_success_at=excluded.last_success_at, updated_at=excluded.updated_at""",
                (
                    unit.fetch_unit_id, unit.source_kind, unit.conference_id, unit.year, unit.unit_key,
                    unit.source_url, unit.status, unit.etag, unit.last_modified, unit.content_hash,
                    unit.paper_count, unit.error_code, unit.lease_owner, unit.lease_expires_at,
                    unit.last_attempt_at, unit.last_success_at, unit.created_at or now, now,
                ),
            )

    def get_fetch_unit(self, fetch_unit_id: str) -> Optional[SourceFetchUnit]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_fetch_units WHERE fetch_unit_id=?", (fetch_unit_id,)
            ).fetchone()
        return self._fetch_unit_from_row(row) if row is not None else None

    def upsert_catalog_paper(self, paper: CatalogPaper, now: Optional[str] = None) -> bool:
        """Insert or update a catalog paper keyed by catalog_paper_id.

        ``metadata_hash`` semantics (spec 293): when the hash is unchanged the
        ``updated_at`` timestamp is left untouched and indexing is not retried; when it
        changes the row is written and ``index_status`` is set to ``pending``.  Returns
        ``True`` when the hash changed (so the caller may schedule re-embedding).
          """
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            existing = connection.execute(
                "SELECT metadata_hash FROM catalog_papers WHERE catalog_paper_id=?",
                (paper.catalog_paper_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] == paper.metadata_hash:
                    return False
            changed = existing is None or existing[0] != paper.metadata_hash
            if existing is not None:
                connection.execute(
                    """UPDATE catalog_papers SET
                         conference_id=?, year=?, title=?, normalized_title=?, authors_json=?,
                         abstract=?, keywords_json=?, doi=?, dblp_key=?, publication_stage=?,
                         official_page_url=?, official_pdf_url=?, prepublication_pdf_url=?, arxiv_id=?,
                         metadata_hash=?, index_status=?, updated_at=?
                       WHERE catalog_paper_id=?""",
                    (
                        paper.conference_id, paper.year, paper.title, paper.normalized_title,
                        json.dumps(paper.authors), paper.abstract, json.dumps(paper.keywords), paper.doi,
                        paper.dblp_key, paper.publication_stage, paper.official_page_url,
                        paper.official_pdf_url, paper.prepublication_pdf_url,                         paper.arxiv_id,
                        paper.metadata_hash, "pending", now,
                        paper.catalog_paper_id,
                    ),
                )
                return changed
            connection.execute(
                """INSERT INTO catalog_papers
                     (catalog_paper_id, conference_id, year, title, normalized_title, authors_json,
                      abstract, keywords_json, doi, dblp_key, publication_stage, official_page_url,
                      official_pdf_url, prepublication_pdf_url, arxiv_id, metadata_hash,
                      index_status, index_version, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    paper.catalog_paper_id, paper.conference_id, paper.year, paper.title, paper.normalized_title,
                    json.dumps(paper.authors), paper.abstract, json.dumps(paper.keywords), paper.doi, paper.dblp_key,
                    paper.publication_stage, paper.official_page_url, paper.official_pdf_url,
                    paper.prepublication_pdf_url, paper.arxiv_id, paper.metadata_hash,
                    paper.index_status or "pending", paper.index_version, paper.created_at or now, now,
                ),
            )
            return True

    def get_catalog_paper(self, catalog_paper_id: str) -> Optional[CatalogPaper]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM catalog_papers WHERE catalog_paper_id=?", (catalog_paper_id,)
            ).fetchone()
        return self._catalog_paper_from_row(row) if row is not None else None

    def save_source_record(self, record: CatalogSourceRecord, now: Optional[str] = None) -> None:
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO catalog_source_records
                     (source_record_id, catalog_paper_id, fetch_unit_id, source_kind, source_key,
                      raw_metadata_json, observed_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(source_kind, source_key) DO UPDATE SET
                     catalog_paper_id=excluded.catalog_paper_id,
                     fetch_unit_id=excluded.fetch_unit_id,
                     raw_metadata_json=excluded.raw_metadata_json,
                     observed_at=excluded.observed_at""",
                (
                    record.source_record_id, record.catalog_paper_id, record.fetch_unit_id,
                    record.source_kind, record.source_key, json.dumps(record.raw_metadata),
                    record.observed_at or now,
                ),
            )

    def create_search_job(self, job: SearchJob, now: Optional[str] = None) -> None:
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO search_jobs
                     (search_id, query, conference_ids_json, years_json, status, graph_version,
                      degraded, error_code, total_results, created_at, started_at, completed_at,
                      expires_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(search_id) DO UPDATE SET
                     status=excluded.status, graph_version=excluded.graph_version,
                     degraded=excluded.degraded, error_code=excluded.error_code,
                     total_results=excluded.total_results, started_at=excluded.started_at,
                     completed_at=excluded.completed_at, expires_at=excluded.expires_at,
                     updated_at=excluded.updated_at""",
                (
                    job.search_id, job.query, json.dumps(job.conference_ids), json.dumps(job.years),
                    job.status, job.graph_version, int(job.degraded), job.error_code, job.total_results,
                    job.created_at or now, job.started_at, job.completed_at, job.expires_at, now,
                ),
            )

    def save_source_progress(self, progress: SearchSourceProgress, now: Optional[str] = None) -> None:
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO search_source_progress
                     (search_id, source_kind, status, cached_units_json, fetching_units_json,
                      completed_units_json, paper_count, error_code, message_code, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(search_id, source_kind) DO UPDATE SET
                     status=excluded.status, cached_units_json=excluded.cached_units_json,
                     fetching_units_json=excluded.fetching_units_json,
                     completed_units_json=excluded.completed_units_json,
                     paper_count=excluded.paper_count, error_code=excluded.error_code,
                     message_code=excluded.message_code, updated_at=excluded.updated_at""",
                (
                    progress.search_id, progress.source_kind, progress.status,
                    json.dumps(progress.cached_units), json.dumps(progress.fetching_units),
                    json.dumps(progress.completed_units), progress.paper_count, progress.error_code,
                    progress.message_code, progress.updated_at or now,
                ),
            )

    def append_search_event(self, event: SearchEvent, now: Optional[str] = None) -> int:
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            cursor = connection.execute(
                """INSERT INTO search_events
                     (search_id, node_name, source_kind, event_type, status, safe_payload_json,
                      created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    event.search_id, event.node_name, event.source_kind, event.event_type, event.status,
                    json.dumps(event.safe_payload), event.created_at or now,
                ),
            )
            return int(cursor.lastrowid)

    def save_search_result(self, result: SearchResult, now: Optional[str] = None) -> None:
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO search_results
                     (search_id, catalog_paper_id, rank, retrieval_score, rerank_score,
                      final_score, snapshot_json, created_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(search_id, catalog_paper_id) DO NOTHING""",
                (
                    result.search_id, result.catalog_paper_id, result.rank, result.retrieval_score,
                    result.rerank_score, result.final_score, json.dumps(result.snapshot),
                    result.created_at or now,
                ),
            )

    def get_search_results(self, search_id: str) -> List[SearchResult]:
        with self._connect() as connection:
            rows = connection.execute(
                  "SELECT * FROM search_results WHERE search_id=? ORDER BY rank", (search_id,)
             ).fetchall()
        results = []
        for row in rows:
            results.append(
                SearchResult(
                    row["search_id"], row["catalog_paper_id"], row["rank"], row["retrieval_score"],
                    row["rerank_score"], row["final_score"], json.loads(row["snapshot_json"] or "{}"),
                    row["created_at"],
                  )
             )
        return results

    @staticmethod
    def _search_result_from_row(row: sqlite3.Row) -> SearchResult:
        """Map one ``search_results`` row to the domain ``SearchResult`` type."""
        return SearchResult(
            row["search_id"], row["catalog_paper_id"], row["rank"], row["retrieval_score"],
            row["rerank_score"], row["final_score"], json.loads(row["snapshot_json"] or "{}"),
            row["created_at"],
        )

    # --- schema v2: atomic lease / frozen paging ----------------------------------------
    # The lease and frozen-result behaviour below is the subtask C increment.  It uses
    # only the single-statement, row-counted conditional UPDATE so that under WAL a given
    # fetch unit can never be claimed by two owners at once.  No import-batch CAS/lease
    # state machine is reused or copied (C-2/C-6): the search lease lives solely on the
    # dedicated ``source_fetch_units.lease_*`` columns.

    def acquire_fetch_unit(
        self,
        fetch_unit_id: str,
        owner: str,
        lease_seconds: int,
        now: Optional[str] = None,
    ) -> bool:
        """Atomically claim a fetch unit for ``owner`` via a single conditional UPDATE.

        The whole decision is one statement inside one transaction, so SQLite serializes
        concurrent writers (WAL + busy_timeout + the row lock).  The predicate
        ``lease_owner IS NULL OR lease_expires_at < now`` means an unclaimed unit is
        claimable and an *expired* lease can be re-claimed by any owner (lease recovery),
        while a still-valid lease rejects every other owner.  ``rowcount`` is the only
        success signal: >0 means this connection won the claim.  ISO-8601/RFC3339 UTC
        timestamps compare in lexicographic order, so the string comparison against
        ``lease_expires_at`` is equivalent to a time comparison.
        """
        now = now or _utcnow()
        expires_at = self._add_seconds(now, lease_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN")
            cursor = connection.execute(
                 """UPDATE source_fetch_units
                    SET lease_owner=?, lease_expires_at=?, status='fetching',
                        last_attempt_at=?, updated_at=?
                    WHERE fetch_unit_id=?
                      AND (lease_owner IS NULL OR lease_expires_at < ?)""",
                 (owner, expires_at, now, now, fetch_unit_id, now),
            )
            connection.commit()
            return cursor.rowcount > 0

    def renew_lease(
        self,
        fetch_unit_id: str,
        owner: str,
        lease_seconds: int,
        now: Optional[str] = None,
    ) -> bool:
        """Extend the lease only for the current owner who still holds a valid lease."""
        now = now or _utcnow()
        expires_at = self._add_seconds(now, lease_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN")
            cursor = connection.execute(
                 """UPDATE source_fetch_units
                    SET lease_expires_at=?, updated_at=?
                    WHERE fetch_unit_id=? AND lease_owner=? AND lease_expires_at >= ?""",
                 (expires_at, now, fetch_unit_id, owner, now),
            )
            connection.commit()
            return cursor.rowcount > 0

    def release_lease(
        self,
        fetch_unit_id: str,
        owner: str,
        status: str = "completed",
        now: Optional[str] = None,
    ) -> bool:
        """Release the lease back to ``pending`` only for the owner that holds it."""
        now = now or _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN")
            cursor = connection.execute(
                 """UPDATE source_fetch_units
                    SET lease_owner=NULL, lease_expires_at=NULL, status=?,
                        last_success_at=?, updated_at=?
                    WHERE fetch_unit_id=? AND lease_owner=?""",
                 (status, now, now, fetch_unit_id, owner),
            )
            connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _add_seconds(rfc3339_utc: str, seconds: int) -> str:
        """Return ``rfc3339_utc`` advanced by ``seconds`` in the same RFC3339 ``Z`` form."""
        parsed = datetime.fromisoformat(rfc3339_utc.replace("Z", "+00:00"))
        shifted = parsed + timedelta(seconds=seconds)
        return shifted.isoformat(timespec="seconds").replace("+00:00", "Z")

    def get_search_results_page(
        self,
        search_id: str,
        page: int,
        page_size: int = 10,
    ) -> List[SearchResult]:
        """Read a fixed page of frozen results ordered by ``rank``.

        Paging is by rank only (``ORDER BY rank`` fixed by spec 291/293), so repeated
        reads are stable: the same 10/10/1 split for a 21-row result set, and reading
        the same page twice yields the identical list.  ``page`` is 1-based.
        """
        page = max(int(page), 1)
        page_size = max(int(page_size), 1)
        offset = (page - 1) * page_size
        with self._connect() as connection:
            rows = connection.execute(
                 "SELECT * FROM search_results WHERE search_id=? "
                 "ORDER BY rank LIMIT ? OFFSET ?",
                 (search_id, page_size, offset),
            ).fetchall()
        return [self._search_result_from_row(row) for row in rows]
