import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from backend.app.api import common, routes_paper
from backend.app.main import app
from backend.app.paper_discovery.application import paper_import as paper_import_module
from backend.app.paper_discovery.application.entry import (
    BROWSER_SESSION_EXPIRED,
    BROWSER_SESSION_REQUIRED,
    BrowserManagerError,
)
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
    def __init__(self, download_error=None):
        self.closed = False
        self.download_error = download_error

    def close(self):
        self.closed = True

    def download_pdf(self, candidate, *_args, **kwargs):
        self.download_calls = getattr(self, "download_calls", [])
        self.download_calls.append((candidate.candidate_id, kwargs))
        if self.download_error is not None:
            raise BrowserManagerError(
                self.download_error,
                "https://evil.example Cookie=session=secret",
                retryable=True,
            )
        return None


class FakeBrowser:
    def __init__(self, download_error=None):
        self.opened = []
        self.sessions = []
        self.download_error = download_error

    def health(self):
        return {"available": True, "version": "1.52.0", "supported_sites": ["acm", "ieee"], "reason": None}

    def open_session(self, site, url):
        self.opened.append((site, url))
        session = FakeLoginSession(self.download_error)
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


def _setup(monkeypatch, tmp_path, importer, *, browser_download_error=None):
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
    browser = FakeBrowser(browser_download_error)
    monkeypatch.setattr(routes_paper, "_paper_store", lambda: discovery)
    monkeypatch.setattr(routes_paper, "_paper_batch_service", lambda: service)
    monkeypatch.setattr(routes_paper, "_paper_browser_manager", lambda: browser)
    common.paper_browser_sessions.clear()
    return service, browser


def _wait_for_batch_status(client, path, predicate, *, attempts=200, interval=0.01):
    """按谓词轮询批次状态，直到**批次聚合状态与条目状态同时**稳定满足条件。

    背景（既有 flaky，非本轮引入）：后台 runner 跑在模块级共享的
    ``ThreadPoolExecutor(max_workers=3)``（paper_import_batch_service.py:60）上，
    批次聚合行 ``state`` 与条目 ``state`` 由 store 的两次独立判读得出，读到的快照
    可能是「条目已终态、批次聚合尚未刷新（仍为 running）」的中间态。只等条目会让
    紧随其后的批次断言在全量套件的调度抖动下偶发失败。

    因此统一用 ``predicate(status)`` 同时约束批次聚合状态与条目状态，消除该窗口；
    谓词仍是对同一份服务端响应快照的断言，不改变用例语义，也不引入裸 sleep 等待。
    """
    status = None
    for _ in range(attempts):
        status = client.get(path).json()
        if predicate(status):
            return status
        time.sleep(interval)
    return status


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
    # to waiting_login.  Poll until the first tick of progress is visible —
    # the item CAS and the batch aggregation are two independent reads, so wait
    # for both to settle on waiting_login before asserting the snapshot.
    assert created.json()["status"] == "queued"
    batch_id = created.json()["batch_id"]
    status = _wait_for_batch_status(
        client,
        f"/api/papers/import-batches/{batch_id}",
        lambda body: body["items"][0]["status"] == "waiting_login"
        and body["status"] == "waiting_login",
    )
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
    status = _wait_for_batch_status(
        client,
        f"/api/papers/import-batches/{batch_id}",
        lambda body: body["status"] in {"completed", "failed", "partial_success"},
    )
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
    batch_id = created.json()["batch_id"]
    # The create endpoint is asynchronous; wait until the first attempt has
    # reached waiting_login before opening the browser session.  Otherwise the
    # resume call can race the initial claim and return its pre-login snapshot.
    _wait_for_batch_status(
        client,
        f"/api/papers/import-batches/{batch_id}",
        lambda body: body["items"][0]["status"] == "waiting_login",
    )
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


