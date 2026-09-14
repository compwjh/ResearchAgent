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

设计原则：
- 重活（DBLP 源、Qdrant、下载器）全部复用既有函数，这里只做「参数映射 + 结果摘要 + 失败降级」。
- 任意异常都转成 ``DispatchResult(ok=False, error=...)``，由编排器回灌模型并继续对话，
  绝不因单个工具失败中断整轮（符合 Task02 的「失败降级」约束）。
- 重型依赖在适配器内部惰性 import，保证模块可被安全 import（不影响 ``import app``）。
"""

from __future__ import annotations

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

    source_hint = str(args.get("source", "all")).lower()
    query = str(args.get("query", "")).strip()
    years = args.get("years") or None
    limit = args.get("limit")
    publication_scope = str(args.get("publication_scope", "all"))

    service = _build_paper_search_service()
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
    lines = []
    for index, candidate in enumerate(candidates, start=1):
        title = getattr(candidate, "title", "")
        if not title:
            continue
        lines.append(f"{index}. {title}")
        # ``PaperCandidate.candidate_id`` is the existing stable catalog
        # identity (derived by PaperDiscoverySearchService and persisted as
        # the candidate key).  Expose it under the Spec034 contract name so
        # Search Worker can carry real candidates forward without serializing
        # the whole candidate object or introducing a second ID generator.
        catalog_paper_id = (
            getattr(candidate, "catalog_paper_id", None)
            or getattr(candidate, "candidate_id", None)
        )
        if catalog_paper_id:
            lines.append(f"   catalog_paper_id: {catalog_paper_id}")
        # 详情页 URL 只取自候选对象本身（优先 article_url，回退 source_page_url），
        # 绝不拼接 / 猜测；两个都缺失时该行不输出，让模型知道该篇无法补摘要。
        detail_url = getattr(candidate, "article_url", None) or getattr(candidate, "source_page_url", None)
        if detail_url:
            lines.append(f"   详情页: {detail_url}")
        abstract = str(getattr(candidate, "abstract", "") or "").strip()
        if abstract:
            lines.append(f"   摘要: {abstract}")
        else:
            lines.append("   摘要: （缺失，可对该篇详情页调用 fetch_paper_detail 补齐）")
    body = f"检索完成：来源={getattr(chosen, 'short_name', '?')}，命中 {count} 篇候选论文。\n" + "\n".join(lines)
    return DispatchResult(ok=True, name="search_paper_catalog", output=body)


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


_ADAPTERS: Dict[str, DispatchFn] = {
    "search_paper_catalog": _search_catalog,
    "download_and_import_paper": _download_import,
    "fetch_paper_detail": _fetch_paper_detail,
    "kb_search": _kb_search,
    "kb_ask": _kb_ask,
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
