import hashlib
import re
from types import SimpleNamespace

import httpx

import backend.app.paper_discovery.infrastructure.usenix_publication_source as usenix_source_module
from backend.app.paper_discovery.application.paper_discovery_search import PaperDiscoverySearchService
from backend.app.paper_discovery.domain.paper_discovery import ConferenceSource, SearchJob
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_title
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
    assert source.store.unit.year == 2024
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
    assert failed.year == 2025
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


# --- Spec-032.1 Task03: presentation detail fetch unit (abstract backfill) ----
#
# The accepted-paper listing carries no abstract, so the sync stage adds a
# second, lease-guarded unit per presentation page.  Every guard below uses an
# injected fake client/store; none of them touches the real network.

LISTING_24 = "https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers"
UNIT_24 = "usenix|usenix-security|/conference/usenixsecurity24/summer-accepted-papers/"
FALL_UNIT_24 = "usenix|usenix-security|/conference/usenixsecurity24/fall-accepted-papers/"
PAPER_A = "https://www.usenix.org/conference/usenixsecurity24/presentation/alpha"
PAPER_B = "https://www.usenix.org/conference/usenixsecurity24/presentation/beta"
DETAIL_A = "usenix|usenix-security|/conference/usenixsecurity24/presentation/alpha|detail"
DETAIL_B = "usenix|usenix-security|/conference/usenixsecurity24/presentation/beta|detail"
ABSTRACT_A = "Alpha studies collaborative perception under partial observability."
ABSTRACT_B = "Beta studies verifiable scheduling across untrusted hosts."
# Mirrors the real schedule layout: the presentation href sits inside <h2> and
# is a same-origin relative path, exactly like the published markup.
PAPER_A_PATH = "/conference/usenixsecurity24/presentation/alpha"
PAPER_B_PATH = "/conference/usenixsecurity24/presentation/beta"


def _listing_block(title, author, href, abstract=""):
    description = (f'<p class="field-paper-description-long">{abstract}</p>') if abstract else ""
    return (
        '<article class="node node-paper view-mode-schedule">'
        f'<h2><a href="{href}">{title}</a></h2>'
        f'<p class="field-paper-people-text">{author}</p>{description}</article>'
    )


# The two 2024 slugs are the SAME schedule, exactly as the real site serves it:
# summer carries Alpha's abstract, fall does not.  A naive per-page sync would
# wipe Alpha's abstract again when the fall page is persisted.
LISTED_ABSTRACT = "Abstract carried by the listing page must be preserved."
SUMMER_LISTING_HTML = (
    _listing_block("Alpha", "Ada Lovelace", PAPER_A_PATH)
    + _listing_block("Beta", "Grace Hopper", PAPER_B_PATH)
)
FALL_LISTING_HTML = (
    _listing_block("Alpha", "Ada Lovelace", PAPER_A_PATH, abstract=LISTED_ABSTRACT)
    + _listing_block("Beta", "Grace Hopper", PAPER_B_PATH)
)
# The site orders the slugs summer then fall; the alphabetic str(hash) start
# below flips that for half of the runs, so both orders are covered.
DETAIL_PAGES = (SUMMER_LISTING_HTML, FALL_LISTING_HTML)
# Alpha's abstract arrives from whichever listing slug is served first.
LISTING_HTML = SUMMER_LISTING_HTML


def _detail_markup(title, author, abstract, *, date="2024-01-01"):
    return (
        f'<meta name="citation_title" content="{title}">'
        f'<meta name="citation_author" content="{author}">'
        f'<meta name="citation_publication_date" content="{date}">'
        f'<div class="field-name-field-paper-description"><p>{abstract}</p></div>'
    )


DETAIL_HTML_A = _detail_markup("Alpha", "Ada Lovelace", ABSTRACT_A)
DETAIL_HTML_B = _detail_markup("Beta", "Grace Hopper", ABSTRACT_B)


