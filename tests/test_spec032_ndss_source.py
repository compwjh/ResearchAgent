"""spec-032 Task04：NDSS 官方目录适配器测试（真实页面结构固定样本）。"""

from __future__ import annotations

import unittest

from backend.app.paper_discovery.infrastructure.ndss_publication_source import (
    NDSS_DETAIL_URL_REJECTED,
    NDSS_FETCH_FAILED,
    NdssAcceptedSource,
    NdssPaper,
    listing_url,
    parse_ndss_detail,
    parse_ndss_list,
)

# 摘自 https://www.ndss-symposium.org/ndss2026/accepted-papers/（真实结构，已裁剪）
LIST_HTML = """
<div class="pt-cv-view pt-cv-blockgrid iscvblock iscvreal list1 layout1" id="pt-cv-view-j2wvi17v">
  <div data-id="pt-cv-page-1" class="pt-cv-page" data-cvc="2">
    <div class=" pt-cv-content-item pt-cv-2-col" data-pid="23756">
      <h2 class="pt-cv-title"><a href="https://www.ndss-symposium.org/ndss-paper/a-causal-perspective-for-enhancing-jailbreak-attack-and-defense/" class="_self" target="_self">A Causal Perspective for Enhancing Jailbreak Attack and Defense</a></h2>
      <div class="pt-cv-ctf-list">
        <div class="pt-cv-custom-fields pt-cv-ctf-display_authors">
          <div class="pt-cv-ctf-value"><p>Licheng Pan (Zhejiang University), Yunsheng Lu (University of Chicago), Jiexi Liu (Alibaba Group)</p></div>
        </div>
      </div>
    </div>
    <div class=" pt-cv-content-item pt-cv-2-col" data-pid="23757">
      <h2 class="pt-cv-title"><a href="https://www.ndss-symposium.org/ndss-paper/ace-a-security-architecture-for-llm-integrated-app-systems/" class="_self">ACE: A Security Architecture for LLM-Integrated App Systems</a></h2>
      <div class="pt-cv-ctf-list">
        <div class="pt-cv-custom-fields pt-cv-ctf-display_authors">
          <div class="pt-cv-ctf-value"><p>Alice Smith (MIT), Bob Lee (UCSD)</p></div>
        </div>
      </div>
    </div>
    <div class=" pt-cv-content-item pt-cv-2-col" data-pid="23758">
      <h2 class="pt-cv-title"><a href="https://www.ndss-symposium.org/ndss-paper/no-author-paper/" class="_self">Paper Without Authors On Listing</a></h2>
    </div>
  </div>
</div>
"""

# 摘自 https://www.ndss-symposium.org/ndss-paper/a-causal-perspective.../（真实结构，已裁剪）
DETAIL_HTML = """
<html><body class="wp-singular ndss-paper-template-default single single-ndss-paper postid-23756 category-ndss-2026 tag-fall-cycle-2026">
<div class="new-wrapper paper-single">
  <div class="page-header purple-heading paper-single-heading"><h1>A Causal Perspective for Enhancing Jailbreak Attack and Defense</h1></div>
  <div class="paper-buttons">
    <div class="btn-group-vertical" role="group">
      <a role="button" class="btn btn-light btn-sm pdf-button" target="_blank" href="https://www.ndss-symposium.org/wp-content/uploads/2026-f797-paper.pdf">Paper</a>
    </div>
  </div>
  <div class="paper-data">
    <p><strong>
    <p>Licheng Pan (Zhejiang University), Yunsheng Lu (University of Chicago), Jiexi Liu (Alibaba Group)</p>
    </strong></p>
    <p><p>Uncovering the mechanisms behind "jailbreaks" is crucial.<br />
    We propose textbf{Causal Analyst}, a framework that integrates LLMs.<br />
    Our analysis reveals direct causal drivers.</p>
  </div>
</div>
</body></html>
"""


class ParseListTests(unittest.TestCase):
    def test_parses_title_url_and_authors(self):
        papers = parse_ndss_list(LIST_HTML, page_url=listing_url(2026))
        self.assertEqual(len(papers), 3)
        first = papers[0]
        self.assertEqual(first.title, "A Causal Perspective for Enhancing Jailbreak Attack and Defense")
        self.assertEqual(
            first.article_url,
            "https://www.ndss-symposium.org/ndss-paper/a-causal-perspective-for-enhancing-jailbreak-attack-and-defense/",
        )
        # 单位（括号）被剥离，只保留姓名
        self.assertEqual(
            first.authors,
            ("Licheng Pan", "Yunsheng Lu", "Jiexi Liu"),
        )

    def test_missing_authors_yields_empty_tuple(self):
        papers = parse_ndss_list(LIST_HTML, page_url=listing_url(2026))
        self.assertEqual(papers[2].authors, ())
        self.assertEqual(papers[2].title, "Paper Without Authors On Listing")

    def test_dedupes_repeated_links(self):
        doubled = LIST_HTML + LIST_HTML
        self.assertEqual(len(parse_ndss_list(doubled, page_url=listing_url(2026))), 3)

    def test_empty_html_returns_empty(self):
        self.assertEqual(parse_ndss_list("", page_url=""), ())


