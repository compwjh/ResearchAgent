import httpx

from backend.app.paper_discovery.infrastructure.semantic_scholar_adapter import (
    SEMANTIC_SCHOLAR_API_URL,
    SemanticScholarFallbackAdapter,
    SemanticScholarRequestLimiter,
    semantic_scholar_retry_delay,
)


def _candidate(**overrides):
    value = {
        "title": "Budget Recycling Differential Privacy",
        "authors": ["Ada Lovelace"],
        "year": 2024,
        "doi": "10.1109/SP54263.2024.00212",
    }
    value.update(overrides)
    return value


def _payload(*, pdf_url="https://arxiv.org/pdf/2403.11445", title=None):
    return {
        "paperId": "s2-paper-id",
        "title": title or "Budget Recycling Differential Privacy",
        "abstract": "A privacy abstract.",
        "authors": [{"authorId": "1", "name": "Ada Lovelace"}],
        "year": 2024,
        "externalIds": {"DOI": "10.1109/SP54263.2024.00212", "ArXiv": "2403.11445"},
        "url": "https://www.semanticscholar.org/paper/s2-paper-id",
        "openAccessPdf": {"url": pdf_url, "status": "GREEN"} if pdf_url else None,
    }


def test_lookup_by_doi_maps_open_access_pdf_and_sends_optional_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_payload())

    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)), api_key="secret"
    )
    result = adapter.lookup(_candidate(), allowed_hosts={"arxiv.org"})

    assert result.matched
    assert result.match.pdf_url == "https://arxiv.org/pdf/2403.11445"
    assert result.match.abstract == "A privacy abstract."
    assert seen[0].url == httpx.URL(
        f"{SEMANTIC_SCHOLAR_API_URL}/paper/DOI:10.1109%2Fsp54263.2024.00212",
        params={"fields": "paperId,title,abstract,authors,year,externalIds,url,openAccessPdf"},
    )
    assert seen[0].headers["x-api-key"] == "secret"


def test_lookup_rejects_mismatched_title_and_unregistered_pdf_host():
    body = _payload(pdf_url="https://downloads.example/paper.pdf", title="A Different Paper")
    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    )
    assert adapter.lookup(_candidate(), allowed_hosts={"downloads.example"}).code == "SEMANTIC_SCHOLAR_MATCH_UNCERTAIN"

    body = _payload()
    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    )
    assert adapter.lookup(_candidate(), allowed_hosts={"ieeexplore.ieee.org"}).code == "SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST"


def test_lookup_maps_no_pdf_auth_not_found_and_rate_limit():
    no_pdf = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=_payload(pdf_url=None))))
    )
    assert no_pdf.lookup(_candidate(), allowed_hosts={"arxiv.org"}).code == "SEMANTIC_SCHOLAR_NO_OPEN_PDF"

    auth = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(403)))
    )
    assert auth.lookup(_candidate()).code == "SEMANTIC_SCHOLAR_AUTH_FAILED"

    not_found = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(404)))
    )
    assert not_found.lookup(_candidate()).code == "SEMANTIC_SCHOLAR_NOT_FOUND"

    calls = []
    responses = [httpx.Response(429), httpx.Response(200, json=_payload())]
    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: (calls.append(True), responses.pop(0))[1])),
        retries=1,
        sleep=lambda _seconds: None,
    )
    assert adapter.lookup(_candidate(), allowed_hosts={"arxiv.org"}).matched
    assert len(calls) == 2


def test_lookup_treats_malformed_open_access_url_as_no_pdf():
    body = _payload(pdf_url="https://[malformed/paper.pdf")
    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    )
    assert adapter.lookup(_candidate(), allowed_hosts={"arxiv.org"}).code == "SEMANTIC_SCHOLAR_NO_OPEN_PDF"


def test_rate_limit_retry_honors_retry_after_without_exposing_provider_body():
    sleeps = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "3"}, text="secret=provider"),
        httpx.Response(200, json=_payload()),
    ]
    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: responses.pop(0))),
        retries=1,
        backoff=1.0,
        sleep=sleeps.append,
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )

    assert adapter.lookup(_candidate(), allowed_hosts={"arxiv.org"}).matched
    assert sleeps == [3.0]


def test_retry_after_is_not_reused_after_network_failure():
    sleeps = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "3"}, text="secret=provider"),
        httpx.ConnectError("network down"),
        httpx.Response(200, json=_payload()),
    ]

    def handler(request):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise httpx.ConnectError(str(response), request=request)
        return response

    adapter = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=2,
        backoff=1.0,
        sleep=sleeps.append,
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )

    assert adapter.lookup(_candidate(), allowed_hosts={"arxiv.org"}).matched
    assert sleeps == [3.0, 2.0]


def test_retry_after_is_bounded_and_malformed_header_uses_exponential_delay():
    assert semantic_scholar_retry_delay(httpx.Response(429, headers={"Retry-After": "999"}), 0, 1.0) == 30.0
    assert semantic_scholar_retry_delay(httpx.Response(429, headers={"Retry-After": "not-a-number"}), 1, 1.0) == 2.0


def test_rate_limiter_is_shared_by_independent_adapter_instances():
    clock = {"value": 0.0}
    waits = []

    def now():
        return clock["value"]

    def sleep(seconds):
        waits.append(seconds)
        clock["value"] += seconds

    limiter = SemanticScholarRequestLimiter(now=now, sleep=sleep)
    responses = [_payload(), _payload()]

    def handler(_request):
        return httpx.Response(200, json=responses.pop(0))

    first = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        rate_limiter=limiter,
    )
    second = SemanticScholarFallbackAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        rate_limiter=limiter,
    )

    assert first.lookup(_candidate(), allowed_hosts={"arxiv.org"}).matched
    assert second.lookup(_candidate(), allowed_hosts={"arxiv.org"}).matched
    assert waits == [1.0]
