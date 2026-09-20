"""Spec032 Task10 fixed-sample contracts for approved-plan auto import."""

from __future__ import annotations

from pathlib import Path

from backend.app.paper_discovery.domain.paper_import_batch import PaperImportBatch
from backend.app.research.application.acquisition import (
    ApprovedPlanAutoImporter,
    ResearchAcquisitionService,
)
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.domain.models import ResearchPaperSelection, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _task(store: ResearchStore, task_id: str = "task-032-auto") -> None:
    store.create_task(
        ResearchTask(
            research_task_id=task_id,
            owner_id="owner",
            conversation_id="conversation",
            goal="approved plan goal",
            language="en",
            quality_profile="balanced",
            review_plan_first=True,
            target_paper_count=1,
            soft_budget_seconds=60,
            status="running",
            current_plan_version=1,
            created_at="",
            updated_at="",
        )
    )
    store.replace_selections(
        task_id,
        [
            ResearchPaperSelection(task_id, "paper-good", 1.0, "[]", "catalog", ""),
            ResearchPaperSelection(task_id, "paper-over-budget", 0.9, "[]", "catalog", ""),
        ],
    )


class _Acquisition:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def confirm(self, task_id, **kwargs):
        self.calls.append({"task_id": task_id, **kwargs})
        return {"status": "running", "batch_id": "batch-1", "items": []}


