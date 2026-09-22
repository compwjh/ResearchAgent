"""Versioned cross-source result contracts for Spec032.

The individual source parsers intentionally keep their source-specific record
types.  This module is the narrow hand-off boundary used by a Worker/Tool: every
source can wrap its records in the same serializable envelope without sharing a
network client or making the worker understand HTML/PDF details.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Mapping

from backend.app.paper_discovery.domain.source_authority import canonical_source_id

SOURCE_CONTRACT_SCHEMA_VERSION = "source-contract-v1"
CONTRACT_SCHEMA_VERSION = SOURCE_CONTRACT_SCHEMA_VERSION

SOURCE_RESULT_STATUSES = frozenset({
    "queued", "checking_cache", "fetching", "merging", "completed", "cached",
    "partial", "failed", "unchanged",
})
IMPORT_RESULT_STATUSES = frozenset({"queued", "running", "completed", "waiting", "partial", "failed"})


def _json_value(value: Any) -> Any:
    """Convert nested contract values to deterministic JSON-safe primitives."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_value(item) for item in value)
    # Result payloads must be safe to hand directly to ``json.dumps``.  Source
    # adapters should normally provide mappings/dataclasses, but stringifying an
    # unexpected extension value is safer than leaking a non-serializable object
    # into a worker hand-off.
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass(frozen=True)
class ContractError:
    """Stable, retry-aware error information; no exception repr is persisted."""

    code: str
    retryable: bool = False
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "retryable": bool(self.retryable)}
        if self.message:
            payload["message"] = self.message
        return payload


def _error_value(value: Any) -> ContractError | None:
    if value is None:
        return None
    if isinstance(value, ContractError):
        return value
    if isinstance(value, Mapping):
        code = str(value.get("code") or value.get("error_code") or "SOURCE_FAILED").strip()
        return ContractError(code or "SOURCE_FAILED", bool(value.get("retryable")),
                             str(value.get("message") or "").strip() or None)
    return ContractError(str(value).strip() or "SOURCE_FAILED")


