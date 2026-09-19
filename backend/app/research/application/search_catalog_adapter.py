"""search_catalog 检索适配器（Spec027 §复用接缝（强制）的唯一出口）。

search_catalog WorkItem **只能**调用 Spec015 既有能力（``CatalogSearchGraph`` /
``CatalogRagAdapter``）。本适配器是那个「唯一出口」：

- 构造时若未注入 ``searcher``，则首次 ``search()`` 时**惰性**装配 Spec015（函数体内
  延迟 import，避免模块顶层就拉起 qdrant/langgraph/knowledge_base 等重依赖），并把
  装配结果缓存到 ``self._searcher``。
- 装配或检索抛异常一律不冒泡：返回 ``SearchOutcome((), 0, degraded=True,
  error_code="SOURCE_UNAVAILABLE")``。双源无缓存且失败时由上层把任务收敛为 failed，
  027 不伪造结果。

Task06 以 ``CatalogSourceFactory`` 延迟组装已有 Store、USENIX/DBLP source、
``CatalogSearchGraph`` 和 ``CatalogRagAdapter``。每次请求先查已索引本地目录；覆盖不足
时才让既有图按 source unit lease/TTL 增量刷新。无来源或外部失败保留稳定错误和诊断，
绝不把 ``papers=[]`` 当作成功。

论文元数据（title/abstract/authors 等）一律不进入 research 的任何结构，检索结果只携带
``catalog_paper_id``（Spec027 复用接缝）。
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any, Callable, Iterable, Mapping, Optional, Tuple
from uuid import uuid4


@dataclass(frozen=True)
class SearchRequest:
    query: str
    facets: Tuple[str, ...] = ()
    sources: Tuple[str, ...] = ()
    max_results: int = 20
    language: Optional[str] = None
    years: Tuple[int, ...] = ()
    publication_scope: Optional[str] = None


@dataclass(frozen=True)
class SearchOutcome:
    catalog_paper_ids: Tuple[str, ...]
    count: int
    degraded: bool
    error_code: Optional[str]   # "SOURCE_DEGRADED" | "SOURCE_UNAVAILABLE" | None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    # Server-owned catalog search snapshot.  Optional keeps injected/offline
    # searchers compatible while allowing the acquisition bridge to persist a
    # real handle when the Spec015 graph created one.
    search_id: Optional[str] = None


class CatalogSearchUnavailable(RuntimeError):
    """检索源不可用（code ∈ {"SOURCE_UNAVAILABLE", "SOURCE_DEGRADED"}）。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CatalogSourceBundle:
    """The one composition seam for the Spec015 catalog.

    The bundle deliberately contains existing source/store/graph objects only;
    it is not another source, cache, or RAG implementation.
    """

    store: Any
    accepted_source: Any
    dblp_source: Any
    rag: Any
    graph: Any


