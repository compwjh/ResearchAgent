"""Task11 durable candidate issue and recovery contracts."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

from backend.app.api import routes_paper
from backend.app.paper_discovery.domain.paper_import_batch import PaperImportBatch
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
