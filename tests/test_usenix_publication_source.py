from types import SimpleNamespace

import httpx

import backend.app.paper_discovery.infrastructure.usenix_publication_source as usenix_source_module
from backend.app.paper_discovery.application.paper_discovery_search import PaperDiscoverySearchService
from backend.app.paper_discovery.domain.paper_discovery import ConferenceSource, SearchJob
from backend.app.paper_discovery.infrastructure.arxiv_adapter import ArxivFallbackResult, ArxivMatch
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.usenix_publication_source import UsenixAcceptedSource

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


# --- Spec-015: per-year cycle slug resolution (URL defect regression) -------
#
# 2022-2024 only serve ``summer``/``fall``; 2025+ serves ``cycle1``.  The
# historical ROUTED_SOURCE template bakes a literal ``cycle`` prefix into the
# placeholder (``cycle{cycle}-accepted-papers``), which historically produced
# nonsense such as ``cyclecycle1`` / ``cyclesummer``.  These guards pin the
# fixed behavior.

SEC24_SUMMER = "https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers"
SEC24_FALL = "https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers"
SEC24_CYCLE1 = "https://www.usenix.org/conference/usenixsecurity24/cycle1-accepted-papers"
SEC25_CYCLE1 = "https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers"


def _source(handler, **kwargs):
    base = {"client": httpx.Client(transport=httpx.MockTransport(handler)),
                "dns_resolver": lambda _host: [PUBLIC], "pdf_page_validator": lambda _path: 1,
                "sleep": lambda _v: None}
    base.update(kwargs)
    return UsenixAcceptedSource(**base)


def test_sync_unit_ensures_new_fetch_unit_before_acquire(monkeypatch):
    calls = []

    class Store:
        def __init__(self):
            self.unit = None

        def get_fetch_unit(self, unit_id):
            return self.unit if self.unit and self.unit.fetch_unit_id == unit_id else None

        def ensure_fetch_unit(self, unit, now):
            calls.append("ensure")
            self.unit = unit
            return True

        def acquire_fetch_unit(self, unit_id, owner, lease_seconds, now):
            calls.append("acquire")
            assert self.get_fetch_unit(unit_id) is not None
            return True

        def save_fetch_unit(self, unit, now):
            calls.append("save")
            self.unit = unit

    source = _source(lambda _request: httpx.Response(200, text=""))
    source.store = Store()
    monkeypatch.setattr(source, "_fetch_listing", lambda _listing: ("<html>", None))
    monkeypatch.setattr(usenix_source_module, "parse_accepted_papers", lambda _text, page_url: ())
    result = SimpleNamespace(completed=[], failed=[], cached=[], paper_count=0)

    source._sync_one_page(
        "search-ensure", "usenix-security", SEC24_SUMMER, "owner", 300,
        "2026-01-01T00:00:00Z", result, None,
    )

    assert calls[:2] == ["ensure", "acquire"]
    assert result.completed == ["usenix|usenix-security|/conference/usenixsecurity24/summer-accepted-papers/"]


def test_default_year_2024_resolves_summer_and_fall_not_cycle1():
    reached = []

    def handler(request):
        reached.append(str(request.url))
        return httpx.Response(404)

    source = _source(handler)
    result = source.search(ROUTED_SOURCE, "secure", [2024])
    assert SEC24_SUMMER in reached
    assert SEC24_FALL in reached
    assert SEC24_CYCLE1 not in reached
    # Both slugs 404 -> the whole year is unavailable, but that is not the point
    # of this guard; the point is which URLs the resolver requested.
    assert result.error_code == "USENIX_UNAVAILABLE"


def test_default_year_2025_resolves_cycle1():
    reached = []

    def handler(request):
        reached.append(str(request.url))
        return httpx.Response(404)

    source = _source(handler)
    source.search(ROUTED_SOURCE, "secure", [2025])
    assert SEC25_CYCLE1 in reached
    assert all("cycle1-accepted-papers" in url for url in reached)


def test_listing_url_normalizes_bare_and_full_cycle_slugs_without_double_prefix():
    route = {"listing_url_template": "https://www.usenix.org/conference/usenixsecurity{yy}/cycle{cycle}-accepted-papers"}
    source = _source(lambda _request: httpx.Response(404))

    bare = source._listing_url(route, 2024, "1")
    full = source._listing_url(route, 2024, "cycle1")
    legacy = source._listing_url(route, 2024, "summer")

    assert bare == "https://www.usenix.org/conference/usenixsecurity24/cycle1-accepted-papers"
    assert full == "https://www.usenix.org/conference/usenixsecurity24/cycle1-accepted-papers"
    assert legacy == "https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers"
    for url in (bare, full, legacy):
        assert "cyclecycle" not in url
        assert "cyclesummer" not in url


