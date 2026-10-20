"""Small immutable domain projections shared by store and application."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .identity import canonical_external_ids, deterministic_identity_key

SCHEMA_VERSION = "literature-map-v1"
EDGE_BASES = frozenset({"title_abstract", "title_only"})
_SAFE_MODEL_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,127}$")
_CONTENT_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def validate_edge_metadata(*, basis: object, model_version: object, content_hash: object) -> None:
    """Validate the public evidence fields persisted on a map edge.

    Citation edges may leave all three values empty.  When present, the
    fields are deliberately narrow so an internal path, prompt or credential
    cannot become a portable graph artifact through a direct edge column.
    """

    if basis is not None and (not isinstance(basis, str) or basis not in EDGE_BASES):
        raise ValueError("INVALID_EDGE_BASIS")
    if model_version is not None and (
        not isinstance(model_version, str) or not _SAFE_MODEL_VERSION_RE.fullmatch(model_version)
    ):
        raise ValueError("INVALID_EDGE_MODEL_VERSION")
    if content_hash is not None and (
        not isinstance(content_hash, str) or not _CONTENT_HASH_RE.fullmatch(content_hash)
    ):
        raise ValueError("INVALID_EDGE_CONTENT_HASH")


def safe_edge_basis(value: object) -> str | None:
    return value if isinstance(value, str) and value in EDGE_BASES else None


def safe_edge_model_version(value: object) -> str | None:
    return value if isinstance(value, str) and _SAFE_MODEL_VERSION_RE.fullmatch(value) else None


def safe_edge_content_hash(value: object) -> str | None:
    return value if isinstance(value, str) and _CONTENT_HASH_RE.fullmatch(value) else None


@dataclass
class LiteratureMap:
    map_id: str
    owner_id: str
    name: str
    topic: str
    project_id: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    requested_count: int = 30
    revision: int = 0
    status: str = "generating"
    view_settings: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_id": self.map_id,
            "name": self.name,
            "topic": self.topic,
            "owner_id": self.owner_id,
            "project_id": self.project_id,
            "filters": self.filters,
            "requested_count": self.requested_count,
            "revision": self.revision,
            "status": self.status,
            "view_settings": self.view_settings,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MapPaper:
    node_id: str
    map_id: str
    external_ids: dict[str, str]
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    keywords: tuple[str, ...] = ()
    citation_count: int | None = None
    source_url: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    catalog_paper_id: str | None = None
    document_id: str | None = None
    download_status: str | None = None
    position: dict[str, float] | None = None
    group_id: str | None = None
    identity_key: str | None = None
    removed: bool = False

    @classmethod
    def new(cls, map_id: str, *, semantic_scholar_id: str | None = None, external_ids: Mapping[str, Any] | None = None, title: str, **kwargs: Any) -> "MapPaper":
        supplied_ids = dict(external_ids or {})
        if semantic_scholar_id is not None:
            supplied_ids["semantic_scholar"] = semantic_scholar_id
        ids = canonical_external_ids(supplied_ids)
        key = deterministic_identity_key(ids)
        if not key:
            raise ValueError("paper external identity required")
        return cls(node_id=uuid.uuid4().hex, map_id=map_id, external_ids=ids, title=str(title).strip(), identity_key=key, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "map_id": self.map_id,
            "external_ids": self.external_ids,
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "abstract": self.abstract,
            "keywords": list(self.keywords),
            "citation_count": self.citation_count,
            "source_url": self.source_url,
            "provenance": self.provenance,
            "catalog_paper_id": self.catalog_paper_id,
            "document_id": self.document_id,
            "download_status": self.download_status,
            "position": self.position,
            "group_id": self.group_id,
            "removed": self.removed,
        }


@dataclass
class MapGroup:
    """A user-owned presentation group inside one literature map."""

    group_id: str
    map_id: str
    name: str
    color: str
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, str]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "color": self.color,
        }


@dataclass
class MapEdge:
    edge_id: str
    map_id: str
    kind: str
    source_id: str
    target_id: str
    provenance: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    basis: str | None = None
    model_version: str | None = None
    content_hash: str | None = None

    @classmethod
    def new(cls, map_id: str, kind: str, source_id: str, target_id: str, **kwargs: Any) -> "MapEdge":
        if source_id == target_id:
            raise ValueError("self edge is not allowed")
        if kind not in {"citation", "similarity"}:
            raise ValueError("unsupported edge kind")
        if kind == "similarity" and target_id < source_id:
            source_id, target_id = target_id, source_id
        return cls(uuid.uuid4().hex, map_id, kind, source_id, target_id, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "map_id": self.map_id,
            "kind": self.kind,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "provenance": self.provenance,
            "score": self.score,
            "basis": self.basis,
            "model_version": self.model_version,
            "content_hash": self.content_hash,
        }


@dataclass
class MapJob:
    job_id: str
    map_id: str
    operation: str
    status: str = "queued"
    step: str = "discover"
    cursor: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    failed_units: list[dict[str, Any]] = field(default_factory=list)
    idempotency_key: str | None = None
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "map_id": self.map_id,
            "operation": self.operation,
            "status": self.status,
            "step": self.step,
            "cursor": self.cursor,
            "counts": self.counts,
            "failed_units": self.failed_units,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MapPreview:
    preview_id: str
    map_id: str
    job_id: str
    kind: str
    status: str = "queued"
    base_revision: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    diff: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    idempotency_key: str | None = None
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id,
            "map_id": self.map_id,
            "kind": self.kind,
            "status": self.status,
            "base_revision": self.base_revision,
            "candidates": self.candidates,
            "diff": self.diff,
            "warnings": self.warnings,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MapEvent:
    event_seq: int
    map_id: str
    job_id: str
    type: str
    status: str
    step: str
    counts: dict[str, int] = field(default_factory=dict)
    error_code: str | None = None
    created_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_seq": self.event_seq,
            "map_id": self.map_id,
            "job_id": self.job_id,
            "type": self.type,
            "status": self.status,
            "step": self.step,
            "counts": self.counts,
            "error_code": self.error_code,
            "created_at": self.created_at,
        }


def content_hash(title: str, abstract: str | None) -> str:
    return hashlib.sha256(json.dumps({"title": title, "abstract": abstract or ""}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