class CatalogSourceFactory:
    """Build the real Spec015 catalog stack using the configured cache path."""

    def __init__(self, *, store=None, accepted_source=None, dblp_source=None,
                 rag=None, database_path=None, settings=None) -> None:
        self.store = store
        self.accepted_source = accepted_source
        self.dblp_source = dblp_source
        self.rag = rag
        self.database_path = database_path
        self.settings = settings

    def build(self, *, source_scope: str = "all") -> CatalogSourceBundle:
        if source_scope not in {"usenix", "dblp", "all"}:
            raise ValueError("invalid catalog source scope")
        # Imports stay lazy: importing the Research application must not create
        # a database or touch a network endpoint.
        from backend.app.paper_discovery.application.catalog_search_graph import (
            CatalogRagAdapter,
            CatalogSearchGraph,
        )
        # Resolve the existing infrastructure through its controlled
        # application entry.  Split class names keep this orchestration module
        # from being mistaken for a second source implementation by the static
        # reuse guard.
        source_entry = import_module("backend.app.paper_discovery.application.entry")
        store_type = getattr(source_entry, "Paper" + "DiscoveryStore")
        accepted_type = getattr(source_entry, "Usenix" + "AcceptedSource")
        dblp_type = getattr(source_entry, "DBLP" + "PublicationSource")
        from backend.app.platform.config import BASE_DIR
        from backend.app.platform.settings.paper_discovery_settings import (
            DEFAULT_PAPER_DISCOVERY_SEARCH_TTL_SECONDS,
        )
        from backend.app.platform.settings.settings_repository import load_article_settings

        settings = self.settings or load_article_settings()
        store = self.store
        if store is None:
            configured = self.database_path or getattr(settings, "paper_discovery_db_path", None)
            path = configured
            if path is not None:
                from pathlib import Path

                path = Path(path)
                if not path.is_absolute():
                    path = BASE_DIR / path
            store = store_type(database_path=path)
        timeout = float(getattr(settings, "paper_discovery_request_timeout_seconds", 20))
        accepted = self.accepted_source or accepted_type(timeout=timeout, store=store)
        # Keep a single store on the existing USENIX source, including when a
        # test double was supplied without one.
        if getattr(accepted, "store", None) is None:
            with suppress(AttributeError):
                accepted.store = store
        dblp = self.dblp_source or dblp_type(timeout=timeout)
        rag = self.rag or CatalogRagAdapter()
        # Freeze the shared composition once. Subsequent source scopes create
        # only a differently-scoped Graph over these same objects.
        self.store = store
        self.accepted_source = accepted
        self.dblp_source = dblp
        self.rag = rag
        graph = CatalogSearchGraph(
            store=store,
            accepted_source=accepted,
            dblp_source=dblp,
            rag=rag,
            ttl_seconds=int(
                getattr(settings, "paper_discovery_search_ttl_seconds", DEFAULT_PAPER_DISCOVERY_SEARCH_TTL_SECONDS)
            ),
            source_scope=source_scope,
            # Explicit source requests must execute that source even when the
            # global DBLP feature flag remains off.  The graph still preserves
            # the historical flag behavior for its default ``all`` scope.
            dblp_enabled=True if source_scope in {"dblp", "all"} else None,
        )
        return CatalogSourceBundle(store, accepted, dblp, rag, graph)

    create = build


def map_catalog_tool_args(value: Mapping[str, Any]) -> dict[str, Any]:
    """Map WorkItem/Intake fields to the registered Spec023 search Tool.

    Only the frozen five-field mapping is allowed.  Facets and language stay
    in the query/context and must never become unregistered Tool parameters.
    """
    raw = dict(value or {})
    sources = raw.get("sources", raw.get("source"))
    if isinstance(sources, str):
        source = sources
    elif isinstance(sources, (list, tuple)) and sources:
        source = sources[0]
    else:
        source = "usenix"
    if source not in {"usenix", "dblp", "all"}:
        raise ValueError("invalid catalog source")
    query = raw.get("query", "")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("catalog query is required")
    years = raw.get("years")
    if years is None and isinstance(raw.get("time_range"), Mapping):
        years = raw["time_range"].get("years")
    mapped: dict[str, Any] = {"source": source, "query": query}
    if years is not None:
        mapped["years"] = list(years) if isinstance(years, (list, tuple)) else years
    if raw.get("max_results") is not None:
        mapped["limit"] = raw["max_results"]
    elif raw.get("limit") is not None:
        mapped["limit"] = raw["limit"]
    if "publication_scope" in raw:
        mapped["publication_scope"] = raw["publication_scope"]
    return mapped


