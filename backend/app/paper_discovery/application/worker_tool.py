"""受控的多来源 Worker Tool facade。

Worker 只看这个小型、可序列化的 envelope；真正的目录抓取、缓存、URL 安全和
PDF 导入仍由既有 ``SourceRegistry``、来源 Adapter 与 ``paper_import`` 执行。
这个模块不实现网络客户端，也不把任意 URL 变成信任来源。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, is_dataclass, replace
from typing import Any, Mapping
from urllib.parse import urlsplit

from backend.app.paper_discovery.domain.paper_discovery import SourceFetchUnit
from backend.app.paper_discovery.domain.source_authority import canonical_source_id
from backend.app.paper_discovery.domain.source_contract import (
    IMPORT_RESULT_STATUSES,
    SOURCE_RESULT_STATUSES,
    ContractError,
    ImportResult,
    SourceResult,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_TIMEOUT,
    LOGIN_REQUIRED,
    PaperDownloadError,
)
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry

_KNOWN_SOURCES = frozenset({"usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref"})

WORKER_TOOL_SCHEMA_VERSION = "worker-tool-v1"
PAPER_DISCOVERY_TOOL_NAME = "paper_discovery"


def _safe(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _safe(value.to_dict())
    if is_dataclass(value):
        return _safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_safe(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _error(code: str, *, retryable: bool = False, message: str | None = None) -> ContractError:
    return ContractError(code=code, retryable=retryable, message=message)


@dataclass(frozen=True)
class WorkerToolResult:
    """Machine-readable result shared by discovery and import Tool calls."""

    tool: str
    operation: str
    source_id: str
    status: str
    provenance: Mapping[str, Any]
    candidate_id: str | None = None
    payload: Mapping[str, Any] | None = None
    error: ContractError | Mapping[str, Any] | str | None = None
    elapsed_ms: int = 0
    schema_version: str = WORKER_TOOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", canonical_source_id(self.source_id, strict=True))
        if self.tool != PAPER_DISCOVERY_TOOL_NAME:
            raise ValueError(f"unsupported worker tool: {self.tool!r}")
        if self.operation not in {"discover", "import"}:
            raise ValueError(f"unsupported worker operation: {self.operation!r}")
        valid_statuses = SOURCE_RESULT_STATUSES if self.operation == "discover" else IMPORT_RESULT_STATUSES
        if self.status not in valid_statuses:
            raise ValueError(f"unsupported worker result status for {self.operation}: {self.status!r}")
        if self.schema_version != WORKER_TOOL_SCHEMA_VERSION:
            raise ValueError(f"unsupported worker tool schema version: {self.schema_version!r}")
        if not isinstance(self.elapsed_ms, int) or isinstance(self.elapsed_ms, bool) or self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")
        if self.candidate_id is not None and not str(self.candidate_id).strip():
            raise ValueError("candidate_id must be non-empty when present")
        if not isinstance(self.provenance, Mapping):
            raise ValueError("provenance must be an object")
        raw_error = self.error
        if raw_error is not None and not isinstance(raw_error, ContractError):
            if isinstance(raw_error, Mapping):
                raw_error = _error(
                    str(raw_error.get("code") or "TOOL_FAILED"),
                    retryable=bool(raw_error.get("retryable")),
                    message=str(raw_error.get("message") or "") or None,
                )
            else:
                raw_error = _error(str(raw_error) or "TOOL_FAILED")
            object.__setattr__(self, "error", raw_error)

    @property
    def error_code(self) -> str | None:
        return self.error.code if isinstance(self.error, ContractError) else None

    def to_dict(self) -> dict[str, Any]:
        error = self.error
        if isinstance(error, ContractError):
            error = error.to_dict()
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "operation": self.operation,
            "source_id": self.source_id,
            "status": self.status,
            "candidate_id": self.candidate_id,
            "provenance": _safe(self.provenance),
            "payload": _safe(self.payload or {}),
            "error": error,
            "elapsed_ms": int(self.elapsed_ms),
        }


def validate_worker_tool_result(payload: Mapping[str, Any], *, expected_source: str | None = None,
                                expected_operation: str | None = None) -> WorkerToolResult:
    """Validate a Tool result before a Worker consumes it.

    This is intentionally stricter than the display-oriented ``DispatchResult``:
    missing schema/source/provenance or malformed retry metadata is rejected.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("worker tool result must be an object")
    if payload.get("schema_version") != WORKER_TOOL_SCHEMA_VERSION:
        raise ValueError("unsupported worker tool schema version")
    error = payload.get("error")
    if error is not None and not isinstance(error, Mapping):
        raise ValueError("error must be an object or null")
    if isinstance(error, Mapping) and (
        not isinstance(error.get("code"), str) or not isinstance(error.get("retryable"), bool)
    ):
        raise ValueError("error requires string code and boolean retryable")
    source_id = str(payload.get("source_id") or "")
    if expected_source is not None and canonical_source_id(source_id, strict=True) != canonical_source_id(expected_source, strict=True):
        raise ValueError("worker result source does not match request")
    operation = str(payload.get("operation") or "")
    if expected_operation is not None and operation != expected_operation:
        raise ValueError("worker result operation does not match request")
    return WorkerToolResult(
        tool=str(payload.get("tool") or ""),
        operation=operation,
        source_id=source_id,
        status=str(payload.get("status") or ""),
        candidate_id=(str(payload["candidate_id"]) if payload.get("candidate_id") is not None else None),
        provenance=payload.get("provenance") if isinstance(payload.get("provenance"), Mapping) else {},
        payload=payload.get("payload") if isinstance(payload.get("payload"), Mapping) else {},
        error=error,
        elapsed_ms=payload.get("elapsed_ms") if isinstance(payload.get("elapsed_ms"), int) else -1,
        schema_version=str(payload.get("schema_version")),
    )


