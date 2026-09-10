import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest

from backend.app.paper_discovery.application.entry import (
    BROWSER_SESSION_EXPIRED,
    BROWSER_SESSION_REQUIRED,
    BrowserManagerError,
)
from backend.app.paper_discovery.application.paper_import import LOGIN_REQUIRED, PaperImportError, PaperImportResult
from backend.app.paper_discovery.application.paper_import_batch_service import (
    CANDIDATE_NOT_FOUND,
    INVALID_SEARCH_SNAPSHOT,
    PaperImportBatchService,
    PaperImportBatchServiceError,
)
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.domain.paper_import_batch import (
    BATCH_WAITING_LOGIN,
    ITEM_COMPLETED,
    ITEM_DOWNLOADING,
    ITEM_FAILED,
    ITEM_WAITING_LOGIN,
)
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import (
    DATABASE_LOCKED,
    PaperImportBatchStore,
    PaperImportBatchStoreError,
)


def _candidate(candidate_id: str, search_id: str = "search-1") -> PaperCandidate:
    return PaperCandidate(
        candidate_id,
        search_id,
        f"Paper {candidate_id}",
        "ccs",
        "CCS",
        year=2025,
        doi=f"10.1000/{candidate_id}",
        article_url="https://papers.example/article",
        pdf_url="https://papers.example/paper.pdf",
    )


def _service(tmp_path, importer, *, max_workers=3):
    return PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "state.sqlite3"),
        importer=importer,
        max_workers=max_workers,
    )


def _create(service, candidates):
    return service.create_batch(
        "search-1",
        [candidate.candidate_id for candidate in candidates],
        search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        candidates=candidates,
    )


def test_public_items_continue_when_one_item_requires_login(tmp_path):
    calls = []

    def importer(candidate, *_args):
        calls.append(candidate.candidate_id)
        if candidate.candidate_id == "login":
            raise PaperImportError(LOGIN_REQUIRED, "需要登录", retryable=True)
        return PaperImportResult("paper-public", "2025-CCS-Paper-public.pdf", "indexed")

    service = _service(tmp_path, importer)
    candidates = [_candidate("public"), _candidate("login")]
    batch = _create(service, candidates)

    result = service.run_batch(batch.batch_id)

    items = {item.candidate_id: item for item in service.store.get_items(batch.batch_id)}
    assert items["public"].status == ITEM_COMPLETED
    assert items["login"].status == ITEM_WAITING_LOGIN
    assert result.status == BATCH_WAITING_LOGIN
    assert set(calls) == {"public", "login"}


def test_failed_item_can_be_retried_and_success_is_not_reexecuted(tmp_path):
    attempts = {"retry": 0, "done": 0}

    def importer(candidate, *_args):
        attempts[candidate.candidate_id] += 1
        if candidate.candidate_id == "retry" and attempts["retry"] == 1:
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    candidates = [_candidate("retry"), _candidate("done")]
    batch = _create(service, candidates)
    service.run_batch(batch.batch_id)
    assert service.store.get_item(service.store.get_items(batch.batch_id)[0].item_id).status == ITEM_FAILED

    service.retry_batch(batch.batch_id, candidates=candidates)

    items = {item.candidate_id: item for item in service.store.get_items(batch.batch_id)}
    assert items["retry"].status == ITEM_COMPLETED
    assert items["done"].status == ITEM_COMPLETED
    assert attempts == {"retry": 2, "done": 1}


def test_concurrent_processing_allows_one_claimed_executor(tmp_path):
    calls = 0
    lock = Lock()
    importer_started = Event()
    allow_importer_to_finish = Event()

    def importer(candidate, *_args):
        nonlocal calls
        with lock:
            calls += 1
        importer_started.set()
        assert allow_importer_to_finish.wait(timeout=5)
        return PaperImportResult("paper-one", None, "indexed")

    service = _service(tmp_path, importer, max_workers=2)
    candidate = _candidate("one")
    batch = _create(service, [candidate])
    item = service.store.get_items(batch.batch_id)[0]
    service._snapshots[batch.batch_id] = {candidate.candidate_id: candidate}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.process_item, item.item_id) for _index in range(2)]
        assert importer_started.wait(timeout=2)
        deadline = time.monotonic() + 2
        while service.store.get_item(item.item_id).status != ITEM_DOWNLOADING and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.store.get_item(item.item_id).status == ITEM_DOWNLOADING
        allow_importer_to_finish.set()
        results = [future.result(timeout=5) for future in futures]

    assert calls == 1
    assert all(result.status == ITEM_COMPLETED for result in results)
    assert service.store.get_item(item.item_id).attempt_count == 1


