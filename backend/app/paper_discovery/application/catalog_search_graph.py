"""Fixed LangGraph catalog search and its restartable application runner.

The project virtualenv provides LangGraph. A small explicit fallback remains
for minimal test images, but both paths use the same persisted node contract.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, TypedDict
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import models as qdrant_models

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - only for minimal runtime images
    END = START = StateGraph = None

from backend.app.knowledge_base.application import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    embed_texts,
    encode_sparse,
    ensure_collection,
    get_client,
    rerank_hits,
    rrf_fuse,
)
from backend.app.paper_discovery.domain.paper_discovery import (
    CatalogPaper,
    CatalogSourceRecord,
    SearchEvent,
    SearchJob,
    SearchResult,
    SearchSourceProgress,
    SourceFetchUnit,
)
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.platform.config import EMBED_DIM

GRAPH_VERSION = "catalog-search-v1"
NODE_NAMES = (
    "validate_request", "plan_fetch_units", "sync_usenix", "sync_dblp",
    "merge_catalog_metadata", "index_changed_catalog_papers", "retrieve_and_rerank",
    "freeze_search_results", "finalize_job",
)
SOURCE_KINDS = ("usenix", "dblp")
EVENT_ERROR_CODES = frozenset({
    "DBLP_UNAVAILABLE", "DBLP_TIMEOUT", "DBLP_NETWORK_ERROR", "DBLP_HTTP_ERROR",
    "DBLP_INVALID_RESPONSE", "DBLP_RATE_LIMITED", "USENIX_UNAVAILABLE",
    "USENIX_SYNC_FAILED", "USENIX_FETCH_FAILED", "USENIX_PARSE_FAILED",
    "USENIX_UNIT_FAILED", "NO_PAGES", "INDEX_UNAVAILABLE", "RAG_DEGRADED",
    "SOURCES_UNAVAILABLE", "SEARCH_WORKFLOW_FAILED", "INVALID_QUERY",
})
EVENT_MESSAGE_CODES = frozenset({
    "SOURCE_QUEUED", "CHECKING_CACHE", "FETCHING_SOURCE", "MERGING_METADATA",
    "SOURCE_COMPLETED", "CACHE_HIT", "SOURCE_FAILED", "INDEX_DEGRADED",
    "SOURCE_SKIPPED",
})


class _GraphState(TypedDict, total=False):
    search_id: str
    job: SearchJob
    usenix: dict[str, Any]
    dblp: dict[str, Any]
    ranked: list[dict[str, Any]]
    degraded: bool


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CatalogRagAdapter:
    """Injectable directory RAG boundary using the existing KB primitives.

    The personal KB helpers remain unchanged by default.  This adapter only
    changes the collection name and payload/filter shape, and degrades to a
    deterministic lexical result when Ollama/Qdrant is unavailable.
    """

    collection_name = "paper-discovery-catalog"
    # Directory points are not document chunks.  Keeping an explicit chunker
    # namespace prevents the shared RRF key from colliding with personal-KB
    # chunks that happen to use the same paper id/chunk index.
    catalog_chunker = "catalog-v1"

    def __init__(self, *, client: Any = None, embedder: Callable = embed_texts,
                 sparse_encoder: Callable = encode_sparse,
                 reranker: Callable = rerank_hits,
                 collection_name: Optional[str] = None):
        self.client = client
        self.embedder = embedder
        self.sparse_encoder = sparse_encoder
        self.reranker = reranker
        self.collection_name = collection_name or self.collection_name
        self.degraded = False

    @staticmethod
    def _text(paper: CatalogPaper) -> str:
        return "\n".join((paper.title, paper.abstract or "", " ".join(paper.keywords)))

    def _client(self):
        return self.client or get_client()

    def index(self, papers: Iterable[CatalogPaper]) -> bool:
        papers = list(papers)
        if not papers:
            return True
        try:
            target = self._client()
            ensure_collection(target, dim=EMBED_DIM, collection_name=self.collection_name)
            vectors = self.embedder([self._text(paper) for paper in papers])
            target.upsert(
                collection_name=self.collection_name,
                points=[qdrant_models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"paper-discovery-catalog:{paper.catalog_paper_id}")),
                    vector={DENSE_VECTOR: vector, SPARSE_VECTOR: self.sparse_encoder(self._text(paper))},
                    payload={
                        # ``rrf_fuse`` is intentionally shared with the KB and
                        # reads ``paper_id``/``chunker``.  Keep the directory
                        # identity in both the shared field and its canonical
                        # field so a catalog hit can always be frozen back to
                        # CatalogPaper.
                        "paper_id": paper.catalog_paper_id,
                        "catalog_paper_id": paper.catalog_paper_id,
                        "chunker": self.catalog_chunker,
                        "chunk_index": 0,
                        "page": 0,
                        "page_end": 0,
                        "file_name": "catalog",
                        "conference_id": paper.conference_id,
                        "year": paper.year,
                        "title": paper.title,
                        "normalized_title": paper.normalized_title,
                        "abstract": paper.abstract or "",
                        "keywords": paper.keywords,
                        "metadata_hash": paper.metadata_hash,
                        "text": self._text(paper),
                    },
                ) for paper, vector in zip(papers, vectors, strict=False)],
            )
            self.degraded = False
            return True
        except Exception:
            # The graph records a per-paper failed index and continues.  No
            # paper is falsely marked indexed when the external RAG is down.
            self.degraded = True
            return False

    @staticmethod
    def _filter(*, conference_ids: Optional[Iterable[str]], years: Optional[Iterable[int]]):
        must = []
        if conference_ids:
            must.append(qdrant_models.FieldCondition(
                key="conference_id", match=qdrant_models.MatchAny(any=list(conference_ids))))
        if years:
            must.append(qdrant_models.FieldCondition(
                key="year", match=qdrant_models.MatchAny(any=[int(item) for item in years])))
        return qdrant_models.Filter(must=must) if must else None

    def _fallback(self, query: str, papers: Iterable[CatalogPaper]) -> list[dict[str, Any]]:
        query_key = normalize_title(query)
        ranked = []
        for paper in papers:
            text = normalize_title(self._text(paper))
            score = 1.0 if query_key and query_key in text else 0.0
            ranked.append({"catalog_paper_id": paper.catalog_paper_id,
                           "retrieval_score": score, "rerank_score": None, "final_score": score})
        ranked.sort(key=lambda item: (-item["final_score"], item["catalog_paper_id"]))
        return ranked

    def retrieve_and_rerank(self, query: str, papers: Iterable[CatalogPaper], **kwargs: Any) -> list[dict[str, Any]]:
        papers = [paper for paper in papers if paper.index_status == "indexed"]
        # ``rrf_fuse`` returns the shared KB ``Hit`` type, whose identity field
        # is named ``paper_id``.  The catalog boundary must resolve that shared
        # identity back to an indexed CatalogPaper before handing results to
        # the graph; otherwise an old/malformed point could leak an empty ID
        # and be silently discarded by ``freeze_search_results``.
        catalog_ids = {str(paper.catalog_paper_id): paper.catalog_paper_id for paper in papers}
        try:
            target = self._client()
            if not target.collection_exists(self.collection_name):
                raise RuntimeError("catalog collection unavailable")
            dense = self.embedder([query])[0]
            query_filter = self._filter(conference_ids=kwargs.get("conference_ids"), years=kwargs.get("years"))
            dense_points = target.query_points(collection_name=self.collection_name, query=dense,
                                               using=DENSE_VECTOR, limit=max(1, len(papers)),
                                               query_filter=query_filter).points
            sparse_points = target.query_points(collection_name=self.collection_name,
                                                query=self.sparse_encoder(query), using=SPARSE_VECTOR,
                                                limit=max(1, len(papers)), query_filter=query_filter).points
            hits = rrf_fuse([dense_points, sparse_points])
            original_hits = list(hits)
            reranked = self.reranker(query, hits) if self.reranker is not None else None
            if hasattr(reranked, "hits"):
                hits = list(reranked.hits)
                degraded = bool(getattr(reranked, "degraded", False))
                scores = getattr(reranked, "scores_by_original_index", None)
                if scores is not None:
                    score_by_id = {id(hit): float(score) for hit, score in zip(original_hits, scores, strict=False)}
                    for hit in hits:
                        if id(hit) in score_by_id:
                            hit.rerank_score = score_by_id[id(hit)]
            else:
                degraded = True
            self.degraded = degraded
            result = []
            for hit in hits:
                hit_paper_id = str(getattr(hit, "paper_id", "") or "")
                catalog_paper_id = catalog_ids.get(hit_paper_id)
                if not catalog_paper_id:
                    # Keep compatibility with injectable Hit-like test doubles
                    # that expose the canonical directory field directly.
                    hit_catalog_id = str(getattr(hit, "catalog_paper_id", "") or "")
                    catalog_paper_id = catalog_ids.get(hit_catalog_id)
                if not catalog_paper_id:
                    continue
                final = hit.rerank_score if hit.rerank_score is not None else hit.score
                result.append({"catalog_paper_id": catalog_paper_id,
                               "retrieval_score": float(hit.score),
                               "rerank_score": hit.rerank_score,
                               "final_score": float(final)})
            return result
        except Exception:
            self.degraded = True
            return self._fallback(query, papers)


class CatalogSearchGraph:
    """Nine fixed nodes with SQLite checkpoints at every externally visible stage."""

    def __init__(self, *, store: Any, accepted_source: Any, dblp_source: Any,
                 rag: Optional[CatalogRagAdapter] = None, ttl_seconds: int = 86400,
                 dblp_enabled: Optional[bool] = None):
        self.store = store
        self.accepted_source = accepted_source
        self.dblp_source = dblp_source
        self.rag = rag or CatalogRagAdapter()
        self.ttl_seconds = int(ttl_seconds)
        # Explicit override wins so tests can exercise the DBLP path even though
        # the source is disabled by default in production configuration.
        self.dblp_enabled_override = dblp_enabled
        self.compiled_graph = self._build_graph()

    def _build_graph(self):
        """Compile exactly nine nodes; source nodes fan out and join explicitly."""
        if StateGraph is None:
            return None
        graph = StateGraph(_GraphState)

        graph.add_node("validate_request", lambda state: (self.validate_request(state["job"]) or {}))
        graph.add_node("plan_fetch_units", lambda state: (self.plan_fetch_units(state["job"]) or {}))
        graph.add_node("sync_usenix", lambda state: {"usenix": self.sync_usenix(state["job"])})
        graph.add_node("sync_dblp", lambda state: {"dblp": self.sync_dblp(state["job"])})
        graph.add_node("merge_catalog_metadata", lambda state: (self.merge_catalog_metadata(state["job"], state.get("usenix"), state.get("dblp")) or {}))
        graph.add_node("index_changed_catalog_papers", lambda state: (self.index_changed_catalog_papers(state["job"]) or {}))
        graph.add_node("retrieve_and_rerank", lambda state: dict(zip(("ranked", "degraded"), self.retrieve_and_rerank(state["job"]), strict=True)))
        graph.add_node("freeze_search_results", lambda state: (self.freeze_search_results(
            state["job"], state.get("ranked", []), degraded=bool(state.get("degraded")),
            source_results=(state.get("usenix", {}), state.get("dblp", {})),
        ) or {}))
        graph.add_node("finalize_job", lambda state: (self.finalize_job(state["job"]) or {}))
        graph.add_edge(START, "validate_request")
        graph.add_edge("validate_request", "plan_fetch_units")
        graph.add_edge("plan_fetch_units", "sync_usenix")
        graph.add_edge("plan_fetch_units", "sync_dblp")
        graph.add_edge("sync_usenix", "merge_catalog_metadata")
        graph.add_edge("sync_dblp", "merge_catalog_metadata")
        graph.add_edge("merge_catalog_metadata", "index_changed_catalog_papers")
        graph.add_edge("index_changed_catalog_papers", "retrieve_and_rerank")
        graph.add_edge("retrieve_and_rerank", "freeze_search_results")
        graph.add_edge("freeze_search_results", "finalize_job")
        graph.add_edge("finalize_job", END)
        return graph.compile()

    def _event(self, search_id: str, node: str, event_type: str,
               status: Optional[str] = None, source_kind: Optional[str] = None,
               payload: Optional[Mapping[str, Any]] = None) -> None:
        payload = dict(payload or {})
        # The store applies the final allowlist too; keeping this boundary
        # narrow prevents accidental URL/exception propagation from fakes.
        if "error_code" in payload and payload["error_code"] not in EVENT_ERROR_CODES:
            payload["error_code"] = "SEARCH_WORKFLOW_FAILED"
        self.store.append_search_event(SearchEvent(
            0, search_id, node, source_kind, event_type, status,
            payload, _now(),
        ))

    def _progress(self, search_id: str, source: str, status: str, *, count: int = 0,
                  error_code: Optional[str] = None, message_code: Optional[str] = None,
                  cached: Optional[list[dict]] = None, fetching: Optional[list[dict]] = None,
                  completed: Optional[list[dict]] = None) -> None:
        self.store.save_source_progress(SearchSourceProgress(
            search_id, source, status, cached or [], fetching or [], completed or [], count,
            error_code, message_code or {
                "queued": "SOURCE_QUEUED", "checking_cache": "CHECKING_CACHE",
                "fetching": "FETCHING_SOURCE", "merging": "MERGING_METADATA",
                "completed": "SOURCE_COMPLETED", "cached": "CACHE_HIT",
                "failed": "SOURCE_FAILED", "skipped": "SOURCE_SKIPPED",
            }.get(status, "SOURCE_QUEUED"), _now(),
        ))

    def run(self, search_id: str) -> SearchJob:
        job = self.store.get_search_job(search_id)
        if job is None:
            raise KeyError(search_id)
        try:
            if self.compiled_graph is not None:
                self.compiled_graph.invoke({"search_id": search_id, "job": job})
            else:  # minimal runtime fallback; node order and persistence are identical
                self.validate_request(job)
                self.plan_fetch_units(job)
                usenix = self.sync_usenix(job)
                dblp = self.sync_dblp(job)
                self.merge_catalog_metadata(job, usenix, dblp)
                self.index_changed_catalog_papers(job)
                ranked, degraded = self.retrieve_and_rerank(job)
                self.freeze_search_results(job, ranked, degraded=degraded, source_results=(usenix, dblp))
                self.finalize_job(job)
        except Exception:  # checkpoint a stable failure, never leak internals
            self._event(search_id, "finalize_job", "JOB_FAILED", "failed",
                        payload={"error_code": "SEARCH_WORKFLOW_FAILED", "message_code": "SEARCH_WORKFLOW_FAILED"})
            self.store.create_search_job(SearchJob(
                job.search_id, job.query, job.conference_ids, job.years, "failed", GRAPH_VERSION,
                True, "SEARCH_WORKFLOW_FAILED", job.total_results, job.created_at, job.started_at,
                _now(), job.expires_at, _now(),
            ))
        return self.store.get_search_job(search_id) or job

    def validate_request(self, job: SearchJob) -> None:
        if job.conference_ids != ["usenix-security"] or job.years != sorted(set(job.years)):
            raise ValueError("INVALID_SEARCH_SCOPE")
        if not job.query.strip() or not 1 <= len(job.query.strip()) <= 500:
            raise ValueError("INVALID_QUERY")
        self.store.create_search_job(SearchJob(
            job.search_id, job.query.strip(), job.conference_ids, job.years, "running", GRAPH_VERSION,
            False, None, job.total_results, job.created_at or _now(), _now(), None, job.expires_at, _now(),
        ))
        self._event(job.search_id, "validate_request", "NODE_COMPLETED", "running")

    def plan_fetch_units(self, job: SearchJob) -> None:
        for source in SOURCE_KINDS:
            self._progress(job.search_id, source, "checking_cache")
        self._event(job.search_id, "plan_fetch_units", "NODE_COMPLETED", "running")

    def sync_usenix(self, job: SearchJob) -> dict[str, Any]:
        self._progress(job.search_id, "usenix", "fetching")
        self._event(job.search_id, "sync_usenix", "SOURCE_STARTED", "fetching", "usenix")
        try:
            if getattr(self.accepted_source, "store", None) is None:
                self.accepted_source.store = self.store
            source = next(item for item in self.store.list_conferences() if item.conference_id == "usenix-security")
            self.accepted_source._discovery_routes = list(source.discovery_routes)
            sync = getattr(self.accepted_source, "sync_usenix_units", None)
            if callable(sync):
                result = sync(job.search_id, source.conference_id, job.years, owner=f"search:{job.search_id}")
            else:
                result = self._search_fallback(self.accepted_source, source, job, "usenix")
            status = getattr(result, "status", "completed")
            error = getattr(result, "error_code", None)
            count = int(getattr(result, "paper_count", 0) or 0)
            progress_status = "failed" if status == "failed" else (
                "cached" if status == "cached" else (
                    "merging" if status == "partial" else (
                        "fetching" if status == "waiting" else "completed"
                    )
                )
            )
            waiting_units = list(getattr(result, "waiting", ()) or ())
            self._progress(
                job.search_id, "usenix", progress_status, count=count, error_code=error,
                fetching=[{"unit_id": unit_id} for unit_id in waiting_units],
            )
            return {
                "status": status, "error_code": error, "paper_count": count,
                "waiting_units": waiting_units,
            }
        except Exception:
            self._progress(job.search_id, "usenix", "failed", error_code="USENIX_UNAVAILABLE")
            return {"status": "failed", "error_code": "USENIX_UNAVAILABLE", "paper_count": 0}

    def _dblp_enabled(self) -> bool:
        """DBLP now answers with a bot challenge instead of JSON; default off."""
        if self.dblp_enabled_override is not None:
            return bool(self.dblp_enabled_override)
        cached = getattr(self, "_dblp_enabled_cache", None)
        if cached is None:
            from backend.app.platform.settings.settings_repository import load_article_settings

            cached = bool(getattr(load_article_settings(), "paper_discovery_dblp_enabled", False))
            self._dblp_enabled_cache = cached
        return cached

    def sync_dblp(self, job: SearchJob) -> dict[str, Any]:
        if not self._dblp_enabled():
            # ``completed`` keeps the persisted status inside the store's CHECK
            # constraint; SOURCE_SKIPPED is what tells the UI the source is off
            # rather than empty. A skipped source is never degraded, so the job
            # can still complete instead of reporting a permanent partial.
            self._progress(job.search_id, "dblp", "completed", message_code="SOURCE_SKIPPED")
            self._event(job.search_id, "sync_dblp", "SOURCE_SKIPPED", "completed", "dblp")
            return {"status": "skipped", "error_code": None, "paper_count": 0,
                    "cached_units": [], "fetching_units": [], "waiting_units": []}
        self._progress(job.search_id, "dblp", "fetching")
        self._event(job.search_id, "sync_dblp", "SOURCE_STARTED", "fetching", "dblp")
        try:
            source = next(item for item in self.store.list_conferences() if item.conference_id == "usenix-security")
            # Every DBLP year has a durable unit before any source evidence is
            # written.  This satisfies the FK and lets a completed year skip
            # the network on subsequent searches.
            pending_years: list[int] = []
            lease_owner = f"search:{job.search_id}"
            lease_seconds = 300
            leased_units: list[str] = []
            cached_units: list[dict[str, Any]] = []
            fetching_units: list[dict[str, Any]] = []
            for year in job.years:
                unit_id = f"dblp|{source.conference_id}|{year}|stream"
                existing = self.store.get_fetch_unit(unit_id)
                if existing is not None and existing.status == "completed":
                    cached_units.append({"unit_id": unit_id, "year": year})
                    continue
                now = _now()
                unit = SourceFetchUnit(
                    fetch_unit_id=unit_id, source_kind="dblp", conference_id=source.conference_id,
                    year=year, unit_key=f"{source.dblp_stream}|{year}", status="pending",
                    created_at=existing.created_at if existing else now, updated_at=now,
                )
                ensure = getattr(self.store, "ensure_fetch_unit", None)
                if callable(ensure):
                    ensure(unit, now)
                elif existing is None:
                    # Compatibility for narrow fake stores.  The production
                    # PaperDiscoveryStore uses ensure_fetch_unit above, which
                    # is INSERT .. DO NOTHING and cannot erase a competing
                    # worker's lease.
                    self.store.save_fetch_unit(unit, now)
                acquired = True
                acquire = getattr(self.store, "acquire_fetch_unit", None)
                if callable(acquire):
                    acquired = bool(acquire(unit_id, lease_owner, lease_seconds, now))
                if acquired:
                    pending_years.append(year)
                    leased_units.append(unit_id)
                else:
                    fetching_units.append({"unit_id": unit_id, "year": year})
            if not pending_years:
                if fetching_units:
                    self._progress(job.search_id, "dblp", "fetching", count=0,
                                   cached=cached_units, fetching=fetching_units,
                                   completed=cached_units)
                    return {"status": "waiting", "error_code": None, "paper_count": 0,
                            "cached_units": cached_units, "fetching_units": fetching_units,
                            "waiting_units": fetching_units}
                self._progress(job.search_id, "dblp", "cached", count=0,
                               cached=cached_units, fetching=fetching_units, completed=cached_units)
                return {"status": "cached", "error_code": None, "paper_count": 0,
                        "cached_units": cached_units, "fetching_units": fetching_units}
            sync = getattr(self.dblp_source, "sync_dblp_units", None)
            result = sync(job.search_id, source, pending_years) if callable(sync) else self.dblp_source.search(source, job.query, pending_years, limit=100)
            records = list(getattr(result, "records", ()) or ())
            for record in records:
                self._persist_dblp_record(record, source, job)
            completed = []
            error = getattr(result, "error_code", None)
            warnings = list(getattr(result, "warnings", ()) or ())
            failed_years = set()
            for value in getattr(result, "failed_years", ()) or ():
                try:
                    failed_years.add(int(value))
                except (TypeError, ValueError):
                    continue
            # Older injectable sources only exposed warnings.  Infer failed
            # years from observed record years when possible; if a warning
            # carries no per-year evidence (including an empty successful
            # year), conservatively degrade every pending unit.
            if warnings and not error and not failed_years:
                observed_years = {
                    year for year in (self._record_year(record) for record in records)
                    if year in pending_years
                }
                failed_years.update(
                    {int(year) for year in pending_years} - observed_years
                    or {int(year) for year in pending_years}
                )
            warning_error = str(warnings[0]) if warnings else None
            effective_error = error or warning_error
            has_year_failure = bool(failed_years)
            all_years_failed = bool(pending_years) and {int(year) for year in pending_years}.issubset(failed_years) and not records
            for year in pending_years:
                unit_id = f"dblp|{source.conference_id}|{year}|stream"
                count = sum(1 for record in records if self._record_year(record) == year)
                existing = self.store.get_fetch_unit(unit_id)
                if year in failed_years:
                    # A warning identifies a degraded year even when that
                    # year produced no records; a hard all-year error keeps
                    # the retryable unit in failed state when it has no data.
                    unit_status = "failed" if all_years_failed and not count and not (existing and existing.paper_count) else (
                        "partial" if warnings or count or (existing and existing.paper_count) else "failed"
                    )
                elif has_year_failure:
                    unit_status = "completed"
                elif error:
                    unit_status = "partial" if count or (existing and existing.paper_count) else "failed"
                else:
                    unit_status = "completed"
                final_unit = SourceFetchUnit(
                    fetch_unit_id=unit_id, source_kind="dblp", conference_id=source.conference_id,
                    year=year, unit_key=f"{source.dblp_stream}|{year}",
                    status=unit_status, paper_count=count,
                    error_code=effective_error if unit_status != "completed" else None,
                    lease_owner=lease_owner if unit_id in leased_units else None,
                    last_success_at=_now() if unit_status == "completed" else None,
                    created_at=existing.created_at if existing else _now(),
                    updated_at=_now(),
                )
                self.store.save_fetch_unit(final_unit, _now())
                release = getattr(self.store, "release_lease", None)
                if callable(release) and unit_id in leased_units:
                    release(unit_id, lease_owner, status=unit_status, now=_now())
                completed.append({"unit_id": unit_id, "year": year, "paper_count": count, "status": unit_status})
            failed = bool(error and not records) or all_years_failed
            source_degraded = bool(error or warnings)
            waiting = bool(fetching_units)
            progress_status = "fetching" if waiting else ("failed" if failed else ("merging" if source_degraded else "completed"))
            self._progress(job.search_id, "dblp", progress_status,
                           count=len(records), error_code=effective_error, cached=cached_units,
                           fetching=fetching_units, completed=completed)
            return {"status": "waiting" if waiting else ("failed" if failed else ("partial" if source_degraded else "completed")), "error_code": effective_error,
                    "paper_count": len(records), "warnings": warnings, "cached_units": cached_units,
                    "fetching_units": fetching_units, "completed_units": completed,
                    "failed_years": sorted(failed_years), "waiting_units": fetching_units}
        except Exception:
            # A network/parser exception must not leave a valid lease blocking
            # future searches.  The unit remains retryable (failed), never
            # completed.
            release = getattr(self.store, "release_lease", None)
            if callable(release):
                for unit_id in locals().get("leased_units", []):
                    with contextlib.suppress(Exception):
                        release(unit_id, locals().get("lease_owner", ""), status="failed", now=_now())
            self._progress(job.search_id, "dblp", "failed", error_code="DBLP_UNAVAILABLE")
            return {"status": "failed", "error_code": "DBLP_UNAVAILABLE", "paper_count": 0}

    @staticmethod
    def _record_year(record: Mapping[str, Any]) -> Optional[int]:
        info = record.get("info", record) if isinstance(record, Mapping) else {}
        value = info.get("year") if isinstance(info, Mapping) else None
        return int(value) if str(value or "").isdigit() else None

    def _search_fallback(self, adapter: Any, source: Any, job: SearchJob, kind: str) -> dict[str, Any]:
        result = adapter.search(source, job.query, job.years, limit=100)
        for record in list(getattr(result, "records", ()) or ()):
            self._persist_dblp_record(record, source, job)
        return {"status": "failed" if getattr(result, "error_code", None) else "completed",
                "error_code": getattr(result, "error_code", None), "paper_count": len(getattr(result, "records", ()) or ())}

    def _persist_dblp_record(self, record: Mapping[str, Any], source: Any, job: SearchJob) -> None:
        info = record.get("info", record) if isinstance(record, Mapping) else {}
        if not isinstance(info, Mapping):
            return
        title = str(info.get("title") or "").strip()
        if not title:
            return
        year = int(info["year"]) if str(info.get("year", "")).isdigit() else None
        unit_id = f"dblp|{source.conference_id}|{year}|stream"
        if self.store.get_fetch_unit(unit_id) is None:
            now = _now()
            unit = SourceFetchUnit(
                fetch_unit_id=unit_id, source_kind="dblp", conference_id=source.conference_id,
                year=year, unit_key=f"{getattr(source, 'dblp_stream', source.conference_id)}|{year}",
                status="pending", created_at=now, updated_at=now,
            )
            ensure = getattr(self.store, "ensure_fetch_unit", None)
            if callable(ensure):
                ensure(unit, now)
            else:
                self.store.save_fetch_unit(unit, now)
        normalized = normalize_title(title)
        doi = normalize_doi(info.get("doi")) or None
        authors = [str(item) for item in info.get("authors", []) if item]
        existing = []
        try:
            existing = [paper for paper in self.store.list_catalog_papers(index_status=None)
                        if paper.conference_id == source.conference_id and (
                            (doi and normalize_doi(paper.doi) == doi) or
                            (paper.normalized_title == normalized and paper.year == year)
                        )]
        except (AttributeError, TypeError):
            existing = []

        if existing:
            # USENIX is authoritative.  DBLP contributes only fields absent in
            # the official row, while its DOI/key remain useful provenance.
            official = next((item for item in existing
                             if "usenix" in set(self.store.get_catalog_source_kinds(item.catalog_paper_id))), None)
            base = official or existing[0]
            merged = CatalogPaper(
                base.catalog_paper_id, base.conference_id, base.year or year,
                base.title or title, base.normalized_title or normalized,
                list(base.authors or authors), base.abstract or info.get("abstract"),
                list(base.keywords or info.get("keywords", []) or []), base.doi or doi,
                base.dblp_key or info.get("key"), base.publication_stage or "published",
                base.official_page_url or info.get("url"), base.official_pdf_url or info.get("ee"),
                base.prepublication_pdf_url, base.arxiv_id, "",
                "pending", base.index_version, base.created_at, _now(),
            )
            metadata = {
                "title": merged.title, "year": merged.year, "abstract": merged.abstract,
                "doi": merged.doi, "key": merged.dblp_key, "authors": merged.authors,
                "official_page_url": merged.official_page_url,
            }
            merged.metadata_hash = hashlib.sha256(
                json.dumps(metadata, sort_keys=True, default=str).encode()
            ).hexdigest()
            if hasattr(self.store, "merge_catalog_paper"):
                self.store.merge_catalog_paper(merged, [item.catalog_paper_id for item in existing
                                                        if item.catalog_paper_id != base.catalog_paper_id])
            else:
                self.store.upsert_catalog_paper(merged)
            paper = merged
        else:
            # DBLP-only metadata without an abstract is not visible until the
            # authoritative USENIX row arrives, but its source is harmless to
            # ignore here (and avoids an unusable catalog row).
            if not info.get("abstract"):
                return
            paper_id = hashlib.sha256(f"{source.conference_id}|{normalized}|{year}".encode()).hexdigest()[:32]
            metadata = {"title": title, "year": year, "abstract": info.get("abstract"), "doi": doi, "key": info.get("key")}
            paper = CatalogPaper(
                paper_id, source.conference_id, year, title, normalized, authors,
                info.get("abstract"), list(info.get("keywords", []) or []), doi, info.get("key"), "published",
                info.get("url"), info.get("ee"), None, None,
                hashlib.sha256(json.dumps(metadata, sort_keys=True, default=str).encode()).hexdigest(),
            )
            self.store.upsert_catalog_paper(paper)
        self.store.save_source_record(CatalogSourceRecord(
            f"dblp|{paper.catalog_paper_id}", paper.catalog_paper_id, unit_id, "dblp",
            str(info.get("key") or paper.catalog_paper_id), dict(info), _now(),
        ))

    def merge_catalog_metadata(self, job: SearchJob, *_: Any) -> None:
        # Task14's standalone source runner also records a source-local job for
        # backwards compatibility.  Restore the authoritative graph envelope
        # before merge/index/freeze so query, expiry and scope are never lost.
        self.store.create_search_job(SearchJob(
            job.search_id, job.query, job.conference_ids, job.years, "running", GRAPH_VERSION,
            False, None, 0, job.created_at, job.started_at or _now(), None, job.expires_at, _now(),
        ))
        self._merge_existing_catalog_duplicates(job)
        self._event(job.search_id, "merge_catalog_metadata", "NODE_COMPLETED", "merging")

    def _merge_existing_catalog_duplicates(self, job: SearchJob) -> None:
        """Reconcile records when DBLP wins the source-node race.

        The two source nodes are allowed to run in parallel.  Consequently a
        DBLP row may be inserted before the official USENIX row.  Grouping by
        DOI (or normalized title/year) here makes merge a real metadata step,
        rather than an empty checkpoint event.
        """
        merge = getattr(self.store, "merge_catalog_paper", None)
        source_kinds = getattr(self.store, "get_catalog_source_kinds", None)
        if not callable(merge) or not callable(source_kinds):
            return
        papers = self.store.list_catalog_papers(job.conference_ids, job.years, index_status=None)
        groups: dict[tuple[Any, ...], list[CatalogPaper]] = {}
        title_groups: dict[tuple[Any, ...], list[tuple[Any, ...]]] = {}
        no_doi: list[CatalogPaper] = []
        for paper in papers:
            title_key = (
                paper.conference_id, paper.year,
                paper.normalized_title or normalize_title(paper.title),
            )
            doi = normalize_doi(paper.doi)
            if doi:
                doi_key = ("doi", paper.conference_id, doi)
                groups.setdefault(doi_key, []).append(paper)
                title_groups.setdefault(title_key, []).append(doi_key)
            else:
                no_doi.append(paper)
        for paper in no_doi:
            title_key = (
                paper.conference_id, paper.year,
                paper.normalized_title or normalize_title(paper.title),
            )
            matching_doi_groups = list(dict.fromkeys(title_groups.get(title_key, [])))
            if len(matching_doi_groups) == 1:
                groups[matching_doi_groups[0]].append(paper)
            else:
                groups.setdefault(("title",) + title_key, []).append(paper)
        for candidates in groups.values():
            if len(candidates) < 2:
                continue
            official = next((paper for paper in candidates if "usenix" in set(source_kinds(paper.catalog_paper_id))), None)
            base = official or candidates[0]
            merged = base
            for paper in candidates:
                if paper.catalog_paper_id == base.catalog_paper_id:
                    continue
                merged = CatalogPaper(
                    merged.catalog_paper_id, merged.conference_id, merged.year or paper.year,
                    merged.title or paper.title, merged.normalized_title or paper.normalized_title,
                    list(merged.authors or paper.authors), merged.abstract or paper.abstract,
                    list(merged.keywords or paper.keywords), merged.doi or normalize_doi(paper.doi),
                    merged.dblp_key or paper.dblp_key, merged.publication_stage or paper.publication_stage,
                    merged.official_page_url or paper.official_page_url,
                    merged.official_pdf_url or paper.official_pdf_url,
                    merged.prepublication_pdf_url or paper.prepublication_pdf_url,
                    merged.arxiv_id or paper.arxiv_id, "", "pending", merged.index_version,
                    merged.created_at, _now(),
                )
            metadata = {
                "title": merged.title, "year": merged.year, "abstract": merged.abstract,
                "doi": merged.doi, "dblp_key": merged.dblp_key, "authors": merged.authors,
                "official_page_url": merged.official_page_url,
            }
            merged.metadata_hash = hashlib.sha256(
                json.dumps(metadata, sort_keys=True, default=str).encode()
            ).hexdigest()
            merge(merged, [paper.catalog_paper_id for paper in candidates
                           if paper.catalog_paper_id != base.catalog_paper_id])

    def index_changed_catalog_papers(self, job: SearchJob) -> None:
        papers = self.store.list_catalog_papers(
            job.conference_ids, job.years, index_status="pending"
        )
        failed = 0
        for paper in papers:
            try:
                indexed = self.rag.index([paper])
                # ``None`` is the legacy injectable adapter success value;
                # explicit False is the external dependency degraded result.
                if indexed is False:
                    raise RuntimeError("RAG unavailable")
                self.store.mark_catalog_indexed(paper.catalog_paper_id)
            except Exception:
                self.store.mark_catalog_index_failed(paper.catalog_paper_id)
                failed += 1
        if failed:
            self._event(job.search_id, "index_changed_catalog_papers", "INDEX_DEGRADED", "partial",
                        payload={"count": failed, "error_code": "INDEX_UNAVAILABLE", "message_code": "INDEX_DEGRADED"})
        self._event(job.search_id, "index_changed_catalog_papers", "NODE_COMPLETED", "running")

    def retrieve_and_rerank(self, job: SearchJob) -> tuple[list[dict[str, Any]], bool]:
        papers = [paper for paper in self.store.list_catalog_papers(job.conference_ids, job.years)
                  if paper.index_status == "indexed"]
        try:
            ranked = self.rag.retrieve_and_rerank(job.query, papers, conference_ids=job.conference_ids, years=job.years)
            return ranked, any(item.get("rerank_score") is None for item in ranked)
        except Exception:
            fallback = CatalogRagAdapter().retrieve_and_rerank(job.query, papers)
            return fallback, True

    def freeze_search_results(self, job: SearchJob, ranked: Iterable[Mapping[str, Any]], *, degraded: bool,
                              source_results: tuple[Mapping[str, Any], Mapping[str, Any]]) -> None:
        if any(item.get("status") in {"waiting", "queued"} for item in source_results):
            self.store.create_search_job(SearchJob(
                job.search_id, job.query, job.conference_ids, job.years, "queued", GRAPH_VERSION,
                False, None, 0, job.created_at or _now(), None, None, job.expires_at, _now(),
            ))
            self._event(job.search_id, "freeze_search_results", "NODE_DEFERRED", "queued")
            return
        by_id = {item.catalog_paper_id: item for item in self.store.list_catalog_papers(job.conference_ids, job.years)
                 if item.index_status == "indexed"}
        candidates = []
        seen = set()
        for item in ranked:
            paper = by_id.get(str(item.get("catalog_paper_id")))
            # A missing abstract must not discard an accepted paper: USENIX
            # listing pages carry no abstract, so requiring one dropped every
            # catalog entry and left the user with an empty result set. The
            # abstract is surfaced as ``abstract_status`` for the UI instead.
            if paper is None or paper.catalog_paper_id in seen:
                continue
            seen.add(paper.catalog_paper_id)
            candidates.append((paper, item))
        def stable_key(pair):
            paper, item = pair
            year = paper.year if paper.year is not None else -1
            return (-float(item.get("final_score", 0) or 0),
                    -float(item.get("retrieval_score", 0) or 0), -year,
                    paper.normalized_title or normalize_title(paper.title), paper.catalog_paper_id)
        candidates.sort(key=stable_key)
        rows: list[SearchResult] = []
        for rank, (paper, item) in enumerate(candidates, 1):
            snapshot = {"catalog_paper_id": paper.catalog_paper_id, "rank": rank, "title": paper.title,
                        "authors": paper.authors, "year": paper.year, "conference_id": paper.conference_id,
                        "conference_name": "USENIX Security", "abstract": paper.abstract, "keywords": paper.keywords,
                        "abstract_status": "missing" if not paper.abstract else "available",
                        "doi": paper.doi, "publication_stage": paper.publication_stage,
                        "source_page_url": paper.official_page_url,
                        "source_kinds": self.store.get_catalog_source_kinds(paper.catalog_paper_id)
                        if hasattr(self.store, "get_catalog_source_kinds") else ["usenix"],
                        "retrieval_score": float(item.get("retrieval_score", 0) or 0),
                        "rerank_score": item.get("rerank_score"), "final_score": float(item.get("final_score", 0) or 0),
                        "existing_paper_id": None}
            rows.append(SearchResult(job.search_id, paper.catalog_paper_id, rank,
                                     snapshot["retrieval_score"], snapshot["rerank_score"], snapshot["final_score"], snapshot, _now()))
        degraded_sources = sum(1 for item in source_results
                               if item.get("status") in {"failed", "partial"}
                               or item.get("error_code"))
        status = "failed" if degraded_sources == 2 and not rows else (
            "partial" if degraded_sources or degraded else "completed"
        )
        self.store.freeze_search_results(job.search_id, rows, status=status, degraded=bool(degraded or degraded_sources),
                                         error_code="SOURCES_UNAVAILABLE" if status == "failed" else None)
        self._event(job.search_id, "freeze_search_results", "NODE_COMPLETED", status)

    def finalize_job(self, job: SearchJob) -> None:
        status = self.store.get_search_job(job.search_id).status if self.store.get_search_job(job.search_id) else "completed"
        self._event(job.search_id, "finalize_job", "JOB_COMPLETED" if status in {"completed", "partial", "failed"} else "JOB_DEFERRED", status)


def reset_running_job_ids(store: Any) -> list[str]:
    """Make interrupted jobs retryable and return exactly those job IDs.

    The ID list is captured in the same transaction as the status update so a
    startup scheduler can submit the jobs it actually recovered rather than
    guessing from a later, potentially larger queued set.
    """
    now = _now()
    with store._connect() as connection:
        connection.execute("BEGIN")
        rows = connection.execute(
            "SELECT search_id FROM search_jobs WHERE status='running' ORDER BY created_at"
        ).fetchall()
        cursor = connection.execute(
            "UPDATE search_jobs SET status='queued', started_at=NULL, updated_at=? WHERE status='running'", (now,)
        )
        # Keep the update/count assertion close to the transaction for stores
        # with unusual row-factory implementations; returned IDs are canonical.
        if cursor.rowcount != len(rows):
            raise RuntimeError("running search recovery count changed during update")
        return [str(row[0]) for row in rows]


def reset_running_jobs(store: Any, *, return_search_ids: bool = False) -> int | list[str]:
    """Make jobs from a previous process retryable on startup.

    Existing callers receive the historical integer count.  New schedulers can
    opt into the safe ID list without breaking those callers.
    """
    search_ids = reset_running_job_ids(store)
    return search_ids if return_search_ids else len(search_ids)


__all__ = [
    "CatalogRagAdapter", "CatalogSearchGraph", "GRAPH_VERSION", "NODE_NAMES",
    "reset_running_jobs", "reset_running_job_ids",
]
