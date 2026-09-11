"""spec-023 Task07 — 真实工具执行适配器（复用既有实现，不新建第二套）。

``build_default_dispatch()`` 返回 ``(name, args) -> DispatchResult`` 的可调用对象，
按注册表工具名分派到**既有的**业务入口：

- ``search_paper_catalog``   -> ``PaperDiscoverySearchService.search``（经 common._build_paper_search_service）
- ``download_and_import_paper`` -> ``import_candidate``，allowed_hosts 复用既有
  ``_paper_candidate_hosts`` 白名单（usenix.org 同源 + 服务端配置），**不新建旁路下载器**。
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
from typing import Callable, Dict

from backend.app.skills.tool_executor import DispatchResult

logger = logging.getLogger(__name__)

DispatchFn = Callable[[dict], DispatchResult]


def _summarize(obj, limit: int = 5) -> str:
    if isinstance(obj, (list, tuple)):
        items = list(obj)[:limit]
        return "\n".join(str(x) for x in items)
    return str(obj)


# ----------------------------- 各工具适配器 ----------------------------- #

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
    # 按 source 提示挑选会议来源（best-effort；无匹配则用首个启用来源）
    chosen = None
    for c in conferences:
        short = str(getattr(c, "short_name", "")).lower()
        venue = " ".join(getattr(c, "venue_aliases", []) or []).lower()
        if source_hint == "dblp" and ("dblp" in short or "dblp" in venue):
            chosen = c
            break
        if source_hint == "usenix" and "usenix" in short:
            chosen = c
            break
    if chosen is None:
        chosen = conferences[0]

    result = service.search(
        source=chosen,
        query=query,
        years=years,
        limit=int(limit) if limit is not None else None,
        publication_scope=publication_scope,
    )
    count = len(getattr(result, "candidates", []) or [])
    titles = [getattr(c, "title", "") for c in getattr(result, "candidates", []) or []][:5]
    body = f"检索完成：来源={getattr(chosen, 'short_name', '?')}，命中 {count} 篇候选论文。\n" + "\n".join(
        f"- {t}" for t in titles if t
    )
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


_ADAPTERS: Dict[str, DispatchFn] = {
    "search_paper_catalog": _search_catalog,
    "download_and_import_paper": _download_import,
    "kb_search": _kb_search,
    "kb_ask": _kb_ask,
}


def build_default_dispatch() -> Callable[[str, dict], DispatchResult]:
    """构造默认分派器：按工具名调用既有适配器，未知工具 / 异常均安全降级。"""

    def dispatch(name: str, args: dict) -> DispatchResult:
        adapter = _ADAPTERS.get(name)
        if adapter is None:
            return DispatchResult(ok=False, name=name, error=f"未找到工具「{name}」的执行器。")
        try:
            return adapter(args)
        except Exception as exc:  # 任何执行异常都降级为错误结果，不中断对话
            logger.warning("工具 %s 执行失败，降级：%s", name, exc)
            return DispatchResult(ok=False, name=name, error=f"执行失败：{type(exc).__name__}")

    return dispatch