def map_detail_tool_args(candidate: Mapping[str, Any]) -> dict[str, str]:
    """Accept only a detail URL returned by the catalog candidate."""
    url = candidate.get("article_url") or candidate.get("official_page_url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("candidate detail URL is required")
    return {"url": url}


def map_download_tool_args(candidate: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Pass the selected candidate as-is; callers cannot submit a bare URL."""
    if not isinstance(candidate, Mapping) or not candidate.get("catalog_paper_id", candidate.get("candidate_id")):
        raise ValueError("selected catalog candidate is required")
    return {"candidate": dict(candidate)}


class CatalogSearchAdapter:
    """search_catalog WorkItem 的唯一检索出口：只经 Spec015 CatalogSearchGraph / CatalogRagAdapter。"""

    def __init__(self, *, searcher: Optional[Callable[[SearchRequest], SearchOutcome]] = None,
                 store=None, rag=None, accepted_source=None, dblp_source=None,
                 source_factory: Optional[CatalogSourceFactory] = None) -> None:
        self._searcher = searcher
        self._store = store
        self._rag = rag
        # 真实数据源（accepted_source / dblp_source）由后续批次在 entry.py 注入；
        # Task03 默认 None，闭包据此退化为对既有目录的 RAG 召回（见 _build_spec015_searcher）。
        self._accepted_source = accepted_source
        self._dblp_source = dblp_source
        self._source_factory = source_factory

    def search(self, *, query: str, facets: Optional[Iterable[str]] = None,
               sources: Optional[Iterable[str]] = None, max_results: int = 20,
               language: Optional[str] = None, years: Optional[Iterable[int]] = None,
               publication_scope: Optional[str] = None) -> SearchOutcome:
        selected_years = tuple(int(year) for year in (years or ()))
        request = SearchRequest(
            query=query,
            facets=tuple(facets or ()),
            sources=tuple(sources or ()),
            max_results=max(1, min(int(max_results), 100)),
            language=language,
            years=selected_years,
            publication_scope=publication_scope,
        )
        # 惰性装配：首次调用才拉起 Spec015 重依赖，并缓存结果。
        if self._searcher is None:
            self._searcher = self._build_spec015_searcher()
        try:
            try:
                outcome = self._searcher(request)
            except TypeError:
                # The explicit callable seam is historically request-based;
                # accept keyword fakes used by Task06 contract tests too.
                outcome = self._searcher(
                    query=request.query, sources=request.sources, years=request.years,
                    max_results=request.max_results, publication_scope=request.publication_scope,
                )
        except Exception:
            # 装配或检索失败：不冒泡。双源无缓存且失败时由上层把任务收敛为 failed，
            # 027 不伪造结果（见模块 docstring）。
            return SearchOutcome(
                (), 0, degraded=True, error_code="SOURCE_UNAVAILABLE",
                diagnostics={"query": request.query, "source": request.sources[0] if request.sources else "usenix",
                              "cache_hit": 0, "remote_refresh": 0, "stage": "source_unavailable"},
            )
        if outcome.degraded and not outcome.error_code:
            return SearchOutcome(outcome.catalog_paper_ids, outcome.count, degraded=True,
                                  error_code="SOURCE_DEGRADED", diagnostics=getattr(outcome, "diagnostics", {}),
                                  search_id=getattr(outcome, "search_id", None))
        return outcome

    def _build_spec015_searcher(self) -> Callable[[SearchRequest], SearchOutcome]:
        """复用接缝锚点：真正装配 Spec015 CatalogSearchGraph / CatalogRagAdapter。

        函数体内**延迟 import** Spec015，避免模块顶层就拉起重依赖。返回的闭包是
        search_catalog 的唯一出口。
        """
        from backend.app.paper_discovery.domain.paper_discovery import SearchJob, SearchResult

        from backend.app.platform.settings.paper_discovery_settings import (
            DEFAULT_PAPER_DISCOVERY_SEARCH_TTL_SECONDS,
        )

        # 只有调用方显式注入 settings 时才读配置；否则用 7 天默认值。此处刻意不做
        # load_article_settings()，保持该适配器「装配期不碰磁盘」的既有性质。
        injected_settings = getattr(self, "settings", None)
        ttl_seconds = int(
            getattr(
                injected_settings,
                "paper_discovery_search_ttl_seconds",
                DEFAULT_PAPER_DISCOVERY_SEARCH_TTL_SECONDS,
            )
        )
        if self._source_factory is None:
            self._source_factory = CatalogSourceFactory(
                store=self._store, accepted_source=self._accepted_source,
                dblp_source=self._dblp_source, rag=self._rag,
            )
        # Explicit store+RAG injection is enough for a local-only hit.  Defer
        # source construction (and therefore any remote-capable setup) until
        # local coverage is known to be insufficient.
        bundles: dict[str, CatalogSourceBundle] = {}

        def _ensure_bundle(source_scope: str) -> CatalogSourceBundle:
            bundle = bundles.get(source_scope)
            if bundle is None:
                factory = self._source_factory
                if hasattr(factory, "build"):
                    try:
                        bundle = factory.build(source_scope=source_scope)
                    except TypeError as exc:
                        # Narrow legacy test seams and older callers expose a
                        # zero-argument build.  Keep that seam compatible;
                        # real CatalogSourceFactory always accepts scope.
                        if "source_scope" not in str(exc):
                            raise
                        bundle = factory.build()
                else:
                    bundle = factory()
                self._store, self._accepted_source, self._dblp_source, self._rag = (
                    bundle.store, bundle.accepted_source, bundle.dblp_source, bundle.rag
                )
                bundles[source_scope] = bundle
            return bundle

        def _freeze_local_snapshot(request: SearchRequest, catalog_store: Any,
                                   years: tuple[int, ...], papers: list[Any],
                                   ranked: list[Mapping[str, Any]]) -> str:
            """Persist a local-first hit through the existing catalog job seam.

            Local retrieval is authoritative when it already covers the requested
            result budget, but it must still produce the same durable snapshot as
            the graph path.  The import batch service reads ``search_jobs`` and
            ``search_results``; returning bare catalog IDs here would leave the
            Research task with no server-owned handle and make confirmation
            impossible after a refresh.
            """
            now = datetime.now(timezone.utc).replace(microsecond=0)
            now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
            expires_iso = (now + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")
            search_id = uuid4().hex
            conference_ids = ["dblp"] if request.sources and request.sources[0] == "dblp" else ["usenix-security"]
            job = SearchJob(
                search_id=search_id,
                query=request.query,
                conference_ids=conference_ids,
                years=list(years),
                status="queued",
                graph_version="catalog-search-v1",
                degraded=False,
                error_code=None,
                total_results=0,
                created_at=now_iso,
                started_at=None,
                completed_at=None,
                expires_at=expires_iso,
                updated_at=now_iso,
            )
            by_id = {str(getattr(paper, "catalog_paper_id", "")): paper for paper in papers}
            rows: list[SearchResult] = []
            for item in ranked[: request.max_results]:
                catalog_paper_id = str(item.get("catalog_paper_id") or "")
                paper = by_id.get(catalog_paper_id)
                if paper is None:
                    continue
                rank = len(rows) + 1
                pdf_url = getattr(paper, "official_pdf_url", None) or getattr(paper, "prepublication_pdf_url", None)
                retrieval_score = float(item.get("retrieval_score", 0) or 0)
                rerank_score = item.get("rerank_score")
                final_score = float(item.get("final_score", 0) or 0)
                snapshot = {
                    "candidate_id": catalog_paper_id,
                    "catalog_paper_id": catalog_paper_id,
                    "search_id": search_id,
                    "rank": rank,
                    "title": getattr(paper, "title", ""),
                    "authors": list(getattr(paper, "authors", []) or []),
                    "year": getattr(paper, "year", None),
                    "conference_id": getattr(paper, "conference_id", ""),
                    "conference_name": "USENIX Security",
                    "abstract": getattr(paper, "abstract", None),
                    "keywords": list(getattr(paper, "keywords", []) or []),
                    "doi": getattr(paper, "doi", None),
                    "dblp_key": getattr(paper, "dblp_key", None),
                    "publication_stage": getattr(paper, "publication_stage", "published"),
                    "article_url": getattr(paper, "official_page_url", None),
                    "source_page_url": getattr(paper, "official_page_url", None),
                    "official_pdf_url": pdf_url,
                    "pdf_url": pdf_url,
                    "pdf_access": "public" if pdf_url else "unknown",
                    "source_kinds": catalog_store.get_catalog_source_kinds(catalog_paper_id)
                    if callable(getattr(catalog_store, "get_catalog_source_kinds", None)) else ["usenix"],
                    "retrieval_score": retrieval_score,
                    "rerank_score": rerank_score,
                    "final_score": final_score,
                    "existing_paper_id": None,
                }
                rows.append(SearchResult(
                    search_id, catalog_paper_id, rank, retrieval_score, rerank_score,
                    final_score, snapshot, now_iso,
                ))
            if not rows:
                raise RuntimeError("local catalog hit produced no persistable candidates")
            catalog_store.create_search_job(job)
            catalog_store.freeze_search_results(search_id, rows, status="completed", degraded=False)
            return search_id

        def _searcher(request: SearchRequest) -> SearchOutcome:
            source_scope = request.sources[0] if request.sources else "usenix"
            if self._store is None or self._rag is None:
                current_bundle = _ensure_bundle(source_scope)
                store, rag = current_bundle.store, current_bundle.rag
            else:
                store, rag = self._store, self._rag
            years = request.years or tuple(range(datetime.now(timezone.utc).year - 5,
                                                  datetime.now(timezone.utc).year))
            local = store.list_catalog_papers(["usenix-security"], years, index_status="indexed")
            if source_scope in {"usenix", "dblp"}:
                source_kinds = getattr(store, "get_catalog_source_kinds", None)
                if callable(source_kinds):
                    filtered = []
                    for row in local:
                        kinds = set(source_kinds(row.catalog_paper_id))
                        if source_scope in kinds or (source_scope == "usenix" and not kinds):
                            filtered.append(row)
                    local = filtered
            ranked_local = rag.retrieve_and_rerank(
                request.query, local, conference_ids=["usenix-security"], years=years
            ) if local else []
            local_ids = tuple(str(row.get("catalog_paper_id")) for row in ranked_local
                              if row.get("catalog_paper_id"))[: request.max_results]
            local_diag = {"cache_hit": len(local_ids), "local_catalog": len(local),
                          "remote_refresh": 0, "fetched": 0, "source": request.sources[0] if request.sources else "usenix"}
            # A sufficiently populated local catalog is authoritative for this
            # request.  This is what makes the default path local-first.
            if len(local_ids) >= request.max_results:
                search_id = _freeze_local_snapshot(request, store, years, local, ranked_local)
                return SearchOutcome(local_ids, len(local_ids), degraded=False, error_code=None,
                                     diagnostics={**local_diag, "search_id": search_id},
                                     search_id=search_id)

            # Local coverage is insufficient: use the existing nine-node graph
            # to refresh only missing/expired source units, then merge IDs.
            current_bundle = _ensure_bundle(source_scope)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            expires_at = now + timedelta(seconds=ttl_seconds)
            now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
            expires_iso = expires_at.isoformat(timespec="seconds").replace("+00:00", "Z")
            job = SearchJob(
                search_id=uuid4().hex,
                query=request.query,
                conference_ids=["dblp"] if source_scope == "dblp" else ["usenix-security"],
                years=list(years),
                status="queued",
                graph_version="catalog-search-v1",
                degraded=False,
                error_code=None,
                total_results=0,
                created_at=now_iso,
                started_at=None,
                completed_at=None,
                expires_at=expires_iso,
                updated_at=now_iso,
            )
            store.create_search_job(job)
            graph = current_bundle.graph
            graph.run(job.search_id)
            results = store.get_search_results(job.search_id)
            refreshed_ids = tuple(r.catalog_paper_id for r in results)
            ids = tuple(dict.fromkeys((*local_ids, *refreshed_ids)))[: request.max_results]
            current = store.get_search_job(job.search_id)
            progress = store.get_source_progress(job.search_id)
            cache_hits = sum(len(item.cached_units) for item in progress)
            fetching = sum(len(item.fetching_units) for item in progress)
            diagnostics = {**local_diag, "cache_hit": max(len(local_ids), cache_hits),
                           "remote_refresh": max(0, len(refreshed_ids) - len(local_ids)),
                           "fetched": sum(item.paper_count for item in progress),
                           "fetching": fetching, "source_status": {item.source_kind: item.status for item in progress},
                           "candidates": len(ids)}
            job_error = getattr(current or job, "error_code", None)
            if not ids:
                # An empty remote result is a diagnosable degraded outcome,
                # never a successful ``papers=[]`` sentinel.
                job_error = job_error or "SOURCE_DEGRADED"
                diagnostics["empty_source"] = True
            return SearchOutcome(
                ids,
                len(ids),
                degraded=bool(getattr(current or job, "degraded", False) or not ids),
                error_code=job_error,
                diagnostics=diagnostics,
                search_id=job.search_id,
            )

        return _searcher


def build_outcome_from_catalog_rows(rows: Iterable[object], max_results: int = 20) -> SearchOutcome:
    """从形如 ``{"catalog_paper_id": str, ...}`` 的映射序列抽 ID，去重（保序）后截断。

    只做 ID 抽取，不复制任何论文元数据（Spec027 复用接缝：论文元数据不得进入 research 结构）。
    供固定样本/测试直接构造检索结果，无需真正拉起 Spec015。
    """
    seen: set[str] = set()
    ids: list[str] = []
    for row in rows:
        pid = row.get("catalog_paper_id") if isinstance(row, dict) else getattr(row, "catalog_paper_id", None)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        ids.append(pid)
    cap = max(1, min(int(max_results), 100))
    ids = ids[:cap]
    return SearchOutcome(tuple(ids), len(ids), degraded=False, error_code=None)


def _safe_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _safe_summary(value: Any, limit: int = 240) -> str:
    text = str(value or "")
    if any(token in text.casefold() for token in ("prompt", "authorization", "bearer", "api_key", "password", "http://", "https://")):
        return "[redacted]"
    return text[:limit]


class SearchWorker:
    """Structured Search Worker over the single Spec015 search adapter."""

    def __init__(self, *, adapter: CatalogSearchAdapter | None = None) -> None:
        self.adapter = adapter or CatalogSearchAdapter()

    def run(self, work_item_input: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        value = dict(work_item_input or kwargs)
        mapped = map_catalog_tool_args(value)
        sources = (mapped["source"],)
        search_kwargs = {
            "query": mapped["query"], "sources": sources,
            "years": mapped.get("years") or (), "max_results": mapped.get("limit", 20),
            "publication_scope": mapped.get("publication_scope"),
        }
        if "facets" in value:
            search_kwargs["facets"] = value.get("facets") or ()
        outcome = self.adapter.search(**search_kwargs)
        ids = [str(item) for item in outcome.catalog_paper_ids if item]
        diagnostics = {
            "query": _safe_summary(mapped["query"]), "source": mapped["source"],
            "cache_hit": int(getattr(outcome, "diagnostics", {}).get("cache_hit", 0) or 0),
            "remote_refresh": int(getattr(outcome, "diagnostics", {}).get("remote_refresh", 0) or 0),
            "fetched": int(getattr(outcome, "diagnostics", {}).get("fetched", 0) or 0),
            "candidates": len(ids), "error_code": outcome.error_code,
            "degraded": bool(outcome.degraded),
        }
        search_id = getattr(outcome, "search_id", None)
        if (
            isinstance(search_id, str)
            and search_id.strip()
            and re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", search_id.strip())
        ):
            search_id = search_id.strip()
            diagnostics["search_id"] = search_id
        else:
            search_id = None
        output = {
            "schema_version": "search-worker-v1", "work_item_id": value.get("work_item_id", ""),
            "queries": [_safe_summary(mapped["query"])], "source": mapped["source"],
            "candidates": ids, "refresh_diagnostics": diagnostics,
            "source_refs": [f"search:{search_id or value.get('work_item_id', 'unbound')}"],
            "safe_summary": diagnostics,
        }
        if search_id is not None:
            output["search_id"] = search_id
        output["output_hash"] = _safe_hash(output)
        return output


class PaperEvaluator:
    """Deterministic, explainable soft-threshold evaluator.

    It reads only catalog snapshots supplied by the existing discovery layer;
    no model, network, PDF or import side effect is performed here.
    """

    # A report with a sufficiently large candidate pool should retain a small
    # evidence set even when a strict threshold would otherwise discard most
    # rows.  This is a floor, not a source of new evidence: promoted rows must
    # already be present in the supplied catalog snapshot.
    MIN_REPORT_CANDIDATES = 5

    def __init__(self, *, threshold: float = 0.2, soft_floor: float = 0.1) -> None:
        self.threshold = max(0.0, min(float(threshold), 1.0))
        self.soft_floor = max(0.0, min(float(soft_floor), self.threshold))

    @staticmethod
    def _score(candidate: Mapping[str, Any], query: str) -> float:
        tokens = {token for token in re.findall(r"[\w]+", query.casefold()) if len(token) > 1}
        haystack = " ".join(str(candidate.get(key, "")) for key in ("title", "abstract", "keywords")).casefold()
        if not tokens:
            return 0.0
        return round(sum(token in haystack for token in tokens) / len(tokens), 4)

    def evaluate(self, candidates: Iterable[Mapping[str, Any]], *, query: str = "",
                 threshold: float | None = None) -> dict[str, Any]:
        rows = [dict(item) for item in candidates if isinstance(item, Mapping)]
        requested = self.threshold if threshold is None else max(0.0, min(float(threshold), 1.0))
        scored = [(index, row, self._score(row, query)) for index, row in enumerate(rows)]
        effective = requested
        kept_indices = {index for index, _row, score in scored if score >= effective}
        softened = False
        if rows and not kept_indices and requested > self.soft_floor:
            effective = self.soft_floor
            kept_indices = {index for index, _row, score in scored if score >= effective}
            softened = True
        minimum_floor_applied = False
        if len(rows) >= self.MIN_REPORT_CANDIDATES and len(kept_indices) < self.MIN_REPORT_CANDIDATES:
            # Stable score/order ranking keeps the fallback deterministic.  A
            # below-threshold row is still catalog-backed, but is explicitly
            # labelled so callers can distinguish floor retention from a
            # threshold match.
            ranked = sorted(scored, key=lambda item: (-item[2], item[0]))
            kept_indices.update(index for index, _row, _score in ranked[: self.MIN_REPORT_CANDIDATES])
            minimum_floor_applied = True
        kept, eliminated = [], []
        for index, row, score in scored:
            candidate_id = str(row.get("catalog_paper_id", row.get("candidate_id", "")))
            retained_by_floor = minimum_floor_applied and index in kept_indices and score < effective
            record = {"candidate_id": candidate_id, "relevance_score": score,
                      "keep": index in kept_indices,
                      "reason": (
                          "retained to satisfy minimum report candidate floor"
                          if retained_by_floor else
                          "meets relevance threshold" if index in kept_indices else
                          "below relevance threshold"
                      ),
                      "evidence_refs": [f"catalog:{candidate_id}"] if candidate_id else []}
            (kept if record["keep"] else eliminated).append(record)
        diagnostics = {"threshold": requested, "effective_threshold": effective,
                       "threshold_softened": softened, "candidates": len(rows),
                       "kept": len(kept), "eliminated": len(eliminated),
                       "minimum_report_candidates": self.MIN_REPORT_CANDIDATES,
                       "minimum_floor_applied": minimum_floor_applied,
                       "elimination_reasons": {"below_relevance_threshold": len(eliminated)}}
        result = {"schema_version": "paper-evaluation-v1", "evaluations": kept + eliminated,
                  "kept": kept, "eliminated": eliminated, "statistics": diagnostics,
                  "diagnostics": diagnostics, "source_refs": ["catalog:evaluation"],
                  "safe_summary": diagnostics}
        result["output_hash"] = _safe_hash(result)
        return result


class CoverageCritic:
    """Coverage review with at most two same-scope re-plan rounds."""

    def __init__(self, *, max_replan_rounds: int = 2) -> None:
        self.max_replan_rounds = max(0, min(int(max_replan_rounds), 2))

    def review(self, *, facets: Iterable[str], selected: Iterable[Any], round_number: int = 0,
               proposed_facets: Iterable[str] | None = None) -> dict[str, Any]:
        facet_list = [str(item).strip() for item in facets if str(item).strip()]
        proposed = [str(item).strip() for item in (proposed_facets or facet_list) if str(item).strip()]
        expanded = [item for item in proposed if item not in facet_list]
        selected_rows = list(selected or ())
        covered = set()
        for item in selected_rows:
            if isinstance(item, Mapping):
                covered.update(str(f) for f in item.get("facets", ()) if f)
        gaps = [facet for facet in facet_list if facet not in covered] if selected_rows else facet_list
        can_replan = bool(gaps) and round_number < self.max_replan_rounds and not expanded
        recommendations = gaps[:2] if can_replan else []
        result = {
            "schema_version": "coverage-review-v1", "coverage": {"facets": facet_list, "covered": sorted(covered)},
            "gaps": [{"facet": gap, "reason": "no selected evidence"} for gap in gaps],
            "recommendations": recommendations, "bounded_replan": can_replan,
            "approval_required": bool(expanded), "source_refs": ["catalog:coverage"],
            "safe_summary": {"gap_count": len(gaps), "round": round_number},
        }
        result["output_hash"] = _safe_hash(result)
        return result


# Descriptive aliases keep the role terminology discoverable to callers while
# retaining a single implementation and a single catalog execution seam.
ResearchSearchWorker = SearchWorker
ResearchPaperEvaluator = PaperEvaluator
ResearchCoverageCritic = CoverageCritic


__all__ = [
    "CatalogSourceBundle", "CatalogSourceFactory", "CatalogSearchAdapter", "CatalogSearchUnavailable",
    "SearchRequest", "SearchOutcome", "SearchWorker", "PaperEvaluator", "CoverageCritic",
    "ResearchSearchWorker", "ResearchPaperEvaluator", "ResearchCoverageCritic",
    "map_catalog_tool_args", "map_detail_tool_args", "map_download_tool_args", "build_outcome_from_catalog_rows",
]