class MemoryDetailStore:
    """Minimal in-memory store exposing the fetch-unit/catalog/event surface."""

    def __init__(self, *, details=None, listing=LISTING_HTML, cached=None):
        self.units = {}
        self.events = []
        self.papers = {}
        self.details = dict(details or {})
        self.listing = listing
        self.cached = dict(cached or {})

    def ensure_fetch_unit(self, unit, now):
        self.units.setdefault(unit.fetch_unit_id, unit)
        return True

    def get_fetch_unit(self, unit_id):
        return self.cached.get(unit_id) or self.units.get(unit_id)

    def acquire_fetch_unit(self, unit_id, owner, lease_seconds, now):
        unit = self.units.get(unit_id)
        if unit is None:
            return False
        unit.status, unit.lease_owner = "fetching", owner
        return True

    def save_fetch_unit(self, unit, now):
        self.units[unit.fetch_unit_id] = unit

    def release_lease(self, unit_id, owner, status="completed", now=None):
        unit = self.units.get(unit_id)
        if unit is None or unit.lease_owner != owner:
            return False
        unit.lease_owner, unit.lease_expires_at, unit.status = None, None, status
        return True

    def get_catalog_paper(self, catalog_paper_id):
        return self.papers.get(catalog_paper_id)

    def upsert_catalog_paper(self, paper, now=None):
        self.papers[paper.catalog_paper_id] = paper
        return True

    def save_source_record(self, record, now=None):
        return None

    def append_search_event(self, event, now=None):
        self.events.append(event)
        return len(self.events)

    def save_source_progress(self, progress, now=None):
        self.progress = progress
        return None

    def create_search_job(self, job, now=None):
        self.job = job
        return None


def _detail_source(store):
    """Source whose only network seam is the injected mock transport.

    The mock counts every non-listing request in ``calls``, so "zero detail
    requests" can be asserted directly instead of inferred from unit state.
    """
    calls = []

    def handler(request):
        if request.url.path.endswith("-accepted-papers"):
            return httpx.Response(200, text=store.listing)
        url = str(request.url)
        calls.append(url)
        produce = store.details.get(request.url.path)
        return produce() if produce is not None else httpx.Response(404)

    source = _source(handler)
    source.store = store
    return source, calls


def _sync(source, search_id="search-detail", *, owner="worker"):
    return source.sync_usenix_units(
        search_id, "usenix-security", [2024], owner=owner,
        lease_seconds=300, now="2099-01-01T00:00:00Z",
    )


def _abstracts(store):
    return {paper.title: paper.abstract for paper in store.papers.values()}


def test_detail_unit_backfills_missing_abstract():
    store = MemoryDetailStore(details={
        "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(200, text=DETAIL_HTML_A),
        "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(200, text=DETAIL_HTML_B),
    })
    source, calls = _detail_source(store)

    result = _sync(source, "search-detail-fill")

    # Each 2024 slug serves the same two papers, so the second listing page does
    # not re-request the pages the first one already fetched.
    assert calls == [PAPER_A, PAPER_B]
    assert result.status == "completed"
    assert {UNIT_24, DETAIL_A, DETAIL_B} <= set(store.units)
    assert store.units[UNIT_24].year == 2024
    assert store.units[DETAIL_A].year == 2024
    assert store.units[DETAIL_A].status == "completed"
    assert store.units[DETAIL_A].content_hash
    assert store.units[DETAIL_A].lease_owner is None
    # The fall listing must not wipe what the summer listing's detail unit filled.
    assert _abstracts(store) == {"Alpha": ABSTRACT_A, "Beta": ABSTRACT_B}


def test_detail_unit_never_overwrites_an_existing_abstract():
    """The listing-supplied abstract survives the detail page."""
    store = MemoryDetailStore(
        listing=FALL_LISTING_HTML,
        details={"/conference/usenixsecurity24/presentation/alpha":
                 lambda: httpx.Response(200, text=DETAIL_HTML_A)},
    )
    source, calls = _detail_source(store)

    _sync(source, "search-detail-keep")

    # fill-if-missing: the listing-supplied abstract is never replaced by the
    # detail page's parse, and Alpha's presentation page is not even requested
    # (only the still-missing Beta page is).
    assert _abstracts(store)["Alpha"] == LISTED_ABSTRACT
    assert DETAIL_A not in store.units
    assert calls == [PAPER_B]