def test_partial_slug_failure_keeps_year_available():
    def handler(request):
        path = request.url.path
        if path.endswith("summer-accepted-papers"):
            return httpx.Response(404)
        if path.endswith("fall-accepted-papers"):
            return httpx.Response(200, text=f'<a href="{DETAIL}">paper</a>')
        if path.endswith("/presentation/demo"):
            return httpx.Response(200, text=DETAIL_HTML)
        if path.endswith("official.pdf"):
            return httpx.Response(200, content=b"%PDF-1.7 official")
        return httpx.Response(404)

    source = _source(handler)
    result = source.search(ROUTED_SOURCE, "secure", [2024])
    assert len(result.records) == 1
    assert result.records[0]["info"]["publication_stage"] == "accepted"
    assert result.error_code != "USENIX_UNAVAILABLE"


def test_sync_usenix_partial_pages_persists_legal_progress_status(tmp_path):
    def handler(request):
        path = request.url.path
        if path.endswith("summer-accepted-papers"):
            return httpx.Response(404)
        if path.endswith("fall-accepted-papers"):
            return httpx.Response(200, text=f'<a href="{SEC24_DETAIL}">paper</a>')
        if path.endswith("/presentation/demo"):
            return httpx.Response(200, text=SEC24_DETAIL_HTML)
        if path.endswith("official.pdf"):
            return httpx.Response(200, content=b"%PDF-1.7 official")
        return httpx.Response(404)

    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-usenix-partial", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    source = _source(handler)
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = source.sync_usenix_units(
        job.search_id, "usenix-security", [2024], owner="worker",
        now="2099-01-01T00:00:00Z",
    )

    assert result.status == "partial"
    progress = store.get_source_progress(job.search_id)
    assert progress and progress[0].status in {"fetching", "merging"}
    assert store.get_search_job(job.search_id).status == "partial"


