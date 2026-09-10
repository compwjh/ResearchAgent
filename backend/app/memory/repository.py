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
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from backend.app.platform.config import BASE_DIR
from .models import Conversation, MemoryEvidence, MemoryRecord, Message, ProcessingStep, Project

SCHEMA_VERSION = 2
OWNER_ID = os.getenv("MEMORY_OWNER_ID", "local-user")
_write_lock = threading.RLock()

MEMORY_SCOPES = {"global", "project"}
MEMORY_CATEGORIES = {"user_preference", "stable_fact", "project_rule", "capability_method"}
MEMORY_SOURCE_KINDS = {"explicit", "repeated", "verified_failure", "manual"}
MEMORY_STATUSES = {"candidate", "active", "superseded", "disabled", "deleted"}
MEMORY_HISTORY_POLICIES = {"from_binding", "include_prior_history"}


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
                connection.execute("COMMIT")
        except Exception as error:
            connection.rollback()
            raise RuntimeError("memory schema migration failed; startup is fail-closed") from error
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
                kind TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL,
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
    def _project(row: sqlite3.Row) -> Project:
        return Project(row["project_id"], row["owner_id"], row["name"], row["instructions"], row["status"], _dt(row["created_at"]), _dt(row["updated_at"]))

    @staticmethod
    def _conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(row["conversation_id"], row["owner_id"], row["project_id"], row["title"], row["status"], row["memory_history_policy"], _dt(row["created_at"]), _dt(row["updated_at"]), _dt(row["memory_binding_at"]), row["memory_binding_message_id"])

    @staticmethod
    def _message(row: sqlite3.Row) -> Message:
        return Message(row["message_id"], row["conversation_id"], row["owner_id"], row["parent_message_id"], row["role"], row["content"], row["status"], row["model"], row["mode"], _dt(row["created_at"]), _dt(row["completed_at"]))

    @staticmethod
    def _memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(row["memory_id"], row["owner_id"], row["scope"], row["project_id"], row["category"], row["statement"], row["source_kind"], row["status"], float(row["confidence"]), row["supersedes_id"], _dt(row["created_at"]), _dt(row["updated_at"]), _dt(row["last_used_at"]))

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
            at, item_id = decode_cursor(cursor, "projects")
            clause = " AND (updated_at < ? OR (updated_at = ? AND project_id < ?))"
            params.extend([at, at, item_id])
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM projects WHERE owner_id=? AND status!='deleted'{clause} ORDER BY updated_at DESC, project_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        page = rows[:limit]
        next_cursor = encode_cursor("projects", page[-1]["updated_at"], page[-1]["project_id"]) if len(rows) > limit else None
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

    def list_conversations(self, owner_id: str, project_id: Optional[str] = None, cursor: Optional[str] = None, limit: int = 20) -> tuple[list[Conversation], Optional[str]]:
        limit = max(1, min(int(limit), 100)); params: list[object] = [owner_id]; clause = ""
        if project_id is None:
            clause += " AND project_id IS NULL"
        else:
            if not self.get_project(project_id, owner_id):
                raise LookupError("project not found")
            clause += " AND project_id=?"; params.append(project_id)
        if cursor:
            at, item_id = decode_cursor(cursor, "conversations"); clause += " AND (updated_at < ? OR (updated_at = ? AND conversation_id < ?))"; params.extend([at, at, item_id])
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM conversations WHERE owner_id=? AND status!='deleted'{clause} ORDER BY updated_at DESC, conversation_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        page = rows[:limit]; next_cursor = encode_cursor("conversations", page[-1]["updated_at"], page[-1]["conversation_id"]) if len(rows) > limit else None
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

    def create_memory(self, owner_id: str, scope: str, project_id: Optional[str], category: str, statement: str, source_kind: str, confidence: float, *, status: str = "active", supersedes_id: Optional[str] = None) -> MemoryRecord:
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

    def create_memory_evidence(self, memory_id: str, conversation_id: Optional[str], message_id: Optional[str], evidence_type: str, excerpt: Optional[str]) -> None:
        if evidence_type not in {"user_statement", "repeated_sessions", "tool_failure", "manual"}:
            raise ValueError("invalid evidence type")
        with self.transaction() as db:
            memory_row = db.execute("SELECT owner_id, scope, project_id FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
            if not memory_row:
                raise LookupError("memory not found")
            conversation_row = None
            if conversation_id:
                conversation_row = db.execute("SELECT owner_id, project_id FROM conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
                if not conversation_row or conversation_row["owner_id"] != memory_row["owner_id"]:
                    raise LookupError("conversation not found")
                if memory_row["scope"] == "project" and conversation_row["project_id"] != memory_row["project_id"]:
                    raise ValueError("memory evidence project mismatch")
            if message_id:
                message_row = db.execute("""SELECT m.owner_id, m.conversation_id, c.project_id
                    FROM messages m JOIN conversations c ON c.conversation_id=m.conversation_id
                    WHERE m.message_id=?""", (message_id,)).fetchone()
                if not message_row or message_row["owner_id"] != memory_row["owner_id"] or (conversation_id and message_row["conversation_id"] != conversation_id):
                    raise LookupError("message not found")
                if memory_row["scope"] == "project" and message_row["project_id"] != memory_row["project_id"]:
                    raise ValueError("memory evidence project mismatch")
            db.execute("INSERT INTO memory_evidence VALUES (?, ?, ?, ?, ?)", (memory_id, conversation_id, message_id, evidence_type, (excerpt or "")[:500] or None))

    def list_memory_evidence(self, memory_id: str, owner_id: str) -> list[MemoryEvidence]:
        with self.connection() as db:
            rows = db.execute("SELECT e.* FROM memory_evidence e JOIN memories m ON m.memory_id=e.memory_id WHERE e.memory_id=? AND m.owner_id=?", (memory_id, owner_id)).fetchall()
        return [MemoryEvidence(row["memory_id"], row["conversation_id"], row["message_id"], row["evidence_type"], row["excerpt"]) for row in rows]

    def create_processing_step(self, message_id: str, kind: str, status: str, summary: Optional[str] = None, *, label: Optional[str] = None) -> ProcessingStep:
        now, step_id = _now(), uuid.uuid4().hex; label = label or kind
        with self.transaction() as db: db.execute("INSERT INTO processing_steps VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (step_id, message_id, kind, label, status, summary, now, now if status != "running" else None))
        with self.connection() as db: row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
        return ProcessingStep(row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"], _dt(row["started_at"]), _dt(row["completed_at"]))

    def list_processing_steps(self, message_id: str, owner_id: str) -> list[ProcessingStep]:
        with self.connection() as db:
            rows = db.execute("SELECT s.* FROM processing_steps s JOIN messages m ON m.message_id=s.message_id WHERE s.message_id=? AND m.owner_id=? ORDER BY s.started_at", (message_id, owner_id)).fetchall()
        return [ProcessingStep(row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"], _dt(row["started_at"]), _dt(row["completed_at"])) for row in rows]


SQLiteMemoryRepository = MemoryRepository
