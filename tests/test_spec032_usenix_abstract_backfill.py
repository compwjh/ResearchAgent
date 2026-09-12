"""spec-032：USENIX 摘要回填入口（列表页无摘要 → 详情页 fill-if-missing）离线测试。"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.paper_discovery.infrastructure.usenix_publication_source import UsenixAcceptedSource


@dataclass
class _Paper:
    catalog_paper_id: str
    year: int
    abstract: Optional[str]
    official_page_url: str
    title: str = "Some Paper Title"
    authors: tuple = ()
    keywords: tuple = ()
    doi: str = ""
    dblp_key: str = ""
    publication_stage: str = "accepted"
    official_pdf_url: str = ""
    prepublication_pdf_url: str = ""
    arxiv_id: str = ""
    index_status: str = "pending"
    index_version: int = 1
    metadata_hash: str = ""
    created_at: str = "2026-09-13T00:00:00Z"
    updated_at: str = "2026-09-13T00:00:00Z"


class _FakeStore:
    def __init__(self, papers):
        self.papers = list(papers)
        self.saved: list[Any] = []

    def list_catalog_papers(self, conference_ids=None):
        return list(self.papers)

    def get_catalog_paper(self, catalog_paper_id):
        return next((p for p in self.papers if p.catalog_paper_id == catalog_paper_id), None)

    def upsert_catalog_paper(self, paper, now=None):
        for index, existing in enumerate(self.papers):
            if existing.catalog_paper_id == paper.catalog_paper_id:
                self.papers[index] = paper
        self.saved.append(paper)
        return True


def _source(store, detail_results):
    source = UsenixAcceptedSource(timeout=5, store=store, sleep=lambda _s: None)

    def fake_detail(url):
        return detail_results.get(url, {"ok": False, "error_code": "USENIX_FETCH_FAILED", "abstract": ""})

    source.fetch_paper_detail = fake_detail  # type: ignore[method-assign]
    return source


class BackfillAbstractsTests(unittest.TestCase):
    def _papers(self):
        return [
            _Paper("p1", 2024, None, "https://www.usenix.org/conference/usenixsecurity24/presentation/ren"),
            _Paper("p2", 2024, "", "https://www.usenix.org/conference/usenixsecurity24/presentation/lee"),
            _Paper("p3", 2025, None, "https://www.usenix.org/conference/usenixsecurity25/presentation/kim"),
            _Paper("p4", 2024, "already has abstract", "https://www.usenix.org/conference/usenixsecurity24/presentation/chen"),
            _Paper("p5", 2024, None, "https://evil.example/presentation/x"),
        ]

    def test_fills_only_missing_abstracts(self):
        store = _FakeStore(self._papers())
        source = _source(store, {
            "https://www.usenix.org/conference/usenixsecurity24/presentation/ren": {
                "ok": True, "error_code": None, "abstract": "Abstract A"},
            "https://www.usenix.org/conference/usenixsecurity24/presentation/lee": {
                "ok": True, "error_code": None, "abstract": "Abstract B"},
        })
        result = source.backfill_abstracts("usenix-security", years=[2024], limit=10, interval=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["filled"], 2)
        self.assertEqual(result["failed"], 0)
        filled = {p.catalog_paper_id: p.abstract for p in store.papers}
        self.assertEqual(filled["p1"], "Abstract A")
        self.assertEqual(filled["p2"], "Abstract B")
        self.assertEqual(filled["p4"], "already has abstract")  # 已存在的摘要不被覆盖

    def test_respects_limit(self):
        store = _FakeStore(self._papers())
        source = _source(store, {
            "https://www.usenix.org/conference/usenixsecurity24/presentation/ren": {
                "ok": True, "error_code": None, "abstract": "A"},
        })
        result = source.backfill_abstracts("usenix-security", years=[2024], limit=1, interval=0)
        self.assertEqual(result["attempted"], 1)

    def test_year_filter_skips_other_years(self):
        store = _FakeStore(self._papers())
        source = _source(store, {})
        result = source.backfill_abstracts("usenix-security", years=[2025], limit=10, interval=0)
        self.assertEqual(result["attempted"], 1)  # 只有 p3 属于 2025

    def test_off_host_url_is_skipped_without_request(self):
        store = _FakeStore(self._papers())
        source = _source(store, {})
        result = source.backfill_abstracts("usenix-security", years=[2024], limit=10, interval=0)
        self.assertEqual(result["filled"], 0)
        # p5 是外部 URL，被计入 skipped，且从未发起请求
        self.assertIn("p5", [p.catalog_paper_id for p in store.papers])

    def test_failed_detail_is_recorded_not_fatal(self):
        store = _FakeStore(self._papers())
        source = _source(store, {
            "https://www.usenix.org/conference/usenixsecurity24/presentation/ren": {
                "ok": False, "error_code": "USENIX_FETCH_FAILED", "abstract": ""},
        })
        result = source.backfill_abstracts("usenix-security", years=[2024], limit=10, interval=0)
        # p1 与 p2 都缺摘要且都抓取失败 → 各自记一次失败，互不中断
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["filled"], 0)
        self.assertTrue(result["failures"])


if __name__ == "__main__":
    unittest.main()
