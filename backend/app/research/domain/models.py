"""Research Task 领域实体（纯 Python，无 IO / 无网络 / 无 SQLite 依赖）。

所有 JSON 字段（*_json）在实体里保持**字符串**语义，to_dict() 原样返回字符串；
仅便捷属性在需要时才做 json.loads，解析失败返回空值、不抛异常。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Self


@dataclass
class ResearchTask:
    """研究任务聚合根：用户发起的一个可持久化深度研究任务。"""

    research_task_id: str
    owner_id: str
    conversation_id: str
    goal: str
    language: str
    quality_profile: str
    review_plan_first: bool
    target_paper_count: int
    soft_budget_seconds: int
    status: str
    current_plan_version: int
    created_at: str
    updated_at: str
    project_id: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "research_task_id": self.research_task_id,
            "owner_id": self.owner_id,
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "goal": self.goal,
            "language": self.language,
            "quality_profile": self.quality_profile,
            "review_plan_first": self.review_plan_first,
            "target_paper_count": self.target_paper_count,
            "soft_budget_seconds": self.soft_budget_seconds,
            "status": self.status,
            "current_plan_version": self.current_plan_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            research_task_id=row["research_task_id"],
            owner_id=row["owner_id"],
            project_id=row.get("project_id"),
            conversation_id=row["conversation_id"],
            goal=row["goal"],
            language=row["language"],
            quality_profile=row["quality_profile"],
            review_plan_first=bool(row["review_plan_first"]),
            target_paper_count=int(row["target_paper_count"]),
            soft_budget_seconds=int(row["soft_budget_seconds"]),
            status=row["status"],
            current_plan_version=int(row["current_plan_version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row.get("completed_at"),
        )


@dataclass
class ResearchPlan:
    """研究计划：某一版本的受校验 WorkItem 集合与摘要。"""

    research_task_id: str
    version: int
    rationale_summary: str
    facets_json: str
    status: str
    created_at: str
    planner_model: str | None = None

    def to_dict(self) -> dict:
        return {
            "research_task_id": self.research_task_id,
            "version": self.version,
            "planner_model": self.planner_model,
            "rationale_summary": self.rationale_summary,
            "facets_json": self.facets_json,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            research_task_id=row["research_task_id"],
            version=int(row["version"]),
            planner_model=row.get("planner_model"),
            rationale_summary=row["rationale_summary"],
            facets_json=row["facets_json"],
            status=row["status"],
            created_at=row["created_at"],
        )


@dataclass
class ResearchSessionPlan:
    """可在 ResearchTask 创建前存在的会话计划版本（Spec034 Task04）。"""

    research_session_id: str
    version: int
    schema_version: str
    output_hash: str
    objective: str
    scope_json: str
    work_items_json: str
    capabilities_json: str
    budget_json: str
    report_structure_json: str
    safety_summary_json: str
    status: str
    created_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        values["version"] = int(values["version"])
        return cls(**values)


@dataclass
class ResearchWorkItem:
    """研究计划中的一个 WorkItem：单一角色执行的原子任务。"""

    work_item_id: str
    research_task_id: str
    plan_version: int
    task_type: str
    role: str
    depends_on_json: str
    input_json: str
    status: str
    attempt: int
    created_at: str
    updated_at: str
    output_json: str | None = None
    model_tier: str | None = None
    resolved_model: str | None = None
    worker_slot: str | None = None
    error_code: str | None = None
    started_at: str | None = None
    ended_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "work_item_id": self.work_item_id,
            "research_task_id": self.research_task_id,
            "plan_version": self.plan_version,
            "task_type": self.task_type,
            "role": self.role,
            "depends_on_json": self.depends_on_json,
            "input_json": self.input_json,
            "output_json": self.output_json,
            "model_tier": self.model_tier,
            "resolved_model": self.resolved_model,
            "worker_slot": self.worker_slot,
            "status": self.status,
            "attempt": self.attempt,
            "error_code": self.error_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            work_item_id=row["work_item_id"],
            research_task_id=row["research_task_id"],
            plan_version=int(row["plan_version"]),
            task_type=row["task_type"],
            role=row["role"],
            depends_on_json=row["depends_on_json"],
            input_json=row["input_json"],
            status=row["status"],
            attempt=int(row["attempt"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            output_json=row.get("output_json"),
            model_tier=row.get("model_tier"),
            resolved_model=row.get("resolved_model"),
            worker_slot=row.get("worker_slot"),
            error_code=row.get("error_code"),
            started_at=row.get("started_at"),
            ended_at=row.get("ended_at"),
        )

    @property
    def depends_on(self) -> list[str]:
        """解析 depends_on_json；空串/None/非 list/解析失败均返回空 list，不抛异常。"""
        raw = self.depends_on_json
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return []
        return value if isinstance(value, list) else []

    @property
    def input_params(self) -> dict:
        """解析 input_json 为参数字典；空串/None/非 dict/解析失败均返回空 dict，不抛异常。"""
        raw = self.input_json
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class SchedulerLease:
    """Durable ownership lease for one schedulable task/work item.

    ``task_id`` is intentionally generic: the scheduler uses a WorkItem id
    today, while recovery callers may use a task id.  The database is the
    source of truth for ownership; this value is only a read model.
    """

    task_id: str
    owner_token: str | None
    expires_at: str | None
    heartbeat_at: str | None

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            task_id=row["task_id"],
            owner_token=row.get("owner_token"),
            expires_at=row.get("expires_at"),
            heartbeat_at=row.get("heartbeat_at"),
        )


@dataclass(frozen=True)
class SchedulerCheckpoint:
    """Durable scheduler hand-off written before a node is advanced."""

    task_id: str
    plan_version: int
    node_id: str
    state_json: str
    input_digest: str
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            task_id=row["task_id"],
            plan_version=int(row["plan_version"]),
            node_id=row["node_id"],
            state_json=row["state_json"],
            input_digest=row["input_digest"],
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )


@dataclass(frozen=True)
class ResourceReservation:
    """A bounded, expiring reservation held by the global scheduler."""

    worker_id: str
    model_tier: str
    estimated_bytes: int
    expires_at: str
    task_id: str | None = None
    reservation_id: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            worker_id=row["worker_id"],
            model_tier=row["model_tier"],
            estimated_bytes=int(row["estimated_bytes"]),
            expires_at=row["expires_at"],
            task_id=row.get("task_id"),
            reservation_id=row.get("reservation_id"),
            created_at=row.get("created_at", ""),
        )


@dataclass
class ResearchEvent:
    """研究任务事件：用于 SSE 持久化与断线恢复的安全事件流。"""

    research_task_id: str
    event_seq: int
    event_type: str
    safe_payload_json: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "research_task_id": self.research_task_id,
            "event_seq": self.event_seq,
            "event_type": self.event_type,
            "safe_payload_json": self.safe_payload_json,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            research_task_id=row["research_task_id"],
            event_seq=int(row["event_seq"]),
            event_type=row["event_type"],
            safe_payload_json=row["safe_payload_json"],
            created_at=row["created_at"],
        )

    @property
    def source_event_id(self) -> str:
        """Canonical ProcessingStep projection identity for this event."""
        return f"research-event:{self.research_task_id}:{self.event_seq}"


@dataclass
class ResearchPaperSelection:
    """论文入选评估：引用 Spec015 全局目录，不复制论文元数据。"""

    research_task_id: str
    catalog_paper_id: str
    relevance: float
    facets_json: str
    evidence_level: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "research_task_id": self.research_task_id,
            "catalog_paper_id": self.catalog_paper_id,
            "relevance": self.relevance,
            "facets_json": self.facets_json,
            "evidence_level": self.evidence_level,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            research_task_id=row["research_task_id"],
            catalog_paper_id=row["catalog_paper_id"],
            relevance=float(row["relevance"]),
            facets_json=row["facets_json"],
            evidence_level=row["evidence_level"],
            created_at=row["created_at"],
        )


@dataclass
class AcquisitionApproval:
    """Immutable user confirmation snapshot for one Research selection version.

    ``paper_ids`` are catalog identifiers only.  The batch/document stores
    remain the owners of candidate snapshots and canonical document ids.
    """

    task_id: str
    selection_version: int
    paper_ids: list[str]
    status: str
    idempotency_key: str | None = None
    batch_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def research_task_id(self) -> str:
        return self.task_id

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "research_task_id": self.task_id,
            "selection_version": int(self.selection_version),
            "paper_ids": list(self.paper_ids),
            "status": self.status,
            "batch_id": self.batch_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        raw = row.get("paper_ids_json") or "[]"
        try:
            paper_ids = json.loads(raw)
        except (TypeError, ValueError):
            paper_ids = []
        if not isinstance(paper_ids, list):
            paper_ids = []
        return cls(
            task_id=row.get("task_id", row.get("research_task_id")),
            selection_version=int(row["selection_version"]),
            paper_ids=[str(value) for value in paper_ids],
            status=row["status"],
            idempotency_key=row.get("idempotency_key"),
            batch_id=row.get("batch_id"),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )


@dataclass
class ResearchDocumentLink:
    """Reference from a catalog paper to an existing KB/import item."""

    task_id: str
    catalog_paper_id: str
    document_id: str | None = None
    import_item_id: str | None = None
    status: str = "queued"
    error_code: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def research_task_id(self) -> str:
        return self.task_id

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "research_task_id": self.task_id,
            "catalog_paper_id": self.catalog_paper_id,
            "document_id": self.document_id,
            "import_item_id": self.import_item_id,
            "status": self.status,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            task_id=row.get("task_id", row.get("research_task_id")),
            catalog_paper_id=row["catalog_paper_id"],
            document_id=row.get("document_id"),
            import_item_id=row.get("import_item_id"),
            status=row.get("status", "queued"),
            error_code=row.get("error_code"),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )


@dataclass
class EvidenceUpgrade:
    """Durable status projection for a claim's full-text evidence upgrade."""

    claim_id: str
    from_level: str
    to_level: str
    chunk_ids: list[str]
    status: str
    task_id: str | None = None
    document_id: str | None = None
    page: int | None = None
    page_end: int | None = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "from_level": self.from_level,
            "to_level": self.to_level,
            "chunk_ids": list(self.chunk_ids),
            "status": self.status,
            "task_id": self.task_id,
            "document_id": self.document_id,
            "page": self.page,
            "page_end": self.page_end,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        try:
            chunk_ids = json.loads(row.get("chunk_ids_json") or "[]")
        except (TypeError, ValueError):
            chunk_ids = []
        return cls(
            claim_id=row["claim_id"],
            from_level=row["from_level"],
            to_level=row["to_level"],
            chunk_ids=[str(value) for value in chunk_ids] if isinstance(chunk_ids, list) else [],
            status=row["status"],
            task_id=row.get("task_id"),
            document_id=row.get("document_id"),
            page=row.get("page"),
            page_end=row.get("page_end"),
            created_at=row.get("created_at", ""),
        )


