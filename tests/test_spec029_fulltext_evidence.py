"""Task04 full-text evidence contracts (no network, PDF, or Qdrant writes)."""

from pathlib import Path

from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.research.application.evidence_upgrade import EvidenceUpgradeError, EvidenceUpgradeService
from backend.app.research.domain.models import ResearchDocumentLink, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _task(store: ResearchStore) -> None:
    store.create_task(ResearchTask(
        research_task_id="task-029", owner_id="owner", conversation_id="conversation",
        goal="goal", language="en", quality_profile="balanced", review_plan_first=False,
        target_paper_count=2, soft_budget_seconds=60, status="planning", current_plan_version=1,
        created_at="", updated_at="",
    ))
    store.upsert_document_link(ResearchDocumentLink(
        "task-029", "paper-a", "document-a", "item-a", "completed",
    ))


def _manifest(document_id: str = "document-a", text: str = "indexed full text") -> dict:
    return {
        "document_id": document_id,
        "source_sha256": "a" * 64,
        "indexed_source_sha256": "a" * 64,
        "source_hash_state": "verified",
        "status": "complete",
        "index_fingerprint": "b" * 64,
        "chunks": [{"chunk_index": 2, "text": text, "page": 3, "page_end": 4}],
    }


def test_fulltext_upgrade_is_allowlisted_and_persists_locator_provenance(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    calls = []

    def search(question, **kwargs):
        calls.append((question, kwargs))
        return [Hit("document-a", "paper.pdf", 3, 2, "indexed full text", 0.9, page_end=4)]

    service = EvidenceUpgradeService(
        store,
        search=search,
        manifest_reader=lambda document_id, chunker: _manifest(document_id),
        generation_reader=lambda: {"run_id": "generation-1"},
    )
    result = service.upgrade(
        "task-029", claim_id="claim-1", question="what is the result?",
        document_ids=["document-a"],
    )

    assert result.status == "upgraded"
    assert result.to_level == "fulltext"
    assert result.document_id == "document-a"
    assert result.chunk_ids
    assert result.page == 3 and result.page_end == 4
    assert result.source_sha256 == "a" * 64
    assert result.manifest_generation == "generation-1"
    assert result.manifest_fingerprint == "b" * 64
    assert calls[0][1]["document_ids"] == ("document-a",)
    assert store.get_evidence_upgrade("claim-1").to_dict() == result.to_dict()


def test_unapproved_document_and_unlocatable_hit_fail_closed(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    service = EvidenceUpgradeService(
        store,
        search=lambda *_args, **_kwargs: [Hit("document-a", "paper.pdf", 3, 2, "model altered text", 0.9)],
        manifest_reader=lambda *_args: _manifest(),
        generation_reader=lambda: {"run_id": "generation-1"},
    )
    try:
        service.upgrade("task-029", claim_id="claim-2", question="q", document_ids=["not-approved"])
    except EvidenceUpgradeError as error:
        assert error.code == "DOCUMENT_NOT_APPROVED"
    else:
        raise AssertionError("unapproved documents must be rejected")

    result = service.upgrade("task-029", claim_id="claim-2", question="q", document_ids=["document-a"])
    assert result.status == "insufficient"
    assert result.to_level == "abstract"
    assert result.chunk_ids == []


def test_revalidate_marks_rebuilt_or_deleted_evidence_without_editing_report(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    service = EvidenceUpgradeService(
        store,
        search=lambda *_args, **_kwargs: [Hit("document-a", "paper.pdf", 3, 2, "indexed full text", 0.9)],
        manifest_reader=lambda document_id, chunker: _manifest(document_id),
        generation_reader=lambda: {"run_id": "generation-1"},
    )
    service.upgrade("task-029", claim_id="claim-3", question="q", document_ids=["document-a"])

    rebuilt = EvidenceUpgradeService(
        store,
        search=lambda *_args, **_kwargs: [],
        manifest_reader=lambda document_id, chunker: {**_manifest(document_id), "index_fingerprint": "c" * 64},
        generation_reader=lambda: {"run_id": "generation-2"},
    )
    updated = rebuilt.revalidate("task-029")
    assert updated[0].status == "revalidation_required"

    deleted = EvidenceUpgradeService(
        store,
        search=lambda *_args, **_kwargs: [],
        manifest_reader=lambda *_args: (_ for _ in ()).throw(FileNotFoundError()),
        generation_reader=lambda: {"run_id": "generation-2"},
    )
    assert deleted.revalidate("task-029")[0].status == "unavailable"
