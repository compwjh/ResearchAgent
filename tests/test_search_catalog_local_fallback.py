"""spec-030 修复 — ``search_paper_catalog`` 在实时源 0 命中时走本地已索引目录兜底（TDD，全离线）。

背景（已实证）：research 的 agent 工具路径走 ``_search_catalog``，外部实时源（DBLP/USENIX
accepted）当前不可用，返回 0 条就被当成成功，导致下游 Spec030 候选论文恒为 0。本测试锁定
兜底行为（全部用假对象隔离网络 / Qdrant / 本机 SQLite）：

1. 外部源 0 命中 -> 走本地兜底，产出非空 ``catalog_paper_id``（来自真实目录行，绝不伪造）。
2. 外部源有结果 -> 不走兜底（目录出口不得被调用）。
3. 兜底检索抛异常 -> 安全退化为 0 条且不抛（不把 500 抛给上层）。
4. 兜底返回 id、但 store 读不到对应真实行 -> 退化为 0 条，不伪造。
5. 兜底首行标注「本地目录」，且 search_id 取 adapter 返回的（有则填、无则 None）。
6. 同样输入两次调用 -> 输出逐字符一致（结果确定）。
"""

import pytest

from backend.app.paper_discovery.application.paper_discovery_search import SearchResult
from backend.app.paper_discovery.domain.paper_discovery import SearchSession
from backend.app.research.application.search_catalog_adapter import SearchOutcome
from backend.app.skills.tool_dispatch import build_default_dispatch

TOOL = "search_paper_catalog"
MAX_LISTED = 8


class _FakeConference:
    def __init__(self, conference_id, short_name, *, enabled=True, aliases=None):
        self.conference_id = conference_id
        self.name = f"{short_name} full name"
        self.short_name = short_name
        self.dblp_stream = f"conf/{conference_id}"
        self.venue_aliases = list(aliases or [])
        self.enabled = enabled


class _Paper:
    """极简目录行替身，只暴露兜底回填读取的字段。"""

    def __init__(self, pid, title, url, abstract):
        self.catalog_paper_id = pid
        self.title = title
        self.official_page_url = url
        self.abstract = abstract


class _FakeStore:
    def __init__(self, conferences, papers=None):
        self._conferences = list(conferences)
        self._papers = {p.catalog_paper_id: p for p in (papers or [])}

    def list_conferences(self):
        return sorted(self._conferences, key=lambda c: c.short_name)

    def get_catalog_paper(self, pid):
        return self._papers.get(pid)


class _FakeSearchService:
    """假实时检索服务：回放预设候选（可设 0 条以触发兜底）。"""

    def __init__(self, candidates):
        self._candidates = list(candidates)

    def search(self, source, query, years, limit, publication_scope):
        session = SearchSession(search_id="live-sid", query=query, expires_at="", created_at="")
        return SearchResult(session, list(self._candidates), [], None)


class _RecordingAdapter:
    """假 ``CatalogSearchAdapter``：记录是否被调用，并按预设返回 ``SearchOutcome``。"""

    def __init__(self, outcome, *, raise_on_search=False):
        self._outcome = outcome
        self.raise_on_search = raise_on_search
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_on_search:
            raise RuntimeError("local catalog adapter exploded")
        return self._outcome


def _fake_adapter_factory(outcome, *, raise_on_search=False):
    def factory():
        return _RecordingAdapter(outcome, raise_on_search=raise_on_search)

    return factory


@pytest.fixture
def patched(monkeypatch):
    """统一注入 fake service/store/adapter，返回 (service, adapter_holder, run)。"""

    service = _FakeSearchService([])
    papers = [
        _Paper(f"catalog-{i}", f"Local Paper {i}",
               f"https://www.usenix.org/conference/usenixsecurity24/presentation/p{i}",
               f"Abstract for local paper {i}.")
        for i in range(1, 21)
    ]
    store = _FakeStore(
        [_FakeConference("usenix-security", "USENIX Security")], papers=papers
    )
    outcome = SearchOutcome(
        tuple(p.catalog_paper_id for p in papers[:MAX_LISTED]),
        MAX_LISTED, False, None, search_id="fallback-sid",
    )
    adapter = _RecordingAdapter(outcome)

    monkeypatch.setattr(
        "backend.app.api.common._build_paper_search_service", lambda: service
    )
    monkeypatch.setattr("backend.app.api.common._paper_store", lambda: store)
    monkeypatch.setattr(
        "backend.app.research.application.search_catalog_adapter.CatalogSearchAdapter",
        lambda: adapter,
    )

    def run(candidates, **args):
        service._candidates = list(candidates)
        return build_default_dispatch()(TOOL, {"source": "usenix", "query": "security", **args})

    return service, adapter, run


# --- 1. 实时 0 命中 -> 本地兜底产出非空 catalog_paper_id -----------------------