def test_later_listing_slug_does_not_wipe_a_backfilled_abstract():
    """A later listing page must not re-wipe an abstract filled from the detail page."""
    store = MemoryDetailStore(
        listing=SUMMER_LISTING_HTML,
        details={"/conference/usenixsecurity24/presentation/alpha":
                 lambda: httpx.Response(200, text=DETAIL_HTML_A)},
    )
    source, _calls = _detail_source(store)

    _sync(source, "search-detail-order")

    # The detail unit backfilled Alpha's abstract; the other listing slug is
    # persisted afterwards with an empty abstract and must not erase it.
    assert _abstracts(store)["Alpha"] == ABSTRACT_A
    assert store.units[DETAIL_A].status == "completed"


def test_completed_detail_unit_skips_every_network_request():
    # Both listing units AND both detail units are already completed, so the
    # whole sync (listing + detail) must be served from cache.
    listings = [_completed(UNIT_24), _completed(FALL_UNIT_24)]
    store = MemoryDetailStore(
        cached={**{unit.fetch_unit_id: unit for unit in listings},
                DETAIL_A: _completed(DETAIL_A), DETAIL_B: _completed(DETAIL_B)},
    )
    source, calls = _detail_source(store)

    result = _sync(source, "search-detail-cache")

    assert [url for url in calls if "presentation" in url] == []
    assert result.status == "completed"
    assert result.completed == []


def test_one_failed_detail_page_does_not_break_remaining_papers():
    store = MemoryDetailStore(details={
        "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(500),
        "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(200, text=DETAIL_HTML_B),
    })
    source, calls = _detail_source(store)

    result = _sync(source, "search-detail-failure")

    assert calls == [PAPER_A, PAPER_B]
    assert store.units[DETAIL_A].status == "failed"
    assert store.units[DETAIL_A].error_code == "USENIX_HTTP_500"
    # A failed detail unit stays retryable and must not be left leased forever.
    assert store.units[DETAIL_A].lease_owner is None
    assert store.units[DETAIL_B].status == "completed"
    # Alpha's abstract stays missing (retryable) while Beta's was filled.
    assert _abstracts(store) == {"Alpha": None, "Beta": ABSTRACT_B}
    # An abstract is an enhancement, not the recall path: a failed detail page
    # must NOT degrade the run.  The listing (the authoritative source) fully
    # succeeded, so the source reports "completed" - not "partial"/degraded.
    assert result.status == "completed"
    assert result.error_code is None
    # The failure stays visible: the unit records it and the event is emitted.
    assert result.detail_failed == [DETAIL_A]
    assert result.failed == []
    assert any(event.event_type == "USENIX_DETAIL_FAILED" for event in store.events)


def test_detail_unit_rejects_urls_outside_the_presentation_allowlist():
    rejected = (
        "https://evil.example/conference/usenixsecurity24/presentation/alpha",
        "https://www.usenix.org/conference/usenixsecurity24/presentation/alpha?inject=1",
        "https://www.usenix.org/conference/usenixsecurity24/accepted-papers",
        "http://www.usenix.org/conference/usenixsecurity24/presentation/alpha",
        "https://www.usenix.org/conference/usenixsecurity24/presentation/alpha#x",
        "https://evil.example/evil.pdf",
    )
    store = MemoryDetailStore()
    source, calls = _detail_source(store)
    result = SimpleNamespace(completed=[], failed=[], cached=[], waiting=[], paper_count=0)

    for url in rejected:
        assert source._detail_url_ok(url) is None
        source._sync_detail_unit("search-detail-reject", "usenix-security", url,
                                 "worker", 300, "2099-01-01T00:00:00Z", result,
                                 catalog_paper_id="unused")

    assert calls == []
    assert store.units == {}
    assert all(event.event_type == "USENIX_DETAIL_REJECTED" for event in store.events)


