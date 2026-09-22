"""Spec027 Research Task 持久化仓储（独立 SQLite 库）。

本模块是 Spec027 的**唯一**持久化入口，使用独立于 `data/memory` /
`data/paper_search` / `data/kb` 的 SQLite 库（`data/research/research.sqlite3`），
避免与 Spec015/022 既有数据耦合，整体删除即完成回滚。

设计要点（与 Spec027 §持久化与并发、§明确不做 对齐）：
- 独立库 + `schema_meta` 单例版本表；迁移在单一显式事务内、幂等、可回滚。
- 外键一律 `ON DELETE RESTRICT`（不用 CASCADE）；级联删除由 `delete_task`
  在本文件内按子表→主表顺序显式实现，保证 Spec015 目录/KB 数据不被误删。
- `event_seq` 在写事件的同一事务内 `UPDATE … SET last_event_seq = last_event_seq + 1`
  原子领号，配合 `_write_lock` 与 `BEGIN IMMEDIATE`，保证并发 Worker 不冲突、不重用、无洞。
- `mark_running_interrupted` 是 027 自有启动审计（running→interrupted），刻意区别于
  Spec015 `reset_running_jobs`（running→queued 重试语义），两者不得混用。
- 论文元数据不复制：只存 `catalog_paper_id` 字符串，引用 Spec015 全局目录。
- 全部时间戳存 UTC（`_utcnow()`），展示层再转本地。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from backend.app.platform.config import BASE_DIR
from backend.app.research.domain.contracts import (
    AGENT_ROLES,
    AGENT_RUN_STATUSES,
    APPROVAL_KINDS,
    APPROVAL_STATUSES,
    EVENT_TYPES,
    EVIDENCE_LEVELS,
    INTAKE_CONFIRMATION_STATUSES,
    INTAKE_FIELDS,
    INTAKE_SOURCES,
    INTAKE_STATUSES,
    NOTIFICATION_KINDS,
    NOTIFICATION_STATUSES,
    PLAN_STATUSES,
    ROLE_WHITELIST,
    SESSION_STATUSES,
    SESSION_TERMINAL,
    TASK_TERMINAL,
    TASK_TYPE_WHITELIST,
    WORKITEM_TERMINAL,
)
from backend.app.research.domain.models import (
    AcquisitionApproval,
    AcquisitionEvent,
    AcquisitionIssue,
    AgentCheckpoint,
    AgentRun,
    ApprovalRequest,
    ClaimEvidence,
    ComparisonDimension,
    EvidenceUpgrade,
    IntakeField,
    ManualResolution,
    PaperComparisonCell,
    PreliminaryReport,
    ResearchArtifact,
    ResearchClaim,
    ResearchDocumentLink,
    ResearchEvent,
    ResearchIntakeDraft,
    ResearchNotification,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchReport,
    ResearchSession,
    ResearchSessionPlan,
    ResearchTask,
    ResearchWorkItem,
    ResourceReservation,
    SchedulerCheckpoint,
    SchedulerLease,
)
from backend.app.research.domain.state_machine import (
    transition_agent_run,
    transition_approval,
    transition_intake,
    transition_session,
    transition_task,
    transition_workitem,
)

# Task04 adds Session plan/command tables as an explicit v3 migration.  Keep
# this separate from the Task02 v2 marker so existing v2 databases are upgraded
# on their next open rather than relying on a fresh database path.
SCHEMA_VERSION = 3

# 写操作全局串行锁：保证 event_seq 原子领号在进程内也无竞争；锁内只做必要写，
# 计算（JSON 序列化等）已尽量外移。RLock 允许同一线程重入。
_write_lock = threading.RLock()


class LegacyCleanupError(RuntimeError):
    """Stable maintenance failure; callers must treat the transaction as aborted."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

_EVENT_SAFE_KEYS = {
    "status", "goal_excerpt", "quality_profile", "target_paper_count", "review_plan_first",
    "plan_version", "previous_plan_version", "replan_round", "stop_reason", "reason",
    "facets", "items", "work_item_id", "task_type", "role", "model_tier", "resolved_model",
    "worker_slot", "code", "error_code", "selected_count", "selected_paper_ids", "catalog_paper_ids", "search_worker", "search_id",
    "coverage", "gaps", "recommendations", "bounded_replan", "approval_required", "evaluations",
    "statistics", "output_hash", "node_type", "node_key", "parent_node_key", "parent_source_event_id",
    "parent_step_id", "kind", "label", "summary", "display_order", "research_session_id",
    "skill_name", "tool_name", "result_id", "result_length", "length", "content_hash", "tool_call_id",
    "attempt", "event_type", "from_tier", "to_tier", "granted", "source_ref", "facets_by_paper",
    "reason_code", "from_provider", "to_provider", "from_model", "to_model",
}
_EVENT_SENSITIVE_PARTS = ("prompt", "cot", "reasoning", "credential", "password", "secret", "token", "authorization", "cookie", "api_key", "access_key")


def _safe_event_value(value: object, *, depth: int = 0) -> object:
    if depth > 3:
        return None
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.casefold()
            if key_text not in _EVENT_SAFE_KEYS or any(part in lowered for part in _EVENT_SENSITIVE_PARTS):
                continue
            cleaned = _safe_event_value(item, depth=depth + 1)
            if cleaned is not None:
                result[key_text[:80]] = cleaned
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value[:64]:
            cleaned = _safe_event_value(item, depth=depth + 1)
            if cleaned is not None:
                result.append(cleaned)
        return result
    if isinstance(value, str):
        # Scrub values inside otherwise-allowed summaries as well as filtering
        # sensitive field names.  The replacement is intentionally stable so
        # clients can render it without seeing provider credentials.
        cleaned = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]", value)
        cleaned = re.sub(r"(?i)((?:token|secret|password|cookie)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", cleaned)
        cleaned = re.sub(r"(?i)https?://[^\s,;]+", "[REDACTED]", cleaned)
        return cleaned[:1000]
    if isinstance(value, (int, float, bool)):
        return value
    return None


def _safe_event_payload(payload: object) -> dict:
    value = _safe_event_value(payload)
    return value if isinstance(value, dict) else {}


def canonical_research_event_id(research_task_id: str, event_seq: int) -> str:
    """Stable cross-store event identity used by the ProcessingStep projector."""
    if not research_task_id or int(event_seq) < 1:
        raise ValueError("invalid research event identity")
    return f"research-event:{research_task_id}:{int(event_seq)}"


canonical_event_id = canonical_research_event_id


def validate_session_external_references(session: ResearchSession, memory_repository) -> None:
    """Validate cross-database conversation/message ownership at the seam.

    SQLite cannot enforce a foreign key into the memory DB.  The caller may
    supply the existing MemoryRepository here; no replacement store is ever
    created by this module.
    """
    conversation = memory_repository.get_conversation(session.conversation_id, session.owner_id)
    if conversation is None:
        raise ResearchSessionNotFound(session.conversation_id)
    if conversation.owner_id != session.owner_id:
        raise ResearchSessionNotFound(session.conversation_id)
    message = memory_repository.get_message(session.trigger_message_id, session.owner_id)
    if message is None or message.conversation_id != session.conversation_id:
        raise ResearchSessionNotFound(session.trigger_message_id)


def default_database_path() -> Path:
    """返回数据库文件路径：环境变量 RESEARCH_DB_PATH 优先，否则 BASE_DIR/data/research/research.sqlite3。

    独立库路径是 Spec027「整体删除即回滚」的前提，绝不回退到 memory/paper_search/kb 库。
    """
    override = os.environ.get("RESEARCH_DB_PATH")
    if override:
        return Path(override)
    return BASE_DIR / "data" / "research" / "research.sqlite3"