WORKER_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["discover", "import"]},
        "source_id": {
            "type": "string",
            "enum": ["usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref"],
        },
        "scope": {
            "type": "object",
            "description": "服务器受控 query/years/route；不接受 URL、Cookie 或凭据。",
        },
        "candidate": {
            "type": "object",
            "description": "由 discover 返回并由服务端冻结的候选快照。",
        },
    },
    "required": ["operation", "source_id"],
    "additionalProperties": False,
}


class PaperDiscoveryToolFacade:
    """将来源专用 Worker 输入接到既有 discovery/import 实现。"""

    _SCOPE_KEYS = frozenset({"query", "years", "limit", "publication_scope", "route", "conference_id"})
    _URL_KEYS = frozenset({"url", "urls", "pdf_url", "source_links", "cookie", "authorization", "token"})

    def __init__(self, *, registry: SourceRegistry | None = None, store: Any = None,
                 timeout: float = 20.0) -> None:
        if store is None and registry is None:
            # Resolve the application-owned store lazily at real Tool execution
            # time; importing the registry remains side-effect free.
            try:
                from backend.app.api.common import _paper_store
                store = _paper_store()
            except Exception:  # noqa: BLE001 - isolated doubles may omit app providers
                store = None
        self.store = store
        self.registry = registry or SourceRegistry(store=store, timeout=timeout)
        self.timeout = timeout

    @staticmethod
    def _candidate_id(record: Any, source_id: str, *, adapter: Any = None) -> str:
        for name in ("candidate_id", "catalog_paper_id", "paper_id", "stable_id"):
            value = record.get(name) if isinstance(record, Mapping) else getattr(record, name, None)
            if value:
                return str(value)
        if adapter is not None and callable(getattr(adapter, "normalize_identity", None)):
            try:
                identity = adapter.normalize_identity(record)
                if identity:
                    return f"{source_id}:{identity}"
            except Exception:  # noqa: BLE001 - fallback identity remains deterministic
                pass
        info = record if isinstance(record, Mapping) else {}
        title = str(info.get("title", "")).strip().casefold()
        year = str(info.get("year", ""))
        doi = str(info.get("doi", "")).strip().casefold()
        digest = hashlib.sha256(f"{source_id}|{doi}|{title}|{year}".encode()).hexdigest()[:24]
        return f"{source_id}:{digest}"

    @staticmethod
    def _record_provenance(record: Any, source_id: str) -> dict[str, Any]:
        raw = record.get("provenance") if isinstance(record, Mapping) else getattr(record, "provenance", None)
        if isinstance(raw, Mapping):
            return {str(key): canonical_source_id(value) for key, value in raw.items() if value}
        return {"record": source_id}

    def _validate_scope(self, scope: Any) -> tuple[dict[str, Any] | None, ContractError | None]:
        if scope is None:
            return {}, None
        if not isinstance(scope, Mapping):
            return None, _error("INVALID_SCOPE", message="scope must be an object")
        if any(key in self._URL_KEYS or "url" in str(key).casefold() for key in scope):
            return None, _error("UNAUTHORIZED_URL", message="scope cannot contain URL or credential fields")
        unknown = set(scope) - self._SCOPE_KEYS
        if unknown:
            return None, _error("INVALID_SCOPE", message="scope contains unsupported fields")
        result = dict(scope)
        if "query" in result and (not isinstance(result["query"], str) or not result["query"].strip()):
            return None, _error("INVALID_QUERY", message="query must be non-empty")
        if "years" in result:
            years = result["years"]
            if not isinstance(years, list) or not years or any(isinstance(y, bool) or not isinstance(y, int) for y in years):
                return None, _error("INVALID_YEARS", message="years must be a non-empty integer list")
            if any(year < 1900 or year > 2100 for year in years):
                return None, _error("INVALID_YEARS", message="years are outside the controlled range")
            result["years"] = sorted(set(years))
        if "limit" in result:
            limit = result["limit"]
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
                return None, _error("INVALID_LIMIT", message="limit must be an integer between 1 and 100")
            result["limit"] = int(limit)
        return result, None

    def _conference(self, source_id: str) -> Any:
        conferences = list(self.store.list_conferences()) if self.store is not None else []
        if source_id == "usenix":
            return next((item for item in conferences if item.conference_id == "usenix-security"), None)
        if source_id == "dblp":
            return next((item for item in conferences if item.enabled), None)
        return next((item for item in conferences if item.conference_id.replace("-", "_") == source_id), None)

    def _cached_records(self, source_id: str, scope: Mapping[str, Any]) -> tuple[list[Any], set[int]]:
        """Read complete catalog units and their source records after a restart.

        ``sync_units`` keeps adapter-local state, so calling it directly from a new
        Worker process loses the durable cache written by ``CatalogSourceRuntime``.
        The existing source-fetch/source-record tables are the source of truth here;
        pending catalog papers are intentionally readable because indexing is a
        separate concern.
        """
        connect = getattr(self.store, "_connect", None) if self.store is not None else None
        if not callable(connect):
            return [], set()
        years = {int(value) for value in scope.get("years", ()) if isinstance(value, int) and not isinstance(value, bool)}
        requested_route = str(scope.get("route") or scope.get("catalog") or "").strip().casefold()
        route_filter = ""
        params: list[Any] = [source_id, source_id]
        if years:
            route_filter += " AND p.year IN (" + ",".join("?" for _ in years) + ")"
            params.extend(sorted(years))
        if requested_route in {"official", "official_catalog", "venue"}:
            route_filter += " AND u.unit_key LIKE '%:official'"
        elif requested_route in {"crossref", "doi"}:
            route_filter += " AND u.unit_key NOT LIKE '%:official'"
        query = (
            "SELECT r.catalog_paper_id, r.fetch_unit_id, r.raw_metadata_json, "
            "u.year AS unit_year, u.unit_key, p.title, p.authors_json, p.abstract, "
            "p.keywords_json, p.doi, p.publication_stage, p.official_page_url, "
            "p.official_pdf_url, p.prepublication_pdf_url, p.year AS paper_year "
            "FROM catalog_source_records AS r "
            "JOIN source_fetch_units AS u ON u.fetch_unit_id = r.fetch_unit_id "
            "JOIN catalog_papers AS p ON p.catalog_paper_id = r.catalog_paper_id "
            "WHERE r.source_kind=? AND u.source_kind=? AND u.status='completed'" +
            route_filter +
            " ORDER BY CASE WHEN u.unit_key LIKE '%:official' THEN 0 ELSE 1 END, "
            "u.year DESC, r.catalog_paper_id"
        )
        records: list[Any] = []
        covered_years: set[int] = set()
        seen_ids: set[str] = set()
        try:
            with connect() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except Exception:  # noqa: BLE001 - cache reads must not break live fallback
            return [], set()
        for row in rows:
            candidate_id = str(row["catalog_paper_id"] or "")
            if not candidate_id or candidate_id in seen_ids:
                continue
            try:
                raw = json.loads(row["raw_metadata_json"] or "{}")
            except (TypeError, ValueError):
                raw = {}
            record = dict(raw) if isinstance(raw, Mapping) else {}
            record.setdefault("candidate_id", candidate_id)
            record.setdefault("source_id", source_id)
            record.setdefault("title", row["title"] or "")
            record.setdefault("authors", json.loads(row["authors_json"] or "[]"))
            record.setdefault("abstract", row["abstract"])
            record.setdefault("keywords", json.loads(row["keywords_json"] or "[]"))
            record.setdefault("doi", row["doi"])
            record.setdefault("year", row["paper_year"] if row["paper_year"] is not None else row["unit_year"])
            record.setdefault("publication_stage", row["publication_stage"] or "published")
            record.setdefault("article_url", row["official_page_url"])
            record.setdefault("pdf_url", row["official_pdf_url"])
            record.setdefault("prepublication_pdf_url", row["prepublication_pdf_url"])
            if not isinstance(record.get("provenance"), Mapping):
                record["provenance"] = {"record": source_id}
            records.append(record)
            seen_ids.add(candidate_id)
            year = row["unit_year"] if row["unit_year"] is not None else row["paper_year"]
            if year is not None:
                covered_years.add(int(year))
        return records, covered_years

    def _discover_records(self, source_id: str, scope: Mapping[str, Any], adapter: Any) -> tuple[list[Any], dict[str, Any], str | None]:
        years = scope.get("years") or []
        if source_id in {"usenix", "dblp"}:
            conference = self._conference(source_id)
            if conference is None:
                return [], {}, "SOURCE_NOT_CONFIGURED"
            query = str(scope.get("query") or "")
            if not query:
                return [], {}, "INVALID_QUERY"
            result = adapter.search(conference, query, years, limit=int(scope.get("limit") or 20))
            return list(getattr(result, "records", ()) or ()), {"years": years}, getattr(result, "error_code", None)
        if callable(getattr(adapter, "sync_units", None)):
            cached_records, cached_years = self._cached_records(source_id, scope)
            requested_years = [int(year) for year in years]
            missing_years = [year for year in requested_years if year not in cached_years]
            # A complete persistent unit is authoritative for Worker discovery;
            # only missing/failed/expired units go back through the adapter.
            if cached_records and (not requested_years or not missing_years):
                return cached_records[:int(scope.get("limit") or 20)], {
                    "years": requested_years,
                    "failed_years": [],
                    "cached_years": sorted(cached_years),
                    "cache_hit": True,
                }, None
            sync_scope = dict(scope)
            if requested_years and missing_years:
                sync_scope["years"] = missing_years
            result = adapter.sync_units(sync_scope)
            records = list(getattr(result, "records", ()) or ())
            records = cached_records + records
            records = records[:int(scope.get("limit") or 20)]
            failed = list(getattr(result, "failed_years", ()) or ())
            coverage = {"years": requested_years, "failed_years": failed,
                        "cached_years": sorted(cached_years), "cache_hit": bool(cached_records)}
            return records, coverage, getattr(result, "error_code", None)
        if callable(getattr(adapter, "discover_units", None)):
            units = list(adapter.discover_units(dict(scope)))
            records: list[Any] = []
            failures: list[str] = []
            for unit in units:
                try:
                    updated, response = adapter.fetch_unit(unit, unit.conditional_headers() if hasattr(unit, "conditional_headers") else None)
                    if response is not None:
                        records.extend(adapter.parse_catalog(response))
                    elif getattr(updated, "status", "") == "failed":
                        failures.append(str(getattr(unit, "unit_key", "unit")))
                except Exception:  # noqa: BLE001 - one source unit cannot poison the envelope
                    failures.append(str(getattr(unit, "unit_key", "unit")))
            records = records[:int(scope.get("limit") or 20)]
            return records, {"years": years, "failed_units": failures}, "SOURCE_FAILED" if failures and not records else None
        return [], {}, "SOURCE_UNSUPPORTED"

    def _persist_legacy_candidates(self, source_id: str, records: list[Any],
                                   scope: Mapping[str, Any]) -> list[Any]:
        """Persist query-scoped USENIX/DBLP hits and replace transient IDs.

        The legacy ``search`` adapters return source records, while import is
        intentionally keyed by server-owned catalog IDs. Reuse the catalog
        runtime's existing merge/provenance writer so discover and import share
        one durable identity instead of inventing an import-only lookup.
        """
        if source_id not in {"usenix", "dblp"} or not records:
            return records
        if self.store is None or not callable(getattr(self.store, "save_fetch_unit", None)):
            raise RuntimeError("catalog persistence unavailable")
        from backend.app.paper_discovery.application.catalog_runtime import CatalogSourceRuntime

        runtime = CatalogSourceRuntime(store=self.store, registry=self.registry, timeout=self.timeout)
        conference_id = "usenix-security"
        query = str(scope.get("query") or "")
        query_key = hashlib.sha256(query.casefold().encode("utf-8")).hexdigest()[:16]
        requested_years = [int(year) for year in scope.get("years", ())]
        year_records: dict[int, list[Any]] = {}
        for record in records:
            info = record.get("info", record) if isinstance(record, Mapping) else {}
            raw_year = info.get("year") if isinstance(info, Mapping) else getattr(record, "year", None)
            try:
                year = int(raw_year) if raw_year is not None else (requested_years[0] if len(requested_years) == 1 else None)
            except (TypeError, ValueError):
                year = requested_years[0] if len(requested_years) == 1 else None
            if year is None:
                continue
            year_records.setdefault(year, []).append(record)

        persisted_records: list[Any] = []
        for year, records_for_year in year_records.items():
            unit_key = f"worker-query:{year}:official" if source_id == "usenix" else f"worker-query:{year}"
            fetch_unit_id = f"{source_id}|worker-query|{year}|{query_key}"
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            unit = SourceFetchUnit(
                fetch_unit_id=fetch_unit_id,
                source_kind=source_id,
                conference_id=conference_id,
                year=year,
                unit_key=unit_key,
                status="pending",
                paper_count=0,
                created_at=now,
                updated_at=now,
            )
            self.store.save_fetch_unit(unit, now)
            persisted_ids: set[str] = set()
            try:
                for record in records_for_year:
                    catalog_paper_id = runtime._persist_record(source_id, unit, record)
                    if not catalog_paper_id:
                        continue
                    persisted_ids.add(catalog_paper_id)
                    item = _safe(record)
                    if isinstance(item, dict):
                        item["candidate_id"] = catalog_paper_id
                        item["catalog_paper_id"] = catalog_paper_id
                        item["source_id"] = source_id
                        persisted_records.append(item)
                    else:
                        persisted_records.append({"candidate_id": catalog_paper_id, "source_id": source_id, "record": item})
            except Exception:
                persisted_count = len(persisted_ids)
                terminal = replace(unit, status="partial" if persisted_count else "failed",
                                   paper_count=persisted_count, updated_at=now)
                self.store.save_fetch_unit(terminal, now)
                raise
            persisted_count = len(persisted_ids)
            terminal = replace(unit, status="completed", paper_count=persisted_count, updated_at=now)
            self.store.save_fetch_unit(terminal, now)
        return persisted_records

    def discover(self, source_id: str, scope: Mapping[str, Any] | None = None) -> WorkerToolResult:
        started = time.monotonic()
        try:
            canonical = canonical_source_id(source_id, strict=True)
            entry = self.registry.get(canonical)
            if entry is None:
                raise ValueError("unknown source id")
            if not entry.enabled:
                return self._failed("discover", canonical, _error("SOURCE_DISABLED"), started)
            safe_scope, scope_error = self._validate_scope(scope)
            if scope_error:
                return self._failed("discover", canonical, scope_error, started)
            adapter = self.registry.adapter(canonical, store=self.store, timeout=self.timeout)
            records, coverage, code = self._discover_records(canonical, safe_scope or {}, adapter)
            records = self._persist_legacy_candidates(canonical, records, safe_scope or {})
            candidates = []
            provenance: dict[str, Any] = {}
            for record in records:
                candidate_id = self._candidate_id(record, canonical, adapter=adapter)
                item = _safe(record)
                if isinstance(item, dict):
                    item.setdefault("candidate_id", candidate_id)
                    item.setdefault("source_id", canonical)
                candidates.append(item)
                provenance[candidate_id] = self._record_provenance(record, canonical)
            status = "failed" if code and not candidates else "partial" if code else "completed"
            error = _error(code, retryable=code in {"SOURCE_FAILED", "DBLP_UNAVAILABLE"}) if code else None
            source_result = SourceResult(
                source_id=canonical, operation="discover", status=status,
                scope=safe_scope or {}, coverage={**coverage, "candidate_count": len(candidates)},
                papers=tuple(candidates), error=error, elapsed_ms=0,
            )
            payload = {"source_result": source_result.to_dict(), "candidates": candidates}
            return WorkerToolResult(
                tool=PAPER_DISCOVERY_TOOL_NAME, operation="discover", source_id=canonical,
                status=status, provenance=provenance, payload=payload,
                error=error, elapsed_ms=_elapsed(started),
            )
        except ValueError:
            canonical = str(source_id or "").strip().casefold()
            if canonical not in {"usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref"}:
                canonical = "usenix"
            return self._failed("discover", canonical, _error("SOURCE_NOT_ALLOWED"), started)
        except Exception:  # noqa: BLE001 - never expose exception repr to Worker
            canonical = str(source_id or "").strip().casefold() or "usenix"
            return self._failed("discover", canonical, _error("SOURCE_FAILED", retryable=True), started)

    def import_candidate(self, source_id: str, candidate: Mapping[str, Any]) -> WorkerToolResult:
        started = time.monotonic()
        canonical = str(source_id or "").strip().casefold()
        candidate_id: str | None = None
        try:
            canonical = canonical_source_id(source_id, strict=True)
            entry = self.registry.get(canonical)
            if entry is None:
                raise ValueError("unknown source id")
            if not entry.enabled:
                return self._failed("import", canonical, _error("SOURCE_DISABLED"), started)
            if not isinstance(candidate, Mapping):
                return self._failed("import", canonical, _error("INVALID_CANDIDATE"), started)
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            if not candidate_id:
                return self._failed("import", canonical, _error("INVALID_CANDIDATE"), started)
            supplied_source = candidate.get("source_id") or candidate.get("source_kind")
            if supplied_source and canonical_source_id(supplied_source, strict=True) != canonical:
                return self._failed("import", canonical, _error("SOURCE_MISMATCH"), started)
            # The Tool input carries only a stable ID. All metadata and URL
            # candidates must be recovered from the server-owned catalog.
            get_catalog_paper = getattr(self.store, "get_catalog_paper", None)
            get_catalog_source_kinds = getattr(self.store, "get_catalog_source_kinds", None)
            if not callable(get_catalog_paper) or not callable(get_catalog_source_kinds):
                return self._failed("import", canonical, _error("CATALOG_UNAVAILABLE"), started, candidate_id=candidate_id)
            paper = get_catalog_paper(candidate_id)
            if paper is None or str(getattr(paper, "catalog_paper_id", "")) != candidate_id:
                return self._failed("import", canonical, _error("CANDIDATE_NOT_FOUND"), started, candidate_id=candidate_id)
            source_kinds = {
                canonical_source_id(item, strict=True)
                for item in get_catalog_source_kinds(candidate_id)
            }
            if canonical not in source_kinds:
                return self._failed("import", canonical, _error("SOURCE_MISMATCH"), started, candidate_id=candidate_id)
            if not str(getattr(paper, "title", "") or "").strip():
                return self._failed("import", canonical, _error("INVALID_CANDIDATE"), started, candidate_id=candidate_id)
            # This snapshot is reconstructed exclusively from persisted catalog
            # fields; untrusted caller metadata and URLs never reach import.
            trusted_candidate = {
                "candidate_id": candidate_id,
                "catalog_paper_id": candidate_id,
                "source_id": canonical,
                "source_kind": canonical,
                "conference_id": getattr(paper, "conference_id", None),
                "title": paper.title,
                "authors": list(getattr(paper, "authors", ()) or ()),
                "year": getattr(paper, "year", None),
                "doi": getattr(paper, "doi", None),
                "abstract": getattr(paper, "abstract", None),
                "keywords": list(getattr(paper, "keywords", ()) or ()),
                "dblp_key": getattr(paper, "dblp_key", None),
                "publication_stage": getattr(paper, "publication_stage", "published"),
                "official_page_url": getattr(paper, "official_page_url", None),
                "article_url": getattr(paper, "official_page_url", None),
                "source_page_url": getattr(paper, "official_page_url", None),
                "pdf_url": getattr(paper, "official_pdf_url", None),
                "prepublication_pdf_url": getattr(paper, "prepublication_pdf_url", None),
                "arxiv_id": getattr(paper, "arxiv_id", None),
            }
            trusted_candidate["source_links"] = [
                {"kind": kind, "url": url}
                for kind, url in (
                    ("official_page", trusted_candidate["official_page_url"]),
                    ("official_pdf", trusted_candidate["pdf_url"]),
                    ("prepublication_pdf", trusted_candidate["prepublication_pdf_url"]),
                )
                if url
            ]
            # Preserve the existing fixed server allowlist. Never derive allowed hosts from
            # candidate URLs and never accept a caller-provided URL as an allowlist entry.
            from backend.app.api.common import _paper_candidate_hosts
            from backend.app.paper_discovery.application.paper_import import import_candidate as import_existing
            from backend.app.platform.settings.settings_repository import load_article_settings

            target_url = trusted_candidate.get("pdf_url")
            urls: list[Any] = [target_url, trusted_candidate.get("article_url"), trusted_candidate.get("official_page_url"), trusted_candidate.get("prepublication_pdf_url")]
            links = trusted_candidate.get("source_links")
            if isinstance(links, list):
                urls.extend(
                    link.get("url") if isinstance(link, Mapping) else link
                    for link in links
                )
            allowed_hosts = {item.casefold() for item in _paper_candidate_hosts(trusted_candidate)}
            for raw_url in urls:
                if not raw_url:
                    continue
                host = urlsplit(str(raw_url)).hostname
                if not host or host.casefold() not in allowed_hosts:
                    return self._failed("import", canonical, _error("UNAUTHORIZED_URL"), started, candidate_id=candidate_id)
            result = import_existing(trusted_candidate, settings=load_article_settings(), allowed_hosts=allowed_hosts)
            document_id = getattr(result, "paper_id", None)
            result_code = getattr(result, "error_code", None)
            status = "completed" if document_id and not result_code else "failed"
            import_result = ImportResult(
                candidate_id=candidate_id, status=status, document_id=str(document_id) if document_id else None,
                identity_verdict="verified" if status == "completed" else None,
                attempts=1, error=_error(str(result_code), retryable=True) if result_code else None,
                elapsed_ms=0,
            )
            return WorkerToolResult(
                tool=PAPER_DISCOVERY_TOOL_NAME, operation="import", source_id=canonical,
                status=status, candidate_id=candidate_id,
                provenance={"candidate": canonical, "document": canonical if document_id else None},
                payload={"import_result": import_result.to_dict()}, error=import_result.error,
                elapsed_ms=_elapsed(started),
            )
        except PaperDownloadError as exc:
            # Keep the download boundary's stable, actionable code visible to
            # the Worker.  A generic IMPORT_FAILED here made a real blocked or
            # login-gated paper indistinguishable from an internal exception,
            # and discarded the candidate id needed for retry/manual recovery.
            code = str(getattr(exc, "code", "DOWNLOAD_FAILED") or "DOWNLOAD_FAILED")
            return self._failed(
                "import",
                canonical if canonical in _KNOWN_SOURCES else "usenix",
                _error(code, retryable=code in {DOWNLOAD_TIMEOUT, LOGIN_REQUIRED}),
                started,
                candidate_id=candidate_id,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "PaperImportError":
                return self._failed("import", canonical, _error(str(getattr(exc, "code", "IMPORT_FAILED")), retryable=bool(getattr(exc, "retryable", False))), started)
            if isinstance(exc, ValueError):
                return self._failed("import", canonical if canonical in _KNOWN_SOURCES else "usenix", _error("SOURCE_NOT_ALLOWED"), started)
            return self._failed("import", canonical if canonical in _KNOWN_SOURCES else "usenix", _error("IMPORT_FAILED", retryable=True), started)

    def dispatch(self, args: Mapping[str, Any]) -> WorkerToolResult:
        operation = args.get("operation") if isinstance(args, Mapping) else None
        source_id = args.get("source_id") if isinstance(args, Mapping) else None
        if operation == "discover":
            return self.discover(str(source_id or ""), args.get("scope"))
        if operation == "import":
            return self.import_candidate(str(source_id or ""), args.get("candidate"))
        source = str(source_id or "").strip().casefold()
        if source not in _KNOWN_SOURCES:
            source = "usenix"
        return self._failed("discover", source, _error("INVALID_OPERATION"), time.monotonic())

    @staticmethod
    def _failed(operation: str, source_id: str, error: ContractError, started: float,
                *, candidate_id: str | None = None) -> WorkerToolResult:
        return WorkerToolResult(
            tool=PAPER_DISCOVERY_TOOL_NAME, operation=operation,
            source_id=canonical_source_id(source_id, strict=True), status="failed",
            candidate_id=candidate_id, provenance={}, payload={}, error=error,
            elapsed_ms=_elapsed(started),
        )


def _elapsed(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


# Stable, descriptive aliases for callers that refer to this boundary as a
# Tool rather than a facade.  They do not create a second implementation.
PaperDiscoveryTool = PaperDiscoveryToolFacade
ToolResult = WorkerToolResult
PAPER_DISCOVERY_TOOL_SCHEMA = WORKER_TOOL_SCHEMA


__all__ = [
    "PAPER_DISCOVERY_TOOL_NAME", "PAPER_DISCOVERY_TOOL_SCHEMA", "WORKER_TOOL_SCHEMA",
    "WORKER_TOOL_SCHEMA_VERSION", "PaperDiscoveryTool", "PaperDiscoveryToolFacade",
    "ToolResult", "WorkerToolResult", "validate_worker_tool_result",
]