@pytest.mark.parametrize("browser_code", [BROWSER_SESSION_EXPIRED, BROWSER_SESSION_REQUIRED])
def test_resume_browser_session_race_returns_424_without_reimport(monkeypatch, tmp_path, browser_code):
    attempts = []

    def importer(candidate, *_args, downloader=None, **_kwargs):
        attempts.append(candidate.candidate_id)
        if downloader is None:
            raise PaperImportError(LOGIN_REQUIRED, "需要登录", retryable=True)
        downloader(candidate)
        return PaperImportResult("paper-1", "safe.pdf", "indexed")

    service, browser = _setup(
        monkeypatch,
        tmp_path,
        importer,
        browser_download_error=browser_code,
    )
    client = TestClient(app)
    created = client.post(
        "/api/papers/import-batches",
        json={"search_id": "search-1", "candidate_ids": ["candidate-1"]},
    )
    item_id = created.json()["items"][0]["item_id"]
    client.post(f"/api/papers/import-items/{item_id}/login")

    response = client.post(f"/api/papers/import-items/{item_id}/resume")

    assert response.status_code == 424
    assert response.json()["code"] == browser_code
    assert response.json()["retryable"] is True
    assert attempts == ["candidate-1", "candidate-1"]
    assert browser.sessions[0].closed is True
    body = response.text.lower()
    assert "evil.example" not in body
    assert "secret" not in body
    current = service.store.get_item(item_id)
    assert current.status == "failed"
    assert current.error_code == browser_code


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
    status = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_id}",
        lambda payload: payload["status"] == "completed"
        and payload["items"][0]["status"] == "completed",
    )
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
    """同一论文在**活跃态**再次新建批次撞 import_item_title → 409 DUPLICATE_IMPORT。

    用阻塞的 importer 把首个条目稳定停在 downloading（活跃态），消除后台 runner 抢跑竞态；
    若首条目已 completed 则不再 409（见 test_completed_item_no_longer_blocks_new_batch_via_api）。
    """
    started = Event()
    finish = Event()

    def importer(candidate, *_args):
        started.set()
        assert finish.wait(timeout=5)
        return PaperImportResult("paper-1", "safe.pdf", "indexed")

    _setup(monkeypatch, tmp_path, importer)
    client = TestClient(app)
    first = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    assert first.status_code == 200
    assert started.wait(timeout=5)  # 条目已进入活跃态
    second = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    finish.set()
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
    status = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_id}",
        lambda body: body["status"] in {"completed", "failed", "partial_success"}
        and any(item["status"] == "failed" for item in body["items"]),
    )
    failed = next(item for item in status["items"] if item["status"] == "failed")
    assert failed["error_code"] == "DOWNLOAD_TIMEOUT"

    resp = client.post(f"/api/papers/import-items/{failed['item_id']}/retry")
    assert resp.status_code == 200
    # 立即返回：目标条目回到 queued/running；已成功条目不受影响。
    target = next(item for item in resp.json()["items"] if item["item_id"] == failed["item_id"])
    assert target["status"] in {"queued", "running"}
    other = next(item for item in resp.json()["items"] if item["candidate_id"] == "candidate-2")
    assert other["status"] == "completed"

    status = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_id}",
        lambda body: body["status"] == "completed"
        and next(
            item for item in body["items"] if item["item_id"] == failed["item_id"]
        )["status"]
        == "completed",
    )
    target = next(item for item in status["items"] if item["item_id"] == failed["item_id"])
    assert target["status"] == "completed"
    assert attempts["candidate-1"] == 2
    assert attempts["candidate-2"] == 1