def _utcnow() -> str:
    """当前 UTC 时间戳，格式 `YYYY-MM-DDTHH:MM:SSZ`。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_after(seconds: int, now: str | None = None) -> str:
    """Return a comparable UTC timestamp without relying on the system clock twice."""
    if now:
        try:
            base = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid scheduler timestamp") from exc
    else:
        base = datetime.now(timezone.utc)
    return (base + timedelta(seconds=max(1, int(seconds)))).isoformat(timespec="seconds").replace("+00:00", "Z")


def encode_cursor(created_at: str, task_id: str) -> str:
    """把分页锚点 (created_at, task_id) 编码为不可猜测的 keyset 游标。"""
    payload = {"v": 1, "at": created_at, "id": task_id}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """解码 keyset 游标；任何结构异常一律抛 ValueError('invalid cursor')。

    用 base64 仅做不透明封装，不做业务含义；非法游标由调用方转 400，避免 SQL 注入。
    """
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("invalid cursor")
    try:
        raw = base64.urlsafe_b64decode(cursor)
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as err:
        raise ValueError("invalid cursor") from err
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("invalid cursor")
    at = payload.get("at")
    tid = payload.get("id")
    if not isinstance(at, str) or not isinstance(tid, str):
        raise ValueError("invalid cursor")
    return at, tid


class ResearchTaskNotFound(Exception):
    """指定的 research_task_id（且属于 owner）不存在。

    属性 ``code = "TASK_NOT_FOUND"`` 供上层映射稳定错误文案。
    """

    code = "TASK_NOT_FOUND"

    def __init__(self, research_task_id: str):
        self.research_task_id = research_task_id
        super().__init__(f"research task not found: {research_task_id}")


class ResearchPlanNotFound(Exception):
    """指定的 (research_task_id, version) 计划版本不存在。"""

    code = "PLAN_NOT_FOUND"

    def __init__(self, research_task_id: str, version: int):
        self.research_task_id = research_task_id
        self.version = version
        super().__init__(f"research plan not found: {research_task_id} v{version}")


class ResearchPlanConflict(Exception):
    """同一 (research_task_id, version) 计划已存在，禁止覆盖（版本不可覆盖契约）。"""

    code = "PLAN_VALIDATION_FAILED"

    def __init__(self, research_task_id: str, version: int):
        self.research_task_id = research_task_id
        self.version = version
        super().__init__(f"research plan already exists: {research_task_id} v{version}")


class ResearchWorkItemNotFound(Exception):
    """指定的 work_item_id 不存在。"""

    code = "WORK_ITEM_NOT_FOUND"

    def __init__(self, work_item_id: str):
        self.work_item_id = work_item_id
        super().__init__(f"research work item not found: {work_item_id}")


class ResearchSessionNotFound(Exception):
    code = "RESEARCH_SESSION_NOT_FOUND"

    def __init__(self, research_session_id: str):
        self.research_session_id = research_session_id
        super().__init__(f"research session not found: {research_session_id}")


class ResearchSessionActiveConflict(Exception):
    code = "RESEARCH_SESSION_ACTIVE_CONFLICT"


class ApprovalConflict(Exception):
    code = "APPROVAL_CONFLICT"


class ApprovalStale(Exception):
    code = "APPROVAL_STALE"


class AgentRunBindingError(ValueError):
    code = "AGENT_RUN_BINDING_INVALID"


class AgentRunWriteDiscarded(Exception):
    """A late worker write lost the running-generation CAS race."""

    code = "AGENT_RUN_WRITE_DISCARDED"


class ResearchArtifactConflict(Exception):
    code = "ARTIFACT_IMMUTABLE_CONFLICT"


class ResearchReportConflict(Exception):
    code = "REPORT_VERSION_CONFLICT"


class NotificationConflict(Exception):
    code = "NOTIFICATION_IDEMPOTENCY_CONFLICT"


def _notification_identity_matches(existing: sqlite3.Row | dict, candidate: ResearchNotification) -> bool:
    """Compare the durable notification identity, excluding generated seq/id."""
    try:
        existing_payload = json.loads(existing["payload_json"])
        candidate_payload = json.loads(candidate.payload_json)
    except (TypeError, ValueError):
        existing_payload = existing["payload_json"]
        candidate_payload = candidate.payload_json
    return (
        existing["notification_kind"] == candidate.notification_kind
        and existing["status"] == candidate.status
        and int(existing["subject_version"]) == int(candidate.subject_version)
        and existing["research_session_id"] == candidate.research_session_id
        and existing["research_task_id"] == candidate.research_task_id
        and existing_payload == candidate_payload
    )


def _validate_notification_payload(value: object, *, depth: int = 0) -> None:
    """Reject unsafe notification facts without imposing a product key list."""
    if depth > 4:
        raise ValueError("notification payload is too deeply nested")
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("notification payload is too large")
        for key, child in value.items():
            lowered = str(key).casefold()
            if any(part in lowered for part in _EVENT_SENSITIVE_PARTS) or "url" in lowered:
                raise ValueError("notification payload contains sensitive field")
            _validate_notification_payload(child, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise ValueError("notification payload list is too large")
        for child in value:
            _validate_notification_payload(child, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 2000 or re.search(r"(?:https?://|ftp://|www\.)", value, re.I):
            raise ValueError("notification payload contains unsafe value")
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise ValueError("notification payload contains unsupported value")


# update_task 允许更新的白名单列（与 research_tasks 表列名一致）。
_TASK_UPDATE_WHITELIST = frozenset(
    {
        "project_id",
        "current_plan_version",
        "goal",
        "language",
        "quality_profile",
        "target_paper_count",
        "soft_budget_seconds",
        "review_plan_first",
    }
)


class ResearchStore:
    """Spec027 Research Task 独立 SQLite 持久化仓储。

    连接参数照搬既有 store 范式：`timeout=30.0`、``row_factory = sqlite3.Row``、
    ``PRAGMA foreign_keys = ON``。Research Task 需要跨进程恢复，因此显式启用
    SQLite WAL；并发领取/心跳由 `BEGIN IMMEDIATE` + 条件更新裁决，避免读写互相
    阻塞而不改变既有状态机。
    写操作统一在 ``with _write_lock, self._connect() as conn:`` 内
    ``BEGIN IMMEDIATE`` → 操作 → ``commit``，异常时 ``rollback`` 并向上抛。
    """

    def __init__(self, database_path: Optional[Path] = None):
        """打开（或新建）独立库，并在单事务内幂等建表 + 校验 schema_meta 版本。

        结构：BEGIN → CREATE schema_meta/v1 全部表 → 迁移（v1 无操作）→ 校验版本 → commit。
        连续两次构造同一库不报错、不产生重复数据（所有 CREATE 用 IF NOT EXISTS）。
        """
        self.database_path = Path(database_path or default_database_path())
        # 父目录可能不存在（首次建库），提前创建以避免连接失败。
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL)")
            self._initialize_v1(connection)
            current = self._current_schema_version(connection)
            # v1/v2 均通过同一事务执行幂等加性迁移；v2 -> v3 是 Task04 的
            # Session plan/command 表迁移，失败时整个事务回滚。
            if current is None or current < SCHEMA_VERSION:
                self._migrate_to_current(connection)
            # Task09 is an additive maintenance table layered on the stable
            # v3 marker; existing v3 databases must receive it too.
            self._ensure_task09_schema(connection)
            self._ensure_spec029_schema(connection)
            self._ensure_spec030_schema(connection)
            self._ensure_spec031_schema(connection)
            self._ensure_spec040_schema(connection)
            self._validate_schema_meta(connection)
            connection.commit()

    # ------------------------------------------------------------------ #
    # 迁移 / 校验（照抄 paper_discovery_store 范式）
    # ------------------------------------------------------------------ #

    def _initialize_v1(self, connection: sqlite3.Connection) -> None:
        """创建 v1 全部表与索引（全部 IF NOT EXISTS，幂等）。外键 RESTRICT，论文元数据不复制。"""
        connection.execute(
            """CREATE TABLE IF NOT EXISTS research_tasks(
                research_task_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                project_id TEXT,
                conversation_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                language TEXT NOT NULL,
                quality_profile TEXT NOT NULL,
                review_plan_first INTEGER NOT NULL DEFAULT 0,
                target_paper_count INTEGER NOT NULL,
                soft_budget_seconds INTEGER NOT NULL,
                status TEXT NOT NULL,
                current_plan_version INTEGER NOT NULL DEFAULT 1,
                last_event_seq INTEGER NOT NULL DEFAULT 0,
                search_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS research_plans(
                research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
                version INTEGER NOT NULL,
                planner_model TEXT,
                rationale_summary TEXT NOT NULL,
                facets_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(research_task_id, version)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS research_work_items(
                work_item_id TEXT PRIMARY KEY,
                research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
                plan_version INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                role TEXT NOT NULL,
                depends_on_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT,
                model_tier TEXT,
                resolved_model TEXT,
                worker_slot TEXT,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                started_at TEXT,
                ended_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT,
                last_error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS research_events(
                research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
                event_seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                safe_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(research_task_id, event_seq)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS research_paper_selections(
                research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
                catalog_paper_id TEXT NOT NULL,
                relevance REAL NOT NULL DEFAULT 0,
                facets_json TEXT NOT NULL DEFAULT '[]',
                evidence_level TEXT NOT NULL DEFAULT 'catalog',
                created_at TEXT NOT NULL,
                PRIMARY KEY(research_task_id, catalog_paper_id)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS preliminary_reports(
                report_id TEXT PRIMARY KEY,
                research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
                plan_version INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'preliminary',
                markdown TEXT NOT NULL,
                limitations_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                UNIQUE(research_task_id, plan_version)
            )"""
        )
        # schema_meta 单例表达式索引：防止意外写入第二行（损坏版本表）。
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS research_schema_meta_singleton ON schema_meta((1))")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_tasks_owner_created "
            "ON research_tasks(owner_id, created_at, research_task_id)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_tasks_project ON research_tasks(project_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_work_items_task ON research_work_items(research_task_id, plan_version)"
        )

    @staticmethod
    def _ensure_task09_schema(connection: sqlite3.Connection) -> None:
        """Create Task09 audit storage for fresh and already-v3 databases."""
        connection.execute("""CREATE TABLE IF NOT EXISTS research_legacy_cleanup_audits(
            cleanup_id TEXT PRIMARY KEY,
            owner_id TEXT,
            mode TEXT NOT NULL CHECK(mode IN ('dry_run','execute')),
            status TEXT NOT NULL CHECK(status IN ('planned','completed','aborted')),
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_cleanup_audits_created "
            "ON research_legacy_cleanup_audits(created_at, cleanup_id)"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS research_session_create_requests(
            owner_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            research_session_id TEXT,
            conversation_id TEXT,
            trigger_message_id TEXT,
            response_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(owner_id, idempotency_key)
        )""")

    @staticmethod
    def _ensure_spec029_schema(connection: sqlite3.Connection) -> None:
        """Create the Research↔paper-import bridge without changing KB state."""
        connection.execute("""CREATE TABLE IF NOT EXISTS research_selection_versions(
            research_task_id TEXT PRIMARY KEY REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            selection_version INTEGER NOT NULL DEFAULT 0 CHECK(selection_version >= 0),
            updated_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_acquisition_approvals(
            approval_id TEXT PRIMARY KEY,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            selection_version INTEGER NOT NULL CHECK(selection_version >= 1),
            paper_ids_json TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT,
            batch_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(research_task_id, selection_version),
            UNIQUE(research_task_id, idempotency_key)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_document_links(
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            catalog_paper_id TEXT NOT NULL,
            document_id TEXT,
            import_item_id TEXT,
            status TEXT NOT NULL,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(research_task_id, catalog_paper_id)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_acquisition_events(
            event_id TEXT PRIMARY KEY,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            paper_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            status TEXT NOT NULL,
            error_code TEXT,
            batch_id TEXT,
            import_item_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(research_task_id, paper_id, phase, status, import_item_id, error_code)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_evidence_upgrades(
            claim_id TEXT PRIMARY KEY,
            research_task_id TEXT,
            document_id TEXT,
            from_level TEXT NOT NULL,
            to_level TEXT NOT NULL,
            chunk_ids_json TEXT NOT NULL,
            page INTEGER,
            page_end INTEGER,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_acq_events_task ON research_acquisition_events(research_task_id, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_doc_links_task ON research_document_links(research_task_id, catalog_paper_id)")
        # Task11 keeps one durable issue per candidate across Research tasks;
        # JSON columns retain compact task/attempt/action history without
        # copying candidate metadata or creating a second import state machine.
        connection.execute("""CREATE TABLE IF NOT EXISTS research_acquisition_issues(
            issue_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL UNIQUE,
            task_ids_json TEXT NOT NULL DEFAULT '[]',
            reason_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            attempts_json TEXT NOT NULL DEFAULT '[]',
            actions_json TEXT NOT NULL DEFAULT '[]',
            resolution_json TEXT,
            import_item_id TEXT,
            batch_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_manual_resolutions(
            resolution_id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL REFERENCES research_acquisition_issues(issue_id) ON DELETE RESTRICT,
            method TEXT NOT NULL,
            user_document_id TEXT,
            identity_verdict TEXT NOT NULL,
            confirmed_at TEXT,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_acq_issues_status ON research_acquisition_issues(status, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_acq_issues_candidate ON research_acquisition_issues(candidate_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_manual_resolutions_issue ON research_manual_resolutions(issue_id, created_at)")
        # Task04 adds provenance to the already shipped evidence projection.
        # Keep this additive so Task03 databases remain readable.
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(research_evidence_upgrades)").fetchall()
        }
        for name, declaration in (
            ("source_sha256", "TEXT"),
            ("manifest_generation", "TEXT"),
            ("manifest_fingerprint", "TEXT"),
            ("chunker", "TEXT"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE research_evidence_upgrades ADD COLUMN {name} {declaration}")
        # Spec029 acquisition needs a durable server-owned catalog snapshot
        # handle.  Keep this additive so pre-029 research databases remain
        # readable without changing the schema version marker.
        task_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(research_tasks)").fetchall()
        }
        if "search_id" not in task_columns:
            connection.execute("ALTER TABLE research_tasks ADD COLUMN search_id TEXT")
        # 一个研究任务可扇出多个 search worker，各自产出不同的 server 快照句柄。
        # 选集必须记住自己来自哪一次检索，否则导入桥只能拿任务级（第一个）search_id
        # 去解析候选，遇到「选集来自后出发的 worker」就必然 CANDIDATE_NOT_FOUND。
        # 加性加列，不改 schema version，pre-029 库保持可读。
        selection_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(research_paper_selections)").fetchall()
        }
        if "source_search_id" not in selection_columns:
            connection.execute("ALTER TABLE research_paper_selections ADD COLUMN source_search_id TEXT")
        # 选集可能横跨多个 search worker 的快照，导入桥会按来源快照建多个批次。
        # batch_id 保留为主批次，batch_ids_json 记录全部批次 id（JSON 数组）。
        approval_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(research_acquisition_approvals)").fetchall()
        }
        if "batch_ids_json" not in approval_columns:
            connection.execute("ALTER TABLE research_acquisition_approvals ADD COLUMN batch_ids_json TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_evidence_task ON research_evidence_upgrades(research_task_id)")
        # Existing Spec027 databases already contain a current selection but
        # no version row.  Seed it as version 1 without copying paper data.
        connection.execute(
            """INSERT OR IGNORE INTO research_selection_versions(research_task_id, selection_version, updated_at)
               SELECT research_task_id, 1, COALESCE(MAX(created_at), '')
               FROM research_paper_selections GROUP BY research_task_id"""
        )

    @staticmethod
    def _ensure_spec030_schema(connection: sqlite3.Connection) -> None:
        """Add the versioned evidence-matrix tables without copying paper data."""
        connection.execute("""CREATE TABLE IF NOT EXISTS research_reports(
            report_id TEXT PRIMARY KEY,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
            report_version INTEGER NOT NULL CHECK(report_version >= 1),
            status TEXT NOT NULL CHECK(status IN ('draft','generating','completed','partial','failed')),
            markdown TEXT NOT NULL,
            html TEXT NOT NULL,
            report_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE(research_task_id, report_version)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_reports_task ON research_reports(research_task_id, report_version)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_claims(
            claim_id TEXT PRIMARY KEY,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
            topic TEXT NOT NULL,
            statement TEXT NOT NULL,
            confidence TEXT NOT NULL CHECK(confidence IN ('low','medium','high')),
            status TEXT NOT NULL CHECK(status IN ('supported','contested','unresolved')),
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE(research_task_id, plan_version, claim_id)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_claim_evidence(
            evidence_id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL REFERENCES research_claims(claim_id) ON DELETE RESTRICT,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
            paper_id TEXT NOT NULL,
            evidence_level TEXT NOT NULL CHECK(evidence_level IN ('catalog','abstract','fulltext')),
            stance TEXT NOT NULL CHECK(stance IN ('supports','contradicts','contextual')),
            status TEXT NOT NULL CHECK(status IN ('available','unavailable','revalidation_required')),
            quote_digest TEXT NOT NULL DEFAULT '',
            locator_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_comparison_dimensions(
            dimension_id TEXT NOT NULL,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
            label TEXT NOT NULL,
            definition TEXT NOT NULL,
            display_order INTEGER NOT NULL CHECK(display_order >= 0),
            created_at TEXT NOT NULL,
            PRIMARY KEY(research_task_id, plan_version, dimension_id),
            UNIQUE(research_task_id, plan_version, display_order)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_comparison_cells(
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
            claim_id TEXT NOT NULL REFERENCES research_claims(claim_id) ON DELETE RESTRICT,
            paper_id TEXT NOT NULL,
            dimension_id TEXT NOT NULL,
            relation TEXT NOT NULL CHECK(relation IN ('supports','contradicts','contextual','missing')),
            summary TEXT NOT NULL DEFAULT '',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            missing_reason TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(research_task_id, plan_version, claim_id, paper_id, dimension_id)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_claims_task ON research_claims(research_task_id, plan_version)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_evidence_task_v1 ON research_claim_evidence(research_task_id, plan_version, claim_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_cells_task ON research_comparison_cells(research_task_id, plan_version)")

    @staticmethod
    def _ensure_spec031_schema(connection: sqlite3.Connection) -> None:
        """Add bounded, owner-scoped routing observation tables.

        This is intentionally additive and does not change the schema marker:
        existing Spec027/028 databases must open without a destructive
        migration.  No prompt, answer, chain-of-thought, or credential field
        exists in these tables.
        """
        connection.execute("""CREATE TABLE IF NOT EXISTS research_routing_decisions(
            decision_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            idempotency_key TEXT,
            task_type TEXT NOT NULL,
            features_json TEXT NOT NULL,
            candidate_models_json TEXT NOT NULL,
            chosen_model TEXT NOT NULL,
            reason TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(owner_id, idempotency_key)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_model_outcomes(
            decision_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            schema_valid INTEGER,
            quality_score REAL,
            ttft REAL,
            duration REAL,
            tokens INTEGER,
            error_code TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(decision_id) REFERENCES research_routing_decisions(decision_id) ON DELETE RESTRICT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_resource_snapshots(
            snapshot_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            available_memory INTEGER,
            loaded_models_json TEXT NOT NULL,
            estimated_kv INTEGER,
            active_workers INTEGER,
            captured_at TEXT NOT NULL,
            probe_error TEXT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_routing_policies(
            version TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            rules_json TEXT NOT NULL,
            thresholds_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','shadow','active','retired')),
            created_at TEXT NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_routing_decisions_owner_created ON research_routing_decisions(owner_id, created_at, decision_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_routing_outcomes_owner ON research_model_outcomes(owner_id, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_resource_snapshots_owner ON research_resource_snapshots(owner_id, captured_at, snapshot_id)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_routing_gate_evidence(
            evidence_id TEXT PRIMARY KEY,
            policy_version TEXT NOT NULL,
            quality_samples INTEGER NOT NULL CHECK(quality_samples >= 0),
            quality_score REAL NOT NULL,
            schema_valid_rate REAL NOT NULL,
            resource_snapshot_id TEXT NOT NULL,
            resource_workers INTEGER NOT NULL CHECK(resource_workers >= 1),
            created_at TEXT NOT NULL,
            FOREIGN KEY(resource_snapshot_id) REFERENCES research_resource_snapshots(snapshot_id) ON DELETE RESTRICT
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_routing_gate_evidence_policy ON research_routing_gate_evidence(policy_version, created_at)")

    @staticmethod
    def _ensure_spec040_schema(connection: sqlite3.Connection) -> None:
        """Add durable retry metadata to existing WorkItem tables."""
        columns = {row[1] for row in connection.execute("PRAGMA table_info(research_work_items)").fetchall()}
        if "retry_count" not in columns:
            connection.execute("ALTER TABLE research_work_items ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
        if "next_retry_at" not in columns:
            connection.execute("ALTER TABLE research_work_items ADD COLUMN next_retry_at TEXT")
        if "last_error_code" not in columns:
            connection.execute("ALTER TABLE research_work_items ADD COLUMN last_error_code TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_work_items_retry_due "
            "ON research_work_items(status, next_retry_at, research_task_id)"
        )

    @staticmethod
    def _ensure_scheduler_schema(connection: sqlite3.Connection) -> None:
        """Create Task03 scheduler tables lazily and idempotently.

        Task02's runtime gate owns tiny probe tables with the same names.  A
        lazy additive migration keeps that probe backwards compatible while
        ensuring every production scheduler write sees the durable schema.
        Scheduler ids deliberately have no foreign key: ``task_id`` is the
        WorkItem identity at dispatch time and a ResearchTask identity during
        task-level recovery.
        """
        connection.execute("""CREATE TABLE IF NOT EXISTS scheduler_leases(
            task_id TEXT PRIMARY KEY,
            owner_token TEXT,
            expires_at TEXT,
            heartbeat_at TEXT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS scheduler_checkpoints(
            task_id TEXT NOT NULL,
            plan_version INTEGER NOT NULL,
            node_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            input_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(task_id, plan_version, node_id)
        )""")
        checkpoint_columns = {row[1] for row in connection.execute("PRAGMA table_info(scheduler_checkpoints)").fetchall()}
        if "created_at" not in checkpoint_columns:
            connection.execute("ALTER TABLE scheduler_checkpoints ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        if "updated_at" not in checkpoint_columns:
            connection.execute("ALTER TABLE scheduler_checkpoints ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        connection.execute("""CREATE TABLE IF NOT EXISTS resource_reservations(
            reservation_id TEXT PRIMARY KEY,
            task_id TEXT,
            worker_id TEXT NOT NULL,
            model_tier TEXT NOT NULL,
            estimated_bytes INTEGER NOT NULL CHECK(estimated_bytes >= 0),
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            released_at TEXT,
            grant_token TEXT
        )""")
        reservation_columns = {row[1] for row in connection.execute("PRAGMA table_info(resource_reservations)").fetchall()}
        if "grant_token" not in reservation_columns:
            connection.execute("ALTER TABLE resource_reservations ADD COLUMN grant_token TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_leases_expiry "
            "ON scheduler_leases(expires_at, task_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_checkpoints_task "
            "ON scheduler_checkpoints(task_id, plan_version, node_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_resource_reservations_active "
            "ON resource_reservations(expires_at, released_at, task_id)"
        )

    @staticmethod
    def _migrate_to_current(connection: sqlite3.Connection) -> None:
        """Apply additive research-library migrations in the caller transaction."""
        connection.execute("""CREATE TABLE IF NOT EXISTS research_sessions(
            research_session_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            plan_message_id TEXT,
            activity_message_id TEXT,
            final_message_id TEXT,
            intake_draft_id TEXT NOT NULL UNIQUE,
            research_task_id TEXT,
            current_plan_version INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            unread_state_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        # A partial unique index is the SQLite equivalent of the active-session
        # CAS. Terminal sessions remain available for history and rebinding.
        connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_research_sessions_active
            ON research_sessions(owner_id, conversation_id)
            WHERE status NOT IN ('interrupted','partial','completed','failed','cancelled')""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_sessions_owner_created ON research_sessions(owner_id, created_at, research_session_id)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_intake_drafts(
            intake_draft_id TEXT PRIMARY KEY,
            research_session_id TEXT NOT NULL UNIQUE REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_intake_fields(
            intake_draft_id TEXT NOT NULL REFERENCES research_intake_drafts(intake_draft_id) ON DELETE RESTRICT,
            field_name TEXT NOT NULL,
            value_json TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL NOT NULL,
            confirmation_status TEXT NOT NULL,
            updated_by_message_id TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(intake_draft_id, field_name)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_approval_requests(
            approval_request_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            subject_version INTEGER NOT NULL,
            requested_scope_json TEXT NOT NULL,
            approved_scope_json TEXT,
            status TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            decided_by_message_id TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            UNIQUE(owner_id, idempotency_key)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_approvals_session ON research_approval_requests(owner_id, research_session_id, subject_version)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_command_results(
            owner_id TEXT NOT NULL,
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            idempotency_key TEXT NOT NULL,
            command TEXT NOT NULL,
            subject_version INTEGER NOT NULL DEFAULT 0,
            subject_id TEXT NOT NULL DEFAULT '',
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(owner_id, idempotency_key)
        )""")
        command_columns = {row[1] for row in connection.execute("PRAGMA table_info(research_command_results)").fetchall()}
        if "subject_version" not in command_columns:
            connection.execute("ALTER TABLE research_command_results ADD COLUMN subject_version INTEGER NOT NULL DEFAULT 0")
        if "subject_id" not in command_columns:
            connection.execute("ALTER TABLE research_command_results ADD COLUMN subject_id TEXT NOT NULL DEFAULT ''")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_activity_outbox(
            outbox_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            subject_version INTEGER NOT NULL,
            command_idempotency_key TEXT NOT NULL,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            activity_message_id TEXT,
            status TEXT NOT NULL CHECK(status IN ('pending','failed','completed')),
            error_code TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, research_session_id, subject_version, command_idempotency_key)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_session_plans(
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            version INTEGER NOT NULL,
            schema_version TEXT NOT NULL,
            output_hash TEXT NOT NULL,
            objective TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            work_items_json TEXT NOT NULL,
            capabilities_json TEXT NOT NULL,
            budget_json TEXT NOT NULL,
            report_structure_json TEXT NOT NULL,
            safety_summary_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(research_session_id, version)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_session_plans_current ON research_session_plans(research_session_id, version)")
        # The activation row is the durable anchor for approve_plan.  Its
        # deterministic task id lets a retry resume after any process crash
        # between task/plan/work-item/outbox writes without creating a second
        # task or leaving an unlinked orphan.
        connection.execute("""CREATE TABLE IF NOT EXISTS research_plan_activations(
            activation_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            subject_version INTEGER NOT NULL,
            command_idempotency_key TEXT NOT NULL,
            research_task_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('pending','failed','completed')),
            error_code TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, research_session_id, subject_version, command_idempotency_key)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_plan_activations_session ON research_plan_activations(owner_id, research_session_id, subject_version)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_agent_runs(
            agent_run_id TEXT PRIMARY KEY,
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            research_task_id TEXT REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            work_item_id TEXT REFERENCES research_work_items(work_item_id) ON DELETE RESTRICT,
            attempt INTEGER NOT NULL,
            continued_from_agent_run_id TEXT REFERENCES research_agent_runs(agent_run_id) ON DELETE RESTRICT,
            role TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            skill_schema_version TEXT NOT NULL,
            skill_content_hash TEXT NOT NULL,
            resolved_model TEXT NOT NULL,
            reasoning_effort TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT '',
            allowed_tools_json TEXT NOT NULL,
            status TEXT NOT NULL,
            model_loop_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            input_hash TEXT NOT NULL DEFAULT '',
            output_hash TEXT NOT NULL DEFAULT '',
            checkpoint_ref TEXT,
            checkpoint_hash TEXT,
            error_code TEXT,
            started_at TEXT,
            ended_at TEXT,
            generation INTEGER NOT NULL DEFAULT 0
        )""")
        agent_columns = {row[1] for row in connection.execute("PRAGMA table_info(research_agent_runs)").fetchall()}
        if "generation" not in agent_columns:
            connection.execute("ALTER TABLE research_agent_runs ADD COLUMN generation INTEGER NOT NULL DEFAULT 0")
        if "provider" not in agent_columns:
            connection.execute("ALTER TABLE research_agent_runs ADD COLUMN provider TEXT NOT NULL DEFAULT ''")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_agent_runs_task ON research_agent_runs(research_task_id, work_item_id, status)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_agent_checkpoints(
            checkpoint_ref TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            research_session_id TEXT NOT NULL REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            research_task_id TEXT REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            work_item_id TEXT REFERENCES research_work_items(work_item_id) ON DELETE RESTRICT,
            agent_run_id TEXT NOT NULL REFERENCES research_agent_runs(agent_run_id) ON DELETE RESTRICT,
            schema_version TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            continued_from_agent_run_id TEXT REFERENCES research_agent_runs(agent_run_id) ON DELETE RESTRICT,
            UNIQUE(agent_run_id, content_hash)
        )""")
        checkpoint_columns = {row[1] for row in connection.execute("PRAGMA table_info(research_agent_checkpoints)").fetchall()}
        if "continued_from_agent_run_id" not in checkpoint_columns:
            connection.execute("ALTER TABLE research_agent_checkpoints ADD COLUMN continued_from_agent_run_id TEXT REFERENCES research_agent_runs(agent_run_id) ON DELETE RESTRICT")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_checkpoints_owner ON research_agent_checkpoints(owner_id, research_session_id, research_task_id, work_item_id)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_artifacts(
            artifact_id TEXT PRIMARY KEY,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            report_version INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            content TEXT,
            storage_ref TEXT,
            content_hash TEXT NOT NULL,
            generated_by_agent_run_id TEXT NOT NULL REFERENCES research_agent_runs(agent_run_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            CHECK ((content IS NOT NULL) != (storage_ref IS NOT NULL)),
            UNIQUE(research_task_id, report_version, artifact_type)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_notifications(
            notification_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            research_session_id TEXT REFERENCES research_sessions(research_session_id) ON DELETE RESTRICT,
            research_task_id TEXT REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            notification_kind TEXT NOT NULL,
            status TEXT NOT NULL,
            subject_version INTEGER NOT NULL,
            event_seq INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            read_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (research_session_id IS NOT NULL OR research_task_id IS NOT NULL),
            CHECK ((status='read' AND read_at IS NOT NULL) OR (status='unread' AND read_at IS NULL)),
            UNIQUE(owner_id, idempotency_key),
            UNIQUE(owner_id, event_seq)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_notifications_owner_seq ON research_notifications(owner_id, event_seq)")
        connection.execute("""CREATE TABLE IF NOT EXISTS research_projection_retries(
            source_event_id TEXT PRIMARY KEY,
            research_task_id TEXT NOT NULL REFERENCES research_tasks(research_task_id) ON DELETE RESTRICT,
            attempts INTEGER NOT NULL DEFAULT 1,
            error_code TEXT NOT NULL DEFAULT 'TRACE_PROJECTION_FAILED',
            last_error TEXT,
            pending INTEGER NOT NULL DEFAULT 1 CHECK(pending IN (0,1)),
            updated_at TEXT NOT NULL
        )""")
        connection.execute("UPDATE schema_meta SET version=?", (SCHEMA_VERSION,))

    @staticmethod
    def _current_schema_version(connection: sqlite3.Connection) -> Optional[int]:
        """读取已存版本；结构损坏/多行则抛 RuntimeError（事务回滚）。None 表示全新库。"""
        try:
            columns = connection.execute("PRAGMA table_info(schema_meta)").fetchall()
            if (
                len(columns) != 1
                or columns[0][1] != "version"
                or str(columns[0][2]).upper() != "INTEGER"
                or not columns[0][3]
            ):
                raise RuntimeError("Invalid research schema metadata: malformed schema_meta table")
            rows = connection.execute("SELECT version, typeof(version) AS value_type FROM schema_meta").fetchall()
        except sqlite3.DatabaseError as error:
            raise RuntimeError("Invalid research schema metadata: malformed schema_meta table") from error
        if len(rows) > 1:
            raise RuntimeError("Invalid research schema metadata: expected exactly one row")
        if not rows:
            return None
        row = rows[0]
        if row[1] != "integer":
            raise RuntimeError(f"Unsupported or corrupt research schema version: {row[0]!r}")
        return int(row[0])

    @staticmethod
    def _validate_schema_meta(connection: sqlite3.Connection) -> None:
        """校验 schema_meta 结构；缺行则补写 SCHEMA_VERSION，版本不符则抛错（事务回滚）。"""
        try:
            columns = connection.execute("PRAGMA table_info(schema_meta)").fetchall()
            if (
                len(columns) != 1
                or columns[0][1] != "version"
                or str(columns[0][2]).upper() != "INTEGER"
                or not columns[0][3]
            ):
                raise RuntimeError("Invalid research schema metadata: malformed schema_meta table")
            rows = connection.execute("SELECT version, typeof(version) AS value_type FROM schema_meta").fetchall()
        except sqlite3.DatabaseError as error:
            raise RuntimeError("Invalid research schema metadata: malformed schema_meta table") from error
        if len(rows) > 1:
            raise RuntimeError("Invalid research schema metadata: expected exactly one row")
        if not rows:
            connection.execute("INSERT INTO schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
            return
        row = rows[0]
        if row[1] != "integer" or row[0] != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported or corrupt research schema version: {row[0]!r}")

    def _connect(self) -> sqlite3.Connection:
        """新建跨进程安全的 SQLite 连接。

        `journal_mode=WAL` 是数据库级幂等设置；每个连接重复执行不会改变语义，
        但会让多个 worker 在恢复/调度时可以并发读库，写入仍由 SQLite 串行化。
        `busy_timeout` 与 Python 连接 timeout 同步，避免短暂写锁竞争直接暴露为
        ``database is locked``。
        """
        connection = sqlite3.connect(str(self.database_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    # ------------------------------------------------------------------ #
    # ResearchTask 写 / 读
    # ------------------------------------------------------------------ #

    def create_task(self, task: ResearchTask) -> ResearchTask:
        """插入任务并回读返回。last_event_seq 初始 0；created_at/updated_at 未给则补 UTC。"""
        created_at = task.created_at or _utcnow()
        updated_at = task.updated_at or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO research_tasks(
                        research_task_id, owner_id, project_id, conversation_id, goal, language,
                        quality_profile, review_plan_first, target_paper_count, soft_budget_seconds,
                        status, current_plan_version, last_event_seq, search_id, created_at, updated_at, completed_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task.research_task_id,
                        task.owner_id,
                        task.project_id,
                        task.conversation_id,
                        task.goal,
                        task.language,
                        task.quality_profile,
                        1 if task.review_plan_first else 0,
                        task.target_paper_count,
                        task.soft_budget_seconds,
                        task.status,
                        task.current_plan_version,
                        0,
                        task.search_id,
                        created_at,
                        updated_at,
                        task.completed_at,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=?", (task.research_task_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(row))

    def set_task_search_id(self, research_task_id: str, search_id: str) -> ResearchTask:
        """Persist the first valid server-owned catalog snapshot handle.

        Search handles are opaque server values.  A task may fan out to more
        than one search worker, so the first handle is retained as the stable
        acquisition bridge and is never silently replaced by a later worker.
        Callers must pass a non-empty bounded opaque identifier; no client URL
        or snapshot contents are accepted here.
        """
        value = str(search_id or "").strip()
        if not value or len(value) > 200 or re.search(r"[^A-Za-z0-9._:-]", value):
            raise ValueError("invalid search_id")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=?",
                    (research_task_id,),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchTaskNotFound(research_task_id)
                if row["search_id"] is None:
                    conn.execute(
                        "UPDATE research_tasks SET search_id=?, updated_at=? WHERE research_task_id=? AND search_id IS NULL",
                        (value, _utcnow(), research_task_id),
                    )
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=?",
                    (research_task_id,),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(row))

    def get_task_search_id(self, research_task_id: str) -> str | None:
        """Read the task's persisted catalog snapshot handle for acquisition."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT search_id FROM research_tasks WHERE research_task_id=?",
                (research_task_id,),
            ).fetchone()
        if row is None:
            return None
        value = str(row["search_id"] or "").strip()
        return value or None

    def get_task(self, research_task_id: str, owner_id: str) -> Optional[ResearchTask]:
        """按 owner 隔离读取任务；查不到返回 None（owner 隔离是 Spec027 硬约束）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                (research_task_id, owner_id),
            ).fetchone()
        return ResearchTask.from_row(dict(row)) if row else None

    def list_tasks(
        self,
        owner_id: str,
        *,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> tuple[list[ResearchTask], Optional[str]]:
        """按 (created_at, research_task_id) 升序 keyset 分页列出某 owner 的任务。

        project_id 为 None 时不按项目过滤（返回该 owner 全部）；limit 夹到 1..100；
        无下一页时 next_cursor 为 None。
        """
        limit = max(1, min(int(limit), 100))
        params: list = [owner_id]
        sql = "SELECT * FROM research_tasks WHERE owner_id=?"
        if project_id is not None:
            sql += " AND project_id=?"
            params.append(project_id)
        if status is not None:
            sql += " AND status=?"
            params.append(status)
        if cursor is not None:
            at, tid = decode_cursor(cursor)
            sql += " AND (created_at, research_task_id) > (?, ?)"
            params.extend([at, tid])
        sql += " ORDER BY created_at, research_task_id LIMIT ?"
        params.append(limit + 1)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        items = [ResearchTask.from_row(dict(r)) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last["created_at"], last["research_task_id"])
        return items, next_cursor

    def list_tasks_for_status(self, status: str) -> list[ResearchTask]:
        """Internal recovery snapshot used to attach owner-scoped status facts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_tasks WHERE status=? ORDER BY created_at, research_task_id",
                (status,),
            ).fetchall()
        return [ResearchTask.from_row(dict(row)) for row in rows]

    def update_task_status(
        self,
        research_task_id: str,
        owner_id: str,
        next_status: str,
        *,
        expected_status: str | None = None,
    ) -> ResearchTask | None:
        """按 owner 读当前状态→状态机校验→更新 status/updated_at；终态写 completed_at。

        转移非法时 ``transition_task`` 抛 ``InvalidStateTransition``，**原样向上抛，不吞**。
        """
        if expected_status is not None:
            return self.update_task_status_cas(
                research_task_id, owner_id, expected_status, next_status
            )
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchTaskNotFound(research_task_id)
                current_status = row["status"]
                # 非法转移（含终态→running）在此抛 InvalidStateTransition 并向上传播。
                transition_task(current_status, next_status)
                now = _utcnow()
                if next_status in TASK_TERMINAL:
                    conn.execute(
                        "UPDATE research_tasks SET status=?, updated_at=?, completed_at=? "
                        "WHERE research_task_id=? AND owner_id=?",
                        (next_status, now, now, research_task_id, owner_id),
                    )
                else:
                    conn.execute(
                        "UPDATE research_tasks SET status=?, updated_at=? "
                        "WHERE research_task_id=? AND owner_id=?",
                        (next_status, now, research_task_id, owner_id),
                    )
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(row))

    def update_task_status_cas(
        self,
        research_task_id: str,
        owner_id: str,
        expected_status: str,
        next_status: str,
    ) -> ResearchTask | None:
        """Conditionally transition a task while holding the SQLite write lock.

        The read/validate/write sequence is deliberately kept in one
        ``BEGIN IMMEDIATE`` transaction.  A caller that loses the race gets
        ``None`` and must re-read the task; it must never overwrite the newer
        state or infer success from a stale in-memory snapshot.
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchTaskNotFound(research_task_id)
                if row["status"] != expected_status:
                    conn.commit()
                    return None
                transition_task(row["status"], next_status)
                now = _utcnow()
                if next_status in TASK_TERMINAL:
                    conn.execute(
                        "UPDATE research_tasks SET status=?, updated_at=?, completed_at=? "
                        "WHERE research_task_id=? AND owner_id=? AND status=?",
                        (next_status, now, now, research_task_id, owner_id, expected_status),
                    )
                else:
                    conn.execute(
                        "UPDATE research_tasks SET status=?, updated_at=? "
                        "WHERE research_task_id=? AND owner_id=? AND status=?",
                        (next_status, now, research_task_id, owner_id, expected_status),
                    )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    conn.commit()
                    return None
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(row))

    # Descriptive aliases are intentionally kept on the store seam so callers
    # do not create an application-level second CAS implementation.
    cas_update_task_status = update_task_status_cas
    transition_task_cas = update_task_status_cas

    def pause_task_cas(
        self, research_task_id: str, owner_id: str, *, expected_status: str | None = None
    ) -> ResearchTask | None:
        """CAS pause for an active task; queued WorkItems remain resumable."""
        task = self.get_task(research_task_id, owner_id)
        if task is None:
            raise ResearchTaskNotFound(research_task_id)
        expected = expected_status or task.status
        if task.status == "paused" and expected_status in (None, "paused"):
            return task
        return self.update_task_status_cas(research_task_id, owner_id, expected, "paused")

    def resume_task_cas(
        self, research_task_id: str, owner_id: str, *, expected_status: str = "paused"
    ) -> ResearchTask | None:
        """CAS resume; a stale pause winner cannot resume a newer state."""
        return self.update_task_status_cas(research_task_id, owner_id, expected_status, "running")

    pause_task = pause_task_cas
    resume_task = resume_task_cas

    def cancel_task_cas(
        self, research_task_id: str, owner_id: str, *, expected_status: str | None = None
    ) -> tuple[ResearchTask, int] | None:
        """Atomically cancel a task and all queued/running WorkItems.

        The task status CAS and WorkItem cancellation share one transaction, so
        a scheduler claim cannot interleave and leave a newly queued node after
        cancellation.  Existing terminal WorkItems are retained as evidence.
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchTaskNotFound(research_task_id)
                if expected_status is not None and row["status"] != expected_status:
                    conn.commit()
                    return None
                if row["status"] in TASK_TERMINAL:
                    conn.commit()
                    return ResearchTask.from_row(dict(row)), 0
                transition_task(row["status"], "cancelled")
                now = _utcnow()
                conn.execute(
                    "UPDATE research_tasks SET status='cancelled', updated_at=?, completed_at=? "
                    "WHERE research_task_id=? AND owner_id=? AND status=?",
                    (now, now, research_task_id, owner_id, row["status"]),
                )
                item_rows = conn.execute(
                    "SELECT work_item_id,status FROM research_work_items WHERE research_task_id=? "
                    "AND status IN ('queued','running')",
                    (research_task_id,),
                ).fetchall()
                for item in item_rows:
                    transition_workitem(item["status"], "cancelled")
                    conn.execute(
                        "UPDATE research_work_items SET status='cancelled', ended_at=?, updated_at=? "
                        "WHERE work_item_id=? AND status IN ('queued','running')",
                        (now, now, item["work_item_id"]),
                    )
                updated = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(updated)), len(item_rows)

    def cancel_task(
        self, research_task_id: str, owner_id: str, *, expected_status: str | None = None
    ) -> ResearchTask | None:
        """Compatibility wrapper returning the task projection only."""
        result = self.cancel_task_cas(
            research_task_id, owner_id, expected_status=expected_status
        )
        return result[0] if result is not None else None

    def update_task(self, research_task_id: str, owner_id: str, **fields) -> ResearchTask:
        """部分更新任务白名单字段并刷新 updated_at；不存在抛 ResearchTaskNotFound。

        fields 仅允许白名单；含非法键抛 ValueError（不静默忽略）。
        """
        invalid = set(fields) - _TASK_UPDATE_WHITELIST
        if invalid:
            raise ValueError(f"unknown task fields: {sorted(invalid)}")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchTaskNotFound(research_task_id)
                if fields:
                    set_clauses: list[str] = []
                    params: list = []
                    for key, value in fields.items():
                        set_clauses.append(f"{key}=?")
                        # review_plan_first 是 bool→INTEGER 列，需归一化。
                        params.append(1 if key == "review_plan_first" and value else (0 if key == "review_plan_first" else value))
                    set_clauses.append("updated_at=?")
                    params.append(_utcnow())
                    params.append(research_task_id)
                    params.append(owner_id)
                    conn.execute(
                        f"UPDATE research_tasks SET {', '.join(set_clauses)} WHERE research_task_id=? AND owner_id=?",
                        params,
                    )
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(row))

    def delete_task(self, research_task_id: str, owner_id: str) -> bool:
        """单事务内按子表→主表顺序显式删除该 owner 的任务及其全部私有数据。

        外键为 RESTRICT，故库级不会级联；这里显式按序清子表再删主表，返回是否删到行。
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # 子表无 owner 列，仅按 research_task_id 删除（research_task_id 必属于该 owner）。
                conn.execute("DELETE FROM research_events WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_work_items WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_acquisition_events WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_document_links WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_acquisition_approvals WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_selection_versions WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_evidence_upgrades WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_comparison_cells WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_claim_evidence WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_comparison_dimensions WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_claims WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_reports WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_paper_selections WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM preliminary_reports WHERE research_task_id=?", (research_task_id,))
                conn.execute("DELETE FROM research_plans WHERE research_task_id=?", (research_task_id,))
                cur = conn.execute(
                    "DELETE FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (research_task_id, owner_id),
                )
                deleted = cur.rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return deleted > 0

    def delete_tasks_by_project(self, project_id: str, owner_id: str) -> int:
        """单事务内显式级联删除某 owner 在某项目下的全部任务及其私有数据，返回删除的任务数。

        Spec027 §持久化与并发：级联删除走应用层，**不用 DB 外键 CASCADE**（外键一律 RESTRICT）。
        与 `delete_task` 同源写法，只把「单个 task_id」换成「该项目下该 owner 的全部 task_id」：
        先查 id 集合，再按序清子表，最后删主表，全程一个 `BEGIN IMMEDIATE` 事务（不逐任务开事务）。
        `project_id IS NULL` 的未绑定任务不会被命中（SQL `project_id=?` 不匹配 NULL），
        其它项目、其它 owner 的任务同样不受影响。无匹配任务时返回 0，不抛异常。
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                task_ids = [
                    row["research_task_id"]
                    for row in conn.execute(
                        "SELECT research_task_id FROM research_tasks WHERE project_id=? AND owner_id=?",
                        (project_id, owner_id),
                    ).fetchall()
                ]
                for research_task_id in task_ids:
                    # 子表无 owner 列，仅按 research_task_id 删除（该 id 已由上面的 owner 过滤保证归属）。
                    conn.execute("DELETE FROM research_events WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_work_items WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_acquisition_events WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_document_links WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_acquisition_approvals WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_selection_versions WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_evidence_upgrades WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_comparison_cells WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_claim_evidence WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_comparison_dimensions WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_claims WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_reports WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_paper_selections WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM preliminary_reports WHERE research_task_id=?", (research_task_id,))
                    conn.execute("DELETE FROM research_plans WHERE research_task_id=?", (research_task_id,))
                cur = conn.execute(
                    "DELETE FROM research_tasks WHERE project_id=? AND owner_id=?",
                    (project_id, owner_id),
                )
                deleted = max(int(cur.rowcount), 0)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return deleted

    def list_tasks_by_project(self, project_id: str, owner_id: str) -> list[ResearchTask]:
        """列出某 owner 在某项目下的全部任务（按创建时间升序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_tasks WHERE project_id=? AND owner_id=? ORDER BY created_at, research_task_id",
                (project_id, owner_id),
            ).fetchall()
        return [ResearchTask.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------ #
    # Task09 legacy cleanup (精确 dry-run / all-or-nothing execute)
    # ------------------------------------------------------------------ #

    def _legacy_cleanup_snapshot(self, connection: sqlite3.Connection, owner_id: str | None) -> dict:
        """Build a deterministic, owner-scoped snapshot inside a transaction.

        A task is legacy only when its old ``conversation_id`` is blank and it
        has no Session binding.  A bound task is never silently classified as
        removable, even when its Session is terminal.  Active unbound tasks
        are treated as a hard validation error so execute can never remove a
        live research run.
        """
        params: list[object] = []
        owner_clause = ""
        if owner_id is not None:
            owner_clause = " AND t.owner_id=?"
            params.append(owner_id)
        tasks = connection.execute(
            """SELECT t.* FROM research_tasks t
               WHERE (t.conversation_id IS NULL OR TRIM(t.conversation_id)='')
                 AND NOT EXISTS (
                   SELECT 1 FROM research_sessions s
                   WHERE s.research_task_id=t.research_task_id
                 )""" + owner_clause + " ORDER BY t.created_at, t.research_task_id",
            params,
        ).fetchall()
        active = [row["research_task_id"] for row in tasks if row["status"] not in TASK_TERMINAL]
        removable = [row for row in tasks if row["status"] in TASK_TERMINAL]

        table_specs = (
            ("research_plans", "version", "version"),
            ("research_work_items", "work_item_id", "work_item_id"),
            ("research_events", "event_seq", "event_seq"),
            ("research_acquisition_events", "event_id", "event_id"),
            ("research_document_links", "catalog_paper_id", "catalog_paper_id"),
            ("research_acquisition_approvals", "approval_id", "approval_id"),
            ("research_selection_versions", "research_task_id", "research_task_id"),
            ("research_evidence_upgrades", "claim_id", "claim_id"),
            ("research_comparison_cells", "claim_id", "claim_id"),
            ("research_claim_evidence", "evidence_id", "evidence_id"),
            ("research_comparison_dimensions", "dimension_id", "dimension_id"),
            ("research_claims", "claim_id", "claim_id"),
            ("research_reports", "report_id", "report_id"),
            ("research_paper_selections", "catalog_paper_id", "catalog_paper_id"),
            ("preliminary_reports", "report_id", "report_id"),
            ("research_activity_outbox", "outbox_id", "outbox_id"),
            ("research_agent_runs", "agent_run_id", "agent_run_id"),
            ("research_agent_checkpoints", "checkpoint_ref", "checkpoint_ref"),
            ("research_artifacts", "artifact_id", "artifact_id"),
            ("research_notifications", "notification_id", "notification_id"),
            ("research_projection_retries", "source_event_id", "source_event_id"),
            ("research_plan_activations", "activation_id", "activation_id"),
        )
        targets: list[dict] = []
        for task in tasks:
            task_id = str(task["research_task_id"])
            children: dict[str, list[str]] = {}
            child_counts: dict[str, int] = {}
            for table, id_column, output_column in table_specs:
                # All current stores have these tables.  The existence check
                # keeps a pre-Task04 research DB dry-run readable and avoids
                # turning an absent optional table into a partial delete.
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if exists is None:
                    children[table] = []
                    child_counts[table] = 0
                    continue
                rows = connection.execute(
                    f"SELECT {id_column} FROM {table} WHERE research_task_id=? ORDER BY {id_column}",
                    (task_id,),
                ).fetchall()
                values = [str(row[output_column]) for row in rows]
                children[table] = values
                child_counts[table] = len(values)
            targets.append(
                {
                    "research_task_id": task_id,
                    "owner_id": str(task["owner_id"]),
                    "conversation_id": task["conversation_id"],
                    "status": task["status"],
                    "removable": task["status"] in TASK_TERMINAL,
                    "created_at": task["created_at"],
                    "children": children,
                    "child_counts": child_counts,
                    "child_count": sum(child_counts.values()),
                }
            )
        task_ids = {item["research_task_id"] for item in targets if item["removable"]}
        task_count_sql = "SELECT COUNT(*) FROM research_tasks"
        task_count_params: list[object] = []
        if owner_id is not None:
            task_count_sql += " WHERE owner_id=?"
            task_count_params.append(owner_id)
        all_tasks = connection.execute(task_count_sql, task_count_params).fetchone()[0]
        bound_tasks = connection.execute(
            """SELECT COUNT(*) FROM research_tasks t
               WHERE (t.conversation_id IS NOT NULL AND TRIM(t.conversation_id)!='')
                  OR EXISTS (SELECT 1 FROM research_sessions s WHERE s.research_task_id=t.research_task_id)"""
            + (" AND t.owner_id=?" if owner_id is not None else ""),
            ([owner_id] if owner_id is not None else []),
        ).fetchone()[0]
        active_sessions = connection.execute(
            "SELECT COUNT(*) FROM research_sessions WHERE status NOT IN ('interrupted','partial','completed','failed','cancelled')"
            + (" AND owner_id=?" if owner_id is not None else ""),
            ([owner_id] if owner_id is not None else []),
        ).fetchone()[0]
        return {
            "owner_id": owner_id,
            "target_task_ids": sorted(task_ids),
            "targets": targets,
            "counts": {
                "tasks_total": int(all_tasks),
                "candidate_tasks": len(targets),
                "target_tasks": len(removable),
                "target_children": sum(item["child_count"] for item in targets if item["removable"]),
            },
            "protected_counts": {
                "bound_tasks": int(bound_tasks),
                "active_sessions": int(active_sessions),
                "blocked_active_legacy_tasks": len(active),
            },
            "validation_errors": ([
                {"code": "LEGACY_CLEANUP_ACTIVE_RESEARCH", "task_ids": sorted(active)}
            ] if active else []),
        }

    @staticmethod
    def _cross_store_snapshot(external_snapshot: Callable[[], dict] | None) -> dict:
        if external_snapshot is None:
            return {
                "status": "unverified", "reason": "external snapshot provider not supplied",
                "sessions": None, "catalog": None, "kb": None,
            }
        value = external_snapshot()
        if not isinstance(value, dict):
            raise LegacyCleanupError("LEGACY_CLEANUP_AUDIT_INVALID", "external snapshot must be an object")
        # Keep the audit shape explicit even when an operator only wires one
        # external store.  Missing stores are *unverified*, never implicitly
        # unchanged.
        snapshot = {"sessions": value.get("sessions"), "catalog": value.get("catalog"), "kb": value.get("kb")}
        if not all(name in value and value.get(name) is not None for name in ("sessions", "catalog", "kb")):
            snapshot["status"] = "unverified"
            snapshot["reason"] = "sessions/catalog/kb snapshot is incomplete"
            return snapshot
        status = value.get("status", "measured")
        if status not in {"measured", "unverified"}:
            raise LegacyCleanupError("LEGACY_CLEANUP_AUDIT_INVALID", "external snapshot status is invalid")
        snapshot["status"] = status
        if value.get("reason") is not None:
            snapshot["reason"] = str(value["reason"])
        return snapshot

    def dry_run_legacy_cleanup(
        self, owner_id: str | None = None, *, external_snapshot: Callable[[], dict] | None = None,
    ) -> dict:
        """Return and persist a non-mutating cleanup plan.

        The only write is the audit row; no Task or child row is changed.
        ``owner_id`` is optional for operator maintenance, but API callers
        should always pass the authenticated owner to preserve isolation.
        """
        cleanup_id = uuid.uuid4().hex
        with _write_lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                snapshot = self._legacy_cleanup_snapshot(connection, owner_id)
                report = {
                    "cleanup_id": cleanup_id, "mode": "dry_run", "status": "planned", **snapshot,
                    "cross_store": {"before": self._cross_store_snapshot(external_snapshot), "after": None, "unchanged": None},
                }
                connection.execute(
                    "INSERT INTO research_legacy_cleanup_audits(cleanup_id, owner_id, mode, status, report_json, created_at) VALUES(?,?,?,?,?,?)",
                    (cleanup_id, owner_id, "dry_run", "planned", json.dumps(report, ensure_ascii=False, sort_keys=True), _utcnow()),
                )
                connection.commit()
                return report
            except Exception:
                connection.rollback()
                raise

    def execute_legacy_cleanup(
        self, owner_id: str | None = None, *, confirm: bool = False, dry_run_id: str | None = None,
        external_snapshot: Callable[[], dict] | None = None,
    ) -> dict:
        """Delete only validated legacy Tasks and all private children atomically.

        ``confirm`` is an explicit maintenance guard.  Selection, active
        Session checks, per-table row counts, and final Task deletion all run
        under one ``BEGIN IMMEDIATE``.  Any mismatch/exception rolls back the
        complete delete, including its audit row.
        """
        if not confirm:
            raise LegacyCleanupError("LEGACY_CLEANUP_CONFIRMATION_REQUIRED", "cleanup requires confirm=True")
        if not dry_run_id:
            raise LegacyCleanupError("LEGACY_CLEANUP_DRY_RUN_REQUIRED", "execute requires a matching dry-run audit id")
        cleanup_id = uuid.uuid4().hex
        delete_order = (
            "research_artifacts", "research_agent_checkpoints", "research_notifications",
            "research_projection_retries", "research_agent_runs", "research_activity_outbox",
            "research_plan_activations", "research_events", "research_work_items",
            "research_acquisition_events", "research_document_links", "research_acquisition_approvals",
            "research_selection_versions", "research_evidence_upgrades",
            "research_comparison_cells", "research_claim_evidence", "research_comparison_dimensions", "research_claims",
            "research_paper_selections", "preliminary_reports", "research_plans",
        )
        # Keep these outside the transaction so the rollback audit can retain
        # the evidence that caused an abort, including the post-rollback
        # research-store snapshot.
        snapshot: dict | None = None
        after: dict | None = None
        cross_before: dict | None = None
        cross_after: dict | None = None
        cross_status = "not_evaluated"
        deleted: dict[str, int] = dict.fromkeys(delete_order, 0)
        with _write_lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                snapshot = self._legacy_cleanup_snapshot(connection, owner_id)
                if snapshot["validation_errors"]:
                    raise LegacyCleanupError("LEGACY_CLEANUP_ACTIVE_RESEARCH", "active legacy research tasks cannot be cleaned")
                audit_row = connection.execute(
                    "SELECT * FROM research_legacy_cleanup_audits WHERE cleanup_id=? AND owner_id IS ? AND mode='dry_run' AND status='planned'",
                    (dry_run_id, owner_id),
                ).fetchone()
                if audit_row is None:
                    raise LegacyCleanupError("LEGACY_CLEANUP_DRY_RUN_INVALID", "dry-run audit is missing, consumed, or owner-mismatched")
                try:
                    dry_report = json.loads(audit_row["report_json"])
                    created_at = datetime.fromisoformat(str(audit_row["created_at"]).replace("Z", "+00:00"))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise LegacyCleanupError("LEGACY_CLEANUP_DRY_RUN_INVALID", "dry-run audit is malformed") from exc
                if (datetime.now(timezone.utc) - created_at).total_seconds() > 3600:
                    raise LegacyCleanupError("LEGACY_CLEANUP_DRY_RUN_EXPIRED", "dry-run audit is older than one hour")
                if dry_report.get("target_task_ids") != snapshot.get("target_task_ids") or dry_report.get("targets") != snapshot.get("targets"):
                    raise LegacyCleanupError("LEGACY_CLEANUP_TARGET_CHANGED", "legacy cleanup targets changed after dry-run")
                if not snapshot["target_task_ids"]:
                    raise LegacyCleanupError("LEGACY_CLEANUP_NO_MATCH", "dry-run selected no removable legacy tasks")
                cross_before = self._cross_store_snapshot(external_snapshot)
                if cross_before["status"] == "unverified":
                    cross_status = "unverified"
                    # Capture the second side even though no business delete
                    # is attempted, so the aborted audit always has a
                    # before/after cross-store record.
                    cross_after = self._cross_store_snapshot(external_snapshot)
                    raise LegacyCleanupError(
                        "LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED",
                        "sessions/catalog/kb cross-store snapshot is unverified",
                    )
                task_ids = snapshot["target_task_ids"]
                placeholders = ",".join("?" for _ in task_ids)
                if task_ids:
                    for table in delete_order:
                        exists = connection.execute(
                            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                        ).fetchone()
                        if exists is None:
                            continue
                        cursor = connection.execute(
                            f"DELETE FROM {table} WHERE research_task_id IN ({placeholders})",
                            task_ids,
                        )
                        deleted[table] = max(int(cursor.rowcount), 0)
                    task_cursor = connection.execute(
                        f"DELETE FROM research_tasks WHERE research_task_id IN ({placeholders})"
                        + (" AND owner_id=?" if owner_id is not None else ""),
                        (*task_ids, owner_id) if owner_id is not None else task_ids,
                    )
                    deleted["research_tasks"] = max(int(task_cursor.rowcount), 0)
                    if deleted["research_tasks"] != len(task_ids):
                        raise LegacyCleanupError("LEGACY_CLEANUP_VALIDATION_FAILED", "target Task count changed during cleanup")
                expected: dict[str, int] = dict.fromkeys(delete_order, 0)
                for item in snapshot["targets"]:
                    for table, count in item["child_counts"].items():
                        if table in expected:
                            expected[table] += int(count)
                for table, count in expected.items():
                    if deleted[table] != count:
                        raise LegacyCleanupError(
                            "LEGACY_CLEANUP_VALIDATION_FAILED",
                            f"child count mismatch for {table}: expected {count}, deleted {deleted[table]}",
                        )
                after = self._legacy_cleanup_snapshot(connection, owner_id)
                cross_after = self._cross_store_snapshot(external_snapshot)
                if cross_after["status"] == "unverified":
                    cross_status = "unverified"
                    raise LegacyCleanupError(
                        "LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED",
                        "sessions/catalog/kb cross-store snapshot is unverified",
                    )
                cross_unchanged = all(
                    cross_before[name] == cross_after[name]
                    for name in ("sessions", "catalog", "kb")
                )
                if not cross_unchanged:
                    cross_status = "changed"
                    raise LegacyCleanupError(
                        "LEGACY_CLEANUP_CROSS_STORE_CHANGED",
                        "sessions/catalog/kb changed during legacy cleanup",
                    )
                cross_status = "unchanged"
                report = {
                    "cleanup_id": cleanup_id, "mode": "execute", "status": "completed",
                    "before": snapshot, "deleted": {"research_tasks": deleted.get("research_tasks", 0), "children": deleted},
                    "after": after, "cross_store": {
                        "before": cross_before, "after": cross_after,
                        "unchanged": True, "status": cross_status,
                    },
                }
                connection.execute(
                    "INSERT INTO research_legacy_cleanup_audits(cleanup_id, owner_id, mode, status, report_json, created_at) VALUES(?,?,?,?,?,?)",
                    (cleanup_id, owner_id, "execute", "completed", json.dumps(report, ensure_ascii=False, sort_keys=True), _utcnow()),
                )
                connection.execute(
                    "UPDATE research_legacy_cleanup_audits SET status='completed' WHERE cleanup_id=?",
                    (dry_run_id,),
                )
                connection.commit()
                return report
            except Exception as error:
                connection.rollback()
                # Verify the rollback result from a fresh connection.  This
                # is evidence only; the original cleanup error remains
                # authoritative if the verification itself fails.
                try:
                    with self._connect() as verification_connection:
                        after = self._legacy_cleanup_snapshot(verification_connection, owner_id)
                except Exception:
                    after = None
                # Failure evidence is intentionally a small, payload-free
                # audit row written after the deletion transaction rolls back;
                # it cannot make any partial delete visible.
                failure = {
                    "cleanup_id": cleanup_id,
                    "mode": "execute",
                    "status": "aborted",
                    "error_code": getattr(error, "code", "LEGACY_CLEANUP_FAILED"),
                    "message": str(error)[:240],
                    "before": snapshot,
                    "after": after,
                    "deleted": {
                        "research_tasks": 0,
                        "children": dict.fromkeys(delete_order, 0),
                    },
                    "attempted": {
                        "research_tasks": deleted.get("research_tasks", 0),
                        "children": deleted,
                    },
                    "cross_store": {
                        "before": cross_before,
                        "after": cross_after,
                        "unchanged": False,
                        "status": cross_status,
                    },
                }
                try:
                    with self._connect() as audit_connection:
                        audit_connection.execute(
                            "INSERT INTO research_legacy_cleanup_audits(cleanup_id, owner_id, mode, status, report_json, created_at) VALUES(?,?,?,?,?,?)",
                            (cleanup_id, owner_id, "execute", "aborted", json.dumps(failure, ensure_ascii=False, sort_keys=True), _utcnow()),
                        )
                except Exception:
                    # The original cleanup error is authoritative.
                    pass
                raise

    def list_legacy_cleanup_audits(self, owner_id: str | None = None, *, limit: int = 20) -> list[dict]:
        """Read persisted cleanup audit reports without exposing payload data."""
        clause = " WHERE owner_id=?" if owner_id is not None else ""
        params = [owner_id] if owner_id is not None else []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT report_json FROM research_legacy_cleanup_audits" + clause + " ORDER BY created_at DESC, cleanup_id DESC LIMIT ?",
                (*params, max(1, min(int(limit), 100))),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_session_create_request(self, owner_id: str, idempotency_key: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_session_create_requests WHERE owner_id=? AND idempotency_key=?",
                (owner_id, idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def save_session_create_request(
        self, *, owner_id: str, idempotency_key: str, request_fingerprint: str,
        research_session_id: str, conversation_id: str, trigger_message_id: str,
        response: dict,
    ) -> dict:
        """Persist a safe create response under an owner/key CAS."""
        now = _utcnow()
        response_json = json.dumps(response, ensure_ascii=False, sort_keys=True)
        with _write_lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM research_session_create_requests WHERE owner_id=? AND idempotency_key=?",
                    (owner_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_fingerprint"] != request_fingerprint:
                        raise LegacyCleanupError("SESSION_CREATE_IDEMPOTENCY_CONFLICT", "idempotency key reused with a different request")
                    connection.commit()
                    return dict(existing)
                connection.execute(
                    "INSERT INTO research_session_create_requests(owner_id,idempotency_key,request_fingerprint,research_session_id,conversation_id,trigger_message_id,response_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (owner_id, idempotency_key, request_fingerprint, research_session_id, conversation_id, trigger_message_id, response_json, now, now),
                )
                row = connection.execute(
                    "SELECT * FROM research_session_create_requests WHERE owner_id=? AND idempotency_key=?",
                    (owner_id, idempotency_key),
                ).fetchone()
                connection.commit()
                return dict(row)
            except Exception:
                connection.rollback()
                raise

    # ------------------------------------------------------------------ #
    # ResearchPlan 写 / 读
    # ------------------------------------------------------------------ #

    def create_plan(self, plan: ResearchPlan) -> ResearchPlan:
        """插入计划版本；同一 (research_task_id, version) 已存在则抛 ResearchPlanConflict（版本不可覆盖）。"""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT 1 FROM research_plans WHERE research_task_id=? AND version=?",
                    (plan.research_task_id, plan.version),
                ).fetchone()
                if existing is not None:
                    conn.rollback()
                    raise ResearchPlanConflict(plan.research_task_id, plan.version)
                conn.execute(
                    """INSERT INTO research_plans(
                        research_task_id, version, planner_model, rationale_summary, facets_json, status, created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        plan.research_task_id,
                        plan.version,
                        plan.planner_model,
                        plan.rationale_summary,
                        plan.facets_json,
                        plan.status,
                        plan.created_at or _utcnow(),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_plans WHERE research_task_id=? AND version=?",
                    (plan.research_task_id, plan.version),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchPlan.from_row(dict(row))

    def create_plan_version_cas(
        self,
        plan: ResearchPlan,
        owner_id: str,
        *,
        expected_current_version: int,
    ) -> tuple[ResearchPlan, ResearchTask] | None:
        """Append an immutable task plan and advance its version pointer atomically.

        A stale planner/review callback returns ``None``.  The existing plan
        row is never updated or replaced, which makes an old callback
        auditable while preventing it from silently becoming the current plan.
        """
        if int(plan.version) != int(expected_current_version) + 1:
            raise ValueError("plan version must advance by exactly one")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                task_row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (plan.research_task_id, owner_id),
                ).fetchone()
                if task_row is None:
                    conn.rollback()
                    raise ResearchTaskNotFound(plan.research_task_id)
                if int(task_row["current_plan_version"]) != int(expected_current_version):
                    conn.commit()
                    return None
                if conn.execute(
                    "SELECT 1 FROM research_plans WHERE research_task_id=? AND version=?",
                    (plan.research_task_id, int(plan.version)),
                ).fetchone() is not None:
                    conn.commit()
                    raise ResearchPlanConflict(plan.research_task_id, plan.version)
                conn.execute(
                    """INSERT INTO research_plans(
                        research_task_id,version,planner_model,rationale_summary,facets_json,status,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        plan.research_task_id, int(plan.version), plan.planner_model,
                        plan.rationale_summary, plan.facets_json, plan.status,
                        plan.created_at or _utcnow(),
                    ),
                )
                now = _utcnow()
                changed = conn.execute(
                    "UPDATE research_tasks SET current_plan_version=?, updated_at=? "
                    "WHERE research_task_id=? AND owner_id=? AND current_plan_version=?",
                    (int(plan.version), now, plan.research_task_id, owner_id, int(expected_current_version)),
                ).rowcount
                if changed != 1:
                    conn.rollback()
                    return None
                saved_plan = conn.execute(
                    "SELECT * FROM research_plans WHERE research_task_id=? AND version=?",
                    (plan.research_task_id, int(plan.version)),
                ).fetchone()
                saved_task = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (plan.research_task_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchPlan.from_row(dict(saved_plan)), ResearchTask.from_row(dict(saved_task))

    append_plan_version_cas = create_plan_version_cas

    def get_plan(self, research_task_id: str, version: int) -> Optional[ResearchPlan]:
        """读取指定版本计划；不存在返回 None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_plans WHERE research_task_id=? AND version=?",
                (research_task_id, version),
            ).fetchone()
        return ResearchPlan.from_row(dict(row)) if row else None

    def list_plans(self, research_task_id: str) -> list[ResearchPlan]:
        """列出某任务全部计划版本（按 version 升序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_plans WHERE research_task_id=? ORDER BY version ASC",
                (research_task_id,),
            ).fetchall()
        return [ResearchPlan.from_row(dict(r)) for r in rows]

    def get_current_plan(self, research_task_id: str) -> Optional[ResearchPlan]:
        """取最大版本计划（当前计划）；不存在返回 None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_plans WHERE research_task_id=? ORDER BY version DESC LIMIT 1",
                (research_task_id,),
            ).fetchone()
        return ResearchPlan.from_row(dict(row)) if row else None

    def update_plan_status(self, research_task_id: str, version: int, next_status: str) -> ResearchPlan:
        """更新计划状态；next_status 必须属于 PLAN_STATUSES，否则 ValueError；不存在抛 ResearchPlanNotFound。"""
        if next_status not in PLAN_STATUSES:
            raise ValueError(f"invalid plan status: {next_status}")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_plans WHERE research_task_id=? AND version=?",
                    (research_task_id, version),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchPlanNotFound(research_task_id, version)
                conn.execute(
                    "UPDATE research_plans SET status=? WHERE research_task_id=? AND version=?",
                    (next_status, research_task_id, version),
                )
                row = conn.execute(
                    "SELECT * FROM research_plans WHERE research_task_id=? AND version=?",
                    (research_task_id, version),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchPlan.from_row(dict(row))

    # ------------------------------------------------------------------ #
    # ResearchWorkItem 写 / 读
    # ------------------------------------------------------------------ #

    def create_work_items(self, research_task_id: str, items: list[ResearchWorkItem]) -> list[ResearchWorkItem]:
        """单事务批量插入 WorkItem；任一 item 的 task_type/role 不在白名单则整批回滚并抛 ValueError。"""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                for it in items:
                    if it.task_type not in TASK_TYPE_WHITELIST:
                        conn.rollback()
                        raise ValueError(f"unknown task_type: {it.task_type}")
                    if it.role not in ROLE_WHITELIST:
                        conn.rollback()
                        raise ValueError(f"unknown role: {it.role}")
                now = _utcnow()
                for it in items:
                    conn.execute(
                        """INSERT INTO research_work_items(
                            work_item_id, research_task_id, plan_version, task_type, role,
                            depends_on_json, input_json, output_json, model_tier, resolved_model,
                            worker_slot, status, attempt, error_code, started_at, ended_at,
                            retry_count, next_retry_at, last_error_code, created_at, updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            it.work_item_id,
                            research_task_id,
                            it.plan_version,
                            it.task_type,
                            it.role,
                            it.depends_on_json,
                            it.input_json,
                            it.output_json,
                            it.model_tier,
                            it.resolved_model,
                            it.worker_slot,
                            it.status,
                            it.attempt,
                            it.error_code,
                            it.started_at,
                            it.ended_at,
                            it.retry_count,
                            it.next_retry_at,
                            it.last_error_code,
                            it.created_at or now,
                            it.updated_at or now,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        result: list[ResearchWorkItem] = []
        for it in items:
            wi = self.get_work_item(it.work_item_id)
            if wi is not None:
                result.append(wi)
        return result

    def get_work_item(self, work_item_id: str) -> Optional[ResearchWorkItem]:
        """读取单个 WorkItem；不存在返回 None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)
            ).fetchone()
        return ResearchWorkItem.from_row(dict(row)) if row else None

    def update_work_item_input(self, work_item_id: str, input_json: str) -> ResearchWorkItem:
        """Persist the bounded upstream-result injection before dispatch."""
        if not isinstance(input_json, str) or len(input_json) > 100_000:
            raise ValueError("work item input is invalid")
        with _write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE research_work_items SET input_json=?, updated_at=? WHERE work_item_id=?",
                (input_json, _utcnow(), work_item_id),
            )
            row = conn.execute("SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)).fetchone()
        if row is None:
            raise ResearchWorkItemNotFound(work_item_id)
        return ResearchWorkItem.from_row(dict(row))

    def schedule_work_item_retry(
        self,
        work_item_id: str,
        *,
        error_code: str,
        next_retry_at: str,
        retry_count: int | None = None,
    ) -> ResearchWorkItem:
        """Atomically move a live WorkItem to durable ``waiting_retry``.

        Terminal rows win races with a late failure and are returned untouched;
        this prevents a stale worker from reopening completed evidence.
        """
        if not error_code or not next_retry_at:
            raise ValueError("error_code and next_retry_at are required")
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)
                ).fetchone()
                if row is None:
                    raise ResearchWorkItemNotFound(work_item_id)
                current = row["status"]
                if current in WORKITEM_TERMINAL:
                    conn.commit()
                    return ResearchWorkItem.from_row(dict(row))
                if current != "waiting_retry":
                    transition_workitem(current, "waiting_retry")
                count = int(row["retry_count"] or 0) + 1 if retry_count is None else int(retry_count)
                if count < 1:
                    raise ValueError("retry_count must be positive")
                now = _utcnow()
                conn.execute(
                    """UPDATE research_work_items
                       SET status='waiting_retry', retry_count=?, next_retry_at=?,
                           last_error_code=?, error_code=?, ended_at=NULL, updated_at=?
                       WHERE work_item_id=? AND status NOT IN ('completed','failed','cancelled','interrupted')""",
                    (count, next_retry_at, error_code, error_code, now, work_item_id),
                )
                row = conn.execute(
                    "SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchWorkItem.from_row(dict(row))

    def requeue_due_work_items(self, *, now: str | None = None, research_task_id: str | None = None) -> int:
        """Make due waiting items claimable in one transaction after restart."""
        current = now or _utcnow()
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                clauses = ["status='waiting_retry'", "(next_retry_at IS NULL OR next_retry_at<=?)"]
                params: list[object] = [current]
                if research_task_id is not None:
                    clauses.append("research_task_id=?")
                    params.append(research_task_id)
                changed = conn.execute(
                    f"UPDATE research_work_items SET status='queued', next_retry_at=NULL, updated_at=? WHERE {' AND '.join(clauses)}",
                    [current, *params],
                ).rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return int(changed)

    def list_work_items(
        self, research_task_id: str, *, plan_version: Optional[int] = None
    ) -> list[ResearchWorkItem]:
        """列出某任务的 WorkItem；可按月计划版本过滤（按创建时间升序）。"""
        params: list = [research_task_id]
        sql = "SELECT * FROM research_work_items WHERE research_task_id=?"
        if plan_version is not None:
            sql += " AND plan_version=?"
            params.append(plan_version)
        sql += " ORDER BY created_at, work_item_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ResearchWorkItem.from_row(dict(r)) for r in rows]

    def update_work_item_status(
        self,
        work_item_id: str,
        next_status: str,
        *,
        error_code: Optional[str] = None,
        output_json: Optional[str] = None,
        resolved_model: Optional[str] = None,
        model_tier: Optional[str] = None,
        worker_slot: Optional[str] = None,
        attempt: Optional[int] = None,
        retry_count: Optional[int] = None,
        next_retry_at: Optional[str] = None,
        last_error_code: Optional[str] = None,
    ) -> ResearchWorkItem:
        """更新 WorkItem 状态并可选写回结果字段；状态机校验非法则抛 InvalidStateTransition。

        next_status==running 且 started_at 为空时写 started_at；终态写 ended_at；
        attempt 非 None 时覆盖（重试计数）；其他字段仅当非 None 时更新。不存在抛 ResearchWorkItemNotFound。
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)
                ).fetchone()
                if row is None:
                    conn.rollback()
                    raise ResearchWorkItemNotFound(work_item_id)
                current_status = row["status"]
                # AgentRunner owns the live WorkItem projection and may reach
                # a terminal state before the orchestrator has serialized the
                # returned AgentRunOutput.  Allow that same terminal state to
                # receive its result payload exactly once; a different
                # terminal state or any rewind still goes through the strict
                # state machine and is rejected.
                same_terminal_writeback = (
                    current_status == next_status
                    and current_status in WORKITEM_TERMINAL
                    and any(value is not None for value in (
                        error_code, output_json, resolved_model, model_tier,
                        worker_slot, attempt, retry_count, next_retry_at, last_error_code,
                    ))
                )
                if not same_terminal_writeback:
                    transition_workitem(current_status, next_status)
                now = _utcnow()
                set_clauses: list[str] = ["status=?"]
                params: list = [next_status]
                if next_status == "running" and row["started_at"] is None:
                    set_clauses.append("started_at=?")
                    params.append(now)
                if next_status in WORKITEM_TERMINAL:
                    set_clauses.append("ended_at=?")
                    params.append(now)
                if error_code is not None:
                    set_clauses.append("error_code=?")
                    params.append(error_code)
                if output_json is not None:
                    set_clauses.append("output_json=?")
                    params.append(output_json)
                if resolved_model is not None:
                    set_clauses.append("resolved_model=?")
                    params.append(resolved_model)
                if model_tier is not None:
                    set_clauses.append("model_tier=?")
                    params.append(model_tier)
                if worker_slot is not None:
                    set_clauses.append("worker_slot=?")
                    params.append(worker_slot)
                if attempt is not None:
                    set_clauses.append("attempt=?")
                    params.append(attempt)
                if retry_count is not None:
                    if int(retry_count) < 0:
                        raise ValueError("retry_count must be non-negative")
                    set_clauses.append("retry_count=?")
                    params.append(int(retry_count))
                if next_retry_at is not None:
                    set_clauses.append("next_retry_at=?")
                    params.append(next_retry_at)
                if last_error_code is not None:
                    set_clauses.append("last_error_code=?")
                    params.append(last_error_code)
                set_clauses.append("updated_at=?")
                params.append(now)
                params.append(work_item_id)
                conn.execute(
                    f"UPDATE research_work_items SET {', '.join(set_clauses)} WHERE work_item_id=?",
                    params,
                )
                row = conn.execute(
                    "SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchWorkItem.from_row(dict(row))

    # ------------------------------------------------------------------ #
    # Spec028 durable scheduler: leases, checkpoints and reservations
    # ------------------------------------------------------------------ #

    def claim_scheduler_lease(
        self,
        task_id: str,
        owner_token: str | None = None,
        *,
        lease_seconds: int = 60,
        now: str | None = None,
    ) -> SchedulerLease | None:
        """Atomically claim an unowned/expired lease.

        SQLite's ``BEGIN IMMEDIATE`` is the cross-process CAS boundary.  An
        active owner is never overwritten, and the token is generated before
        entering the transaction so callers can safely persist it alongside a
        worker invocation.
        """
        if not task_id:
            raise ValueError("task_id is required")
        token = owner_token or uuid.uuid4().hex
        current = now or _utcnow()
        expiry = _utc_after(lease_seconds, current)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                row = conn.execute(
                    "SELECT * FROM scheduler_leases WHERE task_id=?", (task_id,)
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO scheduler_leases(task_id,owner_token,expires_at,heartbeat_at) VALUES(?,?,?,?)",
                        (task_id, token, expiry, current),
                    )
                elif row["owner_token"] and row["expires_at"] and row["expires_at"] > current:
                    conn.commit()
                    return None
                else:
                    changed = conn.execute(
                        """UPDATE scheduler_leases SET owner_token=?, expires_at=?, heartbeat_at=?
                           WHERE task_id=? AND (owner_token IS NULL OR expires_at IS NULL OR expires_at<=?)""",
                        (token, expiry, current, task_id, current),
                    ).rowcount
                    if changed != 1:
                        conn.commit()
                        return None
                row = conn.execute("SELECT * FROM scheduler_leases WHERE task_id=?", (task_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return SchedulerLease.from_row(dict(row))

    def get_scheduler_lease(self, task_id: str) -> SchedulerLease | None:
        with self._connect() as conn:
            self._ensure_scheduler_schema(conn)
            row = conn.execute("SELECT * FROM scheduler_leases WHERE task_id=?", (task_id,)).fetchone()
        return SchedulerLease.from_row(dict(row)) if row else None

    def list_scheduler_leases(self, *, now: str | None = None) -> list[SchedulerLease]:
        """Return currently active leases without exposing owner tokens.

        The scheduler status projection only needs an aggregate count.  Keep
        this read model scoped to non-expired ownership so callers cannot
        accidentally report stale leases as active after a restart.
        """
        current = now or _utcnow()
        with self._connect() as conn:
            self._ensure_scheduler_schema(conn)
            rows = conn.execute(
                """SELECT * FROM scheduler_leases
                   WHERE owner_token IS NOT NULL AND expires_at IS NOT NULL AND expires_at>?
                   ORDER BY task_id""",
                (current,),
            ).fetchall()
        return [SchedulerLease.from_row(dict(row)) for row in rows]

    def claim_work_item(
        self,
        work_item_id: str,
        owner_token: str,
        *,
        lease_seconds: int = 60,
        now: str | None = None,
    ) -> ResearchWorkItem | None:
        """Claim a queued WorkItem and its lease in one SQLite transaction."""
        if not work_item_id or not owner_token:
            raise ValueError("work_item_id and owner_token are required")
        current = now or _utcnow()
        expiry = _utc_after(lease_seconds, current)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                item = conn.execute(
                    "SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)
                ).fetchone()
                if item is None:
                    conn.rollback()
                    raise ResearchWorkItemNotFound(work_item_id)
                if item["status"] != "queued":
                    conn.commit()
                    return None
                # Keep the existing domain state machine authoritative even
                # though the lease and status CAS share one transaction.
                transition_workitem(item["status"], "running")
                lease = conn.execute("SELECT * FROM scheduler_leases WHERE task_id=?", (work_item_id,)).fetchone()
                if lease is not None and lease["owner_token"] and lease["expires_at"] and lease["expires_at"] > current:
                    conn.commit()
                    return None
                conn.execute(
                    """INSERT INTO scheduler_leases(task_id,owner_token,expires_at,heartbeat_at) VALUES(?,?,?,?)
                       ON CONFLICT(task_id) DO UPDATE SET owner_token=excluded.owner_token,expires_at=excluded.expires_at,heartbeat_at=excluded.heartbeat_at""",
                    (work_item_id, owner_token, expiry, current),
                )
                changed = conn.execute(
                    "UPDATE research_work_items SET status='running',started_at=COALESCE(started_at,?),attempt=attempt+1,updated_at=? WHERE work_item_id=? AND status='queued'",
                    (current, current, work_item_id),
                ).rowcount
                if changed != 1:
                    conn.rollback()
                    return None
                row = conn.execute("SELECT * FROM research_work_items WHERE work_item_id=?", (work_item_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchWorkItem.from_row(dict(row))

    def heartbeat_scheduler_lease(
        self,
        task_id: str,
        owner_token: str,
        *,
        lease_seconds: int = 60,
        now: str | None = None,
    ) -> SchedulerLease | None:
        """Extend a lease only while its exact token is still current."""
        if not owner_token:
            return None
        current = now or _utcnow()
        expiry = _utc_after(lease_seconds, current)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                changed = conn.execute(
                    """UPDATE scheduler_leases SET expires_at=?, heartbeat_at=?
                       WHERE task_id=? AND owner_token=? AND expires_at>?""",
                    (expiry, current, task_id, owner_token, current),
                ).rowcount
                row = conn.execute("SELECT * FROM scheduler_leases WHERE task_id=?", (task_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return SchedulerLease.from_row(dict(row)) if changed == 1 and row else None

    def release_scheduler_lease(self, task_id: str, owner_token: str) -> bool:
        """Release only the owner-held lease; stale workers cannot clear it."""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                changed = conn.execute(
                    """UPDATE scheduler_leases SET owner_token=NULL, expires_at=NULL, heartbeat_at=NULL
                       WHERE task_id=? AND owner_token=?""",
                    (task_id, owner_token),
                ).rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return changed == 1

    def recover_expired_scheduler_leases(self, *, now: str | None = None) -> int:
        """Clear expired lease owners, returning the number made available."""
        current = now or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                changed = conn.execute(
                    """UPDATE scheduler_leases SET owner_token=NULL, expires_at=NULL, heartbeat_at=NULL
                       WHERE owner_token IS NOT NULL AND (expires_at IS NULL OR expires_at<=?)""",
                    (current,),
                ).rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return max(0, int(changed))

    def save_scheduler_checkpoint(
        self,
        task_id: str | SchedulerCheckpoint,
        plan_version: int | None = None,
        node_id: str | None = None,
        state_json: str | dict | list | None = None,
        input_digest: str | None = None,
        *,
        now: str | None = None,
    ) -> SchedulerCheckpoint:
        """Persist a validated checkpoint before a node advances.

        Dict/list state is encoded canonically.  A caller-supplied digest must
        match the exact persisted bytes, preventing a corrupt checkpoint from
        being treated as resumable after restart.
        """
        if isinstance(task_id, SchedulerCheckpoint):
            checkpoint = task_id
            task_id, plan_version, node_id, state_json = (
                checkpoint.task_id, checkpoint.plan_version, checkpoint.node_id, checkpoint.state_json
            )
            input_digest = input_digest or checkpoint.input_digest
        if not task_id or plan_version is None or not node_id or state_json is None:
            raise ValueError("checkpoint identity is incomplete")
        if isinstance(state_json, str):
            try:
                parsed = json.loads(state_json)
            except (TypeError, ValueError) as exc:
                raise ValueError("checkpoint state must be valid JSON") from exc
            if not isinstance(parsed, (dict, list)):
                raise ValueError("checkpoint state must be an object or array")
            content = state_json
        elif isinstance(state_json, (dict, list)):
            content = json.dumps(state_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        else:
            raise ValueError("checkpoint state must be JSON")
        if len(content.encode("utf-8")) > 200_000:
            raise ValueError("checkpoint state is too large")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if input_digest is not None and input_digest != digest:
            raise ValueError("checkpoint input digest mismatch")
        current = now or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                conn.execute(
                    """INSERT INTO scheduler_checkpoints(task_id,plan_version,node_id,state_json,input_digest,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(task_id,plan_version,node_id) DO UPDATE SET
                         state_json=excluded.state_json,input_digest=excluded.input_digest,updated_at=excluded.updated_at""",
                    (task_id, int(plan_version), node_id, content, digest, current, current),
                )
                row = conn.execute(
                    "SELECT * FROM scheduler_checkpoints WHERE task_id=? AND plan_version=? AND node_id=?",
                    (task_id, int(plan_version), node_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return SchedulerCheckpoint.from_row(dict(row))

    def get_scheduler_checkpoint(self, task_id: str, plan_version: int, node_id: str) -> SchedulerCheckpoint | None:
        with self._connect() as conn:
            self._ensure_scheduler_schema(conn)
            row = conn.execute(
                "SELECT * FROM scheduler_checkpoints WHERE task_id=? AND plan_version=? AND node_id=?",
                (task_id, int(plan_version), node_id),
            ).fetchone()
        if row is None:
            return None
        checkpoint = SchedulerCheckpoint.from_row(dict(row))
        if hashlib.sha256(checkpoint.state_json.encode("utf-8")).hexdigest() != checkpoint.input_digest:
            raise ValueError("checkpoint input digest mismatch")
        return checkpoint

    def advance_work_item_from_checkpoint(
        self, work_item_id: str, *, plan_version: int, input_digest: str, owner_token: str | None = None
    ) -> bool:
        """CAS a queued WorkItem to running after checkpoint validation."""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                checkpoint = conn.execute(
                    "SELECT * FROM scheduler_checkpoints WHERE task_id=? AND plan_version=? AND node_id=?",
                    (work_item_id, int(plan_version), work_item_id),
                ).fetchone()
                if checkpoint is None or checkpoint["input_digest"] != input_digest:
                    conn.commit()
                    return False
                if hashlib.sha256(checkpoint["state_json"].encode("utf-8")).hexdigest() != input_digest:
                    conn.commit()
                    return False
                lease_clause = ""
                params: list[object] = [work_item_id, int(plan_version)]
                if owner_token is not None:
                    lease_clause = " AND EXISTS (SELECT 1 FROM scheduler_leases l WHERE l.task_id=? AND l.owner_token=? AND l.expires_at>?)"
                    params.extend([work_item_id, owner_token, _utcnow()])
                changed = conn.execute(
                    "UPDATE research_work_items SET status='running', started_at=COALESCE(started_at,?), updated_at=? "
                    "WHERE work_item_id=? AND plan_version=? AND status='queued'" + lease_clause,
                    (_utcnow(), _utcnow(), *params),
                ).rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return changed == 1

    def reserve_resources(
        self,
        worker_id: str,
        model_tier: str,
        estimated_bytes: int,
        *,
        task_id: str | None = None,
        expires_at: str | None = None,
        lease_seconds: int = 60,
        capacity_bytes: int | None = None,
        grant_token: str | None = None,
        now: str | None = None,
    ) -> ResourceReservation | None:
        """Atomically reserve capacity without overselling active bytes."""
        if not worker_id or not model_tier or int(estimated_bytes) < 0:
            raise ValueError("invalid resource reservation")
        current = now or _utcnow()
        expiry = expires_at or _utc_after(lease_seconds, current)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                conn.execute(
                    "DELETE FROM resource_reservations WHERE released_at IS NULL AND expires_at<=?",
                    (current,),
                )
                existing = conn.execute(
                    "SELECT 1 FROM resource_reservations WHERE worker_id=? AND released_at IS NULL AND expires_at>?",
                    (worker_id, current),
                ).fetchone()
                # Strong/27B capacity is a database-level singleton.  This
                # check is intentionally inside the same BEGIN IMMEDIATE
                # transaction as cleanup and INSERT; callers must not perform
                # a preceding SELECT that can race across scheduler objects.
                strong_tier = str(model_tier).strip().lower() in {"strong", "27b", "32b", "70b", "quality"}
                existing_strong = None
                if strong_tier:
                    existing_strong = conn.execute(
                        "SELECT 1 FROM resource_reservations WHERE released_at IS NULL AND expires_at>? "
                        "AND lower(model_tier) IN ('strong','27b','32b','70b','quality') LIMIT 1",
                        (current,),
                    ).fetchone()
                used = conn.execute(
                    "SELECT COALESCE(SUM(estimated_bytes),0) FROM resource_reservations WHERE released_at IS NULL AND expires_at>?",
                    (current,),
                ).fetchone()[0]
                if existing is not None or existing_strong is not None or (capacity_bytes is not None and int(used) + int(estimated_bytes) > int(capacity_bytes)):
                    conn.commit()
                    return None
                reservation_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO resource_reservations(reservation_id,task_id,worker_id,model_tier,estimated_bytes,expires_at,created_at,released_at,grant_token)
                       VALUES(?,?,?,?,?,?,?,NULL,?)""",
                    (reservation_id, task_id, worker_id, model_tier, int(estimated_bytes), expiry, current, grant_token),
                )
                row = conn.execute("SELECT * FROM resource_reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResourceReservation.from_row(dict(row))

    def release_resource_reservation(
        self,
        reservation_id: str,
        *,
        worker_id: str | None = None,
        task_id: str | None = None,
        grant_token: str | None = None,
        now: str | None = None,
    ) -> bool:
        current = now or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                sql = "UPDATE resource_reservations SET released_at=? WHERE reservation_id=? AND released_at IS NULL"
                params: list[object] = [current, reservation_id]
                if worker_id is not None:
                    sql += " AND worker_id=?"
                    params.append(worker_id)
                if task_id is not None:
                    sql += " AND task_id=?"
                    params.append(task_id)
                if grant_token is not None:
                    sql += " AND grant_token=?"
                    params.append(grant_token)
                changed = conn.execute(sql, params).rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return changed == 1

    def get_resource_reservation(self, reservation_id: str) -> ResourceReservation | None:
        with self._connect() as conn:
            self._ensure_scheduler_schema(conn)
            row = conn.execute(
                "SELECT * FROM resource_reservations WHERE reservation_id=?", (reservation_id,)
            ).fetchone()
        return ResourceReservation.from_row(dict(row)) if row else None

    def list_resource_reservations(self, *, task_id: str | None = None, now: str | None = None) -> list[ResourceReservation]:
        current = now or _utcnow()
        with self._connect() as conn:
            self._ensure_scheduler_schema(conn)
            if task_id is None:
                rows = conn.execute(
                    "SELECT * FROM resource_reservations WHERE released_at IS NULL AND expires_at>? ORDER BY created_at,reservation_id",
                    (current,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM resource_reservations WHERE task_id=? AND released_at IS NULL AND expires_at>? ORDER BY created_at,reservation_id",
                    (task_id, current),
                ).fetchall()
        return [ResourceReservation.from_row(dict(row)) for row in rows]

    def recover_expired_resource_reservations(self, *, now: str | None = None) -> int:
        return len(self.recover_expired_resource_reservation_rows(now=now))

    def recover_expired_resource_reservation_rows(self, *, now: str | None = None) -> list[dict]:
        """Atomically mark expired rows released and return safe ownership data.

        Returning the task/count data lets a live process reconcile its
        in-memory probe quota; a restarted process can safely no-op when the
        old in-memory quota no longer exists.
        """
        current = now or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_scheduler_schema(conn)
                rows = conn.execute(
                    "SELECT reservation_id, task_id FROM resource_reservations "
                    "WHERE released_at IS NULL AND expires_at<=? ORDER BY reservation_id",
                    (current,),
                ).fetchall()
                if rows:
                    conn.execute(
                        "UPDATE resource_reservations SET released_at=? WHERE released_at IS NULL AND expires_at<=?",
                        (current, current),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return [{"reservation_id": row["reservation_id"], "task_id": row["task_id"]} for row in rows]

    def save_routing_gate_evidence(self, evidence: dict) -> dict:
        """Persist server-generated activation evidence immutably."""
        required = ("evidence_id", "policy_version", "quality_samples", "quality_score", "schema_valid_rate", "resource_snapshot_id", "resource_workers", "created_at")
        if any(key not in evidence for key in required):
            raise ValueError("routing gate evidence is incomplete")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_spec031_schema(conn)
                snapshot = conn.execute(
                    "SELECT snapshot_id FROM research_resource_snapshots WHERE snapshot_id=?",
                    (evidence["resource_snapshot_id"],),
                ).fetchone()
                if snapshot is None:
                    raise ValueError("resource snapshot evidence is missing")
                conn.execute(
                    """INSERT INTO research_routing_gate_evidence(
                       evidence_id, policy_version, quality_samples, quality_score,
                       schema_valid_rate, resource_snapshot_id, resource_workers, created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (evidence["evidence_id"], evidence["policy_version"], int(evidence["quality_samples"]),
                     float(evidence["quality_score"]), float(evidence["schema_valid_rate"]),
                     evidence["resource_snapshot_id"], int(evidence["resource_workers"]), evidence["created_at"]),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return dict(evidence)

    def get_routing_gate_evidence(self, evidence_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT e.*, s.available_memory, s.estimated_kv, s.probe_error
                     FROM research_routing_gate_evidence e
                     JOIN research_resource_snapshots s ON s.snapshot_id=e.resource_snapshot_id
                    WHERE e.evidence_id=?""",
                (evidence_id,),
            ).fetchone()
        return dict(row) if row else None

    def routing_quality_summary(self, policy_version: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS samples,
                          AVG(quality_score) AS quality_score,
                          AVG(CASE WHEN schema_valid=1 THEN 1.0 ELSE 0.0 END) AS schema_valid_rate
                     FROM research_model_outcomes o
                     JOIN research_routing_decisions d ON d.decision_id=o.decision_id
                    WHERE d.policy_version=? AND o.quality_score IS NOT NULL""",
                (policy_version,),
            ).fetchone()
        return {
            "samples": int(row["samples"] or 0),
            "quality_score": float(row["quality_score"] or 0.0),
            "schema_valid_rate": float(row["schema_valid_rate"] or 0.0),
        }

    # ------------------------------------------------------------------ #
    # Spec034 session state / approvals / runtime records
    # ------------------------------------------------------------------ #

    def create_session(self, session: ResearchSession, draft: ResearchIntakeDraft | None = None, *, memory_repository=None) -> ResearchSession:
        """Create an active session and its one-to-one draft atomically.

        The partial unique index is deliberately the final arbiter for two
        concurrent coordinators; callers receive a stable conflict code.
        """
        if session.status not in SESSION_STATUSES:
            raise ValueError("invalid research session status")
        if memory_repository is None:
            raise ValueError("memory repository is required for session creation")
        validate_session_external_references(session, memory_repository)
        if draft is not None and (
            draft.research_session_id != session.research_session_id
            or draft.intake_draft_id != session.intake_draft_id
        ):
            raise ValueError("intake draft does not belong to session")
        now = _utcnow()
        draft = draft or ResearchIntakeDraft(session.intake_draft_id, session.research_session_id, "collecting", now, now)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if session.research_task_id is not None:
                    task = conn.execute(
                        "SELECT owner_id, conversation_id FROM research_tasks WHERE research_task_id=?",
                        (session.research_task_id,),
                    ).fetchone()
                    if (
                        task is None
                        or task["owner_id"] != session.owner_id
                        or task["conversation_id"] != session.conversation_id
                    ):
                        raise ResearchTaskNotFound(session.research_task_id)
                conn.execute("""INSERT INTO research_sessions(
                    research_session_id, owner_id, conversation_id, trigger_message_id,
                    plan_message_id, activity_message_id, final_message_id, intake_draft_id,
                    research_task_id, current_plan_version, status, unread_state_json, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    session.research_session_id, session.owner_id, session.conversation_id,
                    session.trigger_message_id, session.plan_message_id, session.activity_message_id,
                    session.final_message_id, session.intake_draft_id, session.research_task_id,
                    session.current_plan_version, session.status, session.unread_state_json or "{}",
                    session.created_at or now, session.updated_at or now,
                ))
                conn.execute("""INSERT INTO research_intake_drafts(intake_draft_id, research_session_id, status, created_at, updated_at)
                    VALUES(?,?,?,?,?)""", (draft.intake_draft_id, draft.research_session_id, draft.status, draft.created_at or now, draft.updated_at or now))
                row = conn.execute("SELECT * FROM research_sessions WHERE research_session_id=?", (session.research_session_id,)).fetchone()
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                if "uq_research_sessions_active" in str(exc) or "research_sessions.owner_id" in str(exc):
                    raise ResearchSessionActiveConflict() from exc
                raise
            except Exception:
                conn.rollback()
                raise
        return ResearchSession.from_row(dict(row))

    def get_session(self, research_session_id: str, owner_id: str) -> ResearchSession | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                (research_session_id, owner_id),
            ).fetchone()
        return ResearchSession.from_row(dict(row)) if row else None

    def get_session_by_trigger(self, conversation_id: str, trigger_message_id: str, owner_id: str) -> ResearchSession | None:
        """Find a prior owner-scoped Session for trigger replay recovery."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM research_sessions
                WHERE conversation_id=? AND trigger_message_id=? AND owner_id=?
                ORDER BY created_at DESC, research_session_id DESC LIMIT 1""",
                (conversation_id, trigger_message_id, owner_id),
            ).fetchone()
        return ResearchSession.from_row(dict(row)) if row else None

    def get_active_session(self, conversation_id: str, owner_id: str) -> ResearchSession | None:
        """Resolve the active Session without relying on a capped list page."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM research_sessions
                WHERE conversation_id=? AND owner_id=?
                  AND status NOT IN ('interrupted','partial','completed','failed','cancelled')
                ORDER BY updated_at DESC, research_session_id DESC LIMIT 1""",
                (conversation_id, owner_id),
            ).fetchone()
        return ResearchSession.from_row(dict(row)) if row else None

    def get_session_by_task(self, research_task_id: str, owner_id: str) -> ResearchSession | None:
        """Resolve the owner-scoped Session link for a Task detail projection."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT s.* FROM research_sessions s
                WHERE s.research_task_id=? AND s.owner_id=?
                ORDER BY s.updated_at DESC, s.research_session_id DESC LIMIT 1""",
                (research_task_id, owner_id),
            ).fetchone()
        return ResearchSession.from_row(dict(row)) if row else None

    # ------------------------------------------------------------------ #
    # Spec034 Session plan versions (Task04)
    # ------------------------------------------------------------------ #

    def create_session_plan(self, plan: ResearchSessionPlan, owner_id: str) -> ResearchSessionPlan:
        """Insert an immutable, owner-scoped plan version before Task creation."""
        if plan.version < 1 or plan.status not in PLAN_STATUSES:
            raise ValueError("invalid session plan")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (plan.research_session_id, owner_id),
                ).fetchone():
                    raise ResearchSessionNotFound(plan.research_session_id)
                if conn.execute(
                    "SELECT 1 FROM research_session_plans WHERE research_session_id=? AND version=?",
                    (plan.research_session_id, plan.version),
                ).fetchone():
                    conn.rollback()
                    raise ResearchPlanConflict(plan.research_session_id, plan.version)
                conn.execute(
                    """INSERT INTO research_session_plans(
                        research_session_id, version, schema_version, output_hash, objective,
                        scope_json, work_items_json, capabilities_json, budget_json,
                        report_structure_json, safety_summary_json, status, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        plan.research_session_id, plan.version, plan.schema_version, plan.output_hash,
                        plan.objective, plan.scope_json, plan.work_items_json, plan.capabilities_json,
                        plan.budget_json, plan.report_structure_json, plan.safety_summary_json,
                        plan.status, plan.created_at or _utcnow(),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_session_plans WHERE research_session_id=? AND version=?",
                    (plan.research_session_id, plan.version),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSessionPlan.from_row(dict(row))

    def create_session_plan_cas(
        self,
        plan: ResearchSessionPlan,
        owner_id: str,
        *,
        expected_current_version: int,
    ) -> tuple[ResearchSessionPlan, ResearchSession] | None:
        """Append a Session plan and advance its pointer in one CAS transaction."""
        if int(plan.version) != int(expected_current_version) + 1:
            raise ValueError("plan version must advance by exactly one")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                session_row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (plan.research_session_id, owner_id),
                ).fetchone()
                if session_row is None:
                    conn.rollback()
                    raise ResearchSessionNotFound(plan.research_session_id)
                if int(session_row["current_plan_version"]) != int(expected_current_version):
                    conn.commit()
                    return None
                if conn.execute(
                    "SELECT 1 FROM research_session_plans WHERE research_session_id=? AND version=?",
                    (plan.research_session_id, int(plan.version)),
                ).fetchone() is not None:
                    conn.commit()
                    raise ResearchPlanConflict(plan.research_session_id, plan.version)
                conn.execute(
                    """INSERT INTO research_session_plans(
                        research_session_id,version,schema_version,output_hash,objective,
                        scope_json,work_items_json,capabilities_json,budget_json,
                        report_structure_json,safety_summary_json,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        plan.research_session_id, int(plan.version), plan.schema_version,
                        plan.output_hash, plan.objective, plan.scope_json, plan.work_items_json,
                        plan.capabilities_json, plan.budget_json, plan.report_structure_json,
                        plan.safety_summary_json, plan.status, plan.created_at or _utcnow(),
                    ),
                )
                changed = conn.execute(
                    "UPDATE research_sessions SET current_plan_version=?, updated_at=? "
                    "WHERE research_session_id=? AND owner_id=? AND current_plan_version=?",
                    (int(plan.version), _utcnow(), plan.research_session_id, owner_id, int(expected_current_version)),
                ).rowcount
                if changed != 1:
                    conn.rollback()
                    return None
                saved_plan = conn.execute(
                    "SELECT * FROM research_session_plans WHERE research_session_id=? AND version=?",
                    (plan.research_session_id, int(plan.version)),
                ).fetchone()
                saved_session = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (plan.research_session_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSessionPlan.from_row(dict(saved_plan)), ResearchSession.from_row(dict(saved_session))

    append_session_plan_cas = create_session_plan_cas

    def get_session_plan(self, research_session_id: str, owner_id: str, version: int | None = None) -> ResearchSessionPlan | None:
        with self._connect() as conn:
            if version is None:
                row = conn.execute(
                    """SELECT p.* FROM research_session_plans p JOIN research_sessions s
                    ON s.research_session_id=p.research_session_id
                    WHERE p.research_session_id=? AND s.owner_id=? ORDER BY p.version DESC LIMIT 1""",
                    (research_session_id, owner_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT p.* FROM research_session_plans p JOIN research_sessions s
                    ON s.research_session_id=p.research_session_id
                    WHERE p.research_session_id=? AND p.version=? AND s.owner_id=?""",
                    (research_session_id, version, owner_id),
                ).fetchone()
        return ResearchSessionPlan.from_row(dict(row)) if row else None

    def list_session_plans(self, research_session_id: str, owner_id: str) -> list[ResearchSessionPlan]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.* FROM research_session_plans p JOIN research_sessions s
                ON s.research_session_id=p.research_session_id
                WHERE p.research_session_id=? AND s.owner_id=? ORDER BY p.version""",
                (research_session_id, owner_id),
            ).fetchall()
        return [ResearchSessionPlan.from_row(dict(row)) for row in rows]

    def update_session_plan_status(
        self, research_session_id: str, owner_id: str, version: int, next_status: str
    ) -> ResearchSessionPlan:
        """Update the lifecycle status of an existing Session plan version."""
        if next_status not in PLAN_STATUSES:
            raise ValueError("invalid session plan status")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone():
                    raise ResearchSessionNotFound(research_session_id)
                changed = conn.execute(
                    "UPDATE research_session_plans SET status=? WHERE research_session_id=? AND version=?",
                    (next_status, research_session_id, int(version)),
                ).rowcount
                if changed != 1:
                    raise ResearchPlanNotFound(research_session_id, int(version))
                row = conn.execute(
                    "SELECT * FROM research_session_plans WHERE research_session_id=? AND version=?",
                    (research_session_id, int(version)),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSessionPlan.from_row(dict(row))

    def supersede_session_plans(self, research_session_id: str, owner_id: str, keep_version: int) -> int:
        """Mark all earlier proposed/active plans superseded in one owner-scoped CAS."""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone():
                    raise ResearchSessionNotFound(research_session_id)
                cur = conn.execute(
                    """UPDATE research_session_plans SET status='superseded'
                    WHERE research_session_id=? AND version<? AND status IN ('proposed','active')""",
                    (research_session_id, keep_version),
                )
                conn.commit()
                return max(int(cur.rowcount), 0)
            except Exception:
                conn.rollback()
                raise

    def list_sessions_page(
        self, owner_id: str, *, status: str | None = None, limit: int = 20, cursor: str | None = None,
    ) -> tuple[list[ResearchSession], str | None]:
        """Owner/status-scoped keyset page for the Research Tab."""
        limit = max(1, min(int(limit), 100))
        params: list[object] = [owner_id]
        sql = "SELECT * FROM research_sessions WHERE owner_id=?"
        if status is not None:
            if status not in SESSION_STATUSES:
                raise ValueError("invalid research session status")
            sql += " AND status=?"
            params.append(status)
        if cursor is not None:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8"))
                expected_kind = f"research_sessions:v1:status={status or '*'}"
                if decoded.get("v") != 1 or decoded.get("kind") != expected_kind or not decoded.get("at") or not decoded.get("id"):
                    raise ValueError
                sql += " AND (created_at, research_session_id) > (?, ?)"
                params.extend([str(decoded["at"]), str(decoded["id"])])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
                raise ValueError("invalid cursor") from None
        sql += " ORDER BY created_at, research_session_id LIMIT ?"
        params.append(limit + 1)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = page[-1]
            kind = f"research_sessions:v1:status={status or '*'}"
            raw = json.dumps({"v": 1, "kind": kind, "at": last["created_at"], "id": last["research_session_id"]}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            next_cursor = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return [ResearchSession.from_row(dict(row)) for row in page], next_cursor

    @staticmethod
    def encode_sessions_cursor(session: ResearchSession, *, status: str | None = None) -> str:
        """Encode a cursor at an actually returned Session boundary.

        Filtered callers may scan more raw rows than they return.  Exposing
        this small encoder keeps their next page anchored to the last visible
        row instead of skipping the remainder of an overfull raw page.
        """
        kind = f"research_sessions:v1:status={status or '*'}"
        raw = json.dumps(
            {"v": 1, "kind": kind, "at": session.created_at, "id": session.research_session_id},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def list_sessions(self, owner_id: str, *, status: str | None = None, limit: int = 20) -> list[ResearchSession]:
        """Backward-compatible first page list used by existing coordinators."""
        return self.list_sessions_page(owner_id, status=status, limit=limit)[0]

    def update_session_status(self, research_session_id: str, owner_id: str, next_status: str) -> ResearchSession:
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(research_session_id)
                transition_session(row["status"], next_status)
                now = _utcnow()
                conn.execute(
                    "UPDATE research_sessions SET status=?, updated_at=? WHERE research_session_id=? AND owner_id=?",
                    (next_status, now, research_session_id, owner_id),
                )
                row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=?", (research_session_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSession.from_row(dict(row))

    def reconcile_session_status(self, research_session_id: str, owner_id: str, next_status: str) -> ResearchSession:
        """Repair a stale Session projection from a durable terminal Task."""
        if next_status not in SESSION_TERMINAL:
            raise ValueError("reconciliation status must be terminal")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(research_session_id)
                if row["status"] not in SESSION_TERMINAL:
                    conn.execute(
                        "UPDATE research_sessions SET status=?, updated_at=? WHERE research_session_id=? AND owner_id=?",
                        (next_status, _utcnow(), research_session_id, owner_id),
                    )
                row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSession.from_row(dict(row))

    def cancel_session_research(self, research_session_id: str, owner_id: str) -> tuple[ResearchSession, ResearchTask | None, int]:
        """CAS-cancel Session and its active Task/WorkItems in one transaction.

        Only expected state-machine conflicts are surfaced; no broad exception
        suppression is used, so callers can retry a failed cross-store Saga.
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                session_row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone()
                if session_row is None:
                    raise ResearchSessionNotFound(research_session_id)
                transition_session(session_row["status"], "cancelled")
                task = None
                task_id = session_row["research_task_id"]
                if task_id is not None:
                    now = _utcnow()
                    task_row = conn.execute(
                        "SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                        (task_id, owner_id),
                    ).fetchone()
                    if task_row is None:
                        raise ResearchTaskNotFound(task_id)
                    if task_row["status"] not in TASK_TERMINAL:
                        transition_task(task_row["status"], "cancelled")
                        conn.execute(
                            "UPDATE research_tasks SET status='cancelled', updated_at=?, completed_at=? WHERE research_task_id=? AND owner_id=?",
                            (now, now, task_id, owner_id),
                        )
                    for item_row in conn.execute(
                        "SELECT work_item_id,status FROM research_work_items WHERE research_task_id=?",
                        (task_id,),
                    ).fetchall():
                        if item_row["status"] in {"queued", "running"}:
                            transition_workitem(item_row["status"], "cancelled")
                            conn.execute(
                                "UPDATE research_work_items SET status='cancelled', ended_at=?, updated_at=? WHERE work_item_id=? AND status IN ('queued','running')",
                                (now, now, item_row["work_item_id"]),
                            )
                    task_row = conn.execute(
                        "SELECT * FROM research_tasks WHERE research_task_id=?",
                        (task_id,),
                    ).fetchone()
                    task = ResearchTask.from_row(dict(task_row))
                now = _utcnow()
                conn.execute(
                    "UPDATE research_sessions SET status='cancelled', updated_at=? WHERE research_session_id=? AND owner_id=? AND status NOT IN ('interrupted','partial','completed','failed','cancelled')",
                    (now, research_session_id, owner_id),
                )
                session_row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=?",
                    (research_session_id,),
                ).fetchone()
                cancelled_count = int(conn.execute(
                    "SELECT COUNT(*) FROM research_work_items WHERE research_task_id=? AND status='cancelled'",
                    (task_id,),
                ).fetchone()[0]) if task_id else 0
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSession.from_row(dict(session_row)), task, cancelled_count

    def update_session_links(self, research_session_id: str, owner_id: str, **fields) -> ResearchSession:
        allowed = {
            "plan_message_id",
            "activity_message_id",
            "final_message_id",
            "research_task_id",
            "current_plan_version",
            "unread_state_json",
        }
        if set(fields) - allowed:
            raise ValueError("invalid session field")
        if not fields:
            result = self.get_session(research_session_id, owner_id)
            if result is None:
                raise ResearchSessionNotFound(research_session_id)
            return result
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone():
                    raise ResearchSessionNotFound(research_session_id)
                if "research_task_id" in fields and fields["research_task_id"] is not None:
                    task = conn.execute(
                        "SELECT research_task_id, owner_id, conversation_id FROM research_tasks WHERE research_task_id=?",
                        (fields["research_task_id"],),
                    ).fetchone()
                    session_row = conn.execute(
                        "SELECT conversation_id, research_task_id FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                        (research_session_id, owner_id),
                    ).fetchone()
                    if (
                        task is None
                        or task["owner_id"] != owner_id
                        or task["conversation_id"] != session_row["conversation_id"]
                    ):
                        raise ResearchTaskNotFound(fields["research_task_id"])
                    if session_row["research_task_id"] not in (None, fields["research_task_id"]):
                        raise ValueError("research task does not belong to session")
                fields["updated_at"] = _utcnow()
                sql = ", ".join(f"{name}=?" for name in fields)
                conn.execute(
                    f"UPDATE research_sessions SET {sql} WHERE research_session_id=? AND owner_id=?",
                    (*fields.values(), research_session_id, owner_id),
                )
                row = conn.execute(
                    "SELECT * FROM research_sessions WHERE research_session_id=?", (research_session_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchSession.from_row(dict(row))

    def get_intake_draft(self, research_session_id: str, owner_id: str) -> ResearchIntakeDraft | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT d.* FROM research_intake_drafts d JOIN research_sessions s ON s.research_session_id=d.research_session_id
                WHERE d.research_session_id=? AND s.owner_id=?""",
                (research_session_id, owner_id),
            ).fetchone()
        return ResearchIntakeDraft.from_row(dict(row)) if row else None

    def update_intake_status(self, intake_draft_id: str, owner_id: str, next_status: str) -> ResearchIntakeDraft:
        if next_status not in INTAKE_STATUSES:
            raise ValueError("invalid intake status")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT d.* FROM research_intake_drafts d JOIN research_sessions s ON s.research_session_id=d.research_session_id
                    WHERE d.intake_draft_id=? AND s.owner_id=?""",
                    (intake_draft_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(intake_draft_id)
                transition_intake(row["status"], next_status)
                now = _utcnow()
                conn.execute(
                    "UPDATE research_intake_drafts SET status=?, updated_at=? WHERE intake_draft_id=?",
                    (next_status, now, intake_draft_id),
                )
                row = conn.execute(
                    "SELECT * FROM research_intake_drafts WHERE intake_draft_id=?", (intake_draft_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchIntakeDraft.from_row(dict(row))

    def upsert_intake_field(self, field: IntakeField, owner_id: str) -> IntakeField:
        if field.field_name not in INTAKE_FIELDS:
            raise ValueError("invalid intake field")
        if field.source not in INTAKE_SOURCES:
            raise ValueError("invalid intake source")
        if not 0 <= float(field.confidence) <= 1:
            raise ValueError("invalid intake confidence")
        if field.confirmation_status not in INTAKE_CONFIRMATION_STATUSES:
            raise ValueError("invalid intake confirmation")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                valid = conn.execute(
                    """SELECT 1 FROM research_intake_drafts d JOIN research_sessions s ON s.research_session_id=d.research_session_id
                    WHERE d.intake_draft_id=? AND s.owner_id=?""",
                    (field.intake_draft_id, owner_id),
                ).fetchone()
                if not valid:
                    raise ResearchSessionNotFound(field.intake_draft_id)
                now = field.updated_at or _utcnow()
                conn.execute(
                    """INSERT INTO research_intake_fields(intake_draft_id, field_name, value_json, source, confidence, confirmation_status, updated_by_message_id, updated_at)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(intake_draft_id, field_name) DO UPDATE SET value_json=excluded.value_json, source=excluded.source, confidence=excluded.confidence, confirmation_status=excluded.confirmation_status, updated_by_message_id=excluded.updated_by_message_id, updated_at=excluded.updated_at""",
                    (
                        field.intake_draft_id,
                        field.field_name,
                        field.value_json,
                        field.source,
                        field.confidence,
                        field.confirmation_status,
                        field.updated_by_message_id,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_intake_fields WHERE intake_draft_id=? AND field_name=?",
                    (field.intake_draft_id, field.field_name),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return IntakeField.from_row(dict(row))

    def list_intake_fields(self, intake_draft_id: str, owner_id: str) -> list[IntakeField]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT f.* FROM research_intake_fields f JOIN research_intake_drafts d ON d.intake_draft_id=f.intake_draft_id JOIN research_sessions s ON s.research_session_id=d.research_session_id
                WHERE f.intake_draft_id=? AND s.owner_id=? ORDER BY f.field_name""",
                (intake_draft_id, owner_id),
            ).fetchall()
        return [IntakeField.from_row(dict(row)) for row in rows]

    def create_approval(self, approval: ApprovalRequest) -> ApprovalRequest:
        if approval.kind not in APPROVAL_KINDS or approval.status not in APPROVAL_STATUSES:
            raise ValueError("invalid approval")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (approval.research_session_id, approval.owner_id),
                ).fetchone():
                    raise ResearchSessionNotFound(approval.research_session_id)
                conn.execute(
                    """INSERT INTO research_approval_requests(approval_request_id, owner_id, research_session_id, kind, subject_id, subject_version, requested_scope_json, approved_scope_json, status, idempotency_key, decided_by_message_id, created_at, decided_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        approval.approval_request_id,
                        approval.owner_id,
                        approval.research_session_id,
                        approval.kind,
                        approval.subject_id,
                        approval.subject_version,
                        approval.requested_scope_json,
                        approval.approved_scope_json,
                        approval.status,
                        approval.idempotency_key,
                        approval.decided_by_message_id,
                        approval.created_at or _utcnow(),
                        approval.decided_at,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_approval_requests WHERE approval_request_id=?",
                    (approval.approval_request_id,),
                ).fetchone()
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                with self._connect() as read_conn:
                    existing = read_conn.execute(
                        "SELECT * FROM research_approval_requests WHERE owner_id=? AND idempotency_key=?",
                        (approval.owner_id, approval.idempotency_key),
                    ).fetchone()
                if existing is not None:
                    # A key is idempotent only for the same approval
                    # identity.  Reusing it for another scope/version must not
                    # silently return the first request.
                    same_identity = (
                        existing["research_session_id"] == approval.research_session_id
                        and existing["kind"] == approval.kind
                        and existing["subject_id"] == approval.subject_id
                        and int(existing["subject_version"]) == int(approval.subject_version)
                        and existing["requested_scope_json"] == approval.requested_scope_json
                    )
                    if not same_identity:
                        raise ApprovalConflict() from exc
                    return ApprovalRequest.from_row(dict(existing))
                raise ApprovalConflict() from exc
            except Exception:
                conn.rollback()
                raise
        return ApprovalRequest.from_row(dict(row))

    def get_approval(self, approval_request_id: str, owner_id: str) -> ApprovalRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_approval_requests WHERE approval_request_id=? AND owner_id=?",
                (approval_request_id, owner_id),
            ).fetchone()
        return ApprovalRequest.from_row(dict(row)) if row else None

    def get_approval_by_idempotency(self, idempotency_key: str, owner_id: str) -> ApprovalRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_approval_requests WHERE idempotency_key=? AND owner_id=?",
                (idempotency_key, owner_id),
            ).fetchone()
        return ApprovalRequest.from_row(dict(row)) if row else None

    def list_approvals(self, research_session_id: str, owner_id: str, *, subject_version: int | None = None) -> list[ApprovalRequest]:
        params: list[object] = [research_session_id, owner_id]
        sql = "SELECT * FROM research_approval_requests WHERE research_session_id=? AND owner_id=?"
        if subject_version is not None:
            sql += " AND subject_version=?"
            params.append(subject_version)
        sql += " ORDER BY created_at, approval_request_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ApprovalRequest.from_row(dict(row)) for row in rows]

    def supersede_approvals(self, research_session_id: str, owner_id: str, *, before_version: int) -> int:
        """Supersede pending approvals for older plan versions (owner-scoped)."""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """UPDATE research_approval_requests SET status='superseded', decided_at=?
                    WHERE research_session_id=? AND owner_id=? AND subject_version<? AND status='pending'""",
                    (_utcnow(), research_session_id, owner_id, before_version),
                )
                conn.commit()
                return max(int(cur.rowcount), 0)
            except Exception:
                conn.rollback()
                raise

    def get_command_result_record(self, idempotency_key: str, owner_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_command_results WHERE owner_id=? AND idempotency_key=?",
                (owner_id, idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def get_command_result(self, idempotency_key: str, owner_id: str) -> dict | None:
        record = self.get_command_result_record(idempotency_key, owner_id)
        return json.loads(record["response_json"]) if record else None

    def save_command_result(self, *, owner_id: str, research_session_id: str, subject_version: int, idempotency_key: str, command: str, response: dict) -> dict:
        """Persist an immutable command response; duplicate keys return first response."""
        payload = json.dumps(response, ensure_ascii=False, sort_keys=True)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT * FROM research_command_results WHERE owner_id=? AND idempotency_key=?",
                    (owner_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if (existing["research_session_id"], existing["command"], int(existing["subject_version"])) != (research_session_id, command, int(subject_version)):
                        raise ValueError("command idempotency identity conflict")
                    conn.commit()
                    return json.loads(existing["response_json"])
                conn.execute(
                    "INSERT INTO research_command_results(owner_id,research_session_id,idempotency_key,command,subject_version,subject_id,response_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (owner_id, research_session_id, idempotency_key, command, int(subject_version), research_session_id, payload, _utcnow()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return response

    def create_activity_outbox(self, *, owner_id: str, research_session_id: str, subject_version: int, command_idempotency_key: str, research_task_id: str) -> dict:
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_activity_outbox WHERE owner_id=? AND research_session_id=? AND subject_version=? AND command_idempotency_key=?",
                    (owner_id, research_session_id, subject_version, command_idempotency_key),
                ).fetchone()
                if row is None:
                    now = _utcnow()
                    outbox_id = uuid.uuid4().hex
                    conn.execute(
                        "INSERT INTO research_activity_outbox(outbox_id,owner_id,research_session_id,subject_version,command_idempotency_key,research_task_id,status,error_code,attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (outbox_id, owner_id, research_session_id, subject_version, command_idempotency_key, research_task_id, "pending", None, 0, now, now),
                    )
                    row = conn.execute("SELECT * FROM research_activity_outbox WHERE outbox_id=?", (outbox_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return dict(row)

    def create_plan_activation(self, *, owner_id: str, research_session_id: str,
                               subject_version: int, command_idempotency_key: str) -> dict:
        """Create/read the approve-plan activation anchor idempotently."""
        activation_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"research-plan-activation:{owner_id}:{research_session_id}:{int(subject_version)}:{command_idempotency_key}",
        ).hex
        task_id = uuid.uuid5(uuid.NAMESPACE_URL, f"research-task:{activation_id}").hex
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                session = conn.execute(
                    "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                    (research_session_id, owner_id),
                ).fetchone()
                if session is None:
                    raise ResearchSessionNotFound(research_session_id)
                row = conn.execute(
                    "SELECT * FROM research_plan_activations WHERE owner_id=? AND research_session_id=? AND subject_version=? AND command_idempotency_key=?",
                    (owner_id, research_session_id, int(subject_version), command_idempotency_key),
                ).fetchone()
                if row is None:
                    now = _utcnow()
                    conn.execute(
                        """INSERT INTO research_plan_activations(
                            activation_id,owner_id,research_session_id,subject_version,
                            command_idempotency_key,research_task_id,status,error_code,
                            attempts,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (activation_id, owner_id, research_session_id, int(subject_version),
                         command_idempotency_key, task_id, "pending", None, 0, now, now),
                    )
                    row = conn.execute(
                        "SELECT * FROM research_plan_activations WHERE activation_id=?", (activation_id,)
                    ).fetchone()
                elif row["research_task_id"] != task_id:
                    raise ValueError("activation identity conflict")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return dict(row)

    def get_plan_activation(self, *, owner_id: str, research_session_id: str,
                            subject_version: int, command_idempotency_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_plan_activations WHERE owner_id=? AND research_session_id=? AND subject_version=? AND command_idempotency_key=?",
                (owner_id, research_session_id, int(subject_version), command_idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def update_plan_activation(self, activation_id: str, *, status: str,
                               error_code: str | None = None) -> dict:
        if status not in {"pending", "failed", "completed"}:
            raise ValueError("invalid plan activation status")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE research_plan_activations SET status=?, error_code=?, attempts=attempts+1, updated_at=? WHERE activation_id=?",
                    (status, error_code, _utcnow(), activation_id),
                )
                row = conn.execute(
                    "SELECT * FROM research_plan_activations WHERE activation_id=?", (activation_id,)
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(activation_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return dict(row)

    def activate_plan(self, *, activation: dict, task: ResearchTask,
                      plan: ResearchPlan, items: list[ResearchWorkItem],
                      outbox_key: str) -> tuple[ResearchTask, dict]:
        """Atomically and idempotently materialize an approved plan.

        The activation row is created before approval, while this transaction
        commits the Task, ResearchPlan, missing WorkItems, outbox and final
        activation status together.  A retry therefore observes either the
        complete set or none of the materialization writes.
        """
        if activation["research_task_id"] != task.research_task_id:
            raise ValueError("activation task identity conflict")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                anchor = conn.execute(
                    "SELECT * FROM research_plan_activations WHERE activation_id=? AND owner_id=? AND research_session_id=? AND subject_version=? AND command_idempotency_key=?",
                    (activation["activation_id"], task.owner_id, activation["research_session_id"], int(activation["subject_version"]), outbox_key),
                ).fetchone()
                if anchor is None:
                    raise ResearchSessionNotFound(activation["research_session_id"])
                existing_task = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_task_id=?",
                    (task.research_task_id,),
                ).fetchone()
                if existing_task is not None and (
                    existing_task["owner_id"] != task.owner_id
                    or existing_task["conversation_id"] != task.conversation_id
                ):
                    raise ValueError("activation task owner/session mismatch")
                if existing_task is None:
                    now = task.created_at or _utcnow()
                    conn.execute(
                        """INSERT INTO research_tasks(
                            research_task_id, owner_id, project_id, conversation_id, goal,
                            language, quality_profile, review_plan_first, target_paper_count,
                            soft_budget_seconds, status, current_plan_version, last_event_seq,
                            created_at, updated_at, completed_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (task.research_task_id, task.owner_id, task.project_id, task.conversation_id,
                         task.goal, task.language, task.quality_profile,
                         1 if task.review_plan_first else 0, task.target_paper_count, task.soft_budget_seconds,
                         "planning", task.current_plan_version, 0, now, task.updated_at or now,
                         task.completed_at),
                    )
                elif existing_task["status"] == "draft":
                    conn.execute(
                        "UPDATE research_tasks SET status='planning', updated_at=? WHERE research_task_id=?",
                        (_utcnow(), task.research_task_id),
                    )
                elif existing_task["status"] not in {"planning"}:
                    raise ValueError("activation task is not resumable")
                plan_row = conn.execute(
                    "SELECT 1 FROM research_plans WHERE research_task_id=? AND version=?",
                    (plan.research_task_id, plan.version),
                ).fetchone()
                if plan_row is None:
                    conn.execute(
                        """INSERT INTO research_plans(
                            research_task_id,version,planner_model,rationale_summary,
                            facets_json,status,created_at)
                        VALUES(?,?,?,?,?,?,?)""",
                        (plan.research_task_id, plan.version, plan.planner_model,
                         plan.rationale_summary, plan.facets_json, plan.status,
                         plan.created_at or _utcnow()),
                    )
                for item in items:
                    if item.task_type not in TASK_TYPE_WHITELIST or item.role not in ROLE_WHITELIST:
                        raise ValueError("invalid work item authorization")
                    existing_item = conn.execute(
                        "SELECT research_task_id, plan_version FROM research_work_items WHERE work_item_id=?",
                        (item.work_item_id,),
                    ).fetchone()
                    if existing_item is not None:
                        if (existing_item["research_task_id"], int(existing_item["plan_version"])) != (item.research_task_id, int(item.plan_version)):
                            raise ValueError("work item identity conflict")
                        continue
                    now = item.created_at or _utcnow()
                    conn.execute(
                        """INSERT INTO research_work_items(
                            work_item_id,research_task_id,plan_version,task_type,role,
                            depends_on_json,input_json,output_json,model_tier,resolved_model,
                            worker_slot,status,attempt,error_code,started_at,ended_at,
                            created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (item.work_item_id, item.research_task_id, item.plan_version,
                         item.task_type, item.role, item.depends_on_json, item.input_json,
                         item.output_json, item.model_tier, item.resolved_model, item.worker_slot,
                         item.status, item.attempt, item.error_code, item.started_at, item.ended_at,
                         now, item.updated_at or now),
                    )
                outbox = conn.execute(
                    "SELECT * FROM research_activity_outbox WHERE owner_id=? AND research_session_id=? AND subject_version=? AND command_idempotency_key=?",
                    (task.owner_id, activation["research_session_id"], int(activation["subject_version"]), outbox_key),
                ).fetchone()
                if outbox is None:
                    now = _utcnow()
                    outbox_id = uuid.uuid4().hex
                    conn.execute(
                        """INSERT INTO research_activity_outbox(
                            outbox_id,owner_id,research_session_id,subject_version,
                            command_idempotency_key,research_task_id,status,error_code,
                            attempts,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (outbox_id, task.owner_id, activation["research_session_id"],
                         int(activation["subject_version"]), outbox_key, task.research_task_id,
                         "pending", None, 0, now, now),
                    )
                    outbox = conn.execute("SELECT * FROM research_activity_outbox WHERE outbox_id=?", (outbox_id,)).fetchone()
                elif outbox["research_task_id"] != task.research_task_id:
                    raise ValueError("outbox task identity conflict")
                conn.execute(
                    "UPDATE research_plan_activations SET status='completed', error_code=NULL, attempts=attempts+1, updated_at=? WHERE activation_id=?",
                    (_utcnow(), activation["activation_id"]),
                )
                task_row = conn.execute("SELECT * FROM research_tasks WHERE research_task_id=?", (task.research_task_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchTask.from_row(dict(task_row)), dict(outbox)

    def get_activity_outbox(self, *, owner_id: str, research_session_id: str, subject_version: int, command_idempotency_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_activity_outbox WHERE owner_id=? AND research_session_id=? AND subject_version=? AND command_idempotency_key=?",
                (owner_id, research_session_id, subject_version, command_idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def update_activity_outbox(self, outbox_id: str, *, status: str, activity_message_id: str | None = None, error_code: str | None = None) -> dict:
        if status not in {"pending", "failed", "completed"}:
            raise ValueError("invalid activity outbox status")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE research_activity_outbox SET status=?, activity_message_id=COALESCE(?,activity_message_id), error_code=?, attempts=attempts+1, updated_at=? WHERE outbox_id=?",
                    (status, activity_message_id, error_code, _utcnow(), outbox_id),
                )
                row = conn.execute("SELECT * FROM research_activity_outbox WHERE outbox_id=?", (outbox_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return dict(row)

    def decide_approval(
        self,
        approval_request_id: str,
        owner_id: str,
        next_status: str,
        *,
        approved_scope_json: str | None = None,
        decided_by_message_id: str | None = None,
        subject_version: int | None = None,
    ) -> ApprovalRequest:
        if next_status not in APPROVAL_STATUSES:
            raise ValueError("invalid approval status")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM research_approval_requests WHERE approval_request_id=? AND owner_id=?",
                    (approval_request_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(approval_request_id)
                if subject_version is not None and int(subject_version) != int(row["subject_version"]):
                    raise ApprovalStale()
                if row["status"] != "pending":
                    if row["status"] == next_status:
                        conn.commit()
                        return ApprovalRequest.from_row(dict(row))
                    raise ApprovalConflict()
                transition_approval(row["status"], next_status)
                now = _utcnow()
                conn.execute(
                    "UPDATE research_approval_requests SET status=?, approved_scope_json=?, decided_by_message_id=?, decided_at=? WHERE approval_request_id=? AND owner_id=? AND status='pending'",
                    (next_status, approved_scope_json, decided_by_message_id, now, approval_request_id, owner_id),
                )
                row = conn.execute(
                    "SELECT * FROM research_approval_requests WHERE approval_request_id=?", (approval_request_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ApprovalRequest.from_row(dict(row))

    def create_agent_run(self, run: AgentRun, *, owner_id: str | None = None) -> AgentRun:
        if run.role not in AGENT_ROLES or run.status not in AGENT_RUN_STATUSES or run.attempt < 1:
            raise ValueError("invalid agent run")
        if (run.research_task_id is None) != (run.work_item_id is None):
            raise AgentRunBindingError("task and work_item must be bound together")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                session_row = conn.execute(
                    "SELECT research_task_id FROM research_sessions WHERE research_session_id=?",
                    (run.research_session_id,),
                ).fetchone()
                if session_row is None:
                    raise AgentRunBindingError("session not found")
                effective_owner = owner_id or run.owner_id
                if not effective_owner:
                    raise AgentRunBindingError("owner_id is required")
                if run.owner_id is not None and run.owner_id != effective_owner:
                    raise AgentRunBindingError("run owner mismatch")
                session_owner = conn.execute(
                    "SELECT owner_id, conversation_id, research_task_id FROM research_sessions WHERE research_session_id=?",
                    (run.research_session_id,),
                ).fetchone()
                if session_owner["owner_id"] != effective_owner:
                    raise AgentRunBindingError("session owner mismatch")
                session_task_id = session_owner["research_task_id"]
                if session_task_id is None:
                    if run.research_task_id is not None or run.work_item_id is not None:
                        raise AgentRunBindingError("unapproved session cannot bind task")
                    if run.role != "planner":
                        raise AgentRunBindingError("only planner may run before task approval")
                elif run.research_task_id != session_task_id:
                    raise AgentRunBindingError("task does not belong to session")
                if run.role != "planner" and (
                    run.research_task_id is None or run.work_item_id is None
                ):
                    raise AgentRunBindingError("execution run requires task and work item")
                if (
                    run.research_task_id
                    and not conn.execute(
                        "SELECT 1 FROM research_tasks WHERE research_task_id=? AND owner_id=? AND conversation_id=?",
                        (run.research_task_id, effective_owner, session_owner["conversation_id"]),
                    ).fetchone()
                ):
                    raise AgentRunBindingError("task owner/session mismatch")
                if (
                    run.work_item_id
                    and not conn.execute(
                        "SELECT 1 FROM research_work_items WHERE work_item_id=? AND research_task_id=?",
                        (run.work_item_id, run.research_task_id),
                    ).fetchone()
                ):
                    raise AgentRunBindingError("work item mismatch")
                if run.continued_from_agent_run_id:
                    previous = conn.execute(
                        """SELECT agent_run_id, research_session_id, research_task_id,
                           work_item_id, status
                           FROM research_agent_runs
                           WHERE agent_run_id=?""",
                        (run.continued_from_agent_run_id,),
                    ).fetchone()
                    if (
                        previous is None
                        or previous["research_session_id"] != run.research_session_id
                        or previous["research_task_id"] != run.research_task_id
                        or previous["work_item_id"] != run.work_item_id
                        or previous["status"] != "limit_reached"
                    ):
                        raise AgentRunBindingError("continued run binding is invalid")
                conn.execute(
                    """INSERT INTO research_agent_runs(agent_run_id, research_session_id, research_task_id, work_item_id, attempt, continued_from_agent_run_id, role, skill_name, skill_schema_version, skill_content_hash, resolved_model, reasoning_effort, provider, allowed_tools_json, status, model_loop_count, tool_call_count, input_hash, output_hash, checkpoint_ref, checkpoint_hash, error_code, started_at, ended_at, generation)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(
                        run.to_dict().get(key)
                        for key in (
                            "agent_run_id",
                            "research_session_id",
                            "research_task_id",
                            "work_item_id",
                            "attempt",
                            "continued_from_agent_run_id",
                            "role",
                            "skill_name",
                            "skill_schema_version",
                            "skill_content_hash",
                            "resolved_model",
                            "reasoning_effort",
                            "provider",
                            "allowed_tools_json",
                            "status",
                            "model_loop_count",
                            "tool_call_count",
                            "input_hash",
                            "output_hash",
                            "checkpoint_ref",
                            "checkpoint_hash",
                            "error_code",
                            "started_at",
                            "ended_at", "generation",
                        )
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_agent_runs WHERE agent_run_id=?", (run.agent_run_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AgentRun.from_row(dict(row))

    def get_agent_run(self, agent_run_id: str, owner_id: str) -> AgentRun | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT r.* FROM research_agent_runs r JOIN research_sessions s ON s.research_session_id=r.research_session_id
                WHERE r.agent_run_id=? AND s.owner_id=?""",
                (agent_run_id, owner_id),
            ).fetchone()
        return AgentRun.from_row(dict(row)) if row else None

    def get_agent_run_usage(
        self,
        owner_id: str,
        research_session_id: str,
        research_task_id: str | None,
        *,
        chain_from_agent_run_id: str | None = None,
    ) -> dict[str, int]:
        """Return owner-bound cumulative usage for a Task or continuation chain."""
        with self._connect() as conn:
            if chain_from_agent_run_id:
                row = conn.execute(
                    """WITH RECURSIVE chain(agent_run_id) AS (
                           SELECT agent_run_id FROM research_agent_runs
                           WHERE agent_run_id=?
                           UNION ALL
                           SELECT r.continued_from_agent_run_id
                           FROM research_agent_runs r JOIN chain c ON c.agent_run_id=r.agent_run_id
                           WHERE r.continued_from_agent_run_id IS NOT NULL
                       )
                       SELECT COALESCE(SUM(r.model_loop_count), 0) AS model_loops,
                              COALESCE(SUM(r.tool_call_count), 0) AS tool_calls
                       FROM research_agent_runs r
                       JOIN chain c ON c.agent_run_id=r.agent_run_id
                       JOIN research_sessions s ON s.research_session_id=r.research_session_id
                       WHERE s.owner_id=? AND r.research_session_id=?
                         AND (r.research_task_id IS ? OR r.research_task_id=?)""",
                    (chain_from_agent_run_id, owner_id, research_session_id, research_task_id, research_task_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT COALESCE(SUM(r.model_loop_count), 0) AS model_loops,
                              COALESCE(SUM(r.tool_call_count), 0) AS tool_calls
                       FROM research_agent_runs r
                       JOIN research_sessions s ON s.research_session_id=r.research_session_id
                       WHERE s.owner_id=? AND r.research_session_id=?
                         AND (r.research_task_id IS ? OR r.research_task_id=?)""",
                    (owner_id, research_session_id, research_task_id, research_task_id),
                ).fetchone()
        return {"model_loops": int(row["model_loops"]), "tool_calls": int(row["tool_calls"])}

    def update_agent_run_status(
        self, agent_run_id: str, owner_id: str, next_status: str, *, error_code: str | None = None
    ) -> AgentRun:
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT r.* FROM research_agent_runs r JOIN research_sessions s ON s.research_session_id=r.research_session_id
                    WHERE r.agent_run_id=? AND s.owner_id=?""",
                    (agent_run_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(agent_run_id)
                transition_agent_run(row["status"], next_status)
                now = _utcnow()
                ended = now if next_status != "running" else None
                generation = int(row["generation"])
                next_generation = generation + 1 if next_status != "running" else generation
                updated = conn.execute(
                    "UPDATE research_agent_runs SET status=?, error_code=?, started_at=COALESCE(started_at, ?), ended_at=?, generation=? WHERE agent_run_id=? AND status=? AND generation=?",
                    (next_status, error_code, now if next_status == "running" else None, ended, next_generation, agent_run_id, row["status"], generation),
                )
                if updated.rowcount != 1:
                    raise AgentRunWriteDiscarded()
                row = conn.execute("SELECT * FROM research_agent_runs WHERE agent_run_id=?", (agent_run_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AgentRun.from_row(dict(row))

    def update_agent_run_model_metadata(
        self,
        agent_run_id: str,
        owner_id: str,
        *,
        resolved_model: str,
        reasoning_effort: str,
        provider: str,
        expected_generation: int,
    ) -> AgentRun:
        """CAS-write the provider resolution for the currently running Run."""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT r.* FROM research_agent_runs r JOIN research_sessions s
                       ON s.research_session_id=r.research_session_id
                       WHERE r.agent_run_id=? AND s.owner_id=?""",
                    (agent_run_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(agent_run_id)
                if row["status"] != "running" or int(row["generation"]) != int(expected_generation):
                    raise AgentRunWriteDiscarded()
                updated = conn.execute(
                    """UPDATE research_agent_runs
                       SET resolved_model=?, reasoning_effort=?, provider=?
                       WHERE agent_run_id=? AND status='running' AND generation=?""",
                    (resolved_model, reasoning_effort, provider, agent_run_id, expected_generation),
                )
                if updated.rowcount != 1:
                    raise AgentRunWriteDiscarded()
                row = conn.execute(
                    "SELECT * FROM research_agent_runs WHERE agent_run_id=?", (agent_run_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AgentRun.from_row(dict(row))

    def update_agent_run_counters(
        self,
        agent_run_id: str,
        owner_id: str,
        *,
        model_loop_count: int | None = None,
        tool_call_count: int | None = None,
        checkpoint_ref: str | None = None,
        checkpoint_hash: str | None = None,
        output_hash: str | None = None,
        expected_generation: int | None = None,
    ) -> AgentRun:
        """Monotonic Run counters/checkpoint write barrier."""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT r.* FROM research_agent_runs r JOIN research_sessions s ON s.research_session_id=r.research_session_id
                    WHERE r.agent_run_id=? AND s.owner_id=?""",
                    (agent_run_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ResearchSessionNotFound(agent_run_id)
                loop = int(row["model_loop_count"]) if model_loop_count is None else int(model_loop_count)
                calls = int(row["tool_call_count"]) if tool_call_count is None else int(tool_call_count)
                if loop < int(row["model_loop_count"]) or calls < int(row["tool_call_count"]):
                    raise ValueError("agent run counters must be monotonic")
                generation = int(row["generation"])
                if expected_generation is not None and generation != int(expected_generation):
                    raise AgentRunWriteDiscarded()
                if row["status"] != "running":
                    raise AgentRunWriteDiscarded()
                updated = conn.execute(
                    "UPDATE research_agent_runs SET model_loop_count=?, tool_call_count=?, checkpoint_ref=COALESCE(?, checkpoint_ref), checkpoint_hash=COALESCE(?, checkpoint_hash), output_hash=COALESCE(?, output_hash) WHERE agent_run_id=? AND status='running' AND generation=?",
                    (loop, calls, checkpoint_ref, checkpoint_hash, output_hash, agent_run_id, generation),
                )
                if updated.rowcount != 1:
                    raise AgentRunWriteDiscarded()
                row = conn.execute("SELECT * FROM research_agent_runs WHERE agent_run_id=?", (agent_run_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AgentRun.from_row(dict(row))

    def create_agent_checkpoint(
        self, checkpoint: AgentCheckpoint, *, expected_generation: int | None = None
    ) -> AgentCheckpoint:
        """Insert an immutable checkpoint after validating complete run identity."""
        if not checkpoint.checkpoint_ref or not checkpoint.content_hash or not checkpoint.schema_version or not isinstance(checkpoint.content, str):
            raise ValueError("checkpoint identity is incomplete")
        if hashlib.sha256(checkpoint.content.encode("utf-8")).hexdigest() != checkpoint.content_hash:
            raise ValueError("checkpoint content hash mismatch")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                run = conn.execute(
                    """SELECT r.*, s.owner_id AS session_owner FROM research_agent_runs r
                    JOIN research_sessions s ON s.research_session_id=r.research_session_id
                    WHERE r.agent_run_id=?""", (checkpoint.agent_run_id,)
                ).fetchone()
                if run is None or run["session_owner"] != checkpoint.owner_id:
                    raise ValueError("checkpoint owner/run mismatch")
                if run["status"] != "running" or (
                    expected_generation is not None
                    and int(run["generation"]) != int(expected_generation)
                ):
                    raise AgentRunWriteDiscarded()
                if run["research_session_id"] != checkpoint.research_session_id or run["research_task_id"] != checkpoint.research_task_id or run["work_item_id"] != checkpoint.work_item_id:
                    raise ValueError("checkpoint binding mismatch")
                if checkpoint.continued_from_agent_run_id != run["continued_from_agent_run_id"]:
                    raise ValueError("checkpoint continuation binding mismatch")
                if checkpoint.continued_from_agent_run_id:
                    previous = conn.execute(
                        "SELECT research_session_id, research_task_id, work_item_id, status FROM research_agent_runs WHERE agent_run_id=?",
                        (checkpoint.continued_from_agent_run_id,),
                    ).fetchone()
                    if previous is None or previous["status"] != "limit_reached" or previous["research_session_id"] != checkpoint.research_session_id or previous["research_task_id"] != checkpoint.research_task_id or previous["work_item_id"] != checkpoint.work_item_id:
                        raise ValueError("checkpoint previous run binding mismatch")
                existing = conn.execute("SELECT * FROM research_agent_checkpoints WHERE checkpoint_ref=?", (checkpoint.checkpoint_ref,)).fetchone()
                if existing:
                    if existing["content_hash"] != checkpoint.content_hash or existing["owner_id"] != checkpoint.owner_id:
                        raise ValueError("checkpoint ref conflict")
                    conn.commit()
                    return AgentCheckpoint.from_row(dict(existing))
                conn.execute(
                    """INSERT INTO research_agent_checkpoints(checkpoint_ref, owner_id, research_session_id, research_task_id, work_item_id, agent_run_id, schema_version, content, content_hash, created_at, continued_from_agent_run_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (checkpoint.checkpoint_ref, checkpoint.owner_id, checkpoint.research_session_id, checkpoint.research_task_id, checkpoint.work_item_id, checkpoint.agent_run_id, checkpoint.schema_version, checkpoint.content, checkpoint.content_hash, checkpoint.created_at or _utcnow(), checkpoint.continued_from_agent_run_id),
                )
                row = conn.execute("SELECT * FROM research_agent_checkpoints WHERE checkpoint_ref=?", (checkpoint.checkpoint_ref,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AgentCheckpoint.from_row(dict(row))

    def get_agent_checkpoint(self, checkpoint_ref: str, owner_id: str) -> AgentCheckpoint | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_agent_checkpoints WHERE checkpoint_ref=? AND owner_id=?",
                (checkpoint_ref, owner_id),
            ).fetchone()
        return AgentCheckpoint.from_row(dict(row)) if row else None

    def create_artifact(self, artifact: ResearchArtifact, *, owner_id: str | None = None) -> ResearchArtifact:
        if artifact.artifact_type not in {"markdown", "html", "citation_manifest", "intermediate"}:
            raise ValueError("invalid artifact type")
        if int(artifact.report_version) < 1:
            raise ValueError("artifact report_version must be positive")
        if (artifact.content is None) == (artifact.storage_ref is None):
            raise ValueError("artifact content/storage_ref are mutually exclusive")
        if artifact.content is not None:
            content_hash = hashlib.sha256(artifact.content.encode("utf-8")).hexdigest()
            if artifact.content_hash != content_hash:
                raise ValueError("artifact content_hash does not match content")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if owner_id is not None and not conn.execute(
                    "SELECT 1 FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (artifact.research_task_id, owner_id),
                ).fetchone():
                    raise ResearchTaskNotFound(artifact.research_task_id)
                if not conn.execute(
                    "SELECT 1 FROM research_agent_runs WHERE agent_run_id=? AND research_task_id=? AND role='synthesizer'",
                    (artifact.generated_by_agent_run_id, artifact.research_task_id),
                ).fetchone():
                    raise ValueError("artifact generator is not synthesizer run")
                conn.execute(
                    """INSERT INTO research_artifacts(artifact_id, research_task_id, report_version, artifact_type, content, storage_ref, content_hash, generated_by_agent_run_id, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        artifact.artifact_id,
                        artifact.research_task_id,
                        artifact.report_version,
                        artifact.artifact_type,
                        artifact.content,
                        artifact.storage_ref,
                        artifact.content_hash,
                        artifact.generated_by_agent_run_id,
                        artifact.created_at or _utcnow(),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_artifacts WHERE artifact_id=?", (artifact.artifact_id,)
                ).fetchone()
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ResearchArtifactConflict() from exc
            except Exception:
                conn.rollback()
                raise
        return ResearchArtifact.from_row(dict(row))

    def list_artifacts(
        self, research_task_id: str, *, report_version: int | None = None, owner_id: str | None = None
    ) -> list[ResearchArtifact]:
        if owner_id is not None:
            return self.list_artifacts_for_task(research_task_id, owner_id, report_version=report_version)
        params: list[object] = [research_task_id]
        sql = "SELECT * FROM research_artifacts WHERE research_task_id=?"
        if report_version is not None:
            sql += " AND report_version=?"
            params.append(report_version)
        sql += " ORDER BY report_version, artifact_type"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ResearchArtifact.from_row(dict(row)) for row in rows]

    def get_artifact(self, artifact_id: str, owner_id: str) -> ResearchArtifact | None:
        """Read one artifact through its task owner binding.

        Artifact rows intentionally do not duplicate ``owner_id``.  The join
        is the authorization boundary and prevents a guessed artifact ID from
        crossing task/owner scope.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT a.* FROM research_artifacts a
                JOIN research_tasks t ON t.research_task_id=a.research_task_id
                WHERE a.artifact_id=? AND t.owner_id=?""",
                (artifact_id, owner_id),
            ).fetchone()
        return ResearchArtifact.from_row(dict(row)) if row else None

    def list_artifacts_for_task(
        self, research_task_id: str, owner_id: str, *, report_version: int | None = None
    ) -> list[ResearchArtifact]:
        """Owner-scoped artifact listing; unknown/cross-owner task is empty."""
        with self._connect() as conn:
            params: list[object] = [research_task_id, owner_id]
            sql = """SELECT a.* FROM research_artifacts a
                JOIN research_tasks t ON t.research_task_id=a.research_task_id
                WHERE a.research_task_id=? AND t.owner_id=?"""
            if report_version is not None:
                sql += " AND a.report_version=?"
                params.append(report_version)
            sql += " ORDER BY a.report_version, a.artifact_type, a.artifact_id"
            rows = conn.execute(sql, params).fetchall()
        return [ResearchArtifact.from_row(dict(row)) for row in rows]

    def create_notification(self, notification: ResearchNotification) -> ResearchNotification:
        if notification.notification_kind not in NOTIFICATION_KINDS or notification.status not in NOTIFICATION_STATUSES:
            raise ValueError("invalid notification")
        if (notification.status == "read") != bool(notification.read_at):
            raise ValueError("read_at/status mismatch")
        try:
            payload = json.loads(notification.payload_json or "{}")
        except (TypeError, ValueError) as exc:
            raise ValueError("notification payload must be JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("notification payload must be an object")
        _validate_notification_payload(payload)
        with self._connect() as read_conn:
            existing = read_conn.execute(
                "SELECT * FROM research_notifications WHERE owner_id=? AND idempotency_key=?",
                (notification.owner_id, notification.idempotency_key),
            ).fetchone()
        if existing is not None:
            if _notification_identity_matches(existing, notification):
                return ResearchNotification.from_row(dict(existing))
            raise NotificationConflict()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if (
                    notification.research_session_id
                    and not conn.execute(
                        "SELECT 1 FROM research_sessions WHERE research_session_id=? AND owner_id=?",
                        (notification.research_session_id, notification.owner_id),
                    ).fetchone()
                ):
                    raise ResearchSessionNotFound(notification.research_session_id)
                if (
                    notification.research_task_id
                    and not conn.execute(
                        "SELECT 1 FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                        (notification.research_task_id, notification.owner_id),
                    ).fetchone()
                ):
                    raise ResearchTaskNotFound(notification.research_task_id)
                if notification.research_session_id and notification.research_task_id:
                    task_binding = conn.execute(
                        "SELECT 1 FROM research_sessions WHERE research_session_id=? AND research_task_id=? AND owner_id=?",
                        (notification.research_session_id, notification.research_task_id, notification.owner_id),
                    ).fetchone()
                    if task_binding is None:
                        raise ValueError("notification task/session mismatch")
                # Allocate owner-scoped event_seq atomically when callers leave it at 0.
                current_seq = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(event_seq),0) FROM research_notifications WHERE owner_id=?",
                        (notification.owner_id,),
                    ).fetchone()[0]
                )
                if notification.event_seq and int(notification.event_seq) <= current_seq:
                    raise ValueError("notification event_seq must increase")
                seq = notification.event_seq or current_seq + 1
                conn.execute(
                    """INSERT INTO research_notifications(notification_id, owner_id, research_session_id, research_task_id, notification_kind, status, subject_version, event_seq, payload_json, idempotency_key, read_at, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        notification.notification_id,
                        notification.owner_id,
                        notification.research_session_id,
                        notification.research_task_id,
                        notification.notification_kind,
                        notification.status,
                        notification.subject_version,
                        seq,
                        notification.payload_json,
                        notification.idempotency_key,
                        notification.read_at,
                        notification.created_at or _utcnow(),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM research_notifications WHERE notification_id=?", (notification.notification_id,)
                ).fetchone()
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                with self._connect() as read_conn:
                    existing = read_conn.execute(
                        "SELECT * FROM research_notifications WHERE owner_id=? AND idempotency_key=?",
                        (notification.owner_id, notification.idempotency_key),
                    ).fetchone()
                if existing is not None:
                    if _notification_identity_matches(existing, notification):
                        return ResearchNotification.from_row(dict(existing))
                    raise NotificationConflict() from exc
                raise NotificationConflict() from exc
            except Exception:
                conn.rollback()
                raise
        return ResearchNotification.from_row(dict(row))

    def mark_notification_read(self, notification_id: str, owner_id: str) -> ResearchNotification | None:
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM research_notifications WHERE notification_id=? AND owner_id=?",
                (notification_id, owner_id),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            if row["status"] == "unread":
                conn.execute(
                    "UPDATE research_notifications SET status='read', read_at=? WHERE notification_id=? AND owner_id=? AND status='unread'",
                    (_utcnow(), notification_id, owner_id),
                )
            row = conn.execute(
                "SELECT * FROM research_notifications WHERE notification_id=?", (notification_id,)
            ).fetchone()
            conn.commit()
        return ResearchNotification.from_row(dict(row))

    def list_notifications(self, owner_id: str, *, after_seq: int = 0, limit: int = 100) -> list[ResearchNotification]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_notifications WHERE owner_id=? AND event_seq>? ORDER BY event_seq LIMIT ?",
                (owner_id, int(after_seq), max(1, min(int(limit), 500))),
            ).fetchall()
        return [ResearchNotification.from_row(dict(row)) for row in rows]

    # ------------------------------------------------------------------ #
    # ResearchEvent（event_seq 原子领号）
    # ------------------------------------------------------------------ #

    def append_event(self, research_task_id: str, event_type: str, payload: dict) -> ResearchEvent:
        """原子追加事件：同事务内先 UPDATE 领号再 INSERT，保证并发不冲突/不重用/无洞。

        event_type 必须在 EVENT_TYPES 内，否则 ValueError；payload 用 json.dumps(ensure_ascii=False,
        sort_keys=True) 存 safe_payload_json。任务不存在（UPDATE 影响 0 行）抛 ResearchTaskNotFound。
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event_type}")
        payload = _safe_event_payload(payload)
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "UPDATE research_tasks SET last_event_seq = last_event_seq + 1, updated_at=? WHERE research_task_id=?",
                    (_utcnow(), research_task_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise ResearchTaskNotFound(research_task_id)
                seq_row = conn.execute(
                    "SELECT last_event_seq FROM research_tasks WHERE research_task_id=?",
                    (research_task_id,),
                ).fetchone()
                seq = int(seq_row["last_event_seq"])
                now = _utcnow()
                safe_payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                conn.execute(
                    """INSERT INTO research_events(research_task_id, event_seq, event_type, safe_payload_json, created_at)
                       VALUES(?,?,?,?,?)""",
                    (research_task_id, seq, event_type, safe_payload_json, now),
                )
                row = conn.execute(
                    "SELECT * FROM research_events WHERE research_task_id=? AND event_seq=?",
                    (research_task_id, seq),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchEvent.from_row(dict(row))

    def list_events(self, research_task_id: str, *, after_seq: int = 0, limit: int = 200) -> list[ResearchEvent]:
        """按 event_seq 升序列出事件；after_seq 之后、limit 夹到 1..1000。"""
        limit = max(1, min(int(limit), 1000))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_events WHERE research_task_id=? AND event_seq > ? ORDER BY event_seq ASC LIMIT ?",
                (research_task_id, int(after_seq), limit),
            ).fetchall()
        return [ResearchEvent.from_row(dict(r)) for r in rows]

    def last_event_seq(self, research_task_id: str) -> int:
        """返回某任务当前 last_event_seq（不存在/无事件返回 0）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_event_seq FROM research_tasks WHERE research_task_id=?",
                (research_task_id,),
            ).fetchone()
        return int(row["last_event_seq"]) if row is not None else 0

    # ------------------------------------------------------------------ #
    # Spec031 routing observation (bounded + owner scoped)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _routing_decision_from_row(row):
        from backend.app.research.application.routing_observation import RoutingDecision
        return RoutingDecision(
            decision_id=row["decision_id"], owner_id=row["owner_id"],
            task_type=row["task_type"], features=json.loads(row["features_json"]),
            candidate_models=json.loads(row["candidate_models_json"]),
            chosen_model=row["chosen_model"], reason=row["reason"],
            policy_version=row["policy_version"], created_at=row["created_at"],
        )

    @staticmethod
    def _model_outcome_from_row(row):
        from backend.app.research.application.routing_observation import ModelOutcome
        return ModelOutcome(
            decision_id=row["decision_id"], schema_valid=None if row["schema_valid"] is None else bool(row["schema_valid"]),
            quality_score=row["quality_score"], ttft=row["ttft"], duration=row["duration"],
            tokens=row["tokens"], error_code=row["error_code"], created_at=row["created_at"],
        )

    @staticmethod
    def _resource_observation_from_row(row):
        from backend.app.research.application.routing_observation import ResourceObservation
        return ResourceObservation(
            snapshot_id=row["snapshot_id"], owner_id=row["owner_id"],
            available_memory=row["available_memory"], loaded_models=json.loads(row["loaded_models_json"]),
            estimated_kv=row["estimated_kv"], active_workers=row["active_workers"],
            captured_at=row["captured_at"], probe_error=row["probe_error"],
        )

    def save_routing_decision(self, decision, *, idempotency_key: str | None = None):
        """Persist one redacted decision; same owner/key is idempotent."""
        # Keep the persistence seam safe even when callers bypass the
        # application service and hand-build a dataclass.
        from backend.app.research.application.routing_observation import _validate_routing_decision
        _validate_routing_decision(decision, idempotency_key=idempotency_key)
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = conn.execute(
                        "SELECT * FROM research_routing_decisions WHERE owner_id=? AND idempotency_key=?",
                        (decision.owner_id, idempotency_key),
                    ).fetchone()
                    if existing:
                        if existing["decision_id"] != decision.decision_id and (
                            existing["task_type"] != decision.task_type
                            or existing["chosen_model"] != decision.chosen_model
                            or existing["policy_version"] != decision.policy_version
                        ):
                            raise ValueError("routing decision idempotency conflict")
                        conn.commit()
                        return self._routing_decision_from_row(existing)
                existing = conn.execute(
                    "SELECT * FROM research_routing_decisions WHERE decision_id=?", (decision.decision_id,)
                ).fetchone()
                if existing:
                    candidate = self._routing_decision_from_row(existing)
                    if candidate.owner_id != decision.owner_id or candidate.public() != decision.public():
                        raise ValueError("routing decision identity conflict")
                    conn.commit()
                    return candidate
                conn.execute(
                    """INSERT INTO research_routing_decisions(
                       decision_id, owner_id, idempotency_key, task_type, features_json,
                       candidate_models_json, chosen_model, reason, policy_version, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (decision.decision_id, decision.owner_id, idempotency_key, decision.task_type,
                     json.dumps(decision.features, ensure_ascii=False, sort_keys=True),
                     json.dumps(decision.candidate_models, ensure_ascii=False), decision.chosen_model,
                     decision.reason, decision.policy_version, decision.created_at or _utcnow()),
                )
                row = conn.execute("SELECT * FROM research_routing_decisions WHERE decision_id=?", (decision.decision_id,)).fetchone()
                conn.commit()
                return self._routing_decision_from_row(row)
            except Exception:
                conn.rollback()
                raise

    record_routing_decision = save_routing_decision

    def get_routing_decision(self, decision_id: str, *, owner_id: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_routing_decisions WHERE decision_id=? AND owner_id=?",
                (decision_id, owner_id),
            ).fetchone()
        return self._routing_decision_from_row(row) if row else None

    def list_routing_decisions(self, *, owner_id: str, task_type: str | None = None, limit: int = 100):
        limit = max(1, min(int(limit), 500))
        query = "SELECT * FROM research_routing_decisions WHERE owner_id=?"
        args: list[object] = [owner_id]
        if task_type:
            query += " AND task_type=?"
            args.append(task_type)
        query += " ORDER BY created_at ASC, decision_id ASC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()
        return [self._routing_decision_from_row(row) for row in rows]

    def list_routing_decisions_paged(
        self, *, owner_id: str, task_type: str | None = None, filter_text: str | None = None,
        cursor: str | None = None, limit: int = 20,
    ) -> tuple[list[object], str | None]:
        """Owner-scoped, redaction-agnostic keyset page of routing decisions.

        ``cursor`` is the opaque ``encode_cursor(created_at, decision_id)`` token;
        an undecodable cursor raises ``ValueError`` so the API layer can map it to
        a 400.  Filtering is an owner-scoped substring match over task_type /
        chosen_model / reason.  ``limit`` is clamped to [1, 100]; the returned
        page never exceeds it and ``next_cursor`` is None on the last page.
        """
        limit = max(1, min(int(limit), 100))
        args: list[object] = [owner_id]
        sql = "SELECT * FROM research_routing_decisions WHERE owner_id=?"
        if task_type:
            sql += " AND task_type=?"
            args.append(task_type)
        if filter_text:
            sql += " AND (task_type LIKE ? OR chosen_model LIKE ? OR reason LIKE ?)"
            like = f"%{filter_text}%"
            args.extend([like, like, like])
        if cursor is not None:
            at, tid = decode_cursor(cursor)  # raises ValueError -> 400 upstream
            sql += " AND (created_at, decision_id) > (?, ?)"
            args.extend([at, tid])
        sql += " ORDER BY created_at ASC, decision_id ASC LIMIT ?"
        args.append(limit + 1)
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        page = rows[:limit]
        items = [self._routing_decision_from_row(row) for row in page]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at, last.decision_id)
        return items, next_cursor

    def save_model_outcome(self, outcome, *, owner_id: str):
        from backend.app.research.application.routing_observation import _bounded_text, _validate_outcome
        _bounded_text(owner_id, name="owner_id", limit=160)
        _bounded_text(outcome.decision_id, name="decision_id", limit=160)
        _bounded_text(outcome.created_at or _utcnow(), name="created_at", limit=64)
        for field in ("schema_valid", "quality_score", "ttft", "duration", "tokens", "error_code"):
            _validate_outcome(getattr(outcome, field), field=field)
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                decision = conn.execute(
                    "SELECT owner_id FROM research_routing_decisions WHERE decision_id=?", (outcome.decision_id,)
                ).fetchone()
                if decision is None or decision["owner_id"] != owner_id:
                    raise ValueError("routing outcome decision is not owned by owner")
                existing = conn.execute("SELECT * FROM research_model_outcomes WHERE decision_id=?", (outcome.decision_id,)).fetchone()
                if existing:
                    candidate = self._model_outcome_from_row(existing)
                    if candidate.public() != outcome.public() or existing["owner_id"] != owner_id:
                        raise ValueError("routing outcome idempotency conflict")
                    conn.commit()
                    return candidate
                conn.execute(
                    """INSERT INTO research_model_outcomes(
                       decision_id, owner_id, schema_valid, quality_score, ttft,
                       duration, tokens, error_code, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (outcome.decision_id, owner_id,
                     None if outcome.schema_valid is None else int(outcome.schema_valid), outcome.quality_score,
                     outcome.ttft, outcome.duration, outcome.tokens, outcome.error_code,
                     outcome.created_at or _utcnow()),
                )
                row = conn.execute("SELECT * FROM research_model_outcomes WHERE decision_id=?", (outcome.decision_id,)).fetchone()
                conn.commit()
                return self._model_outcome_from_row(row)
            except Exception:
                conn.rollback()
                raise

    record_model_outcome = save_model_outcome

    def get_model_outcome(self, decision_id: str, *, owner_id: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_model_outcomes WHERE decision_id=? AND owner_id=?",
                (decision_id, owner_id),
            ).fetchone()
        return self._model_outcome_from_row(row) if row else None

    def save_resource_snapshot(self, observation):
        from backend.app.research.application.routing_observation import _bounded_text, _safe_models
        _bounded_text(observation.owner_id, name="owner_id", limit=160)
        _bounded_text(observation.snapshot_id, name="snapshot_id", limit=160)
        _bounded_text(observation.captured_at, name="captured_at", limit=64)
        _safe_models(observation.loaded_models)
        if observation.probe_error is not None:
            _bounded_text(observation.probe_error, name="probe_error", limit=80)
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute("SELECT * FROM research_resource_snapshots WHERE snapshot_id=?", (observation.snapshot_id,)).fetchone()
                if existing:
                    current = self._resource_observation_from_row(existing)
                    if current.owner_id != observation.owner_id or current.public() != observation.public():
                        raise ValueError("resource snapshot idempotency conflict")
                    conn.commit()
                    return current
                conn.execute(
                    """INSERT INTO research_resource_snapshots(
                       snapshot_id, owner_id, available_memory, loaded_models_json,
                       estimated_kv, active_workers, captured_at, probe_error)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (observation.snapshot_id, observation.owner_id, observation.available_memory,
                     json.dumps(observation.loaded_models, ensure_ascii=False), observation.estimated_kv,
                     observation.active_workers, observation.captured_at, observation.probe_error),
                )
                row = conn.execute("SELECT * FROM research_resource_snapshots WHERE snapshot_id=?", (observation.snapshot_id,)).fetchone()
                conn.commit()
                return self._resource_observation_from_row(row)
            except Exception:
                conn.rollback()
                raise

    record_resource_snapshot = save_resource_snapshot

    def list_resource_snapshots(self, *, owner_id: str, limit: int = 100):
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_resource_snapshots WHERE owner_id=? ORDER BY captured_at ASC, snapshot_id ASC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
        return [self._resource_observation_from_row(row) for row in rows]

    def save_routing_policy(self, payload: dict) -> dict:
        from backend.app.research.application.routing_observation import _safe_policy_payload
        payload = _safe_policy_payload(payload)
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute("SELECT * FROM research_routing_policies WHERE version=?", (payload["version"],)).fetchone()
                if existing:
                    current = {
                        "version": existing["version"], "profile": existing["profile"],
                        "rules": json.loads(existing["rules_json"]), "thresholds": json.loads(existing["thresholds_json"]),
                        "status": existing["status"], "created_at": existing["created_at"],
                    }
                    if current["profile"] != payload["profile"] or current["rules"] != payload["rules"] or current["thresholds"] != payload["thresholds"]:
                        raise ValueError("routing policy version conflict")
                    conn.commit()
                    return current
                conn.execute(
                    """INSERT INTO research_routing_policies(version, profile, rules_json, thresholds_json, status, created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (payload["version"], payload["profile"], json.dumps(payload["rules"], ensure_ascii=False, sort_keys=True), json.dumps(payload["thresholds"], ensure_ascii=False, sort_keys=True), payload["status"], payload["created_at"]),
                )
                conn.commit()
                return payload
            except Exception:
                conn.rollback()
                raise

    def get_routing_policy(self, version: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM research_routing_policies WHERE version=?", (version,)).fetchone()
        if row is None:
            return None
        return {
            "version": row["version"], "profile": row["profile"], "rules": json.loads(row["rules_json"]),
            "thresholds": json.loads(row["thresholds_json"]), "status": row["status"], "created_at": row["created_at"],
        }

    def get_active_routing_policy(self) -> dict | None:
        """Return the single currently-active routing policy, or None.

        Used by the read-only ``GET /status`` projection.  Never raises on a
        missing row; a None result is the legitimate "no active policy" state.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_routing_policies WHERE status='active' ORDER BY created_at DESC, version DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "version": row["version"], "profile": row["profile"], "rules": json.loads(row["rules_json"]),
            "thresholds": json.loads(row["thresholds_json"]), "status": row["status"], "created_at": row["created_at"],
        }

    def activate_routing_policy(self, version: str, *, expected_status: str | None = None) -> dict:
        """Atomically retire the current active policy and activate ``version``.

        Task03 intentionally rejects ``active`` at the write seam.  Task04 is
        the only explicit activation seam and keeps the transition in one
        SQLite transaction so a failed update cannot leave two active
        policies (or no active policy).
        """
        if not version:
            raise ValueError("routing policy version is required")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_spec031_schema(conn)
                target = conn.execute(
                    "SELECT * FROM research_routing_policies WHERE version=?", (version,)
                ).fetchone()
                if target is None:
                    raise ValueError("routing policy not found")
                if target["status"] == "active":
                    conn.commit()
                    return {
                        "version": target["version"], "profile": target["profile"],
                        "rules": json.loads(target["rules_json"]),
                        "thresholds": json.loads(target["thresholds_json"]),
                        "status": target["status"], "created_at": target["created_at"],
                    }
                if target["status"] not in {"draft", "shadow"}:
                    raise ValueError("only draft or shadow policy may be activated")
                if expected_status is not None and target["status"] != expected_status:
                    raise ValueError("routing policy status changed")
                conn.execute(
                    "UPDATE research_routing_policies SET status='retired' WHERE status='active' AND version<>?",
                    (version,),
                )
                changed = conn.execute(
                    "UPDATE research_routing_policies SET status='active' WHERE version=? AND status IN ('draft','shadow')",
                    (version,),
                ).rowcount
                if changed != 1:
                    raise ValueError("routing policy activation conflict")
                row = conn.execute(
                    "SELECT * FROM research_routing_policies WHERE version=?", (version,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "version": row["version"], "profile": row["profile"],
            "rules": json.loads(row["rules_json"]),
            "thresholds": json.loads(row["thresholds_json"]),
            "status": row["status"], "created_at": row["created_at"],
        }

    def mark_projection_retry(self, research_task_id: str, event_seq: int, error: str) -> dict:
        source_event_id = canonical_research_event_id(research_task_id, event_seq)
        with self._connect() as conn, _write_lock:
            conn.execute(
                """INSERT INTO research_projection_retries(source_event_id, research_task_id, attempts, error_code, last_error, pending, updated_at)
                VALUES(?,?,1,'TRACE_PROJECTION_FAILED',?,1,?)
                ON CONFLICT(source_event_id) DO UPDATE SET attempts=attempts+1, last_error=excluded.last_error, pending=1, updated_at=excluded.updated_at""",
                (source_event_id, research_task_id, "TRACE_PROJECTION_FAILED", _utcnow()),
            )
            row = conn.execute(
                "SELECT * FROM research_projection_retries WHERE source_event_id=?", (source_event_id,)
            ).fetchone()
        return dict(row)

    def clear_projection_retry(self, source_event_id: str) -> bool:
        with self._connect() as conn, _write_lock:
            result = conn.execute(
                "UPDATE research_projection_retries SET pending=0, updated_at=? WHERE source_event_id=?",
                (_utcnow(), source_event_id),
            )
        return bool(result.rowcount)

    def list_projection_retries(self, research_task_id: str | None = None, *, pending_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM research_projection_retries WHERE 1=1"
        params: list[object] = []
        if research_task_id is not None:
            sql += " AND research_task_id=?"
            params.append(research_task_id)
        if pending_only:
            sql += " AND pending=1"
        sql += " ORDER BY updated_at, source_event_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def replay_persisted_events(
        self,
        research_task_id: str,
        events: list[ResearchEvent] | None = None,
        *,
        projector: Callable[[ResearchEvent], object] | None = None,
        strict_tree: bool = False,
    ) -> list[ResearchEvent]:
        """Replay durable events parent-first, then by event sequence.

        ``ResearchEvent`` remains the source of truth.  The optional callable
        is deliberately a seam for the later ProcessingStep projector: each
        successful callback clears its retry marker; a failure records (or
        increments) one and is re-raised without changing the durable event.
        """
        if events is not None:
            persisted = events
        else:
            persisted = []
            after_seq = 0
            target_seq = self.last_event_seq(research_task_id)
            while after_seq < target_seq:
                page = self.list_events(research_task_id, after_seq=after_seq, limit=1000)
                if not page:
                    break
                persisted.extend(page)
                next_seq = page[-1].event_seq
                if next_seq <= after_seq:
                    raise RuntimeError("replay event pagination cursor did not advance")
                after_seq = next_seq
        if any(event.research_task_id != research_task_id for event in persisted):
            raise ValueError("replay event belongs to another task")
        records: list[tuple[ResearchEvent, dict, str]] = []
        for event in persisted:
            try:
                try:
                    payload = json.loads(event.safe_payload_json or "{}")
                except (TypeError, ValueError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                expected_source_event_id = canonical_research_event_id(research_task_id, event.event_seq)
                supplied_source_event_id = payload.get("source_event_id")
                if supplied_source_event_id is not None and str(supplied_source_event_id) != expected_source_event_id:
                    raise ValueError("replay source_event_id is not canonical")
                source_event_id = expected_source_event_id
                records.append((event, payload, source_event_id))
            except Exception as exc:
                self.mark_projection_retry(research_task_id, event.event_seq, str(exc))
                raise
        by_source = {source: (event, payload, source) for event, payload, source in records}
        if len(by_source) != len(records):
            raise ValueError("replay contains duplicate event identity")
        by_key = {
            str(payload["node_key"]): (event, payload, source)
            for event, payload, source in records
            if payload.get("node_key")
        }

        def depth(record: tuple[ResearchEvent, dict, str], seen: set[str] | None = None) -> int:
            _event, payload, _source = record
            parent_source = payload.get("parent_source_event_id")
            parent_key = payload.get("parent_node_key")
            if not parent_source and not parent_key:
                return 0
            parent = by_source.get(str(parent_source)) if parent_source else by_key.get(str(parent_key))
            if parent is None:
                raise ValueError("replay parent event is missing")
            marker = str(parent_source or parent_key)
            seen = seen or set()
            if marker in seen:
                raise ValueError("replay parent cycle")
            return 1 + depth(parent, seen | {marker})

        def tree_type(payload: dict, event: ResearchEvent) -> str:
            value = str(payload.get("node_type") or "").casefold()
            if value == "work_item":
                value = "agent"
            if value in {"phase", "agent", "skill", "tool", "operation"}:
                return value
            return {"task": "phase", "plan": "phase", "coverage": "phase", "report": "phase", "terminal": "phase", "worker": "agent"}.get(event.event_type, "operation")

        def validate_tree(record: tuple[ResearchEvent, dict, str], seen: set[str] | None = None) -> int:
            event, payload, _source = record
            parent_source = payload.get("parent_source_event_id")
            parent_key = payload.get("parent_node_key")
            if parent_source and parent_key:
                source_parent = by_source.get(str(parent_source))
                key_parent = by_key.get(str(parent_key))
                source_key = source_parent[1].get("node_key") if source_parent else None
                if source_parent is None or key_parent is None or str(source_key) != str(parent_key):
                    raise ValueError("replay parent source_event_id and node_key conflict")
            parent = by_source.get(str(parent_source)) if parent_source else by_key.get(str(parent_key))
            if parent is None:
                if parent_source or parent_key:
                    raise ValueError("replay parent event is missing")
                depth_value = 0
            else:
                marker = str(parent_source or parent_key)
                if marker in (seen or set()):
                    raise ValueError("replay parent cycle")
                depth_value = validate_tree(parent, (seen or set()) | {marker}) + 1
            if depth_value >= 3:
                raise ValueError("replay tree exceeds three levels")
            if strict_tree:
                actual = tree_type(payload, event)
                expected = "phase" if depth_value == 0 else "agent" if depth_value == 1 else "skill_or_tool"
                if (expected == "phase" and actual != "phase") or (expected == "agent" and actual != "agent") or (expected == "skill_or_tool" and actual not in {"skill", "tool"}):
                    raise ValueError("invalid research processing tree node type")
            return depth_value

        marked_failure: int | None = None
        try:
            if strict_tree:
                for record in records:
                    try:
                        validate_tree(record)
                    except Exception as exc:
                        self.mark_projection_retry(research_task_id, record[0].event_seq, str(exc))
                        marked_failure = record[0].event_seq
                        raise
            records.sort(key=lambda record: (depth(record), int(record[0].event_seq)))
        except Exception as exc:
            # Parent ordering is part of projection, not event persistence.
            # Keep the durable event untouched and leave an explicit retry
            # marker so a later replay can recover after the missing parent or
            # cycle is resolved.
            failed = next(
                (
                    event for event, payload, _source in records
                    if payload.get("parent_source_event_id") or payload.get("parent_node_key")
                ),
                records[0][0] if records else None,
            )
            if failed is not None and marked_failure is None:
                self.mark_projection_retry(research_task_id, failed.event_seq, str(exc))
            raise
        ordered = [record[0] for record in records]
        if projector is not None:
            for event in ordered:
                source_event_id = canonical_research_event_id(research_task_id, event.event_seq)
                try:
                    projector(event)
                except Exception as exc:
                    self.mark_projection_retry(research_task_id, event.event_seq, str(exc))
                    raise
                self.clear_projection_retry(source_event_id)
        return ordered

    replay_events = replay_persisted_events

    # ------------------------------------------------------------------ #
    # ResearchPaperSelection
    # ------------------------------------------------------------------ #

    def replace_selections(
        self, research_task_id: str, selections: list[ResearchPaperSelection]
    ) -> list[ResearchPaperSelection]:
        """单事务先删旧选集再插新；evidence_level 不在 EVIDENCE_LEVELS 内抛 ValueError（整批不落库）。"""
        for s in selections:
            if s.evidence_level not in EVIDENCE_LEVELS:
                raise ValueError(f"invalid evidence_level: {s.evidence_level}")
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM research_paper_selections WHERE research_task_id=?", (research_task_id,)
                )
                now = _utcnow()
                conn.execute(
                    """INSERT INTO research_selection_versions(research_task_id, selection_version, updated_at)
                    VALUES(?,?,?)
                    ON CONFLICT(research_task_id) DO UPDATE SET
                        selection_version=research_selection_versions.selection_version+1,
                        updated_at=excluded.updated_at""",
                    (research_task_id, 1, now),
                )
                for s in selections:
                    conn.execute(
                        """INSERT INTO research_paper_selections(
                            research_task_id, catalog_paper_id, relevance, facets_json, evidence_level,
                            created_at, source_search_id
                        ) VALUES(?,?,?,?,?,?,?)""",
                        (
                            research_task_id,
                            s.catalog_paper_id,
                            s.relevance,
                            s.facets_json,
                            s.evidence_level,
                            s.created_at or now,
                            getattr(s, "source_search_id", None),
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.list_selections(research_task_id)

    def get_selection_version(self, research_task_id: str) -> int:
        """Return the durable candidate snapshot version (zero before first selection)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT selection_version FROM research_selection_versions WHERE research_task_id=?",
                (research_task_id,),
            ).fetchone()
        return int(row["selection_version"]) if row else 0

    def list_selections(self, research_task_id: str) -> list[ResearchPaperSelection]:
        """列出某任务论文选集（按 relevance 降序）；只引用 Spec015 目录 catalog_paper_id，不复制元数据。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_paper_selections WHERE research_task_id=? ORDER BY relevance DESC",
                (research_task_id,),
            ).fetchall()
        return [ResearchPaperSelection.from_row(dict(r)) for r in rows]

    def update_selection_source(self, research_task_id: str, catalog_paper_id: str, search_id: str) -> None:
        """把某条选集的来源快照句柄改写为刷新后的 search_id。

        搜索快照过期后按原 query 重跑检索会得到新句柄；写回后后续确认/重试可直接
        复用，不必每次都刷新。只改句柄，不动 relevance/facets/evidence_level，
        也不触碰 selection_version（选集内容没变）。
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE research_paper_selections SET source_search_id=? "
                    "WHERE research_task_id=? AND catalog_paper_id=?",
                    (str(search_id), research_task_id, str(catalog_paper_id)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------------ #
    # Spec029 acquisition bridge (references only; no KB state is copied)
    # ------------------------------------------------------------------ #

    def create_acquisition_approval(self, approval: AcquisitionApproval) -> AcquisitionApproval:
        """Persist one confirmation snapshot, returning the existing row on replay.

        The task/version unique key is the primary idempotency guard.  A replay
        with a different candidate set is rejected instead of silently
        submitting a second import batch.
        """
        if not approval.task_id or int(approval.selection_version) < 1:
            raise ValueError("invalid acquisition approval")
        paper_ids = [str(value) for value in approval.paper_ids if str(value)]
        if not paper_ids or len(set(paper_ids)) != len(paper_ids):
            raise ValueError("paper_ids must be non-empty and unique")
        encoded = json.dumps(paper_ids, ensure_ascii=False, separators=(",", ":"))
        now = approval.created_at or _utcnow()
        updated = approval.updated_at or now
        approval_id = approval.to_dict().get("approval_id") or uuid.uuid4().hex
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if approval.idempotency_key:
                    replay = conn.execute(
                        "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? AND idempotency_key=?",
                        (approval.task_id, approval.idempotency_key),
                    ).fetchone()
                    if replay is not None:
                        current = AcquisitionApproval.from_row(dict(replay))
                        if (
                            current.selection_version != int(approval.selection_version)
                            or current.paper_ids != paper_ids
                        ):
                            raise ValueError("acquisition idempotency key conflicts with an existing confirmation")
                        conn.commit()
                        return current
                existing = conn.execute(
                    "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? AND selection_version=?",
                    (approval.task_id, int(approval.selection_version)),
                ).fetchone()
                if existing is not None:
                    current = AcquisitionApproval.from_row(dict(existing))
                    if current.paper_ids != paper_ids:
                        raise ValueError("acquisition selection version is already confirmed")
                    conn.commit()
                    return current
                conn.execute(
                    """INSERT INTO research_acquisition_approvals(
                        approval_id,research_task_id,selection_version,paper_ids_json,status,idempotency_key,batch_id,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (approval_id, approval.task_id, int(approval.selection_version), encoded,
                     approval.status or "confirmed", approval.idempotency_key, approval.batch_id, now, updated),
                )
                row = conn.execute(
                    "SELECT * FROM research_acquisition_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AcquisitionApproval.from_row(dict(row))

    def get_acquisition_approval(
        self, research_task_id: str, selection_version: int | None = None, *, idempotency_key: str | None = None
    ) -> AcquisitionApproval | None:
        if selection_version is None and idempotency_key is None:
            sql, params = (
                "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? ORDER BY selection_version DESC LIMIT 1",
                (research_task_id,),
            )
        elif idempotency_key is not None:
            sql, params = (
                "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? AND idempotency_key=?",
                (research_task_id, idempotency_key),
            )
        else:
            sql, params = (
                "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? AND selection_version=?",
                (research_task_id, int(selection_version)),
            )
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return AcquisitionApproval.from_row(dict(row)) if row else None

    def list_acquisition_approvals(self, research_task_id: str) -> list[AcquisitionApproval]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? ORDER BY selection_version",
                (research_task_id,),
            ).fetchall()
        return [AcquisitionApproval.from_row(dict(row)) for row in rows]

    def update_acquisition_approval(self, research_task_id: str, selection_version: int, **fields) -> AcquisitionApproval:
        allowed = {"status", "batch_id", "batch_ids_json"}
        if set(fields) - allowed:
            raise ValueError("unknown acquisition approval fields")
        assignments = [f"{key}=?" for key in fields]
        values = list(fields.values())
        assignments.append("updated_at=?")
        values.append(_utcnow())
        values.extend((research_task_id, int(selection_version)))
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if assignments:
                    conn.execute(
                        "UPDATE research_acquisition_approvals SET " + ",".join(assignments) +
                        " WHERE research_task_id=? AND selection_version=?", values,
                    )
                row = conn.execute(
                    "SELECT * FROM research_acquisition_approvals WHERE research_task_id=? AND selection_version=?",
                    (research_task_id, int(selection_version)),
                ).fetchone()
                if row is None:
                    raise ValueError("acquisition approval not found")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AcquisitionApproval.from_row(dict(row))

    def upsert_document_link(self, link: ResearchDocumentLink) -> ResearchDocumentLink:
        if not link.task_id or not link.catalog_paper_id:
            raise ValueError("document link requires task and catalog paper")
        now = link.created_at or _utcnow()
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT INTO research_document_links(
                        research_task_id,catalog_paper_id,document_id,import_item_id,status,error_code,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(research_task_id,catalog_paper_id) DO UPDATE SET
                        document_id=excluded.document_id, import_item_id=excluded.import_item_id,
                        status=excluded.status, error_code=excluded.error_code, updated_at=excluded.updated_at""",
                    (link.task_id, link.catalog_paper_id, link.document_id, link.import_item_id,
                     link.status, link.error_code, now, link.updated_at or now),
                )
                row = conn.execute(
                    "SELECT * FROM research_document_links WHERE research_task_id=? AND catalog_paper_id=?",
                    (link.task_id, link.catalog_paper_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchDocumentLink.from_row(dict(row))

    def list_document_links(self, research_task_id: str) -> list[ResearchDocumentLink]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_document_links WHERE research_task_id=? ORDER BY catalog_paper_id",
                (research_task_id,),
            ).fetchall()
        return [ResearchDocumentLink.from_row(dict(row)) for row in rows]

    def append_acquisition_event(self, event: AcquisitionEvent) -> AcquisitionEvent:
        if not event.task_id or not event.paper_id or not event.phase or not event.status:
            raise ValueError("invalid acquisition event")
        event_id = event.event_id or uuid.uuid4().hex
        created_at = event.created_at or _utcnow()
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    """SELECT * FROM research_acquisition_events WHERE research_task_id=? AND paper_id=? AND phase=?
                       AND status=? AND import_item_id IS ? AND error_code IS ?""",
                    (event.task_id, event.paper_id, event.phase, event.status, event.import_item_id, event.error_code),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """INSERT INTO research_acquisition_events(
                            event_id,research_task_id,paper_id,phase,status,error_code,batch_id,import_item_id,created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (event_id, event.task_id, event.paper_id, event.phase, event.status, event.error_code,
                         event.batch_id, event.import_item_id, created_at),
                    )
                    existing = conn.execute(
                        "SELECT * FROM research_acquisition_events WHERE event_id=?", (event_id,)
                    ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AcquisitionEvent.from_row(dict(existing))

    def list_acquisition_events(self, research_task_id: str) -> list[AcquisitionEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_acquisition_events WHERE research_task_id=? ORDER BY created_at,event_id",
                (research_task_id,),
            ).fetchall()
        return [AcquisitionEvent.from_row(dict(row)) for row in rows]

    # ------------------------------------------------------------------ #
    # Task11 candidate-scoped acquisition issues / manual resolutions
    # ------------------------------------------------------------------ #

    def upsert_acquisition_issue(self, issue: AcquisitionIssue, *, task_id: str | None = None) -> AcquisitionIssue:
        """Create or merge the one issue row for a stable candidate id.

        Repeated batch status polls are idempotent for the issue identity while
        preserving distinct attempts and Research task associations.  No
        client-provided URL or credential enters this table.
        """
        candidate_id = str(issue.candidate_id or "").strip()
        reason_code = str(issue.reason_code or "ACQUISITION_FAILED").strip()
        if not candidate_id or not reason_code:
            raise ValueError("acquisition issue requires candidate_id and reason_code")
        supplied_tasks = [str(value).strip() for value in (issue.task_ids or []) if str(value).strip()]
        if task_id and str(task_id).strip():
            supplied_tasks.append(str(task_id).strip())
        supplied_attempts = [dict(value) for value in (issue.attempts or []) if isinstance(value, dict)]
        supplied_actions = [str(value).strip() for value in (issue.actions or []) if str(value).strip()]
        now = issue.updated_at or issue.created_at or _utcnow()
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT * FROM research_acquisition_issues WHERE candidate_id=?", (candidate_id,)
                ).fetchone()
                if existing is not None:
                    current = AcquisitionIssue.from_row(dict(existing))
                    issue_id = current.issue_id
                    task_ids = list(dict.fromkeys((current.task_ids or []) + supplied_tasks))
                    attempts = list(current.attempts or [])
                    for attempt in supplied_attempts:
                        if attempt not in attempts:
                            attempts.append(attempt)
                    # Actions describe the current recoverable state, while
                    # ``attempts`` retains the historical action paths. Do
                    # not union actions across states: a candidate that moved
                    # from ``waiting_login`` to ``failed`` must not keep
                    # exposing ``login``/``resume`` after the browser window
                    # is gone.
                    actions = supplied_actions or list(current.actions or [])
                    status = str(issue.status or current.status or "open")
                    resolution = issue.resolution if issue.resolution is not None else current.resolution
                    # A fresh failure after a prior resolution is a new
                    # actionable episode, but a completed import stays closed.
                    resolved_at = issue.resolved_at if status == "resolved" else None
                    conn.execute(
                        """UPDATE research_acquisition_issues SET task_ids_json=?, reason_code=?, status=?,
                           attempts_json=?, actions_json=?, resolution_json=?, import_item_id=?, batch_id=?,
                           updated_at=?, resolved_at=? WHERE issue_id=?""",
                        (json.dumps(task_ids, ensure_ascii=False), reason_code, status,
                         json.dumps(attempts[-100:], ensure_ascii=False), json.dumps(actions, ensure_ascii=False),
                         json.dumps(resolution, ensure_ascii=False) if resolution is not None else None,
                         issue.import_item_id or current.import_item_id, issue.batch_id or current.batch_id,
                         now, resolved_at, issue_id),
                    )
                else:
                    issue_id = issue.issue_id or f"acq-{hashlib.sha256(candidate_id.encode('utf-8')).hexdigest()[:32]}"
                    task_ids = list(dict.fromkeys(supplied_tasks))
                    resolution_json = json.dumps(issue.resolution, ensure_ascii=False) if issue.resolution is not None else None
                    conn.execute(
                        """INSERT INTO research_acquisition_issues(
                           issue_id,candidate_id,task_ids_json,reason_code,status,attempts_json,actions_json,
                           resolution_json,import_item_id,batch_id,created_at,updated_at,resolved_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (issue_id, candidate_id, json.dumps(task_ids, ensure_ascii=False), reason_code,
                         issue.status or "open", json.dumps(supplied_attempts[-100:], ensure_ascii=False),
                         json.dumps(supplied_actions, ensure_ascii=False), resolution_json,
                         issue.import_item_id, issue.batch_id, issue.created_at or now, now, issue.resolved_at),
                    )
                row = conn.execute("SELECT * FROM research_acquisition_issues WHERE issue_id=?", (issue_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AcquisitionIssue.from_row(dict(row))

    def record_acquisition_issue(
        self, *, candidate_id: str, task_id: str, reason_code: str, status: str = "open",
        actions: list[str] | None = None, attempt: dict | None = None,
        import_item_id: str | None = None, batch_id: str | None = None,
    ) -> AcquisitionIssue:
        return self.upsert_acquisition_issue(
            AcquisitionIssue(
                candidate_id=candidate_id, reason_code=reason_code, status=status,
                attempts=[attempt] if attempt else [], actions=actions or [],
                import_item_id=import_item_id, batch_id=batch_id,
            ), task_id=task_id,
        )

    def get_acquisition_issue(self, issue_id: str) -> AcquisitionIssue | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_acquisition_issues WHERE issue_id=?", (str(issue_id),)
            ).fetchone()
        return AcquisitionIssue.from_row(dict(row)) if row else None

    def get_acquisition_issue_for_candidate(self, candidate_id: str) -> AcquisitionIssue | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_acquisition_issues WHERE candidate_id=?", (str(candidate_id),)
            ).fetchone()
        return AcquisitionIssue.from_row(dict(row)) if row else None

    def list_acquisition_issues(
        self, *, task_id: str | None = None, status: str | None = None,
        reason_code: str | None = None, limit: int = 100,
    ) -> list[AcquisitionIssue]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_acquisition_issues ORDER BY updated_at DESC, issue_id LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        result: list[AcquisitionIssue] = []
        for row in rows:
            issue = AcquisitionIssue.from_row(dict(row))
            if task_id and str(task_id) not in (issue.task_ids or []):
                continue
            if status and issue.status != status:
                continue
            if reason_code and issue.reason_code != reason_code:
                continue
            result.append(issue)
        return result

    def resolve_acquisition_issue(self, issue_id: str, resolution: dict[str, object]) -> AcquisitionIssue:
        issue = self.get_acquisition_issue(issue_id)
        if issue is None:
            raise ValueError("acquisition issue not found")
        now = _utcnow()
        updated = AcquisitionIssue(
            **{**issue.__dict__, "status": "resolved", "resolution": dict(resolution),
               "updated_at": now, "resolved_at": now}
        )
        return self.upsert_acquisition_issue(updated)

    def add_manual_resolution(self, resolution: ManualResolution) -> ManualResolution:
        if not resolution.issue_id or resolution.method not in {"login", "resume", "upload", "retry", "import"}:
            raise ValueError("invalid manual resolution")
        now = resolution.created_at or _utcnow()
        resolution_id = resolution.resolution_id or uuid.uuid4().hex
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT INTO research_manual_resolutions(
                       resolution_id,issue_id,method,user_document_id,identity_verdict,confirmed_at,evidence_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (resolution_id, resolution.issue_id, resolution.method, resolution.user_document_id,
                     resolution.identity_verdict, resolution.confirmed_at or now,
                     json.dumps(resolution.evidence or {}, ensure_ascii=False), now),
                )
                row = conn.execute(
                    "SELECT * FROM research_manual_resolutions WHERE resolution_id=?", (resolution_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ManualResolution.from_row(dict(row))

    def list_manual_resolutions(self, issue_id: str) -> list[ManualResolution]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_manual_resolutions WHERE issue_id=? ORDER BY created_at,resolution_id",
                (str(issue_id),),
            ).fetchall()
        return [ManualResolution.from_row(dict(row)) for row in rows]

    def save_evidence_upgrade(self, upgrade: EvidenceUpgrade) -> EvidenceUpgrade:
        if not upgrade.claim_id or not upgrade.from_level or not upgrade.to_level:
            raise ValueError("invalid evidence upgrade")
        now = upgrade.created_at or _utcnow()
        with _write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT INTO research_evidence_upgrades(
                        claim_id,research_task_id,document_id,from_level,to_level,chunk_ids_json,page,page_end,status,created_at,
                        source_sha256,manifest_generation,manifest_fingerprint,chunker
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(claim_id) DO UPDATE SET research_task_id=excluded.research_task_id,
                        document_id=excluded.document_id,from_level=excluded.from_level,to_level=excluded.to_level,
                        chunk_ids_json=excluded.chunk_ids_json,page=excluded.page,page_end=excluded.page_end,
                        status=excluded.status,created_at=excluded.created_at,
                        source_sha256=excluded.source_sha256,manifest_generation=excluded.manifest_generation,
                        manifest_fingerprint=excluded.manifest_fingerprint,chunker=excluded.chunker""",
                    (upgrade.claim_id, upgrade.task_id, upgrade.document_id, upgrade.from_level, upgrade.to_level,
                     json.dumps(upgrade.chunk_ids, ensure_ascii=False), upgrade.page, upgrade.page_end, upgrade.status, now,
                     upgrade.source_sha256, upgrade.manifest_generation, upgrade.manifest_fingerprint, upgrade.chunker),
                )
                row = conn.execute("SELECT * FROM research_evidence_upgrades WHERE claim_id=?", (upgrade.claim_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return EvidenceUpgrade.from_row(dict(row))

    def get_evidence_upgrade(self, claim_id: str) -> EvidenceUpgrade | None:
        """Read one evidence projection without reading report text."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_evidence_upgrades WHERE claim_id=?", (claim_id,)
            ).fetchone()
        return EvidenceUpgrade.from_row(dict(row)) if row is not None else None

    def list_evidence_upgrades(self, research_task_id: str) -> list[EvidenceUpgrade]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_evidence_upgrades WHERE research_task_id=? ORDER BY claim_id",
                (research_task_id,),
            ).fetchall()
        return [EvidenceUpgrade.from_row(dict(row)) for row in rows]

    # ------------------------------------------------------------------ #
    # Spec030 evidence matrix
    # ------------------------------------------------------------------ #

    def save_claim(self, claim: ResearchClaim) -> ResearchClaim:
        """Insert an immutable claim projection; identical retries are idempotent."""
        if not claim.claim_id or not claim.task_id or not claim.topic.strip() or not claim.statement.strip():
            raise ValueError("invalid research claim")
        encoded = json.dumps(list(claim.evidence_ids or []), ensure_ascii=False, separators=(",", ":"))
        now = claim.created_at or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute("SELECT * FROM research_claims WHERE claim_id=?", (claim.claim_id,)).fetchone()
                if existing is not None:
                    current = ResearchClaim.from_row(dict(existing))
                    if current.to_dict() | {"created_at": claim.created_at or current.created_at} != claim.to_dict() | {"created_at": current.created_at}:
                        raise ValueError("claim_id already exists with different content")
                    conn.commit()
                    return current
                conn.execute("""INSERT INTO research_claims(
                    claim_id,research_task_id,plan_version,topic,statement,confidence,status,evidence_ids_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""", (
                    claim.claim_id, claim.task_id, int(claim.plan_version), claim.topic, claim.statement,
                    claim.confidence, claim.status, encoded, now,
                ))
                row = conn.execute("SELECT * FROM research_claims WHERE claim_id=?", (claim.claim_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ResearchClaim.from_row(dict(row))

    def get_claim(self, claim_id: str) -> ResearchClaim | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM research_claims WHERE claim_id=?", (claim_id,)).fetchone()
        return ResearchClaim.from_row(dict(row)) if row else None

    def list_claims(self, research_task_id: str, *, plan_version: int | None = None) -> list[ResearchClaim]:
        sql = "SELECT * FROM research_claims WHERE research_task_id=?"
        params: list[object] = [research_task_id]
        if plan_version is not None:
            sql += " AND plan_version=?"
            params.append(int(plan_version))
        sql += " ORDER BY claim_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ResearchClaim.from_row(dict(row)) for row in rows]

    def save_claim_evidence(self, evidence: ClaimEvidence) -> ClaimEvidence:
        if not evidence.evidence_id or not evidence.claim_id or not evidence.task_id or not evidence.paper_id:
            raise ValueError("invalid claim evidence")
        now = evidence.created_at or _utcnow()
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute("SELECT * FROM research_claim_evidence WHERE evidence_id=?", (evidence.evidence_id,)).fetchone()
                if existing is None:
                    conn.execute("""INSERT INTO research_claim_evidence(
                        evidence_id,claim_id,research_task_id,plan_version,paper_id,evidence_level,stance,status,
                        quote_digest,locator_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                        evidence.evidence_id, evidence.claim_id, evidence.task_id, int(evidence.plan_version), evidence.paper_id,
                        evidence.evidence_level, evidence.stance, evidence.status, evidence.quote_digest,
                        json.dumps(evidence.locator or {}, ensure_ascii=False, separators=(",", ":")), now,
                    ))
                else:
                    current = ClaimEvidence.from_row(dict(existing))
                    immutable = (current.claim_id, current.task_id, current.plan_version, current.paper_id, current.evidence_level, current.stance)
                    requested = (evidence.claim_id, evidence.task_id, int(evidence.plan_version), evidence.paper_id, evidence.evidence_level, evidence.stance)
                    if immutable != requested:
                        raise ValueError("evidence_id already exists with different identity")
                    conn.execute("""UPDATE research_claim_evidence SET status=?, quote_digest=?, locator_json=? WHERE evidence_id=?""", (
                        evidence.status, evidence.quote_digest,
                        json.dumps(evidence.locator or {}, ensure_ascii=False, separators=(",", ":")), evidence.evidence_id,
                    ))
                row = conn.execute("SELECT * FROM research_claim_evidence WHERE evidence_id=?", (evidence.evidence_id,)).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return ClaimEvidence.from_row(dict(row))

    def get_claim_evidence(self, evidence_id: str) -> ClaimEvidence | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM research_claim_evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
        return ClaimEvidence.from_row(dict(row)) if row else None

    def list_claim_evidence(self, research_task_id: str, *, plan_version: int | None = None) -> list[ClaimEvidence]:
        sql = "SELECT * FROM research_claim_evidence WHERE research_task_id=?"
        params: list[object] = [research_task_id]
        if plan_version is not None:
            sql += " AND plan_version=?"
            params.append(int(plan_version))
        sql += " ORDER BY evidence_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ClaimEvidence.from_row(dict(row)) for row in rows]

    def replace_comparison_dimensions(self, research_task_id: str, plan_version: int, dimensions: list[ComparisonDimension]) -> list[ComparisonDimension]:
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM research_comparison_dimensions WHERE research_task_id=? AND plan_version=?", (research_task_id, int(plan_version)))
                for item in dimensions:
                    conn.execute("""INSERT INTO research_comparison_dimensions(
                        dimension_id,research_task_id,plan_version,label,definition,display_order,created_at
                    ) VALUES(?,?,?,?,?,?,?)""", (
                        item.dimension_id, research_task_id, int(plan_version), item.label, item.definition,
                        int(item.display_order), item.created_at or _utcnow(),
                    ))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.list_comparison_dimensions(research_task_id, plan_version=plan_version)

    def list_comparison_dimensions(self, research_task_id: str, *, plan_version: int | None = None) -> list[ComparisonDimension]:
        sql = "SELECT * FROM research_comparison_dimensions WHERE research_task_id=?"
        params: list[object] = [research_task_id]
        if plan_version is not None:
            sql += " AND plan_version=?"
            params.append(int(plan_version))
        sql += " ORDER BY display_order, dimension_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ComparisonDimension.from_row(dict(row)) for row in rows]

    def replace_comparison_cells(self, research_task_id: str, plan_version: int, cells: list[PaperComparisonCell]) -> list[PaperComparisonCell]:
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM research_comparison_cells WHERE research_task_id=? AND plan_version=?", (research_task_id, int(plan_version)))
                for item in cells:
                    conn.execute("""INSERT INTO research_comparison_cells(
                        research_task_id,plan_version,claim_id,paper_id,dimension_id,relation,summary,evidence_ids_json,missing_reason,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""", (
                        research_task_id, int(plan_version), item.claim_id, item.paper_id, item.dimension_id, item.relation,
                        item.summary, json.dumps(list(item.evidence_ids or []), ensure_ascii=False, separators=(",", ":")),
                        item.missing_reason, item.created_at or _utcnow(),
                    ))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.list_comparison_cells(research_task_id, plan_version=plan_version)

    def list_comparison_cells(self, research_task_id: str, *, plan_version: int | None = None) -> list[PaperComparisonCell]:
        sql = "SELECT * FROM research_comparison_cells WHERE research_task_id=?"
        params: list[object] = [research_task_id]
        if plan_version is not None:
            sql += " AND plan_version=?"
            params.append(int(plan_version))
        sql += " ORDER BY claim_id, paper_id, dimension_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [PaperComparisonCell.from_row(dict(row)) for row in rows]

    # Explicit names used by application adapters and isolated contract tests.
    save_comparison_dimensions = replace_comparison_dimensions
    save_comparison_cells = replace_comparison_cells
    get_comparison_dimensions = list_comparison_dimensions
    get_comparison_cells = list_comparison_cells

    # ------------------------------------------------------------------ #
    # PreliminaryReport
    # ------------------------------------------------------------------ #

    def next_report_version(self, research_task_id: str, owner_id: str) -> int:
        """Return the next immutable Spec030 version for an owner-bound task."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT MAX(version) AS version FROM (
                       SELECT r.report_version AS version FROM research_reports r
                       JOIN research_tasks t ON t.research_task_id=r.research_task_id
                       WHERE r.research_task_id=? AND t.owner_id=?
                       UNION ALL
                       SELECT a.report_version AS version FROM research_artifacts a
                       JOIN research_tasks t ON t.research_task_id=a.research_task_id
                       WHERE a.research_task_id=? AND t.owner_id=?)""",
                (research_task_id, owner_id, research_task_id, owner_id),
            ).fetchone()
        return int(row["version"] or 0) + 1

    def save_research_report(self, report: ResearchReport, *, owner_id: str | None = None) -> ResearchReport:
        """Insert one immutable report version; never update an existing row."""
        if report.status not in {"draft", "generating", "completed", "partial", "failed"}:
            raise ValueError("invalid research report status")
        if int(report.plan_version) < 1 or int(report.report_version) < 1:
            raise ValueError("report versions must be positive")
        try:
            json.loads(report.report_json)
            json.loads(report.limitations_json or "[]")
        except (TypeError, ValueError) as exc:
            raise ValueError("research report JSON is invalid") from exc
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if owner_id is not None and not conn.execute(
                    "SELECT 1 FROM research_tasks WHERE research_task_id=? AND owner_id=?",
                    (report.research_task_id, owner_id),
                ).fetchone():
                    raise ResearchTaskNotFound(report.research_task_id)
                conn.execute(
                    """INSERT INTO research_reports(
                       report_id,research_task_id,plan_version,report_version,status,markdown,html,
                       report_json,limitations_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (report.report_id, report.research_task_id, int(report.plan_version),
                     int(report.report_version), report.status, report.markdown, report.html,
                     report.report_json, report.limitations_json, report.created_at or _utcnow()),
                )
                row = conn.execute("SELECT * FROM research_reports WHERE report_id=?", (report.report_id,)).fetchone()
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ResearchReportConflict() from exc
            except Exception:
                conn.rollback()
                raise
        return ResearchReport.from_row(dict(row))

    def get_research_report(
        self, research_task_id: str, owner_id: str, *, report_version: int | None = None
    ) -> ResearchReport | None:
        sql = """SELECT r.* FROM research_reports r
                 JOIN research_tasks t ON t.research_task_id=r.research_task_id
                 WHERE r.research_task_id=? AND t.owner_id=?"""
        params: list[object] = [research_task_id, owner_id]
        if report_version is not None:
            sql += " AND r.report_version=?"
            params.append(int(report_version))
        else:
            sql += " ORDER BY r.report_version DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return ResearchReport.from_row(dict(row)) if row else None

    def list_research_reports(self, research_task_id: str, owner_id: str) -> list[ResearchReport]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT r.* FROM research_reports r
                   JOIN research_tasks t ON t.research_task_id=r.research_task_id
                   WHERE r.research_task_id=? AND t.owner_id=? ORDER BY r.report_version""",
                (research_task_id, owner_id),
            ).fetchall()
        return [ResearchReport.from_row(dict(row)) for row in rows]

    # Explicit aliases used by application adapters and contract tests.
    create_research_report = save_research_report
    get_report_version = get_research_report

    def save_report(self, report: PreliminaryReport) -> PreliminaryReport:
        """写入/更新某计划版本的报告（同一计划版本唯一）：ON CONFLICT 覆盖 markdown/limitations/status。"""
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO preliminary_reports(
                        report_id, research_task_id, plan_version, status, markdown, limitations_json, created_at
                    ) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(research_task_id, plan_version) DO UPDATE SET
                        markdown=excluded.markdown,
                        limitations_json=excluded.limitations_json,
                        status=excluded.status""",
                    (
                        report.report_id,
                        report.research_task_id,
                        report.plan_version,
                        report.status,
                        report.markdown,
                        report.limitations_json,
                        report.created_at or _utcnow(),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM preliminary_reports WHERE research_task_id=? AND plan_version=?",
                    (report.research_task_id, report.plan_version),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return PreliminaryReport.from_row(dict(row))

    def get_report(
        self, research_task_id: str, plan_version: Optional[int] = None
    ) -> Optional[PreliminaryReport]:
        """读取报告；plan_version 为 None 时取最大版本（当前正式报告）；不存在返回 None。"""
        with self._connect() as conn:
            if plan_version is None:
                row = conn.execute(
                    "SELECT * FROM preliminary_reports WHERE research_task_id=? ORDER BY plan_version DESC LIMIT 1",
                    (research_task_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM preliminary_reports WHERE research_task_id=? AND plan_version=?",
                    (research_task_id, plan_version),
                ).fetchone()
        return PreliminaryReport.from_row(dict(row)) if row else None

    # ------------------------------------------------------------------ #
    # 崩溃收敛审计（Spec027 启动审计，区别于 Spec015 reset_running_jobs）
    # ------------------------------------------------------------------ #

    def mark_running_interrupted(self) -> int:
        """启动审计：把所有 running 的 task 收敛为 interrupted，并为每个追加一条 terminal 事件；
        同时把这些 task 下 running 的 work_item 置为 interrupted。

        **刻意区别于 Spec015 `reset_running_jobs`（catalog_search_graph.py:843）的 running→queued
        重试语义**：027 的 running 任务在崩溃后不再重试，直接收敛为 interrupted（终态），因自动续跑/
        租约属于 Spec028。本方法**只处理 running，不动 queued**（WorkItem 转移表不允许
        queued→interrupted），故 queued work_item 保持 queued。返回被收敛的 task 数量。
        """
        with _write_lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                now = _utcnow()
                running_tasks = conn.execute(
                    "SELECT research_task_id FROM research_tasks WHERE status='running'"
                ).fetchall()
                count = 0
                for task_row in running_tasks:
                    task_id = task_row["research_task_id"]
                    # 单语句同时置终态并原子领号（避免 read-modify-write 竞争）。
                    conn.execute(
                        "UPDATE research_tasks SET status='interrupted', updated_at=?, completed_at=?, "
                        "last_event_seq = last_event_seq + 1 WHERE research_task_id=?",
                        (now, now, task_id),
                    )
                    seq_row = conn.execute(
                        "SELECT last_event_seq FROM research_tasks WHERE research_task_id=?", (task_id,)
                    ).fetchone()
                    seq = int(seq_row["last_event_seq"])
                    conn.execute(
                        """INSERT INTO research_events(research_task_id, event_seq, event_type, safe_payload_json, created_at)
                           VALUES(?,?,?,?,?)""",
                        (
                            task_id,
                            seq,
                            "terminal",
                            json.dumps(
                                {"status": "interrupted", "reason": "startup_audit"},
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            now,
                        ),
                    )
                    # 仅 running 的 work_item 收敛；queued 保持不动（转移表不允许 queued→interrupted）。
                    conn.execute(
                        "UPDATE research_work_items SET status='interrupted', ended_at=? "
                        "WHERE research_task_id=? AND status='running'",
                        (now, task_id),
                    )
                    count += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return count


# Stable descriptive aliases for callers introduced by Spec034.  Keeping the
# original concise methods avoids a second repository implementation.
ResearchStore.create_research_session = ResearchStore.create_session
ResearchStore.get_research_session = ResearchStore.get_session
ResearchStore.list_research_sessions = ResearchStore.list_sessions
ResearchStore.update_research_session_status = ResearchStore.update_session_status
ResearchStore.create_approval_request = ResearchStore.create_approval
ResearchStore.get_approval_request = ResearchStore.get_approval
ResearchStore.create_research_artifact = ResearchStore.create_artifact
ResearchStore.create_research_notification = ResearchStore.create_notification
ResearchStore.get_research_artifact = ResearchStore.get_artifact
ResearchStore.list_research_artifacts = ResearchStore.list_artifacts_for_task
ResearchStore.mark_research_notification_read = ResearchStore.mark_notification_read
ResearchStore.list_research_notifications = ResearchStore.list_notifications
# Task09 descriptive aliases keep maintenance callers independent from the
# original verb ordering used by the store implementation.
ResearchStore.legacy_cleanup_dry_run = ResearchStore.dry_run_legacy_cleanup
ResearchStore.cleanup_legacy_tasks = ResearchStore.execute_legacy_cleanup

# Spec028 keeps both concise and descriptive names available so existing
# callers can migrate incrementally without introducing another repository.
ResearchStore.claim_lease = ResearchStore.claim_scheduler_lease
ResearchStore.acquire_scheduler_lease = ResearchStore.claim_scheduler_lease
ResearchStore.try_claim_lease = ResearchStore.claim_scheduler_lease
ResearchStore.get_lease = ResearchStore.get_scheduler_lease
ResearchStore.heartbeat_lease = ResearchStore.heartbeat_scheduler_lease
ResearchStore.renew_lease = ResearchStore.heartbeat_scheduler_lease
ResearchStore.release_lease = ResearchStore.release_scheduler_lease
ResearchStore.recover_expired_leases = ResearchStore.recover_expired_scheduler_leases
ResearchStore.recover_expired = ResearchStore.recover_expired_scheduler_leases
ResearchStore.save_checkpoint = ResearchStore.save_scheduler_checkpoint
ResearchStore.get_checkpoint = ResearchStore.get_scheduler_checkpoint
ResearchStore.advance_from_checkpoint = ResearchStore.advance_work_item_from_checkpoint
ResearchStore.reserve_resource = ResearchStore.reserve_resources
ResearchStore.reserve = ResearchStore.reserve_resources
ResearchStore.release_reservation = ResearchStore.release_resource_reservation
ResearchStore.release_resource = ResearchStore.release_resource_reservation
ResearchStore.list_reservations = ResearchStore.list_resource_reservations
ResearchStore.get_reservation = ResearchStore.get_resource_reservation
ResearchStore.recover_expired_reservations = ResearchStore.recover_expired_resource_reservations