def test_usenix_http_failure_releases_lease_for_retry_after_restart(tmp_path):
    store_path = tmp_path / "state.sqlite3"
    store = PaperDiscoveryStore(store_path)
    job = SearchJob(
        "search-usenix-failure-retry", "secure", ["usenix-security"], [2025],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    source = _source(lambda _request: httpx.Response(503))
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = source.sync_usenix_units(
        job.search_id, "usenix-security", [2025], owner="worker-a",
        lease_seconds=300, now="2099-01-01T00:00:00Z",
    )

    unit_id = "usenix|usenix-security|/conference/usenixsecurity25/cycle1-accepted-papers/"
    assert result.status == "failed"
    failed = store.get_fetch_unit(unit_id)
    assert failed and failed.status == "failed"
    assert failed.lease_owner is None and failed.lease_expires_at is None

    # A fresh store instance models a worker restart; the failed unit must be
    # immediately claimable instead of being permanently owned by worker-a.
    restarted_store = PaperDiscoveryStore(store_path)
    assert restarted_store.acquire_fetch_unit(
        unit_id, "worker-b", 300, now="2099-01-01T00:00:01Z"
    )


def test_usenix_exception_releases_lease_for_retry_after_restart(tmp_path, monkeypatch):
    store_path = tmp_path / "state.sqlite3"
    store = PaperDiscoveryStore(store_path)
    job = SearchJob(
        "search-usenix-exception-retry", "secure", ["usenix-security"], [2025],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    source = _source(lambda _request: httpx.Response(200, text="<html>"))
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)
    monkeypatch.setattr(source, "_fetch_listing", lambda _listing: (_ for _ in ()).throw(RuntimeError("boom")))

    result = source.sync_usenix_units(
        job.search_id, "usenix-security", [2025], owner="worker-a",
        lease_seconds=300, now="2099-01-01T00:00:00Z",
    )

    unit_id = "usenix|usenix-security|/conference/usenixsecurity25/cycle1-accepted-papers/"
    assert result.status == "failed"
    failed = store.get_fetch_unit(unit_id)
    assert failed and failed.lease_owner is None and failed.lease_expires_at is None

    restarted_store = PaperDiscoveryStore(store_path)
    assert restarted_store.acquire_fetch_unit(
        unit_id, "worker-b", 300, now="2099-01-01T00:00:01Z"
    )


def test_all_slugs_failed_marks_unavailable():
    def handler(request):
        path = request.url.path
        if path.endswith("summer-accepted-papers") or path.endswith("fall-accepted-papers"):
            return httpx.Response(404)
        return httpx.Response(404)

    source = _source(handler)
    result = source.search(ROUTED_SOURCE, "secure", [2024])
    assert result.records == ()
    assert result.error_code == "USENIX_UNAVAILABLE"


def test_discovered_pages_maps_year_to_cycle_slugs():
    source = _source(lambda _request: httpx.Response(404))
    pages = source._discovered_pages("usenix-security", [2024, 2025])
    assert SEC24_SUMMER in pages
    assert SEC24_FALL in pages
    assert SEC25_CYCLE1 in pages
    assert SEC24_CYCLE1 not in pages


# --- Spec-015 regression guards: legacy/template path & out-of-range years ---
#
# The 2024 scenario must use its own detail fixtures so a 2025-year constant
# (DETAIL/DETAIL_HTML) does not bleed its 2025 publication date into a 2024
# listing. These constants pin the year explicitly.
SEC24_DETAIL = "https://www.usenix.org/conference/usenixsecurity24/presentation/demo"
SEC24_DETAIL_HTML = ('<meta name="citation_title" content="Secure Search">'
                     '<meta name="citation_author" content="Ada Lovelace">'
                     '<meta name="citation_publication_date" content="2024-01-01">'
                     '<a href="/official.pdf">PDF</a>'
                     '<a href="/prepub.pdf">Prepublication PDF</a>')
SEC24_CYCLE2 = "https://www.usenix.org/conference/usenixsecurity24/cycle2-accepted-papers"


def test_listing_for_applies_template_to_summer_slug():
    route = ROUTED_SOURCE.discovery_routes[0]
    source = _source(lambda _request: httpx.Response(404))
    result = source._listing_for(SEC24_SUMMER, route)
    assert result == SEC24_SUMMER
    assert "cyclesummer" not in result
    assert "-accepted-papers-accepted-papers" not in result


def test_listing_for_returns_original_page_without_template():
    source = _source(lambda _request: httpx.Response(404))
    assert source._listing_for(SEC24_SUMMER, {}) == SEC24_SUMMER
    other = "https://www.usenix.org/other/page"
    assert source._listing_for(other, ROUTED_SOURCE.discovery_routes[0]) == other


def test_explicit_cycle_requests_only_that_cycle():
    reached = []

    def handler(request):
        reached.append(str(request.url))
        return httpx.Response(404)

    source = _source(handler)
    source.search(ROUTED_SOURCE, "secure", [2024], cycle="2")
    assert SEC24_CYCLE2 in reached
    assert not any("summer" in url for url in reached)
    assert not any("fall" in url for url in reached)


def test_explicit_cycle1_matches_default_behavior():
    def make():
        reached = []

        def handler(request):
            reached.append(str(request.url))
            return httpx.Response(404)

        return _source(handler), reached

    source_explicit, reached_explicit = make()
    source_explicit.search(ROUTED_SOURCE, "secure", [2024], cycle="cycle1")

    source_default, reached_default = make()
    source_default.search(ROUTED_SOURCE, "secure", [2024])

    assert set(reached_explicit) == set(reached_default)
    assert SEC24_SUMMER in reached_explicit
    assert SEC24_FALL in reached_explicit
    assert SEC24_CYCLE1 not in reached_explicit


def test_out_of_range_year_generates_no_listing():
    source = _source(lambda _request: httpx.Response(404))
    pages = source._discovered_pages("usenix-security", [2021, 2024])
    assert not any("usenixsecurity21" in url for url in pages)
    assert SEC24_SUMMER in pages
    assert SEC24_FALL in pages

    reached = []

    def handler(request):
        reached.append(str(request.url))
        return httpx.Response(404)

    out = _source(handler)
    out.search(ROUTED_SOURCE, "secure", [2021])
    assert reached == []


def test_only_out_of_range_years_marks_unavailable():
    def handler(request):
        raise AssertionError("out-of-range year must not fetch any listing")

    source = _source(handler)
    result = source.search(ROUTED_SOURCE, "secure", [2021])
    assert result.records == ()
    assert result.error_code == "USENIX_UNAVAILABLE"


def test_out_of_range_year_does_not_pollute_successful_search():
    reached = []

    def handler(request):
        reached.append(str(request.url))
        path = request.url.path
        if path.endswith("summer-accepted-papers"):
            return httpx.Response(404)
        if path.endswith("fall-accepted-papers"):
            return httpx.Response(200, text=f'<a href="{SEC24_DETAIL}">paper</a>')
        if path.endswith("/presentation/demo"):
            return httpx.Response(200, text=SEC24_DETAIL_HTML)
        if path.endswith("official.pdf"):
            return httpx.Response(200, content=b"%PDF-1.7 official")
        return httpx.Response(404)

    source = _source(handler)
    result = source.search(ROUTED_SOURCE, "secure", [2021, 2024])
    assert len(result.records) == 1
    assert result.error_code is None
    assert "USENIX_UNAVAILABLE" not in result.warnings
    assert not any("usenixsecurity21" in url for url in reached)
