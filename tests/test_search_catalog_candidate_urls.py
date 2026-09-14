"""spec-032.1 Task07 — ``search_paper_catalog`` 的 output 必须带详情页 URL（TDD，全离线）。

背景（端到端验收发现的真实缺陷）：用户点名 usenix-catalog-orchestration 技能后，
``search_paper_catalog`` **成功**检索到 20 篇 USENIX 2024 论文，但返回给模型的文本
只拼了标题，没有详情页 URL，模型因此无法对摘要为空的候选调用
``fetch_paper_detail`` 补齐摘要（技能硬边界禁止模型自行拼接 URL）。

本测试锁定 ``_search_catalog`` 的 output 契约（全部用 fake service，不触网）：

1. 每篇候选都带详情页 URL（优先 ``article_url``）。
2. 无 ``article_url`` 时回退 ``source_page_url``。
3. 两个 URL 都缺失时不输出 URL 行，且不报错、不中断。
4. 摘要已有则输出摘要；缺失时给出引导文案，不得编造。
5. 输出条数受控（≤8 篇）且仍包含「命中总数」说明。
6. URL 只能来自候选对象本身，不得拼接／构造。
"""

import pytest

from backend.app.paper_discovery.application.paper_discovery_search import SearchResult
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.skills.tool_dispatch import build_default_dispatch

TOOL = "search_paper_catalog"
MAX_LISTED = 8


def _candidate(index, **overrides):
    """构造一篇候选；只显式给出本测试关心的字段。"""
    fields = {
        "candidate_id": f"c{index}",
        "search_id": "s1",
        "title": f"Paper {index}",
        "conference_id": "usenix-security",
        "conference_name": "USENIX Security",
        "year": 2024,
    }
    fields.update(overrides)
    return PaperCandidate(**fields)


class _FakeConference:
    def __init__(self, conference_id, short_name, *, enabled=True, aliases=None):
        self.conference_id = conference_id
        self.name = f"{short_name} full name"
        self.short_name = short_name
        self.dblp_stream = f"conf/{conference_id}"
        self.venue_aliases = list(aliases or [])
        self.enabled = enabled


class _FakeStore:
    def __init__(self, conferences):
        self._conferences = list(conferences)

    def list_conferences(self):
        return sorted(self._conferences, key=lambda c: c.short_name)


class _FakeSearchService:
    """假检索服务：回放预设候选，绝不触网。"""

    def __init__(self, candidates):
        self._candidates = list(candidates)
        self.sources = []

    def search(self, source, query, years, limit, publication_scope):
        self.sources.append(source)
        session = SearchSession(search_id="s1", query=query, expires_at="", created_at="")
        return SearchResult(session, list(self._candidates), [], None)


@pytest.fixture
def fake_service(monkeypatch):
    """注入 fake service/store，返回 ``(service, run)``。

    ``service.candidates`` 可在调用前替换，以复用同一批 patch。
    """
    service = _FakeSearchService([])
    store = _FakeStore([_FakeConference("usenix-security", "USENIX Security")])
    monkeypatch.setattr(
        "backend.app.api.common._build_paper_search_service", lambda: service
    )
    monkeypatch.setattr("backend.app.api.common._paper_store", lambda: store)

    def run(candidates):
        service._candidates = list(candidates)
        return build_default_dispatch()(TOOL, {"source": "usenix", "query": "fuzzing"})

    service.run = run
    return service


# --- 1. 每篇候选都带详情页 URL（优先 article_url） ----------------------------

def test_each_candidate_exposes_article_url(fake_service):
    candidates = [
        _candidate(1, article_url="https://www.usenix.org/conference/usenixsecurity24/presentation/one"),
        _candidate(2, article_url="https://www.usenix.org/conference/usenixsecurity24/presentation/two"),
    ]

    result = fake_service.run(candidates)

    assert result.ok is True, result.error
    for c in candidates:
        assert c.title in result.output
        assert c.article_url in result.output, "每篇候选都必须暴露详情页 URL 供 fetch_paper_detail 使用"


def test_article_url_preferred_over_source_page_url(fake_service):
    url = "https://www.usenix.org/conference/usenixsecurity24/presentation/one"
    fallback = "https://www.usenix.org/conference/usenixsecurity24/accepted-papers"

    result = fake_service.run([_candidate(1, article_url=url, source_page_url=fallback)])

    assert url in result.output
    assert fallback not in result.output, "有 article_url 时不得输出回退地址"


# --- 2. 无 article_url -> 回退 source_page_url -------------------------------