def test_detail_stage_is_incremental_and_idempotent(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-detail-retry", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    details = {
        "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(200, text=DETAIL_HTML_A),
        "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(500),
    }
    first, calls = _detail_source(MemoryDetailStore(details=details))
    first.store = store
    first._discovery_routes = list(ROUTED_SOURCE.discovery_routes)
    _sync(first, job.search_id)
    # Each page is fetched exactly once per run even though both 2024 slugs
    # serve the same papers.
    assert calls == [PAPER_A, PAPER_B]

    # The second run models the next search with a fresh client: the completed
    # Alpha unit is served from cache while the failed Beta unit is retried.
    second, calls2 = _detail_source(MemoryDetailStore(details=details))
    second.store = store
    second._discovery_routes = list(ROUTED_SOURCE.discovery_routes)
    result = _sync(second, job.search_id)

    assert calls2 == [PAPER_B]
    # Incremental recovery: only the still-failing page was retried, and the
    # previously completed unit was served from cache.
    assert calls2.count(PAPER_A) == 0
    assert store.get_fetch_unit(DETAIL_A).status == "completed"
    assert store.get_fetch_unit(DETAIL_B).status == "failed"
    # Beta's detail page keeps failing across runs, but the listing succeeded
    # both times, so neither run may degrade the source to "partial".
    assert result.status == "completed"
    assert result.detail_failed == [DETAIL_B]


def _paper_id(title):
    return hashlib.sha256(f"usenix-security|{normalize_title(title)}".encode("utf-8")).hexdigest()[:32]


# --- Spec-032.1 detail-failure isolation: an abstract is never a job degrade --
#
# A presentation page (abstract backfill) is an *enhancement*: when only detail
# pages fail, the recall path (the listing) is intact, so neither the source
# status nor the frozen job may turn "partial"/degraded.  The failure must stay
# observable and retryable instead.

def test_detail_only_failure_keeps_source_completed_and_job_undegraded(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-detail-only", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    # Both listings succeed; only Alpha's presentation page fails, so Beta's
    # abstract is still backfilled.
    memory = MemoryDetailStore(details={
        "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(500),
        "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(200, text=DETAIL_HTML_B),
    })
    source, calls = _detail_source(memory)
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = _sync(source, job.search_id)

    assert calls == [PAPER_A, PAPER_B]
    # The listing succeeded end to end, so the source is completed, not partial.
    assert result.status == "completed"
    assert result.error_code is None
    assert result.failed == []
    assert result.detail_failed == [DETAIL_A]
    # No listing unit may be reported as failed: `failed` keeps its original
    # listing-page meaning so the job is not marked degraded.
    assert not any(unit.startswith(UNIT_24) for unit in result.failed)
    # Progress/job rows agree: the job is completed and not degraded.
    progress = store.get_source_progress(job.search_id)
    assert progress and progress[0].status == "completed"
    persisted_job = store.get_search_job(job.search_id)
    assert persisted_job.status == "completed" and persisted_job.degraded is False
    # Internal consistency: every unit recorded as failed is a detail unit.
    assert all("|detail" in unit for unit in result.detail_failed)


def test_frozen_job_is_not_degraded_when_only_detail_pages_failed(tmp_path):
    """The consumer's contract: a detail-only failure never reaches degraded_sources."""
    from backend.app.paper_discovery.application.catalog_search_graph import CatalogSearchGraph

    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-detail-freeze", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    memory = MemoryDetailStore(details={
        "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(500),
        "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(200, text=DETAIL_HTML_B),
    })
    source, _calls = _detail_source(memory)
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = _sync(source, job.search_id)
    assert result.status == "completed"

    # Mirror exactly what sync_usenix hands to freeze_search_results, so the
    # assertion covers the real cross-module boundary without touching the graph.
    handed_source = {"status": result.status, "error_code": result.error_code,
                     "degraded": bool(result.failed)}
    assert handed_source["degraded"] is False

    graph = CatalogSearchGraph.__new__(CatalogSearchGraph)
    graph.store = store
    graph.freeze_search_results(job, [], degraded=False, source_results=(handed_source, {}))

    frozen = store.get_search_job(job.search_id)
    assert frozen.status != "partial"
    assert frozen.degraded is False
    assert frozen.error_code is None


