"""spec-031 P1：中文 query 目录跨语言排序的回归与新增行为测试。

覆盖三个已拍板决策：
- Q6① CJK 检测 → 语义分优先（中文 query 不再退化为字典序）
- Q7② 静态跨语言术语映射（独立 JSON，fail-open、可注入）
- Q8① 降级路径词法全 0 → fail-closed 返回空 + degraded
"""
from types import SimpleNamespace

import backend.app.paper_discovery.application.catalog_search_graph as catalog_graph_module
from backend.app.paper_discovery.application.catalog_search_graph import (
    CatalogRagAdapter,
    load_term_mapping,
)
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper


class _Hit:
    """Minimal Hit-like double: ``paper_id`` resolves to a catalog row,
    ``score`` becomes the semantic ``final_score`` when no reranker is set."""

    def __init__(self, paper_id: str, score: float):
        self.paper_id = paper_id
        self.score = score
        self.rerank_score = None


class _FakeQdrant:
    def collection_exists(self, name):
        return True

    def query_points(self, **kwargs):
        # Content is irrelevant: ``rrf_fuse`` is monkeypatched in the ranking
        # tests below to inject controlled hits directly.
        return SimpleNamespace(points=[])


def _indexed(*, paper_id, title, abstract="", keywords=None, metadata_hash="x"):
    return CatalogPaper(
        paper_id, "usenix-security", 2024, title,
        abstract=abstract, keywords=list(keywords or []),
        metadata_hash=metadata_hash, index_status="indexed",
    )


def _patch_fuse(monkeypatch, hits):
    monkeypatch.setattr(catalog_graph_module, "rrf_fuse", lambda *a, **k: list(hits))
    monkeypatch.setattr(catalog_graph_module, "ensure_collection", lambda *a, **k: None)


def _adapter(**kwargs):
    opts = {
        "term_mapping": {},
        "embedder": lambda texts: [[0.0] for _ in texts],
        "sparse_encoder": lambda text: {"indices": [], "values": []},
        "reranker": None,
        "client": _FakeQdrant(),
    }
    opts.update(kwargs)
    return CatalogRagAdapter(**opts)


# ---------------------------------------------------------------------------
# Q6① CJK → semantic-first
# ---------------------------------------------------------------------------
def test_cjk_query_ranks_by_semantic_score(monkeypatch):
    # Hits with distinct final scores; insertion order is neither score order
    # nor catalog_paper_id order.
    hits = [_Hit("p-mid", 0.5), _Hit("p-low", 0.2), _Hit("p-high", 0.9)]
    _patch_fuse(monkeypatch, hits)
    papers = [
        _indexed(paper_id="p-low", title="Low side channel paper",
                 abstract="timing cache side channel analysis"),
        _indexed(paper_id="p-high", title="Highly relevant side channel paper",
                 abstract="comprehensive side channel timing attack survey"),
        _indexed(paper_id="p-mid", title="Medium side channel paper",
                 abstract="some side channel discussion"),
    ]
    adapter = _adapter()
    ranked = adapter.retrieve_and_rerank("侧信道攻击的论文", papers)
    ids = [item["catalog_paper_id"] for item in ranked]
    scores = [item["final_score"] for item in ranked]
    # Primary key for a CJK query must be the semantic score (descending)…
    assert scores == sorted(scores, reverse=True)
    assert ids == ["p-high", "p-mid", "p-low"]
    # …and NOT the lexicographic catalog_paper_id order (the original bug).
    assert ids != sorted(ids)


def test_english_query_keeps_lexical_priority(monkeypatch):
    # Regression guard: an exact/strong metadata (lexical) match must still
    # outrank a higher vector score for an English query.
    hits = [_Hit("p-other", 0.95), _Hit("p-target", 0.3)]
    _patch_fuse(monkeypatch, hits)
    title = "Back-Propagating System Dependency Impact for Attack Investigation"
    papers = [
        _indexed(paper_id="p-target", title=title, abstract="target"),
        _indexed(paper_id="p-other", title="Unrelated Paper", abstract="unrelated"),
    ]
    adapter = _adapter()
    ranked = adapter.retrieve_and_rerank(title, papers)
    assert ranked[0]["catalog_paper_id"] == "p-target"
    # The exact-title match wins despite a *lower* semantic score.
    assert ranked[0]["final_score"] == 0.3


