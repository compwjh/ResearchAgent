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

SCHEMA_VERSION = 1
OWNER_ID = os.getenv("MEMORY_OWNER_ID", "local-user")
_write_lock = threading.RLock()


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
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS projects (
                        project_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                        name TEXT NOT NULL, instructions TEXT, status TEXT NOT NULL DEFAULT 'active',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(owner_id, name)
                    );
                    CREATE TABLE IF NOT EXISTS conversations (
                        conversation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                        project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                        title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
                        memory_history_policy TEXT NOT NULL DEFAULT 'from_binding',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated
                        ON conversations(owner_id, updated_at DESC, conversation_id DESC);
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                        owner_id TEXT NOT NULL, parent_message_id TEXT, role TEXT NOT NULL,
                        content TEXT NOT NULL, status TEXT NOT NULL, model TEXT, mode TEXT,
                        created_at TEXT NOT NULL, completed_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                        ON messages(conversation_id, created_at DESC, message_id DESC);
                    CREATE TABLE IF NOT EXISTS memories (
                        memory_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, scope TEXT NOT NULL,
                        project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE,
                        category TEXT NOT NULL, statement TEXT NOT NULL, source_kind TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active', confidence REAL NOT NULL,
                        supersedes_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        last_used_at TEXT,
                        CHECK ((scope='project' AND project_id IS NOT NULL) OR (scope='global' AND project_id IS NULL))
                    );
                    CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(owner_id, project_id, status);
                    CREATE TABLE IF NOT EXISTS memory_evidence (
                        memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
                        conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL,
                        message_id TEXT, evidence_type TEXT NOT NULL, excerpt TEXT
                    );
                    CREATE TABLE IF NOT EXISTS processing_steps (
                        step_id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
                        kind TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL,
                        summary TEXT, started_at TEXT NOT NULL, completed_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_steps_message ON processing_steps(message_id, started_at);
                    INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (1, '""" + _now() + """');
                    """
                )
        finally:
            connection.close()

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        return Project(row["project_id"], row["owner_id"], row["name"], row["instructions"], row["status"], _dt(row["created_at"]), _dt(row["updated_at"]))

    @staticmethod
    def _conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(row["conversation_id"], row["owner_id"], row["project_id"], row["title"], row["status"], row["memory_history_policy"], _dt(row["created_at"]), _dt(row["updated_at"]))

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
        if project_id and not self.get_project(project_id, owner_id):
            raise LookupError("project not found")
        now, conversation_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO conversations VALUES (?, ?, ?, ?, 'active', ?, ?, ?)", (conversation_id, owner_id, project_id, title.strip()[:200], memory_history_policy, now, now))
        return self.get_conversation(conversation_id, owner_id)

    def create_conversation_messages(self, owner_id: str, content: str, project_id: Optional[str], model: Optional[str], mode: Optional[str]) -> tuple[Conversation, Message, Message]:
        """Atomically create a first conversation, user message and assistant placeholder."""
        if project_id and not self.get_project(project_id, owner_id):
            raise LookupError("project not found")
        now, conversation_id, user_id, assistant_id = _now(), uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO conversations VALUES (?, ?, ?, ?, 'active', 'from_binding', ?, ?)", (conversation_id, owner_id, project_id, content[:80], now, now))
            db.execute("INSERT INTO messages VALUES (?, ?, ?, NULL, 'user', ?, 'completed', ?, ?, ?, ?)", (user_id, conversation_id, owner_id, content, model, mode, now, now))
            db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, 'assistant', '', 'pending', ?, ?, ?, NULL)", (assistant_id, conversation_id, owner_id, user_id, model, mode, now))
        return self.get_conversation(conversation_id, owner_id), self.get_message(user_id, owner_id), self.get_message(assistant_id, owner_id)

    def get_conversation(self, conversation_id: str, owner_id: str) -> Optional[Conversation]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversations WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (conversation_id, owner_id)).fetchone()
        return self._conversation(row) if row else None

    def update_conversation(self, conversation_id: str, owner_id: str, **changes) -> Optional[Conversation]:
        allowed = {"title", "project_id", "status", "memory_history_policy"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "project_id" in values and values["project_id"] and not self.get_project(values["project_id"], owner_id):
            raise LookupError("project not found")
        if not values:
            return self.get_conversation(conversation_id, owner_id)
        values["updated_at"] = _now()
        assignments = ", ".join(f"{key}=?" for key in values)
        with self.transaction() as db:
            result = db.execute(f"UPDATE conversations SET {assignments} WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (*values.values(), conversation_id, owner_id))
            if result.rowcount == 0:
                return None
        return self.get_conversation(conversation_id, owner_id)

    def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        with self.transaction() as db:
            result = db.execute("UPDATE conversations SET status='deleted', updated_at=? WHERE conversation_id=? AND owner_id=?", (_now(), conversation_id, owner_id))
        return result.rowcount > 0

    def list_conversations(self, owner_id: str, project_id: Optional[str] = None, cursor: Optional[str] = None, limit: int = 20) -> tuple[list[Conversation], Optional[str]]:
        limit = max(1, min(int(limit), 100)); params: list[object] = [owner_id]; clause = ""
        if project_id is None:
            clause += " AND project_id IS NULL"
        else:
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

    def create_memory(self, owner_id: str, scope: str, project_id: Optional[str], category: str, statement: str, source_kind: str, confidence: float, *, status: str = "active", supersedes_id: Optional[str] = None) -> MemoryRecord:
        if scope != "project" or not project_id or not self.get_project(project_id, owner_id): raise ValueError("only existing project memories are supported")
        if not statement.strip() or not 0 <= float(confidence) <= 1: raise ValueError("invalid memory")
        now, memory_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (memory_id, owner_id, scope, project_id, category, statement.strip(), source_kind, status, float(confidence), supersedes_id, now, now, None))
        return self.get_memory(memory_id, owner_id)

    def get_memory(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        with self.connection() as db: row = db.execute("SELECT * FROM memories WHERE memory_id=? AND owner_id=?", (memory_id, owner_id)).fetchone()
        return self._memory(row) if row else None

    def list_memories(self, owner_id: str, project_id: Optional[str] = None, *, status: str = "active") -> list[MemoryRecord]:
        params: list[object] = [owner_id, status]; clause = " AND scope='project'"
        if project_id is None: clause += " AND project_id IS NULL"
        else: clause += " AND project_id=?"; params.append(project_id)
        with self.connection() as db: rows = db.execute(f"SELECT * FROM memories WHERE owner_id=? AND status=?{clause} ORDER BY updated_at DESC, memory_id DESC", params).fetchall()
        return [self._memory(row) for row in rows]

    def mark_memory_used(self, memory_id: str, owner_id: str) -> Optional[MemoryRecord]:
        with self.transaction() as db:
            db.execute("UPDATE memories SET last_used_at=?, updated_at=? WHERE memory_id=? AND owner_id=?", (_now(), _now(), memory_id, owner_id))
        return self.get_memory(memory_id, owner_id)

    def create_memory_evidence(self, memory_id: str, conversation_id: Optional[str], message_id: Optional[str], evidence_type: str, excerpt: Optional[str]) -> None:
        with self.transaction() as db: db.execute("INSERT INTO memory_evidence VALUES (?, ?, ?, ?, ?)", (memory_id, conversation_id, message_id, evidence_type, (excerpt or "")[:500] or None))

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
