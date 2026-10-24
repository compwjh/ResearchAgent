"""SQLite persistence for projects, conversations and project memory.

This database is deliberately independent from paper, article and knowledge-base
stores.  A repository opens short-lived connections so streaming requests do not
hold a connection/transaction while waiting for a model.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from backend.app.chat.application.token_budget import chars_for_tokens
from backend.app.platform.config import BASE_DIR, MEMORY_ANALYSIS_MODEL

from .markdown_store import MarkdownMemoryStore
from .migration import SCHEMA_VERSION, create_baseline_schema, current_schema_version, record_schema_version
from .models import (
    Conversation,
    ConversationSummary,
    EvolutionCheckpoint,
    MemoryAnalysisItem,
    MemoryAnalysisJob,
    Message,
    ProcessingStep,
    Project,
    RawEvent,
    SkillImprovementProposal,
    SystemRule,
)
from .preserve import preserve_legacy_owner_data

# SCHEMA_VERSION 现由 ``migration`` 定义（重置后的新基线，旧 v1→v7 迁移链已移除）。
__all__ = ["SCHEMA_VERSION"]

EVOLUTION_LEASE_SECONDS = 300
OWNER_ID = os.getenv("MEMORY_OWNER_ID", "local-user")
_write_lock = threading.RLock()

MEMORY_SCOPES = {"global", "project"}
# 注：``MEMORY_CATEGORIES`` / ``MEMORY_SOURCE_KINDS`` / ``MEMORY_STATUSES`` 随
# ``memories`` 表停用一并移除（长期记忆改由 MD 承载，见 spec-038）。
MEMORY_HISTORY_POLICIES = {"from_binding", "include_prior_history"}
ANALYSIS_STATUSES = {"pending", "running", "completed", "partial", "failed"}
ANALYSIS_DECISIONS = {"auto_saved", "pending_confirmation", "duplicate", "superseded", "ignored", "failed"}
SKILL_PROPOSAL_STATUSES = {"proposed", "accepted", "rejected", "applied"}
_PROCESSING_DETAIL_MAX_CHARS = 4000
_PROCESSING_DETAIL_BLOCKED = {"prompt", "cot", "reasoning", "credential", "password", "secret", "token", "authorization", "cookie", "api_key", "url"}


def _sanitize_processing_detail_json(value: Optional[str]) -> Optional[str]:
    """Keep processing projections bounded and free of sensitive fields."""
    if value is None:
        return None
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return None

    def clean(item, depth=0):
        if depth > 3:
            return None
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                if any(blocked in str(key).casefold() for blocked in _PROCESSING_DETAIL_BLOCKED):
                    continue
                safe = clean(child, depth + 1)
                if safe is not None:
                    result[str(key)[:80]] = safe
            return result
        if isinstance(item, list):
            return [clean(child, depth + 1) for child in item[:32]]
        if isinstance(item, (str, int, float, bool)):
            return item[:500] if isinstance(item, str) else item
        return None

    cleaned = clean(parsed)
    if cleaned is None:
        return None
    encoded = json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
    return encoded if len(encoded) <= _PROCESSING_DETAIL_MAX_CHARS else '{"truncated":true}'


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
        raise ValueError("invalid cursor") from None


@dataclass(frozen=True)
class ConversationSegment:
    """One append-only, non-overlapping compaction window of a conversation."""

    segment_id: str
    owner_id: str
    conversation_id: str
    project_id: Optional[str]
    seq: int
    from_message_id: str
    to_message_id: str
    char_count: int
    est_tokens: int
    generator: str
    content_hash: str
    summary_text: str
    created_at: datetime


@dataclass(frozen=True)
class ActiveSkill:
    """Spec032.1 Task10: the one sticky Skill of a conversation.

    Kept in its own table (never on the frozen ``conversations`` row) so the
    legacy schema and its ``Conversation`` dataclass stay untouched."""

    conversation_id: str
    owner_id: str
    skill_name: str
    updated_at: datetime


@dataclass(frozen=True)
class CompactionJob:
    """A background conversation-compaction job; at most one non-terminal
    job per conversation is enforced by a partial unique index."""

    job_id: str
    owner_id: str
    conversation_id: str
    status: str
    trigger: str
    est_tokens_before: Optional[int]
    est_tokens_after: Optional[int]
    error: Optional[str]
    created_at: datetime
    finished_at: Optional[datetime]


class MemoryRepository:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a short-lived connection that is closed on exit.

        ``sqlite3.Connection.__exit__`` only ends the transaction, it never
        closes the handle, so returning a bare connection leaked one file
        handle per call (all ``with self.connection()`` reads) and left WAL
        side-files behind, breaking temp-directory cleanup.
        """
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.database_path), timeout=5.0, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            with _write_lock, self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.execute("COMMIT")
        except Exception:
            # ``self.connection()`` closes the handle, but a rollback is still
            # required to release the writer lock held by BEGIN IMMEDIATE.
            # Inside the ``with`` this is normally a no-op (sqlite3.__exit__
            # already rolled back); it only does real work if the caller
            # swallows GeneratorExit.
            with contextlib.suppress(sqlite3.ProgrammingError):
                connection.rollback()
            raise

    def initialize(self) -> None:
        """创建/校验记忆库 schema（spec-038 新基线）。

        旧实现维护 v1→v7 的增量迁移链（约 800 行，含补丁与 writable_schema 修复），
        已按 spec-038 决策整体移除：无生产数据、可删库重建，且 L1 记忆真相源已迁到
        Markdown 文件。现在只做两件事：

        1. 在新库（或已重建的库）上直接建出基线表（``migration.create_baseline_schema``）；
        2. 校验 ``schema_version``：**低于**基线的旧库残留一律 fail-closed，要求重建。

        数据保全（旧 ``system_rules`` 内容写入 ``USER.md``）在删表**之前**由
        ``preserve_legacy_owner_data`` 完成，见 ``memory/preserve.py``。

        单事务：DDL 与版本写入在同一 ``BEGIN IMMEDIATE`` 中，失败整体回滚。
        """
        try:
            with self.connection() as connection, _write_lock:
                # 先做数据保全：旧库里的 system_rules 内容需要在建表/重建前搬进 USER.md。
                preserve_legacy_owner_data(connection)

                connection.execute("BEGIN IMMEDIATE")
                create_baseline_schema(connection, OWNER_ID)
                current = current_schema_version(connection)
                if current > SCHEMA_VERSION:
                    raise RuntimeError(f"unsupported memory schema version: {current}")
                if current != 0 and current < SCHEMA_VERSION:
                    # 新基线建立前的老库残留（v1..v7）：拒绝在半旧 schema 上写入。
                    raise RuntimeError(f"legacy memory schema version {current} is no longer supported; rebuild required")
                record_schema_version(connection, SCHEMA_VERSION, _now())
                connection.execute("COMMIT")
        except Exception as error:
            # Rollback still matters for the writer lock held by BEGIN
            # IMMEDIATE; the handle is closed by ``self.connection()``.  A
            # connection closed after its own rollback raises
            # ProgrammingError, which must not mask the original failure.
            with contextlib.suppress(sqlite3.ProgrammingError, UnboundLocalError):
                connection.rollback()
            raise SystemRuleUnavailableError("memory schema migration failed; startup is fail-closed") from error

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
        return Conversation(row["conversation_id"], row["owner_id"], row["project_id"], row["title"], row["status"], row["memory_history_policy"], _dt(row["created_at"]), _dt(row["updated_at"]), _dt(row["memory_binding_at"]), row["memory_binding_message_id"], row["reasoning_effort"] if "reasoning_effort" in row.keys() else "medium")

    @staticmethod
    def _message(row: sqlite3.Row) -> Message:
        return Message(row["message_id"], row["conversation_id"], row["owner_id"], row["parent_message_id"], row["role"], row["content"], row["status"], row["model"], row["mode"], _dt(row["created_at"]), _dt(row["completed_at"]), row["reasoning_content"] if "reasoning_content" in row.keys() else None, row["reasoning_status"] if "reasoning_status" in row.keys() else None, _dt(row["reasoning_started_at"]) if "reasoning_started_at" in row.keys() else None, _dt(row["reasoning_completed_at"]) if "reasoning_completed_at" in row.keys() else None, _dt(row["first_reasoning_at"]) if "first_reasoning_at" in row.keys() else None, _dt(row["first_answer_token_at"]) if "first_answer_token_at" in row.keys() else None, bool(row["reasoning_truncated"]) if "reasoning_truncated" in row.keys() else False, int(row["reasoning_chars"] or 0) if "reasoning_chars" in row.keys() else 0, int(row["last_event_seq"] or 0) if "last_event_seq" in row.keys() else 0)

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

    # ------------------------------------------------------------------ 方法卡
    # spec-038 决策：``capability_methods`` 语义已并入 MD 笔记（``MEMORY.md`` /
    # ``projects/<id>.md``），``memories`` / ``memory_evidence`` 表随之停用。此处
    # 的 create/list/failure 三个方法与 ``_validate_capability_evidence`` 只服务于
    # 已删除的表，按「禁止重复实现」原则整体移除；能力笔记的写入统一走
    # ``MarkdownMemoryStore.append_memory``。
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
            # spec-038：``memories`` 表已停用，原「来源必须是 capability method」的
            # 校验不再适用。``source_memory_id`` 保留为 MD 侧条目的弱引用。
            if not isinstance(source_memory_id, str) or not source_memory_id.strip():
                raise ValueError("invalid proposal source memory id")
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

    # ------------------------------------------------------------ 全局用户画像
    # spec-038 P1：``system_rules`` 表已停用，全局用户画像（原系统规则 content）
    # 的真相源是 ``data/memory/USER.md``。以下三个方法保留原有公开签名与异常语义，
    # 但底层改为读写 Markdown 文件，绝不再触碰已删除的表。
    #
    # ``enabled`` 在 MD 模型中不再有意义（USER.md 存在即生效），为兼容既有调用方与
    # 前端契约而保留：内容非空即视为 enabled=True，空文件视 False。

    @staticmethod
    def _user_memory_store() -> MarkdownMemoryStore:
        """构造默认 MD store；独立成方法以便测试替换。"""
        return MarkdownMemoryStore()

    def _read_user_memory(self) -> str:
        """读取 USER.md；读取失败一律 fail-closed 为 SYSTEM_RULE_UNAVAILABLE。"""
        try:
            return self._user_memory_store().read_user().strip()
        except Exception as error:
            raise SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE") from error

    def get_system_rule(self, owner_id: str) -> SystemRule:
        """读取全局用户画像（USER.md），语义与旧的 owner-scoped system rule 对齐。"""
        content = self._read_user_memory()
        return SystemRule(owner_id, content, bool(content), datetime.now(timezone.utc))

    def upsert_system_rule(self, owner_id: str, content: str, enabled: bool) -> SystemRule:
        """整体写入 USER.md（原子替换）；校验规则沿用旧实现。"""
        if not isinstance(content, str) or len(content) > 12000:
            raise ValueError("system rule content must be at most 12000 Unicode characters")
        value = content.strip()
        if enabled and not value:
            raise ValueError("system rule cannot be enabled with empty content")
        try:
            self._user_memory_store().write_user(value)
        except ValueError:
            raise
        except Exception as error:
            raise SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE") from error
        return self.get_system_rule(owner_id)

    def set_system_rule_enabled(self, owner_id: str, enabled: bool) -> SystemRule:
        """MD 模型下 enabled 由「内容是否为空」决定；禁用等价于清空。"""
        current = self.get_system_rule(owner_id)
        if enabled and not current.content:
            raise ValueError("system rule cannot be enabled with empty content")
        if not enabled:
            return self.upsert_system_rule(owner_id, "", False)
        return self.upsert_system_rule(owner_id, current.content, True)

    def clear_system_rule(self, owner_id: str) -> None:
        """清空 USER.md（保留空文件，与旧的 content=''/enabled=0 语义等价）。"""
        try:
            self._user_memory_store().write_user("")
        except Exception as error:
            raise SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE") from error

    def get_conversation_active_skill(self, conversation_id: str, owner_id: str) -> Optional[ActiveSkill]:
        """Read the sticky Skill of one conversation (owner-scoped), if any.

        Advisory state: a corrupt/unreadable row degrades to ``None`` (no
        sticky skill) instead of breaking the conversation.
        """
        try:
            with self.connection() as db:
                row = db.execute(
                    "SELECT conversation_id, owner_id, skill_name, updated_at FROM conversation_active_skill"
                    " WHERE conversation_id=? AND owner_id=?",
                    (conversation_id, owner_id),
                ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        try:
            return ActiveSkill(
                row["conversation_id"], row["owner_id"], row["skill_name"], _dt(row["updated_at"]),
            )
        except Exception:
            return None

    def set_conversation_active_skill(self, conversation_id: str, owner_id: str, skill_name: str) -> None:
        """Activate (or switch) the sticky Skill of a conversation."""
        name = (skill_name or "").strip()
        if not name:
            raise ValueError("active skill name must not be empty")
        try:
            with self.transaction() as db:
                db.execute(
                    """INSERT INTO conversation_active_skill(conversation_id, owner_id, skill_name, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(conversation_id) DO UPDATE SET
                            owner_id=excluded.owner_id,
                            skill_name=excluded.skill_name,
                            updated_at=excluded.updated_at""",
                    (conversation_id, owner_id, name, _now()),
                )
        except ValueError:
            raise
        except Exception as error:
            raise SystemRuleUnavailableError("SKILL_STICKINESS_UNAVAILABLE") from error

    def clear_conversation_active_skill(self, conversation_id: str, owner_id: str) -> None:
        """Drop the sticky Skill (explicit exit or an unusable skill). Idempotent."""
        try:
            with self.transaction() as db:
                db.execute(
                    "DELETE FROM conversation_active_skill WHERE conversation_id=? AND owner_id=?",
                    (conversation_id, owner_id),
                )
        except Exception as error:
            raise SystemRuleUnavailableError("SKILL_STICKINESS_UNAVAILABLE") from error

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
            if not values["name"] or len(values["name"]) > 120:
                raise ValueError("invalid project name")
        if not values:
            return self.get_project(project_id, owner_id)
        values["updated_at"] = _now()
        try:
            with self.transaction() as db:
                result = db.execute(f"UPDATE projects SET {', '.join(f'{key}=?' for key in values)} WHERE project_id=? AND owner_id=? AND status!='deleted'", (*values.values(), project_id, owner_id))
                if result.rowcount == 0:
                    return None
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

    def get_last_reasoning_effort(self, owner_id: str) -> str:
        with self.connection() as db:
            row = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
        return str(row["last_reasoning_effort"] if row else "xhigh")

    def set_last_reasoning_effort(self, owner_id: str, effort: str) -> str:
        if effort not in {"off", "low", "medium", "high", "xhigh"}:
            raise ValueError("invalid reasoning effort")
        now = _now()
        with self.transaction() as db:
            current = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
            if current and current["last_reasoning_effort"] == effort:
                return effort
            db.execute("INSERT INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at) VALUES (?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET last_reasoning_effort=excluded.last_reasoning_effort, updated_at=excluded.updated_at", (owner_id, effort, now))
        return effort

    def create_conversation(self, owner_id: str, project_id: Optional[str] = None, title: str = "", memory_history_policy: str = "from_binding", reasoning_effort: Optional[str] = None, *, conversation_id: Optional[str] = None) -> Conversation:
        if memory_history_policy not in MEMORY_HISTORY_POLICIES:
            raise ValueError("invalid memory history policy")
        if project_id:
            project = self.get_project(project_id, owner_id)
            if not project:
                raise LookupError("project not found")
            if project.status != "active":
                raise ValueError("project is not active")
        now, conversation_id = _now(), conversation_id or uuid.uuid4().hex
        with self.transaction() as db:
            preference = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
            selected_effort = reasoning_effort or (str(preference["last_reasoning_effort"]) if preference else "xhigh")
            if selected_effort not in {"off", "low", "medium", "high", "xhigh"}:
                raise ValueError("invalid reasoning effort")
            db.execute("INSERT INTO conversations(conversation_id, owner_id, project_id, title, status, memory_history_policy, created_at, updated_at, memory_binding_at, memory_binding_message_id, reasoning_effort) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, NULL, NULL, ?)", (conversation_id, owner_id, project_id, title.strip()[:200], memory_history_policy, now, now, selected_effort))
        return self.get_conversation(conversation_id, owner_id)

    def create_conversation_messages(self, owner_id: str, content: str, project_id: Optional[str], model: Optional[str], mode: Optional[str], reasoning_effort: Optional[str] = None, *, update_preference: bool = False) -> tuple[Conversation, Message, Message]:
        """Atomically create a first conversation, user message and assistant placeholder."""
        if project_id:
            project = self.get_project(project_id, owner_id)
            if not project:
                raise LookupError("project not found")
            if project.status != "active":
                raise ValueError("project is not active")
        now, conversation_id, user_id, assistant_id = _now(), uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        with self.transaction() as db:
            if reasoning_effort is None:
                preference = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
                reasoning_effort = str(preference["last_reasoning_effort"] if preference else "xhigh")
            if reasoning_effort not in {"off", "low", "medium", "high", "xhigh"}:
                raise ValueError("invalid reasoning effort")
            db.execute("INSERT INTO conversations(conversation_id, owner_id, project_id, title, status, memory_history_policy, created_at, updated_at, memory_binding_at, memory_binding_message_id, reasoning_effort) VALUES (?, ?, ?, ?, 'active', 'from_binding', ?, ?, NULL, NULL, ?)", (conversation_id, owner_id, project_id, content[:80], now, now, reasoning_effort))
            db.execute("INSERT INTO messages(message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, created_at, completed_at) VALUES (?, ?, ?, NULL, 'user', ?, 'completed', ?, ?, ?, ?)", (user_id, conversation_id, owner_id, content, model, mode, now, now))
            db.execute("INSERT INTO messages(message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, created_at, completed_at) VALUES (?, ?, ?, ?, 'assistant', '', 'pending', ?, ?, ?, NULL)", (assistant_id, conversation_id, owner_id, user_id, model, mode, now))
            if update_preference:
                db.execute("INSERT INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at) VALUES (?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET last_reasoning_effort=excluded.last_reasoning_effort, updated_at=excluded.updated_at", (owner_id, reasoning_effort, now))
        return self.get_conversation(conversation_id, owner_id), self.get_message(user_id, owner_id), self.get_message(assistant_id, owner_id)

    def create_message_pair(
        self,
        conversation_id: str,
        owner_id: str,
        content: str,
        *,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        update_preference: bool = False,
    ) -> tuple[Conversation, Message, Message]:
        """Atomically freeze a turn and, when explicit, update its defaults.

        The user/assistant rows and the conversation/preference pair share one
        write transaction.  A preference write failure therefore cannot leave
        a visible message whose next-turn default disagrees with its session.
        """
        allowed_efforts = {"off", "low", "medium", "high", "xhigh"}
        if reasoning_effort is not None and reasoning_effort not in allowed_efforts:
            raise ValueError("invalid reasoning effort")
        now, user_id, assistant_id = _now(), uuid.uuid4().hex, uuid.uuid4().hex
        with self.transaction() as db:
            conversation_row = db.execute(
                "SELECT * FROM conversations WHERE conversation_id=? AND owner_id=? AND status!='deleted'",
                (conversation_id, owner_id),
            ).fetchone()
            if not conversation_row:
                raise LookupError("conversation not found")
            effort = reasoning_effort if reasoning_effort is not None else str(conversation_row["reasoning_effort"])
            if update_preference:
                db.execute(
                    "UPDATE conversations SET reasoning_effort=?, updated_at=? WHERE conversation_id=? AND owner_id=?",
                    (effort, now, conversation_id, owner_id),
                )
                preference = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
                if not preference:
                    db.execute("INSERT INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at) VALUES (?, ?, ?)", (owner_id, effort, now))
                elif preference["last_reasoning_effort"] != effort:
                    db.execute("UPDATE user_chat_preferences SET last_reasoning_effort=?, updated_at=? WHERE owner_id=?", (effort, now, owner_id))
            else:
                db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=? AND owner_id=?", (now, conversation_id, owner_id))
            db.execute("INSERT INTO messages(message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, created_at, completed_at) VALUES (?, ?, ?, NULL, 'user', ?, 'completed', ?, ?, ?, ?)", (user_id, conversation_id, owner_id, content, model, mode, now, now))
            db.execute("INSERT INTO messages(message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, created_at, completed_at) VALUES (?, ?, ?, ?, 'assistant', '', 'pending', ?, ?, ?, NULL)", (assistant_id, conversation_id, owner_id, user_id, model, mode, now))
        # spec-038 P2 收尾接线：成对写入是**生产聊天主链路**（``routes_conversations``）
        # 的写消息入口，必须与 ``create_message`` 一样把两条新消息同步进 L2 索引，
        # 否则 ``session_search`` 在生产上永远搜不到历史消息。两条都要索引：user 有正文，
        # assistant 是 pending 占位（空正文也建行，供后续 ``update_message`` 落定内容时覆盖）。
        # 必须在写事务**之外**调用（索引内部另开 BEGIN IMMEDIATE），且 fail-open。
        self._sync_message_index(user_id)
        self._sync_message_index(assistant_id)
        return self.get_conversation(conversation_id, owner_id), self.get_message(user_id, owner_id), self.get_message(assistant_id, owner_id)

    def update_conversation_reasoning(self, conversation_id: str, owner_id: str, effort: str) -> tuple[Optional[Conversation], str, Optional[datetime]]:
        if effort not in {"off", "low", "medium", "high", "xhigh"}:
            raise ValueError("invalid reasoning effort")
        now = _now()
        with self.transaction() as db:
            current = db.execute("SELECT conversation_id, reasoning_effort, updated_at FROM conversations WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (conversation_id, owner_id)).fetchone()
            if not current:
                return None, effort, None
            preference = db.execute("SELECT last_reasoning_effort, updated_at FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
            if current["reasoning_effort"] != effort:
                db.execute("UPDATE conversations SET reasoning_effort=?, updated_at=? WHERE conversation_id=? AND owner_id=?", (effort, now, conversation_id, owner_id))
            if not preference:
                db.execute("INSERT INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at) VALUES (?, ?, ?)", (owner_id, effort, now))
                returned_at = now
            elif preference["last_reasoning_effort"] != effort:
                db.execute("UPDATE user_chat_preferences SET last_reasoning_effort=?, updated_at=? WHERE owner_id=?", (effort, now, owner_id))
                returned_at = now
            else:
                returned_at = preference["updated_at"]
        return self.get_conversation(conversation_id, owner_id), effort, _dt(returned_at)

    def get_conversation(self, conversation_id: str, owner_id: str) -> Optional[Conversation]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversations WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (conversation_id, owner_id)).fetchone()
        return self._conversation(row) if row else None

    def get_conversation_including_deleted(self, conversation_id: str, owner_id: str) -> Optional[Conversation]:
        """Read binding state for idempotent server-side session recovery.

        Ordinary callers keep using ``get_conversation`` so deleted sessions
        remain invisible.  The map binding bridge needs the tombstone to
        avoid silently reusing a historical request key for a new conversation.
        """
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE conversation_id=? AND owner_id=?",
                (conversation_id, owner_id),
            ).fetchone()
        return self._conversation(row) if row else None

    def update_conversation(self, conversation_id: str, owner_id: str, **changes) -> Optional[Conversation]:
        confirm_move = bool(changes.pop("confirm_move", False))
        allowed = {"title", "project_id", "status", "memory_history_policy", "reasoning_effort"}
        values = {key: value for key, value in changes.items() if key in allowed}
        current = self.get_conversation(conversation_id, owner_id)
        if not current:
            return None
        # ``reasoning_effort`` 是否**有效变更**：key 存在且与当前值不同才算。
        # 无实质变更（no-op）必须既不刷新会话 ``updated_at``，也不动跨会话偏好
        # 时间戳——因为 keyset 分页按 ``updated_at`` 排序，no-op 刷新会让客户端
        # 基于旧键翻页时游标错乱。因此这里用独立布尔量记录，而不是靠 pop key。
        effort_changed = "reasoning_effort" in values and values["reasoning_effort"] != current.reasoning_effort
        requested_reasoning = values.get("reasoning_effort") if effort_changed else None
        if "memory_history_policy" in values and values["memory_history_policy"] not in MEMORY_HISTORY_POLICIES:
            raise ValueError("invalid memory history policy")
        if "reasoning_effort" in values and values["reasoning_effort"] not in {"off", "low", "medium", "high", "xhigh"}:
            raise ValueError("invalid reasoning effort")
        if "reasoning_effort" in values and not effort_changed:
            values.pop("reasoning_effort")
        if not values and requested_reasoning is None:
            # 无任何有效变更：既不改会话行，也不动偏好时间戳。
            return current
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
            # 走到这里说明 values 已被清空：要么本次 patch 无任何字段，要么只有
            # 「与当前值相同的 reasoning_effort」（no-op，已 pop）。两种情形都不得
            # 刷新会话 ``updated_at``；仅当确有跨会话默认 effort 变更时才动偏好行。
            if requested_reasoning is None:
                return current
            now = _now()
            with self.transaction() as db:
                preference = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
                if not preference:
                    db.execute("INSERT INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at) VALUES (?, ?, ?)", (owner_id, requested_reasoning, now))
                elif preference["last_reasoning_effort"] != requested_reasoning:
                    db.execute("UPDATE user_chat_preferences SET last_reasoning_effort=?, updated_at=? WHERE owner_id=?", (requested_reasoning, now, owner_id))
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
            # spec-038：旧实现会在此把「旧项目记忆的证据」与本次会话解绑
            # （``UPDATE memory_evidence``）。``memories`` / ``memory_evidence``
            # 已停用，记忆改由 MD 承载，故该写路径整体移除；会话自身的历史隔离
            # 仍由上方 ``memory_binding_at`` 截止点保证。
            result = db.execute(f"UPDATE conversations SET {assignments} WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (*values.values(), conversation_id, owner_id))
            if result.rowcount == 0:
                return None
            if requested_reasoning is not None:
                # Keep the conversation snapshot and cross-session default in
                # the same transaction for every update entry point.
                preference = db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id=?", (owner_id,)).fetchone()
                if not preference:
                    db.execute("INSERT INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at) VALUES (?, ?, ?)", (owner_id, requested_reasoning, values["updated_at"]))
                elif preference["last_reasoning_effort"] != requested_reasoning:
                    db.execute("UPDATE user_chat_preferences SET last_reasoning_effort=?, updated_at=? WHERE owner_id=?", (requested_reasoning, values["updated_at"], owner_id))
        return self.get_conversation(conversation_id, owner_id)

    def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        with self.transaction() as db:
            result = db.execute("UPDATE conversations SET status='deleted', updated_at=? WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (_now(), conversation_id, owner_id))
            if result.rowcount > 0:
                # Spec032.1 Task10: a soft-deleted conversation must not keep a
                # sticky skill alive (nothing else reads it, but a later
                # restore would silently resurrect it).  The conversations
                # table predates the FK, so clean up explicitly.
                db.execute("DELETE FROM conversation_active_skill WHERE conversation_id=? AND owner_id=?", (conversation_id, owner_id))
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
        limit = max(1, min(int(limit), 100))
        params: list[object] = [owner_id]
        clause = ""
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
            clause += " AND project_id=?"
            params.append(project_id)
        if status is None:
            clause += " AND status!='deleted'"
        else:
            clause += " AND status=?"
            params.append(status)
        # Every list scope gets its own opaque cursor namespace.  In
        # particular, a project cursor must never be accepted by the default
        # or another project's list, even when the status filter is omitted.
        cursor_kind = f"conversations:v3:project={project_id or '*'}:status={status or '*'}:unbound={int(unbound_only)}"
        if cursor:
            at, item_id = decode_cursor(cursor, cursor_kind)
            clause += " AND (updated_at < ? OR (updated_at = ? AND conversation_id < ?))"
            params.extend([at, at, item_id])
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM conversations WHERE owner_id=?{clause} ORDER BY updated_at DESC, conversation_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        page = rows[:limit]
        next_cursor = encode_cursor(cursor_kind, page[-1]["updated_at"], page[-1]["conversation_id"]) if len(rows) > limit else None
        return [self._conversation(row) for row in page], next_cursor

    def _sync_message_index(self, message_id: str) -> None:
        """把一条消息同步进 L2 会话检索索引（spec-038 P2 收尾接线）。

        - **延迟导入** ``session_search``：后者会 import 本模块，顶层互导会成环；
        - 受 ``MEMORY_FTS_ENABLED`` 开关控制（关闭时不动索引也不报错）；
        - **fail-open**：索引失败绝不阻断消息写入（消息是会话真相源），失败只记观测；
        - **显式传入自身 repository**：索引必须落在本实例的 ``database_path`` 上。
          若在此无参构造默认仓储，调用方操作临时库时索引会写进进程默认库
          （``data/memory/memory.sqlite3``），既漏索引又污染真实库。

        必须在写事务**之外**调用：索引内部另开 ``BEGIN IMMEDIATE`` 事务。
        """
        from backend.app.platform import config as platform_config
        from backend.app.platform.observability.safe import safe_call

        if not platform_config.MEMORY_FTS_ENABLED:
            return

        def _index() -> None:
            from .session_search import build_default_index

            build_default_index(repository=self).index_message(message_id)

        safe_call(_index)

    def create_message(self, conversation_id: str, owner_id: str, role: str, content: str, *, status: str = "pending", model: Optional[str] = None, mode: Optional[str] = None, parent_message_id: Optional[str] = None) -> Message:
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        now, message_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO messages(message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (message_id, conversation_id, owner_id, parent_message_id, role, content, status, model, mode, now, now if status in {"completed", "failed", "interrupted"} else None))
            db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (now, conversation_id))
        self._sync_message_index(message_id)
        return self.get_message(message_id, owner_id)

    def create_activity_message(
        self, conversation_id: str, owner_id: str, content: str, *,
        activity_idempotency_key: str, status: str = "pending",
        model: Optional[str] = None, mode: Optional[str] = None,
        parent_message_id: Optional[str] = None,
    ) -> Message:
        """Create or return one assistant activity message for a stable key."""
        if not isinstance(activity_idempotency_key, str) or not activity_idempotency_key.strip() or len(activity_idempotency_key) > 240:
            raise ValueError("invalid activity idempotency key")
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM messages WHERE owner_id=? AND conversation_id=? AND activity_idempotency_key=?", (owner_id, conversation_id, activity_idempotency_key)).fetchone()
            if existing is not None:
                return self._message(existing)
            message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"research-activity:{owner_id}:{conversation_id}:{activity_idempotency_key}").hex
            now = _now()
            db.execute("""INSERT INTO messages(message_id,conversation_id,owner_id,parent_message_id,role,content,status,model,mode,created_at,completed_at,activity_idempotency_key)
                VALUES(?,?,?,?, 'assistant',?,?,?,?,?,?,?)""", (message_id, conversation_id, owner_id, parent_message_id, content, status, model, mode, now, now if status in {"completed", "failed", "interrupted"} else None, activity_idempotency_key))
            row = db.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
        self._sync_message_index(message_id)
        return self._message(row)

    def get_activity_message(self, conversation_id: str, owner_id: str, activity_idempotency_key: str) -> Optional[Message]:
        if not isinstance(activity_idempotency_key, str) or not activity_idempotency_key.strip():
            return None
        with self.connection() as db:
            row = db.execute("SELECT * FROM messages WHERE owner_id=? AND conversation_id=? AND activity_idempotency_key=?", (owner_id, conversation_id, activity_idempotency_key)).fetchone()
        return self._message(row) if row else None

    def create_idempotent_message_pair(
        self, conversation_id: str, owner_id: str, content: str, *,
        idempotency_key: str, model: Optional[str] = None, mode: Optional[str] = None,
    ) -> tuple[Conversation, Message, Message]:
        """Create or replay the durable user/assistant pair used by research intake."""
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 240:
            raise ValueError("invalid idempotency key")
        with self.transaction() as db:
            conversation_row = db.execute("SELECT * FROM conversations WHERE conversation_id=? AND owner_id=? AND status!='deleted'", (conversation_id, owner_id)).fetchone()
            if conversation_row is None:
                raise LookupError("conversation not found")
            user_key, assistant_key = f"{idempotency_key}:user", f"{idempotency_key}:assistant"
            user_row = db.execute("SELECT * FROM messages WHERE owner_id=? AND conversation_id=? AND activity_idempotency_key=?", (owner_id, conversation_id, user_key)).fetchone()
            if user_row is None:
                now = _now()
                user_id = uuid.uuid5(uuid.NAMESPACE_URL, f"research-intake:{owner_id}:{conversation_id}:{user_key}").hex
                db.execute("INSERT INTO messages(message_id,conversation_id,owner_id,parent_message_id,role,content,status,model,mode,created_at,completed_at,activity_idempotency_key) VALUES(?,?,?,NULL,'user',?,?,?,?,?,?,?)", (user_id, conversation_id, owner_id, content, "completed", model, mode, now, now, user_key))
                user_row = db.execute("SELECT * FROM messages WHERE message_id=?", (user_id,)).fetchone()
            assistant_row = db.execute("SELECT * FROM messages WHERE owner_id=? AND conversation_id=? AND activity_idempotency_key=?", (owner_id, conversation_id, assistant_key)).fetchone()
            if assistant_row is None:
                now = _now()
                assistant_id = uuid.uuid5(uuid.NAMESPACE_URL, f"research-intake:{owner_id}:{conversation_id}:{assistant_key}").hex
                db.execute("INSERT INTO messages(message_id,conversation_id,owner_id,parent_message_id,role,content,status,model,mode,created_at,completed_at,activity_idempotency_key) VALUES(?,?,?,?,'assistant','',?,?,?,?,NULL,?)", (assistant_id, conversation_id, owner_id, user_row["message_id"], "pending", model, mode, now, assistant_key))
                assistant_row = db.execute("SELECT * FROM messages WHERE message_id=?", (assistant_id,)).fetchone()
            db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (_now(), conversation_id))
        return self._conversation(conversation_row), self._message(user_row), self._message(assistant_row)

    def get_message(self, message_id: str, owner_id: str) -> Optional[Message]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM messages WHERE message_id=? AND owner_id=?", (message_id, owner_id)).fetchone()
        return self._message(row) if row else None

    def update_message(self, message_id: str, owner_id: str, *, content: Optional[str] = None, status: Optional[str] = None, reasoning_content: Optional[str] = None, reasoning_status: Optional[str] = None, reasoning_started_at: Optional[str] = None, reasoning_completed_at: Optional[str] = None, first_reasoning_at: Optional[str] = None, first_answer_token_at: Optional[str] = None, reasoning_truncated: Optional[bool] = None, reasoning_chars: Optional[int] = None, last_event_seq: Optional[int] = None) -> Optional[Message]:
        values = {}
        if content is not None:
            values["content"] = content
        if status is not None:
            values["status"] = status
            values["completed_at"] = _now() if status in {"completed", "failed", "interrupted"} else None
        for key, value in (
            ("reasoning_content", reasoning_content),
            ("reasoning_status", reasoning_status),
            ("reasoning_started_at", reasoning_started_at),
            ("reasoning_completed_at", reasoning_completed_at),
            ("first_reasoning_at", first_reasoning_at),
            ("first_answer_token_at", first_answer_token_at),
            ("reasoning_truncated", int(reasoning_truncated) if reasoning_truncated is not None else None),
            ("reasoning_chars", reasoning_chars),
            ("last_event_seq", last_event_seq),
        ):
            if value is not None:
                values[key] = value
        if not values:
            return self.get_message(message_id, owner_id)
        with self.transaction() as db:
            assignments = []
            params: list[object] = []
            for key, value in values.items():
                if key == "last_event_seq":
                    assignments.append("last_event_seq=CASE WHEN last_event_seq < ? THEN ? ELSE last_event_seq END")
                    params.extend((value, value))
                else:
                    assignments.append(f"{key}=?")
                    params.append(value)
            result = db.execute(
                f"UPDATE messages SET {', '.join(assignments)} WHERE message_id=? AND owner_id=?"
                + (" AND last_event_seq <= ?" if last_event_seq is not None else ""),
                (*params, message_id, owner_id, *((last_event_seq,) if last_event_seq is not None else ())),
            )
            if result.rowcount == 0:
                return None
        # 仅「内容变更」或「进入终态」才重建检索索引：流式回答期间 update_message
        # 会被高频调用（reasoning/seq 等字段逐帧更新），若每次都 upsert 索引会造成
        # 明显写放大；纯推理/序号字段不进检索索引（spec-038 P2 收尾）。
        if content is not None or (status is not None and status in {"completed", "failed", "interrupted"}):
            self._sync_message_index(message_id)
        return self.get_message(message_id, owner_id)

    def update_message_reasoning(self, message_id: str, owner_id: str, *, content: Optional[str] = None, status: Optional[str] = None, started_at: Optional[str] = None, completed_at: Optional[str] = None, first_reasoning_at: Optional[str] = None, first_answer_token_at: Optional[str] = None, truncated: Optional[bool] = None, chars: Optional[int] = None, last_event_seq: Optional[int] = None) -> Optional[Message]:
        return self.update_message(message_id, owner_id, reasoning_content=content, reasoning_status=status, reasoning_started_at=started_at, reasoning_completed_at=completed_at, first_reasoning_at=first_reasoning_at, first_answer_token_at=first_answer_token_at, reasoning_truncated=truncated, reasoning_chars=chars, last_event_seq=last_event_seq)

    def record_event_seq(self, message_id: str, owner_id: str, event_seq: int, *, terminal_status: Optional[str] = None) -> bool:
        """Persist an event sequence only monotonically and before terminal replay."""
        if int(event_seq) < 1:
            return False
        with self.transaction() as db:
            clause = "last_event_seq < ?"
            params: list[object] = [int(event_seq)]
            if terminal_status not in {"completed", "failed", "interrupted"}:
                clause += " AND status NOT IN ('completed','failed','interrupted')"
            result = db.execute(f"UPDATE messages SET last_event_seq=? WHERE message_id=? AND owner_id=? AND {clause}", (int(event_seq), message_id, owner_id, *params))
        return result.rowcount > 0

    def list_messages(self, conversation_id: str, owner_id: str, *, before: Optional[str] = None, target_chars: int = 4000, limit: int = 50) -> tuple[list[Message], Optional[str]]:
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        target_chars = max(1, min(int(target_chars), 100_000))
        limit = max(1, min(int(limit), 50))
        params: list[object] = [conversation_id, owner_id]
        clause = ""
        if before:
            at, item_id = decode_cursor(before, "messages")
            clause = " AND (created_at < ? OR (created_at = ? AND message_id < ?))"
            params.extend([at, at, item_id])
            with self.connection() as db:
                cursor_row = db.execute("SELECT conversation_id, owner_id, created_at FROM messages WHERE message_id=?", (item_id,)).fetchone()
            if not cursor_row or cursor_row["conversation_id"] != conversation_id or cursor_row["owner_id"] != owner_id or cursor_row["created_at"] != at:
                raise ValueError("invalid cursor")
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM messages WHERE conversation_id=? AND owner_id=?{clause} ORDER BY created_at DESC, message_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        selected = []
        chars = 0
        for row in rows:
            selected.append(self._message(row))
            chars += len(row["content"] or "")
            if chars >= target_chars:
                break
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

    # ------------------------------------------------------------------ 长期记忆
    # spec-038 决策：``memories`` / ``memory_evidence`` 表已停用，长期记忆的真相源
    # 改为 MD 文件（``MEMORY.md`` / ``projects/<id>.md``，见 ``MarkdownMemoryStore``）。
    # 原 create/get/list/update/confirm/delete/undo/mark_used/promote 一族方法只服务于
    # 已删除的表，整体移除；路由层改为读写 ``USER.md``（全局画像）并由 P3 接管其余
    # 记忆的 MD 化，避免出现第二套记忆实现。
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

    # 注：原 ``count_capability_method_evidence`` 依赖已停用的 ``memories`` 表与
    # ``category='capability_method'`` 语义，随方法卡一并移除（能力笔记改由 MD 承载）。
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
            selected.append(item)
            used += len(item.summary_text)
        return selected

    def list_recall_summaries(self, owner_id: str, project_id: Optional[str], *, query: str = "", budget_chars: int = 1500) -> list[ConversationSummary]:
        params: list[object] = [owner_id]
        clause = "c.owner_id=? AND s.status='active'"
        if project_id:
            clause += " AND c.project_id=?"
            params.append(project_id)
        else:
            clause += " AND c.project_id IS NULL"
        with self.connection() as db:
            # 常驻「最近跨会话记忆」候选上限（spec-022 Task04 跨会话召回）。50 → 10：
            # 相关性过滤发生在该 LIMIT 之后，候选集越小越不该把无关历史摘要灌进新会话。
            rows = db.execute(f"SELECT s.* FROM conversation_summaries s JOIN conversations c ON c.conversation_id=s.conversation_id WHERE {clause} ORDER BY s.updated_at DESC LIMIT 10", params).fetchall()
        terms = {part.lower() for part in (query or "").split() if len(part) > 1}
        items = [self._summary(row) for row in rows]
        if terms:
            relevant = [item for item in items if any(term in item.summary_text.lower() for term in terms)]
            items = relevant
        selected, used = [], 0
        for item in items:
            if used + len(item.summary_text) > max(0, int(budget_chars)):
                break
            selected.append(item)
            used += len(item.summary_text)
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

    def append_conversation_segment(
        self,
        conversation_id: str,
        owner_id: str,
        project_id: Optional[str],
        seq: int,
        from_message_id: str,
        to_message_id: str,
        char_count: int,
        est_tokens: int,
        content_hash: str,
        summary_text: str,
        *,
        generator: str = "rule",
    ) -> ConversationSegment:
        """Append a compaction segment (append-only; never UPDATE/DELETE).

        The segment window is caller-controlled; the store only persists it.
        """
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        now, segment_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            db.execute(
                "INSERT INTO conversation_segments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    segment_id, owner_id, conversation_id, project_id, int(seq),
                    from_message_id, to_message_id, int(char_count), int(est_tokens),
                    generator, content_hash, summary_text, now,
                ),
            )
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversation_segments WHERE segment_id=?", (segment_id,)).fetchone()
        return self._segment(row) if row else None

    def list_conversation_segments(self, conversation_id: str, owner_id: str, project_id: Optional[str]) -> list[ConversationSegment]:
        """Return segments for a conversation ordered by seq ascending.

        project_id is matched strictly: when None, only segments with
        project_id IS NULL are returned (unbound conversations).
        """
        if project_id is None:
            clause, params = " AND project_id IS NULL", (conversation_id, owner_id)
        else:
            clause, params = " AND project_id=?", (conversation_id, owner_id, project_id)
        with self.connection() as db:
            rows = db.execute(
                f"SELECT * FROM conversation_segments WHERE conversation_id=? AND owner_id=?{clause} ORDER BY seq ASC",
                params,
            ).fetchall()
        return [self._segment(row) for row in rows]

    def next_segment_start_message(self, conversation_id: str, owner_id: str) -> Optional[str]:
        """Return the message id to start the next segment from.

        - No prior segment: the conversation's earliest message id (ordered by
          (created_at, message_id)), or None when there are no messages.
        - Has prior segment: the message strictly after the last segment's
          to_message_id; None when that is already the last message.
        """
        with self.connection() as db:
            last = db.execute(
                "SELECT to_message_id FROM conversation_segments WHERE conversation_id=? AND owner_id=? ORDER BY seq DESC LIMIT 1",
                (conversation_id, owner_id),
            ).fetchone()
            if last is None:
                row = db.execute(
                    "SELECT message_id FROM messages WHERE conversation_id=? AND owner_id=? ORDER BY created_at ASC, message_id ASC LIMIT 1",
                    (conversation_id, owner_id),
                ).fetchone()
                return row["message_id"] if row else None
            anchor = db.execute(
                "SELECT created_at, message_id FROM messages WHERE message_id=? AND conversation_id=? AND owner_id=?",
                (last["to_message_id"], conversation_id, owner_id),
            ).fetchone()
            if anchor is None:
                row = db.execute(
                    "SELECT message_id FROM messages WHERE conversation_id=? AND owner_id=? ORDER BY created_at ASC, message_id ASC LIMIT 1",
                    (conversation_id, owner_id),
                ).fetchone()
                return row["message_id"] if row else None
            row = db.execute(
                "SELECT message_id FROM messages WHERE conversation_id=? AND owner_id=? "
                "AND (created_at > ? OR (created_at = ? AND message_id > ?)) "
                "ORDER BY created_at ASC, message_id ASC LIMIT 1",
                (conversation_id, owner_id, anchor["created_at"], anchor["created_at"], anchor["message_id"]),
            ).fetchone()
            return row["message_id"] if row else None

    def create_compaction_job(self, conversation_id: str, owner_id: str, *, trigger: str, est_tokens_before: Optional[int] = None) -> Optional[CompactionJob]:
        """Atomically claim a compaction job via the partial unique index.

        INSERTs with status='queued'; a concurrent/duplicate claim collides with
        idx_compaction_job_active (one active job per conversation) and raises
        sqlite3.IntegrityError, which is caught and surfaced as None so the
        caller can respond 409. No read-then-write race is introduced.
        """
        if trigger not in {"auto", "manual"}:
            raise ValueError("invalid compaction trigger")
        if not self.get_conversation(conversation_id, owner_id):
            raise LookupError("conversation not found")
        now, job_id = _now(), uuid.uuid4().hex
        with self.transaction() as db:
            try:
                db.execute(
                    "INSERT INTO conversation_compaction_jobs VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL, ?, NULL)",
                    (job_id, owner_id, conversation_id, trigger, est_tokens_before, now),
                )
            except sqlite3.IntegrityError:
                return None
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversation_compaction_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def get_compaction_job(self, job_id: str, owner_id: str) -> Optional[CompactionJob]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversation_compaction_jobs WHERE job_id=? AND owner_id=?", (job_id, owner_id)).fetchone()
        return self._job(row) if row else None

    def get_latest_compaction_job(self, conversation_id: str, owner_id: str) -> Optional[CompactionJob]:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM conversation_compaction_jobs WHERE conversation_id=? AND owner_id=? ORDER BY created_at DESC, job_id DESC LIMIT 1",
                (conversation_id, owner_id),
            ).fetchone()
        return self._job(row) if row else None

    def finish_compaction_job(self, job_id: str, owner_id: str, *, status: str, est_tokens_after: Optional[int] = None, error: Optional[str] = None) -> Optional[CompactionJob]:
        """Move a job to a terminal state (done/failed) and stamp finished_at."""
        if status not in {"done", "failed"}:
            raise ValueError("invalid compaction job status")
        with self.transaction() as db:
            db.execute(
                "UPDATE conversation_compaction_jobs SET status=?, est_tokens_after=?, error=?, finished_at=? WHERE job_id=? AND owner_id=?",
                (status, est_tokens_after, (error or "")[:500] or None, _now(), job_id, owner_id),
            )
        with self.connection() as db:
            row = db.execute("SELECT * FROM conversation_compaction_jobs WHERE job_id=? AND owner_id=?", (job_id, owner_id)).fetchone()
        return self._job(row) if row else None

    @staticmethod
    def _segment(row: sqlite3.Row) -> ConversationSegment:
        return ConversationSegment(
            row["segment_id"], row["owner_id"], row["conversation_id"], row["project_id"],
            int(row["seq"]), row["from_message_id"], row["to_message_id"],
            int(row["char_count"]), int(row["est_tokens"]), row["generator"],
            row["content_hash"], row["summary_text"], _dt(row["created_at"]),
        )

    @staticmethod
    def _job(row: sqlite3.Row) -> CompactionJob:
        return CompactionJob(
            row["job_id"], row["owner_id"], row["conversation_id"], row["status"], row["trigger"],
            row["est_tokens_before"], row["est_tokens_after"], row["error"],
            _dt(row["created_at"]), _dt(row["finished_at"]),
        )

    # ------------------------------------------------------------------ 召回
    # spec-038：原 ``list_recall_context`` 与 ``create/list_memory_evidence`` 依赖
    # 已停用的 ``memories`` / ``memory_evidence``，随表一并移除。会话装配现由
    # ``MarkdownMemoryStore.load_snapshot`` 提供文件记忆快照（P1 前半段已接线），
    # 其余记忆召回在 P3 以 MD 为真相源重建。
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

    # 注：原 ``create_analysis_memory`` 在写入 ``memory_analysis_items`` 的同时把结果
    # 落到已停用的 ``memories``（含 supersede 与证据）并返回 ``MemoryRecord``。表停用后
    # 该写入路径不具备等价物，按「禁止重复实现」原则移除；分析项本身（审计流水）仍由
    # ``create_memory_analysis_item`` 完整保留。记忆落定改由 MD（P3）负责。

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
        return [self._processing_step_from_row(row) for row in rows]

    # Spec034 Task07 additive processing-tree/projector seam.  These methods
    # intentionally follow the Spec038 repository above instead of restoring
    # the removed v1-v7 migration chain.
    @staticmethod
    def _processing_step_from_row(row: sqlite3.Row) -> ProcessingStep:
        keys = row.keys()
        return ProcessingStep(
            row["step_id"], row["message_id"], row["kind"], row["label"], row["status"], row["summary"],
            _dt(row["started_at"]), _dt(row["completed_at"]),
            row["parent_step_id"] if "parent_step_id" in keys else None,
            (row["node_type"] or "operation") if "node_type" in keys else "operation",
            row["node_key"] if "node_key" in keys else None,
            int(row["display_order"] or 0) if "display_order" in keys else 0,
            row["detail_json"] if "detail_json" in keys else None,
            row["source_event_id"] if "source_event_id" in keys else None,
            row["research_session_id"] if "research_session_id" in keys else None,
            int(row["schema_version"] or 1) if "schema_version" in keys else 1,
        )

    def _validate_processing_parent(self, db: sqlite3.Connection, message_id: str, parent_step_id: Optional[str], *, step_id: Optional[str] = None, node_type: str = "operation", strict_tree: bool = False) -> None:
        if parent_step_id is None:
            if strict_tree and node_type != "phase":
                raise ValueError("research processing tree root must be phase")
            return
        current = parent_step_id
        seen: set[str] = set()
        chain: list[sqlite3.Row] = []
        while current:
            if current in seen or current == step_id:
                raise ValueError("processing step parent cycle")
            seen.add(current)
            row = db.execute("SELECT step_id, message_id, parent_step_id, node_type FROM processing_steps WHERE step_id=?", (current,)).fetchone()
            if row is None or row["message_id"] != message_id:
                raise ValueError("processing step parent must belong to message")
            chain.append(row)
            current = row["parent_step_id"]
        if len(chain) >= 3:
            raise ValueError("processing step tree exceeds three levels")
        if strict_tree:
            expected_chain = ["phase"] if len(chain) == 1 else ["agent", "phase"]
            for row, expected in zip(chain, expected_chain, strict=True):
                actual = str(row["node_type"] or "operation")
                if (expected == "skill_or_tool" and actual not in {"skill", "tool"}) or (expected != "skill_or_tool" and actual != expected):
                    raise ValueError("invalid research processing tree node type")
            expected_child = "agent" if len(chain) == 1 else "skill_or_tool"
            if (expected_child == "agent" and node_type != "agent") or (expected_child == "skill_or_tool" and node_type not in {"skill", "tool"}):
                raise ValueError("invalid research processing tree node type")

    def create_processing_step(self, message_id: str, kind: str, status: str, summary: Optional[str] = None, *, label: Optional[str] = None, logical_sequence: int = 0, parent_step_id: Optional[str] = None, node_type: str = "operation", node_key: Optional[str] = None, display_order: int = 0, detail_json: Optional[str] = None, source_event_id: Optional[str] = None, research_session_id: Optional[str] = None, strict_tree: bool = False) -> ProcessingStep:
        aliases = {"done": "completed", "error": "failed", "abort": "interrupted"}
        status = aliases.get(status, status)
        if status not in {"running", "completed", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid processing step status")
        if node_type not in {"phase", "agent", "skill", "tool", "operation"}:
            raise ValueError("invalid processing step node type")
        if node_key is not None and not str(node_key).strip():
            raise ValueError("processing node_key must not be empty")
        detail_json = _sanitize_processing_detail_json(detail_json)
        label = label or kind
        sequence = max(0, int(logical_sequence))
        now = _now()
        with self.transaction() as db:
            row = None
            if source_event_id:
                row = db.execute("SELECT * FROM processing_steps WHERE source_event_id=?", (source_event_id,)).fetchone()
                if row is not None and row["message_id"] != message_id:
                    raise ValueError("source_event_id belongs to another message")
            if row is None and node_key:
                row = db.execute("SELECT * FROM processing_steps WHERE message_id=? AND node_key=?", (message_id, node_key)).fetchone()
            if row is None and not node_key and not source_event_id:
                row = db.execute("SELECT * FROM processing_steps WHERE message_id=? AND kind=? AND logical_sequence=?", (message_id, kind, sequence)).fetchone()
            if row is None:
                self._validate_processing_parent(db, message_id, parent_step_id, node_type=node_type, strict_tree=strict_tree)
                if node_key or source_event_id:
                    sequence = int(db.execute("SELECT COALESCE(MAX(logical_sequence), -1) + 1 FROM processing_steps WHERE message_id=? AND kind=?", (message_id, kind)).fetchone()[0])
                step_id = uuid.uuid4().hex
                db.execute("""INSERT INTO processing_steps(step_id,message_id,kind,logical_sequence,label,status,summary,started_at,completed_at,parent_step_id,node_type,node_key,display_order,detail_json,source_event_id,research_session_id,schema_version)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,2)""", (step_id, message_id, kind, sequence, label, status, (summary or "")[:500] or None, now, now if status != "running" else None, parent_step_id, node_type, node_key, int(display_order), detail_json, source_event_id, research_session_id))
                row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
            else:
                if strict_tree and row["parent_step_id"] is None and row["node_type"] != "phase":
                    raise ValueError("research processing tree root must be phase")
                if parent_step_id is not None and row["parent_step_id"] != parent_step_id:
                    raise ValueError("processing step parent conflicts with existing node")
                if row["status"] == "running" and status != "running":
                    db.execute("""UPDATE processing_steps SET label=?,status=?,summary=?,completed_at=?,source_event_id=COALESCE(?,source_event_id),detail_json=COALESCE(?,detail_json),research_session_id=COALESCE(?,research_session_id),display_order=?,schema_version=2 WHERE step_id=?""", (label, status, (summary or "")[:500] or None, now, source_event_id, detail_json, research_session_id, int(display_order), row["step_id"]))
                    row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (row["step_id"],)).fetchone()
                elif row["status"] == "running" and (summary or detail_json or source_event_id):
                    db.execute("""UPDATE processing_steps SET label=COALESCE(?,label),summary=COALESCE(?,summary),source_event_id=COALESCE(?,source_event_id),detail_json=COALESCE(?,detail_json),research_session_id=COALESCE(?,research_session_id),display_order=?,schema_version=2 WHERE step_id=?""", (label, (summary or "")[:500] or None, source_event_id, detail_json, research_session_id, int(display_order), row["step_id"]))
                    row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (row["step_id"],)).fetchone()
        return self._processing_step_from_row(row)

    def finalize_processing_steps(self, message_id: str, *, status: str = "failed", summary: Optional[str] = None) -> int:
        status = {"error": "failed", "abort": "interrupted", "done": "completed"}.get(status, status)
        if status not in {"completed", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid processing step status")
        with self.transaction() as db:
            result = db.execute("UPDATE processing_steps SET status=?,summary=COALESCE(?,summary),completed_at=? WHERE message_id=? AND status='running'", (status, (summary or "")[:500] or None, _now(), message_id))
        return result.rowcount

    def update_processing_step(self, step_id: str, status: str, summary: Optional[str] = None, *, label: Optional[str] = None) -> Optional[ProcessingStep]:
        status = {"done": "completed", "error": "failed", "abort": "interrupted"}.get(status, status)
        if status not in {"running", "completed", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid processing step status")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
            if not row:
                return None
            if row["status"] != "running" and status == "running":
                return self._processing_step_from_row(row)
            db.execute("UPDATE processing_steps SET status=?,label=?,summary=?,completed_at=? WHERE step_id=?", (status, label or row["label"], (summary or row["summary"] or "")[:500] or None, _now() if status != "running" else None, step_id))
            row = db.execute("SELECT * FROM processing_steps WHERE step_id=?", (step_id,)).fetchone()
        return self._processing_step_from_row(row)

    def project_research_event_step(self, message_id: str, owner_id: str, *, node_key: str, source_event_id: str, kind: str, status: str, label: Optional[str] = None, summary: Optional[str] = None, parent_step_id: Optional[str] = None, node_type: str = "operation", display_order: int = 0, detail_json: Optional[str] = None, research_session_id: Optional[str] = None, strict_tree: bool = False) -> ProcessingStep:
        try:
            if re.fullmatch(r"research-event:[^:]+:[1-9][0-9]*", source_event_id) is None:
                raise ValueError("invalid source_event_id")
            with self.connection() as db:
                if db.execute("SELECT 1 FROM messages WHERE message_id=? AND owner_id=?", (message_id, owner_id)).fetchone() is None:
                    raise LookupError("message not found")
            step = self.create_processing_step(message_id, kind, status, summary, label=label, parent_step_id=parent_step_id, node_type=node_type, node_key=node_key, display_order=display_order, detail_json=detail_json, source_event_id=source_event_id, research_session_id=research_session_id, strict_tree=bool(strict_tree or research_session_id))
        except Exception:
            with self.transaction() as db:
                now = _now()
                db.execute("""INSERT INTO processing_step_projection_retries(source_event_id,message_id,error_code,attempts,last_error,pending,updated_at) VALUES(?,?, 'TRACE_PROJECTION_FAILED',1,?,1,?) ON CONFLICT(source_event_id) DO UPDATE SET attempts=attempts+1,last_error=excluded.last_error,pending=1,updated_at=excluded.updated_at""", (source_event_id, message_id, "TRACE_PROJECTION_FAILED", now))
            raise
        with self.transaction() as db:
            db.execute("UPDATE processing_step_projection_retries SET pending=0,updated_at=? WHERE source_event_id=?", (_now(), source_event_id))
        return step

    def mark_processing_projection_retry(self, source_event_id: str, message_id: str, error: str) -> dict:
        with self.transaction() as db:
            now = _now()
            db.execute("""INSERT INTO processing_step_projection_retries(source_event_id,message_id,error_code,attempts,last_error,pending,updated_at) VALUES(?,?, 'TRACE_PROJECTION_FAILED',1,?,1,?) ON CONFLICT(source_event_id) DO UPDATE SET attempts=attempts+1,last_error=excluded.last_error,pending=1,updated_at=excluded.updated_at""", (source_event_id, message_id, "TRACE_PROJECTION_FAILED", now))
            return dict(db.execute("SELECT * FROM processing_step_projection_retries WHERE source_event_id=?", (source_event_id,)).fetchone())

    def list_processing_projection_retries(self, *, pending_only: bool = True) -> list[dict]:
        with self.connection() as db:
            sql = "SELECT * FROM processing_step_projection_retries" + (" WHERE pending=1" if pending_only else "")
            rows = db.execute(sql + " ORDER BY updated_at, source_event_id").fetchall()
        return [dict(row) for row in rows]

    def replay_processing_steps(self, message_id: str, owner_id: str, events: list[dict], *, strict_tree: bool = False) -> list[ProcessingStep]:
        normalized: list[dict] = []
        for event in events:
            item = dict(event)
            if isinstance(item.get("safe_payload_json"), str):
                try:
                    payload = json.loads(item["safe_payload_json"])
                    if isinstance(payload, dict):
                        item = {**payload, **item}
                except (TypeError, ValueError):
                    pass
            task_id = item.get("research_task_id")
            seq = int(item.get("event_seq", 0))
            if not task_id or seq < 1:
                raise ValueError("persisted event is missing research task identity")
            source_event_id = f"research-event:{task_id}:{seq}"
            if item.get("source_event_id") not in (None, source_event_id):
                raise ValueError("persisted event source_event_id is not canonical")
            item["source_event_id"] = source_event_id
            normalized.append(item)
        task_ids = {item["research_task_id"] for item in normalized}
        if len(task_ids) > 1:
            raise ValueError("replay events belong to multiple research tasks")
        by_source = {item["source_event_id"]: item for item in normalized}
        by_key = {item["node_key"]: item for item in normalized if item.get("node_key")}

        def depth(item: dict, seen: set[str] | None = None) -> int:
            seen = seen or set()
            parent = item.get("parent_source_event_id") or item.get("parent_node_key")
            parent_item = by_source.get(parent) or by_key.get(parent)
            if parent_item is None:
                if parent:
                    raise ValueError("replay parent source_event_id is missing")
                return 0
            if parent in seen:
                raise ValueError("replay parent cycle")
            result = 1 + depth(parent_item, seen | {parent})
            if result >= 3:
                raise ValueError("replay tree exceeds three levels")
            return result

        def normalized_node_type(item: dict) -> str:
            value = str(item.get("node_type") or "operation").casefold()
            if value == "operation":
                value = {"task": "phase", "plan": "phase", "coverage": "phase", "report": "phase", "terminal": "phase", "worker": "agent"}.get(str(item.get("event_type") or "").casefold(), value)
            return "agent" if value == "work_item" else value

        strict = bool(strict_tree or any(item.get("research_session_id") for item in normalized))
        if strict:
            for item in normalized:
                level = depth(item)
                expected = "phase" if level == 0 else "agent" if level == 1 else "skill_or_tool"
                actual = normalized_node_type(item)
                if (expected == "phase" and actual != "phase") or (expected == "agent" and actual != "agent") or (expected == "skill_or_tool" and actual not in {"skill", "tool"}):
                    raise ValueError("invalid research processing tree node type")

        normalized.sort(key=lambda item: (depth(item), int(item.get("event_seq", 0))))
        results: list[ProcessingStep] = []
        step_by_source: dict[str, ProcessingStep] = {}
        step_by_key: dict[str, ProcessingStep] = {}
        for item in normalized:
            source_event_id = item["source_event_id"]
            parent_source = item.get("parent_source_event_id")
            parent_key = item.get("parent_node_key")
            parent_step = step_by_source.get(parent_source) if parent_source else step_by_key.get(parent_key) if parent_key else None
            if (parent_source or parent_key) and parent_step is None:
                raise ValueError("parent event was not replayed")
            node_key = str(item.get("node_key") or source_event_id)
            step = self.project_research_event_step(
                message_id, owner_id, node_key=node_key, source_event_id=source_event_id,
                kind=str(item.get("kind") or item.get("event_type") or "operation"),
                status=str(item.get("status") or "completed"), label=item.get("label"), summary=item.get("summary"),
                parent_step_id=parent_step.step_id if parent_step else None,
                node_type=normalized_node_type(item), display_order=int(item.get("display_order", item.get("event_seq", 0))),
                detail_json=item.get("detail_json"), research_session_id=item.get("research_session_id"), strict_tree=strict,
            )
            results.append(step)
            step_by_source[source_event_id] = step
            step_by_key[node_key] = step
        return results

    replay_projected_events = replay_processing_steps


SQLiteMemoryRepository = MemoryRepository
