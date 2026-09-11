"""SQLite persistence for projects, conversations and project memory.

This database is deliberately independent from paper, article and knowledge-base
stores.  A repository opens short-lived connections so streaming requests do not
hold a connection/transaction while waiting for a model.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from backend.app.platform.config import BASE_DIR, MEMORY_ANALYSIS_MODEL
from .models import (
    Conversation,
    ConversationSummary,
    EvolutionCheckpoint,
    MemoryEvidence,
    MemoryAnalysisItem,
    MemoryAnalysisJob,
    MemoryRecord,
    Message,
    ProcessingStep,
    Project,
    RawEvent,
    SkillImprovementProposal,
    SystemRule,
)

SCHEMA_VERSION = 6
EVOLUTION_LEASE_SECONDS = 300
OWNER_ID = os.getenv("MEMORY_OWNER_ID", "local-user")
_write_lock = threading.RLock()

MEMORY_SCOPES = {"global", "project"}
MEMORY_CATEGORIES = {"user_preference", "stable_fact", "project_rule", "capability_method"}
MEMORY_SOURCE_KINDS = {"explicit", "repeated", "verified_failure", "manual"}
MEMORY_STATUSES = {"candidate", "active", "superseded", "disabled", "deleted"}
MEMORY_HISTORY_POLICIES = {"from_binding", "include_prior_history"}
ANALYSIS_STATUSES = {"pending", "running", "completed", "partial", "failed"}
ANALYSIS_DECISIONS = {"auto_saved", "pending_confirmation", "duplicate", "superseded", "ignored", "failed"}
SKILL_PROPOSAL_STATUSES = {"proposed", "accepted", "rejected", "applied"}


class LeaseLostError(RuntimeError):
    """Raised when a stale analysis worker attempts a durable write."""


class SystemRuleUnavailableError(RuntimeError):
    """Raised when the rule state cannot be determined safely."""


def default_database_path() -> Path:
    configured = os.getenv("MEMORY_DB_PATH", "").strip()
    return Path(configured) if configured else BASE_DIR / "data" / "memory" / "memory.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def encode_cursor(kind: str, created_at: str, item_id: str) -> str:
    raw = json.dumps({"v": 1, "kind": kind, "at": created_at, "id": item_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, kind: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        if value.get("v") != 1 or value.get("kind") != kind or not value.get("at") or not value.get("id"):
            raise ValueError
        return str(value["at"]), str(value["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("invalid cursor")


class MemoryRepository:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.initialize()

    def connection(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.database_path), timeout=5.0, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connection()
        try:
            with _write_lock:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.execute("COMMIT")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        connection = self.connection()
        try:
            with _write_lock:
                # DDL is deliberately executed one statement at a time.  The
                # old implementation used executescript(), which implicitly
                # committed and could leave a half-applied migration.
                connection.execute("BEGIN IMMEDIATE")
                self._create_schema_v1(connection)
                current_row = connection.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
                current = int(current_row["version"] or 0)
                if current > SCHEMA_VERSION:
                    raise RuntimeError(f"unsupported memory schema version: {current}")
                if current < 1:
                    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (1, _now()))
                    current = 1
                if current < 2:
                    self._migrate_v1_to_v2(connection)
                    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (2, _now()))
                    current = 2
                elif not self._is_schema_v2(connection):
                    # Repair the first Task03 draft, which marked version 2
                    # without applying its structural migration.
                    self._migrate_v1_to_v2(connection)
                if current < 3:
                    self._migrate_v2_to_v3(connection)
                    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (3, _now()))
                    current = 3
                elif not self._is_schema_v3(connection):
                    raise RuntimeError("incomplete memory schema v3")
                if current < 4:
                    self._migrate_v3_to_v4(connection)
                    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (4, _now()))
                    current = 4
                elif not self._is_schema_v4(connection):
                    raise RuntimeError("incomplete memory schema v4")
                if current < 5:
                    self._migrate_v4_to_v5(connection)
                    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (5, _now()))
                    current = 5
                elif not self._is_schema_v5(connection):
                    raise RuntimeError("incomplete memory schema v5")
                if not self._is_schema_v5(connection):
                    raise RuntimeError("memory schema v5 validation failed")
                if current < 6:
                    self._migrate_v5_to_v6(connection)
                    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (6, _now()))
                    current = 6
                elif not self._is_schema_v6(connection):
                    # v6 was briefly shipped with a nullable SQLite PRIMARY
                    # KEY declaration. Repair only that exact legacy shape;
                    # all other structural corruption remains fail-closed.
                    if self._is_legacy_v6_shape(connection):
                        self._repair_legacy_v6(connection)
                    else:
                        raise RuntimeError("incomplete memory schema v6")
                if not self._is_schema_v6(connection):
                    raise RuntimeError("memory schema v6 validation failed")
                # Task07 is an additive repository extension. Keep the public
                # v6 number for Task10 compatibility while applying the table
                # atomically to fresh and existing v6 databases.
                task07_table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_improvement_proposals'"
                ).fetchone()
                if not task07_table:
                    self._migrate_v6_to_task07(connection)
                elif not self._is_task07_schema(connection):
                    raise RuntimeError("incomplete Task07 proposal schema")
                if not self._is_task07_schema(connection):
                    raise RuntimeError("Task07 proposal schema validation failed")
                connection.execute("COMMIT")
        except Exception as error:
            connection.rollback()
            raise SystemRuleUnavailableError("memory schema migration failed; startup is fail-closed") from error
        finally:
            connection.close()

    @staticmethod
    def _create_schema_v1(connection: sqlite3.Connection) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                name TEXT NOT NULL, instructions TEXT, status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(owner_id, name)
            )""",
            """CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
                memory_history_policy TEXT NOT NULL DEFAULT 'from_binding',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated ON conversations(owner_id, updated_at DESC, conversation_id DESC)",
            """CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                owner_id TEXT NOT NULL, parent_message_id TEXT, role TEXT NOT NULL,
                content TEXT NOT NULL, status TEXT NOT NULL, model TEXT, mode TEXT,
                created_at TEXT NOT NULL, completed_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at DESC, message_id DESC)",
            """CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, scope TEXT NOT NULL,
                project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                category TEXT NOT NULL, statement TEXT NOT NULL, source_kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', confidence REAL NOT NULL,
                supersedes_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                last_used_at TEXT,
                CHECK ((scope='project' AND project_id IS NOT NULL) OR (scope='global' AND project_id IS NULL))
            )""",
            "CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(owner_id, project_id, status)",
            """CREATE TABLE IF NOT EXISTS memory_evidence (
                memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
                conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL,
                message_id TEXT, evidence_type TEXT NOT NULL, excerpt TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS processing_steps (
                step_id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
                kind TEXT NOT NULL, logical_sequence INTEGER NOT NULL DEFAULT 0, label TEXT NOT NULL, status TEXT NOT NULL,
                summary TEXT, started_at TEXT NOT NULL, completed_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_steps_message ON processing_steps(message_id, started_at)",
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()}
        if "memory_binding_at" not in columns:
            connection.execute("ALTER TABLE conversations ADD COLUMN memory_binding_at TEXT")
        if "memory_binding_message_id" not in columns:
            connection.execute("ALTER TABLE conversations ADD COLUMN memory_binding_message_id TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope_status ON memories(owner_id, scope, status, updated_at DESC, memory_id DESC)")
        # Version 2 also makes global evidence safe across project deletion.
        connection.execute("ALTER TABLE memory_evidence RENAME TO memory_evidence_legacy")
        connection.execute("""CREATE TABLE memory_evidence (
            memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
            conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL,
            message_id TEXT REFERENCES messages(message_id) ON DELETE SET NULL,
            evidence_type TEXT NOT NULL, excerpt TEXT
        )""")
        connection.execute("""INSERT INTO memory_evidence(memory_id, conversation_id, message_id, evidence_type, excerpt)
            SELECT e.memory_id, e.conversation_id,
                   CASE WHEN e.message_id IS NOT NULL AND EXISTS (SELECT 1 FROM messages m WHERE m.message_id=e.message_id) THEN e.message_id ELSE NULL END,
                   e.evidence_type, e.excerpt
            FROM memory_evidence_legacy e""")
        connection.execute("DROP TABLE memory_evidence_legacy")

    @staticmethod
    def _is_schema_v2(connection: sqlite3.Connection) -> bool:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()}
        if not {"memory_binding_at", "memory_binding_message_id"} <= columns:
            return False
        return any(row["table"] == "messages" and row["on_delete"] == "SET NULL" for row in connection.execute("PRAGMA foreign_key_list(memory_evidence)").fetchall())

    @staticmethod
    def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
        connection.execute("""CREATE TABLE IF NOT EXISTS raw_events (
            event_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            message_id TEXT REFERENCES messages(message_id) ON DELETE SET NULL,
            event_kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(owner_id, conversation_id, idempotency_key)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_events_session ON raw_events(owner_id, conversation_id, created_at, event_id)")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversation_summaries (
            summary_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            summary_text TEXT NOT NULL,
            source_event_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, conversation_id)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_summaries_scope ON conversation_summaries(owner_id, conversation_id, status, updated_at DESC)")
        connection.execute("""CREATE TABLE IF NOT EXISTS evolution_checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            cursor TEXT,
            batch_index INTEGER NOT NULL DEFAULT 0,
            total_batches INTEGER NOT NULL DEFAULT 0,
            state_json TEXT NOT NULL DEFAULT '{}',
            attempts INTEGER NOT NULL DEFAULT 0,
            idempotency_key TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, conversation_id, stage)
        )""")

    @staticmethod
    def _is_schema_v3(connection: sqlite3.Connection) -> bool:
        required = {
            "raw_events": {"event_id", "owner_id", "conversation_id", "message_id", "event_kind", "payload", "idempotency_key", "created_at"},
            "conversation_summaries": {"summary_id", "owner_id", "conversation_id", "summary_text", "source_event_id", "status", "created_at", "updated_at"},
            "evolution_checkpoints": {"checkpoint_id", "owner_id", "conversation_id", "stage", "status", "cursor", "batch_index", "total_batches", "state_json", "attempts", "idempotency_key", "error", "created_at", "updated_at"},
        }
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(required) <= tables:
            return False
        for table, columns in required.items():
            actual = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not columns <= actual:
                return False
        expected_fks = {
            "raw_events": {("conversations", "CASCADE"), ("messages", "SET NULL")},
            "conversation_summaries": {("conversations", "CASCADE")},
            "evolution_checkpoints": {("conversations", "CASCADE")},
        }
        for table, expected in expected_fks.items():
            fks = {(row["table"], row["on_delete"]) for row in connection.execute(f"PRAGMA foreign_key_list({table})")}
            if not expected <= fks:
                return False
        expected_unique = {
            "raw_events": {"owner_id", "conversation_id", "idempotency_key"},
            "conversation_summaries": {"owner_id", "conversation_id"},
            "evolution_checkpoints": {"owner_id", "conversation_id", "stage"},
        }
        for table, columns in expected_unique.items():
            found = False
            for index in connection.execute(f"PRAGMA index_list({table})"):
                if not index["unique"]:
                    continue
                index_columns = {row["name"] for row in connection.execute(f"PRAGMA index_info({index['name']})")}
                if columns <= index_columns:
                    found = True
                    break
            if not found:
                return False
        expected_indexes = {
            "idx_raw_events_session": "raw_events",
            "idx_summaries_scope": "conversation_summaries",
        }
        for index, table in expected_indexes.items():
            row = connection.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=? AND tbl_name=?", (index, table)).fetchone()
            if not row:
                return False
        return True

    @staticmethod
    def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
        """Add stable processing-step identity and durable message analysis."""
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(processing_steps)").fetchall()}
        if "logical_sequence" not in columns:
            connection.execute("ALTER TABLE processing_steps ADD COLUMN logical_sequence INTEGER NOT NULL DEFAULT 0")
        # Older repair-round databases may contain the two rows produced by
        # the former running/terminal implementation.  Keep the earliest row
        # and let the state machine update it in place.
        connection.execute("""DELETE FROM processing_steps
            WHERE status='running' AND EXISTS (
                SELECT 1 FROM processing_steps terminal
                WHERE terminal.message_id=processing_steps.message_id
                  AND terminal.kind=processing_steps.kind
                  AND terminal.logical_sequence=processing_steps.logical_sequence
                  AND terminal.status!='running'
            )""")
        connection.execute("""DELETE FROM processing_steps
            WHERE rowid NOT IN (
                SELECT MIN(rowid) FROM processing_steps
                GROUP BY message_id, kind, logical_sequence
            )""")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_steps_message_kind_sequence ON processing_steps(message_id, kind, logical_sequence)")
        connection.execute("""CREATE TABLE IF NOT EXISTS memory_analysis_jobs (
            analysis_id TEXT PRIMARY KEY,
            user_message_id TEXT NOT NULL UNIQUE REFERENCES messages(message_id) ON DELETE CASCADE,
            owner_id TEXT NOT NULL,
            project_id_snapshot TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            model TEXT,
            cursor TEXT,
            batch_no INTEGER NOT NULL DEFAULT 0,
            saved_count INTEGER NOT NULL DEFAULT 0,
            pending_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            lease_token TEXT,
            lease_version INTEGER NOT NULL DEFAULT 0
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_analysis_jobs_work ON memory_analysis_jobs(owner_id, status, updated_at)")
        connection.execute("""CREATE TABLE IF NOT EXISTS memory_analysis_items (
            item_id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL REFERENCES memory_analysis_jobs(analysis_id) ON DELETE CASCADE,
            statement TEXT NOT NULL,
            suggested_scope TEXT NOT NULL,
            confidence REAL NOT NULL,
            rationale_summary TEXT,
            decision_status TEXT NOT NULL,
            memory_id TEXT REFERENCES memories(memory_id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            UNIQUE(analysis_id, statement)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_analysis_items_page ON memory_analysis_items(analysis_id, created_at, item_id)")

    @staticmethod
    def _is_schema_v4(connection: sqlite3.Connection) -> bool:
        step_columns = {row["name"] for row in connection.execute("PRAGMA table_info(processing_steps)").fetchall()}
        if "logical_sequence" not in step_columns:
            return False
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"memory_analysis_jobs", "memory_analysis_items"} <= tables:
            return False
        for table, required in {
            "memory_analysis_jobs": {"analysis_id", "user_message_id", "owner_id", "project_id_snapshot", "status", "model", "cursor", "batch_no", "saved_count", "pending_count", "failed_count", "error_code", "created_at", "updated_at", "completed_at"},
            "memory_analysis_items": {"item_id", "analysis_id", "statement", "suggested_scope", "confidence", "rationale_summary", "decision_status", "memory_id", "created_at", "decided_at"},
        }.items():
            if not required <= {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}: return False
        indexes = {row["name"] for row in connection.execute("PRAGMA index_list(processing_steps)") if row["unique"]}
        if "uq_steps_message_kind_sequence" not in indexes:
            return False
        return True

    @staticmethod
    def _migrate_v4_to_v5(connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(memory_analysis_jobs)").fetchall()}
        if "lease_token" not in columns:
            connection.execute("ALTER TABLE memory_analysis_jobs ADD COLUMN lease_token TEXT")
        if "lease_version" not in columns:
            connection.execute("ALTER TABLE memory_analysis_jobs ADD COLUMN lease_version INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _is_schema_v5(connection: sqlite3.Connection) -> bool:
        if not MemoryRepository._is_schema_v4(connection):
            return False
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(memory_analysis_jobs)").fetchall()}
        return {"lease_token", "lease_version"} <= columns

    @staticmethod
    def _migrate_v5_to_v6(connection: sqlite3.Connection) -> None:
        connection.execute("""CREATE TABLE IF NOT EXISTS system_rules (
            owner_id TEXT NOT NULL PRIMARY KEY,
            content TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
            updated_at TEXT NOT NULL
        )""")

    @staticmethod
    def _is_schema_v6(connection: sqlite3.Connection) -> bool:
        rows = connection.execute("PRAGMA table_info(system_rules)").fetchall()
        if {row["name"] for row in rows} != {"owner_id", "content", "enabled", "updated_at"}:
            return False
        by_name = {row["name"]: row for row in rows}
        owner = by_name.get("owner_id")
        content = by_name.get("content")
        enabled = by_name.get("enabled")
        updated = by_name.get("updated_at")
        definition = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='system_rules'").fetchone()
        sql = (definition["sql"] if definition else "").upper().replace(" ", "").replace("\n", "")
        def default(row, expected: str) -> bool:
            value = str(row["dflt_value"] or "").strip().upper().replace(" ", "")
            return value in {expected, f"'{expected}'", f'"{expected}"'}
        return bool(
            owner and owner["type"].upper() == "TEXT" and owner["notnull"] == 1 and owner["pk"] == 1
            and content and content["type"].upper() == "TEXT" and content["notnull"] == 1 and default(content, "''")
            and enabled and enabled["type"].upper() == "INTEGER" and enabled["notnull"] == 1 and default(enabled, "0")
            and updated and updated["type"].upper() == "TEXT" and updated["notnull"] == 1
            and "CHECK(ENABLEDIN(0,1))" in sql
        )

    @staticmethod
    def _migrate_v6_to_task07(connection: sqlite3.Connection) -> None:
        connection.execute("""CREATE TABLE skill_improvement_proposals (
            proposal_id TEXT NOT NULL PRIMARY KEY,
            owner_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
            target_file TEXT NOT NULL,
            problem_evidence TEXT NOT NULL,
            diff_summary TEXT NOT NULL,
            verification_plan TEXT NOT NULL,
            risk_summary TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            protected_hash_before TEXT NOT NULL DEFAULT '{}',
            protected_hash_after TEXT NOT NULL DEFAULT '{}',
            source_memory_id TEXT REFERENCES memories(memory_id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT,
            CHECK (scope IN ('global', 'project')),
            CHECK ((scope='project' AND project_id IS NOT NULL) OR (scope='global' AND project_id IS NULL)),
            CHECK (status IN ('proposed', 'accepted', 'rejected', 'applied'))
        )""")
        connection.execute("CREATE INDEX idx_skill_proposals_scope ON skill_improvement_proposals(owner_id, scope, project_id, status, updated_at DESC, proposal_id DESC)")
        connection.execute("CREATE INDEX idx_skill_proposals_source ON skill_improvement_proposals(owner_id, source_memory_id)")

    @staticmethod
    def _is_task07_schema(connection: sqlite3.Connection) -> bool:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_improvement_proposals'"
        ).fetchone()
        if not table:
            return False
        expected_columns = [
            ("proposal_id", "TEXT", 1, None, 1),
            ("owner_id", "TEXT", 1, None, 0),
            ("scope", "TEXT", 1, None, 0),
            ("project_id", "TEXT", 0, None, 0),
            ("target_file", "TEXT", 1, None, 0),
            ("problem_evidence", "TEXT", 1, None, 0),
            ("diff_summary", "TEXT", 1, None, 0),
            ("verification_plan", "TEXT", 1, None, 0),
            ("risk_summary", "TEXT", 1, None, 0),
            ("status", "TEXT", 1, "'proposed'", 0),
            ("protected_hash_before", "TEXT", 1, "'{}'", 0),
            ("protected_hash_after", "TEXT", 1, "'{}'", 0),
            ("source_memory_id", "TEXT", 0, None, 0),
            ("created_at", "TEXT", 1, None, 0),
            ("updated_at", "TEXT", 1, None, 0),
            ("decided_at", "TEXT", 0, None, 0),
        ]
        columns = connection.execute("PRAGMA table_info(skill_improvement_proposals)").fetchall()
        actual = [
            (row["name"], str(row["type"]).upper(), int(row["notnull"]), row["dflt_value"], int(row["pk"]))
            for row in columns
        ]
        if actual != expected_columns:
            return False
        sql_row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='skill_improvement_proposals'").fetchone()
        sql = str(sql_row["sql"] if sql_row else "").upper().replace(" ", "").replace("\n", "")
        required_checks = (
            "CHECK(SCOPEIN('GLOBAL','PROJECT'))",
            "CHECK((SCOPE='PROJECT'ANDPROJECT_IDISNOTNULL)OR(SCOPE='GLOBAL'ANDPROJECT_IDISNULL))",
            "CHECK(STATUSIN('PROPOSED','ACCEPTED','REJECTED','APPLIED'))",
        )
        if not all(check in sql for check in required_checks):
            return False
        fks = {(row["from"], row["table"], row["on_delete"]) for row in connection.execute("PRAGMA foreign_key_list(skill_improvement_proposals)").fetchall()}
        if fks != {
            ("project_id", "projects", "CASCADE"),
            ("source_memory_id", "memories", "SET NULL"),
        }:
            return False
        indexes = {row["name"]: row for row in connection.execute("PRAGMA index_list(skill_improvement_proposals)").fetchall()}
        scope_index = indexes.get("idx_skill_proposals_scope")
        source_index = indexes.get("idx_skill_proposals_source")
        if not scope_index or not source_index or scope_index["unique"] or source_index["unique"]:
            return False
        def index_columns(name: str) -> list[str]:
            return [row["name"] for row in connection.execute(f"PRAGMA index_info({name})").fetchall()]
        if index_columns("idx_skill_proposals_scope") != ["owner_id", "scope", "project_id", "status", "updated_at", "proposal_id"]:
            return False
        if index_columns("idx_skill_proposals_source") != ["owner_id", "source_memory_id"]:
            return False
        primary = [row for row in connection.execute("PRAGMA index_list(skill_improvement_proposals)").fetchall() if row["unique"] and row["origin"] == "pk"]
        return len(primary) == 1 and index_columns(primary[0]["name"]) == ["proposal_id"]

    @staticmethod
    def _is_legacy_v6_shape(connection: sqlite3.Connection) -> bool:
        rows = connection.execute("PRAGMA table_info(system_rules)").fetchall()
        if {row["name"] for row in rows} != {"owner_id", "content", "enabled", "updated_at"}:
            return False
        by_name = {row["name"]: row for row in rows}
        sql_row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='system_rules'").fetchone()
        sql = (sql_row["sql"] if sql_row else "").upper().replace(" ", "").replace("\n", "")
        return bool(
            by_name["owner_id"]["type"].upper() == "TEXT" and by_name["owner_id"]["pk"] == 1
            and by_name["owner_id"]["notnull"] == 0
            and by_name["content"]["type"].upper() == "TEXT" and by_name["content"]["notnull"] == 1 and str(by_name["content"]["dflt_value"]).replace(" ", "") == "''"
            and by_name["enabled"]["type"].upper() == "INTEGER" and by_name["enabled"]["notnull"] == 1 and str(by_name["enabled"]["dflt_value"]).replace(" ", "") == "0"
            and by_name["updated_at"]["type"].upper() == "TEXT" and by_name["updated_at"]["notnull"] == 1
            and "CHECK(ENABLEDIN(0,1))" in sql
        )

    @staticmethod
    def _repair_legacy_v6(connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE system_rules RENAME TO system_rules_legacy")
        MemoryRepository._migrate_v5_to_v6(connection)
        connection.execute("INSERT INTO system_rules(owner_id, content, enabled, updated_at) SELECT owner_id, content, enabled, updated_at FROM system_rules_legacy")
        connection.execute("DROP TABLE system_rules_legacy")

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        columns = row.keys()
        last_activity_at = row["last_activity_at"] if "last_activity_at" in columns else row["updated_at"]
        return Project(
            row["project_id"], row["owner_id"], row["name"], row["instructions"], row["status"],
            _dt(row["created_at"]), _dt(row["updated_at"]), _dt(last_activity_at),
        )

    @staticmethod
    def _conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(row["conversation_id"], row["owner_id"], row["project_id"], row["title"], row["status"], row["memory_history_policy"], _dt(row["created_at"]), _dt(row["updated_at"]), _dt(row["memory_binding_at"]), row["memory_binding_message_id"])

    @staticmethod
    def _message(row: sqlite3.Row) -> Message:
        return Message(row["message_id"], row["conversation_id"], row["owner_id"], row["parent_message_id"], row["role"], row["content"], row["status"], row["model"], row["mode"], _dt(row["created_at"]), _dt(row["completed_at"]))

    @staticmethod
    def _memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(row["memory_id"], row["owner_id"], row["scope"], row["project_id"], row["category"], row["statement"], row["source_kind"], row["status"], float(row["confidence"]), row["supersedes_id"], _dt(row["created_at"]), _dt(row["updated_at"]), _dt(row["last_used_at"]))

    @staticmethod
    def _proposal(row: sqlite3.Row) -> SkillImprovementProposal:
        def hashes(value: Optional[str]) -> dict:
            try:
                parsed = json.loads(value or "{}")
            except (TypeError, json.JSONDecodeError):
                parsed = {}
            return parsed if isinstance(parsed, dict) else {}

        return SkillImprovementProposal(
            row["proposal_id"], row["owner_id"], row["scope"], row["project_id"],
            row["target_file"], row["problem_evidence"], row["diff_summary"],
            row["verification_plan"], row["risk_summary"], row["status"],
            hashes(row["protected_hash_before"]), hashes(row["protected_hash_after"]),
            row["source_memory_id"], _dt(row["created_at"]), _dt(row["updated_at"]),
            _dt(row["decided_at"]),
        )

    @staticmethod
    def _canonical_hashes(value: Optional[dict]) -> dict:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("protected hashes must be an object")
        normalized = {}
        for path, digest in value.items():
            if not isinstance(path, str) or not path or "\x00" in path:
                raise ValueError("invalid protected hash path")
            if not isinstance(digest, str) or not digest or "\x00" in digest:
                raise ValueError("invalid protected hash value")
            normalized[path] = digest
        return dict(sorted(normalized.items()))

    @staticmethod
    def _validate_capability_evidence(evidence: object) -> tuple[Optional[str], Optional[str], str, Optional[str]]:
        if not isinstance(evidence, (tuple, list)) or len(evidence) != 4:
            raise ValueError("capability method requires complete evidence")
        conversation_id, message_id, evidence_type, excerpt = evidence
        if not conversation_id and not message_id:
            raise ValueError("capability method evidence needs a source reference")
        if evidence_type not in {"user_statement", "repeated_sessions", "tool_failure", "manual"}:
            raise ValueError("invalid capability method evidence type")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError("capability method evidence needs an excerpt")
        return conversation_id, message_id, evidence_type, excerpt

    def create_capability_method(
        self,
        owner_id: str,
        *,
        scope: str,
        project_id: Optional[str],
        statement: str,
        source_kind: str,
        confidence: float,
        status: str = "active",
        evidence: Optional[tuple[Optional[str], Optional[str], str, Optional[str]]] = None,
        supersedes_id: Optional[str] = None,
    ) -> MemoryRecord:
        """Create one evidence-backed, scoped capability method card."""
        if source_kind not in {"explicit", "repeated", "verified_failure", "manual"}:
            raise ValueError("invalid capability method source")
        evidence_value = self._validate_capability_evidence(evidence)
        if scope not in MEMORY_SCOPES:
            raise ValueError("invalid memory scope")
        if scope == "project":
            if not project_id or not self.get_project(project_id, owner_id):
                raise LookupError("project not found")
        elif project_id is not None:
            raise ValueError("global method cannot have a project")
        if status not in MEMORY_STATUSES:
            raise ValueError("invalid memory status")
        statement_clean = str(statement).strip() if isinstance(statement, str) else ""
        confidence_value = float(confidence)
        if not statement_clean or len(statement_clean) > 1000 or not 0 <= confidence_value <= 1:
            raise ValueError("invalid capability method")
        if supersedes_id:
            previous = self.get_memory(supersedes_id, owner_id)
            if not previous or previous.scope != scope or previous.project_id != project_id:
                raise ValueError("invalid superseded memory")
        normalized = " ".join(statement_clean.split()).casefold()
        with self.transaction() as db:
            scope_sql = "project_id IS NULL" if project_id is None else "project_id=?"
            scope_params: tuple[object, ...] = (owner_id, scope, project_id) if project_id is not None else (owner_id, scope)
            existing_rows = db.execute(
                f"SELECT * FROM memories WHERE owner_id=? AND scope=? AND {scope_sql} AND category='capability_method' AND status IN ('active', 'candidate')",
                scope_params,
            ).fetchall()
            for row in existing_rows:
                if " ".join(row["statement"].split()).casefold() == normalized:
                    return self._memory(row)
            now, memory_id = _now(), uuid.uuid4().hex
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (memory_id, owner_id, scope, project_id, "capability_method", statement_clean, source_kind, status, confidence_value, supersedes_id, now, now, None),
            )
            self._insert_memory_evidence(db, memory_id, owner_id, evidence_value[0], evidence_value[1], evidence_value[2], evidence_value[3])
        return self.get_memory(memory_id, owner_id)

    def list_capability_methods(
        self,
        owner_id: str,
        project_id: Optional[str],
        *,
        query: str = "",
        budget_chars: int = 2000,
        limit: int = 5,
        include_candidates: bool = False,
    ) -> list[MemoryRecord]:
        """Recall a small owner/scope-isolated set of method cards."""
        statuses = {"active", "candidate"} if include_candidates else {"active"}
        params: list[object] = [owner_id, "capability_method"]
        placeholders = ",".join("?" for _ in statuses)
        params.extend(sorted(statuses))
        scope_clause = "(scope='global'"
        if project_id:
            scope_clause += " OR (scope='project' AND project_id=?)"
            params.append(project_id)
        scope_clause += ")"
        with self.connection() as db:
            rows = db.execute(
                f"SELECT * FROM memories WHERE owner_id=? AND category=? AND status IN ({placeholders}) AND {scope_clause} ORDER BY confidence DESC, updated_at DESC, memory_id DESC LIMIT 100",
                params,
            ).fetchall()
        terms = {part.casefold() for part in (query or "").split() if len(part.strip()) > 1}
        items = [self._memory(row) for row in rows]
        if terms:
            items = [item for item in items if any(term in item.statement.casefold() for term in terms)]
        selected, used = [], 0
        for item in items:
            if len(selected) >= max(1, min(int(limit), 20)):
                break
            if used + len(item.statement) > max(0, int(budget_chars)):
                continue
            selected.append(item)
            used += len(item.statement)
        for item in selected:
            if item.status == "active":
                self.mark_memory_used(item.memory_id, owner_id)
        return selected

    def record_capability_failure(
        self,
        owner_id: str,
        memory_id: str,
        conversation_id: Optional[str],
        message_id: Optional[str],
        excerpt: str,
        *,
        penalty: float = 0.5,
    ) -> Optional[MemoryRecord]:
        """Add failure evidence and move the method to review without erasing evidence."""
        if not 0 < float(penalty) <= 1:
            raise ValueError("invalid capability failure penalty")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM memories WHERE memory_id=? AND owner_id=?", (memory_id, owner_id)).fetchone()
            if not row or row["category"] != "capability_method":
                raise LookupError("capability method not found")
            self._insert_memory_evidence(db, memory_id, owner_id, conversation_id, message_id, "tool_failure", excerpt)
            confidence = max(0.0, min(1.0, float(row["confidence"]) * float(penalty)))
            db.execute("UPDATE memories SET confidence=?, status='candidate', updated_at=? WHERE memory_id=? AND owner_id=?", (confidence, _now(), memory_id, owner_id))
        return self.get_memory(memory_id, owner_id)

    def get_skill_improvement_proposal(self, proposal_id: str, owner_id: str) -> Optional[SkillImprovementProposal]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM skill_improvement_proposals WHERE proposal_id=? AND owner_id=?", (proposal_id, owner_id)).fetchone()
        return self._proposal(row) if row else None

    def create_skill_improvement_proposal(
        self,
        owner_id: str,
        *,
        scope: str,
        project_id: Optional[str],
        target_file: str,
        problem_evidence: str,
        diff_summary: str,
        verification_plan: str,
        risk_summary: str,
        source_memory_id: Optional[str] = None,
        protected_hash_before: Optional[dict] = None,
    ) -> SkillImprovementProposal:
        if scope not in MEMORY_SCOPES:
            raise ValueError("invalid proposal scope")
        if scope == "project":
            if not project_id or not self.get_project(project_id, owner_id):
                raise LookupError("project not found")
        elif project_id is not None:
            raise ValueError("global proposal cannot have a project")
        values = (target_file, problem_evidence, diff_summary, verification_plan, risk_summary)
        if any(not isinstance(value, str) or not value.strip() for value in values) or "\x00" in target_file:
            raise ValueError("invalid skill improvement proposal")
        if source_memory_id:
            source = self.get_memory(source_memory_id, owner_id)
            if not source or source.category != "capability_method":
                raise ValueError("proposal source must be a capability method")
            if source.scope != scope or source.project_id != project_id:
                raise ValueError("proposal source scope mismatch")
        before = self._canonical_hashes(protected_hash_before)
        now, proposal_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            if source_memory_id:
                existing = db.execute(
                    "SELECT * FROM skill_improvement_proposals WHERE owner_id=? AND source_memory_id=? AND target_file=? AND status IN ('proposed', 'accepted') ORDER BY updated_at DESC LIMIT 1",
                    (owner_id, source_memory_id, target_file.strip()),
                ).fetchone()
                if existing:
                    return self._proposal(existing)
            db.execute("""INSERT INTO skill_improvement_proposals(
                proposal_id, owner_id, scope, project_id, target_file, problem_evidence,
                diff_summary, verification_plan, risk_summary, status,
                protected_hash_before, protected_hash_after, source_memory_id,
                created_at, updated_at, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, '{}', ?, ?, ?, NULL)""", (
                proposal_id, owner_id, scope, project_id, target_file.strip(), problem_evidence.strip(),
                diff_summary.strip(), verification_plan.strip(), risk_summary.strip(),
                json.dumps(before, ensure_ascii=False, sort_keys=True), source_memory_id, now, now,
            ))
        return self.get_skill_improvement_proposal(proposal_id, owner_id)

    def list_skill_improvement_proposals(
        self,
        owner_id: str,
        *,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[SkillImprovementProposal]:
        if status is not None and status not in SKILL_PROPOSAL_STATUSES:
            raise ValueError("invalid proposal status")
        params: list[object] = [owner_id]
        clause = "owner_id=?"
        if project_id is None:
            clause += " AND scope='global'"
        else:
            clause += " AND (scope='global' OR (scope='project' AND project_id=?))"
            params.append(project_id)
        if status is not None:
            clause += " AND status=?"
            params.append(status)
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM skill_improvement_proposals WHERE {clause} ORDER BY updated_at DESC, proposal_id DESC LIMIT ?", (*params, max(1, min(int(limit), 100)))).fetchall()
        return [self._proposal(row) for row in rows]

    def update_skill_improvement_proposal(
        self,
        proposal_id: str,
        owner_id: str,
        *,
        status: str,
        external_confirmation: bool = False,
        protected_hash_after: Optional[dict] = None,
    ) -> SkillImprovementProposal:
        if status not in SKILL_PROPOSAL_STATUSES:
            raise ValueError("invalid proposal status")
        after = self._canonical_hashes(protected_hash_after)
        allowed = {
            "proposed": {"accepted", "rejected"},
            "accepted": {"rejected", "applied"},
            "rejected": set(),
            "applied": set(),
        }
        now = _now()
        with self.transaction() as db:
            current_row = db.execute("SELECT * FROM skill_improvement_proposals WHERE proposal_id=? AND owner_id=?", (proposal_id, owner_id)).fetchone()
            if not current_row:
                raise LookupError("proposal not found")
            current_status = current_row["status"]
            if status not in allowed[current_status]:
                raise ValueError("invalid proposal transition")
            current = self._proposal(current_row)
            if status == "applied" and (not external_confirmation or after != current.protected_hash_before):
                raise ValueError("applied proposal requires unchanged protected hashes and external confirmation")
            result = db.execute(
                "UPDATE skill_improvement_proposals SET status=?, protected_hash_after=?, updated_at=?, decided_at=? WHERE proposal_id=? AND owner_id=? AND status=?",
                (status, json.dumps(after, ensure_ascii=False, sort_keys=True), now, now, proposal_id, owner_id, current_status),
            )
            if result.rowcount != 1:
                raise ValueError("proposal state conflict")
        return self.get_skill_improvement_proposal(proposal_id, owner_id)

    @staticmethod
    def _system_rule(row: sqlite3.Row) -> SystemRule:
        return SystemRule(row["owner_id"], row["content"], bool(row["enabled"]), _dt(row["updated_at"]))

    def get_system_rule(self, owner_id: str) -> SystemRule:
        """Read one owner rule, failing closed when SQLite cannot answer."""
        try:
            with self.connection() as db:
                row = db.execute("SELECT owner_id, content, enabled, updated_at FROM system_rules WHERE owner_id=?", (owner_id,)).fetchone()
        except Exception as error:
            raise SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE") from error
        if not row:
            return SystemRule(owner_id, "", False, datetime.now(timezone.utc))
        return self._system_rule(row)

    def upsert_system_rule(self, owner_id: str, content: str, enabled: bool) -> SystemRule:
        if not isinstance(content, str) or len(content) > 12000:
            raise ValueError("system rule content must be at most 12000 Unicode characters")
        content = content.strip()
        if enabled and not content:
            raise ValueError("system rule cannot be enabled with empty content")
        try:
            with self.transaction() as db:
                db.execute("""INSERT INTO system_rules(owner_id, content, enabled, updated_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(owner_id) DO UPDATE SET content=excluded.content, enabled=excluded.enabled, updated_at=excluded.updated_at""", (owner_id, content, int(bool(enabled)), _now()))
        except ValueError:
            raise
        except Exception as error:
            raise SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE") from error
        return self.get_system_rule(owner_id)

    def set_system_rule_enabled(self, owner_id: str, enabled: bool) -> SystemRule:
        current = self.get_system_rule(owner_id)
        if enabled and not current.content:
            raise ValueError("system rule cannot be enabled with empty content")
        return self.upsert_system_rule(owner_id, current.content, enabled)

    def clear_system_rule(self, owner_id: str) -> None:
        try:
            with self.transaction() as db:
                db.execute("""INSERT INTO system_rules(owner_id, content, enabled, updated_at) VALUES (?, '', 0, ?)
                    ON CONFLICT(owner_id) DO UPDATE SET content='', enabled=0, updated_at=excluded.updated_at""", (owner_id, _now()))
        except Exception as error:
            raise SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE") from error

    @staticmethod
    def _analysis_job(row: sqlite3.Row) -> MemoryAnalysisJob:
        return MemoryAnalysisJob(
            row["analysis_id"], row["user_message_id"], row["owner_id"],
            row["project_id_snapshot"], row["status"], row["model"],
            row["cursor"], int(row["batch_no"]), int(row["saved_count"]),
            int(row["pending_count"]), int(row["failed_count"]),
            row["error_code"], _dt(row["created_at"]), _dt(row["updated_at"]),
            _dt(row["completed_at"]),
            row["lease_token"], int(row["lease_version"]),
        )

    @staticmethod
    def _analysis_item(row: sqlite3.Row) -> MemoryAnalysisItem:
        return MemoryAnalysisItem(
            row["item_id"], row["analysis_id"], row["statement"],
            row["suggested_scope"], float(row["confidence"]),
            row["rationale_summary"], row["decision_status"], row["memory_id"],
            _dt(row["created_at"]), _dt(row["decided_at"]),
        )

    def create_project(self, owner_id: str, name: str, instructions: Optional[str] = None) -> Project:
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("invalid project name")
        now, project_id = _now(), uuid.uuid4().hex
        try:
            with self.transaction() as db:
                db.execute("INSERT INTO projects VALUES (?, ?, ?, ?, 'active', ?, ?)", (project_id, owner_id, name, instructions, now, now))
        except sqlite3.IntegrityError as error:
            raise ValueError("project already exists") from error
        return self.get_project(project_id, owner_id)

    def get_project(self, project_id: str, owner_id: str) -> Optional[Project]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE project_id=? AND owner_id=? AND status!='deleted'", (project_id, owner_id)).fetchone()
        return self._project(row) if row else None

    def update_project(self, project_id: str, owner_id: str, **changes) -> Optional[Project]:
        values = {key: value for key, value in changes.items() if key in {"name", "instructions", "status"}}
        if "name" in values:
            values["name"] = str(values["name"]).strip()
            if not values["name"] or len(values["name"]) > 120: raise ValueError("invalid project name")
        if not values: return self.get_project(project_id, owner_id)
        values["updated_at"] = _now()
        try:
            with self.transaction() as db:
                result = db.execute(f"UPDATE projects SET {', '.join(f'{key}=?' for key in values)} WHERE project_id=? AND owner_id=? AND status!='deleted'", (*values.values(), project_id, owner_id))
                if result.rowcount == 0: return None
        except sqlite3.IntegrityError as error:
            raise ValueError("project already exists") from error
        return self.get_project(project_id, owner_id)

    def delete_project(self, project_id: str, owner_id: str) -> bool:
        with self.transaction() as db:
            result = db.execute("DELETE FROM projects WHERE project_id=? AND owner_id=?", (project_id, owner_id))
        return result.rowcount > 0

    def list_projects(self, owner_id: str, cursor: Optional[str] = None, limit: int = 20) -> tuple[list[Project], Optional[str]]:
        limit = max(1, min(int(limit), 100))
        params: list[object] = [owner_id]
        clause = ""
        if cursor:
            # The cursor kind is deliberately versioned separately from the
            # legacy updated_at ordering.  A cursor issued before this
            # projection must fail rather than silently mixing keysets.
            at, item_id = decode_cursor(cursor, "projects_activity")
            clause = " AND (last_activity_at < ? OR (last_activity_at = ? AND project_id < ?))"
            params.extend([at, at, item_id])
        with self.connection() as db:
            rows = db.execute(
                f"""
                WITH project_activity AS (
                    SELECT p.*,
                           CASE WHEN COALESCE(MAX(c.updated_at), p.updated_at) > p.updated_at
                                THEN COALESCE(MAX(c.updated_at), p.updated_at)
                                ELSE p.updated_at END AS last_activity_at
                    FROM projects AS p
                    LEFT JOIN conversations AS c
                      ON c.project_id = p.project_id
                     AND c.owner_id = p.owner_id
                     AND c.status != 'deleted'
                    WHERE p.owner_id=? AND p.status!='deleted'
                    GROUP BY p.project_id
                )
                SELECT * FROM project_activity
                WHERE 1=1{clause}
                ORDER BY last_activity_at DESC, project_id DESC
                LIMIT ?
                """,
                (*params, limit + 1),
            ).fetchall()
        page = rows[:limit]
        next_cursor = encode_cursor("projects_activity", page[-1]["last_activity_at"], page[-1]["project_id"]) if len(rows) > limit else None
        return [self._project(row) for row in page], next_cursor

    def create_conversation(self, owner_id: str, project_id: Optional[str] = None, title: str = "", memory_history_policy: str = "from_binding") -> Conversation:
        if memory_history_policy not in MEMORY_HISTORY_POLICIES:
            raise ValueError("invalid memory history policy")
        if project_id:
            project = self.get_project(project_id, owner_id)
            if not project:
                raise LookupError("project not found")
            if project.status != "active":
                raise ValueError("project is not active")
        now, conversation_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO conversations(conversation_id, owner_id, project_id, title, status, memory_history_policy, created_at, updated_at, memory_binding_at, memory_binding_message_id) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, NULL, NULL)", (conversation_id, owner_id, project_id, title.strip()[:200], memory_history_policy, now, now))
        return self.get_conversation(conversation_id, owner_id)

    def create_conversation_messages(self, owner_id: str, content: str, project_id: Optional[str], model: Optional[str], mode: Optional[str]) -> tuple[Conversation, Message, Message]:
        """Atomically create a first conversation, user message and assistant placeholder."""
        if project_id:
            project = self.get_project(project_id, owner_id)
            if not project:
                raise LookupError("project not found")
            if project.status != "active":
                raise ValueError("project is not active")
        now, conversation_id, user_id, assistant_id = _now(), uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO conversations(conversation_id, owner_id, project_id, title, status, memory_history_policy, created_at, updated_at, memory_binding_at, memory_binding_message_id) VALUES (?, ?, ?, ?, 'active', 'from_binding', ?, ?, NULL, NULL)", (conversation_id, owner_id, project_id, content[:80], now, now))
            db.execute("INSERT INTO messages VALUES (?, ?, ?, NULL, 'user', ?, 'completed', ?, ?, ?, ?)", (user_id, conversation_id, owner_id, content, model, mode, now, now))
            db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, 'assistant', '', 'pending', ?, ?, ?, NULL)", (assistant_id, conversation_id, owner_id, user_id, model, mode, now))
        return self.get_conversation(conversation_id, owner_id), self.get_message(user_id, owner_id), self.get_message(assistant_id, owner_id)

    def get_conversation(self, conversation_id: str, owner_id: str) -> Optional[Conversation]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversations WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (conversation_id, owner_id)).fetchone()
        return self._conversation(row) if row else None

    def update_conversation(self, conversation_id: str, owner_id: str, **changes) -> Optional[Conversation]:
        confirm_move = bool(changes.pop("confirm_move", False))
        allowed = {"title", "project_id", "status", "memory_history_policy"}
        values = {key: value for key, value in changes.items() if key in allowed}
        current = self.get_conversation(conversation_id, owner_id)
        if not current:
            return None
        if "memory_history_policy" in values and values["memory_history_policy"] not in MEMORY_HISTORY_POLICIES:
            raise ValueError("invalid memory history policy")
        if "status" in values and values["status"] not in {"active", "archived", "deleted"}:
            raise ValueError("invalid conversation status")
        if "project_id" in values and values["project_id"]:
            project = self.get_project(values["project_id"], owner_id)
            if not project:
                raise LookupError("project not found")
            if project.status != "active":
                raise ValueError("project is not active")
        project_changed = "project_id" in values and values["project_id"] != current.project_id
        has_messages = False
        if project_changed or values.get("memory_history_policy") == "include_prior_history":
            with self.connection() as db:
                has_messages = db.execute("SELECT 1 FROM messages WHERE conversation_id=? LIMIT 1", (conversation_id,)).fetchone() is not None
        if (project_changed or (values.get("memory_history_policy") == "include_prior_history" and has_messages)) and has_messages and not confirm_move:
            raise ValueError("conversation move requires confirmation")
        if not values:
            return current
        values["updated_at"] = _now()
        if project_changed:
            # A new project scope starts at this instant. Existing messages
            # remain durable but are excluded by from_binding context assembly.
            # The cutoff is intentionally retained even when unbinding: an
            # unbound conversation must not re-introduce its old project
            # context, while later unbound messages remain usable.
            values["memory_binding_at"] = values["updated_at"]
            values["memory_binding_message_id"] = None
        assignments = ", ".join(f"{key}=?" for key in values)
        with self.transaction() as db:
            if project_changed:
                # A project-scoped source from the old context must not follow
                # a conversation into its new project. Global evidence remains
                # valid because it is owner-scoped rather than project-scoped.
                db.execute("""UPDATE memory_evidence SET conversation_id=NULL, message_id=NULL
                    WHERE conversation_id=? AND memory_id IN (
                        SELECT memory_id FROM memories WHERE owner_id=? AND scope='project'
                    )""", (conversation_id, owner_id))
            result = db.execute(f"UPDATE conversations SET {assignments} WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (*values.values(), conversation_id, owner_id))
            if result.rowcount == 0:
                return None
        return self.get_conversation(conversation_id, owner_id)

    def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        with self.transaction() as db:
            result = db.execute("UPDATE conversations SET status='deleted', updated_at=? WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (_now(), conversation_id, owner_id))
        return result.rowcount > 0

    def list_conversations(
        self,
        owner_id: str,
        project_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        *,
        status: Optional[str] = None,
        unbound_only: bool = False,
    ) -> tuple[list[Conversation], Optional[str]]:
        limit = max(1, min(int(limit), 100)); params: list[object] = [owner_id]; clause = ""
        if status is not None and status not in {"active", "archived"}:
            raise ValueError("invalid conversation status")
        if unbound_only and project_id is not None:
            raise ValueError("unbound_only cannot be combined with project_id")
        if project_id is None:
            # Preserve the legacy unbound default.  An explicit status is the
            # archive/global view and therefore intentionally spans bindings;
            # callers wanting only unbound rows use unbound_only=true.
            if status is None or unbound_only:
                clause += " AND project_id IS NULL"
        else:
            if not self.get_project(project_id, owner_id):
                raise LookupError("project not found")
            clause += " AND project_id=?"; params.append(project_id)
        if status is None:
            clause += " AND status!='deleted'"
        else:
            clause += " AND status=?"; params.append(status)
        # Every list scope gets its own opaque cursor namespace.  In
        # particular, a project cursor must never be accepted by the default
        # or another project's list, even when the status filter is omitted.
        cursor_kind = f"conversations:v3:project={project_id or '*'}:status={status or '*'}:unbound={int(unbound_only)}"
        if cursor:
            at, item_id = decode_cursor(cursor, cursor_kind); clause += " AND (updated_at < ? OR (updated_at = ? AND conversation_id < ?))"; params.extend([at, at, item_id])
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM conversations WHERE owner_id=?{clause} ORDER BY updated_at DESC, conversation_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        page = rows[:limit]; next_cursor = encode_cursor(cursor_kind, page[-1]["updated_at"], page[-1]["conversation_id"]) if len(rows) > limit else None
        return [self._conversation(row) for row in page], next_cursor

    def create_message(self, conversation_id: str, owner_id: str, role: str, content: str, *, status: str = "pending", model: Optional[str] = None, mode: Optional[str] = None, parent_message_id: Optional[str] = None) -> Message:
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        now, message_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, now, now if status in {"completed", "failed", "interrupted"} else None))
            db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (now, conversation_id))
        return self.get_message(message_id, owner_id)

    def get_message(self, message_id: str, owner_id: str) -> Optional[Message]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM messages WHERE message_id=? AND owner_id=?", (message_id, owner_id)).fetchone()
        return self._message(row) if row else None

    def update_message(self, message_id: str, owner_id: str, *, content: Optional[str] = None, status: Optional[str] = None) -> Optional[Message]:
        values = {}
        if content is not None: values["content"] = content
        if status is not None: values["status"] = status; values["completed_at"] = _now() if status in {"completed", "failed", "interrupted"} else None
        if not values: return self.get_message(message_id, owner_id)
        with self.transaction() as db:
            result = db.execute(f"UPDATE messages SET {', '.join(f'{key}=?' for key in values)} WHERE message_id=? AND owner_id=?", (*values.values(), message_id, owner_id))
            if result.rowcount == 0: return None
        return self.get_message(message_id, owner_id)

    def list_messages(self, conversation_id: str, owner_id: str, *, before: Optional[str] = None, target_chars: int = 4000, limit: int = 50) -> tuple[list[Message], Optional[str]]:
        if not self.get_conversation(conversation_id, owner_id): raise LookupError("conversation not found")
        target_chars = max(1, min(int(target_chars), 100_000)); limit = max(1, min(int(limit), 50)); params: list[object] = [conversation_id, owner_id]; clause = ""
        if before:
            at, item_id = decode_cursor(before, "messages"); clause = " AND (created_at < ? OR (created_at = ? AND message_id < ?))"; params.extend([at, at, item_id])
            with self.connection() as db:
                cursor_row = db.execute("SELECT conversation_id, owner_id, created_at FROM messages WHERE message_id=?", (item_id,)).fetchone()
            if not cursor_row or cursor_row["conversation_id"] != conversation_id or cursor_row["owner_id"] != owner_id or cursor_row["created_at"] != at:
                raise ValueError("invalid cursor")
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM messages WHERE conversation_id=? AND owner_id=?{clause} ORDER BY created_at DESC, message_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        selected = []; chars = 0
        for row in rows:
            selected.append(self._message(row)); chars += len(row["content"] or "")
            if chars >= target_chars: break
        next_cursor = encode_cursor("messages", selected[-1].created_at.isoformat(), selected[-1].message_id) if len(rows) > len(selected) else None
        return selected, next_cursor

    def list_context_messages(self, conversation_id: str, owner_id: str, *, limit: int = 50) -> list[Message]:
        """Assemble only history allowed by the conversation binding policy."""
        conversation = self.get_conversation(conversation_id, owner_id)
        if not conversation:
            raise LookupError("conversation not found")
        params: list[object] = [conversation_id, owner_id]
        clause = ""
        if conversation.memory_history_policy == "from_binding" and conversation.memory_binding_at:
            clause = " AND created_at > ?"
            params.append(conversation.memory_binding_at.isoformat())
        limit = max(1, min(int(limit), 100))
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM messages WHERE conversation_id=? AND owner_id=?{clause} ORDER BY created_at DESC, message_id DESC LIMIT ?", (*params, limit)).fetchall()
        return [self._message(row) for row in rows]

    def create_memory(self, owner_id: str, scope: str, project_id: Optional[str], category: str, statement: str, source_kind: str, confidence: float, *, status: str = "active", supersedes_id: Optional[str] = None, evidence: Optional[tuple[Optional[str], Optional[str], str, Optional[str]]] = None) -> MemoryRecord:
        if scope not in MEMORY_SCOPES:
            raise ValueError("invalid memory scope")
        if scope == "project":
            if not project_id or not self.get_project(project_id, owner_id):
                raise LookupError("project not found")
        elif project_id is not None:
            raise ValueError("global memory cannot have a project")
        if category not in MEMORY_CATEGORIES or source_kind not in MEMORY_SOURCE_KINDS or status not in MEMORY_STATUSES:
            raise ValueError("invalid memory metadata")
        if not isinstance(statement, str) or not statement.strip() or len(statement.strip()) > 1000 or not 0 <= float(confidence) <= 1:
            raise ValueError("invalid memory")
        if supersedes_id:
            previous = self.get_memory(supersedes_id, owner_id)
            if not previous or previous.scope != scope or previous.project_id != project_id:
                raise ValueError("invalid superseded memory")
        now, memory_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (memory_id, owner_id, scope, project_id, category, statement.strip(), source_kind, status, float(confidence), supersedes_id, now, now, None))
            if evidence is not None:
                self._insert_memory_evidence(db, memory_id, owner_id, evidence[0], evidence[1], evidence[2], evidence[3])
        return self.get_memory(memory_id, owner_id)

    def get_memory(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        with self.connection() as db: row = db.execute("SELECT * FROM memories WHERE memory_id=? AND owner_id=?", (memory_id, owner_id)).fetchone()
        return self._memory(row) if row else None

    def list_memories(self, owner_id: str, project_id: Optional[str] = None, *, status: str = "active", scope: Optional[str] = None) -> list[MemoryRecord]:
        """List one scope, preserving the Task02 positional project_id API.

        ``scope`` is explicit for Task03.  For compatibility, passing
        ``project_id='global'`` or ``'project'`` is treated as a scope selector.
        With no scope and no project, the historical unbound-project query is
        retained rather than silently exposing global records.
        """
        if project_id in {"global", "project"} and scope is None:
            scope, project_id = project_id, None
        if scope is not None and scope not in MEMORY_SCOPES:
            raise ValueError("invalid memory scope")
        if status not in MEMORY_STATUSES:
            raise ValueError("invalid memory status")
        explicit_scope = scope is not None
        if scope == "global" and project_id is not None:
            raise ValueError("global scope cannot include project_id")
        if scope == "project" and project_id is None:
            raise ValueError("project scope requires project_id")
        if explicit_scope and scope == "project" and not self.get_project(project_id, owner_id):
            raise LookupError("project not found")
        if scope is None:
            scope = "project"
        params: list[object] = [owner_id, status, scope]
        clause = " AND scope=?"
        if scope == "global":
            clause += " AND project_id IS NULL"
        elif project_id is None:
            clause += " AND project_id IS NULL"
        else:
            clause += " AND project_id=?"; params.append(project_id)
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM memories WHERE owner_id=? AND status=?{clause} ORDER BY updated_at DESC, memory_id DESC", params).fetchall()
        return [self._memory(row) for row in rows]

    def list_recall_memories(self, owner_id: str, project_id: Optional[str]) -> list[MemoryRecord]:
        """Return active global memories followed by the current project scope."""
        params: list[object] = [owner_id]
        clause = " AND (scope='global'"
        if project_id:
            clause += " OR (scope='project' AND project_id=?)"
            params.append(project_id)
        clause += ") AND status='active'"
        with self.connection() as db:
            rows = db.execute(
                f"SELECT * FROM memories WHERE owner_id=?{clause} ORDER BY CASE scope WHEN 'global' THEN 0 ELSE 1 END, updated_at DESC, memory_id DESC",
                params,
            ).fetchall()
        return [self._memory(row) for row in rows]

    def update_memory(self, memory_id: str, owner_id: str, **changes) -> Optional[MemoryRecord]:
        """Govern a memory, versioning content edits instead of overwriting it."""
        allowed = {"statement", "category", "confidence", "status"}
        values = {key: value for key, value in changes.items() if key in allowed}
        current = self.get_memory(memory_id, owner_id)
        if not current or not values:
            return current
        if "status" in values and values["status"] not in MEMORY_STATUSES:
            raise ValueError("invalid memory status")
        if "category" in values and values["category"] not in MEMORY_CATEGORIES:
            raise ValueError("invalid memory category")
        if "confidence" in values and not 0 <= float(values["confidence"]) <= 1:
            raise ValueError("invalid memory confidence")
        content_edit = any(key in values for key in ("statement", "category", "confidence"))
        if content_edit:
            statement = str(values.get("statement", current.statement)).strip()
            category = values.get("category", current.category)
            confidence = float(values.get("confidence", current.confidence))
            new_status = values.get("status", "active")
            if not statement or len(statement) > 1000:
                raise ValueError("invalid memory")
            now, new_id = _now(), uuid.uuid4().hex
            with self.transaction() as db:
                db.execute("UPDATE memories SET status='superseded', updated_at=? WHERE memory_id=? AND owner_id=?", (now, memory_id, owner_id))
                db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (new_id, owner_id, current.scope, current.project_id, category, statement, "manual", new_status, confidence, memory_id, now, now, current.last_used_at.isoformat() if current.last_used_at else None))
                db.execute("INSERT INTO memory_evidence(memory_id, conversation_id, message_id, evidence_type, excerpt) SELECT ?, conversation_id, message_id, 'manual', excerpt FROM memory_evidence WHERE memory_id=?", (new_id, memory_id))
            return self.get_memory(new_id, owner_id)
        with self.transaction() as db:
            result = db.execute("UPDATE memories SET status=?, updated_at=? WHERE memory_id=? AND owner_id=?", (values["status"], _now(), memory_id, owner_id))
        return self.get_memory(memory_id, owner_id) if result.rowcount else None

    def confirm_memory(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        memory = self.get_memory(memory_id, owner_id)
        if not memory:
            return None
        if memory.status != "candidate":
            raise ValueError("memory is not a candidate")
        return self.update_memory(memory_id, owner_id, status="active")

    def delete_memory(self, memory_id: str, owner_id: str) -> bool:
        with self.transaction() as db:
            result = db.execute("UPDATE memories SET status='deleted', updated_at=? WHERE memory_id=? AND owner_id=? AND status!='deleted'", (_now(), memory_id, owner_id))
        return result.rowcount > 0

    def undo_memory(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        memory = self.get_memory(memory_id, owner_id)
        if not memory:
            return None
        if memory.status != "deleted":
            raise ValueError("memory is not deleted")
        return self.update_memory(memory_id, owner_id, status="active")

    def mark_memory_used(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        with self.transaction() as db:
            now = _now()
            db.execute("UPDATE memories SET last_used_at=?, updated_at=? WHERE memory_id=? AND owner_id=? AND status='active'", (now, now, memory_id, owner_id))
        return self.get_memory(memory_id, owner_id)

    def promote_memory(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        """Promote an automatically generated candidate only with evidence.

        Manual confirmation remains available through ``confirm_memory``; this
        stricter seam is used by the evolution worker and never changes scope.
        """
        memory = self.get_memory(memory_id, owner_id)
        if not memory:
            return None
        if memory.status != "candidate":
            raise ValueError("memory is not a candidate")
        with self.connection() as db:
            evidence = db.execute("SELECT 1 FROM memory_evidence WHERE memory_id=? LIMIT 1", (memory_id,)).fetchone()
        if not evidence:
            raise ValueError("memory promotion requires evidence")
        with self.transaction() as db:
            if memory.supersedes_id:
                db.execute("UPDATE memories SET status='superseded', updated_at=? WHERE memory_id=? AND owner_id=?", (_now(), memory.supersedes_id, owner_id))
            db.execute("UPDATE memories SET status='active', updated_at=? WHERE memory_id=? AND owner_id=? AND status='candidate'", (_now(), memory_id, owner_id))
        return self.get_memory(memory_id, owner_id)

    @staticmethod
    def _raw_event(row: sqlite3.Row) -> RawEvent:
        return RawEvent(row["event_id"], row["owner_id"], row["conversation_id"], row["message_id"], row["event_kind"], json.loads(row["payload"]), row["idempotency_key"], _dt(row["created_at"]))

    def append_raw_event(self, owner_id: str, conversation_id: str, event_kind: str, payload: dict, *, message_id: Optional[str] = None, idempotency_key: Optional[str] = None) -> RawEvent:
        """Append an immutable event; a repeated key returns the original row."""
        if not event_kind or not isinstance(payload, dict):
            raise ValueError("invalid raw event")
        conversation = self.get_conversation(conversation_id, owner_id)
        if not conversation:
            raise LookupError("conversation not found")
        now, event_id = _now(), uuid.uuid4().hex
        try:
            with self.transaction() as db:
                if message_id:
                    message_row = db.execute("SELECT owner_id, conversation_id FROM messages WHERE message_id=?", (message_id,)).fetchone()
                    if not message_row or message_row["owner_id"] != owner_id:
                        raise LookupError("message not found")
                    if message_row["conversation_id"] != conversation_id:
                        raise ValueError("message conversation mismatch")
                db.execute("INSERT INTO raw_events(event_id, owner_id, conversation_id, message_id, event_kind, payload, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (event_id, owner_id, conversation_id, message_id, event_kind.strip()[:80], json.dumps(payload, ensure_ascii=False, sort_keys=True), idempotency_key, now))
        except sqlite3.IntegrityError:
            if idempotency_key:
                with self.connection() as db:
                    row = db.execute("SELECT * FROM raw_events WHERE owner_id=? AND conversation_id=? AND idempotency_key=?", (owner_id, conversation_id, idempotency_key)).fetchone()
                if row:
                    return self._raw_event(row)
            raise
        with self.connection() as db:
            row = db.execute("SELECT * FROM raw_events WHERE event_id=?", (event_id,)).fetchone()
        return self._raw_event(row)

    def list_raw_events(self, conversation_id: str, owner_id: str, *, after: Optional[str] = None, limit: int = 1000) -> list[RawEvent]:
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        limit = max(1, min(int(limit), 5000))
        params: list[object] = [owner_id, conversation_id]
        clause = ""
        if after:
            with self.connection() as db:
                row = db.execute("SELECT created_at FROM raw_events WHERE event_id=? AND owner_id=? AND conversation_id=?", (after, owner_id, conversation_id)).fetchone()
            if not row:
                raise ValueError("invalid raw event cursor")
            clause = " AND (created_at > ? OR (created_at = ? AND event_id > ?))"
            params.extend([row["created_at"], row["created_at"], after])
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM raw_events WHERE owner_id=? AND conversation_id=?{clause} ORDER BY created_at, event_id LIMIT ?", (*params, limit)).fetchall()
        return [self._raw_event(row) for row in rows]

    def count_capability_method_evidence(self, owner_id: str, statement: str, *, project_id: Optional[str] = None) -> int:
        """Count distinct user-message conversations for a persisted method signal."""
        normalized = " ".join(str(statement or "").split()).casefold()
        if not normalized:
            return 0
        params: list[object] = [owner_id]
        clause = "r.owner_id=? AND m.role='user' AND r.event_kind IN ('method_repeated', 'repeated', 'method_explicit', 'explicit_memory')"
        if project_id is None:
            clause += " AND c.project_id IS NULL"
        else:
            clause += " AND c.project_id=?"
            params.append(project_id)
        with self.connection() as db:
            rows = db.execute(
                f"SELECT r.conversation_id, r.payload FROM raw_events r JOIN conversations c ON c.conversation_id=r.conversation_id AND c.owner_id=r.owner_id JOIN messages m ON m.message_id=r.message_id AND m.conversation_id=r.conversation_id AND m.owner_id=r.owner_id WHERE {clause}",
                params,
            ).fetchall()
        conversation_ids: set[str] = set()
        for row in rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("category") != "capability_method":
                continue
            candidate = payload.get("method_statement") or payload.get("method") or payload.get("statement")
            if " ".join(str(candidate or "").split()).casefold() == normalized:
                conversation_ids.add(row["conversation_id"])
        return len(conversation_ids)

    def _summary(self, row: sqlite3.Row) -> ConversationSummary:
        return ConversationSummary(row["summary_id"], row["owner_id"], row["conversation_id"], row["summary_text"], row["source_event_id"], row["status"], _dt(row["created_at"]), _dt(row["updated_at"]))

    def upsert_conversation_summary(self, owner_id: str, conversation_id: str, summary_text: str, *, source_event_id: Optional[str] = None, status: str = "active") -> ConversationSummary:
        if not summary_text or status not in {"active", "superseded", "disabled"}:
            raise ValueError("invalid conversation summary")
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        now, summary_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            existing = db.execute("SELECT summary_id, created_at FROM conversation_summaries WHERE owner_id=? AND conversation_id=?", (owner_id, conversation_id)).fetchone()
            if existing:
                summary_id = existing["summary_id"]
                db.execute("UPDATE conversation_summaries SET summary_text=?, source_event_id=?, status=?, updated_at=? WHERE summary_id=? AND owner_id=?", (summary_text, source_event_id, status, now, summary_id, owner_id))
            else:
                db.execute("INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (summary_id, owner_id, conversation_id, summary_text, source_event_id, status, now, now))
        with self.connection() as db:
            return self._summary(db.execute("SELECT * FROM conversation_summaries WHERE summary_id=?", (summary_id,)).fetchone())

    def list_conversation_summaries(self, conversation_id: str, owner_id: str, *, budget_chars: Optional[int] = None) -> list[ConversationSummary]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM conversation_summaries WHERE conversation_id=? AND owner_id=? AND status='active' ORDER BY updated_at DESC", (conversation_id, owner_id)).fetchall()
        items = [self._summary(row) for row in rows]
        if budget_chars is None:
            return items
        selected, used = [], 0
        for item in items:
            if used + len(item.summary_text) > max(0, int(budget_chars)):
                break
            selected.append(item); used += len(item.summary_text)
        return selected

    def list_recall_summaries(self, owner_id: str, project_id: Optional[str], *, query: str = "", budget_chars: int = 1500) -> list[ConversationSummary]:
        params: list[object] = [owner_id]
        clause = "c.owner_id=? AND s.status='active'"
        if project_id:
            clause += " AND c.project_id=?"; params.append(project_id)
        else:
            clause += " AND c.project_id IS NULL"
        with self.connection() as db:
            rows = db.execute(f"SELECT s.* FROM conversation_summaries s JOIN conversations c ON c.conversation_id=s.conversation_id WHERE {clause} ORDER BY s.updated_at DESC LIMIT 50", params).fetchall()
        terms = {part.lower() for part in (query or "").split() if len(part) > 1}
        items = [self._summary(row) for row in rows]
        if terms:
            relevant = [item for item in items if any(term in item.summary_text.lower() for term in terms)]
            items = relevant
        selected, used = [], 0
        for item in items:
            if used + len(item.summary_text) > max(0, int(budget_chars)):
                break
            selected.append(item); used += len(item.summary_text)
        return selected

    def _checkpoint(self, row: sqlite3.Row) -> EvolutionCheckpoint:
        return EvolutionCheckpoint(row["checkpoint_id"], row["owner_id"], row["conversation_id"], row["stage"], row["status"], row["cursor"], int(row["batch_index"]), int(row["total_batches"]), json.loads(row["state_json"] or "{}"), int(row["attempts"]), row["idempotency_key"], row["error"], _dt(row["created_at"]), _dt(row["updated_at"]))

    def get_evolution_checkpoint(self, conversation_id: str, owner_id: str, stage: str = "summarize") -> Optional[EvolutionCheckpoint]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM evolution_checkpoints WHERE conversation_id=? AND owner_id=? AND stage=?", (conversation_id, owner_id, stage)).fetchone()
        return self._checkpoint(row) if row else None

    def list_evolution_work_items(self, owner_id: str) -> list[str]:
        """Return sessions with raw input or a retryable evolution checkpoint."""
        with self.connection() as db:
            rows = db.execute("""SELECT conversation_id FROM raw_events WHERE owner_id=?
                UNION SELECT conversation_id FROM evolution_checkpoints
                WHERE owner_id=? AND status IN ('failed', 'running')""", (owner_id, owner_id)).fetchall()
        return [row["conversation_id"] for row in rows]

    def claim_evolution_checkpoint(self, conversation_id: str, owner_id: str, *, stage: str = "summarize", idempotency_key: Optional[str] = None, total_batches: int = 0, input_last_event_id: Optional[str] = None) -> tuple[EvolutionCheckpoint, bool]:
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        now, checkpoint_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            row = db.execute("SELECT * FROM evolution_checkpoints WHERE conversation_id=? AND owner_id=? AND stage=?", (conversation_id, owner_id, stage)).fetchone()
            if row and row["status"] == "running":
                stale_before = datetime.now(timezone.utc) - timedelta(seconds=EVOLUTION_LEASE_SECONDS)
                updated_at = _dt(row["updated_at"])
                if updated_at and updated_at <= stale_before:
                    result = db.execute("UPDATE evolution_checkpoints SET status='running', total_batches=?, attempts=attempts+1, idempotency_key=?, error=NULL, updated_at=? WHERE checkpoint_id=? AND owner_id=? AND status='running' AND updated_at=?", (total_batches, idempotency_key, now, row["checkpoint_id"], owner_id, row["updated_at"]))
                    if result.rowcount:
                        row = db.execute("SELECT * FROM evolution_checkpoints WHERE checkpoint_id=?", (row["checkpoint_id"],)).fetchone()
                        return self._checkpoint(row), True
                return self._checkpoint(row), False
            if row and row["status"] == "completed":
                prior_last = json.loads(row["state_json"] or "{}").get("input_last_event_id")
                if input_last_event_id and input_last_event_id != prior_last:
                    db.execute("UPDATE evolution_checkpoints SET status='running', total_batches=?, batch_index=0, state_json='{}', attempts=attempts+1, idempotency_key=?, error=NULL, updated_at=? WHERE checkpoint_id=? AND status='completed'", (total_batches, idempotency_key, now, row["checkpoint_id"]))
                    row = db.execute("SELECT * FROM evolution_checkpoints WHERE checkpoint_id=?", (row["checkpoint_id"],)).fetchone()
                    return self._checkpoint(row), True
                return self._checkpoint(row), False
            if row:
                db.execute("UPDATE evolution_checkpoints SET status='running', total_batches=?, attempts=attempts+1, idempotency_key=?, error=NULL, updated_at=? WHERE checkpoint_id=?", (total_batches, idempotency_key, now, row["checkpoint_id"]))
                row = db.execute("SELECT * FROM evolution_checkpoints WHERE checkpoint_id=?", (row["checkpoint_id"],)).fetchone()
                return self._checkpoint(row), True
            db.execute("INSERT INTO evolution_checkpoints VALUES (?, ?, ?, ?, 'running', NULL, 0, ?, '{}', 1, ?, NULL, ?, ?)", (checkpoint_id, owner_id, conversation_id, stage, total_batches, idempotency_key, now, now))
            row = db.execute("SELECT * FROM evolution_checkpoints WHERE checkpoint_id=?", (checkpoint_id,)).fetchone()
        return self._checkpoint(row), True

    def save_evolution_progress(self, checkpoint_id: str, owner_id: str, *, cursor: Optional[str], batch_index: int, state: dict) -> Optional[EvolutionCheckpoint]:
        with self.transaction() as db:
            db.execute("UPDATE evolution_checkpoints SET cursor=?, batch_index=?, state_json=?, updated_at=? WHERE checkpoint_id=? AND owner_id=? AND status='running'", (cursor, int(batch_index), json.dumps(state, ensure_ascii=False, sort_keys=True), _now(), checkpoint_id, owner_id))
        with self.connection() as db:
            row = db.execute("SELECT * FROM evolution_checkpoints WHERE checkpoint_id=? AND owner_id=?", (checkpoint_id, owner_id)).fetchone()
        return self._checkpoint(row) if row else None

    def finish_evolution_checkpoint(self, checkpoint_id: str, owner_id: str, *, status: str, error: Optional[str] = None) -> Optional[EvolutionCheckpoint]:
        if status not in {"completed", "failed", "skipped"}:
            raise ValueError("invalid checkpoint status")
        with self.transaction() as db:
            db.execute("UPDATE evolution_checkpoints SET status=?, error=?, updated_at=? WHERE checkpoint_id=? AND owner_id=?", (status, (error or "")[:500] or None, _now(), checkpoint_id, owner_id))
        with self.connection() as db:
            row = db.execute("SELECT * FROM evolution_checkpoints WHERE checkpoint_id=? AND owner_id=?", (checkpoint_id, owner_id)).fetchone()
        return self._checkpoint(row) if row else None

    def list_recall_context(self, owner_id: str, project_id: Optional[str], *, query: str = "", memory_char_budget: int = 4000, summary_char_budget: int = 1500, char_budget: Optional[int] = None, token_budget: Optional[int] = None) -> dict:
        """Return scoped memories and summaries under independent budgets."""
        if char_budget is not None:
            summary_char_budget = min(summary_char_budget, max(0, int(char_budget)))
        if token_budget is not None:
            summary_char_budget = min(summary_char_budget, max(0, int(token_budget)) * 4)
        memories, used = [], 0
        all_memories = self.list_recall_memories(owner_id, project_id)
        for memory in (item for item in all_memories if item.category != "capability_method"):
            if used + len(memory.statement) > max(0, int(memory_char_budget)):
                continue
            memories.append(memory); used += len(memory.statement)
        methods = self.list_capability_methods(
            owner_id, project_id, query=query,
            budget_chars=max(0, int(memory_char_budget) - used), limit=5,
        )
        memories.extend(methods)
        return {
            "memories": memories,
            "capability_methods": methods,
            "summaries": self.list_recall_summaries(owner_id, project_id, query=query, budget_chars=summary_char_budget),
        }

    def create_memory_evidence(self, memory_id: str, conversation_id: Optional[str], message_id: Optional[str], evidence_type: str, excerpt: Optional[str]) -> None:
        if evidence_type not in {"user_statement", "repeated_sessions", "tool_failure", "manual"}:
            raise ValueError("invalid evidence type")
        with self.transaction() as db:
            memory_row = db.execute("SELECT owner_id FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
            if not memory_row:
                raise LookupError("memory not found")
            self._insert_memory_evidence(db, memory_id, memory_row["owner_id"], conversation_id, message_id, evidence_type, excerpt)

    @staticmethod
    def _insert_memory_evidence(db: sqlite3.Connection, memory_id: str, owner_id: str, conversation_id: Optional[str], message_id: Optional[str], evidence_type: str, excerpt: Optional[str]) -> None:
        memory_row = db.execute("SELECT scope, project_id FROM memories WHERE memory_id=? AND owner_id=?", (memory_id, owner_id)).fetchone()
        if not memory_row:
            raise LookupError("memory not found")
        if conversation_id:
            conversation_row = db.execute("SELECT owner_id, project_id FROM conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
            if not conversation_row or conversation_row["owner_id"] != owner_id:
                raise LookupError("conversation not found")
            if memory_row["scope"] == "project" and conversation_row["project_id"] != memory_row["project_id"]:
                raise ValueError("memory evidence project mismatch")
        if message_id:
            message_row = db.execute("""SELECT m.owner_id, m.conversation_id, c.project_id
                FROM messages m JOIN conversations c ON c.conversation_id=m.conversation_id
                WHERE m.message_id=?""", (message_id,)).fetchone()
            if not message_row or message_row["owner_id"] != owner_id or (conversation_id and message_row["conversation_id"] != conversation_id):
                raise LookupError("message not found")
            if memory_row["scope"] == "project" and message_row["project_id"] != memory_row["project_id"]:
                raise ValueError("memory evidence project mismatch")
        db.execute("INSERT INTO memory_evidence VALUES (?, ?, ?, ?, ?)", (memory_id, conversation_id, message_id, evidence_type, (excerpt or "")[:500] or None))

    def list_memory_evidence(self, memory_id: str, owner_id: str) -> list[MemoryEvidence]:
        with self.connection() as db:
            rows = db.execute("SELECT e.* FROM memory_evidence e JOIN memories m ON m.memory_id=e.memory_id WHERE e.memory_id=? AND m.owner_id=?", (memory_id, owner_id)).fetchall()
        return [MemoryEvidence(row["memory_id"], row["conversation_id"], row["message_id"], row["evidence_type"], row["excerpt"]) for row in rows]

    # ---------- durable post-answer memory analysis ----------
    def create_memory_analysis_job(self, user_message_id: str, owner_id: str, *, model: Optional[str] = None) -> MemoryAnalysisJob:
        model = model or MEMORY_ANALYSIS_MODEL
        with self.transaction() as db:
            row = db.execute("""SELECT m.role, m.conversation_id, m.owner_id, c.project_id
                FROM messages m JOIN conversations c ON c.conversation_id=m.conversation_id
                WHERE m.message_id=?""", (user_message_id,)).fetchone()
            if not row or row["owner_id"] != owner_id or row["role"] != "user":
                raise LookupError("user message not found")
            existing = db.execute("SELECT * FROM memory_analysis_jobs WHERE user_message_id=? AND owner_id=?", (user_message_id, owner_id)).fetchone()
            if existing:
                return self._analysis_job(existing)
            now, analysis_id = _now(), uuid.uuid4().hex
            db.execute("""INSERT INTO memory_analysis_jobs(
                analysis_id, user_message_id, owner_id, project_id_snapshot, status,
                model, cursor, batch_no, saved_count, pending_count, failed_count,
                error_code, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, NULL, 0, 0, 0, 0, NULL, ?, ?, NULL)""", (analysis_id, user_message_id, owner_id, row["project_id"], model, now, now))
            row = db.execute("SELECT * FROM memory_analysis_jobs WHERE analysis_id=?", (analysis_id,)).fetchone()
        return self._analysis_job(row)

    def get_memory_analysis_job(self, user_message_id: str, owner_id: str) -> Optional[MemoryAnalysisJob]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM memory_analysis_jobs WHERE user_message_id=? AND owner_id=?", (user_message_id, owner_id)).fetchone()
        return self._analysis_job(row) if row else None

    def get_memory_analysis_job_by_id(self, analysis_id: str, owner_id: str) -> Optional[MemoryAnalysisJob]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM memory_analysis_jobs WHERE analysis_id=? AND owner_id=?", (analysis_id, owner_id)).fetchone()
        return self._analysis_job(row) if row else None

    def claim_memory_analysis_job(self, analysis_id: str, owner_id: str) -> tuple[Optional[MemoryAnalysisJob], bool]:
        now = _now()
        lease_token = uuid.uuid4().hex
        with self.transaction() as db:
            row = db.execute("SELECT * FROM memory_analysis_jobs WHERE analysis_id=? AND owner_id=?", (analysis_id, owner_id)).fetchone()
            if not row:
                return None, False
            if row["status"] == "running":
                updated = _dt(row["updated_at"])
                stale = updated is None or updated <= datetime.now(timezone.utc) - timedelta(seconds=EVOLUTION_LEASE_SECONDS)
                if not stale:
                    return self._analysis_job(row), False
            if row["status"] in {"completed"}:
                return self._analysis_job(row), False
            result = db.execute("""UPDATE memory_analysis_jobs SET status='running', model=COALESCE(model, ?),
                lease_token=?, lease_version=lease_version+1, updated_at=?, error_code=NULL
                WHERE analysis_id=? AND owner_id=? AND (status!='running' OR updated_at=?)""", (row["model"], lease_token, now, analysis_id, owner_id, row["updated_at"]))
            if not result.rowcount:
                return self._analysis_job(db.execute("SELECT * FROM memory_analysis_jobs WHERE analysis_id=?", (analysis_id,)).fetchone()), False
            row = db.execute("SELECT * FROM memory_analysis_jobs WHERE analysis_id=?", (analysis_id,)).fetchone()
        return self._analysis_job(row), True

    def list_memory_analysis_work_items(self, owner_id: str) -> list[str]:
        with self.connection() as db:
            rows = db.execute("SELECT analysis_id FROM memory_analysis_jobs WHERE owner_id=? AND status IN ('pending', 'running', 'partial', 'failed') ORDER BY created_at", (owner_id,)).fetchall()
        return [row["analysis_id"] for row in rows]

    def save_memory_analysis_progress(self, analysis_id: str, owner_id: str, *, lease_token: str, lease_version: int, cursor: Optional[str], batch_no: int, saved_count: int, pending_count: int, failed_count: int, status: str = "running") -> Optional[MemoryAnalysisJob]:
        if status not in ANALYSIS_STATUSES:
            raise ValueError("invalid analysis status")
        with self.transaction() as db:
            db.execute("""UPDATE memory_analysis_jobs SET cursor=?, batch_no=?, saved_count=?, pending_count=?, failed_count=?, status=?, updated_at=?
                WHERE analysis_id=? AND owner_id=? AND status='running' AND lease_token=? AND lease_version=?""", (cursor, int(batch_no), int(saved_count), int(pending_count), int(failed_count), status, _now(), analysis_id, owner_id, lease_token, int(lease_version)))
        return self.get_memory_analysis_job_by_id(analysis_id, owner_id)

    def finish_memory_analysis_job(self, analysis_id: str, owner_id: str, *, lease_token: str, lease_version: int, status: str, error_code: Optional[str] = None) -> Optional[MemoryAnalysisJob]:
        if status not in {"completed", "partial", "failed"}:
            raise ValueError("invalid analysis final status")
        now = _now()
        with self.transaction() as db:
            db.execute("""UPDATE memory_analysis_jobs SET status=?, error_code=?, updated_at=?, completed_at=?
                WHERE analysis_id=? AND owner_id=? AND status='running' AND lease_token=? AND lease_version=?""", (status, (error_code or "")[:100] or None, now, now if status in {"completed", "failed"} else None, analysis_id, owner_id, lease_token, int(lease_version)))
        return self.get_memory_analysis_job_by_id(analysis_id, owner_id)

    def create_memory_analysis_item(self, analysis_id: str, owner_id: str, statement: str, suggested_scope: str, confidence: float, rationale_summary: Optional[str], *, decision_status: str = "pending_confirmation", memory_id: Optional[str] = None, lease_token: Optional[str] = None, lease_version: Optional[int] = None) -> MemoryAnalysisItem:
        if suggested_scope not in MEMORY_SCOPES or decision_status not in ANALYSIS_DECISIONS:
            raise ValueError("invalid analysis item")
        statement = " ".join(str(statement or "").split())[:1000]
        if not statement or not 0 <= float(confidence) <= 1:
            raise ValueError("invalid analysis item")
        with self.transaction() as db:
            job = db.execute("SELECT analysis_id FROM memory_analysis_jobs WHERE analysis_id=? AND owner_id=?", (analysis_id, owner_id)).fetchone()
            if not job:
                raise LookupError("memory analysis not found")
            if lease_token is not None:
                current = db.execute("SELECT status, lease_token, lease_version FROM memory_analysis_jobs WHERE analysis_id=? AND owner_id=?", (analysis_id, owner_id)).fetchone()
                if not current or current["status"] != "running" or current["lease_token"] != lease_token or int(current["lease_version"]) != int(lease_version or 0):
                    raise LeaseLostError("memory analysis lease lost")
            existing = db.execute("SELECT * FROM memory_analysis_items WHERE analysis_id=? AND statement=?", (analysis_id, statement)).fetchone()
            if existing:
                return self._analysis_item(existing)
            now, item_id = _now(), uuid.uuid4().hex
            db.execute("""INSERT INTO memory_analysis_items(item_id, analysis_id, statement, suggested_scope, confidence, rationale_summary, decision_status, memory_id, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (item_id, analysis_id, statement, suggested_scope, float(confidence), (rationale_summary or "")[:300] or None, decision_status, memory_id, now, now if decision_status not in {"pending_confirmation", "failed"} else None))
            row = db.execute("SELECT * FROM memory_analysis_items WHERE item_id=?", (item_id,)).fetchone()
        return self._analysis_item(row)

    def create_analysis_memory(self, analysis_id: str, owner_id: str, *, lease_token: str, lease_version: int, statement: str, scope: str, project_id: Optional[str], category: str, source_kind: str, confidence: float, supersedes_id: Optional[str], evidence: Optional[tuple[Optional[str], Optional[str], str, Optional[str]]], rationale_summary: Optional[str], decision_status: str) -> tuple[MemoryRecord, MemoryAnalysisItem]:
        """Atomically CAS the analysis lease, write memory/evidence and item."""
        if scope not in MEMORY_SCOPES or category not in MEMORY_CATEGORIES or source_kind not in MEMORY_SOURCE_KINDS or decision_status not in ANALYSIS_DECISIONS:
            raise ValueError("invalid analysis memory")
        statement = " ".join(str(statement or "").split())[:1000]
        if not statement or not 0 <= float(confidence) <= 1:
            raise ValueError("invalid analysis memory")
        if scope == "project":
            if not project_id or not self.get_project(project_id, owner_id):
                raise LookupError("project not found")
        elif project_id is not None:
            raise ValueError("global memory cannot have a project")
        now, memory_id, item_id = _now(), uuid.uuid4().hex, uuid.uuid4().hex
        with self.transaction() as db:
            lease = db.execute("SELECT status, lease_token, lease_version FROM memory_analysis_jobs WHERE analysis_id=? AND owner_id=?", (analysis_id, owner_id)).fetchone()
            if not lease or lease["status"] != "running" or lease["lease_token"] != lease_token or int(lease["lease_version"]) != int(lease_version):
                raise LeaseLostError("memory analysis lease lost")
            existing = db.execute("SELECT * FROM memory_analysis_items WHERE analysis_id=? AND statement=?", (analysis_id, statement)).fetchone()
            if existing:
                memory = self.get_memory(existing["memory_id"], owner_id) if existing["memory_id"] else None
                if memory:
                    return memory, self._analysis_item(existing)
            db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)", (memory_id, owner_id, scope, project_id, category, statement, source_kind, float(confidence), supersedes_id, now, now, None))
            if supersedes_id:
                db.execute("UPDATE memories SET status='superseded', updated_at=? WHERE memory_id=? AND owner_id=?", (now, supersedes_id, owner_id))
            if evidence is not None:
                self._insert_memory_evidence(db, memory_id, owner_id, evidence[0], evidence[1], evidence[2], evidence[3])
            db.execute("INSERT INTO memory_analysis_items(item_id, analysis_id, statement, suggested_scope, confidence, rationale_summary, decision_status, memory_id, created_at, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (item_id, analysis_id, statement, scope, float(confidence), (rationale_summary or "")[:300] or None, decision_status, memory_id, now, now))
            memory_row = db.execute("SELECT * FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
            item_row = db.execute("SELECT * FROM memory_analysis_items WHERE item_id=?", (item_id,)).fetchone()
        return self._memory(memory_row), self._analysis_item(item_row)

    def get_memory_analysis_item(self, item_id: str, owner_id: str) -> Optional[MemoryAnalysisItem]:
        with self.connection() as db:
            row = db.execute("""SELECT i.* FROM memory_analysis_items i JOIN memory_analysis_jobs j ON j.analysis_id=i.analysis_id
                WHERE i.item_id=? AND j.owner_id=?""", (item_id, owner_id)).fetchone()
        return self._analysis_item(row) if row else None

    def list_memory_analysis_items(self, user_message_id: str, owner_id: str, *, cursor: Optional[str] = None, limit: int = 10) -> tuple[list[MemoryAnalysisItem], Optional[str]]:
        job = self.get_memory_analysis_job(user_message_id, owner_id)
        if not job:
            raise LookupError("memory analysis not found")
        limit = max(1, min(int(limit), 100))
        params: list[object] = [job.analysis_id]
        clause = ""
        if cursor:
            at, item_id = decode_cursor(cursor, f"memory-analysis:{job.analysis_id}")
            clause = " AND (created_at > ? OR (created_at = ? AND item_id > ?))"
            params.extend([at, at, item_id])
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM memory_analysis_items WHERE analysis_id=?{clause} ORDER BY created_at, item_id LIMIT ?", (*params, limit + 1)).fetchall()
        page = rows[:limit]
        next_cursor = encode_cursor(f"memory-analysis:{job.analysis_id}", page[-1]["created_at"], page[-1]["item_id"]) if len(rows) > limit else None
        return [self._analysis_item(row) for row in page], next_cursor

    def list_memory_analysis_item_ids(self, analysis_id: str, owner_id: str, item_ids: Optional[list[str]] = None) -> list[MemoryAnalysisItem]:
        params: list[object] = [analysis_id, owner_id]
        clause = ""
        if item_ids:
            placeholders = ",".join("?" for _ in item_ids)
            clause = f" AND i.item_id IN ({placeholders})"
            params.extend(item_ids)
        with self.connection() as db:
            rows = db.execute(f"""SELECT i.* FROM memory_analysis_items i JOIN memory_analysis_jobs j ON j.analysis_id=i.analysis_id
                WHERE i.analysis_id=? AND j.owner_id=?{clause} ORDER BY i.created_at, i.item_id""", params).fetchall()
        return [self._analysis_item(row) for row in rows]

    def update_memory_analysis_item(self, item_id: str, owner_id: str, *, decision_status: str, memory_id: Optional[str] = None) -> Optional[MemoryAnalysisItem]:
        if decision_status not in ANALYSIS_DECISIONS:
            raise ValueError("invalid analysis decision")
        with self.transaction() as db:
            result = db.execute("""UPDATE memory_analysis_items SET decision_status=?, memory_id=?, decided_at=?
                WHERE item_id=? AND analysis_id IN (SELECT analysis_id FROM memory_analysis_jobs WHERE owner_id=?)
                AND decision_status='pending_confirmation'""", (decision_status, memory_id, _now(), item_id, owner_id))
            if not result.rowcount:
                row = db.execute("""SELECT i.* FROM memory_analysis_items i JOIN memory_analysis_jobs j ON j.analysis_id=i.analysis_id
                    WHERE i.item_id=? AND j.owner_id=?""", (item_id, owner_id)).fetchone()
                return self._analysis_item(row) if row else None
            row = db.execute("SELECT * FROM memory_analysis_items WHERE item_id=?", (item_id,)).fetchone()
        return self._analysis_item(row)

    def create_processing_step(self, message_id: str, kind: str, status: str, summary: Optional[str] = None, *, label: Optional[str] = None, logical_sequence: int = 0) -> ProcessingStep:
        """Create or advance one logical step without ever duplicating it.

        The old implementation wrote a fresh row for the terminal event.  A
        stable ``(message_id, kind, logical_sequence)`` identity means SSE
        reconnects and terminal cleanup can safely update the same record.
        """
        aliases = {"done": "completed", "error": "failed", "abort": "interrupted"}
        status = aliases.get(status, status)
        if status not in {"running", "completed", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid processing step status")
        label = label or kind
        sequence = max(0, int(logical_sequence))
        now = _now()
        with self.transaction() as db:
            row = db.execute("SELECT * FROM processing_steps WHERE message_id=? AND kind=? AND logical_sequence=?", (message_id, kind, sequence)).fetchone()
            if row is None:
                step_id = uuid.uuid4().hex
                db.execute("INSERT INTO processing_steps(step_id, message_id, kind, logical_sequence, label, status, summary, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (step_id, message_id, kind, sequence, label, status, (summary or "")[:500] or None, now, now if status != "running" else None))
                row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
            elif row["status"] == "running" and status != "running":
                db.execute("UPDATE processing_steps SET label=?, status=?, summary=?, completed_at=? WHERE step_id=?", (label, status, (summary or "")[:500] or None, now, row["step_id"]))
                row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (row["step_id"],)).fetchone()
            elif row["status"] == "running" and summary:
                db.execute("UPDATE processing_steps SET label=?, summary=? WHERE step_id=?", (label, summary[:500], row["step_id"]))
                row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (row["step_id"],)).fetchone()
        return ProcessingStep(row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"], _dt(row["started_at"]), _dt(row["completed_at"]))

    def finalize_processing_steps(self, message_id: str, *, status: str = "failed", summary: Optional[str] = None) -> int:
        """Move all residual running steps to a real terminal state."""
        status = {"error": "failed", "abort": "interrupted", "done": "completed"}.get(status, status)
        if status not in {"completed", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid processing step status")
        with self.transaction() as db:
            result = db.execute("UPDATE processing_steps SET status=?, summary=COALESCE(?, summary), completed_at=? WHERE message_id=? AND status='running'", (status, (summary or "")[:500] or None, _now(), message_id))
        return result.rowcount

    def update_processing_step(self, step_id: str, status: str, summary: Optional[str] = None, *, label: Optional[str] = None) -> Optional[ProcessingStep]:
        """Explicit step-id update seam for stream reconnect/cleanup callers."""
        aliases = {"done": "completed", "error": "failed", "abort": "interrupted"}
        status = aliases.get(status, status)
        if status not in {"running", "completed", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid processing step status")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
            if not row:
                return None
            if row["status"] != "running" and status == "running":
                return ProcessingStep(row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"], _dt(row["started_at"]), _dt(row["completed_at"]))
            db.execute("UPDATE processing_steps SET status=?, label=?, summary=?, completed_at=? WHERE step_id=?", (status, label or row["label"], (summary or row["summary"] or "")[:500] or None, _now() if status != "running" else None, step_id))
            row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
        return ProcessingStep(row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"], _dt(row["started_at"]), _dt(row["completed_at"]))

    def list_processing_steps(self, message_id: str, owner_id: str) -> list[ProcessingStep]:
        with self.connection() as db:
            rows = db.execute("SELECT s.* FROM processing_steps s JOIN messages m ON m.message_id=s.message_id WHERE s.message_id=? AND m.owner_id=? ORDER BY s.started_at, s.logical_sequence", (message_id, owner_id)).fetchall()
        return [ProcessingStep(row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"], _dt(row["started_at"]), _dt(row["completed_at"])) for row in rows]


SQLiteMemoryRepository = MemoryRepository
