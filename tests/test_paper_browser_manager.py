from __future__ import annotations

from pathlib import Path

import pytest

import backend.app.services.paper_browser_manager as browser_module
from backend.app.services.paper_browser_manager import (
    BROWSER_CRASHED,
    BROWSER_ORIGIN_NOT_ALLOWED,
    BROWSER_PROFILE_LOCKED,
    BROWSER_TIMEOUT,
    BROWSER_UNAVAILABLE,
    PINNED_PLAYWRIGHT_VERSION,
    BrowserManagerError,
    PaperBrowserManager,
)
from backend.app.services.paper_download import DOWNLOAD_BLOCKED, LOGIN_REQUIRED, PaperDownloadError


class FakePage:
    def __init__(self, *, fail_goto: Exception | None = None):
        self.fail_goto = fail_goto
        self.closed = False
        self.timeout = None
        self.navigation_timeout = None
        self.urls = []

    def set_default_timeout(self, value):
        self.timeout = value

    def set_default_navigation_timeout(self, value):
        self.navigation_timeout = value

    def goto(self, url, **_kwargs):
        self.urls.append(url)
        if self.fail_goto:
            raise self.fail_goto
        return {"url": url}

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, *, fail_goto: Exception | None = None):
        self.fail_goto = fail_goto
        self.closed = False
        self.options = None
        self.pages = []
        self.timeout = None
        self.navigation_timeout = None
        self.request = None

    def set_default_timeout(self, value):
        self.timeout = value

    def set_default_navigation_timeout(self, value):
        self.navigation_timeout = value

    def new_page(self):
        page = FakePage(fail_goto=self.fail_goto)
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.contexts = []

    def launch_persistent_context(self, profile, **options):
        context = FakeContext()
        context.profile = profile
        context.options = options
        self.contexts.append(context)
        return context


class FakePlaywright:
    version = PINNED_PLAYWRIGHT_VERSION

    def __init__(self):
        self.chromium = FakeChromium()
        self.closed = False

    def close(self):
        self.closed = True


def _offline_public_dns(_host: str) -> list[str]:
    """Keep fake browser tests offline while exercising production DNS checks."""
    return ["93.184.216.34"]


def _manager(tmp_path: Path, fake: FakePlaywright | None = None):
    fake = fake or FakePlaywright()
    return PaperBrowserManager(
        tmp_path / "profile",
        playwright_factory=lambda: fake,
        dns_resolver=_offline_public_dns,
    )


def test_health_has_only_safe_capability_fields_when_playwright_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_module, "_sync_playwright", None)
    health = PaperBrowserManager(profile_dir=tmp_path / "profile").health()

    assert health == {
        "available": False,
        "version": None,
        "supported_sites": ["acm", "ieee"],
        "reason": BROWSER_UNAVAILABLE,
    }
    assert "profile" not in repr(health).lower()
    assert "cookie" not in repr(health).lower()


def test_headed_context_disables_credential_bearing_recordings(tmp_path):
    fake = FakePlaywright()
    manager = PaperBrowserManager(
        tmp_path / "profile",
        playwright_factory=lambda: fake,
        launch_kwargs={"record_har": "secrets.har", "record_video_dir": "videos", "downloads_path": "downloads"},
    )

    with manager.session("acm", "https://dl.acm.org/doi/10.1145/example") as session:
        context = fake.chromium.contexts[0]
        assert context.options["headless"] is False
        assert context.options["accept_downloads"] is False
        assert "record_har" not in context.options
        assert "record_video_dir" not in context.options
        assert "downloads_path" not in context.options
        assert session.page.urls == ["https://dl.acm.org/doi/10.1145/example"]
        assert session.page.timeout == 300000

    manager.close()
    assert fake.chromium.contexts[0].closed is True


@pytest.mark.parametrize(
    "site,url",
    [
        ("acm", "http://dl.acm.org/doi/example"),
        ("acm", "https://evil.example/doi/example"),
        ("ieee", "https://ieeexplore.ieee.org.evil.example/document/1"),
        ("ieee", "https://ieeexplore.ieee.org:443/document/1"),
        ("ieee", "https://ieeexplore.ieee.org/document/1#token"),
    ],
)
def test_origin_allowlist_rejects_non_exact_origins(tmp_path, site, url):
    manager = _manager(tmp_path)

    with pytest.raises(BrowserManagerError) as error:
        manager.open_session(site, url)

    assert error.value.code == BROWSER_ORIGIN_NOT_ALLOWED
    assert error.value.retryable is False