# ---------------------------------------------------------------------------
# Q7② cross-lingual term mapping (injected, no real file)
# ---------------------------------------------------------------------------
def test_term_mapping_gives_signal_in_fallback():
    # Degraded path (vector unavailable) reached by calling ``_fallback``
    # directly; a Chinese term expands to its English synonym so the lexical
    # channel is no longer blind.
    adapter = _adapter(term_mapping={"侧信道": ["side channel"]})
    papers = [
        _indexed(paper_id="p-side", title="Side Channel Analysis",
                 abstract="timing side channel attack"),
        _indexed(paper_id="p-unrelated", title="Unrelated Paper",
                 abstract="nothing relevant here"),
    ]
    ranked = adapter._fallback("侧信道", papers)
    scores = {item["catalog_paper_id"]: item["final_score"] for item in ranked}
    assert scores["p-side"] > 0.0
    assert scores["p-side"] > scores["p-unrelated"]


def test_term_mapping_missing_file_is_fail_open(tmp_path):
    missing = str(tmp_path / "no_such_file.json")
    # Loader itself never raises and degrades to an empty mapping.
    assert load_term_mapping(missing) == {}
    # An adapter pointed at a missing file still functions (empty mapping).
    adapter = _adapter(term_mapping_path=missing)
    assert adapter._get_term_mapping() == {}


def test_term_mapping_corrupt_file_is_fail_open(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json,,,}")
    assert load_term_mapping(str(bad)) == {}
    # A JSON array (not the expected object) also degrades to empty.
    not_object = tmp_path / "arr.json"
    not_object.write_text("[1, 2, 3]")
    assert load_term_mapping(str(not_object)) == {}


def test_term_mapping_missing_path_does_not_block_retrieval(monkeypatch):
    # "检索继续": a missing map must not raise during a real ranking call.
    hits = [_Hit("p-a", 0.9), _Hit("p-b", 0.4)]
    _patch_fuse(monkeypatch, hits)
    papers = [
        _indexed(paper_id="p-a", title="Alpha malware analysis", abstract="malware"),
        _indexed(paper_id="p-b", title="Beta phishing study", abstract="phishing"),
    ]
    adapter = _adapter(term_mapping_path="/nonexistent/cross_lingual_term_map.json")
    # English query → lexical branch; mapping is irrelevant but must not raise.
    ranked = adapter.retrieve_and_rerank("malware analysis", papers)
    assert [item["catalog_paper_id"] for item in ranked] == ["p-a", "p-b"]


def test_real_term_map_file_loads():
    # Guard the shipped JSON: it must load, be an object, and contain the
    # security-domain terms aligned with the real catalog.
    adapter = CatalogRagAdapter()
    mapping = adapter._get_term_mapping()
    assert isinstance(mapping, dict) and mapping
    assert "侧信道" in mapping and "模糊测试" in mapping and "形式化验证" in mapping


# ---------------------------------------------------------------------------
# Q8① degraded path fail-closed
# ---------------------------------------------------------------------------
def test_fallback_all_zero_lexical_returns_empty_and_degraded():
    adapter = _adapter(term_mapping={})
    papers = [
        _indexed(paper_id="p-a", title="Alpha", abstract="alpha"),
        _indexed(paper_id="p-b", title="Beta", abstract="beta"),
    ]
    # Chinese query whose tokens never collide with English metadata and no map.
    result = adapter._fallback("完全无关的中文查询词汇组合", papers)
    assert result == []
    assert adapter.degraded is True


def test_fallback_partial_signal_still_returns_ranked():
    # Only a *fully* zero lexical channel fails closed; if any paper overlaps,
    # the degraded path still returns a meaningful ordering.
    adapter = _adapter(term_mapping={"词汇": ["alpha"]})
    papers = [
        _indexed(paper_id="p-a", title="Alpha", abstract="alpha stuff"),
        _indexed(paper_id="p-b", title="Beta", abstract="beta stuff"),
    ]
    result = adapter._fallback("词汇", papers)
    assert result != []
    assert [item["catalog_paper_id"] for item in result][0] == "p-a"
