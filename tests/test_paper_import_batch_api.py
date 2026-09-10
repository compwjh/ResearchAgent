import time
from threading import Event

from fastapi.testclient import TestClient

from backend.app.api import common, routes_paper
from backend.app.main import app
from backend.app.paper_discovery.application import paper_import as paper_import_module
from backend.app.paper_discovery.application.paper_import import (
    KB_STORAGE_LOCKED,
    LOGIN_REQUIRED,
    PaperImportError,
    PaperImportResult,
    import_candidate,
)
from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchService
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_download import DOWNLOAD_BLOCKED, DownloadResult
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


def _candidate(candidate_id="candidate-1", doi="10.1000/server-snapshot", title="A Server Snapshot Paper"):
    return PaperCandidate(
        candidate_id,
        "search-1",
        title,
        "ccs",
        "CCS",
        year=2025,
        doi=doi,
        article_url=f"https://dl.acm.org/doi/{doi}",
        pdf_url=f"https://dl.acm.org/doi/pdf/{doi}",
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
    common.paper_browser_sessions.clear()
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
    # Create returns queued immediately; the background runner drives the item
    # to waiting_login.  Poll until the first tick of progress is visible.
    assert created.json()["status"] == "queued"
    batch_id = created.json()["batch_id"]
    status = created.json()
    for _ in range(200):
        status = client.get(f"/api/papers/import-batches/{batch_id}").json()
        if status["items"][0]["status"] == "waiting_login":
            break
        time.sleep(0.01)
    assert status["status"] == "waiting_login"
    assert status["items"][0]["status"] == "waiting_login"
    item_id = status["items"][0]["item_id"]

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
    # Create now returns queued immediately; poll until the background run finishes.
    assert created.json()["status"] == "queued"
    status = created.json()
    for _ in range(200):
        status = client.get(f"/api/papers/import-batches/{batch_id}").json()
        if status["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    assert status["status"] == "completed"
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
    response = routes_paper._paper_import_error_response(
        DOWNLOAD_BLOCKED,
        "https://evil.example/file.pdf Cookie=session=secret Authorization=Bearer token",
    )
    body = response.body.decode()
    assert "evil.example" not in body
    assert "secret" not in body
    assert "authorization" not in body.lower()
    assert "论文导入失败" not in body
    assert "下载地址被安全策略拒绝" in body


def test_batch_create_returns_queued_and_completes_via_polling(monkeypatch, tmp_path):
    """POST /api/papers/imports 必须亚秒级返回 queued，且条目随后由后台推进。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    created = client.post(
        "/api/papers/imports",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"]},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "queued"
    assert all(item["status"] == "queued" for item in body["items"])
    batch_id = body["batch_id"]
    status = body
    for _ in range(200):
        status = client.get(f"/api/papers/imports/{batch_id}").json()
        if status["status"] in {"completed", "failed", "partial_success", "waiting_login"}:
            break
        time.sleep(0.01)
    assert status["status"] == "completed"
    assert status["items"][0]["status"] == "completed"


def test_duplicate_retry_does_not_duplicate_execution(monkeypatch, tmp_path):
    """同一批次重复 retry 只跑一次（单飞），不得并发重复下载。"""
    calls = {"n": 0}
    started = Event()
    finish = Event()

    def importer(candidate, *_args):
        calls["n"] += 1
        started.set()
        assert finish.wait(timeout=5)
        return PaperImportResult("paper-1", "safe.pdf", "indexed")

    _setup(monkeypatch, tmp_path, importer)
    client = TestClient(app)
    created = client.post(
        "/api/papers/imports",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"]},
    )
    assert created.json()["status"] == "queued"
    assert started.wait(timeout=5)
    batch_id = created.json()["batch_id"]
    # Two retries while the original run is still in flight; single-flight must
    # reuse the in-flight runner instead of starting a second download pass.
    client.post(f"/api/papers/imports/{batch_id}/retry")
    client.post(f"/api/papers/imports/{batch_id}/retry")
    finish.set()
    assert calls["n"] == 1


def test_batch_create_rejects_more_than_twenty_candidates(monkeypatch, tmp_path):
    """20 篇上限不变，超限仍返回 BATCH_LIMIT_EXCEEDED（spec-021 §边界）。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    ids = [f"candidate-{index}" for index in range(21)]
    response = client.post(
        "/api/papers/imports",
        json={"search_id": "search-1", "candidate_ids": ids},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BATCH_LIMIT_EXCEEDED"


def test_duplicate_batch_returns_duplicate_import_error(monkeypatch, tmp_path):
    """同一论文再次新建批次撞 import_item_title → 409 DUPLICATE_IMPORT（不再 IMPORT_BATCH_ERROR）。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    first = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    assert first.status_code == 200
    second = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    assert second.status_code == 409
    assert second.json()["code"] == "DUPLICATE_IMPORT"
    assert second.json()["message"] == "该论文已在导入批次中，请在原批次重试"


def test_item_retry_route_requeues_failed_item_and_returns_batch(monkeypatch, tmp_path):
    """POST /api/papers/import-items/{id}/retry：失败条目回到 queued 并后台重跑，200+批次负载。"""
    attempts: dict[str, int] = {}

    def importer(candidate, *_args):
        cid = candidate.candidate_id
        attempts[cid] = attempts.get(cid, 0) + 1
        if cid == "candidate-1" and attempts[cid] == 1:
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{cid}", "safe.pdf", "indexed")

    # 该端点需要两个候选都存在于服务端快照中（否则 CANDIDATE_NOT_FOUND），故本地保存两个。
    # 两个候选必须使用唯一 doi，否则会撞 paper_candidates 的 (search_id, doi) 唯一索引。
    discovery = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    discovery.save_search(
        SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        [
            _candidate(doi="10.1000/server-snapshot-1", title="A Server Snapshot Paper One"),
            _candidate("candidate-2", doi="10.1000/server-snapshot-2", title="A Server Snapshot Paper Two"),
        ],
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
    common.paper_browser_sessions.clear()
    client = TestClient(app)
    created = client.post(
        "/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1", "candidate-2"]}
    )
    batch_id = created.json()["batch_id"]
    status = created.json()
    for _ in range(200):
        status = client.get(f"/api/papers/imports/{batch_id}").json()
        if status["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    failed = next(item for item in status["items"] if item["status"] == "failed")
    assert failed["error_code"] == "DOWNLOAD_TIMEOUT"

    resp = client.post(f"/api/papers/import-items/{failed['item_id']}/retry")
    assert resp.status_code == 200
    # 立即返回：目标条目回到 queued/running；已成功条目不受影响。
    target = next(item for item in resp.json()["items"] if item["item_id"] == failed["item_id"])
    assert target["status"] in {"queued", "running"}
    other = next(item for item in resp.json()["items"] if item["candidate_id"] == "candidate-2")
    assert other["status"] == "completed"

    for _ in range(200):
        status = client.get(f"/api/papers/imports/{batch_id}").json()
        target = next(item for item in status["items"] if item["item_id"] == failed["item_id"])
        if target["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert target["status"] == "completed"
    assert attempts["candidate-1"] == 2
    assert attempts["candidate-2"] == 1


def test_item_retry_route_rejects_non_failed_item(monkeypatch, tmp_path):
    """已成功条目重试 → 400 INVALID_STATE_TRANSITION。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    created = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    batch_id = created.json()["batch_id"]
    status = created.json()
    for _ in range(200):
        status = client.get(f"/api/papers/imports/{batch_id}").json()
        if status["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    item_id = status["items"][0]["item_id"]
    resp = client.post(f"/api/papers/import-items/{item_id}/retry")
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_STATE_TRANSITION"


def test_item_retry_route_missing_item_returns_404(monkeypatch, tmp_path):
    """缺失条目重试 → 404 ITEM_NOT_FOUND。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    resp = client.post("/api/papers/import-items/does-not-exist/retry")
    assert resp.status_code == 404
    assert resp.json()["code"] == "ITEM_NOT_FOUND"


def test_storage_locked_import_sets_item_error_code_via_api(monkeypatch, tmp_path):
    """注入假 KB port 触发存储占用 → 批次 item error_code=KB_STORAGE_LOCKED（verification #3）。"""

    class LockedPort:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, _request):
            raise RuntimeError("data/kb/qdrant is already accessed by another instance of Qdrant client")

    discovery = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    discovery.save_search(SearchSession("search-1", "security", "2099-01-01T00:00:00Z"), [_candidate()])

    def fake_download(candidate, _settings, _allowed_hosts, **_kwargs):
        path = tmp_path / "dl.pdf"
        path.write_bytes(b"%PDF-1.7\ncontent")
        return DownloadResult(str(path), path.stat().st_size, "checksum", candidate.pdf_url)

    # import_candidate 的 downloader 默认参数是导入时捕获的旧对象，monkeypatch 模块全局不生效；
    # 改为通过 importer 包装显式注入 fake downloader。
    def importer_with_fake_download(candidate, settings, allowed_hosts, **kwargs):
        kwargs.setdefault("downloader", fake_download)
        return import_candidate(candidate, settings, allowed_hosts, **kwargs)

    service = PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "state.sqlite3"),
        discovery_store=discovery,
        importer=importer_with_fake_download,
    )
    monkeypatch.setattr(routes_paper, "_paper_store", lambda: discovery)
    monkeypatch.setattr(routes_paper, "_paper_batch_service", lambda: service)
    monkeypatch.setattr(paper_import_module, "get_provider", lambda _name: LockedPort())

    client = TestClient(app)
    created = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    assert created.status_code == 200
    batch_id = created.json()["batch_id"]
    status = created.json()
    for _ in range(200):
        status = client.get(f"/api/papers/imports/{batch_id}").json()
        if status["items"][0]["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    item = status["items"][0]
    assert item["status"] == "failed"
    assert item["error_code"] == KB_STORAGE_LOCKED
    # 异常原文（含路径/文件名）绝不得回显。
    assert "qdrant" not in (item["error_message"] or "")


def test_item_retry_route_hits_duplicate_title_returns_409(monkeypatch, tmp_path):
    """POST /api/papers/import-items/{id}/retry：失败条目的同名论文已在另一批次 completed
    → 409 DUPLICATE_IMPORT（不再 IMPORT_BATCH_ERROR/424）。spec-021 Task03（复现 bf22eaa2）。"""
    def importer(candidate, *_args):
        if candidate.candidate_id == "candidate-b":
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{candidate.candidate_id}", "safe.pdf", "indexed")

    discovery = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    # 同名候选必须落在不同 search session：paper_candidates 有
    # (search_id, normalized_title, year, conference_id) 唯一索引，同一 session 下无法存两个
    # 同名候选；但 paper_import_items 的 import_item_title 部分唯一索引与 search_id 无关，
    # 两个批次仍会因同名论文而冲突。
    discovery.save_search(
        SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        [_candidate("candidate-b", doi="10.1000/b", title="Collision Paper")],
    )
    discovery.save_search(
        SearchSession("search-2", "security", "2099-01-01T00:00:00Z"),
        [PaperCandidate("candidate-a", "search-2", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/a", article_url="https://dl.acm.org/doi/10.1000/a", pdf_url="https://dl.acm.org/doi/pdf/10.1000/a")],
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
    common.paper_browser_sessions.clear()
    client = TestClient(app)

    # 先建批次 B（candidate-b）→ 失败（释放索引）
    created_b = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-b"]})
    assert created_b.status_code == 200
    batch_b = created_b.json()["batch_id"]
    status_b = created_b.json()
    for _ in range(200):
        status_b = client.get(f"/api/papers/imports/{batch_b}").json()
        if status_b["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    failed_b = next(it for it in status_b["items"] if it["status"] == "failed")
    assert failed_b["error_code"] == "DOWNLOAD_TIMEOUT"

    # 再建批次 A（candidate-a）→ 完成（占住索引：completed 属于活跃态）
    created_a = client.post("/api/papers/imports", json={"search_id": "search-2", "candidate_ids": ["candidate-a"]})
    assert created_a.status_code == 200
    batch_a = created_a.json()["batch_id"]
    status_a = created_a.json()
    for _ in range(200):
        status_a = client.get(f"/api/papers/imports/{batch_a}").json()
        if status_a["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    assert next(it for it in status_a["items"] if it["status"] == "completed") is not None

    # 重试 B 的失败条目 → 撞 A 的 completed 索引 → 409 DUPLICATE_IMPORT
    resp = client.post(f"/api/papers/import-items/{failed_b['item_id']}/retry")
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_IMPORT"
    assert resp.json()["message"] == "该论文已在导入批次中，请在原批次重试"


def test_batch_retry_route_hits_duplicate_title_returns_409(monkeypatch, tmp_path):
    """POST /api/papers/imports/{batch_id}/retry（及别名 import-batches）→ 整批重试把
    failed→queued 撞同名活跃索引 → 409 DUPLICATE_IMPORT。spec-021 Task03。"""
    def importer(candidate, *_args):
        if candidate.candidate_id == "candidate-b":
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{candidate.candidate_id}", "safe.pdf", "indexed")

    discovery = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    # 同名候选必须落在不同 search session：paper_candidates 有
    # (search_id, normalized_title, year, conference_id) 唯一索引，同一 session 下无法存两个
    # 同名候选；但 paper_import_items 的 import_item_title 部分唯一索引与 search_id 无关，
    # 两个批次仍会因同名论文而冲突。
    discovery.save_search(
        SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        [_candidate("candidate-b", doi="10.1000/b", title="Collision Paper")],
    )
    discovery.save_search(
        SearchSession("search-2", "security", "2099-01-01T00:00:00Z"),
        [PaperCandidate("candidate-a", "search-2", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/a", article_url="https://dl.acm.org/doi/10.1000/a", pdf_url="https://dl.acm.org/doi/pdf/10.1000/a")],
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
    common.paper_browser_sessions.clear()
    client = TestClient(app)

    created_b = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-b"]})
    assert created_b.status_code == 200
    batch_b = created_b.json()["batch_id"]
    status_b = created_b.json()
    for _ in range(200):
        status_b = client.get(f"/api/papers/imports/{batch_b}").json()
        if status_b["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    assert next(it for it in status_b["items"] if it["status"] == "failed")["error_code"] == "DOWNLOAD_TIMEOUT"

    created_a = client.post("/api/papers/imports", json={"search_id": "search-2", "candidate_ids": ["candidate-a"]})
    assert created_a.status_code == 200
    batch_a = created_a.json()["batch_id"]
    status_a = created_a.json()
    for _ in range(200):
        status_a = client.get(f"/api/papers/imports/{batch_a}").json()
        if status_a["status"] in {"completed", "failed", "partial_success"}:
            break
        time.sleep(0.01)
    assert next(it for it in status_a["items"] if it["status"] == "completed") is not None

    # 整批重试 B（failed→queued）撞 A 的 completed 索引 → 409 DUPLICATE_IMPORT
    resp = client.post(f"/api/papers/imports/{batch_b}/retry")
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_IMPORT"
    assert resp.json()["message"] == "该论文已在导入批次中，请在原批次重试"

    # 别名路径同样可读（事务已回滚，B 仍是 failed，可再次复现）
    resp_alias = client.post(f"/api/papers/import-batches/{batch_b}/retry")
    assert resp_alias.status_code == 409
    assert resp_alias.json()["code"] == "DUPLICATE_IMPORT"
