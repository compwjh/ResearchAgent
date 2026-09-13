from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Project:
    project_id: str
    owner_id: str
    name: str
    instructions: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    # Read-only list projection.  It is not persisted on the projects table
    # and defaults to the project's own update time for point reads/writes.
    last_activity_at: Optional[datetime] = None


@dataclass(frozen=True)
class Conversation:
    conversation_id: str
    owner_id: str
    project_id: Optional[str]
    title: str
    status: str
    memory_history_policy: str
    created_at: datetime
    updated_at: datetime
    memory_binding_at: Optional[datetime] = None
    memory_binding_message_id: Optional[str] = None
    reasoning_effort: str = "xhigh"


@dataclass(frozen=True)
class Message:
    message_id: str
    conversation_id: str
    owner_id: str
    parent_message_id: Optional[str]
    role: str
    content: str
    status: str
    model: Optional[str]
    mode: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    reasoning_content: Optional[str] = None
    reasoning_status: Optional[str] = None
    reasoning_started_at: Optional[datetime] = None
    reasoning_completed_at: Optional[datetime] = None
    first_reasoning_at: Optional[datetime] = None
    first_answer_token_at: Optional[datetime] = None
    reasoning_truncated: bool = False
    reasoning_chars: int = 0
    last_event_seq: int = 0


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    owner_id: str
    scope: str
    project_id: Optional[str]
    category: str
    statement: str
    source_kind: str
    status: str
    confidence: float
    supersedes_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]


@dataclass(frozen=True)
class SystemRule:
    """The single current, owner-scoped user rule (never a MemoryRecord)."""

    owner_id: str
    content: str
    enabled: bool
    updated_at: datetime


@dataclass(frozen=True)
class MemoryEvidence:
    memory_id: str
    conversation_id: Optional[str]
    message_id: Optional[str]
    evidence_type: str
    excerpt: Optional[str]


@dataclass(frozen=True)
class ProcessingStep:
    step_id: str
    message_id: str
    kind: str
    label: str
    status: str
    summary: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    parent_step_id: Optional[str] = None
    node_type: str = "operation"
    node_key: Optional[str] = None
    display_order: int = 0
    detail_json: Optional[str] = None
    source_event_id: Optional[str] = None
    research_session_id: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        """Stable REST/SSE projection; v1 callers may ignore the v2 fields."""
        return {
            "step_id": self.step_id,
            "message_id": self.message_id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "parent_step_id": self.parent_step_id,
            "node_type": self.node_type,
            "node_key": self.node_key,
            "display_order": self.display_order,
            "detail_json": self.detail_json,
            "source_event_id": self.source_event_id,
            "research_session_id": self.research_session_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class MemoryAnalysisJob:
    analysis_id: str
    user_message_id: str
    owner_id: str
    project_id_snapshot: Optional[str]
    status: str
    model: Optional[str]
    cursor: Optional[str]
    batch_no: int
    saved_count: int
    pending_count: int
    failed_count: int
    error_code: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    lease_token: Optional[str] = None
    lease_version: int = 0


@dataclass(frozen=True)
class MemoryAnalysisItem:
    item_id: str
    analysis_id: str
    statement: str
    suggested_scope: str
    confidence: float
    rationale_summary: Optional[str]
    decision_status: str
    memory_id: Optional[str]
    created_at: datetime
    decided_at: Optional[datetime]


@dataclass(frozen=True)
class RawEvent:
    event_id: str
    owner_id: str
    conversation_id: str
    message_id: Optional[str]
    event_kind: str
    payload: dict
    idempotency_key: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class ConversationSummary:
    summary_id: str
    owner_id: str
    conversation_id: str
    summary_text: str
    source_event_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvolutionCheckpoint:
    checkpoint_id: str
    owner_id: str
    conversation_id: str
    stage: str
    status: str
    cursor: Optional[str]
    batch_index: int
    total_batches: int
    state: dict
    attempts: int
    idempotency_key: Optional[str]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SkillImprovementProposal:
    """A review-only suggestion; applying it is owned by the external SDD flow."""

    proposal_id: str
    owner_id: str
    scope: str
    project_id: Optional[str]
    target_file: str
    problem_evidence: str
    diff_summary: str
    verification_plan: str
    risk_summary: str
    status: str
    protected_hash_before: dict
    protected_hash_after: dict
    source_memory_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    decided_at: Optional[datetime]