def test_concurrent_resume_waits_for_the_claimed_executor(tmp_path):
    calls = 0
    lock = Lock()
    importer_started = Event()
    allow_importer_to_finish = Event()

    def importer(_candidate, *_args):
        nonlocal calls
        with lock:
            calls += 1
        importer_started.set()
        assert allow_importer_to_finish.wait(timeout=5)
        return PaperImportResult("paper-resumed", None, "indexed")

    service = _service(tmp_path, importer, max_workers=2)
    candidate = _candidate("resume")
    batch = _create(service, [candidate])
    item = service.store.get_items(batch.batch_id)[0]
    service.store.claim_item(item.item_id, "login-worker")
    service.store.transition_item(
        item.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING,
        lease_owner="login-worker",
    )
    service._snapshots[batch.batch_id] = {candidate.candidate_id: candidate}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.resume_item, item.item_id) for _index in range(2)]
        assert importer_started.wait(timeout=2)
        deadline = time.monotonic() + 2
        while service.store.get_item(item.item_id).status != ITEM_DOWNLOADING and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.store.get_item(item.item_id).status == ITEM_DOWNLOADING
        allow_importer_to_finish.set()
        results = [future.result(timeout=5) for future in futures]

    assert calls == 1
    assert all(result.status == ITEM_COMPLETED for result in results)
    assert service.store.get_item(item.item_id).attempt_count == 2


def test_expired_lease_is_recovered_to_stable_failure_and_can_resume(tmp_path):
    calls = 0

    def importer(candidate, *_args):
        nonlocal calls
        calls += 1
        return PaperImportResult("paper-recovered", None, "indexed")

    service = _service(tmp_path, importer)
    candidate = _candidate("recover")
    batch = _create(service, [candidate])
    item = service.store.get_items(batch.batch_id)[0]
    service.store.claim_item(item.item_id, "dead-worker", now="2026-01-01T00:00:00Z", lease_seconds=1)

    assert service.recover_expired_leases(now="2026-01-01T00:01:00Z") == 1
    recovered = service.store.get_item(item.item_id)
    assert recovered.status == ITEM_FAILED
    assert recovered.error_code == "IMPORT_INTERRUPTED"

    service.retry_item(item.item_id, candidates=[candidate])
    assert service.store.get_item(item.item_id).status == ITEM_COMPLETED
    assert calls == 1


def test_old_worker_cannot_mark_reclaimed_item_failed(tmp_path):
    def importer(_candidate, *_args):
        raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)

    service = _service(tmp_path, importer)
    candidate = _candidate("reclaimed")
    batch = _create(service, [candidate])
    item = service.store.get_items(batch.batch_id)[0]
    service.store.claim_item(item.item_id, "old-worker", now="2026-01-01T00:00:00Z", lease_seconds=1)
    assert service.store.recover_expired_leases(now="2026-01-01T00:00:02Z") == 1
    service.store.retry_item(item.item_id)
    service.store.claim_item(item.item_id, "new-worker", now="2026-01-01T00:00:03Z")

    result = service._import_one(item, candidate, "old-worker")

    assert result.status == "downloading"
    current = service.store.get_item(item.item_id)
    assert current.lease_owner == "new-worker"
    assert current.error_code is None


def test_database_locked_is_reported_as_retryable_service_error(tmp_path, monkeypatch):
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    candidate = _candidate("locked")
    batch = _create(service, [candidate])
    item = service.store.get_items(batch.batch_id)[0]

    def locked_claim(*_args, **_kwargs):
        raise PaperImportBatchStoreError(DATABASE_LOCKED, "批次状态库正忙，请稍后重试")

    monkeypatch.setattr(service.store, "claim_item", locked_claim)
    with pytest.raises(PaperImportBatchServiceError) as error:
        service.process_item(item.item_id, candidates=[candidate], lease_owner="worker")

    assert error.value.code == DATABASE_LOCKED
    assert error.value.retryable is True


