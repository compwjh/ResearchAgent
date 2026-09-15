"""spec-038 P1 后半段 · 记忆库 schema 重置后的**新基线**。

背景
----
旧实现对 ``memory.sqlite3`` 维护了一条 v1→v7 的历史迁移链（含若干补丁与
``writable_schema`` 修复），累计约 800 行。spec-038 已确认：**无生产数据、
可删库重建**，且 L1 记忆真相源已迁移到 Markdown 文件（``markdown_store``）。
因此本模块用「新基线直接建表」取代整条历史迁移链：

- 不再存在 v1→v7 的增量迁移；旧库（``schema_version`` 低于新基线）一律
  fail-closed，要求重建（数据保全由 ``preserve_legacy_owner_data`` 负责）。
- 建表语句集中在此处，``MemoryRepository.initialize()`` 只负责调用。

表的取舍（spec-038 决策）
------------------------
**保留**（照搬原 schema，不顺手改动无关表）：``schema_version``、``projects``、
``conversations``、``messages``、``processing_steps``、``raw_events``、
``conversation_summaries``、``evolution_checkpoints``、``memory_analysis_jobs``、
``memory_analysis_items``、``skill_improvement_proposals``、``user_chat_preferences``、
``conversation_segments``、``conversation_compaction_jobs``、
``conversation_active_skill``。

**停用**（不再建表，语义已迁到 MD 笔记）：
- ``memories``            → 全局/项目记忆改由 ``MEMORY.md`` / ``projects/<id>.md`` 承载；
- ``memory_evidence``     → 证据随记忆条目一并落在 MD；
- ``system_rules``        → 全局用户画像改由 ``USER.md`` 承载。

**新增**（spec-038 P2 · L2 会话检索）：``session_search_index`` FTS5 虚表，
统一索引「历史消息 + MD 记忆笔记」，供 ``session_search`` 工具主动翻旧账。

``memory_analysis_items.memory_id`` 旧列为 ``REFERENCES memories(memory_id)``。
表被停用后该外键无法保留，故新基线中把它保留为**普通 TEXT 列**（语义不变：
指向被采纳的记忆），从而不破坏 ``create_analysis_memory`` 的历史契约。

设计要点
--------
1. **幂等**：所有语句 ``CREATE ... IF NOT EXISTS``，反复 ``initialize()`` 无副作用。
2. **单事务**：``initialize()`` 用 ``BEGIN IMMEDIATE`` 包住全部 DDL，失败整体回滚。
3. **fail-closed**：``schema_version`` 高于新基线 → 拒绝启动；低于新基线且**不是**
   本次新建（即老库残留）→ 同样拒绝，避免在半旧 schema 上写入。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

# 重置后的新基线版本号。刻意**大于**历史链的 7，以便区分「本次基线建库」与
# 「旧 v1→v7 库残留」：前者由 initialize() 写入本值，后者因缺少该值而被拒绝。
SCHEMA_VERSION = 8


# --------------------------------------------------------------------------- DDL
# 每条语句都是独立的 ``CREATE ... IF NOT EXISTS``；由 initialize() 逐条 execute
# （而不是 executescript），以便 DDL 与版本写入处于同一事务、失败可整体回滚。

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    # ---------- 版本表 ----------
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
    )""",
    # ---------- 项目 / 会话 / 消息 ----------
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
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        memory_binding_at TEXT, memory_binding_message_id TEXT,
        reasoning_effort TEXT NOT NULL DEFAULT 'xhigh'
            CHECK(reasoning_effort IN ('off', 'low', 'medium', 'high', 'xhigh'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated ON conversations(owner_id, updated_at DESC, conversation_id DESC)",
    """CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
        owner_id TEXT NOT NULL, parent_message_id TEXT, role TEXT NOT NULL,
        content TEXT NOT NULL, status TEXT NOT NULL, model TEXT, mode TEXT,
        created_at TEXT NOT NULL, completed_at TEXT,
        reasoning_content TEXT, reasoning_status TEXT,
        reasoning_started_at TEXT, reasoning_completed_at TEXT,
        first_reasoning_at TEXT, first_answer_token_at TEXT,
        reasoning_truncated INTEGER NOT NULL DEFAULT 0,
        reasoning_chars INTEGER NOT NULL DEFAULT 0,
        last_event_seq INTEGER NOT NULL DEFAULT 0,
        activity_idempotency_key TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at DESC, message_id DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_activity_key ON messages(owner_id, conversation_id, activity_idempotency_key) WHERE activity_idempotency_key IS NOT NULL",
    # ---------- 处理步骤 ----------
    """CREATE TABLE IF NOT EXISTS processing_steps (
        step_id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
        kind TEXT NOT NULL, logical_sequence INTEGER NOT NULL DEFAULT 0, label TEXT NOT NULL, status TEXT NOT NULL,
        summary TEXT, started_at TEXT NOT NULL, completed_at TEXT,
        parent_step_id TEXT REFERENCES processing_steps(step_id) ON DELETE RESTRICT,
        node_type TEXT NOT NULL DEFAULT 'operation', node_key TEXT,
        display_order INTEGER NOT NULL DEFAULT 0, detail_json TEXT,
        source_event_id TEXT, research_session_id TEXT,
        schema_version INTEGER NOT NULL DEFAULT 1
    )""",
    "CREATE INDEX IF NOT EXISTS idx_steps_message ON processing_steps(message_id, started_at)",
    # 稳定身份：同一 (message_id, kind, logical_sequence) 只允许一行，SSE 重连与
    # 终态清理都更新同一记录（替代旧的「新建一行」实现）。
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_steps_message_kind_sequence ON processing_steps(message_id, kind, logical_sequence)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_steps_message_node_key ON processing_steps(message_id, node_key) WHERE node_key IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_steps_source_event_id ON processing_steps(source_event_id) WHERE source_event_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_steps_parent ON processing_steps(parent_step_id, display_order, started_at)",
    """CREATE TABLE IF NOT EXISTS processing_step_projection_retries (
        source_event_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
        error_code TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL,
        pending INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )""",
    # ---------- 审计流水 ----------
    """CREATE TABLE IF NOT EXISTS raw_events (
        event_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
        message_id TEXT REFERENCES messages(message_id) ON DELETE SET NULL,
        event_kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        idempotency_key TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(owner_id, conversation_id, idempotency_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_raw_events_session ON raw_events(owner_id, conversation_id, created_at, event_id)",
    # ---------- 会话摘要（P3 起改由 LLM 摘要写入，表结构不变） ----------
    """CREATE TABLE IF NOT EXISTS conversation_summaries (
        summary_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
        summary_text TEXT NOT NULL,
        source_event_id TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(owner_id, conversation_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_summaries_scope ON conversation_summaries(owner_id, conversation_id, status, updated_at DESC)",
    # ---------- 演进检查点 ----------
    """CREATE TABLE IF NOT EXISTS evolution_checkpoints (
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
    )""",
    # ---------- 记忆分析（审计） ----------
    # 注意：``memory_id`` 保留为普通 TEXT 列。旧实现指向已停用的 ``memories`` 表；
    # 新基线中它是「被采纳记忆」的弱引用，不做外键约束（该表已不存在）。
    """CREATE TABLE IF NOT EXISTS memory_analysis_jobs (
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
    )""",
    "CREATE INDEX IF NOT EXISTS idx_analysis_jobs_work ON memory_analysis_jobs(owner_id, status, updated_at)",
    """CREATE TABLE IF NOT EXISTS memory_analysis_items (
        item_id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL REFERENCES memory_analysis_jobs(analysis_id) ON DELETE CASCADE,
        statement TEXT NOT NULL,
        suggested_scope TEXT NOT NULL,
        confidence REAL NOT NULL,
        rationale_summary TEXT,
        decision_status TEXT NOT NULL,
        memory_id TEXT,
        created_at TEXT NOT NULL,
        decided_at TEXT,
        UNIQUE(analysis_id, statement)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_analysis_items_page ON memory_analysis_items(analysis_id, created_at, item_id)",
    # ---------- 技能改进建议（只读建议，应用由外部 SDD 流程负责） ----------
    # ``source_memory_id`` 同样保留为普通 TEXT 列（原指向已停用的 ``memories``）。
    """CREATE TABLE IF NOT EXISTS skill_improvement_proposals (
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
        source_memory_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        decided_at TEXT,
        CHECK (scope IN ('global', 'project')),
        CHECK ((scope='project' AND project_id IS NOT NULL) OR (scope='global' AND project_id IS NULL)),
        CHECK (status IN ('proposed', 'accepted', 'rejected', 'applied'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_skill_proposals_scope ON skill_improvement_proposals(owner_id, scope, project_id, status, updated_at DESC, proposal_id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_skill_proposals_source ON skill_improvement_proposals(owner_id, source_memory_id)",
    # ---------- 用户偏好 ----------
    """CREATE TABLE IF NOT EXISTS user_chat_preferences (
        owner_id TEXT PRIMARY KEY,
        last_reasoning_effort TEXT NOT NULL DEFAULT 'xhigh',
        updated_at TEXT NOT NULL,
        CHECK(last_reasoning_effort IN ('off', 'low', 'medium', 'high', 'xhigh'))
    )""",
    # ---------- 会话压缩（spec-025） ----------
    """CREATE TABLE IF NOT EXISTS conversation_segments (
        segment_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        project_id TEXT, seq INTEGER NOT NULL, from_message_id TEXT NOT NULL, to_message_id TEXT NOT NULL,
        char_count INTEGER NOT NULL, est_tokens INTEGER NOT NULL,
        generator TEXT NOT NULL DEFAULT 'rule', content_hash TEXT NOT NULL,
        summary_text TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_segments_seq ON conversation_segments(conversation_id, seq)",
    """CREATE TABLE IF NOT EXISTS conversation_compaction_jobs (
        job_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        status TEXT NOT NULL, trigger TEXT NOT NULL,
        est_tokens_before INTEGER, est_tokens_after INTEGER, error TEXT,
        created_at TEXT NOT NULL, finished_at TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_compaction_job_active ON conversation_compaction_jobs(conversation_id) WHERE status IN ('queued','running')",
    # ---------- 粘性技能（spec-032.1） ----------
    """CREATE TABLE IF NOT EXISTS conversation_active_skill (
        conversation_id TEXT NOT NULL PRIMARY KEY
            REFERENCES conversations(conversation_id) ON DELETE CASCADE,
        owner_id TEXT NOT NULL,
        skill_name TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # ---------- L2 会话检索（spec-038 P2） ----------
    # FTS5 虚表：统一索引「历史消息」与「MD 记忆笔记」两类来源，让 Agent 一次检索
    # 既能翻旧对话，也能搜到 USER.md / MEMORY.md / projects/<id>.md 里的笔记。
    #
    # 分词方案：索引列 ``content`` 存的是 **``embed.tokenize`` 分词后空格连接** 的文本
    # （中文走 jieba），查询侧用同一函数把查询词切成 token 再以 ``AND`` 连接 —— 而不是
    # 用 ``tokenize='trigram'``。理由：trigram 对 2 字中文词（如「检索」「偏好」）
    # 无法建立有效 token，中文查询会静默搜不到；jieba 分词与知识库稀疏检索复用同一套
    # 中文处理，行为一致且可复现（本仓库已有唯一实现，禁止第二套分词）。
    #
    # 设计取舍：``content`` 是**原始文本**（未分词），``index_text`` 才是分词后的索引列，
    # 这样查询结果可以直接回显可读原文，不必做去分词还原。FTS5 只对 ``index_text`` 建索引。
    #
    # 同步方式：**显式写入函数**（``SessionSearchIndex.index_message`` /
    # ``index_memory_document`` / ``reindex_all``），不用 SQL 触发器。理由：
    # 1. MD 记忆笔记根本不在 SQLite 里，触发器无法覆盖（需要应用层读文件）；
    # 2. 索引需要 jieba 分词，SQLite 触发器里做不到（不引入自定义 UDF）；
    # 3. 显式函数可被单测直接驱动，行为可控、可回放（``reindex_all`` 全量重建）。
    """CREATE VIRTUAL TABLE IF NOT EXISTS session_search_index USING fts5(
        index_text,
        content UNINDEXED,
        source_kind UNINDEXED,
        ref_id UNINDEXED,
        conversation_id UNINDEXED,
        owner_id UNINDEXED,
        role UNINDEXED,
        created_at UNINDEXED,
        tokenize='unicode61'
    )""",
)


def create_baseline_schema(connection: sqlite3.Connection, owner_id: str) -> None:
    """在新库（或已重建的库）上创建全部基线表与索引。

    幂等：所有语句均带 ``IF NOT EXISTS``。调用方负责事务边界与版本号写入。

    ``owner_id`` 用于播种**默认用户偏好行**：旧 v6→v7 迁移会 ``INSERT OR IGNORE``
    一条默认 ``xhigh`` 偏好，新基线必须保留该行为——否则
    ``update_conversation_reasoning`` 查不到偏好行就会走 INSERT 分支，
    把「effort 与当前值相同」误判成偏好变更并刷新时间戳。
    """
    for statement in _SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT OR IGNORE INTO user_chat_preferences(owner_id, last_reasoning_effort, updated_at)"
        " VALUES (?, 'xhigh', ?)",
        (owner_id, datetime.now(timezone.utc).isoformat()),
    )


def current_schema_version(connection: sqlite3.Connection) -> int:
    """读取当前 ``schema_version`` 最高版本；表不存在或无记录时返回 0。"""
    try:
        row = connection.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
    except sqlite3.OperationalError:
        return 0
    if row is None:
        return 0
    value = row["version"] if isinstance(row, sqlite3.Row) else row[0]
    return int(value or 0)


def record_schema_version(connection: sqlite3.Connection, version: int, applied_at: str) -> None:
    """写入版本行（已存在同版本则忽略），保持 initialize() 可重复执行。"""
    connection.execute(
        "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)",
        (int(version), applied_at),
    )