@dataclass
class AcquisitionEvent:
    """A projection of an existing import item state, not a second state machine."""

    paper_id: str
    phase: str
    status: str
    error_code: str | None = None
    task_id: str = ""
    batch_id: str | None = None
    import_item_id: str | None = None
    created_at: str = ""
    event_id: str | None = None

    @property
    def research_task_id(self) -> str:
        return self.task_id

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "research_task_id": self.task_id,
            "paper_id": self.paper_id,
            "phase": self.phase,
            "status": self.status,
            "error_code": self.error_code,
            "batch_id": self.batch_id,
            "import_item_id": self.import_item_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            event_id=row.get("event_id"),
            task_id=row.get("task_id", row.get("research_task_id")),
            paper_id=row["paper_id"],
            phase=row["phase"],
            status=row["status"],
            error_code=row.get("error_code"),
            batch_id=row.get("batch_id"),
            import_item_id=row.get("import_item_id"),
            created_at=row.get("created_at", ""),
        )


@dataclass
class PreliminaryReport:
    """初步/正式研究报告：只读正文，结论必须带论文引用。"""

    report_id: str
    research_task_id: str
    plan_version: int
    status: str
    markdown: str
    limitations_json: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "research_task_id": self.research_task_id,
            "plan_version": self.plan_version,
            "status": self.status,
            "markdown": self.markdown,
            "limitations_json": self.limitations_json,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(
            report_id=row["report_id"],
            research_task_id=row["research_task_id"],
            plan_version=int(row["plan_version"]),
            status=row["status"],
            markdown=row["markdown"],
            limitations_json=row["limitations_json"],
            created_at=row["created_at"],
        )


