"""Task11 durable candidate issue and recovery contracts."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

from backend.app.api import routes_paper
from backend.app.paper_discovery.application.paper_import import PaperImportResult
from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchService
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.domain.paper_import_batch import PaperImportBatch
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import PaperImportBatchStore
from backend.app.research.application.acquisition import ResearchAcquisitionService
from backend.app.research.domain.models import (
    AcquisitionApproval,
    ManualResolution,
    ResearchDocumentLink,
    ResearchPaperSelection,
    ResearchTask,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _task(store: ResearchStore, task_id: str) -> None:
    store.create_task(ResearchTask(
        research_task_id=task_id, owner_id="owner", conversation_id="conversation",
        goal="goal", language="en", quality_profile="balanced", review_plan_first=False,
        target_paper_count=2, soft_budget_seconds=60, status="running", current_plan_version=1,
        created_at="", updated_at="",
    ))


class _Batch:
    def __init__(self) -> None:
        self.batch = PaperImportBatch("batch-1", "search-1", status="waiting_login")

    def get_status(self, _batch_id):
        return {
            "batch": self.batch.to_dict(),
            "items": [{
                "item_id": "item-1", "candidate_id": "paper-1", "status": "waiting_login",
                "error_code": "LOGIN_REQUIRED", "paper_id": None,
            }],
        }


def test_issue_is_deduplicated_across_tasks_and_keeps_actions(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-a")
    _task(store, "task-b")
    first = store.record_acquisition_issue(
        candidate_id="paper-1", task_id="task-a", reason_code="LOGIN_REQUIRED",
        actions=["login", "resume", "upload"],
        attempt={"status": "waiting_login", "import_item_id": "item-1"},
        import_item_id="item-1", batch_id="batch-1",
    )
    second = store.record_acquisition_issue(
        candidate_id="paper-1", task_id="task-b", reason_code="LOGIN_REQUIRED",
        actions=["login", "resume", "upload"],
        attempt={"status": "waiting_login", "import_item_id": "item-2"},
        import_item_id="item-2", batch_id="batch-2",
    )
    assert first.issue_id == second.issue_id
    issue = store.get_acquisition_issue_for_candidate("paper-1")
    assert issue is not None
    assert issue.task_ids == ["task-a", "task-b"]
    assert {item["import_item_id"] for item in issue.attempts} == {"item-1", "item-2"}
    assert issue.actions == ["login", "resume", "upload"]
    assert [item.issue_id for item in store.list_acquisition_issues(task_id="task-b")] == [issue.issue_id]


def test_research_sync_projects_waiting_login_as_actionable_issue(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-issue")
    store.set_task_search_id("task-issue", "search-1")
    store.replace_selections("task-issue", [ResearchPaperSelection("task-issue", "paper-1", 1.0, "[]", "catalog", "")])
    store.create_acquisition_approval(
        AcquisitionApproval("task-issue", 1, ["paper-1"], "confirmed", "request-1", "batch-1")
    )
    result = ResearchAcquisitionService(store, _Batch()).status("task-issue")
    assert result["issues"][0]["reason_code"] == "LOGIN_REQUIRED"
    assert result["issues"][0]["actions"] == ["login", "resume", "upload"]
    link = store.list_document_links("task-issue")[0]
    assert link.status == "waiting_login"


def test_restarted_research_acquisition_projects_issue_without_refreshing_search(tmp_path: Path):
    research = ResearchStore(tmp_path / "research.sqlite3")
    _task(research, "task-restarted")
    research.set_task_search_id("task-restarted", "search-1")
    research.replace_selections(
        "task-restarted",
        [ResearchPaperSelection("task-restarted", "paper-restarted", 1.0, "[]", "catalog", "", "search-1")],
    )
    batch_store = PaperImportBatchStore(tmp_path / "imports.sqlite3")
    batch = batch_store.create_batch("search-1", ["paper-restarted"])
    item = batch_store.get_items(batch.batch_id)[0]
    batch_store.claim_item(item.item_id, "worker")
    batch_store.transition_item(
        item.item_id,
        "waiting_login",
        expected_state="downloading",
        lease_owner="worker",
        error_code="LOGIN_REQUIRED",
    )
    research.create_acquisition_approval(
        AcquisitionApproval("task-restarted", 1, ["paper-restarted"], "confirmed", "restart-request", batch.batch_id)
    )

    refreshed = []

    def must_not_refresh(*_args):
        refreshed.append(True)
        raise AssertionError("research recovery must not re-run paper search")

    restarted = ResearchAcquisitionService(
        research,
        PaperImportBatchService(batch_store),
        search_refresher=must_not_refresh,
    )
    result = restarted.status("task-restarted")

    assert refreshed == []
    assert result["items"][0]["status"] == "waiting_login"
    assert result["issues"][0]["candidate_id"] == "paper-restarted"
    assert result["issues"][0]["task_ids"] == ["task-restarted"]
    assert result["issues"][0]["actions"] == ["login", "resume", "upload"]


def test_manual_upload_resolution_closes_issue_without_rewriting_report(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-upload")
    issue = store.record_acquisition_issue(
        candidate_id="paper-1", task_id="task-upload", reason_code="IMPORT_FAILED", actions=["retry", "upload"]
    )
    resolution = store.add_manual_resolution(ManualResolution(
        issue_id=issue.issue_id, method="upload", user_document_id="document-1",
        identity_verdict="confirmed", confirmed_at="2026-09-20T00:00:00Z",
        evidence={"basis": "user confirmed title"},
    ))
    assert resolution.issue_id == issue.issue_id
    store.upsert_document_link(ResearchDocumentLink(
        "task-upload", "paper-1", "document-1", "item-1", "completed"
    ))
    resolved = store.resolve_acquisition_issue(issue.issue_id, {
        "method": "upload", "user_document_id": "document-1", "identity_verdict": "confirmed"
    })
    assert resolved.status == "resolved"
    assert resolved.resolved_at
    assert store.list_manual_resolutions(issue.issue_id)[0].user_document_id == "document-1"
    assert store.list_document_links("task-upload")[0].document_id == "document-1"


def test_upload_projects_canonical_indexing_status_to_document_link(tmp_path: Path, monkeypatch):
    from backend.app.api import routes_kb

    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-upload-route")
    issue = store.record_acquisition_issue(
        candidate_id="paper-upload-route", task_id="task-upload-route",
        reason_code="IMPORT_FAILED", actions=["upload"],
        import_item_id="item-upload-route", batch_id="batch-upload-route",
    )

    async def fake_upload(_request, _file):
        return {
            "document_id": "document-upload-route",
            "status": "indexing",
            "file_name": "paper.pdf",
            "source_sha256": "a" * 64,
        }

    monkeypatch.setattr(routes_paper, "_research_issue_store", lambda: store)
    monkeypatch.setattr(routes_kb, "upload_document", fake_upload)

    result = asyncio.run(routes_paper.upload_paper_acquisition_issue(
        issue.issue_id, SimpleNamespace(), object(),
        identity_verdict="confirmed", identity_confirmed=True,
    ))

    assert result["report_action"] == "generate_new_version"
    link = store.list_document_links("task-upload-route")[0]
    assert link.status == "indexing"


def test_issue_actions_follow_latest_item_state(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-state")
    issue = store.record_acquisition_issue(
        candidate_id="paper-state", task_id="task-state", reason_code="LOGIN_REQUIRED",
        actions=["login", "resume", "upload"],
        attempt={"status": "waiting_login", "import_item_id": "item-state"},
        import_item_id="item-state", batch_id="batch-state",
    )
    failed = store.record_acquisition_issue(
        candidate_id="paper-state", task_id="task-state", reason_code="IMPORT_FAILED",
        actions=["retry", "upload"],
        attempt={"status": "failed", "import_item_id": "item-state", "error_code": "DOWNLOAD_TIMEOUT"},
        import_item_id="item-state", batch_id="batch-state",
    )
    assert failed.issue_id == issue.issue_id
    assert failed.actions == ["retry", "upload"]
    assert failed.attempts[0]["status"] == "waiting_login"
    assert failed.attempts[-1]["status"] == "failed"


def test_resume_resolution_keeps_resume_method(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-resume")
    issue = store.record_acquisition_issue(
        candidate_id="paper-resume", task_id="task-resume", reason_code="LOGIN_REQUIRED",
        actions=["login", "resume", "upload"],
    )
    resolution = store.add_manual_resolution(ManualResolution(
        issue_id=issue.issue_id, method="resume", identity_verdict="uncertain",
        confirmed_at="2026-09-20T00:00:00Z", evidence={"action": "resume"},
    ))
    assert resolution.method == "resume"


def test_issue_routes_reuse_action_semantics_and_reject_waiting_login_retry(tmp_path: Path, monkeypatch):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-route")
    waiting = store.record_acquisition_issue(
        candidate_id="paper-route-wait", task_id="task-route", reason_code="LOGIN_REQUIRED",
        actions=["login", "resume", "upload"], import_item_id="item-wait", batch_id="batch-wait",
    )
    failed = store.record_acquisition_issue(
        candidate_id="paper-route-fail", task_id="task-route", reason_code="IMPORT_FAILED",
        actions=["retry", "upload"], import_item_id="item-fail", batch_id="batch-fail",
    )
    monkeypatch.setattr(routes_paper, "_research_issue_store", lambda: store)
    monkeypatch.setattr(routes_paper, "_refresh_issue_links", lambda _issue: None)
    monkeypatch.setattr(routes_paper, "login_paper_import_item", lambda item_id: {"status": "opened", "item_id": item_id})
    monkeypatch.setattr(routes_paper, "resume_paper_import_item", lambda item_id: {"status": "completed", "item_id": item_id})
    monkeypatch.setattr(routes_paper, "retry_paper_import_item", lambda item_id: {"status": "queued", "item_id": item_id})

    rejected = routes_paper.retry_paper_acquisition_issue(waiting.issue_id)
    assert rejected.status_code == 400
    assert rejected.body and b"ISSUE_ACTION_NOT_ALLOWED" in rejected.body

    resumed = routes_paper.resume_paper_acquisition_issue(waiting.issue_id)
    assert resumed["result"]["status"] == "completed"
    assert store.list_manual_resolutions(waiting.issue_id)[0].method == "resume"

    retried = routes_paper.retry_paper_acquisition_issue(failed.issue_id)
    assert retried["result"]["status"] == "queued"
    assert store.list_manual_resolutions(failed.issue_id)[0].method == "retry"


def test_resolved_issue_cannot_be_uploaded_again(tmp_path: Path, monkeypatch):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "task-upload-guard")
    issue = store.record_acquisition_issue(
        candidate_id="paper-upload-guard", task_id="task-upload-guard", reason_code="IMPORT_FAILED",
        actions=["retry", "upload"], import_item_id="item-upload-guard", batch_id="batch-upload-guard",
    )
    store.resolve_acquisition_issue(issue.issue_id, {"method": "upload", "identity_verdict": "confirmed"})
    monkeypatch.setattr(routes_paper, "_research_issue_store", lambda: store)
    response = asyncio.run(routes_paper.upload_paper_acquisition_issue(issue.issue_id, SimpleNamespace(), None))
    assert response.status_code == 400
    assert response.body and b"ISSUE_ACTION_NOT_ALLOWED" in response.body


def test_approved_plan_failed_item_is_visible_in_papers_issue_api(tmp_path: Path, monkeypatch):
    """The automatic Research path records a failed item before issue listing."""
    from backend.app.research.application.acquisition import ApprovedPlanAutoImporter

    research = ResearchStore(tmp_path / "research.sqlite3")
    _task(research, "task-auto-issue")
    research.set_task_search_id("task-auto-issue", "search-auto-issue")
    research.replace_selections(
        "task-auto-issue",
        [ResearchPaperSelection("task-auto-issue", "paper-failed", 1.0, "[]", "catalog", "", "search-auto-issue")],
    )
    candidate = PaperCandidate(
        "paper-failed", "search-auto-issue", "A failed paper", "ccs", "CCS",
        year=2025, doi="10.1000/paper-failed", pdf_url="https://example.test/paper.pdf",
    )
    discovery = PaperDiscoveryStore(tmp_path / "discovery.sqlite3")
    discovery.save_search(SearchSession("search-auto-issue", "goal", "2099-01-01T00:00:00Z"), [candidate])

    started = threading.Event()
    release = threading.Event()

    def importer(*_args, **_kwargs):
        started.set()
        assert release.wait(timeout=5)
        return PaperImportResult(None, None, "failed", error_code="DOWNLOAD_TIMEOUT")

    batch = PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "batch.sqlite3"),
        discovery_store=discovery,
        importer=importer,
    )
    submitted = {}
    submit_batch = batch.submit_batch

    def capture_submit(batch_id, *, candidates=None):
        future = submit_batch(batch_id, candidates=candidates)
        submitted[batch_id] = future
        return future

    monkeypatch.setattr(batch, "submit_batch", capture_submit)
    acquisition = ResearchAcquisitionService(research, batch)
    result = ApprovedPlanAutoImporter(research, acquisition).run(
        "task-auto-issue", approved_plan=True, target_paper_count=1,
    )
    batch_id = result["batch_id"]
    assert started.wait(timeout=5)

    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: True)
    monkeypatch.setattr(routes_paper, "_research_issue_store", lambda: research)
    pending = routes_paper.list_paper_acquisition_issues(
        task_id="task-auto-issue", status="open", reason_code=None, limit=100,
    )
    assert pending["count"] == 0

    release.set()
    submitted[batch_id].result(timeout=5)

    response = routes_paper.list_paper_acquisition_issues(
        task_id="task-auto-issue", status="open", reason_code=None, limit=100,
    )
    assert response["count"] == 1
    issue = response["issues"][0]
    assert issue["candidate_id"] == "paper-failed"
    assert issue["task_ids"] == ["task-auto-issue"]
    assert issue["reason_code"] == "DOWNLOAD_TIMEOUT"
    assert issue["batch_id"] == batch_id