def test_listing_failure_still_degrades_the_job(tmp_path):
    """Regression guard: a listing failure must keep its partial/degraded meaning."""
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-listing-failure", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)

    def handler(request):
        path = request.url.path
        if path.endswith("summer-accepted-papers"):
            return httpx.Response(404)  # a real recall failure
        if path.endswith("fall-accepted-papers"):
            return httpx.Response(200, text=FALL_LISTING_HTML)
        produce = {
            "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(200, text=DETAIL_HTML_A),
            "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(200, text=DETAIL_HTML_B),
        }.get(path)
        return produce() if produce is not None else httpx.Response(404)

    source = _source(handler)
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = _sync(source, job.search_id)

    # One listing of the year failed while the other produced a snapshot:
    # the pre-fix behaviour (partial + degraded) must be preserved exactly.
    assert result.status == "partial"
    assert result.failed == [SEC24_SUMMER]
    assert result.detail_failed == []
    assert store.get_search_job(job.search_id).status == "partial"
    assert store.get_search_job(job.search_id).degraded is True


# One run carrying BOTH failure kinds.  The summer listing 404s while fall
# serves the abstract-free SUMMER_LISTING_HTML, so neither paper gets an
# abstract from a listing and both presentation pages are attempted - and both
# fail.  SUMMER_LISTING_HTML (not FALL_LISTING_HTML) is deliberate: its Alpha
# entry has no abstract, which is what keeps the detail stage from being skipped.
MIXED_FAILURE_DETAILS = {
    "/conference/usenixsecurity24/presentation/alpha": lambda: httpx.Response(500),
    "/conference/usenixsecurity24/presentation/beta": lambda: httpx.Response(500),
}


def _mixed_failure_handler(request):
    path = request.url.path
    if path.endswith("summer-accepted-papers"):
        return httpx.Response(404)  # listing failure
    if path.endswith("fall-accepted-papers"):
        return httpx.Response(200, text=SUMMER_LISTING_HTML)
    produce = MIXED_FAILURE_DETAILS.get(path)
    return produce() if produce is not None else httpx.Response(404)


def test_listing_and_detail_failures_are_tracked_in_separate_buckets(tmp_path):
    """Mixed failures: listing drives the status, details only get recorded."""
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-mixed-failure", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    source = _source(_mixed_failure_handler)
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = _sync(source, job.search_id)

    assert result.status == "partial"
    assert result.failed == [SEC24_SUMMER]
    assert result.detail_failed == [DETAIL_A, DETAIL_B]
    # The detail bucket must never leak into the listing bucket.
    assert not set(result.failed) & set(result.detail_failed)
    assert store.get_fetch_unit(FALL_UNIT_24).year == 2024
    assert store.get_fetch_unit(DETAIL_A).year == 2024


def test_detail_failure_does_not_emit_unit_failed_event(tmp_path):
    """USENIX_UNIT_FAILED stays a listing-only signal."""
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = SearchJob(
        "search-detail-events", "secure", ["usenix-security"], [2024],
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )
    store.create_search_job(job)
    source = _source(_mixed_failure_handler)
    source.store = store
    source._discovery_routes = list(ROUTED_SOURCE.discovery_routes)

    result = _sync(source, job.search_id)

    assert result.detail_failed == [DETAIL_A, DETAIL_B]
    events = store.get_search_events(job.search_id)
    # The detail failures are still observable via their own event, keyed to the
    # affected units.  Only these identity fields are asserted: the store's event
    # sanitizer owns the rest of the payload, so pinning it here would test the
    # sanitizer instead of this stage.
    detail_events = [event for event in events if event.event_type == "USENIX_DETAIL_FAILED"]
    assert [event.safe_payload.get("unit_id") for event in detail_events] == [DETAIL_A, DETAIL_B]
    assert all(event.status == "failed" for event in detail_events)
    # The listing failure is surfaced exactly once, and the detail units never
    # masquerade as a listing-unit failure.
    assert [event.event_type for event in events if event.event_type == "USENIX_UNIT_FAILED"] == \
        ["USENIX_UNIT_FAILED"]