@dataclass
class ResearchSession:
    research_session_id: str
    owner_id: str
    conversation_id: str
    trigger_message_id: str
    intake_draft_id: str
    status: str
    current_plan_version: int = 0
    plan_message_id: str | None = None
    activity_message_id: str | None = None
    final_message_id: str | None = None
    research_task_id: str | None = None
    unread_state_json: str = "{}"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        values["current_plan_version"] = int(values.get("current_plan_version", 0))
        return cls(**values)


@dataclass
class ResearchIntakeDraft:
    intake_draft_id: str
    research_session_id: str
    status: str = "collecting"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(**{key: row[key] for key in cls.__dataclass_fields__ if key in row})


@dataclass
class IntakeField:
    intake_draft_id: str
    field_name: str
    value_json: str
    source: str
    confidence: float
    confirmation_status: str
    updated_at: str
    updated_by_message_id: str | None = None

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        values["confidence"] = float(values["confidence"])
        return cls(**values)


@dataclass
class ApprovalRequest:
    approval_request_id: str
    owner_id: str
    research_session_id: str
    kind: str
    subject_id: str
    subject_version: int
    requested_scope_json: str
    status: str = "pending"
    approved_scope_json: str | None = None
    idempotency_key: str = ""
    decided_by_message_id: str | None = None
    created_at: str = ""
    decided_at: str | None = None

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        values["subject_version"] = int(values["subject_version"])
        return cls(**values)


