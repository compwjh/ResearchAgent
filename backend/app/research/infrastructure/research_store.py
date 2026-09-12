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
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.app.platform.config import BASE_DIR
from backend.app.research.domain.contracts import (
    EVENT_TYPES,
    EVIDENCE_LEVELS,
    PLAN_STATUSES,
    ROLE_WHITELIST,
    TASK_TERMINAL,
    TASK_TYPE_WHITELIST,
    WORKITEM_TERMINAL,
)
from backend.app.research.domain.models import (
    PreliminaryReport,
    ResearchEvent,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.domain.state_machine import (
    transition_task,
    transition_workitem,
)

SCHEMA_VERSION = 1

# 写操作全局串行锁：保证 event_seq 原子领号在进程内也无竞争；锁内只做必要写，
# 计算（JSON 序列化等）已尽量外移。RLock 允许同一线程重入。
_write_lock = threading.RLock()


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
    ``PRAGMA foreign_keys = ON``（**不**设置 journal_mode，与 paper_discovery_store 一致）。
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
            # v1 无更高版本迁移；保留结构与 paper_discovery 一致（current 低于 SCHEMA_VERSION 才迁移）。
            if (current or SCHEMA_VERSION) < SCHEMA_VERSION:
                self._migrate_to_current(connection)
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
    def _migrate_to_current(connection: sqlite3.Connection) -> None:
        """当前 SCHEMA_VERSION == 1，无更高版本迁移；保留占位以维持迁移范式稳定。"""

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
        """新建连接：超时 30s、Row 工厂、外键开启。不设置 journal_mode（与既有 store 一致）。"""
        connection = sqlite3.connect(str(self.database_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
                        status, current_plan_version, last_event_seq, created_at, updated_at, completed_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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

    def update_task_status(self, research_task_id: str, owner_id: str, next_status: str) -> ResearchTask:
        """按 owner 读当前状态→状态机校验→更新 status/updated_at；终态写 completed_at。

        转移非法时 ``transition_task`` 抛 ``InvalidStateTransition``，**原样向上抛，不吞**。
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
                            created_at, updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
    # ResearchEvent（event_seq 原子领号）
    # ------------------------------------------------------------------ #

    def append_event(self, research_task_id: str, event_type: str, payload: dict) -> ResearchEvent:
        """原子追加事件：同事务内先 UPDATE 领号再 INSERT，保证并发不冲突/不重用/无洞。

        event_type 必须在 EVENT_TYPES 内，否则 ValueError；payload 用 json.dumps(ensure_ascii=False,
        sort_keys=True) 存 safe_payload_json。任务不存在（UPDATE 影响 0 行）抛 ResearchTaskNotFound。
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event_type}")
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

    def list_events(
        self, research_task_id: str, *, after_seq: int = 0, limit: int = 200
    ) -> list[ResearchEvent]:
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
                for s in selections:
                    conn.execute(
                        """INSERT INTO research_paper_selections(
                            research_task_id, catalog_paper_id, relevance, facets_json, evidence_level, created_at
                        ) VALUES(?,?,?,?,?,?)""",
                        (
                            research_task_id,
                            s.catalog_paper_id,
                            s.relevance,
                            s.facets_json,
                            s.evidence_level,
                            s.created_at or now,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.list_selections(research_task_id)

    def list_selections(self, research_task_id: str) -> list[ResearchPaperSelection]:
        """列出某任务论文选集（按 relevance 降序）；只引用 Spec015 目录 catalog_paper_id，不复制元数据。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_paper_selections WHERE research_task_id=? ORDER BY relevance DESC",
                (research_task_id,),
            ).fetchall()
        return [ResearchPaperSelection.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------ #
    # PreliminaryReport
    # ------------------------------------------------------------------ #

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
