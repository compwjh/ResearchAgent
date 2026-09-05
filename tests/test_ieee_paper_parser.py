from __future__ import annotations

import pytest

from backend.app.services.ieee_paper_parser import (
    IEEE_PARSE_FAILED,
    IEEEPaperParseError as ParseError,
    IEEEPaperParser,
    parse_ieee_page,
)

PAGE_URL = "https://ieeexplore.ieee.org/document/1234567"
HTML = """
<html><head>
  <meta name="citation_title" content="A Secure Paper Title">
  <meta name="citation_doi" content="10.1109/SP.2025.1234567">
  <link rel="canonical" href="/document/1234567">
</head><body>
  <h1>A Secure Paper Title</h1>
  <a href="/stamp/stamp.jsp?tp=&amp;arnumber=1234567">PDF</a>
</body></html>
"""


def test_parse_html_extracts_metadata_and_relative_pdf_url():
    paper = parse_ieee_page(HTML, PAGE_URL)
    assert paper.title == "A Secure Paper Title"
    assert paper.doi == "10.1109/SP.2025.1234567"
    assert paper.article_url == PAGE_URL
    assert paper.pdf_url == "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=1234567"
    assert paper.pdf_access == "public"


def test_html_title_branding_is_removed_when_no_citation_title():
    paper = IEEEPaperParser().parse_html(
        '<title>Another Paper | IEEE Xplore Digital Library</title>', page_url=PAGE_URL
    )
    assert paper.title == "Another Paper"
    assert paper.pdf_url is None


@pytest.mark.parametrize(
    "url",
    [
        "http://ieeexplore.ieee.org/document/1",
        "https://ieeexplore.ieee.org.evil.example/document/1",
        "https://ieeexplore.ieee.org:443/document/1",
        "https://evil.example/paper.pdf",
    ],
)
def test_exact_ieee_https_origin_is_required(url):
    page = '<meta name="citation_title" content="Paper"><a href="' + url + '">PDF</a>'
    with pytest.raises(ParseError) as error:
        IEEEPaperParser().parse_html(page, page_url=PAGE_URL)
    assert error.value.code == IEEE_PARSE_FAILED
    assert error.value.retryable is True

def test_authentication_query_is_rejected_without_echoing_url():
    page = '<meta name="citation_title" content="Paper"><meta name="citation_pdf_url" content="/stamp/stamp.jsp?token=secret">'
    with pytest.raises(ParseError) as error:
        IEEEPaperParser().parse_html(page, page_url=PAGE_URL)
    assert error.value.code == IEEE_PARSE_FAILED
    assert "token" not in str(error.value).lower()


class FakeRequest:
    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.method = "GET"
        self.headers = headers or {}


class FakePage:
    url = PAGE_URL
    pdf_requests = [FakeRequest("/stamp/stamp.jsp?tp=&arnumber=1234567", {"Accept": "application/pdf"})]

    def content(self):
        return HTML


def test_fake_page_and_captured_pdf_request_are_supported():
    paper = IEEEPaperParser().parse_page(FakePage())
    assert paper.pdf_url.endswith("arnumber=1234567")


def test_credentials_in_captured_request_are_rejected():
    page = FakePage()
    page.pdf_requests = [FakeRequest("/stamp/stamp.jsp?tp=&arnumber=1234567", {"Cookie": "session=secret"})]
    with pytest.raises(ParseError) as error:
        IEEEPaperParser().parse_page(page)
    assert error.value.code == IEEE_PARSE_FAILED


def test_dom_change_has_stable_retryable_error():
    with pytest.raises(ParseError) as error:
        IEEEPaperParser().parse_html("<html><body><div>not an article</div></body></html>", page_url=PAGE_URL)
    assert error.value.code == IEEE_PARSE_FAILED
    assert error.value.retryable is True
