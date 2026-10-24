"""Runtime bridge for the Spec032 source registry and existing catalog store.

This module deliberately uses ``PaperDiscoveryStore``'s existing search-job,
fetch-unit, source-record and provenance tables.  A source sync is represented
by one ``search_jobs`` row (``graph_version=catalog-source-sync-v1``), not by a
second job/cache schema.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Iterable, Mapping

from backend.app.paper_discovery.domain.paper_discovery import (
    CatalogPaper,
    CatalogSourceRecord,
    SearchEvent,
    SearchJob,
    SearchSourceProgress,
    SourceFetchUnit,
)
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.paper_discovery.domain.source_authority import canonical_source_id, route_source_id
from backend.app.paper_discovery.infrastructure.ndss_paper_parser import NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry

SOURCE_SYNC_GRAPH_VERSION = "catalog-source-sync-v1"
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paper-source-sync")
_INFLIGHT: set[str] = set()
_LOCK = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(_safe(v) for v in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _record_value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _record_info(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        info = record.get("info", record)
        return info if isinstance(info, Mapping) else {}
    return {}


def _conference_id(source_id: str, record: Any) -> str:
    info = _record_info(record)
    return str(info.get("conference_id") or {
        "usenix": "usenix-security", "dblp": "usenix-security", "ieee_sp": "sp",
        "ccs": "ccs", "ndss": "ndss",
    }.get(source_id, source_id))


def _unit_id(unit: Any, source_id: str, year: int | None, conference_id: str) -> str:
    value = str(getattr(unit, "fetch_unit_id", "") or "")
    return value or f"{source_id}|{conference_id}|{year or 'global'}"


def _as_store_unit(source_id: str, unit: Any) -> SourceFetchUnit:
    """Normalize legacy aggregate ``FetchUnit`` into the shared SQLite unit."""
    if isinstance(unit, SourceFetchUnit):
        return unit
    scope_key = str(getattr(unit, "scope_key", "global"))
    year = None
    tail = scope_key.rsplit(":", 1)[-1]
    if tail.isdigit():
        year = int(tail)
    conference_id = source_id
    return SourceFetchUnit(
        fetch_unit_id=f"{source_id}|{scope_key}", source_kind=source_id,
        conference_id=conference_id, year=year, unit_key=scope_key,
        source_url=getattr(unit, "source_url", None), status="completed" if getattr(unit, "status", "") in {"fetched", "unchanged"} else getattr(unit, "status", "pending"),
        etag=getattr(unit, "etag", None) or None, last_modified=getattr(unit, "last_modified", None) or None,
        content_hash=getattr(unit, "content_hash", None) or None, created_at=_now(), updated_at=_now(),
    )


def _unit_route(unit: Any) -> str:
    """Recover the adapter route without adding a second fetch-unit schema."""
    fetch_unit_id = str(getattr(unit, "fetch_unit_id", "") or "").casefold()
    unit_key = str(getattr(unit, "unit_key", "") or "").casefold()
    if fetch_unit_id.endswith("|official") or unit_key.endswith(":official"):
        return "official"
    return "crossref"


def _progress_unit(value: Any) -> dict[str, Any] | None:
    """Normalize a completed/cache item to the public progress shape."""
    if isinstance(value, Mapping):
        payload = dict(value)
        unit_id = payload.get("unit_id") or payload.get("fetch_unit_id")
    else:
        payload = {}
        unit_id = value
    if unit_id in (None, ""):
        return None
    payload["unit_id"] = str(unit_id)
    return payload


def _progress_lists(completed: Iterable[Any], cached: Iterable[Any]) -> tuple[list[dict], list[dict]]:
    """Return ``(cached, completed)`` while keeping failed units out of completion."""
    cached_payloads: list[dict] = []
    completed_payloads: list[dict] = []
    seen_completed: set[str] = set()
    seen_cached: set[str] = set()
    for value in completed:
        payload = _progress_unit(value)
        if payload is None:
            continue
        unit_id = payload["unit_id"]
        if str(payload.get("status", "")).casefold() == "failed":
            continue
        if unit_id not in seen_completed:
            completed_payloads.append(payload)
            seen_completed.add(unit_id)
    for value in cached:
        payload = _progress_unit(value)
        if payload is None or str(payload.get("status", "")).casefold() == "failed":
            continue
        unit_id = payload["unit_id"]
        if unit_id not in seen_completed:
            completed_payloads.append(payload)
            seen_completed.add(unit_id)
        if unit_id not in seen_cached:
            cached_payloads.append(payload)
            seen_cached.add(unit_id)
    return cached_payloads, completed_payloads


def _store_unit_progress(source_id: str, units: Iterable[Any], cached: Iterable[Any]) -> tuple[list[dict], list[dict]]:
    """Build progress lists from persisted units, resolving cache years to IDs."""
    cached_keys = {str(item.get("year")) if isinstance(item, Mapping) and item.get("year") is not None else str(item)
                   for item in cached}
    completed: list[dict] = []
    cached_payloads: list[dict] = []
    seen_completed: set[str] = set()
    seen_cached: set[str] = set()
    for raw_unit in units:
        unit = _as_store_unit(source_id, raw_unit)
        if unit.status not in {"completed", "partial"}:
            continue
        payload = _progress_unit({
            "unit_id": unit.fetch_unit_id, "year": unit.year,
            "paper_count": unit.paper_count, "status": unit.status,
        })
        if payload is None:
            continue
        unit_id = payload["unit_id"]
        if unit_id not in seen_completed:
            completed.append(payload)
            seen_completed.add(unit_id)
        if (unit_id in cached_keys or str(unit.year) in cached_keys or str(unit.unit_key) in cached_keys) and unit_id not in seen_cached:
            cached_payloads.append(payload)
            seen_cached.add(unit_id)
    return cached_payloads, completed


class CatalogSourceRuntime:
    """Execute one registered source and persist its real terminal state."""

    def __init__(self, *, store: Any, registry: SourceRegistry | None = None, timeout: float = 20.0):
        self.store = store
        self.registry = registry or SourceRegistry(store=store, timeout=timeout)
        self.timeout = timeout

    def _event(self, search_id: str, source_id: str, event_type: str, status: str,
               payload: Mapping[str, Any] | None = None) -> None:
        self.store.append_search_event(SearchEvent(
            0, search_id, "source_sync", source_id, event_type, status,
            dict(payload or {}), _now(),
        ))

    def _progress(self, search_id: str, source_id: str, status: str, *, count: int = 0,
                  error_code: str | None = None, cached: list[dict] | None = None,
                  fetching: list[dict] | None = None, completed: list[dict] | None = None) -> None:
        self.store.save_source_progress(SearchSourceProgress(
            search_id, source_id, status, cached or [], fetching or [], completed or [], count,
            error_code, "SOURCE_FAILED" if status == "failed" else (
                "CACHE_HIT" if status == "cached" else "SOURCE_COMPLETED" if status == "completed" else "FETCHING_SOURCE"
            ), _now(),
        ))

    def _save_unit(self, unit: SourceFetchUnit) -> SourceFetchUnit:
        now = _now()
        existing = self.store.get_fetch_unit(unit.fetch_unit_id)
        if existing is not None and not unit.created_at:
            unit.created_at = existing.created_at
        unit.updated_at = unit.updated_at or now
        self.store.save_fetch_unit(unit, now)
        return unit

    def _persist_record(self, source_id: str, unit: SourceFetchUnit, record: Any) -> str | None:
        info = _record_info(record)
        title = str(_record_value(record, "title", info.get("title")) or "").strip()
        if not title:
            return None
        year_raw = _record_value(record, "year", info.get("year"))
        try:
            year = int(year_raw) if year_raw is not None else unit.year
        except (TypeError, ValueError):
            year = unit.year
        doi = normalize_doi(_record_value(record, "doi", info.get("doi"))) or None
        normalized = normalize_title(title)
        conference_id = _conference_id(source_id, record)
        candidates = self.store.list_catalog_papers([conference_id], [year], index_status=None)
        existing = next((paper for paper in candidates if (doi and normalize_doi(paper.doi) == doi)
                         or (paper.normalized_title == normalized and paper.year == year)), None)
        authors = list(_record_value(record, "authors", info.get("authors", ())) or ())
        abstract = _record_value(record, "abstract", info.get("abstract"))
        keywords = list(_record_value(record, "keywords", info.get("keywords", ())) or ())
        page_url = _record_value(record, "article_url", info.get("url") or info.get("source_page_url"))
        pdf_url = _record_value(record, "pdf_url", info.get("pdf_url") or info.get("ee"))
        pre_pdf = _record_value(record, "prepublication_pdf_url", info.get("prepublication_pdf_url"))
        stage = _record_value(record, "publication_stage", info.get("publication_stage")) or "published"
        provenance = dict(_record_value(record, "provenance", {}) or {})
        route = _unit_route(unit)
        route_source = route_source_id(source_id, route)
        source_record_id = f"{route_source}|{normalize_doi(doi) or normalized}|{year or ''}"
        source_key = normalize_doi(doi) or f"{normalized}|{year or ''}"
        # ``catalog_source_records`` keeps source_kind canonical, so qualify
        # only the official route's key to retain both records under the table's
        # existing (source_kind, source_key) uniqueness contract.
        if route == "official":
            source_key = f"{route_source}|{source_key}"
        paper_id = existing.catalog_paper_id if existing else hashlib.sha256(
            f"{conference_id}|{source_key}".encode("utf-8")
        ).hexdigest()[:32]
        base = existing or CatalogPaper(
            paper_id, conference_id, year, "", normalized, [], None, [], None, None,
            stage, None, None, None, None, "", "pending", 0, "", _now(),
        )
        values = {
            "title": title, "authors": authors, "abstract": abstract, "keywords": keywords,
            "doi": doi, "official_page_url": page_url, "official_pdf_url": pdf_url,
            "prepublication_pdf_url": pre_pdf,
        }
        filled: dict[str, Any] = {}
        for field_name, value in values.items():
            if value is None or value == "" or value == []:
                continue
            provenance_name = provenance.get(field_name, route_source)
            # Existing official parsers use their public conference source ID
            # in record-level provenance.  Upgrade that legacy value only when
            # it denotes the record's own route; OpenAlex/Crossref enrichment
            # provenance must remain the real external source.
            if route == "official" and canonical_source_id(provenance_name) == canonical_source_id(source_id):
                provenance_name = route_source
            if existing is None or not getattr(base, field_name, None):
                filled[field_name] = value
                self.store.save_field_provenance(paper_id, field_name, provenance_name,
                                                 source_record_id=source_record_id, now=_now())
            elif self.store.save_field_provenance(paper_id, field_name, provenance_name,
                                                  source_record_id=source_record_id, now=_now()):
                filled[field_name] = value
        merged = replace(base, **filled, year=base.year or year, normalized_title=base.normalized_title or normalized,
                         publication_stage=base.publication_stage or stage, updated_at=_now())
        metadata = {
            "title": merged.title, "authors": merged.authors, "year": merged.year,
            "abstract": merged.abstract, "keywords": merged.keywords, "doi": merged.doi,
            "page": merged.official_page_url, "pdf": merged.official_pdf_url,
        }
        merged.metadata_hash = hashlib.sha256(json.dumps(metadata, sort_keys=True, default=str).encode()).hexdigest()
        self.store.upsert_catalog_paper(merged)
        self.store.save_source_record(CatalogSourceRecord(
            source_record_id, paper_id, unit.fetch_unit_id, source_id, source_key, _safe(record), _now(),
        ))
        return paper_id

    def _persist_units_and_records(self, source_id: str, result: Any) -> tuple[int, list[str], list[str]]:
        units = [_as_store_unit(source_id, unit) for unit in list(getattr(result, "units", ()) or ())]
        records = list(getattr(result, "records", ()) or ())
        for unit in units:
            self._save_unit(unit)
        default_unit = units[0] if units else None
        ids: list[str] = []
        for record in records:
            year = _record_value(record, "year", None)
            unit = next((item for item in units if item.year == year), default_unit)
            if unit is None:
                continue
            paper_id = self._persist_record(source_id, unit, record)
            if paper_id:
                ids.append(paper_id)
        failed = [str(year) for year in getattr(result, "failed_years", ()) or ()]
        cached = [str(year) for year in getattr(result, "cached_years", ()) or ()]
        return len(ids), failed, cached

    def run(self, sync_id: str, source_id: str, years: Iterable[int]) -> SearchJob:
        source_id = canonical_source_id(source_id, strict=True)
        job = self.store.get_search_job(sync_id)
        if job is None:
            raise KeyError(sync_id)
        source = self.registry.adapter(source_id, store=self.store, timeout=self.timeout)
        self.store.create_search_job(replace(job, status="running", started_at=_now(), updated_at=_now()))
        self._progress(sync_id, source_id, "fetching")
        self._event(sync_id, source_id, "SOURCE_STARTED", "fetching")
        try:
            selected = sorted({int(year) for year in years})
            cached_progress: list[dict] = []
            completed_progress: list[dict] = []
            # DBLP/USENIX retain the existing graph's durable sync code and
            # leases; this is only an adapter selection seam.
            if source_id in {"usenix", "dblp"}:
                from backend.app.paper_discovery.application.catalog_search_graph import CatalogSearchGraph
                graph = CatalogSearchGraph(
                    store=self.store, accepted_source=self.registry.adapter("usenix", store=self.store),
                    dblp_source=self.registry.adapter("dblp", store=self.store), source_scope=source_id,
                    dblp_enabled=True,
                )
                result = graph.sync_usenix(job) if source_id == "usenix" else graph.sync_dblp(job)
                status = str(result.get("status") or "completed")
                count = int(result.get("paper_count") or 0)
                error = result.get("error_code")
                failed = [] if not error else selected
                cached_raw = result.get("cached_units", ())
                cached = [str(item.get("year")) if isinstance(item, Mapping) and item.get("year") is not None else str(item)
                          for item in cached_raw]
                cached_progress, completed_progress = _progress_lists(
                    result.get("completed_units", ()), cached_raw,
                )
            elif source_id in {"ieee_sp", "ccs", "ndss"}:
                scopes: list[dict[str, Any]] = []
                official_years: set[int] = set()
                if source_id == "ieee_sp":
                    official_years.add(2024)
                elif source_id == "ndss":
                    # The parser's fixed URL map is the sole official-route allowlist;
                    # registry verified_years remains a separate coverage gate.
                    official_years.update(NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS)
                official_selected = [year for year in selected if year in official_years]
                if official_selected:
                    scopes.append({"years": official_selected, "route": "official"})
                    selected = [year for year in selected if year not in official_years]
                if selected:
                    scopes.append({"years": selected})
                class _Combined:
                    units: tuple[Any, ...] = ()
                    records: tuple[Any, ...] = ()
                    failed_years: tuple[int, ...] = ()
                    cached_years: tuple[int, ...] = ()
                    warnings: tuple[str, ...] = ()
                    error_code: str | None = None
                    status: str = "completed"
                combined = _Combined()
                units: list[Any] = []
                records: list[Any] = []
                failed_years: list[int] = []
                cached_years: list[int] = []
                warnings: list[str] = []
                for scope in scopes:
                    part = source.sync_units(scope)
                    units.extend(getattr(part, "units", ()) or ())
                    records.extend(getattr(part, "records", ()) or ())
                    failed_years.extend(getattr(part, "failed_years", ()) or ())
                    cached_years.extend(getattr(part, "cached_years", ()) or ())
                    warnings.extend(getattr(part, "warnings", ()) or ())
                combined.units, combined.records = tuple(units), tuple(records)
                combined.failed_years, combined.cached_years, combined.warnings = tuple(failed_years), tuple(cached_years), tuple(warnings)
                combined.status = "failed" if failed_years and not records else "partial" if failed_years else "completed"
                combined.error_code = "SOURCE_FAILED" if combined.status == "failed" else None
                count, failed, cached = self._persist_units_and_records(source_id, combined)
                status, error = combined.status, combined.error_code
                cached_progress, completed_progress = _store_unit_progress(source_id, combined.units, cached)
            else:
                units = list(source.discover_units({"years": selected}))
                records: list[Any] = []
                failed = []
                cached = []
                count = 0
                for index, unit in enumerate(units):
                    persisted = _as_store_unit(source_id, unit)
                    previous = self.store.get_fetch_unit(persisted.fetch_unit_id)
                    if previous is not None and previous.status == "completed" and previous.content_hash:
                        # Keep the durable terminal unit in the aggregate below.  Reusing
                        # the newly discovered ``pending`` descriptor here would overwrite
                        # a cache hit back to ``pending`` during the final persistence pass.
                        units[index] = previous
                        cached.append(str(persisted.year or persisted.unit_key))
                        continue
                    updated, payload = source.fetch_unit(unit, unit.conditional_headers() if hasattr(unit, "conditional_headers") else None)
                    # The final persistence pass also writes every unit alongside records;
                    # retain the adapter's returned status/hash instead of the original
                    # ``pending`` descriptor so a successful fetch remains completed.
                    units[index] = updated
                    self._save_unit(_as_store_unit(source_id, updated))
                    if payload is None:
                        if updated.status == "failed":
                            failed.append(str(persisted.year or persisted.unit_key))
                        continue
                    records.extend(source.parse_catalog(payload))
                class _Aggregate:
                    pass
                aggregate = _Aggregate()
                aggregate.units = units
                aggregate.records = records
                aggregate.failed_years = failed
                aggregate.cached_years = cached
                count, failed, cached = self._persist_units_and_records(source_id, aggregate)
                status, error = ("failed" if failed and not count else "partial" if failed else "completed"), ("SOURCE_FAILED" if failed else None)
                cached_progress, completed_progress = _store_unit_progress(source_id, units, cached)
            progress_status = "failed" if status == "failed" else "merging" if status == "partial" else "cached" if cached and not count else "completed"
            self._progress(sync_id, source_id, progress_status, count=count, error_code=error,
                           cached=cached_progress, completed=completed_progress)
            self._event(sync_id, source_id, "SOURCE_FAILED" if error else "SOURCE_COMPLETED", progress_status,
                        {"error_code": error} if error else {"paper_count": count})
            final = "failed" if status == "failed" else "partial" if status == "partial" else "completed"
            self.store.create_search_job(replace(job, status=final, degraded=final != "completed", error_code=error,
                                                 total_results=count, completed_at=_now(), updated_at=_now()))
        except Exception:
            self._progress(sync_id, source_id, "failed", error_code="SOURCE_FAILED")
            self._event(sync_id, source_id, "SOURCE_FAILED", "failed", {"error_code": "SOURCE_FAILED"})
            self.store.create_search_job(replace(job, status="failed", degraded=True, error_code="SOURCE_FAILED",
                                                 completed_at=_now(), updated_at=_now()))
        return self.store.get_search_job(sync_id) or job


def submit_catalog_source_sync(runtime: CatalogSourceRuntime, sync_id: str, source_id: str, years: Iterable[int]) -> bool:
    with _LOCK:
        if sync_id in _INFLIGHT:
            return False
        _INFLIGHT.add(sync_id)

    def _run() -> None:
        try:
            runtime.run(sync_id, source_id, years)
        finally:
            with _LOCK:
                _INFLIGHT.discard(sync_id)

    _EXECUTOR.submit(_run)
    return True


__all__ = ["CatalogSourceRuntime", "SOURCE_SYNC_GRAPH_VERSION", "submit_catalog_source_sync"]
