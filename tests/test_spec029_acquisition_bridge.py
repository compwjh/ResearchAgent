from pathlib import Path

from backend.app.paper_discovery.domain.paper_import_batch import PaperImportBatch, PaperImportItem
from backend.app.research.application.acquisition import ResearchAcquisitionService
from backend.app.research.domain.models import (
    AcquisitionApproval,
    AcquisitionEvent,
    ResearchDocumentLink,
    ResearchPaperSelection,
    ResearchTask,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _task(store: ResearchStore, task_id: str = "task-029") -> None:
    store.create_task(ResearchTask(
        research_task_id=task_id, owner_id="owner", conversation_id="conversation",
        goal="goal", language="en", quality_profile="balanced", review_plan_first=False,
        target_paper_count=2, soft_budget_seconds=60, status="planning", current_plan_version=1,
        created_at="", updated_at="",
    ))


def test_acquisition_contract_persists_idempotent_approval_links_and_events(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.replace_selections("task-029", [
        ResearchPaperSelection("task-029", "paper-a", 1.0, "[]", "catalog", ""),
        ResearchPaperSelection("task-029", "paper-b", 0.9, "[]", "catalog", ""),
    ])
    approval = store.create_acquisition_approval(
        AcquisitionApproval("task-029", 1, ["paper-a", "paper-b"], "confirmed", "request-1")
    )
    replay = store.create_acquisition_approval(
        AcquisitionApproval("task-029", 1, ["paper-a", "paper-b"], "confirmed", "request-1")
    )
    assert replay.to_dict()["selection_version"] == 1
    assert replay.to_dict()["paper_ids"] == approval.to_dict()["paper_ids"]

    store.upsert_document_link(ResearchDocumentLink("task-029", "paper-a", "document-a", "item-a", "completed"))
    event = store.append_acquisition_event(AcquisitionEvent("paper-a", "import", "completed", task_id="task-029", batch_id="batch"))
    assert event.status == "completed"
    assert len(store.list_document_links("task-029")) == 1
    assert len(store.list_acquisition_events("task-029")) == 1


class _BatchStore:
    def __init__(self):
        self.batch = PaperImportBatch("batch-1", "search-1", status="queued")
        self.items = [
            PaperImportItem("item-a", "batch-1", "paper-a", status="completed", paper_id="document-a"),
            PaperImportItem("item-b", "batch-1", "paper-b", status="failed", error_code="DOWNLOAD_TIMEOUT"),
        ]

    def get_status(self, batch_id):
        return {"batch": self.batch.to_dict(), "items": [item.to_dict() for item in self.items]}

    def create_batch(self, *_args, **_kwargs):
        return self.batch


def test_confirmation_projects_partial_and_retryable_item_state(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-029", "search-1")
    store.replace_selections("task-029", [
        ResearchPaperSelection("task-029", "paper-a", 1.0, "[]", "catalog", ""),
        ResearchPaperSelection("task-029", "paper-b", 0.9, "[]", "catalog", ""),
    ])
    batch = _BatchStore()
    service = ResearchAcquisitionService(store, batch)
    result = service.confirm(
        "task-029", selection_version=1, paper_ids=["paper-a", "paper-b"],
        idempotency_key="request-1", search_id="search-1",
    )
    assert result["batch_id"] == "batch-1"
    links = {item["catalog_paper_id"]: item for item in result["links"]}
    assert links["paper-a"]["document_id"] == "document-a"
    assert links["paper-b"]["status"] == "failed"
    assert links["paper-b"]["error_code"] == "DOWNLOAD_TIMEOUT"
    assert {event["status"] for event in result["events"]} == {"completed", "failed"}


def test_confirmation_rejects_client_search_handle_mismatch(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-029", "server-search-1")
    store.replace_selections("task-029", [
        ResearchPaperSelection("task-029", "paper-a", 1.0, "[]", "catalog", ""),
    ])

    class _NoCallBatch:
        def create_batch(self, *_args, **_kwargs):
            raise AssertionError("mismatched client search handle must not create a batch")

    service = ResearchAcquisitionService(store, _NoCallBatch())
    try:
        service.confirm(
            "task-029", selection_version=1, paper_ids=["paper-a"],
            idempotency_key="request-1", search_id="client-forged-search",
        )
    except Exception as error:
        assert getattr(error, "code", None) == "ACQUISITION_CONFLICT"
    else:
        raise AssertionError("client search handle mismatch should be rejected")


def test_confirmation_rejects_stale_selection_version(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.replace_selections("task-029", [ResearchPaperSelection("task-029", "paper-a", 1.0, "[]", "catalog", "")])
    store.replace_selections("task-029", [ResearchPaperSelection("task-029", "paper-b", 1.0, "[]", "catalog", "")])
    service = ResearchAcquisitionService(store, _BatchStore())
    try:
        service.confirm("task-029", selection_version=1, paper_ids=["paper-a"], idempotency_key="request-1", search_id="search-1")
    except Exception as error:
        assert getattr(error, "code", None) == "SELECTION_VERSION_STALE"
    else:
        raise AssertionError("stale selection version should be rejected")
