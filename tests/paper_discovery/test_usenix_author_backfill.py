"""spec-035：USENIX 作者回填入口（列表页自带作者 → 按 catalog_paper_id fill-if-missing）离线测试。"""

from __future__ import annotations

import textwrap
import unittest
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from backend.app.paper_discovery.infrastructure.usenix_publication_source import (
    UsenixAcceptedSource,
    _catalog_metadata_hash,
)

CONFERENCE_ID = "usenix-security"


@dataclass
class _Paper:
    catalog_paper_id: str
    year: int
    abstract: Optional[str]
    official_page_url: str
    title: str = "Some Paper Title"
    authors: list = field(default_factory=list)
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
    created_at: str = "2026-09-15T00:00:00Z"
    updated_at: str = "2026-09-15T00:00:00Z"


class _FakeStore:
    """Narrow store exposing only what ``backfill_authors`` reads/writes.

    ``list_catalog_papers`` records the ``index_status`` it was called with: the
    backfill MUST ask for every row (``None``), because a paper whose abstract
    was just backfilled is ``pending`` and the default ``"indexed"`` filter would
    silently skip it.
    """

    def __init__(self, papers):
        self.papers = list(papers)
        self.saved: list[Any] = []
        self.index_status_calls: list[Any] = []

    def list_catalog_papers(self, conference_ids=None, years=None, *, index_status="indexed"):
        self.index_status_calls.append(index_status)
        return list(self.papers)

    def get_catalog_paper(self, catalog_paper_id):
        return next((p for p in self.papers if p.catalog_paper_id == catalog_paper_id), None)

    def upsert_catalog_paper(self, paper, now=None):
        for index, existing in enumerate(self.papers):
            if existing.catalog_paper_id == paper.catalog_paper_id:
                self.papers[index] = paper
                break
        self.saved.append(paper)
        return True


def _listing_markup(*titles_and_authors: tuple[str, str], year: int = 2024) -> str:
    """Build an accepted-paper listing page the real parser accepts."""
    blocks = []
    for index, (title, authors_html) in enumerate(titles_and_authors):
        blocks.append(
            textwrap.dedent(
                f"""
                <article class="node node-paper view-mode-schedule">
                <h2><a href="/conference/usenixsecurity{year % 100:02d}/presentation/paper-{index}">{title}</a></h2>
                <p class="field-paper-people-text">{authors_html}</p>
                </article>
                """
            )
        )
    return f"<main>{''.join(blocks)}</main>"


def _source(store, listing_markup_by_url, *, failing_urls=()):
    """Build a source whose listing fetches are served from a local dict."""
    source = UsenixAcceptedSource(timeout=5, store=store, sleep=lambda _s: None)

    def fake_get_text(url, interval=1.0):
        if url in failing_urls:
            raise OSError("simulated network failure")
        return listing_markup_by_url.get(url, "")

    source._get_text = fake_get_text  # type: ignore[method-assign]
    return source


