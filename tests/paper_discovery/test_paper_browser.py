"""隔离验证论文导入 browser route 的持久化边界。

这些测试只替换服务端快照、浏览器管理器和批任务服务，绝不启动
Playwright、访问网络或触碰知识库/Qdrant。它们保护的边界是：登录只创建
受控 session；续传只能委托现有批任务 -> immutable import 链路。
"""

from dataclasses import dataclass

from backend.app.api import routes_paper
from backend.app.paper_discovery.domain.paper_discovery import SearchSession


@dataclass
class _Candidate:
    candidate_id: str = "candidate-1"
    search_id: str = "search-1"
    article_url: str = "https://dl.acm.org/doi/10.1000/example"
    pdf_url: str = "https://dl.acm.org/doi/pdf/10.1000/example"


@dataclass
class _Item:
    item_id: str = "item-1"
    batch_id: str = "batch-1"
    candidate_id: str = "candidate-1"
    status: str = "waiting_login"
    paper_id: str | None = None
    stored_name: str | None = None
    cleanup_status: str | None = None


@dataclass
class _Batch:
    batch_id: str = "batch-1"
    search_id: str = "search-1"


class _NoWriteStore:
    """The route may read state, but any persistence attempt fails loudly."""

    def __init__(self, item: _Item | None = None):
        self.item = item or _Item()
        self.writes: list[tuple[str, tuple, dict]] = []

    def get_item(self, item_id):
        return self.item if item_id == self.item.item_id else None

    def get_batch(self, batch_id):
        return _Batch() if batch_id == self.item.batch_id else None

    def __getattr__(self, name):
        if name.startswith(("save", "write", "upsert", "remove", "delete", "record", "transition")):
            def forbidden(*args, **kwargs):
                self.writes.append((name, args, kwargs))
                raise AssertionError(f"browser route performed forbidden persistence: {name}")

            return forbidden
        raise AttributeError(name)


class _DiscoverySnapshot:
    def __init__(self, candidate: _Candidate | None = None):
        self.candidate = candidate or _Candidate()
        self.session = SearchSession("search-1", "security", "2099-01-01T00:00:00Z")

    def get_search_session(self, search_id):
        return self.session if search_id == self.session.search_id else None

    def get_candidates(self, search_id):
        return [self.candidate] if search_id == self.session.search_id else []


class _BrowserSession:
    def __init__(self):
        self.closed = False
        self.context = object()
        self.expired = False

    @property
    def is_closed(self):
        return self.closed

    def is_expired(self):
        return self.expired

    def close(self):
        self.closed = True

    def download_pdf(self, candidate, *args, **kwargs):  # pragma: no cover - identity is asserted
        return None


class _BrowserSpy:
    def __init__(self):
        self.opened: list[tuple[str, str]] = []
        self.sessions: list[_BrowserSession] = []

    def open_session(self, site, url):
        self.opened.append((site, url))
        session = _BrowserSession()
        self.sessions.append(session)
        return session


class _BatchServiceSpy:
    def __init__(self, candidate: _Candidate | None = None):
        self.item = _Item()
        self.store = _NoWriteStore(self.item)
        self.discovery_store = _DiscoverySnapshot(candidate)
        self.resume_calls: list[dict] = []

    def resume_item(self, item_id, **kwargs):
        self.resume_calls.append({"item_id": item_id, **kwargs})
        self.item.status = "completed"
        self.item.paper_id = "server-paper-1"
        self.item.stored_name = "safe.pdf"
        return self.item

    def get_status(self, batch_id):
        return {
            "batch": {
                "batch_id": batch_id,
                "search_id": "search-1",
                "status": "completed",
                "state": "completed",
                "total_count": 1,
                "completed_count": 1,
                "failed_count": 0,
                "waiting_login_count": 0,
                "cancelled_count": 0,
                "created_at": "2099-01-01T00:00:00Z",
                "updated_at": "2099-01-01T00:00:00Z",
            },
            "items": [self.item],
        }


def _patch_boundary(monkeypatch, service, browser):
    sessions = {}
    monkeypatch.setattr(routes_paper, "_paper_batch_service", lambda: service)
    monkeypatch.setattr(routes_paper, "_paper_browser_manager", lambda: browser)
    monkeypatch.setattr(routes_paper, "paper_browser_sessions", sessions)
    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: True)
    return sessions


def test_login_uses_server_snapshot_allowlist_and_performs_zero_kb_writes(monkeypatch):
    service = _BatchServiceSpy()
    browser = _BrowserSpy()
    sessions = _patch_boundary(monkeypatch, service, browser)

    response = routes_paper.login_paper_import_item("item-1")

    assert response == {"status": "opened", "item_id": "item-1", "site": "acm"}
    assert browser.opened == [("acm", "https://dl.acm.org/doi/10.1000/example")]
    assert sessions["item-1"] is browser.sessions[0]
    assert service.store.writes == []


def test_login_rejects_unallowlisted_source_before_opening_session(monkeypatch):
    candidate = _Candidate(article_url="https://evil.example/paper", pdf_url="https://evil.example/paper.pdf")
    service = _BatchServiceSpy(candidate)
    browser = _BrowserSpy()
    _patch_boundary(monkeypatch, service, browser)

    response = routes_paper.login_paper_import_item("item-1")

    assert response.status_code == 400
    assert response.body and b"BROWSER_ORIGIN_NOT_ALLOWED" in response.body
    assert browser.opened == []
    assert service.store.writes == []


def test_resume_requires_item_session_without_touching_import_boundary(monkeypatch):
    service = _BatchServiceSpy()
    browser = _BrowserSpy()
    _patch_boundary(monkeypatch, service, browser)

    response = routes_paper.resume_paper_import_item("item-1")

    assert response.status_code == 424
    assert response.body and b"BROWSER_SESSION_REQUIRED" in response.body
    assert service.resume_calls == []
    assert service.store.writes == []


def test_resume_delegates_session_downloader_and_closes_exact_session(monkeypatch):
    service = _BatchServiceSpy()
    browser = _BrowserSpy()
    sessions = _patch_boundary(monkeypatch, service, browser)
    session = _BrowserSession()
    sessions["item-1"] = session

    response = routes_paper.resume_paper_import_item("item-1")

    assert response["status"] == "completed"
    assert service.resume_calls and service.resume_calls[0]["item_id"] == "item-1"
    call = service.resume_calls[0]
    assert call["candidates"][0].candidate_id == "candidate-1"
    assert call["downloader"].__self__ is session
    assert call["downloader"].__func__ is session.download_pdf.__func__
    assert call["context"] is session.context
    assert session.closed is True
    assert "item-1" not in sessions
    assert service.store.writes == []


def test_resume_expired_session_is_fail_closed_without_import(monkeypatch):
    service = _BatchServiceSpy()
    browser = _BrowserSpy()
    sessions = _patch_boundary(monkeypatch, service, browser)
    session = _BrowserSession()
    session.expired = True
    sessions["item-1"] = session

    response = routes_paper.resume_paper_import_item("item-1")

    assert response.status_code == 424
    assert response.body and b"BROWSER_SESSION_EXPIRED" in response.body
    assert service.resume_calls == []
    assert session.closed is True
    assert "item-1" not in sessions
    assert service.store.writes == []
