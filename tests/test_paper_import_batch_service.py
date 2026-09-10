import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from unittest.mock import patch

import pytest

from backend.app.paper_discovery.application.entry import (
    BROWSER_SESSION_EXPIRED,
    BROWSER_SESSION_REQUIRED,
    BrowserManagerError,
)
from backend.app.paper_discovery.application.paper_import import (
    KB_STORAGE_LOCKED,
    LOGIN_REQUIRED,
    PAPER_ALREADY_EXISTS,
    PaperImportError,
    PaperImportResult,
    import_candidate,
)
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
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import (
    DATABASE_LOCKED,
    PaperImportBatchStore,
    PaperImportBatchStoreError,
)
from backend.app.platform.settings.settings_repository import ArticleSettings


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


def test_failed_item_can_be_retried_and_success_is_not_reexecuted(tmp_path, monkeypatch):
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

    # retry_batch 提交后台 runner 后入队即返回；捕获该 Future 并确定性等待其完成
    # （不轮询 store 时序，消除对后台线程速度的依赖）。
    captured: dict[str, object] = {}
    original_submit = service.submit_batch

    def capture_submit(batch_id, *, candidates=None):
        future = original_submit(batch_id, candidates=candidates)
        captured["future"] = future
        return future

    with monkeypatch.context() as m:
        m.setattr(service, "submit_batch", capture_submit)
        service.retry_batch(batch.batch_id, candidates=candidates)

    assert captured["future"].result(timeout=5) is not None
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


def test_expired_lease_is_recovered_to_stable_failure_and_can_resume(tmp_path, monkeypatch):
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

    # retry_item 后台提交，入队即返回；捕获 Future 并确定性等待完成（不轮询 store 时序）。
    captured: dict[str, object] = {}
    original_submit = service.submit_batch

    def capture_submit(batch_id, *, candidates=None):
        future = original_submit(batch_id, candidates=candidates)
        captured["future"] = future
        return future

    with monkeypatch.context() as m:
        m.setattr(service, "submit_batch", capture_submit)
        service.retry_item(item.item_id, candidates=[candidate])

    assert captured["future"].result(timeout=5) is not None
    items = {item.candidate_id: item for item in service.store.get_items(batch.batch_id)}
    assert items["recover"].status == ITEM_COMPLETED
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

def test_submit_batch_is_single_flight_and_runs_in_background(tmp_path):
    """重复触发的批次只产生一个后台 runner（spec-021 §边界：单飞）。"""
    started = Event()
    finish = Event()

    def importer(candidate, *_args):
        started.set()
        assert finish.wait(timeout=5)
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    candidate = _candidate("one")
    batch = _create(service, [candidate])

    # Two submits while nothing is in flight must share one Future/runner.
    first = service.submit_batch(batch.batch_id)
    second = service.submit_batch(batch.batch_id)
    assert second is first
    assert len(service._batch_runners) == 1
    # The batch is still queued in the request thread; the run is backgrounded.
    assert service.store.get_batch(batch.batch_id).status == "queued"

    finish.set()
    assert first.result(timeout=5) is not None
    assert service.store.get_items(batch.batch_id)[0].status == ITEM_COMPLETED
    assert batch.batch_id not in service._batch_runners


def test_failed_item_retry_runs_in_background_and_is_single_flight(tmp_path):
    """retry_batch 不再阻塞请求线程；重复 retry 不重复执行（spec-021）。"""
    attempts = {"retry": 0, "done": 0}
    started = Event()
    finish = Event()

    def importer(candidate, *_args):
        attempts[candidate.candidate_id] += 1
        if candidate.candidate_id == "retry":
            started.set()
            assert finish.wait(timeout=5)
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    candidates = [_candidate("retry"), _candidate("done")]
    batch = _create(service, candidates)
    # Simulate a prior failure without running the (blocking) importer.
    service.store.mark_failed(
        service.store.get_items(batch.batch_id)[0].item_id, "IMPORT_FAILED", "先前置失败", lease_owner=None
    )

    # First retry: re-queues the failed item and submits a background runner.
    service.retry_batch(batch.batch_id, candidates=candidates)
    assert started.wait(timeout=5)
    # Duplicate retry while the runner is in flight must be a single-flight no-op.
    runner_before = service._batch_runners.get(batch.batch_id)
    service.retry_batch(batch.batch_id, candidates=candidates)
    assert service._batch_runners.get(batch.batch_id) is runner_before
    finish.set()
    # Wait for the single background run to finish its state transitions.
    assert runner_before.result(timeout=5) is not None

    items = {item.candidate_id: item for item in service.store.get_items(batch.batch_id)}
    assert items["retry"].status == ITEM_COMPLETED
    assert items["done"].status == ITEM_COMPLETED
    assert attempts == {"retry": 1, "done": 1}