class BackfillAuthorsTests(unittest.TestCase):
    @staticmethod
    def _cid(title: str) -> str:
        return UsenixAcceptedSource._catalog_paper_id(CONFERENCE_ID, title)

    def _papers(self):
        return [
            _Paper(self._cid("Secure Collaborative ML"), 2024, "Abstract A",
                   "https://www.usenix.org/conference/usenixsecurity24/presentation/paper-0",
                   title="Secure Collaborative ML"),
            _Paper(self._cid("Fragment Check"), 2024, "Abstract B",
                   "https://www.usenix.org/conference/usenixsecurity24/presentation/paper-1",
                   title="Fragment Check"),
        ]

    @staticmethod
    def _listings_2024():
        markup = _listing_markup(
            ("Secure Collaborative ML", "Zhenghang Ren, <em>HKUST;</em> Mingxuan Fan"),
            ("Fragment Check", "Hyeonmin Lee, <em>SNU;</em> Taejoong Chung"),
            year=2024,
        )
        return {
            "https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers": markup,
            "https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers": markup,
        }

    def test_fills_authors_from_listing_page(self):
        store = _FakeStore(self._papers())
        source = _source(store, self._listings_2024())
        result = source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        self.assertTrue(result["ok"])
        self.assertEqual(result["filled"], 2)
        self.assertEqual(result["failed"], 0)
        by_id = {p.catalog_paper_id: p.authors for p in store.papers}
        self.assertEqual(by_id[self._cid("Secure Collaborative ML")],
                         ["Zhenghang Ren", "Mingxuan Fan"])
        self.assertEqual(by_id[self._cid("Fragment Check")],
                         ["Hyeonmin Lee", "Taejoong Chung"])

    def test_affiliations_never_become_authors(self):
        """``<em>`` holds the affiliation; splitting on it would fake authors."""
        store = _FakeStore(self._papers())
        source = _source(store, self._listings_2024())
        source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        for paper in store.papers:
            for author in paper.authors:
                self.assertNotIn("HKUST", author)
                self.assertNotIn("SNU", author)
                self.assertIn(" ", author)

    def test_recomputes_metadata_hash_for_new_authors(self):
        """The hash must reflect the authors, or the upsert is dropped as unchanged."""
        store = _FakeStore(self._papers())
        source = _source(store, self._listings_2024())
        source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        for paper in store.papers:
            self.assertEqual(paper.metadata_hash, _catalog_metadata_hash(paper, paper.abstract))
            stale = replace(paper, authors=[])
            self.assertNotEqual(paper.metadata_hash,
                                _catalog_metadata_hash(stale, stale.abstract))

    def test_requests_every_index_status(self):
        """Regression: a pending row (just backfilled abstract) must be visible."""
        store = _FakeStore(self._papers())
        source = _source(store, self._listings_2024())
        source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        self.assertTrue(store.index_status_calls)
        self.assertTrue(all(value is None for value in store.index_status_calls))

    def test_does_not_overwrite_existing_authors(self):
        """fill-if-missing is a hard rule: an existing author list always wins."""
        papers = self._papers()
        papers[0] = replace(papers[0], authors=["Already Present"])
        store = _FakeStore(papers)
        source = _source(store, self._listings_2024())
        result = source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        self.assertEqual(result["filled"], 1)
        by_id = {p.catalog_paper_id: p.authors for p in store.papers}
        self.assertEqual(by_id[self._cid("Secure Collaborative ML")], ["Already Present"])
        self.assertEqual(by_id[self._cid("Fragment Check")],
                         ["Hyeonmin Lee", "Taejoong Chung"])

    def test_paper_missing_from_listing_is_skipped(self):
        papers = self._papers()
        papers.append(_Paper(self._cid("Not On The Listing"), 2024, None,
                             "https://www.usenix.org/conference/usenixsecurity24/presentation/gone",
                             title="Not On The Listing"))
        store = _FakeStore(papers)
        source = _source(store, self._listings_2024())
        result = source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        self.assertEqual(result["filled"], 2)
        self.assertIn(self._cid("Not On The Listing"), result_skipped_ids(result, store))

    def test_year_filter_skips_other_years(self):
        papers = self._papers()
        papers.append(_Paper(self._cid("Twenty Twenty Five"), 2025, None,
                             "https://www.usenix.org/conference/usenixsecurity25/presentation/paper-0",
                             title="Twenty Twenty Five"))
        store = _FakeStore(papers)
        listings = {"https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers":
                    _listing_markup(("Twenty Twenty Five", "Grace Hopper, <em>US Navy</em>"),
                                    year=2025)}
        source = _source(store, listings)
        result = source.backfill_authors(CONFERENCE_ID, years=[2025], interval=0)

        self.assertEqual(result["filled"], 1)
        by_id = {p.catalog_paper_id: p.authors for p in store.papers}
        self.assertEqual(by_id[self._cid("Secure Collaborative ML")], [])
        self.assertEqual(by_id[self._cid("Twenty Twenty Five")], ["Grace Hopper"])

    def test_listing_failure_is_recorded_not_fatal(self):
        """One unreachable listing must not abort the other cycles."""
        store = _FakeStore(self._papers())
        source = _source(
            store,
            self._listings_2024(),
            failing_urls=("https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers",),
        )
        result = source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        self.assertEqual(result["failed"], 1)
        self.assertTrue(result["failures"])
        # The fall listing still served the same papers, so nothing is lost.
        self.assertEqual(result["filled"], 2)

    def test_all_listings_failing_fills_nothing(self):
        store = _FakeStore(self._papers())
        source = _source(store, {}, failing_urls=tuple(self._listings_2024()))
        result = source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)

        self.assertEqual(result["filled"], 0)
        self.assertEqual(result["failed"], 2)
        self.assertTrue(all(p.authors == [] for p in store.papers))

    def test_without_store_is_unavailable(self):
        source = UsenixAcceptedSource(timeout=5, store=None, sleep=lambda _s: None)
        result = source.backfill_authors(CONFERENCE_ID, years=[2024], interval=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "USENIX_STORE_UNAVAILABLE")


def result_skipped_ids(result, store):  # helper: ids that were not written
    written = {p.catalog_paper_id for p in store.saved}
    return [p.catalog_paper_id for p in store.papers if p.catalog_paper_id not in written]


if __name__ == "__main__":
    unittest.main()