def test_zero_live_hits_uses_local_fallback(patched):
    _service, adapter, run = patched

    result = run([])  # 0 条实时候选 -> 触发兜底

    assert result.ok is True, result.error
    assert adapter.calls, "实时 0 命中必须调用本地目录出口"
    assert "USENIX Security（本地目录）" in result.output, "首行必须标注本地目录来源"
    # 兜底只取真实目录行、绝不伪造：catalog_paper_id 来自 fake store 的真实行
    for i in range(1, MAX_LISTED + 1):
        assert f"catalog_paper_id: catalog-{i}" in result.output


def test_local_fallback_exposes_real_metadata_only(patched):
    _service, _adapter, run = patched

    result = run([])

    # 详情页 URL 来自真实目录行（official_page_url 回退），不得编造/拼接
    assert "https://www.usenix.org/conference/usenixsecurity24/presentation/p1" in result.output
    assert "Abstract for local paper 1." in result.output
    assert "（缺失" not in result.output  # 真实摘要存在，不应出现缺失引导
    # 不得出现任何非真实 id 或伪造字段
    assert "fabricated" not in result.output


# --- 2. 实时有结果 -> 不走兜底 ----------------------------------------------


def test_live_hits_skip_local_fallback(patched):
    service, adapter, run = patched

    candidates = [
        type("_C", (), {
            "candidate_id": "c1", "title": "Live Paper 1",
            "article_url": "https://www.usenix.org/x/1", "source_page_url": None,
            "abstract": "live abstract",
        })()
    ]
    result = run(candidates)

    assert result.ok is True, result.error
    assert adapter.calls == [], "实时有结果时不得调用本地目录出口"
    assert "USENIX Security（本地目录）" not in result.output
    assert "catalog_paper_id: c1" in result.output  # 仍走既有实时展示契约


# --- 3. 兜底抛异常 -> 安全退化为 0 条且不抛 ------------------------------------


def test_fallback_exception_degrades_to_zero_without_raising(patched, monkeypatch):
    _service, _adapter, run = patched

    monkeypatch.setattr(
        "backend.app.research.application.search_catalog_adapter.CatalogSearchAdapter",
        _fake_adapter_factory(None, raise_on_search=True),
    )

    # 实时 0 命中 + 兜底异常 -> 必须返回 ok 的 0 条，而不是把异常冒泡为 500
    result = run([])

    assert result.ok is True, "兜底异常必须安全降级（ok=True），不得抛异常"
    assert "USENIX Security（本地目录）" not in result.output, "兜底失败时不得混入本地目录结果"
    assert "命中 0 篇" in result.output, "兜底失败时退化为原 0 条行为"


# --- 4. 兜底返回 id 但 store 读不到真实行 -> 不伪造为 0 条 --------------------


def test_fallback_ids_without_real_rows_degrade_to_zero(patched, monkeypatch):
    _service, _adapter, run = patched

    # adapter 返回 id，但 store 里没有这些行 -> 兜底应退化为 0 条，绝不编造
    outcome = SearchOutcome(("ghost-1", "ghost-2"), 2, False, None, search_id="sid")
    monkeypatch.setattr(
        "backend.app.research.application.search_catalog_adapter.CatalogSearchAdapter",
        _fake_adapter_factory(outcome),
    )

    result = run([])

    assert result.ok is True, result.error
    assert "USENIX Security（本地目录）" not in result.output, "没有真实行不得输出本地兜底结果"
    assert "ghost-1" not in result.output, "不得伪造/回显不存在的目录 id"
    assert "命中 0 篇" in result.output


# --- 5. 来源标注 + search_id 透传 -------------------------------------------


def test_fallback_propagates_search_id_and_labels_source(patched):
    _service, _adapter, run = patched

    result = run([])

    assert result.search_id == "fallback-sid", "search_id 必须取 adapter 返回的真实句柄"
    assert result.name == TOOL


def test_fallback_search_id_none_when_adapter_returns_none(patched, monkeypatch):
    _service, _adapter, run = patched

    outcome = SearchOutcome(
        tuple(f"catalog-{i}" for i in range(1, 4)), 3, False, None, search_id=None
    )
    monkeypatch.setattr(
        "backend.app.research.application.search_catalog_adapter.CatalogSearchAdapter",
        _fake_adapter_factory(outcome),
    )

    result = run([])

    assert result.ok is True, result.error
    assert result.search_id is None, "adapter 无 search_id 时兜底 search_id 必须为空"


# --- 6. 结果确定：同样输入两次调用输出一致 -----------------------------------


def test_fallback_is_deterministic(patched):
    _service, _adapter, run = patched

    first = run([])
    second = run([])

    assert first.output == second.output, "同样输入必须产出完全相同的兜底结果"
    assert first.search_id == second.search_id


# --- 7. 条数受控：本地兜底不超过 _SEARCH_LIST_LIMIT 条 ------------------------


def test_local_fallback_is_bounded(patched):
    _service, _adapter, run = patched

    result = run([])

    listed = [i for i in range(1, 21) if f"Local Paper {i}" in result.output]
    assert 1 <= len(listed) <= MAX_LISTED, f"本地兜底条数必须受控，实际 {len(listed)} 篇"
    assert "Local Paper 9" not in result.output  # 超过上限的不出现
