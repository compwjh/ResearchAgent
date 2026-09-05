import pytest

from backend.app.services.usenix_paper_parser import (
    USENIX_PARSE_FAILED,
    UsenixAcceptedParser,
    UsenixPaperParseError,
    parse_accepted_listing,
    parse_usenix_detail,
)


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