def test_batch_creation_rejects_expired_or_cross_search_snapshots(tmp_path):
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    with pytest.raises(PaperImportBatchServiceError) as expired:
        service.create_batch(
            "search-1", ["c1"],
            search_session=SearchSession("search-1", "security", "2000-01-01T00:00:00Z"),
            candidates=[_candidate("c1")],
        )
    assert expired.value.code == "SEARCH_EXPIRED"

    with pytest.raises(PaperImportBatchServiceError) as mismatch:
        service.create_batch(
            "search-1", ["c1"],
            search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
            candidates=[_candidate("c1", "other-search")],
        )
    assert mismatch.value.code == INVALID_SEARCH_SNAPSHOT

    with pytest.raises(PaperImportBatchServiceError) as missing:
        service.create_batch(
            "search-1", ["missing"],
            search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
            candidates=[_candidate("c1")],
        )
    assert missing.value.code == CANDIDATE_NOT_FOUND


def test_resume_passes_authenticated_downloader_and_context_only_to_current_item(tmp_path):
    received = []
    context = object()
    def downloader(*_args, **_kwargs):
        return None

    def importer(candidate, *_args, downloader=None, context=None, **_kwargs):
        received.append((candidate.candidate_id, downloader, context))
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    candidates = [_candidate("one"), _candidate("two")]
    batch = _create(service, candidates)
    first, second = service.store.get_items(batch.batch_id)
    for item in (first, second):
        service.store.claim_item(item.item_id, f"login-{item.candidate_id}")
        service.store.transition_item(
            item.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING,
            lease_owner=f"login-{item.candidate_id}",
        )
    service._snapshots[batch.batch_id] = {candidate.candidate_id: candidate for candidate in candidates}

    service.resume_item(first.item_id, downloader=downloader, context=context)
    service.resume_item(second.item_id, downloader=None, context=None)

    assert received == [("one", downloader, context), ("two", None, None)]


def test_claim_credentials_are_forwarded_to_the_real_importer_contract(tmp_path):
    received = []

    def importer(candidate, *_args, attempt_owner=None, attempt_token=None):
        received.append((candidate.candidate_id, attempt_owner, attempt_token))
        return PaperImportResult("paper-credentials", None, "indexed")

    service = _service(tmp_path, importer)
    batch = _create(service, [_candidate("credentials")])
    service.run_batch(batch.batch_id)

    item = service.store.get_items(batch.batch_id)[0]
    assert item.status == ITEM_COMPLETED
    assert received[0][0] == "credentials"
    assert received[0][1] == item.attempt_owner
    assert received[0][2] == item.attempt_token
    assert item.attempt_owner.startswith("paper-import:")
    assert item.attempt_token


def test_batch_item_persists_only_fixed_safe_error_message(tmp_path):
    def importer(_candidate, *_args):
        raise RuntimeError(
            "https://evil.example/file.pdf Cookie=session=secret "
            "Authorization: Bearer token password=hunter2"
        )

    service = _service(tmp_path, importer)
    candidate = _candidate("sensitive-error")
    batch = _create(service, [candidate])
    service.run_batch(batch.batch_id)

    item = service.store.get_items(batch.batch_id)[0]
    assert item.status == ITEM_FAILED
    assert item.error_code == "IMPORT_FAILED"
    assert item.error_message == "论文导入失败"
    assert "evil.example" not in item.error_message
    assert "secret" not in item.error_message
    assert "token" not in item.error_message
    assert "password" not in item.error_message


@pytest.mark.parametrize("browser_code", [BROWSER_SESSION_EXPIRED, BROWSER_SESSION_REQUIRED])
def test_browser_session_failure_is_persisted_without_completed_transition(tmp_path, browser_code):
    calls = 0

    def importer(_candidate, *_args):
        nonlocal calls
        calls += 1
        raise BrowserManagerError(
            browser_code,
            "https://evil.example Cookie=session=secret",
            retryable=True,
        )

    service = _service(tmp_path, importer)
    batch = _create(service, [_candidate(f"browser-{browser_code}")])
    service.run_batch(batch.batch_id)

    item = service.store.get_items(batch.batch_id)[0]
    assert calls == 1
    assert item.status == ITEM_FAILED
    assert item.error_code == browser_code
    assert item.error_message in {"受控登录会话已过期，请重新登录", "请先完成受控登录后再续传"}
    assert item.status != ITEM_COMPLETED
    assert "evil.example" not in item.error_message
    assert "secret" not in item.error_message
