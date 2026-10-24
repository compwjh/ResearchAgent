"""Durable projections for map-scoped evidence analysis and conversations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import iso_now

EVIDENCE_LEVELS = frozenset({"abstract", "full"})
ANALYSIS_STATUSES = frozenset({"pending", "running", "completed", "failed"})


@dataclass
class MapAnalysis:
    analysis_id: str
    map_id: str
    node_id: str
    version: int
    status: str
    evidence_level: str
    source_version: str
    model_id: str
    job_id: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    idempotency_key: str | None = None
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        value = {
            "analysis_id": self.analysis_id,
            "map_id": self.map_id,
            "node_id": self.node_id,
            "version": self.version,
            "status": self.status,
            "evidence_level": self.evidence_level,
            "source_version": self.source_version,
            "model_id": self.model_id,
            "job_id": self.job_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.status == "completed" and self.result is not None:
            value["result"] = self.result
        if self.status == "failed" and self.error is not None:
            value["error"] = self.error
        return value


@dataclass
class MapConversationBinding:
    binding_id: str
    owner_id: str
    map_id: str
    node_id: str
    conversation_id: str
    project_id_snapshot: str | None
    evidence_level: str
    source_version: str
    context: dict[str, Any]
    status: str = "reserved"
    idempotency_key: str | None = None
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "owner_id": self.owner_id,
            "map_id": self.map_id,
            "node_id": self.node_id,
            "conversation_id": self.conversation_id,
            "project_id_snapshot": self.project_id_snapshot,
            "evidence_level": self.evidence_level,
            "source_version": self.source_version,
            "context": self.context,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
