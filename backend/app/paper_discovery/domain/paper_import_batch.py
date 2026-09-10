"""Domain objects and state constants for paper import batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

BATCH_QUEUED = "queued"
BATCH_RUNNING = "running"
BATCH_WAITING_LOGIN = "waiting_login"
BATCH_PARTIAL_SUCCESS = "partial_success"
BATCH_COMPLETED = "completed"
BATCH_FAILED = "failed"
BATCH_CANCELLED = "cancelled"
BATCH_STATES = frozenset(
    {BATCH_QUEUED, BATCH_RUNNING, BATCH_WAITING_LOGIN, BATCH_PARTIAL_SUCCESS, BATCH_COMPLETED, BATCH_FAILED, BATCH_CANCELLED}
)

ITEM_QUEUED = "queued"
ITEM_DOWNLOADING = "downloading"
ITEM_WAITING_LOGIN = "waiting_login"
ITEM_VALIDATING = "validating"
ITEM_INDEXING = "indexing"
ITEM_COMPLETED = "completed"
ITEM_FAILED = "failed"
ITEM_CANCELLED = "cancelled"
ITEM_STATES = frozenset(
    {ITEM_QUEUED, ITEM_DOWNLOADING, ITEM_WAITING_LOGIN, ITEM_VALIDATING, ITEM_INDEXING, ITEM_COMPLETED, ITEM_FAILED, ITEM_CANCELLED}
)

ITEM_TRANSITIONS = {
    ITEM_QUEUED: frozenset({ITEM_DOWNLOADING, ITEM_CANCELLED}),
    ITEM_DOWNLOADING: frozenset({ITEM_VALIDATING, ITEM_WAITING_LOGIN, ITEM_FAILED}),
    ITEM_WAITING_LOGIN: frozenset({ITEM_DOWNLOADING, ITEM_QUEUED, ITEM_CANCELLED}),
    ITEM_VALIDATING: frozenset({ITEM_INDEXING, ITEM_FAILED}),
    ITEM_INDEXING: frozenset({ITEM_COMPLETED, ITEM_FAILED}),
    ITEM_FAILED: frozenset({ITEM_QUEUED, ITEM_CANCELLED}),
    ITEM_COMPLETED: frozenset(),
    ITEM_CANCELLED: frozenset(),
}


@dataclass
class PaperImportBatch:
    batch_id: str
    search_id: str
    status: str = BATCH_QUEUED
    created_at: str = ""
    updated_at: str = ""
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    waiting_login_count: int = 0
    cancelled_count: int = 0
    idempotency_key: Optional[str] = None
    search_expires_at: Optional[str] = None

    @property
    def state(self) -> str:
        return self.status

    @state.setter
    def state(self, value: str) -> None:
        self.status = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "search_id": self.search_id,
            "status": self.status,
            "state": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_count": self.total_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "waiting_login_count": self.waiting_login_count,
            "cancelled_count": self.cancelled_count,
            "idempotency_key": self.idempotency_key,
            "search_expires_at": self.search_expires_at,
        }


@dataclass
class PaperImportItem:
    item_id: str
    batch_id: str
    candidate_id: str
    status: str = ITEM_QUEUED
    stored_name: Optional[str] = None
    paper_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: int = 0
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    doi: Optional[str] = None
    dblp_key: Optional[str] = None
    normalized_title: Optional[str] = None
    year: Optional[int] = None
    conference_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    lease_renewed_at: Optional[str] = None
    # Attempt/resource fields are durable internal state.  ``attempt_token``
    # is intentionally omitted from ``to_dict``; the HTTP boundary must never
    # expose the compensation capability.
    attempt_owner: Optional[str] = None
    attempt_token: Optional[str] = None
    resource_capability: Optional[dict[str, Any]] = None
    cleanup_status: Optional[str] = None
    snapshot_json: Optional[str] = None
    snapshot_hash: Optional[str] = None

    @property
    def state(self) -> str:
        return self.status

    @state.setter
    def state(self, value: str) -> None:
        self.status = value

    def to_dict(self) -> dict[str, Any]:
        public_fields = {
            "item_id", "batch_id", "candidate_id", "status", "stored_name", "paper_id",
            "error_code", "error_message", "attempt_count", "lease_expires_at",
            "created_at", "updated_at", "doi", "dblp_key", "normalized_title", "year",
            "conference_id", "idempotency_key", "lease_renewed_at", "cleanup_status",
        }
        result = {name: getattr(self, name) for name in public_fields}
        result["state"] = self.status
        return result
