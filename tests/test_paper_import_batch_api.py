from fastapi.testclient import TestClient

from backend.app.api import routes, routes_paper
from backend.app.main import app
from backend.app.paper_discovery.application.paper_import import LOGIN_REQUIRED, PaperImportError, PaperImportResult
from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchService
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_download import DOWNLOAD_BLOCKED
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import PaperImportBatchStore


class FakeLoginSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def download_pdf(self, candidate, *_args, **kwargs):
        self.download_calls = getattr(self, "download_calls", [])
        self.download_calls.append((candidate.candidate_id, kwargs))
        return None


class FakeBrowser:
    def __init__(self):
        self.opened = []
        self.sessions = []

    def health(self):
        return {"available": True, "version": "1.52.0", "supported_sites": ["acm", "ieee"], "reason": None}

    def open_session(self, site, url):
        self.opened.append((site, url))
        session = FakeLoginSession()
        self.sessions.append(session)
        return session


def _candidate(candidate_id="candidate-1"):
    return PaperCandidate(
        candidate_id,
        "search-1",
        "A Server Snapshot Paper",
        "ccs",
        "CCS",
        year=2025,
        doi="10.1000/server-snapshot",
        article_url="https://dl.acm.org/doi/10.1000/server-snapshot",
        pdf_url="https://dl.acm.org/doi/pdf/10.1000/server-snapshot",
    )


def _setup(monkeypatch, tmp_path, importer):
    discovery = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    discovery.save_search(
        SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        [_candidate()],
    )
    service = PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "state.sqlite3"),
        discovery_store=discovery,
        importer=importer,
    )
    browser = FakeBrowser()
    monkeypatch.setattr(routes_paper, "_paper_store", lambda: discovery)
    monkeypatch.setattr(routes_paper, "_paper_batch_service", lambda: service)
    monkeypatch.setattr(routes_paper, "_paper_browser_manager", lambda: browser)
    routes.paper_browser_sessions.clear()
    return service, browser


def test_batch_create_rejects_client_urls_with_stable_error(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    response = TestClient(app).post(
        "/api/papers/import-batches",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"], "pdf_url": "https://evil.example/x"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IMPORT_BATCH_REQUEST"
    assert set(response.json()) == {"code", "message", "retryable", "request_id"}


def test_batch_status_and_resume_use_server_snapshot(monkeypatch, tmp_path):
    attempts = []

    def importer(candidate, *_args):
        attempts.append(candidate.article_url)
        if len(attempts) == 1:
            raise PaperImportError(LOGIN_REQUIRED, "需要登录", retryable=True)
        return PaperImportResult("paper-1", "2025-CCS-Safe.pdf", "indexed")

    service, browser = _setup(monkeypatch, tmp_path, importer)
    client = TestClient(app)
    created = client.post(
        "/api/papers/import-batches",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"], "idempotency_key": "batch-1"},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "waiting_login"
    assert created.json()["items"][0]["status"] == "waiting_login"
    item_id = created.json()["items"][0]["item_id"]

    health = client.get("/api/papers/browser/health")
    assert health.status_code == 200
    assert set(health.json()) == {"available", "version", "supported_sites", "reason"}

    opened = client.post(f"/api/papers/import-items/{item_id}/login")
    assert opened.status_code == 200
    assert browser.opened == [("acm", "https://dl.acm.org/doi/10.1000/server-snapshot")]

    resumed = client.post(f"/api/papers/import-items/{item_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["items"][0]["paper_id"] == "paper-1"
    assert attempts == ["https://dl.acm.org/doi/10.1000/server-snapshot"] * 2
    assert browser.sessions[0].closed is True
    # No lease or idempotency data is reflected by the public status payload.
    assert "lease_owner" not in resumed.json()["items"][0]
    assert "idempotency_key" not in resumed.json()


def test_cancel_and_retry_routes_keep_stable_state_errors(monkeypatch, tmp_path):
    service, _browser = _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    created = client.post(
        "/api/papers/import-batches",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"]},
    )
    batch_id = created.json()["batch_id"]
    assert created.json()["status"] == "completed"
    cancelled = client.post(f"/api/papers/import-batches/{batch_id}/cancel")
    assert cancelled.status_code == 400
    assert cancelled.json()["code"] == "INVALID_STATE_TRANSITION"
    missing = client.get("/api/papers/import-batches/not-found")
    assert missing.status_code == 404
    assert missing.json()["code"] == "BATCH_NOT_FOUND"


def test_resume_uses_item_session_callback_without_exposing_sensitive_data(monkeypatch, tmp_path):
    captured = []

    def importer(candidate, *_args, downloader=None, context=None, **_kwargs):
        captured.append((candidate.candidate_id, downloader, context))
        if len(captured) == 1:
            raise PaperImportError(LOGIN_REQUIRED, "需要登录", retryable=True)
        return PaperImportResult("paper-1", "safe.pdf", "indexed")

    service, browser = _setup(monkeypatch, tmp_path, importer)
    client = TestClient(app)
    created = client.post(
        "/api/papers/import-batches",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"]},
    )
    item_id = created.json()["items"][0]["item_id"]
    client.post(f"/api/papers/import-items/{item_id}/login")
    response = client.post(f"/api/papers/import-items/{item_id}/resume")

    assert response.status_code == 200
    assert captured and captured[-1][0] == "candidate-1"
    assert callable(captured[-1][1])
    assert captured[-1][2] is None
    body = response.text.lower()
    assert "cookie" not in body
    assert "authorization" not in body
    assert "dl.acm.org/doi/10.1000" not in body
    assert browser.sessions[0].closed is True


def test_single_import_error_response_uses_fixed_safe_message():
    response = routes._paper_import_error_response(
        DOWNLOAD_BLOCKED,
        "https://evil.example/file.pdf Cookie=session=secret Authorization=Bearer token",
    )
    body = response.body.decode()
    assert "evil.example" not in body
    assert "secret" not in body
    assert "authorization" not in body.lower()
    assert "论文导入失败" not in body
    assert "下载地址被安全策略拒绝" in body