def test_approved_plan_is_bounded_and_idempotent_key_is_stable(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    acquisition = _Acquisition()
    importer = ApprovedPlanAutoImporter(store, acquisition)

    first = importer.run("task-032-auto", approved_plan=True, target_paper_count=1, plan_version=1)
    second = importer.run("task-032-auto", approved_plan=True, target_paper_count=1, plan_version=1)

    assert first["status"] == second["status"] == "running"
    assert len(acquisition.calls) == 2
    assert acquisition.calls[0]["paper_ids"] == ["paper-good"]
    assert acquisition.calls[0]["idempotency_key"] == acquisition.calls[1]["idempotency_key"]


def test_unapproved_plan_does_not_call_batch_or_pdf_path(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    acquisition = _Acquisition()
    result = ApprovedPlanAutoImporter(store, acquisition).run(
        "task-032-auto", approved_plan=False, target_paper_count=1
    )

    assert result["reason"] == "PLAN_NOT_APPROVED"
    assert acquisition.calls == []


def test_identity_mismatch_is_blocked_but_other_candidate_continues(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    # Put the mismatching record first in the selection so this test proves
    # the budget is applied after the frozen candidate order, while a valid
    # peer still remains independently importable when the budget allows it.
    store.replace_selections(
        "task-032-auto",
        [
            ResearchPaperSelection("task-032-auto", "paper-wrong", 1.0, "[]", "catalog", ""),
            ResearchPaperSelection("task-032-auto", "paper-good", 0.9, "[]", "catalog", ""),
        ],
    )
    acquisition = _Acquisition()
    result = ApprovedPlanAutoImporter(store, acquisition).run(
        "task-032-auto",
        approved_plan=True,
        target_paper_count=2,
        candidates=[
            {"candidate_id": "paper-wrong", "title": "Wrong link", "year": 2024, "conference_id": "ndss", "identity_verdict": "mismatch"},
            {"candidate_id": "paper-good", "title": "Good paper", "year": 2024, "conference_id": "ndss"},
        ],
    )

    assert result["status"] == "partial"
    assert result["issues"] == [{"candidate_id": "paper-wrong", "error_code": "IDENTITY_MISMATCH"}]
    assert acquisition.calls[0]["paper_ids"] == ["paper-good"]
    links = {link.catalog_paper_id: link for link in store.list_document_links("task-032-auto")}
    assert links["paper-wrong"].status == "waiting_identity"


def test_queued_batch_status_attempts_existing_recovery_hook(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)

    class _Batch:
        def __init__(self):
            self.recovered = []
            self.submitted = []
            self.store = self

        def get_batch(self, batch_id):
            return PaperImportBatch(batch_id, "search-1", status="queued")

        def maybe_recover_batch(self, batch_id):
            self.recovered.append(batch_id)

        def submit_batch(self, batch_id):
            self.submitted.append(batch_id)

        def get_status(self, batch_id):
            return {"batch": {"batch_id": batch_id, "status": "running"}, "items": []}

    batch = _Batch()
    from backend.app.research.application.acquisition import ResearchAcquisitionService

    service = ResearchAcquisitionService(store, batch)
    # The recovery contract is exercised directly through the existing status
    # projector; no new runner or downloader is introduced here.
    store.set_task_search_id("task-032-auto", "search-1")
    store.replace_selections(
        "task-032-auto", [ResearchPaperSelection("task-032-auto", "paper-good", 1.0, "[]", "catalog", "")]
    )
    batch.create_batch = lambda *args, **kwargs: PaperImportBatch("batch-1", "search-1", status="queued")
    service.confirm("task-032-auto", selection_version=2, paper_ids=["paper-good"], idempotency_key="k")
    assert batch.recovered and set(batch.recovered) == {"batch-1"}
    assert batch.submitted and set(batch.submitted) == {"batch-1"}


def test_orchestrator_approval_gate_excludes_ordinary_search(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "approved-task")
    store.append_event("approved-task", "task", {"status": "running", "reason": "plan_approved"})
    ordinary = ResearchTask(
        research_task_id="ordinary-task", owner_id="owner", conversation_id="conversation",
        goal="ordinary", language="en", quality_profile="balanced", review_plan_first=False,
        target_paper_count=2, soft_budget_seconds=60, status="running", current_plan_version=1,
        created_at="", updated_at="",
    )
    store.create_task(ordinary)
    class _Importer:
        def __init__(self):
            self.calls = []

        def run(self, task_id, **kwargs):
            self.calls.append((task_id, kwargs))
            return {"status": "running"}

    importer = _Importer()
    orchestrator = Orchestrator(store=store, probe=type("Probe", (), {})(), auto_importer=importer)

    assert orchestrator._plan_is_approved(store.get_task("approved-task", "owner"), "owner") is True
    assert orchestrator._plan_is_approved(store.get_task("ordinary-task", "owner"), "owner") is False
    orchestrator._auto_import_approved_selection(
        task=store.get_task("approved-task", "owner"), owner_id="owner", plan_version=1
    )
    orchestrator._auto_import_approved_selection(
        task=store.get_task("ordinary-task", "owner"), owner_id="owner", plan_version=1
    )
    assert [task_id for task_id, _ in importer.calls] == ["approved-task"]


def test_orchestrator_cancellation_overrides_prior_plan_approval(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "cancelled-task")
    store.append_event("cancelled-task", "task", {"status": "running", "reason": "plan_approved"})
    store.cancel_task("cancelled-task", "owner")
    orchestrator = Orchestrator(store=store, probe=type("Probe", (), {})())

    assert orchestrator._plan_is_approved(store.get_task("cancelled-task", "owner"), "owner") is False


def test_confirmation_filters_candidate_snapshots_per_frozen_search_handle(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store, "multi-search-task")
    store.set_task_search_id("multi-search-task", "search-a")
    store.replace_selections(
        "multi-search-task",
        [
            ResearchPaperSelection("multi-search-task", "paper-a", 1.0, "[]", "catalog", "", "search-a"),
            ResearchPaperSelection("multi-search-task", "paper-b", 0.9, "[]", "catalog", "", "search-b"),
        ],
    )

    class _GroupedBatch:
        def __init__(self):
            self.calls = []

        def create_batch(self, search_id, paper_ids, **kwargs):
            self.calls.append((search_id, list(paper_ids), list(kwargs.get("candidates") or [])))
            return PaperImportBatch(f"batch-{search_id}", search_id, status="queued")

        def get_status(self, batch_id):
            return {"batch": {"batch_id": batch_id, "status": "queued"}, "items": []}

    batch = _GroupedBatch()
    result = ResearchAcquisitionService(store, batch).confirm(
        "multi-search-task",
        selection_version=2,
        paper_ids=["paper-a", "paper-b"],
        idempotency_key="multi-search",
        candidates=[
            {"candidate_id": "paper-a", "search_id": "search-a", "title": "A", "year": 2024, "conference_id": "ndss"},
            {"candidate_id": "paper-b", "search_id": "search-b", "title": "B", "year": 2024, "conference_id": "ndss"},
        ],
    )

    assert result["batch_ids"] == ["batch-search-a", "batch-search-b"]
    assert [(search_id, ids, [item["candidate_id"] for item in candidates]) for search_id, ids, candidates in batch.calls] == [
        ("search-a", ["paper-a"], ["paper-a"]),
        ("search-b", ["paper-b"], ["paper-b"]),
    ]
