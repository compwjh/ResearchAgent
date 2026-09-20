"""Spec030 Task03 evidence matrix contracts (offline and deterministic)."""

from pathlib import Path
import tempfile

import pytest

from backend.app.research.application.evidence_matrix import EvidenceMatrixError, EvidenceMatrixService
from backend.app.research.domain.models import ResearchDocumentLink, ResearchPaperSelection, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _store() -> ResearchStore:
    store = ResearchStore(Path(tempfile.mkdtemp()) / "research.sqlite3")
    store.create_task(ResearchTask(
        "task-030", "owner", "conversation", "goal", "en", "balanced", False,
        3, 60, "running", 1, "", "",
    ))
    store.replace_selections("task-030", [
        ResearchPaperSelection("task-030", "paper-a", 1.0, "[]", "abstract", ""),
        ResearchPaperSelection("task-030", "paper-b", 0.9, "[]", "abstract", ""),
    ])
    return store


def test_build_matrix_preserves_relations_and_explicit_missing_cells():
    store = _store()
    result = EvidenceMatrixService(store).build_matrix(
        "task-030", "owner",
        dimensions=[{"id": "method", "label": "Method", "definition": "design"}],
        claims=[{"claim_id": "claim-1", "topic": "result", "statement": "A result", "confidence": "high", "status": "contested", "evidence_ids": ["ev-a", "ev-b"]}],
        evidence=[
            {"evidence_id": "ev-a", "claim_id": "claim-1", "paper_id": "paper-a", "evidence_level": "abstract", "stance": "supports", "status": "available", "quote_digest": "", "locator": {"abstract_ref": "catalog:paper-a", "abstract_digest": "a" * 64}},
            {"evidence_id": "ev-b", "claim_id": "claim-1", "paper_id": "paper-b", "evidence_level": "abstract", "stance": "contradicts", "status": "available", "quote_digest": "", "locator": {"abstract_ref": "catalog:paper-b", "abstract_digest": "b" * 64}},
        ],
    )
    cells = {(item["paper_id"], item["relation"]): item for item in result["cells"]}
    assert cells[("paper-a", "supports")]["evidence_ids"] == ["ev-a"]
    assert cells[("paper-b", "contradicts")]["evidence_ids"] == ["ev-b"]
    assert not result["limitations"]


def test_invalid_locator_is_rejected_before_any_claim_is_written():
    store = _store()
    service = EvidenceMatrixService(store)
    with pytest.raises(EvidenceMatrixError) as error:
        service.build_matrix(
            "task-030", "owner", dimensions=[{"id": "d", "label": "D", "definition": "x"}],
            claims=[{"claim_id": "c", "topic": "t", "statement": "s", "confidence": "medium", "status": "supported", "evidence_ids": ["e"]}],
            evidence=[{"evidence_id": "e", "claim_id": "c", "paper_id": "paper-a", "evidence_level": "fulltext", "stance": "supports", "status": "available", "quote_digest": "x", "locator": {"page": 0}}],
        )
    assert error.value.code == "EVIDENCE_LOCATOR_INVALID"
    assert store.list_claims("task-030") == []


def test_unavailable_evidence_downgrades_current_cell_without_deleting_history():
    store = _store()
    service = EvidenceMatrixService(store)
    service.build_matrix(
        "task-030", "owner", dimensions=[{"id": "d", "label": "D", "definition": "x"}],
        claims=[{"claim_id": "c", "topic": "t", "statement": "s", "confidence": "medium", "status": "supported", "evidence_ids": ["e"]}],
        evidence=[{"evidence_id": "e", "claim_id": "c", "paper_id": "paper-a", "evidence_level": "abstract", "stance": "supports", "status": "available", "locator": {"abstract_ref": "catalog:paper-a", "abstract_digest": "a" * 64}}],
    )
    existing = store.get_claim_evidence("e")
    existing.status = "unavailable"
    store.save_claim_evidence(existing)
    current = service.read_matrix("task-030", "owner")
    assert current["cells"][0]["relation"] == "missing"
    assert current["cells"][0]["evidence_ids"] == []
    assert current["evidence"][0]["status"] == "unavailable"
