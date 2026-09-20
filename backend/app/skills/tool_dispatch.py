"""spec-023 Task07 — 真实工具执行适配器（复用既有实现，不新建第二套）。

``build_default_dispatch()`` 返回 ``(name, args) -> DispatchResult`` 的可调用对象，
按注册表工具名分派到**既有的**业务入口：

- ``search_paper_catalog``   -> ``PaperDiscoverySearchService.search``（经 common._build_paper_search_service）
- ``download_and_import_paper`` -> ``import_candidate``，allowed_hosts 复用既有
  ``_paper_candidate_hosts`` 白名单（usenix.org 同源 + 服务端配置），**不新建旁路下载器**。
- ``fetch_paper_detail``     -> ``UsenixAcceptedSource.fetch_paper_detail``（复用既有
  ``_detail_url_ok`` 白名单 + ``_fetch_detail`` 限速请求 + ``parse_usenix_detail``，
  只取 HTML 详情页摘要元数据，**不下载 PDF**）
- ``kb_search``              -> ``hybrid_search``（知识库混合检索）
- ``kb_ask``                -> ``hybrid_search`` 取回片段（最终合成由编排器回灌模型完成）
- ``session_search``        -> ``session_search.search_sessions``（L2 会话检索：FTS5 检索
  历史消息 + MD 记忆笔记；索引与查询都复用 ``SessionSearchIndex`` 唯一实现）

设计原则：
- 重活（DBLP 源、Qdrant、下载器）全部复用既有函数，这里只做「参数映射 + 结果摘要 + 失败降级」。
- 任意异常都转成 ``DispatchResult(ok=False, error=...)``，由编排器回灌模型并继续对话，
  绝不因单个工具失败中断整轮（符合 Task02 的「失败降级」约束）。
- 重型依赖在适配器内部惰性 import，保证模块可被安全 import（不影响 ``import app``）。
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

from backend.app.skills.tool_executor import DispatchResult

logger = logging.getLogger(__name__)

DispatchFn = Callable[[dict], DispatchResult]

# ``search_paper_catalog`` 回灌给模型的候选条数上限：要足够多以便对摘要为空的候选
# 调 ``fetch_paper_detail`` 补齐，又不能一次塞进 20+ 篇把上下文撑爆（总数另行说明）。
_SEARCH_LIST_LIMIT = 8

# ``UsenixAcceptedSource`` owns the per-site rate-limit clock (``_next_request_at``)
# and the response cache (``self._cache``).  Building one per Tool call threw both
# away, so N calls meant N live requests with an empty sleep log - the limiter was
# effectively off and every repeat of a URL hit usenix.org again.  One lazily
# built, process-wide instance keeps that state alive across calls, while the
# heavy import stays lazy (the module must remain safe to import).
_usenix_source: Optional[Any] = None
_usenix_source_lock = threading.Lock()


def _usenix_detail_source() -> Any:
    """Return the process-wide ``UsenixAcceptedSource`` (built on first use)."""
    global _usenix_source
    if _usenix_source is None:
        with _usenix_source_lock:
            if _usenix_source is None:
                from backend.app.paper_discovery.infrastructure.usenix_publication_source import (
                    UsenixAcceptedSource,
                )

                _usenix_source = UsenixAcceptedSource()
    return _usenix_source


def _summarize(obj, limit: int = 5) -> str:
    if isinstance(obj, (list, tuple)):
        items = list(obj)[:limit]
        return "\n".join(str(x) for x in items)
    return str(obj)


# ----------------------------- 各工具适配器 ----------------------------- #

def _matches_usenix(conference) -> bool:
    """USENIX 识别：short_name / venue_aliases 含 usenix（本项目主场景来源）。"""
    short = str(getattr(conference, "short_name", "")).lower()
    venues = " ".join(str(a) for a in (getattr(conference, "venue_aliases", []) or [])).lower()
    return "usenix" in short or "usenix" in venues


def _matches_dblp(conference) -> bool:
    """DBLP 识别：short_name / venue_aliases 含 dblp。本机默认无此配置。"""
    short = str(getattr(conference, "short_name", "")).lower()
    venues = " ".join(str(a) for a in (getattr(conference, "venue_aliases", []) or [])).lower()
    return "dblp" in short or "dblp" in venues


def _pick_conference(conferences: list, source_hint: str):
    """按 source 提示明确选源。返回 (conference, error)；两者互斥。

    规则（spec-023.1 B1，禁止静默退化）：
    - ``usenix``：必须命中 USENIX 来源，否则返回可读错误（不得退到其它会议）。
    - ``dblp``  ：必须命中 dblp 来源，否则返回可读错误（本机未配置 dblp 会议时**严禁**
                  取 conferences[0]，否则会静默返回错误来源的结果）。
    - ``all``  ：明确 USENIX 优先（本项目主场景）；无 USENIX 配置时才退到首个启用来源，
                  并在结果里如实报告实际使用的来源。
    """
    if source_hint == "usenix":
        for c in conferences:
            if _matches_usenix(c):
                return c, None
        available = "、".join(str(getattr(c, "short_name", "?")) for c in conferences)
        return None, f"未找到 USENIX 来源。当前已启用的论文来源：{available}"

    if source_hint == "dblp":
        for c in conferences:
            if _matches_dblp(c):
                return c, None
        available = "、".join(str(getattr(c, "short_name", "?")) for c in conferences)
        return None, (
            "未找到 DBLP 来源：服务端未配置 dblp 会议，"
            f"不会退化为其它会议结果。当前已启用的论文来源：{available}"
        )

    # source="all"：USENIX 优先（主场景），退路仅限「本机确实没有 USENIX 配置」。
    for c in conferences:
        if _matches_usenix(c):
            return c, None
    return conferences[0], None


def _search_catalog(args: dict) -> DispatchResult:
    from backend.app.api.common import _build_paper_search_service, _paper_store
    from backend.app.paper_discovery.application.paper_discovery_search import PaperDiscoverySearchService
    # Build the legacy service up front as the dependency-injection seam.  The
    # production object is replaced by the canonical global-catalog adapter
    # below; lightweight test/embedding fakes keep the historical adapter
    # contract so callers that inject a fake do not need to implement the
    # catalog repository surface merely to exercise formatting/error paths.
    legacy_service = _build_paper_search_service()

    source_hint = str(args.get("source", "all")).lower()
    query = str(args.get("query", "")).strip()
    years = args.get("years") or None
    limit = args.get("limit")
    publication_scope = str(args.get("publication_scope", "all"))

    # Research workers use the canonical Spec015 global catalog.  The legacy
    # PaperDiscoverySearchService emits short-lived PaperCandidate IDs; using
    # it here loses the catalog row needed for report metadata and provenance.
    if source_hint in {"usenix", "all"} and isinstance(legacy_service, PaperDiscoverySearchService):
        from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter

        max_results = _SEARCH_LIST_LIMIT
        if isinstance(limit, int) and not isinstance(limit, bool):
            max_results = max(1, min(int(limit), _SEARCH_LIST_LIMIT))
        try:
            outcome = CatalogSearchAdapter().search(
                query=query,
                sources=("usenix",),
                years=tuple(int(year) for year in (years or ())),
                max_results=max_results,
                publication_scope=publication_scope,
            )
        except Exception as exc:  # noqa: BLE001 - keep Tool failure diagnosable
            logger.warning("canonical USENIX catalog search failed: %s", exc)
            return DispatchResult(ok=False, name="search_paper_catalog", error="CATALOG_SEARCH_FAILED")
        if not outcome.catalog_paper_ids:
            return DispatchResult(
                ok=False, name="search_paper_catalog",
                error=outcome.error_code or "CATALOG_NO_RESULTS", search_id=outcome.search_id,
            )
        store = _paper_store()
        papers = [
            paper for paper_id in outcome.catalog_paper_ids
            if (paper := store.get_catalog_paper(str(paper_id))) is not None
        ]
        if not papers:
            return DispatchResult(
                ok=False, name="search_paper_catalog", error="CATALOG_METADATA_UNAVAILABLE",
                search_id=outcome.search_id,
            )
        body = _format_search_body("USENIX Security（全局目录）", papers, outcome.count)
        return DispatchResult(ok=True, name="search_paper_catalog", output=body, search_id=outcome.search_id)

    # DBLP retains its existing source-specific adapter until its dedicated
    # catalog contract is enabled; it is not used by the USENIX acceptance path.
    service = legacy_service
    conferences = [c for c in _paper_store().list_conferences() if getattr(c, "enabled", True)]
    if not conferences:
        return DispatchResult(ok=False, name="search_paper_catalog", error="服务端未配置任何论文来源")
    chosen, selection_error = _pick_conference(conferences, source_hint)
    if selection_error is not None:
        # 无匹配来源 -> 可读错误，绝不拿 conferences[0] 冒充
        return DispatchResult(ok=False, name="search_paper_catalog", error=selection_error)

    result = service.search(
        source=chosen,
        query=query,
        years=years,
        limit=int(limit) if limit is not None else None,
        publication_scope=publication_scope,
    )
    count = len(getattr(result, "candidates", []) or [])
    candidates = list(getattr(result, "candidates", []) or [])[:_SEARCH_LIST_LIMIT]
    # 实时检索 0 命中：本地已索引目录兜底（复用 CatalogSearchAdapter 唯一出口）。
    # 兜底返回非空结果则直接采用；兜底自身失败 / 无命中则安全退化为原 0 条行为
    # （不把异常抛给上层、也不伪造任何论文元数据）。
    if count == 0:
        fallback = _search_catalog_local_fallback(
            query=query, years=years, limit=limit,
            publication_scope=publication_scope, source_hint=source_hint,
        )
        if fallback is not None:
            return fallback
    body = _format_search_body(getattr(chosen, "short_name", "?"), candidates, count)
    # ``PaperDiscoverySearchService`` persists this snapshot before returning;
    # carry its opaque server handle as structured metadata.  It must not be
    # embedded in the presentation text, where a model could imitate it.
    search_id = getattr(getattr(result, "session", None), "search_id", None)
    return DispatchResult(ok=True, name="search_paper_catalog", output=body, search_id=search_id)


def _format_search_entries(items: list) -> list:
    """将候选 / 目录对象归一化为展示条目；只读取既有属性，不新增任何元数据。

    同时服务于实时路径（``PaperCandidate``）与本地兜底路径（``CatalogPaper``）：
    取标题、稳定 ``catalog_paper_id``、详情页 URL（article_url→source_page_url→
    official_page_url 回退）、摘要。标题为空的对象被跳过。
    """
    entries = []
    for item in items:
        title = getattr(item, "title", "")
        if not title:
            continue
        # 稳定目录身份：优先既有 catalog_paper_id，回退 candidate_id。
        catalog_paper_id = (
            getattr(item, "catalog_paper_id", None)
            or getattr(item, "candidate_id", None)
        )
        # 详情页 URL 只取自对象本身（绝不拼接 / 猜测）；三档回退覆盖两类来源。
        detail_url = (
            getattr(item, "article_url", None)
            or getattr(item, "source_page_url", None)
            or getattr(item, "official_page_url", None)
        )
        abstract = str(getattr(item, "abstract", "") or "").strip()
        entries.append((title, catalog_paper_id, detail_url, abstract, item))
    return entries


def _format_search_body(source_name: str, items: list, count: int) -> str:
    """按既有模型消费格式拼装检索结果文本（与历史实现逐字符一致）。"""
    lines = []
    for index, (title, catalog_paper_id, detail_url, abstract, item) in enumerate(
        _format_search_entries(items), start=1
    ):
        lines.append(f"{index}. {title}")
        if catalog_paper_id:
            lines.append(f"   catalog_paper_id: {catalog_paper_id}")
        # Keep the candidate handoff bounded to the already exposed official
        # detail page.  Direct PDF/source_links fields are intentionally not
        # copied into this model-facing text; the importer can resolve the
        # server-owned PDF from the trusted page through its existing boundary.
        source_links = [detail_url] if detail_url else []
        candidate = {
            "title": title,
            "catalog_paper_id": catalog_paper_id,
            "conference_id": getattr(item, "conference_id", None),
            "year": getattr(item, "year", None),
            "source_page_url": detail_url,
            "source_links": source_links,
        }
        lines.append(
            "   candidate: "
            + json.dumps(
                {key: value for key, value in candidate.items() if value not in (None, "")},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        if detail_url:
            lines.append(f"   详情页: {detail_url}")
        if abstract:
            lines.append(f"   摘要: {abstract}")
        else:
            lines.append("   摘要: （缺失，可对该篇详情页调用 fetch_paper_detail 补齐）")
    return f"检索完成：来源={source_name}，命中 {count} 篇候选论文。\n" + "\n".join(lines)


def _search_catalog_local_fallback(*, query, years, limit, publication_scope, source_hint) -> Optional[DispatchResult]:
    """实时检索 0 命中时的本地已索引目录兜底（Spec027 复用接缝的唯一出口）。

    复用 ``CatalogSearchAdapter``（其内部只经既有 CatalogSearchGraph / CatalogRagAdapter）
    检索本地 SQLite+Qdrant 目录，命中后再用既有 ``PaperDiscoveryStore.get_catalog_paper``
    取**真实**元数据（title / 官方页 URL / 摘要）回填，绝不伪造。兜底自身抛异常或读不到
    任何真实目录行时返回 ``None``，由调用方退化为原 0 条行为（不抛 500、不伪造）。
    """
    from backend.app.api.common import _paper_store
    from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter

    max_results = _SEARCH_LIST_LIMIT
    if isinstance(limit, int) and not isinstance(limit, bool):
        max_results = max(1, min(int(limit), _SEARCH_LIST_LIMIT))

    # 与实时路径 _pick_conference 的优先级一致：dblp 显式请求才走 dblp，其余（all/usenix）走 usenix。
    source_scope = "dblp" if source_hint == "dblp" else "usenix"
    try:
        outcome = CatalogSearchAdapter().search(
            query=query,
            sources=(source_scope,),
            max_results=max_results,
            years=tuple(int(y) for y in (years or ())),
            publication_scope=publication_scope,
        )
    except Exception as exc:  # noqa: BLE001 - 兜底检索失败：安全降级，不冒泡
        logger.warning("search_paper_catalog 本地目录兜底检索失败，退化为 0 条：%s", exc)
        return None

    ids = [str(pid) for pid in (getattr(outcome, "catalog_paper_ids", ()) or ()) if pid][:max_results]
    if not ids:
        return None

    store = _paper_store()
    papers = []
    for pid in ids:
        try:
            paper = store.get_catalog_paper(pid)
        except Exception as exc:  # noqa: BLE001 - 单篇元数据读取失败不阻断其余候选
            logger.warning("search_paper_catalog 读取本地目录论文 %s 失败：%s", pid, exc)
            continue
        if paper is not None:
            papers.append(paper)
    if not papers:
        return None

    body = _format_search_body("USENIX Security（本地目录）", papers, len(papers))
    search_id = getattr(outcome, "search_id", None)
    return DispatchResult(ok=True, name="search_paper_catalog", output=body, search_id=search_id)


def _kb_search(args: dict) -> DispatchResult:
    from backend.app.knowledge_base.infrastructure.retrieve import hybrid_search

    question = str(args.get("question", "")).strip()
    top_k = args.get("top_k")
    chunker = args.get("chunker")
    hits = hybrid_search(question, top_k=top_k, chunker=chunker)
    count = len(hits)
    snippets = []
    for hit in hits[:5]:
        text = getattr(hit, "text", "") or ""
        snippets.append(f"[{getattr(hit, 'file_name', '?')} p{getattr(hit, 'page', '?')}] {text[:200]}")
    body = f"知识库检索到 {count} 段相关片段：\n" + "\n".join(snippets)
    return DispatchResult(ok=True, name="kb_search", output=body)


def _download_import(args: dict) -> DispatchResult:
    from backend.app.api.common import _paper_candidate_hosts
    from backend.app.paper_discovery.application.paper_import import import_candidate
    from backend.app.platform.settings.settings_repository import load_article_settings

    candidate = args.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("title"):
        return DispatchResult(ok=False, name="download_and_import_paper", error="候选记录缺少 title")
    # 复用既有 allowed_hosts 白名单（usenix.org 同源 + 服务端配置），不得传入任意 URL
    allowed_hosts = _paper_candidate_hosts(candidate)
    result = import_candidate(
        candidate,
        settings=load_article_settings(),
        allowed_hosts=allowed_hosts,
    )
    if getattr(result, "ok", False):
        return DispatchResult(
            ok=True,
            name="download_and_import_paper",
            output=f"已下载并导入论文：{candidate.get('title')}（{getattr(result, 'paper_id', '')}）",
        )
    code = getattr(result, "code", "") or "IMPORT_FAILED"
    from backend.app.paper_discovery.application.paper_import import safe_import_error_message

    return DispatchResult(
        ok=False,
        name="download_and_import_paper",
        error=safe_import_error_message(code),
    )


def _kb_ask(args: dict) -> DispatchResult:
    # kb_ask 语义为「基于 KB 回答」：取回片段后由编排器回灌模型合成最终回答，
    # 这里只负责检索（与 kb_search 共用既有混合检索），避免重复合成。
    return _kb_search(args)


def _fetch_paper_detail(args: dict) -> DispatchResult:
    """取单篇 USENIX 论文的详情页摘要元数据（只读 HTML，不下载 PDF）。

    复用既有公开入口 ``UsenixAcceptedSource.fetch_paper_detail``：URL 白名单
    （``_detail_url_ok``）、限速请求（``_fetch_detail``）与解析
    （``parse_usenix_detail``）都只有那一套实现，这里只做「参数校验 + 结果组织成
    模型可读文本 + 失败降级」。
    """
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return DispatchResult(
            ok=False,
            name="fetch_paper_detail",
            error=(
                "缺少必填参数 url：需为 USENIX 官方 presentation 详情页地址，形如 "
                "https://www.usenix.org/conference/<conference>/presentation/<paper>"
            ),
        )

    detail = _usenix_detail_source().fetch_paper_detail(url.strip())
    if not detail.get("ok"):
        # 保留可诊断信息（错误码 + 具体说明），与 _download_import 风格一致。
        code = detail.get("error_code") or "USENIX_DETAIL_FAILED"
        return DispatchResult(
            ok=False, name="fetch_paper_detail", error=f"{code}：{detail.get('error') or code}"
        )

    title = detail.get("title") or "（未解析到标题）"
    authors = "、".join(str(a) for a in (detail.get("authors") or [])) or "（未解析到作者）"
    year = detail.get("year") or "（未解析到年份）"
    abstract = (detail.get("abstract") or "").strip() or "（该详情页未提供摘要）"
    keywords = "、".join(str(k) for k in (detail.get("keywords") or []))
    lines = [
        f"论文详情（来源：USENIX 官方详情页 {detail.get('url') or url}）",
        f"标题：{title}",
        f"作者：{authors}",
        f"年份：{year}",
        f"摘要：{abstract}",
    ]
    if keywords:
        lines.append(f"关键词：{keywords}")
    return DispatchResult(ok=True, name="fetch_paper_detail", output="\n".join(lines))


def _session_search(args: dict) -> DispatchResult:
    """L2 会话检索：全文检索历史消息与 MD 记忆笔记。

    复用 ``memory.session_search.search_sessions``（唯一实现）；该入口自身已把
    「空查询 / 无结果 / FTS5 语法字符 / 内部异常」全部收敛为可读文本，
    因此这里不做二次包装，只透传结果。缺 ``query`` 时才判失败。
    """
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return DispatchResult(ok=False, name="session_search", error="缺少必填参数 query（检索关键词）")

    from backend.app.memory.session_search import search_sessions

    limit = args.get("limit")
    conversation_id = args.get("conversation_id")
    payload = search_sessions(
        query,
        # 非法/缺省 limit 交给 search_sessions 内部的 _clamp_limit 收敛，这里只做类型过滤。
        limit=limit if isinstance(limit, int) and not isinstance(limit, bool) else _DEFAULT_SESSION_LIMIT,
        conversation_id=str(conversation_id) if conversation_id else None,
    )
    return DispatchResult(ok=True, name="session_search", output=str(payload.get("output") or ""))


def _paper_discovery(args: dict) -> DispatchResult:
    """Execute the versioned multi-source Worker Tool facade.

    The facade owns source/URL validation and delegates all actual discovery/import
    work to the existing registry adapters and secure importer.  ``DispatchResult``
    remains backward-compatible while its output is a JSON envelope for this Tool.
    """
    from backend.app.paper_discovery.application.worker_tool import PaperDiscoveryToolFacade

    result = PaperDiscoveryToolFacade().dispatch(args)
    payload = result.to_dict()
    return DispatchResult(
        ok=result.status in {"completed", "partial"},
        name="paper_discovery",
        output=json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


_DEFAULT_SESSION_LIMIT = 10

_ADAPTERS: Dict[str, DispatchFn] = {
    "paper_discovery": _paper_discovery,
    "search_paper_catalog": _search_catalog,
    "download_and_import_paper": _download_import,
    "fetch_paper_detail": _fetch_paper_detail,
    "kb_search": _kb_search,
    "kb_ask": _kb_ask,
    "session_search": _session_search,
}


def build_default_dispatch() -> Callable[[str, dict], DispatchResult]:
    """构造默认分派器：按工具名调用既有适配器，未知工具 / 异常均安全降级。"""

    def dispatch(name: str, args: dict) -> DispatchResult:
        adapter = _ADAPTERS.get(name)
        if adapter is None:
            return DispatchResult(ok=False, name=name, error=f"未找到工具「{name}」的执行器。")
        # 预期内的业务/输入错误：保留可诊断信息（错误码 + 具体说明），不压成通用一句话。
        from backend.app.paper_discovery.application.paper_discovery_search import (
            PaperDiscoverySearchError,
        )

        try:
            return adapter(args)
        except PaperDiscoverySearchError as exc:
            # 来源未配置 / 参数非法等可定位原因：直接透传错误码与消息
            error_code = getattr(exc, "error_code", None) or getattr(exc, "code", None) or "SEARCH_INVALID"
            logger.warning("工具 %s 检索参数/来源不可用：%s", name, exc)
            return DispatchResult(ok=False, name=name, error=f"{error_code}：{exc}")
        except Exception as exc:  # 兜底：非预期异常降级为错误结果，不中断对话
            logger.warning("工具 %s 执行失败，降级：%s", name, exc)
            return DispatchResult(ok=False, name=name, error=f"执行失败：{type(exc).__name__}: {exc}")

    return dispatch