def test_same_profile_is_file_locked_and_same_site_is_serialized(tmp_path):
    first = _manager(tmp_path)
    second = _manager(tmp_path)
    first_session = first.open_session("acm")
    try:
        with pytest.raises(BrowserManagerError) as locked:
            second.open_session("ieee")
        assert locked.value.code == BROWSER_PROFILE_LOCKED

        with pytest.raises(BrowserManagerError) as same_site:
            first.open_session("acm")
        assert same_site.value.code == BROWSER_PROFILE_LOCKED
    finally:
        first_session.close()
        first.close()
        second.close()


def test_browser_failure_closes_context_and_next_session_restarts(tmp_path):
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("acm")
    session.page.fail_goto = RuntimeError("page crashed")

    with pytest.raises(BrowserManagerError) as error:
        session.goto("https://dl.acm.org/doi/10.1145/after")
    assert error.value.code == BROWSER_CRASHED
    assert fake.chromium.contexts[0].closed is True
    session.close()

    restarted = manager.open_session("acm")
    try:
        assert len(fake.chromium.contexts) == 2
    finally:
        restarted.close()
        manager.close()


def test_playwright_timeout_maps_to_stable_timeout_without_crash_recovery(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("acm")
    session.page.fail_goto = playwright.TimeoutError("timed out")

    try:
        with pytest.raises(BrowserManagerError) as error:
            session.goto("https://dl.acm.org/doi/10.1145/timeout")
        assert error.value.code == BROWSER_TIMEOUT
        assert fake.chromium.contexts[0].closed is False
    finally:
        session.close()
        manager.close()


def test_cancel_and_close_are_idempotent(tmp_path):
    manager = _manager(tmp_path)
    session = manager.open_session("ieee")
    session.cancel()
    session.cancel()
    manager.close()


class FakeAPIResponse:
    status = 200
    headers = {"content-type": "application/pdf; charset=binary", "content-length": "9"}

    def body(self):
        return b"%PDF-fake"


class FakeAPIRequest:
    def __init__(self, response=None):
        self.response = response or FakeAPIResponse()
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_authenticated_pdf_request_uses_context_request_and_safe_result(tmp_path):
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("acm")
    request = FakeAPIRequest()
    session.context.request = request
    try:
        result = session.download_pdf(
            {"pdf_url": "https://dl.acm.org/doi/pdf/10.1000/example"},
            pdf_page_validator=lambda _path: 1,
        )
        assert request.calls[0][0] == "https://dl.acm.org/doi/pdf/10.1000/example"
        assert request.calls[0][1]["fail_on_status_code"] is False
        assert result.file_size == 9
        assert result.page_count == 1
        assert Path(result.file_path).read_bytes() == b"%PDF-fake"
        assert "cookie" not in repr(result).lower()
        assert "authorization" not in repr(result).lower()
    finally:
        session.close()
        manager.close()


def test_authenticated_pdf_request_maps_forbidden_without_response_details(tmp_path):
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("ieee")
    response = FakeAPIResponse()
    response.status = 403
    response.headers = {"set-cookie": "secret=do-not-leak"}
    session.context.request = FakeAPIRequest(response)
    try:
        with pytest.raises(PaperDownloadError) as error:
            session.download_pdf("https://ieeexplore.ieee.org/document/1")
        assert error.value.code == LOGIN_REQUIRED
        assert "secret" not in str(error.value).lower()
        assert "cookie" not in str(error.value).lower()
    finally:
        session.close()
        manager.close()
    manager.close()


def test_authenticated_pdf_request_rejects_authentication_query_without_request(tmp_path):
    manager = PaperBrowserManager(
        profile_dir=tmp_path / "profile", playwright_factory=lambda: FakePlaywright(),
        dns_resolver=lambda _host: ["93.184.216.34"],
    )
    session = manager.open_session("acm")
    request = FakeAPIRequest()
    session.context.request = request
    try:
        with pytest.raises(PaperDownloadError) as error:
            session.download_pdf("https://dl.acm.org/doi/pdf/10.1000/example?access_token=secret")
        assert error.value.code == DOWNLOAD_BLOCKED
        assert request.calls == []
        assert "secret" not in str(error.value).lower()
    finally:
        session.close()
        manager.close()


class _SequenceAPIResponse:
    def __init__(self, status, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body

    def body(self):
        return self._body


class _SequenceAPIRequest:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_authenticated_pdf_request_manually_revalidates_each_redirect(tmp_path):
    manager = PaperBrowserManager(
        profile_dir=tmp_path / "profile", playwright_factory=lambda: FakePlaywright(),
        dns_resolver=lambda _host: ["93.184.216.34"],
    )
    session = manager.open_session("ieee")
    request = _SequenceAPIRequest([
        _SequenceAPIResponse(302, {"location": "/document/2"}),
        _SequenceAPIResponse(200, {"content-type": "application/pdf"}, b"%PDF-fake"),
    ])
    session.context.request = request
    try:
        result = session.download_pdf(
            "https://ieeexplore.ieee.org/document/1",
            pdf_page_validator=lambda _path: 1,
        )
        assert [call[0] for call in request.calls] == [
            "https://ieeexplore.ieee.org/document/1",
            "https://ieeexplore.ieee.org/document/2",
        ]
        assert all(call[1]["max_redirects"] == 0 for call in request.calls)
        assert result.url.endswith("/document/2")
    finally:
        session.close()
        manager.close()


def test_authenticated_pdf_request_reuses_page_validator_and_returns_page_count(tmp_path):
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("acm")
    session.context.request = FakeAPIRequest()
    seen_paths = []

    try:
        result = session.download_pdf(
            "https://dl.acm.org/doi/pdf/10.1000/example",
            temp_dir=tmp_path / "downloads",
            pdf_page_validator=lambda path: seen_paths.append(path) or 3,
        )
        assert result.page_count == 3
        assert seen_paths == [Path(result.file_path)]
        assert Path(result.file_path).exists()
    finally:
        session.close()
        manager.close()


def test_authenticated_pdf_request_maps_playwright_timeout_to_stable_timeout(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("acm")

    class TimeoutRequest:
        def get(self, _url, **_kwargs):
            raise playwright.TimeoutError("request timed out")

    session.context.request = TimeoutRequest()
    try:
        with pytest.raises(BrowserManagerError) as error:
            session.download_pdf("https://dl.acm.org/doi/pdf/10.1000/example")
        assert error.value.code == BROWSER_TIMEOUT
        assert fake.chromium.contexts[0].closed is False
    finally:
        session.close()
        manager.close()


def test_authenticated_pdf_request_rejects_unreadable_pdf_and_cleans_temp_file(tmp_path):
    fake = FakePlaywright()
    manager = _manager(tmp_path, fake)
    session = manager.open_session("acm")
    session.context.request = FakeAPIRequest()
    download_dir = tmp_path / "downloads"

    try:
        with pytest.raises(PaperDownloadError) as error:
            session.download_pdf(
                "https://dl.acm.org/doi/pdf/10.1000/example",
                temp_dir=download_dir,
            )
        assert error.value.code == browser_module.INVALID_PDF
        assert list(download_dir.rglob("*")) == []
    finally:
        session.close()
        manager.close()


def test_authenticated_pdf_request_blocks_redirect_to_other_origin(tmp_path):
    manager = PaperBrowserManager(
        profile_dir=tmp_path / "profile", playwright_factory=lambda: FakePlaywright(),
        dns_resolver=lambda _host: ["93.184.216.34"],
    )
    session = manager.open_session("acm")
    request = _SequenceAPIRequest([_SequenceAPIResponse(302, {"location": "https://evil.example/file.pdf"})])
    session.context.request = request
    try:
        with pytest.raises(PaperDownloadError) as error:
            session.download_pdf("https://dl.acm.org/doi/pdf/10.1000/example")
        assert error.value.code == DOWNLOAD_BLOCKED
        assert len(request.calls) == 1
    finally:
        session.close()
        manager.close()
