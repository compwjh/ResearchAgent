from dataclasses import dataclass

import pytest

from backend.app.services.acm_paper_parser import (
    ACM_PARSE_FAILED,
    AcmPaperParseError,
    AcmPaperParser,
    parse_acm_page,
)


HTML = """
<html><head>
<meta name="citation_title" content="A Safe &amp; Useful Paper">
<meta name="citation_doi" content="doi:10.1145/1234567.1234568">
</head><body>
<a href="/doi/10.1145/1234567.1234568">article</a>
<a data-pdf-url="/doi/pdf/10.1145/1234567.1234568">Download PDF</a>
</body></html>
"""


def test_parse_html_extracts_canonical_metadata_and_allowlisted_urls():
    result = parse_acm_page(HTML)
    assert result.title == "A Safe & Useful Paper"
    assert result.doi == "10.1145/1234567.1234568"
    assert result.article_url == "https://dl.acm.org/doi/10.1145/1234567.1234568"
    assert result.pdf_url == "https://dl.acm.org/doi/pdf/10.1145/1234567.1234568"


@dataclass
class FakeRequest:
    url: str


class FakePage:
    url = "https://dl.acm.org/doi/10.1145/2222222.2222223"
    pdf_requests = [FakeRequest("https://dl.acm.org/doi/pdf/10.1145/2222222.2222223")]

    def content(self):
        return '<title>Page title</title><a href="/doi/10.1145/2222222.2222223">article</a>'


def test_fake_page_request_is_supported_and_parser_is_injectable():
    result = AcmPaperParser().parse(FakePage())
    assert result.pdf_url.endswith("/doi/pdf/10.1145/2222222.2222223")
    assert result.title == "Page title"


def test_non_acm_article_is_a_stable_parse_failure():
    with pytest.raises(AcmPaperParseError) as raised:
        parse_acm_page('<title>Title</title><a href="https://evil.example/doi/1">article</a><a href="/doi/pdf/10.1/x">pdf</a>')
    assert raised.value.code == ACM_PARSE_FAILED
    assert raised.value.retryable is True


@pytest.mark.parametrize("url", [
    "/doi/10.1/x?casa_token=secret",
    "/doi/pdf/10.1/x?token=secret",
])
def test_token_urls_are_ignored_and_never_returned(url):
    result = parse_acm_page(f'<title>Title</title><a href="/doi/10.1/x">article</a><a href="{url}">link</a>')
    assert result.pdf_url is None
    assert "secret" not in repr(result)


def test_dom_change_returns_stable_retryable_error_without_sensitive_details():
    with pytest.raises(AcmPaperParseError) as raised:
        parse_acm_page('<html><body><p>Access denied</p></body></html>')
    assert raised.value.code == "ACM_PARSE_FAILED"
    assert "cookie" not in repr(raised.value).lower()
    assert "authorization" not in repr(raised.value).lower()


def test_page_origin_must_be_exact_acm_origin():
    with pytest.raises(AcmPaperParseError) as raised:
        parse_acm_page(HTML, page_url="https://dl.acm.org.evil.example/doi/1")
    assert raised.value.code == ACM_PARSE_FAILED
