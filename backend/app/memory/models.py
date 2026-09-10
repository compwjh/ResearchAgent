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
