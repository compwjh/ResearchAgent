import httpx

from backend.app.domain.paper_discovery import ConferenceSource
from backend.app.services.arxiv_adapter import ArxivFallbackResult, ArxivMatch
from backend.app.services.paper_discovery_search import PaperDiscoverySearchService
from backend.app.services.usenix_publication_source import UsenixAcceptedSource


SOURCE = ConferenceSource("usenix-security", "USENIX Security Symposium", "USENIX Security", "conf/uss", ["USENIX Security"], built_in=True)
ROUTED_SOURCE = ConferenceSource(
    "usenix-security", "USENIX Security Symposium", "USENIX Security", "conf/uss", ["USENIX Security"],
    built_in=True,
    discovery_routes=[{"route_type": "usenix_accepted", "enabled": True,
                       "rate_limit_seconds": 0.5,
                       "listing_url_template": "https://www.usenix.org/conference/usenixsecurity{yy}/cycle{cycle}-accepted-papers"}],
)
LIST = "https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers"
DETAIL = "https://www.usenix.org/conference/usenixsecurity25/presentation/demo"
DETAIL_HTML = '<meta name="citation_title" content="Secure Search"><meta name="citation_author" content="Ada Lovelace"><meta name="citation_publication_date" content="2025-01-01"><a href="/official.pdf">PDF</a><a href="/prepub.pdf">Prepublication PDF</a>'
PUBLIC = "93.184.216.34"


def valid_pdf():
    import fitz
    document = fitz.open()
    document.new_page()
    body = document.tobytes()
    document.close()
    return body


class FakeArxiv:
    def __init__(self, result):
        self.result, self.calls = result, []

    def lookup(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


def test_source_prefers_official_then_prepublication_without_arxiv():
    def handler(request):
        if request.url == httpx.URL(LIST):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if request.url.path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        if request.url.path.endswith("official.pdf"):
            return httpx.Response(200, content=b"%PDF-1.7 official")
        return httpx.Response(404)

    arxiv = FakeArxiv(ArxivFallbackResult(code="ARXIV_MATCH_UNCERTAIN"))
    source = UsenixAcceptedSource(client=httpx.Client(transport=httpx.MockTransport(handler)), arxiv_adapter=arxiv,
                                  dns_resolver=lambda _host: [PUBLIC], pdf_page_validator=lambda _path: 1)
    result = source.search(SOURCE, "secure", [2025])
    assert result.records[0]["info"]["pdf_url"].endswith("official.pdf")
    assert result.records[0]["info"]["publication_stage"] == "accepted"
    assert not arxiv.calls


def test_source_falls_back_to_arxiv_only_after_both_usenix_pdfs_fail():
    match = ArxivMatch("2601.1", "Secure Search", ("Ada Lovelace",), 2025, "https://arxiv.org/pdf/2601.1", "https://arxiv.org/abs/2601.1", 1.0)
    def handler(request):
        if request.url == httpx.URL(LIST):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if request.url.path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(503)
    arxiv = FakeArxiv(ArxivFallbackResult(match=match))
    result = UsenixAcceptedSource(client=httpx.Client(transport=httpx.MockTransport(handler)), arxiv_adapter=arxiv,
                                  dns_resolver=lambda _host: [PUBLIC], pdf_page_validator=lambda _path: 1).search(SOURCE, "secure", [2025])
    info = result.records[0]["info"]
    assert info["source_kind"] == "arxiv" and info["arxiv_id"] == "2601.1"
    assert info["publication_stage"] == "prepublication"
    assert len(arxiv.calls) == 1


class MemoryStore:
    def __init__(self): self.saved = None
    def list_conferences(self): return [SOURCE]
    def save_search(self, session, candidates): self.saved = (session, list(candidates))


def test_search_publication_scope_routes_accepted_without_calling_dblp():
    class FailDBLP:
        def search(self, *args, **kwargs): raise AssertionError("published route called")
    accepted = type("Accepted", (), {"search": lambda self, *a, **k: type("R", (), {"records": ({"info": {"title": "Secure Search", "year": 2026, "authors": ["Ada"], "url": DETAIL, "pdf_url": "https://www.usenix.org/official.pdf", "publication_stage": "accepted", "source_kind": "usenix_accepted"}},), "warnings": (), "error_code": None})()})()
    result = PaperDiscoverySearchService(dblp_source=FailDBLP(), accepted_source=accepted, store=MemoryStore()).search(SOURCE, "secure", [2025], publication_scope="accepted")
    assert result.candidates[0].publication_stage == "accepted"
    assert result.candidates[0].source_kind == "usenix_accepted"


def test_route_cache_avoids_repeated_listing_detail_and_pdf_requests():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url == httpx.URL(LIST):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if request.url.path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(200, content=b"%PDF-1.7 valid")

    clock = [0.0]
    sleeps = []
    source = UsenixAcceptedSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        dns_resolver=lambda _host: [PUBLIC],
        arxiv_adapter=FakeArxiv(ArxivFallbackResult(code="ARXIV_MATCH_UNCERTAIN")), pdf_page_validator=lambda _path: 1,
        now=lambda: clock[0], sleep=lambda value: (sleeps.append(value), clock.__setitem__(0, clock[0] + value)),
    )
    first = source.search(ROUTED_SOURCE, "secure", [2025])
    second = source.search(ROUTED_SOURCE, "secure", [2025])
    assert first.records == second.records and calls == [
        "/conference/usenixsecurity25/cycle1-accepted-papers", "/conference/usenixsecurity25/presentation/demo",
        "/official.pdf",
    ]
    assert sleeps and min(sleeps) >= 0.5