def test_falls_back_to_source_page_url(fake_service):
    fallback = "https://www.usenix.org/conference/usenixsecurity24/accepted-papers"

    result = fake_service.run([_candidate(1, article_url=None, source_page_url=fallback)])

    assert result.ok is True, result.error
    assert fallback in result.output


# --- 3. 两个 URL 都缺失：不输出 URL 行，不报错不中断 --------------------------

def test_missing_urls_do_not_break_output(fake_service):
    result = fake_service.run([
        _candidate(1, article_url=None, source_page_url=None),
        _candidate(2, article_url="https://www.usenix.org/conference/usenixsecurity24/presentation/two"),
    ])

    assert result.ok is True, result.error
    # 无 URL 的候选仍出现在列表里（标题保留），只是没有 URL 行
    assert "Paper 1" in result.output
    assert "Paper 2" in result.output
    assert "https://www.usenix.org/conference/usenixsecurity24/presentation/two" in result.output
    # 不得因为缺 URL 而伪造地址
    assert "None" not in result.output


# --- 4. 摘要：有则给出，无则引导补齐，不编造 ----------------------------------

def test_existing_abstract_is_output(fake_service):
    abstract = "We study collaborative perception under partial observability."

    result = fake_service.run(
        [_candidate(1, article_url="https://www.usenix.org/x", abstract=abstract)]
    )

    assert abstract in result.output
    assert "fetch_paper_detail" not in result.output, "摘要已有则无需再引导补齐"


def test_missing_abstract_guides_to_fetch_paper_detail(fake_service):
    result = fake_service.run(
        [_candidate(1, article_url="https://www.usenix.org/x", abstract=None)]
    )

    assert "fetch_paper_detail" in result.output, "摘要缺失时必须引导模型调用 fetch_paper_detail 补齐"


def test_blank_abstract_treated_as_missing(fake_service):
    result = fake_service.run(
        [_candidate(1, article_url="https://www.usenix.org/x", abstract="   ")]
    )

    assert "fetch_paper_detail" in result.output


# --- 5. 条数受控（≤8）且仍报告命中总数 ---------------------------------------

def test_output_is_bounded_but_reports_total(fake_service):
    candidates = [
        _candidate(i, article_url=f"https://www.usenix.org/conference/usenixsecurity24/presentation/p{i}")
        for i in range(1, 21)
    ]

    result = fake_service.run(candidates)

    assert result.ok is True, result.error
    listed = [i for i in range(1, 21) if f"Paper {i}" in result.output]
    # 上限 8 篇，避免一次 20 篇撑爆上下文
    assert 1 <= len(listed) <= MAX_LISTED, f"输出条数必须受控，实际列出 {len(listed)} 篇"
    # 后 12 篇不得出现在输出里（受控、不撑上下文）
    assert "Paper 9" not in result.output
    assert "20" in result.output, "必须保留命中总数说明，让模型知道还有更多"


# --- 6. URL 只取自候选本身，不拼接不构造 -------------------------------------

def test_output_urls_come_from_candidates_only(fake_service):
    urls = [
        "https://www.usenix.org/conference/usenixsecurity24/presentation/alpha",
        "https://www.usenix.org/conference/usenixsecurity24/presentation/beta",
    ]

    result = fake_service.run([
        _candidate(1, article_url=urls[0]),
        _candidate(2, article_url=urls[1]),
    ])

    assert urls[0] in result.output
    assert urls[1] in result.output
    # 候选未提供的地址不得出现（不得拼接/构造）
    assert "candidate_id" not in result.output
    assert "catalog_paper_id: c1" in result.output


# --- 7. Search Worker candidate contract: stable catalog ID only ----------------

def test_each_candidate_exposes_stable_catalog_paper_id_without_extra_fields(fake_service):
    candidates = [
        _candidate(
            1,
            article_url="https://www.usenix.org/conference/usenixsecurity24/presentation/one",
            pdf_url="https://www.usenix.org/system/files/conference/one.pdf",
            source_links=[{"kind": "attacker-controlled", "url": "https://evil.example/raw"}],
        ),
        _candidate(2, article_url=None, source_page_url=None),
    ]

    first = fake_service.run(candidates)
    second = fake_service.run(candidates)

    assert first.ok is True, first.error
    assert second.ok is True, second.error
    assert "catalog_paper_id: c1" in first.output
    assert "catalog_paper_id: c2" in first.output
    assert first.output == second.output, "现有 candidate_id 映射为 catalog_paper_id 后必须保持稳定"
    # The adapter exposes only the stable ID plus its existing title/abstract/
    # detail fallback; it must not serialize arbitrary candidate fields.
    assert "candidate_id:" not in first.output
    assert "attacker-controlled" not in first.output
    assert "system/files/conference/one.pdf" not in first.output