class ParseDetailTests(unittest.TestCase):
    def setUp(self):
        self.paper = parse_ndss_detail(
            DETAIL_HTML,
            page_url="https://www.ndss-symposium.org/ndss-paper/a-causal-perspective-for-enhancing-jailbreak-attack-and-defense/",
        )

    def test_title_from_h1(self):
        self.assertEqual(self.paper.title, "A Causal Perspective for Enhancing Jailbreak Attack and Defense")

    def test_authors_from_first_paragraph(self):
        self.assertEqual(self.paper.authors, ("Licheng Pan", "Yunsheng Lu", "Jiexi Liu"))

    def test_abstract_from_remaining_paragraphs_and_cleans_latex(self):
        self.assertIn("Uncovering the mechanisms", self.paper.abstract)
        self.assertIn("Causal Analyst", self.paper.abstract)  # textbf{} 已还原
        self.assertNotIn("textbf", self.paper.abstract)
        self.assertNotIn("<br", self.paper.abstract)

    def test_pdf_and_year(self):
        self.assertEqual(self.paper.official_pdf_url, "https://www.ndss-symposium.org/wp-content/uploads/2026-f797-paper.pdf")
        self.assertEqual(self.paper.year, 2026)  # body class category-ndss-2026

    def test_detail_without_title_raises(self):
        with self.assertRaises(ValueError):
            parse_ndss_detail("<html><body><div class='paper-data'><p>x</p></div></body></html>")

    def test_pdf_fallback_when_button_missing(self):
        html = DETAIL_HTML.replace('class="btn btn-light btn-sm pdf-button"', 'class="btn"')
        paper = parse_ndss_detail(html, page_url="https://www.ndss-symposium.org/ndss-paper/x/")
        self.assertEqual(paper.official_pdf_url, "https://www.ndss-symposium.org/wp-content/uploads/2026-f797-paper.pdf")


class UrlAllowlistTests(unittest.TestCase):
    def setUp(self):
        self.source = NdssAcceptedSource()

    def test_listing_url_pattern(self):
        self.assertEqual(listing_url(2026), "https://www.ndss-symposium.org/ndss2026/accepted-papers/")
        self.assertIsNotNone(self.source.listing_url_ok(listing_url(2025)))
        self.assertIsNone(self.source.listing_url_ok("https://www.ndss-symposium.org/ndss-paper/x/"))
        self.assertIsNone(self.source.listing_url_ok("https://evil.example/ndss2026/accepted-papers/"))

    def test_detail_url_rejects_arbitrary_urls(self):
        self.assertIsNotNone(self.source.detail_url_ok("https://www.ndss-symposium.org/ndss-paper/abc/"))
        for bad in ("https://evil.example/ndss-paper/abc/", "http://www.ndss-symposium.org/ndss-paper/abc/",
                    "https://www.ndss-symposium.org/other/abc/", "not-a-url"):
            self.assertIsNone(self.source.detail_url_ok(bad))

    def test_fetch_paper_detail_rejects_without_network(self):
        result = self.source.fetch_paper_detail("https://evil.example/ndss-paper/abc/")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], NDSS_DETAIL_URL_REJECTED)

    def test_fetch_paper_detail_network_failure_code(self):
        class _Boom:
            def get(self, *_args, **_kwargs):
                import httpx

                raise httpx.ConnectError("down")

        source = NdssAcceptedSource(client=_Boom())
        result = source.fetch_paper_detail("https://www.ndss-symposium.org/ndss-paper/abc/")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], NDSS_FETCH_FAILED)


class SourceFetchOfflineTests(unittest.TestCase):
    def test_fetch_listing_parses_injected_html(self):
        class _Fake:
            def get(self, url, **_kwargs):
                class R:
                    status_code = 200
                    text = LIST_HTML

                return R()

        source = NdssAcceptedSource(client=_Fake())
        papers, error = source.fetch_listing(2026)
        self.assertIsNone(error)
        self.assertEqual(len(papers or ()), 3)

    def test_discover_skips_failed_year(self):
        class _Fake:
            def get(self, url, **_kwargs):
                class R:
                    status_code = 200
                    text = LIST_HTML if "ndss2026" in url else ""

                return R()

        source = NdssAcceptedSource(client=_Fake())
        found = source.discover([2025, 2026])
        self.assertEqual(list(found), [2026])  # 2025 空页面不产出

    def test_normalize_identity(self):
        paper = NdssPaper(title="A Causal Perspective", article_url="u", year=2026)
        self.assertEqual(
            NdssAcceptedSource.normalize_identity(paper), "title:acausalperspective:2026"
        )


if __name__ == "__main__":
    unittest.main()
