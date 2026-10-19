from xml.sax.saxutils import escape

import httpx

from backend.app.paper_discovery.infrastructure.arxiv_adapter import (
    ARXIV_API_URL,
    ArxivFallbackAdapter,
    normalize_arxiv_id,
)


def atom_entry(title, authors, year=2025, arxiv_id="2501.00001", pdf="https://arxiv.org/pdf/2501.00001"):
    people = "".join(f"<author><name>{escape(author)}</name></author>" for author in authors)
    return f"""<entry xmlns="http://www.w3.org/2005/Atom">
      <id>https://arxiv.org/abs/{arxiv_id}</id><title>{escape(title)}</title>
      {people}<published>{year}-01-02T00:00:00Z</published>
      <link title="pdf" type="application/pdf" href="{pdf}" />
    </entry>"""


def feed(*entries):
    return '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>"


def test_lookup_strictly_matches_and_preserves_arxiv_source_metadata():
    seen = []
    body = feed(atom_entry("A Secure Search", ["Ada Lovelace", "Grace Hopper"]))

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=body)

    result = ArxivFallbackAdapter(client=httpx.Client(transport=httpx.MockTransport(handler))).lookup(
        "A secure search", ["Grace Hopper", "Ada Lovelace"], 2025
    )

    assert result.matched
    assert result.match.arxiv_id == "2501.00001"
    assert result.match.source_kind == "arxiv"
    assert result.match.publication_stage == "prepublication"
    assert result.match.pdf_url == "https://arxiv.org/pdf/2501.00001"
    assert result.match.source_page_url == "https://arxiv.org/abs/2501.00001"
    assert seen[0].url == httpx.URL(ARXIV_API_URL, params={"search_query": 'ti:"A secure search"', "start": "0", "max_results": "20"})


def test_lookup_by_id_uses_exact_id_list_and_normalizes_versioned_identity():
    seen = []
    body = feed(atom_entry("A Secure Search", ["Ada Lovelace"], arxiv_id="2501.00001v2"))

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=body)

    result = ArxivFallbackAdapter(client=httpx.Client(transport=httpx.MockTransport(handler))).lookup_by_id(
        "arxiv:2501.00001v2", "A secure search", ["Ada Lovelace"], 2025
    )

    assert result.matched
    assert result.match.arxiv_id == "2501.00001v2"
    assert seen[0].url == httpx.URL(
        ARXIV_API_URL,
        params={"id_list": "2501.00001v2", "start": "0", "max_results": "20"},
    )
    assert normalize_arxiv_id("ARXIV:hep-th/9901001v3") == "hep-th/9901001v3"
    assert normalize_arxiv_id("https://arxiv.org/abs/2501.00001") is None
    assert normalize_arxiv_id("2501.00001&foo=bar") is None


def test_lookup_by_id_rejects_same_title_with_different_arxiv_id():
    body = feed(atom_entry("A Secure Search", ["Ada Lovelace"], arxiv_id="2501.00002"))
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))

    result = ArxivFallbackAdapter(client=client).lookup_by_id(
        "2501.00001", "A Secure Search", ["Ada Lovelace"], 2025
    )

    assert not result.matched
    assert result.code == "ARXIV_IDENTITY_CONFLICT"


def test_lookup_by_id_rejects_metadata_conflict_for_exact_arxiv_id():
    body = feed(atom_entry("A Different Search", ["Someone Else"], arxiv_id="2501.00001"))
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))

    result = ArxivFallbackAdapter(client=client).lookup_by_id(
        "2501.00001", "A Secure Search", ["Ada Lovelace"], 2025
    )

    assert not result.matched
    assert result.code == "ARXIV_IDENTITY_CONFLICT"


def test_lookup_rejects_title_author_year_mismatches_and_unsafe_links():
    body = feed(
        atom_entry("A Secure Search Extra", ["Ada Lovelace"], year=2025, arxiv_id="2501.00002"),
        atom_entry("A Secure Search", ["Someone Else"], year=2025, arxiv_id="2501.00003"),
        atom_entry("A Secure Search", ["Ada Lovelace"], year=2024, arxiv_id="2401.00004"),
        atom_entry("A Secure Search", ["Ada Lovelace"], arxiv_id="2501.00005", pdf="http://arxiv.org/pdf/2501.00005"),
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))
    result = ArxivFallbackAdapter(client=client).lookup("A Secure Search", ["Ada Lovelace"], 2025)
    assert not result.matched
    assert result.code == "ARXIV_MATCH_UNCERTAIN"


def test_lookup_skips_when_usenix_pdf_exists_and_caches_results():
    calls = []
    clock = [0.0]

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=feed(atom_entry("Cached Paper", ["Ada"])))

    def sleep(seconds):
        clock[0] += seconds

    adapter = ArxivFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)), now=lambda: clock[0], sleep=sleep
    )
    assert adapter.lookup("Cached Paper", ["Ada"], 2025, usenix_pdf_available=True).code == "USENIX_PDF_AVAILABLE"
    assert adapter.lookup("Cached Paper", ["Ada"], 2025).matched
    assert adapter.lookup("Cached Paper", ["Ada"], 2025).matched
    assert len(calls) == 1


def test_lookup_retries_transient_failure_with_finite_attempts_and_throttles():
    calls = []
    clock = [0.0]
    responses = [httpx.Response(503), httpx.Response(200, text=feed(atom_entry("Retry Paper", ["Ada"]))) ]

    def handler(request):
        calls.append(clock[0])
        return responses.pop(0)

    def sleep(seconds):
        clock[0] += seconds

    adapter = ArxivFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)), retries=1, backoff=0.1,
        now=lambda: clock[0], sleep=sleep,
    )
    assert adapter.lookup("Retry Paper", ["Ada"], 2025).matched
    assert len(calls) == 2
    assert calls[1] - calls[0] >= 3.0