def test_probe_rejects_pseudo_pdf_and_falls_back_to_prepublication():
    def handler(request):
        if request.url == httpx.URL(LIST):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if request.url.path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        if request.url.path.endswith("official.pdf"):
            return httpx.Response(200, content=b"%PDFx forged")
        return httpx.Response(200, content=b"%PDF-1.7 prepublication")

    source = UsenixAcceptedSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)), dns_resolver=lambda _host: [PUBLIC],
        pdf_page_validator=lambda _path: 1,
    )
    result = source.search(ROUTED_SOURCE, "secure", [2025])
    info = result.records[0]["info"]
    assert info["pdf_url"].endswith("prepub.pdf") and info["publication_stage"] == "prepublication"


def test_probe_page_validation_rejects_truncated_pdf_before_arxiv_fallback():
    def handler(request):
        if request.url == httpx.URL(LIST):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if request.url.path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        if request.url.path.endswith("official.pdf"):
            return httpx.Response(200, content=b"%PDF-1.7\ntruncated")
        return httpx.Response(200, content=valid_pdf())

    arxiv = FakeArxiv(ArxivFallbackResult(code="ARXIV_MATCH_UNCERTAIN"))
    source = UsenixAcceptedSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)), dns_resolver=lambda _host: [PUBLIC],
        arxiv_adapter=arxiv,
    )
    result = source.search(ROUTED_SOURCE, "secure", [2025])
    assert result.records[0]["info"]["pdf_url"].endswith("prepub.pdf")
    assert result.records[0]["info"]["publication_stage"] == "prepublication"
    assert not arxiv.calls


def test_probe_rejects_oversized_and_redirected_pdf_without_following_target():
    reached = []

    def handler(request):
        reached.append(str(request.url))
        if request.url == httpx.URL(LIST):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if request.url.path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        if request.url.path.endswith("official.pdf"):
            return httpx.Response(302, headers={"Location": "https://evil.example/secret.pdf"})
        return httpx.Response(200, headers={"Content-Length": str(64 * 1024 * 1024 + 1)}, content=b"%PDF-1.7")

    source = UsenixAcceptedSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        dns_resolver=lambda _host: [PUBLIC], pdf_page_validator=lambda _path: 1,
    )
    result = source.search(ROUTED_SOURCE, "secure", [2025])
    assert result.records[0]["info"]["pdf_url"] is None
    assert not any("evil.example" in url for url in reached)