def _completed(unit_id):
    from backend.app.paper_discovery.domain.paper_discovery import SourceFetchUnit

    return SourceFetchUnit(
        fetch_unit_id=unit_id, source_kind="usenix", conference_id="usenix-security",
        unit_key=unit_id, status="completed", content_hash="a" * 64,
        created_at="2099-01-01T00:00:00Z", updated_at="2099-01-01T00:00:00Z",
    )




# --- spec-032.1 review fixes: year narrowing + hash field parity -------------
#
# MEDIUM-1: the resume stage used to read the catalog with ``years=None``, so a
# search limited to 2024 still discovered and fetched 2025 presentation pages.
# Every request is recorded by the fake transport, so the assertions are on the
# real network surface (and on the real store), not on internal bookkeeping.

DETAIL_2025 = "https://www.usenix.org/conference/usenixsecurity25/presentation/old-2025"


def _year_router(store):
    """Handler serving both years' listings + presentation pages.

    ``calls`` records every presentation-page request, which is the surface the
    resume bug used to widen to years the caller never asked for.
    """
    calls = []

    def handler(request):
        path = request.url.path
        if path.endswith("-accepted-papers"):
            return httpx.Response(200, text=store.listing_for(path))
        url = str(request.url)
        calls.append(url)
        produce = store.details.get(path)
        return produce() if produce is not None else httpx.Response(404)

    return handler, calls


class _TwoYearMemoryStore(MemoryDetailStore):
    """MemoryDetailStore that also serves 2025 listings and catalog reads."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.listing_25 = _listing_block("Old 2025", "Ada Lovelace",
                                         "/conference/usenixsecurity25/presentation/old-2025")

    def listing_for(self, path):
        return self.listing_25 if "usenixsecurity25" in path else self.listing

    def list_catalog_papers(self, conference_ids=None, years=None, *, index_status="indexed"):
        """Mirror the real reader's year filter, so a widened read is observable."""
        papers = list(self.papers.values())
        if conference_ids:
            papers = [p for p in papers if p.conference_id in set(conference_ids)]
        if years:
            papers = [p for p in papers if p.year in {int(y) for y in years}]
        if index_status is not None:
            papers = [p for p in papers if p.index_status == index_status]
        return papers


def _catalog_row(title, year, url, *, abstract=None, index_status="pending"):
    from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper

    return CatalogPaper(
        catalog_paper_id=_paper_id(title), conference_id="usenix-security", year=year,
        title=title, normalized_title=normalize_title(title), authors=["Ada Lovelace"],
        abstract=abstract, official_page_url=url, index_status=index_status,
        created_at="2099-01-01T00:00:00Z", updated_at="2099-01-01T00:00:00Z",
    )


def _two_year_store():
    """2024's Alpha needs its abstract; a stale 2025 row is also abstract-free.

    Both rows are ``pending`` with no abstract, so a read widened to ``years=None``
    resumes both — which is exactly the pre-fix behaviour under test.
    """
    store = _TwoYearMemoryStore(details={
        "/conference/usenixsecurity24/presentation/alpha":
            lambda: httpx.Response(200, text=DETAIL_HTML_A),
        "/conference/usenixsecurity25/presentation/old-2025":
            lambda: httpx.Response(200, text=_detail_markup("Old 2025", "Ada Lovelace", "stale")),
    })
    store.papers[_paper_id("Alpha")] = _catalog_row("Alpha", 2024, PAPER_A)
    store.papers[_paper_id("Old 2025")] = _catalog_row("Old 2025", 2025, DETAIL_2025)
    return store


