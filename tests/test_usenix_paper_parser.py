import pathlib
import textwrap

import pytest

from backend.app.services.usenix_paper_parser import (
    USENIX_PARSE_FAILED,
    UsenixAcceptedParser,
    UsenixPaperParseError,
    parse_accepted_listing,
    parse_accepted_papers,
    parse_usenix_detail,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "usenix"


LISTING_URL = "https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
DETAIL_URL = "https://www.usenix.org/conference/usenixsecurity26/presentation/peng-jiaqian"
LISTING_HTML = """
<main>
  <a href="/conference/usenixsecurity26/presentation/peng-jiaqian">Paper title</a>
  <a href="/conference/usenixsecurity26/presentation/peng-jiaqian">Duplicate</a>
  <a href="/conference/usenixsecurity26/program">Program</a>
  <a href="https://evil.example/presentation/not-usenix">External</a>
  <a href="/conference/usenixsecurity26/presentation/with-query?token=secret">Token</a>
</main>
"""
DETAIL_HTML = """
<html><head>
  <meta name="citation_title" content="A Secure Accepted Paper">
  <meta name="citation_author" content="Alice Example">
  <meta name="citation_author" content="Bob Researcher">
  <meta name="citation_publication_date" content="2026-05-01">
</head><body>
  <a href="/system/files/usenixsecurity26-peng-jiaqian.pdf">PDF</a>
  <a href="/system/files/conference/usenixsecurity26/sec26_prepub_peng-jiaqian.pdf">Prepublication PDF</a>
  <a href="https://evil.example/paper.pdf">External PDF</a>
  <a href="/system/files/leak.pdf?token=secret">Token PDF</a>
</body></html>
"""


def test_listing_extracts_only_explicit_presentation_links_and_deduplicates():
    assert parse_accepted_listing(LISTING_HTML, page_url=LISTING_URL) == (
        DETAIL_URL,
    )


def test_detail_extracts_metadata_and_both_explicit_pdf_variants():
    paper = parse_usenix_detail(DETAIL_HTML, page_url=DETAIL_URL)

    assert paper.article_url == DETAIL_URL
    assert paper.title == "A Secure Accepted Paper"
    assert paper.authors == ("Alice Example", "Bob Researcher")
    assert paper.year == 2026
    assert paper.official_pdf_url == "https://www.usenix.org/system/files/usenixsecurity26-peng-jiaqian.pdf"
    assert paper.prepublication_pdf_url == (
        "https://www.usenix.org/system/files/conference/usenixsecurity26/sec26_prepub_peng-jiaqian.pdf"
    )
    assert paper.pdf_url == paper.official_pdf_url
    assert paper.pdf_access == "public"
    assert paper.publication_stage == "accepted"
    assert paper.source_kind == "usenix_accepted"


def test_detail_supports_explicit_author_markup():
    html = """
    <h1>Markup Authors</h1><time datetime="2025-08-01"></time>
    <span class="author">Ada Lovelace</span><span itemprop="author">Grace Hopper</span>
    """
    paper = parse_usenix_detail(html, page_url=DETAIL_URL)
    assert paper.title == "Markup Authors"
    assert paper.authors == ("Ada Lovelace", "Grace Hopper")
    assert paper.year == 2025


def test_parser_rejects_non_usenix_page_without_echoing_sensitive_url():
    with pytest.raises(UsenixPaperParseError) as error:
        parse_usenix_detail(
            DETAIL_HTML,
            page_url="https://www.usenix.org/conference/usenixsecurity26/presentation/peng?token=secret",
        )
    assert error.value.code == USENIX_PARSE_FAILED
    assert "secret" not in repr(error.value)


def test_object_parser_matches_functional_entry_points():
    parser = UsenixAcceptedParser()
    assert parser.parse_listing(LISTING_HTML, page_url=LISTING_URL) == (DETAIL_URL,)
    assert parser.parse_detail(DETAIL_HTML, page_url=DETAIL_URL).title == "A Secure Accepted Paper"
    assert parser.parse_papers(FIXTURE_DIR.joinpath("cycle1-accepted-papers.html").read_text("utf-8"),
                                page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers")


def _load(name: str) -> str:
    return textwrap.dedent(FIXTURE_DIR.joinpath(name).read_text("utf-8")).strip()


def test_cycle1_papers_extract_title_authors_abstract_and_year():
    papers = parse_accepted_papers(
        _load("cycle1-accepted-papers.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers",
    )
    assert [paper.title for paper in papers] == ["Cycle One Title", "Carol On Networks"]
    first = papers[0]
    assert first.article_url == "https://www.usenix.org/conference/usenixsecurity26/presentation/alice-secure"
    assert first.authors == ("Alice Example", "Bob Researcher")
    assert first.abstract == (
        "This paper studies secure systems and mentions keywords in the abstract text."
    )
    assert first.year == 2026
    assert papers[1].authors == ("Carol Danvers",)


def test_listing_papers_have_no_pdf_and_empty_keywords():
    papers = parse_accepted_papers(
        _load("cycle1-accepted-papers.html"),
        page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers",
    )
    for paper in papers:
        assert paper.official_pdf_url is None
        assert paper.prepublication_pdf_url is None
        assert paper.pdf_url is None
        assert paper.pdf_access == "unknown"
        assert paper.keywords == ()


@pytest.mark.parametrize(
    "name,page_url,title,year",
    [
        (
            "usenixsecurity25-cycle1-accepted-papers.html",
            "https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers",
            "Dave Accepted In 2025",
            2025,
        ),
        (
            "usenixsecurity24-summer-accepted-papers.html",
            "https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers",
            "Summer One",
            2024,
        ),
        (
            "usenixsecurity24-fall-accepted-papers.html",
            "https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers",
            "Fall First",
            2024,
        ),
    ],
)
def test_cycle_summer_and_fall_layouts_parse(name, page_url, title, year):
    papers = parse_accepted_papers(_load(name), page_url=page_url)
    assert papers[0].title == title
    assert papers[0].year == year
    assert papers[0].abstract
    assert papers[0].keywords == ()


def test_cross_year_presentation_link_is_skipped():
    markup = textwrap.dedent(
        """
        <main>
        <article class="node node-paper view-mode-schedule">
        <h2><a href="/conference/usenixsecurity25/presentation/stale">Stale Reference</a></h2>
        <p class="field-paper-people-text">Old Guard</p>
        <p class="field-paper-description-long">A paper that must not be picked up.</p>
        </article>
        </main>
        """
    )
    papers = parse_accepted_papers(
        markup, page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers"
    )
    assert papers == ()


def test_non_usenix_listing_page_raises_without_echoing_token():
    with pytest.raises(UsenixPaperParseError) as error:
        parse_accepted_papers(
            _load("cycle1-accepted-papers.html"),
            page_url="https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers?token=secret",
        )
    assert error.value.code == USENIX_PARSE_FAILED
    assert "secret" not in repr(error.value)