def test_create_batch_auto_run_returns_queued_without_finishing_any_item(tmp_path, monkeypatch):
    """create_batch(auto_run=True) 入队即返回 queued，请求线程内不推进条目。

    确定性版本（消除后台线程抢跑竞态）：用桩替换 `submit_batch`，断言
    『已提交、但未执行』。由于唯一推进条目的 `submit_batch` 被记录但未启动后台
    runner，条目保持 queued 与 create_batch 返回态一致——证明请求线程没有完成任何
    条目（也不依赖后台线程时序）。未触碰 backend/** 业务语义。
    """
    submitted: list[str] = []

    def stub_submit(batch_id, *, candidates=None):
        # 故意不启动后台 runner：证明 create_batch 仅『入队 + 提交』，
        # 真正的导入执行完全发生在 submit_batch（后台）里，而非请求线程。
        submitted.append(batch_id)
        return None

    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    with monkeypatch.context() as m:
        m.setattr(service, "submit_batch", stub_submit)
        returned = service.create_batch(
            "search-1",
            ["one"],
            search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
            candidates=[_candidate("one")],
            auto_run=True,
        )
    # 入队即返回 queued；因 submit_batch 未执行，条目未在任何线程被推进。
    assert returned.status == "queued"
    assert all(item.status == "queued" for item in service.store.get_items(returned.batch_id))
    # 确定性证明：create_batch 确实提交了后台执行（但本次未执行）。
    assert submitted == [returned.batch_id]


def test_duplicate_title_across_batches_maps_to_duplicate_import(tmp_path):
    """对已有条目的同一论文再次新建批次撞 import_item_title 唯一索引 → DUPLICATE_IMPORT
    （spec-021 §边界：禁止再被 IMPORT_BATCH_ERROR 兜底掩盖）。
    """
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    candidates = [_candidate("dup")]
    service.create_batch(
        "search-1", ["dup"],
        search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        candidates=candidates,
    )
    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.create_batch(
            "search-1", ["dup"],
            search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
            candidates=candidates,
        )
    assert exc.value.code == "DUPLICATE_IMPORT"


def test_retry_item_runs_in_background_and_only_retries_target(tmp_path, monkeypatch):
    """retry_item 仅把目标条目回到 queued 并后台执行；已成功条目不被重跑（spec-021 §边界）。"""
    attempts: dict[str, int] = {}

    def importer(candidate, *_args):
        cid = candidate.candidate_id
        attempts[cid] = attempts.get(cid, 0) + 1
        if cid == "retry" and attempts[cid] == 1:
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{cid}", None, "indexed")

    service = _service(tmp_path, importer)
    candidates = [_candidate("retry"), _candidate("done")]
    batch = _create(service, candidates)
    service.run_batch(batch.batch_id)  # retry 首跑失败（FAILED），done 成功（COMPLETED）
    retry_item_id = next(
        item.item_id for item in service.store.get_items(batch.batch_id) if item.candidate_id == "retry"
    )

    # retry_item 后台提交，入队即返回；捕获该 Future 并确定性等待完成
    # （不轮询 store 时序，消除对后台线程速度的依赖）。
    returned = None
    captured: dict[str, object] = {}
    original_submit = service.submit_batch

    def capture_submit(batch_id, *, candidates=None):
        future = original_submit(batch_id, candidates=candidates)
        captured["future"] = future
        return future

    with monkeypatch.context() as m:
        m.setattr(service, "submit_batch", capture_submit)
        returned = service.retry_item(retry_item_id, candidates=candidates)
    # 入队即返回，不在请求线程等待。
    assert returned.status == "queued"

    assert captured["future"].result(timeout=5) is not None
    items = {item.candidate_id: item for item in service.store.get_items(batch.batch_id)}
    assert items["retry"].status == ITEM_COMPLETED
    assert items["done"].status == ITEM_COMPLETED
    assert attempts == {"retry": 2, "done": 1}  # done 不重跑