def test_resume_stage_of_a_cached_listing_stays_inside_the_year():
    """The resume path (cached listing unit) is the one the review flagged.

    A cached listing unit routes the run into ``_resume_detail_units``, which is
    exactly where the pre-fix code read the catalog with ``years=None`` and
    therefore fetched the stale 2025 presentation page.
    """
    store = _two_year_store()
    store.cached = {UNIT_24: _completed(UNIT_24), FALL_UNIT_24: _completed(FALL_UNIT_24)}
    handler, calls = _year_router(store)
    source = _source(handler)
    source.store = store

    result = source.sync_usenix_units("search-resume-cached", "usenix-security", [2024],
                                      owner="worker", lease_seconds=300,
                                      now="2099-01-01T00:00:00Z")

    assert result.cached, "详情unit未走缓存则本用例不成立"
    assert [url for url in calls if "usenixsecurity25" in url] == [], (
        "只搜索 2024 时，续跑阶段不得抓取 2025 的详情页")
    assert calls == [PAPER_A], calls
    assert store.papers[_paper_id("Old 2025")].abstract is None


def test_resume_stage_still_fetches_the_requested_year():
    """The narrowing must not disable the resume path for the requested year."""
    store = _TwoYearMemoryStore(details={
        "/conference/usenixsecurity24/presentation/alpha":
            lambda: httpx.Response(200, text=DETAIL_HTML_A),
        "/conference/usenixsecurity24/presentation/beta":
            lambda: httpx.Response(200, text=DETAIL_HTML_B),
    })
    store.papers[_paper_id("Alpha")] = _catalog_row("Alpha", 2024, PAPER_A)
    store.papers[_paper_id("Beta")] = _catalog_row("Beta", 2024, PAPER_B)
    store.cached = {UNIT_24: _completed(UNIT_24), FALL_UNIT_24: _completed(FALL_UNIT_24)}
    handler, calls = _year_router(store)
    source = _source(handler)
    source.store = store

    source.sync_usenix_units("search-resume-same-year", "usenix-security", [2024],
                             owner="worker", lease_seconds=300,
                             now="2099-01-01T00:00:00Z")

    assert calls == [PAPER_A, PAPER_B], calls
    assert {paper.title: paper.abstract for paper in store.papers.values()} == {
        "Alpha": ABSTRACT_A, "Beta": ABSTRACT_B}


def test_resume_stage_without_years_does_not_crash(tmp_path):
    """No years means no narrowing; the caller must not be required to pass them."""
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    source, calls = _detail_source(store)
    result = SimpleNamespace(completed=[], failed=[], cached=[], waiting=[],
                             detail_failed=[], paper_count=0)

    source._resume_detail_units("search-no-years", "usenix-security", "worker",
                                300, "2099-01-01T00:00:00Z", result, None)

    assert calls == []


# --- MEDIUM-3 (incidental): hash field parity --------------------------------
#
# ``_catalog_metadata_hash`` hashed ``page_unit_id=None`` while ``_persist_paper``
# hashed the real unit id, so an unchanged abstract still produced a different
# hash.  ``upsert_catalog_paper`` treats a changed hash as new metadata and
# resets ``index_status`` to ``pending``, forcing a pointless re-embedding.
# These tests use the REAL store so the reset is observed, not simulated.

def _indexed_row(tmp_path, title, *, abstract):
    """Store a row exactly as the listing sync would, then mark it indexed.

    The stored ``metadata_hash`` must be the one ``_persist_paper``/``_fill_abstract``
    compute for these values; otherwise the fixture itself would look like a
    metadata change and defeat the point of the test.
    """
    from dataclasses import replace

    from backend.app.paper_discovery.infrastructure.usenix_publication_source import (
        _catalog_metadata_hash,
    )

    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    row = replace(_catalog_row(title, 2024, PAPER_A, abstract=abstract),
                  metadata_hash=_catalog_metadata_hash(
                      _catalog_row(title, 2024, PAPER_A, abstract=abstract), abstract))
    assert store.upsert_catalog_paper(row) is True
    assert store.mark_catalog_indexed(row.catalog_paper_id) is True
    assert store.get_catalog_paper(row.catalog_paper_id).index_status == "indexed"
    return store, row.catalog_paper_id


