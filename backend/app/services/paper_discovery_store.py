"""SQLite persistence for conference search sessions and paper candidates."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from backend.app.core.config import BASE_DIR
from backend.app.domain.paper_discovery import ConferenceSource, PaperCandidate, SearchSession
from backend.app.services.paper_discovery_normalization import normalize_doi, normalize_title


SCHEMA_VERSION = 1
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
            self._validate_schema_meta(connection)
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
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS schema_meta_singleton ON schema_meta((1))")
            self._seed(connection)
            connection.commit()

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