def test_retry_item_rejects_non_failed_state(tmp_path):
    """非 failed 条目重试 → INVALID_STATE_TRANSITION（仅 failed 可重试）。"""
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    candidate = _candidate("one")
    batch = _create(service, [candidate])
    service.run_batch(batch.batch_id)  # 成功
    item_id = service.store.get_items(batch.batch_id)[0].item_id
    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.retry_item(item_id, candidates=[candidate])
    assert exc.value.code == "INVALID_STATE_TRANSITION"


def test_retry_item_missing_item_raises_item_not_found(tmp_path):
    """缺失条目重试 → ITEM_NOT_FOUND。"""
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.retry_item("missing-item", candidates=[])
    assert exc.value.code == "ITEM_NOT_FOUND"


def test_retry_item_hits_active_title_index_collision_maps_to_duplicate_import(tmp_path):
    """重试一个 failed 条目，其同名论文已在另一批次处于**活跃态** → 必须映射为
    DUPLICATE_IMPORT（spec-021 Task03/Task06：仅活跃态冲突映射 409）。

    构建顺序：先建批次 A（同名候选 a）并 claim 到 downloading（活跃态，占索引），
    再让 B 的 failed 条目回 queued（活跃态）时撞索引。
    """
    def importer(candidate, *_args):
        if candidate.candidate_id == "b":
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    # 候选 b 与 a 同名同会议同年度 → normalized_title/year/conference_id 相同，会撞索引。
    cand_b = PaperCandidate("b", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/b")
    cand_a = PaperCandidate("a", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/a")
    session = SearchSession("search-1", "security", "2099-01-01T00:00:00Z")
    # 先建批次 B（candidate b）→ 失败（释放索引，不再活跃）
    batch_b = service.create_batch("search-1", ["b"], search_session=session, candidates=[cand_b])
    service.run_batch(batch_b.batch_id)
    # 再建批次 A（candidate a）→ claim 到 downloading（活跃态，占住索引）
    batch_a = service.create_batch("search-1", ["a"], search_session=session, candidates=[cand_a])
    a_item = service.store.get_items(batch_a.batch_id)[0]
    service.store.claim_item(a_item.item_id, "worker")

    b_items = {it.candidate_id: it for it in service.store.get_items(batch_b.batch_id)}
    assert b_items["b"].status == ITEM_FAILED
    assert service.store.get_item(a_item.item_id).status == ITEM_DOWNLOADING

    # 重试 B 的失败条目 → failed→queued 撞 A 的活跃索引 → DUPLICATE_IMPORT
    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.retry_item(b_items["b"].item_id, candidates=[cand_b])
    assert exc.value.code == "DUPLICATE_IMPORT"


def test_retry_batch_hits_active_title_index_collision_maps_to_duplicate_import(tmp_path):
    """整批重试：批次内含 failed 条目，其同名论文已在另一批次处于活跃态 →
    sqlite3.IntegrityError 必须映射为 DUPLICATE_IMPORT（spec-021 Task03/Task06）。
    """
    def importer(candidate, *_args):
        if candidate.candidate_id == "b":
            raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    cand_b = PaperCandidate("b", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/b")
    cand_a = PaperCandidate("a", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/a")
    session = SearchSession("search-1", "security", "2099-01-01T00:00:00Z")
    batch_b = service.create_batch("search-1", ["b"], search_session=session, candidates=[cand_b])
    service.run_batch(batch_b.batch_id)
    batch_a = service.create_batch("search-1", ["a"], search_session=session, candidates=[cand_a])
    a_item = service.store.get_items(batch_a.batch_id)[0]
    service.store.claim_item(a_item.item_id, "worker")

    b_items = {it.candidate_id: it for it in service.store.get_items(batch_b.batch_id)}
    assert b_items["b"].status == ITEM_FAILED
    assert service.store.get_item(a_item.item_id).status == ITEM_DOWNLOADING

    # 整批重试 B（failed→queued）撞 A 的活跃索引 → DUPLICATE_IMPORT
    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.retry_batch(batch_b.batch_id, candidates=[cand_b])
    assert exc.value.code == "DUPLICATE_IMPORT"


def test_completed_item_no_longer_blocks_new_batch_or_retry(tmp_path, monkeypatch):
    """已 completed 的同名条目释放索引 → 同论文可新建批次、failed 条目可重试
    （spec-021 Task06；去重交由 KB find_existing，非批次层拒绝）。"""
    attempts = {"b": 0}

    def importer(candidate, *_args):
        if candidate.candidate_id == "b":
            attempts["b"] += 1
            if attempts["b"] == 1:
                raise PaperImportError("DOWNLOAD_TIMEOUT", "下载超时", retryable=True)
        return PaperImportResult(f"paper-{candidate.candidate_id}", None, "indexed")

    service = _service(tmp_path, importer)
    cand_b = PaperCandidate("b", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/b")
    cand_a = PaperCandidate("a", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/a")
    cand_c = PaperCandidate("c", "search-1", "Collision Paper", "ccs", "CCS", year=2025, doi="10.1000/c")
    session = SearchSession("search-1", "security", "2099-01-01T00:00:00Z")

    batch_b = service.create_batch("search-1", ["b"], search_session=session, candidates=[cand_b])
    service.run_batch(batch_b.batch_id)
    batch_a = service.create_batch("search-1", ["a"], search_session=session, candidates=[cand_a])
    service.run_batch(batch_a.batch_id)
    b_items = {it.candidate_id: it for it in service.store.get_items(batch_b.batch_id)}
    a_items = {it.candidate_id: it for it in service.store.get_items(batch_a.batch_id)}
    assert b_items["b"].status == ITEM_FAILED
    assert a_items["a"].status == ITEM_COMPLETED

    # (1) 重试 B 的 failed 条目不再 409（此时唯一占位者 A 已 completed），后台可重跑成功。
    captured: dict[str, object] = {}
    original_submit = service.submit_batch

    def capture_submit(batch_id, *, candidates=None):
        future = original_submit(batch_id, candidates=candidates)
        captured["future"] = future
        return future

    with monkeypatch.context() as m:
        m.setattr(service, "submit_batch", capture_submit)
        retried = service.retry_item(b_items["b"].item_id, candidates=[cand_b])
    assert retried.status == "queued"
    assert "future" in captured
    captured["future"].result(timeout=5)
    assert service.store.get_item(b_items["b"].item_id).status == ITEM_COMPLETED

    # (2) 新建批次同论文不再 409（B 此时已 completed，A 亦 completed，均不占位）。
    batch_c = service.create_batch("search-1", ["c"], search_session=session, candidates=[cand_c])
    assert batch_c.batch_id not in {batch_a.batch_id, batch_b.batch_id}


def test_reimport_of_existing_paper_reports_existing_and_does_not_duplicate(tmp_path):
    """重新导入已入库论文：批次层不再拒绝，结果由 KB find_existing 表达为
    existing/PAPER_ALREADY_EXISTS，且不重复落盘（spec-021 Task06 §边界最后一条）。"""
    # 用一个"已存在"的注入 port 模拟 KB：find_existing 命中 → 返回 existing。
    papers = {}

    class FakePort:
        def find_existing(self, snapshot):
            title = snapshot.get("title")
            if title in papers:
                return {
                    "paper_id": papers[title],
                    "status": "indexed",
                    "existing": True,
                    "stored_name": f"{title}.pdf",
                }
            return None

        def existing_names(self):
            return set(papers)

        def import_paper(self, request):
            title = request.candidate_snapshot["title"]
            # 只在首次落盘；重复导入必须由 find_existing 拦住，不会走到这里。
            assert title not in papers, "重复导入不得再次落盘"
            papers[title] = "paper-1"
            return {"paper_id": "paper-1", "index_status": "indexed", "stored_name": "p.pdf"}

    def download(candidate, _settings, _hosts, **kwargs):
        path = tmp_path / f"{candidate.candidate_id}.pdf"
        path.write_bytes(b"%PDF-1.7\ncontent")
        return DownloadResult(str(path), path.stat().st_size, "checksum", candidate.pdf_url)

    cand = PaperCandidate(
        "one", "search-1", "Unique Paper", "ccs", "CCS", year=2025,
        doi="10.1000/one", article_url="https://papers.example/a",
        pdf_url="https://papers.example/a.pdf",
    )
    first = import_candidate(
        cand, ArticleSettings(), {"papers.example"}, downloader=download,
        paper_import_port=FakePort(), temp_dir=tmp_path,
    )
    second = import_candidate(
        cand, ArticleSettings(), {"papers.example"}, downloader=download,
        paper_import_port=FakePort(), temp_dir=tmp_path,
    )
    assert first.status == "indexed"
    assert second.existing is True
    assert second.error_code == PAPER_ALREADY_EXISTS
    assert second.paper_id == first.paper_id
    assert len(papers) == 1, "重复导入不得产生第二条记录"