def test_item_retry_route_rejects_non_failed_item(monkeypatch, tmp_path):
    """已成功条目重试 → 400 INVALID_STATE_TRANSITION。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    created = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    batch_id = created.json()["batch_id"]
    status = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_id}",
        lambda body: body["status"] in {"completed", "failed", "partial_success"},
    )
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
    # 条目进入终态与批次聚合刷新是两次独立判读，等两者同时收敛再断言。
    status = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_id}",
        lambda body: body["items"][0]["status"] in {"completed", "failed"}
        and body["status"] in {"completed", "failed", "partial_success"},
    )
    item = status["items"][0]
    assert item["status"] == "failed"
    assert item["error_code"] == KB_STORAGE_LOCKED
    # 异常原文（含路径/文件名）绝不得回显。
    assert "qdrant" not in (item["error_message"] or "")


def _blocking_active_importer(started, finish):
    """candidate-b 立即失败；candidate-a 阻塞在活跃态（downloading）直到 finish。"""
    def importer(candidate, *_args):
        if candidate.candidate_id == "candidate-b":
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        started.set()
        assert finish.wait(timeout=5)
        return PaperImportResult(f"paper-{candidate.candidate_id}", "safe.pdf", "indexed")

    return importer


def test_item_retry_route_hits_active_duplicate_title_returns_409(monkeypatch, tmp_path):
    """POST /api/papers/import-items/{id}/retry：失败条目的同名论文在另一批次处于**活跃态**
    → 409 DUPLICATE_IMPORT（仅活跃态冲突映射 409）。spec-021 Task03/Task06。"""
    started, finish = Event(), Event()
    importer = _blocking_active_importer(started, finish)

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
    status_b = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_b}",
        lambda body: body["status"] == "failed"
        and next(it for it in body["items"] if it["status"] == "failed")["error_code"]
        == "DOWNLOAD_TIMEOUT",
    )
    failed_b = next(it for it in status_b["items"] if it["status"] == "failed")
    assert failed_b["error_code"] == "DOWNLOAD_TIMEOUT"

    # 再建批次 A（candidate-a）→ 其后台 runner 稳定停在 downloading（活跃态，占住索引）
    created_a = client.post("/api/papers/imports", json={"search_id": "search-2", "candidate_ids": ["candidate-a"]})
    assert created_a.status_code == 200
    assert started.wait(timeout=5)

    # 重试 B 的失败条目 → 撞 A 的活跃索引 → 409 DUPLICATE_IMPORT
    resp = client.post(f"/api/papers/import-items/{failed_b['item_id']}/retry")
    finish.set()
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_IMPORT"
    assert resp.json()["message"] == "该论文已在导入批次中，请在原批次重试"


def test_batch_retry_route_hits_active_duplicate_title_returns_409(monkeypatch, tmp_path):
    """POST /api/papers/imports/{batch_id}/retry（及别名 import-batches）→ 整批重试把
    failed→queued 撞同名**活跃**索引 → 409 DUPLICATE_IMPORT。spec-021 Task03/Task06。"""
    started, finish = Event(), Event()
    importer = _blocking_active_importer(started, finish)

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
    status_b = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_b}",
        lambda body: body["status"] == "failed"
        and next(it for it in body["items"] if it["status"] == "failed")["error_code"]
        == "DOWNLOAD_TIMEOUT",
    )
    assert next(it for it in status_b["items"] if it["status"] == "failed")["error_code"] == "DOWNLOAD_TIMEOUT"

    created_a = client.post("/api/papers/imports", json={"search_id": "search-2", "candidate_ids": ["candidate-a"]})
    assert created_a.status_code == 200
    assert started.wait(timeout=5)  # candidate-a 稳定停在活跃态

    # 整批重试 B（failed→queued）撞 A 的活跃索引 → 409 DUPLICATE_IMPORT
    resp = client.post(f"/api/papers/imports/{batch_b}/retry")
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_IMPORT"
    assert resp.json()["message"] == "该论文已在导入批次中，请在原批次重试"

    # 别名路径同样可读（事务已回滚，B 仍是 failed，可再次复现）
    resp_alias = client.post(f"/api/papers/import-batches/{batch_b}/retry")
    finish.set()
    assert resp_alias.status_code == 409
    assert resp_alias.json()["code"] == "DUPLICATE_IMPORT"


def test_completed_item_no_longer_blocks_new_batch_via_api(monkeypatch, tmp_path):
    """已 completed 的论文再次新建批次 → 不再 409，正常入队（spec-021 Task06）。
    去重交由 KB find_existing（结果表达 PAPER_ALREADY_EXISTS），不再由批次层拒绝。"""
    _setup(monkeypatch, tmp_path, lambda *_args: PaperImportResult("paper-1", "safe.pdf", "indexed"))
    client = TestClient(app)
    first = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    assert first.status_code == 200
    batch_id = first.json()["batch_id"]
    status = _wait_for_batch_status(
        client,
        f"/api/papers/imports/{batch_id}",
        lambda body: body["status"] == "completed"
        and body["items"][0]["status"] == "completed",
    )
    assert status["status"] == "completed"

    second = client.post("/api/papers/imports", json={"search_id": "search-1", "candidate_ids": ["candidate-1"]})
    assert second.status_code == 200
    assert second.json()["batch_id"] != batch_id
    assert second.json()["status"] == "queued"