@dataclass(frozen=True)
class SourceResult:
    """Common discovery/fetch/parse result envelope for all seven sources."""

    source_id: str
    operation: str
    status: str
    scope: Mapping[str, Any] = field(default_factory=dict)
    coverage: Mapping[str, Any] = field(default_factory=dict)
    papers: tuple[Any, ...] = ()
    error: ContractError | Mapping[str, Any] | str | None = None
    artifact_handles: Mapping[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    schema_version: str = SOURCE_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        # Worker hand-offs are a closed seven-source boundary: unlike internal
        # provenance reads, an unknown source must not be serialized as a valid
        # result envelope.
        object.__setattr__(self, "source_id", canonical_source_id(self.source_id, strict=True))
        object.__setattr__(self, "error", _error_value(self.error))
        if not str(self.operation).strip():
            raise ValueError("operation must not be empty")
        if self.status not in SOURCE_RESULT_STATUSES:
            raise ValueError(f"unsupported source result status: {self.status!r}")
        if self.schema_version != SOURCE_CONTRACT_SCHEMA_VERSION:
            raise ValueError(f"unsupported source contract schema version: {self.schema_version!r}")
        if not isinstance(self.elapsed_ms, int) or isinstance(self.elapsed_ms, bool) or self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")

    @property
    def error_code(self) -> str | None:
        error = _error_value(self.error)
        return error.code if error else None

    def to_dict(self) -> dict[str, Any]:
        error = _error_value(self.error)
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "operation": self.operation,
            "status": self.status,
            "scope": _json_value(self.scope),
            "coverage": _json_value(self.coverage),
            "papers": [_json_value(item) for item in self.papers],
            "error": error.to_dict() if error else None,
            "artifact_handles": _json_value(self.artifact_handles),
            "elapsed_ms": int(self.elapsed_ms),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceResult":
        papers = payload.get("papers") or ()
        return cls(
            source_id=str(payload.get("source_id") or ""),
            operation=str(payload.get("operation") or ""),
            status=str(payload.get("status") or "failed"),
            scope=payload.get("scope") if isinstance(payload.get("scope"), Mapping) else {},
            coverage=payload.get("coverage") if isinstance(payload.get("coverage"), Mapping) else {},
            papers=tuple(papers) if isinstance(papers, (list, tuple)) else (),
            error=payload.get("error"),
            artifact_handles=(payload.get("artifact_handles")
                              if isinstance(payload.get("artifact_handles"), Mapping) else {}),
            elapsed_ms=max(0, int(payload.get("elapsed_ms") or 0)),
            schema_version=str(payload.get("schema_version") or SOURCE_CONTRACT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class ImportResult:
    """Common candidate import envelope shared by every source strategy."""

    candidate_id: str
    status: str
    document_id: str | None = None
    identity_verdict: str | None = None
    attempts: int = 0
    error: ContractError | Mapping[str, Any] | str | None = None
    artifact_handles: Mapping[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    schema_version: str = SOURCE_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "error", _error_value(self.error))
        if not str(self.candidate_id).strip():
            raise ValueError("candidate_id must not be empty")
        if self.status not in IMPORT_RESULT_STATUSES:
            raise ValueError(f"unsupported import result status: {self.status!r}")
        if self.schema_version != SOURCE_CONTRACT_SCHEMA_VERSION:
            raise ValueError(f"unsupported source contract schema version: {self.schema_version!r}")
        if self.status == "completed" and not str(self.document_id or "").strip():
            raise ValueError("completed import result requires document_id")
        if self.status == "completed" and self.error is not None:
            raise ValueError("completed import result cannot carry an error")
        if (not isinstance(self.attempts, int) or isinstance(self.attempts, bool)
                or not isinstance(self.elapsed_ms, int) or isinstance(self.elapsed_ms, bool)
                or self.attempts < 0 or self.elapsed_ms < 0):
            raise ValueError("attempts and elapsed_ms must be non-negative")

    @property
    def error_code(self) -> str | None:
        error = _error_value(self.error)
        return error.code if error else None

    def to_dict(self) -> dict[str, Any]:
        error = _error_value(self.error)
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "document_id": self.document_id,
            "identity_verdict": self.identity_verdict,
            "attempts": int(self.attempts),
            "error": error.to_dict() if error else None,
            "artifact_handles": _json_value(self.artifact_handles),
            "elapsed_ms": int(self.elapsed_ms),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImportResult":
        return cls(
            candidate_id=str(payload.get("candidate_id") or ""),
            status=str(payload.get("status") or "failed"),
            document_id=str(payload.get("document_id")) if payload.get("document_id") else None,
            identity_verdict=(str(payload.get("identity_verdict"))
                              if payload.get("identity_verdict") else None),
            attempts=max(0, int(payload.get("attempts") or 0)),
            error=payload.get("error"),
            artifact_handles=(payload.get("artifact_handles")
                              if isinstance(payload.get("artifact_handles"), Mapping) else {}),
            elapsed_ms=max(0, int(payload.get("elapsed_ms") or 0)),
            schema_version=str(payload.get("schema_version") or SOURCE_CONTRACT_SCHEMA_VERSION),
        )


class SourceContractMixin:
    """Thin adapter mixin for legacy publication sources.

    The publication adapters keep their typed parser result for existing callers;
    this mixin exposes the same versioned envelope used by ``SourceAdapter`` so a
    Worker can consume either adapter without a second parser implementation.
    """

    contract_schema_version = SOURCE_CONTRACT_SCHEMA_VERSION

    def result(
        self,
        operation: str,
        *,
        status: str = "completed",
        scope: Mapping[str, Any] | None = None,
        coverage: Mapping[str, Any] | None = None,
        papers: Any = (),
        error: Any = None,
        artifact_handles: Mapping[str, Any] | None = None,
        elapsed_ms: int = 0,
    ) -> SourceResult:
        return SourceResult(
            schema_version=self.contract_schema_version,
            source_id=self.source_id,
            operation=operation,
            status=status,
            scope=dict(scope or {}),
            coverage=dict(coverage or {}),
            papers=tuple(papers),
            error=error,
            artifact_handles=dict(artifact_handles or {}),
            elapsed_ms=elapsed_ms,
        )

    def parse_catalog_result(
        self,
        response: Any,
        *,
        scope: Mapping[str, Any] | None = None,
        coverage: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SourceResult:
        try:
            parsed = self.parse_catalog(response, **kwargs)
        except Exception as error:  # noqa: BLE001 - turn adapter failures into the contract envelope
            code = str(getattr(error, "code", "SOURCE_PARSE_FAILED"))
            return self.result(
                "parse_catalog",
                status="failed",
                scope=scope,
                coverage=coverage,
                error={
                    "code": code or "SOURCE_PARSE_FAILED",
                    "retryable": bool(getattr(error, "retryable", False)),
                },
            )
        records = getattr(parsed, "records", parsed or ())
        error_code = getattr(parsed, "error_code", None)
        status = "partial" if error_code and records else "failed" if error_code else "completed"
        result_coverage = dict(coverage or {})
        failed_years = getattr(parsed, "failed_years", ())
        if failed_years:
            result_coverage["failed_years"] = tuple(failed_years)
        return self.result(
            "parse_catalog",
            scope=scope,
            status=status,
            coverage=result_coverage,
            papers=records,
            error=error_code,
        )


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "ContractError",
    "IMPORT_RESULT_STATUSES",
    "ImportResult",
    "SOURCE_CONTRACT_SCHEMA_VERSION",
    "SOURCE_RESULT_STATUSES",
    "SourceContractMixin",
    "SourceResult",
]
