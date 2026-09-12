"""search_catalog 检索适配器（Spec027 §复用接缝（强制）的唯一出口）。

search_catalog WorkItem **只能**调用 Spec015 既有能力（``CatalogSearchGraph`` /
``CatalogRagAdapter``）。本适配器是那个「唯一出口」：

- 构造时若未注入 ``searcher``，则首次 ``search()`` 时**惰性**装配 Spec015（函数体内
  延迟 import，避免模块顶层就拉起 qdrant/langgraph/knowledge_base 等重依赖），并把
  装配结果缓存到 ``self._searcher``。
- 装配或检索抛异常一律不冒泡：返回 ``SearchOutcome((), 0, degraded=True,
  error_code="SOURCE_UNAVAILABLE")``。双源无缓存且失败时由上层把任务收敛为 failed，
  027 不伪造结果。

简化决定（Task03）：``accepted_source`` / ``dblp_source`` 的真实装配需要网络与浏览器，
属 api 层（entry.py）组合职责；Task03 只冻结「接缝与调用形态」，真实数据源由后续批次
注入。因此当没有注入外部数据源时，闭包退化为只用 ``CatalogRagAdapter`` 对既有目录做
召回。

**已知限制（与事实一致，勿照旧文档理解）**：未注入数据源时该分支调用
``rag.retrieve_and_rerank(query=..., papers=[])``，而既有实现
（``paper_discovery/application/catalog_search_graph.py`` 先按 ``papers`` 建
``catalog_ids`` 索引表，再对每个 hit 做 ``catalog_ids.get(...)``，取不到即 ``continue``）
在 ``papers=[]`` 时**必然**丢弃全部命中、返回空列表。故 Task03 默认路径（``entry.py``
不注入真实数据源）**恒**返回 ``degraded=True, error_code="SOURCE_DEGRADED"``，即真实应用
路径下每个研究任务 0 入选、以 ``partial`` 收尾——这是**正确的降级语义**，不是缺陷，但
真实数据源必须由后续批次经 ``entry.py`` 注入后才能产生入选论文。

论文元数据（title/abstract/authors 等）一律不进入 research 的任何结构，检索结果只携带
``catalog_paper_id``（Spec027 复用接缝）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional, Tuple
from uuid import uuid4


@dataclass(frozen=True)
class SearchRequest:
    query: str
    facets: Tuple[str, ...] = ()
    sources: Tuple[str, ...] = ()
    max_results: int = 20
    language: Optional[str] = None


@dataclass(frozen=True)
class SearchOutcome:
    catalog_paper_ids: Tuple[str, ...]
    count: int
    degraded: bool
    error_code: Optional[str]   # "SOURCE_DEGRADED" | "SOURCE_UNAVAILABLE" | None


class CatalogSearchUnavailable(RuntimeError):
    """检索源不可用（code ∈ {"SOURCE_UNAVAILABLE", "SOURCE_DEGRADED"}）。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CatalogSearchAdapter:
    """search_catalog WorkItem 的唯一检索出口：只经 Spec015 CatalogSearchGraph / CatalogRagAdapter。"""

    def __init__(self, *, searcher: Optional[Callable[[SearchRequest], SearchOutcome]] = None,
                 store=None, rag=None, accepted_source=None, dblp_source=None) -> None:
        self._searcher = searcher
        self._store = store
        self._rag = rag
        # 真实数据源（accepted_source / dblp_source）由后续批次在 entry.py 注入；
        # Task03 默认 None，闭包据此退化为对既有目录的 RAG 召回（见 _build_spec015_searcher）。
        self._accepted_source = accepted_source
        self._dblp_source = dblp_source

    def search(self, *, query: str, facets: Optional[Iterable[str]] = None,
               sources: Optional[Iterable[str]] = None, max_results: int = 20,
               language: Optional[str] = None) -> SearchOutcome:
        request = SearchRequest(
            query=query,
            facets=tuple(facets or ()),
            sources=tuple(sources or ()),
            max_results=max(1, min(int(max_results), 100)),
            language=language,
        )
        # 惰性装配：首次调用才拉起 Spec015 重依赖，并缓存结果。
        if self._searcher is None:
            self._searcher = self._build_spec015_searcher()
        try:
            outcome = self._searcher(request)
        except Exception:
            # 装配或检索失败：不冒泡。双源无缓存且失败时由上层把任务收敛为 failed，
            # 027 不伪造结果（见模块 docstring）。
            return SearchOutcome((), 0, degraded=True, error_code="SOURCE_UNAVAILABLE")
        if outcome.degraded and not outcome.error_code:
            return SearchOutcome(outcome.catalog_paper_ids, outcome.count, degraded=True,
                                  error_code="SOURCE_DEGRADED")
        return outcome

    def _build_spec015_searcher(self) -> Callable[[SearchRequest], SearchOutcome]:
        """复用接缝锚点：真正装配 Spec015 CatalogSearchGraph / CatalogRagAdapter。

        函数体内**延迟 import** Spec015，避免模块顶层就拉起重依赖。返回的闭包是
        search_catalog 的唯一出口。
        """
        from backend.app.paper_discovery.application.catalog_search_graph import (
            CatalogRagAdapter,
            CatalogSearchGraph,
        )
        from backend.app.paper_discovery.domain.paper_discovery import SearchJob
        from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore

        ttl_seconds = 86400

        def _searcher(request: SearchRequest) -> SearchOutcome:
            store = self._store or PaperDiscoveryStore()
            rag = self._rag or CatalogRagAdapter()
            # 数据源未注入（Task03 冻结接缝）：退化为对既有目录的 RAG 召回，
            # 绝不自建第二套检索。
            #
            # 注意（已知限制，行为保持不变）：`papers=[]` 时既有 `CatalogRagAdapter` 的
            # `catalog_ids` 索引表为空，全部 hit 会被 `continue` 丢弃 → 恒返回空 →
            # 恒走下面的 `SOURCE_DEGRADED`。真实数据源需由后续批次经 `entry.py` 注入。
            if self._accepted_source is None and self._dblp_source is None:
                ranked = rag.retrieve_and_rerank(query=request.query, papers=[])
                ids = tuple(r.get("catalog_paper_id") for r in ranked)[: request.max_results]
                if ids:
                    return SearchOutcome(ids, len(ids), degraded=False, error_code=None)
                return SearchOutcome((), 0, degraded=True, error_code="SOURCE_DEGRADED")
            # 有真实数据源：走完整 CatalogSearchGraph 九节点（数据源由 entry.py 注入）。
            now = datetime.now(timezone.utc).replace(microsecond=0)
            expires_at = now + timedelta(seconds=ttl_seconds)
            now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
            expires_iso = expires_at.isoformat(timespec="seconds").replace("+00:00", "Z")
            job = SearchJob(
                search_id=uuid4().hex,
                query=request.query,
                conference_ids=["usenix-security"],
                years=[],
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
            graph = CatalogSearchGraph(
                store=store,
                accepted_source=self._accepted_source,
                dblp_source=self._dblp_source,
                rag=rag,
            )
            graph.run(job.search_id)
            results = store.get_search_results(job.search_id)
            ids = tuple(r.catalog_paper_id for r in results)[: request.max_results]
            return SearchOutcome(
                ids,
                len(results),
                degraded=bool(getattr(job, "degraded", False)),
                error_code=None,
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