@dataclass
class AgentRun:
    agent_run_id: str
    research_session_id: str
    attempt: int
    role: str
    skill_name: str
    skill_schema_version: str
    skill_content_hash: str
    resolved_model: str
    reasoning_effort: str
    allowed_tools_json: str
    provider: str = ""
    status: str = "queued"
    research_task_id: str | None = None
    work_item_id: str | None = None
    continued_from_agent_run_id: str | None = None
    model_loop_count: int = 0
    tool_call_count: int = 0
    input_hash: str = ""
    output_hash: str = ""
    checkpoint_ref: str | None = None
    checkpoint_hash: str | None = None
    error_code: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    owner_id: str | None = None
    generation: int = 0

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        for key in ("attempt", "model_loop_count", "tool_call_count"):
            values[key] = int(values.get(key, 0))
        return cls(**values)


@dataclass
class AgentCheckpoint:
    """Immutable, owner-scoped minimum handoff persisted for Runner resume."""

    checkpoint_ref: str
    owner_id: str
    research_session_id: str
    research_task_id: str | None
    work_item_id: str | None
    agent_run_id: str
    schema_version: str
    content: str
    content_hash: str
    created_at: str = ""
    continued_from_agent_run_id: str | None = None

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(**{key: row[key] for key in cls.__dataclass_fields__ if key in row})


@dataclass
class ResearchArtifact:
    artifact_id: str
    research_task_id: str
    report_version: int
    artifact_type: str
    content_hash: str
    generated_by_agent_run_id: str
    content: str | None = None
    storage_ref: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        values["report_version"] = int(values["report_version"])
        return cls(**values)


@dataclass
class ResearchNotification:
    notification_id: str
    owner_id: str
    notification_kind: str
    status: str
    subject_version: int
    event_seq: int
    payload_json: str
    idempotency_key: str
    research_session_id: str | None = None
    research_task_id: str | None = None
    read_at: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        values = {key: row[key] for key in cls.__dataclass_fields__ if key in row}
        values["subject_version"] = int(values["subject_version"])
        values["event_seq"] = int(values["event_seq"])
        return cls(**values)


# Explicit names used by the Task02 contract and the shorter names retained by
# the implementation are intentionally the same runtime types.
ResearchIntakeField = IntakeField