def _persist_paper_like_listing(source, unit_id, title):
    """Re-persist one listing paper through the real ``_persist_paper``."""
    paper = SimpleNamespace(
        title=title, authors=["Ada Lovelace"], year=2024, abstract=None,
        article_url=PAPER_A, official_pdf_url=None, prepublication_pdf_url=None,
    )
    result = SimpleNamespace(completed=[], failed=[], cached=[], waiting=[],
                             detail_failed=[], paper_count=0)
    source._persist_paper("search-repersist", unit_id, "usenix-security", paper,
                          "2099-01-01T00:00:00Z", result)


def test_backfilled_abstract_is_not_reset_by_the_next_listing_sync(tmp_path):
    """An already-embedded abstract must survive the next unchanged listing sync.

    ``_fill_abstract`` and ``_persist_paper`` must hash the same field set.
    When they disagree, re-persisting an unchanged row looks like new metadata
    and resets ``index_status`` to ``pending``, so an abstract that was already
    embedded gets re-embedded for nothing.
    """
    store, paper_id = _indexed_row(tmp_path, "Stable", abstract="already here")
    unit_id = "usenix|usenix-security|/conference/usenixsecurity24/summer-accepted-papers/"
    _seed_fetch_unit(store, unit_id)
    source, _calls = _detail_source(MemoryDetailStore())
    source.store = store

    # The row is already indexed with its abstract; the next listing sync
    # repersists the very same paper (still abstract-free on the listing page).
    _persist_paper_like_listing(source, unit_id, "Stable")

    assert store.get_catalog_paper(paper_id).index_status == "indexed", (
        "摘要与字段集都未变化时，重新同步不得把 index_status 重置为 pending")
    assert store.get_catalog_paper(paper_id).abstract == "already here"


def _seed_fetch_unit(store, unit_id):
    from backend.app.paper_discovery.domain.paper_discovery import SourceFetchUnit

    store.save_fetch_unit(SourceFetchUnit(
        fetch_unit_id=unit_id, source_kind="usenix", conference_id="usenix-security",
        unit_key=unit_id, status="completed", content_hash="a" * 64,
        created_at="2099-01-01T00:00:00Z", updated_at="2099-01-01T00:00:00Z",
    ), "2099-01-01T00:00:00Z")


def _hash_fields(source_text, header):
    """Return the field names hashed inside ``header``'s metadata dict."""
    body = source_text.split(header, 1)[1]
    body = body.split("metadata_hash =", 1)[0] if header == "def _persist_paper" else body
    body = body.split("return hashlib.sha256", 1)[0]
    return set(re.findall(r'"(\w+)":', body))


def test_catalog_metadata_hash_field_set_matches_persist_paper():
    """Both hashes must be computed over the SAME field set."""
    from pathlib import Path

    source_text = Path(
        "backend/app/paper_discovery/infrastructure/usenix_publication_source.py"
    ).read_text(encoding="utf-8")
    persist_fields = _hash_fields(source_text, "def _persist_paper")
    helper_fields = _hash_fields(source_text, "def _catalog_metadata_hash")
    assert helper_fields == persist_fields, (helper_fields, persist_fields)


def test_new_abstract_still_marks_the_row_pending(tmp_path):
    """The real backfill must keep marking the row pending (regression guard)."""
    store, paper_id = _indexed_row(tmp_path, "Stable", abstract=None)
    source, _calls = _detail_source(MemoryDetailStore())
    source.store = store

    source._fill_abstract("usenix-security", paper_id,
                          SimpleNamespace(abstract="fresh abstract"),
                          "2099-01-01T00:00:00Z")

    updated = store.get_catalog_paper(paper_id)
    assert updated.abstract == "fresh abstract"
    assert updated.index_status == "pending"
