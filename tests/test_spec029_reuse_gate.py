"""Spec029 Task02 reuse/evidence gate contracts.

These probes exercise only existing seams with temporary files/SQLite and
in-memory doubles.  They deliberately do not download from the network, run
Qdrant, or create a second import/evidence implementation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.knowledge_base import application as kb_application
from backend.app.knowledge_base.infrastructure.prompts import citation_payloads
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.paper_discovery.application.paper_import import (
    PaperImportResult,
    import_candidate,
)
from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchService
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import PaperImportBatchStore
from backend.app.research.domain import models as research_models
from backend.app.research.infrastructure.research_store import ResearchStore


def _candidate(candidate_id: str, *, title: str | None = None) -> PaperCandidate:
    return PaperCandidate(
        candidate_id=candidate_id,
        search_id="search-029",
        title=title or f"Paper {candidate_id}",
        conference_id="ccs",
        conference_name="CCS",
        year=2025,
        doi=f"10.1000/{candidate_id}",
        article_url=f"https://dl.acm.org/doi/10.1000/{candidate_id}",
        pdf_url=f"https://dl.acm.org/doi/pdf/10.1000/{candidate_id}",
    )


def test_candidate_snapshot_reuses_secure_import_port_and_returns_document_id(tmp_path: Path):
    candidate = _candidate("candidate-a")
    observed: list[tuple[Path, str]] = []

    class Port:
        def find_existing(self, snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, request):
            observed.append((request.trusted_pdf_path, request.candidate_snapshot["candidate_id"]))
            assert request.trusted_pdf_path.is_file()
            return PaperImportResult("document-a", "2025-CCS-Paper-a.pdf", "indexed")

        def compensate_import(self, capability):
            return "completed"

    def downloader(candidate, _settings, _hosts, **_kwargs):
        path = tmp_path / f"{candidate.candidate_id}.pdf"
        path.write_bytes(b"%PDF-1.7\nfixed-contract-sample")
        return DownloadResult(str(path), path.stat().st_size, "sha256", candidate.pdf_url)

    result = import_candidate(
        candidate,
        allowed_hosts={"dl.acm.org"},
        downloader=downloader,
        paper_import_port=Port(),
        temp_dir=tmp_path,
    )

    assert result.status == "indexed"
    assert result.paper_id == "document-a"
    assert observed and observed[0][1] == "candidate-a"


def test_duplicate_candidate_reuses_existing_kb_document_before_download(tmp_path: Path):
    candidate = _candidate("candidate-duplicate")
    download_calls = 0
    imported = False

    class Port:
        def find_existing(self, snapshot):
            if imported:
                return PaperImportResult("document-existing", "existing.pdf", "indexed", existing=True)
            return None

        def existing_names(self):
            return set()

        def import_paper(self, request):
            nonlocal imported
            imported = True
            return PaperImportResult("document-existing", "existing.pdf", "indexed")

        def compensate_import(self, capability):
            return "completed"

    def downloader(candidate, _settings, _hosts, **_kwargs):
        nonlocal download_calls
        download_calls += 1
        path = tmp_path / "candidate.pdf"
        path.write_bytes(b"%PDF-1.7\nduplicate-contract-sample")
        return DownloadResult(str(path), path.stat().st_size, "sha256", candidate.pdf_url)

    port = Port()
    first = import_candidate(candidate, allowed_hosts={"dl.acm.org"}, downloader=downloader, paper_import_port=port, temp_dir=tmp_path)
    second = import_candidate(candidate, allowed_hosts={"dl.acm.org"}, downloader=downloader, paper_import_port=port, temp_dir=tmp_path)

    assert first.paper_id == second.paper_id == "document-existing"
    assert second.existing is True
    assert download_calls == 1


def test_batch_reuse_preserves_partial_failure_and_retries_only_failed_item(tmp_path: Path):
    discovery = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    candidates = [_candidate("a"), _candidate("b")]
    discovery.save_search(SearchSession("search-029", "goal", "2099-01-01T00:00:00Z"), candidates)
    attempts: dict[str, int] = {"a": 0, "b": 0}

    def importer(candidate, *_args, **_kwargs):
        attempts[candidate.candidate_id] += 1
        if candidate.candidate_id == "b" and attempts["b"] == 1:
            return PaperImportResult(None, None, "failed", error_code="KB_IMPORT_FAILED")
        return PaperImportResult(f"document-{candidate.candidate_id}", f"{candidate.candidate_id}.pdf", "indexed")

    service = PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "state.sqlite3"),
        discovery_store=discovery,
        importer=importer,
    )
    batch = service.create_batch("search-029", ["a", "b"], auto_run=False)
    result = service.run_batch(batch.batch_id)
    items = {item.candidate_id: item for item in service.store.get_items(result.batch_id)}
    assert items["a"].status == "completed"
    assert items["b"].status == "failed"

    retried = service.retry_item(items["b"].item_id, candidates=[candidates[1]])
    assert retried.status == "queued"
    service._batch_runners[batch.batch_id].result(timeout=5)
    assert service.store.get_item(items["a"].item_id).status == "completed"
    assert service.store.get_item(items["b"].item_id).status == "completed"
    assert attempts == {"a": 1, "b": 2}


def test_existing_citation_contract_contains_document_chunk_and_page_locator():
    hit = Hit("document-a", "paper.pdf", 3, 4, "full text", 0.8, page_end=4)
    citation = citation_payloads([hit])[0]

    assert citation["document_id"] == "document-a"
    assert citation["chunk_id"]
    assert citation["chunk_index"] == 4
    assert citation["page"] == 3
    assert citation["page_end"] == 4
    assert citation["source_url"].endswith("/api/kb/documents/document-a/source")


def test_document_delete_reuses_kb_boundary_and_removes_source_and_metadata(tmp_path: Path):
    meta_path = tmp_path / "papers.json"
    papers_dir = tmp_path / "papers"
    created = kb_application.create_uploaded_document(
        "paper.pdf",
        "application/pdf",
        b"%PDF-1.7\nfixed-delete-sample",
        meta_path=meta_path,
        papers_dir=papers_dir,
    )
    document_id = created["document"]["document_id"]

    with patch.object(kb_application, "_generation_bound_collection", return_value="papers"), patch.object(
        kb_application, "GenerationBoundIndexPort"
    ) as port:
        port.return_value.delete_document.return_value = None
        deleted = kb_application.delete_document(
            document_id,
            meta_path=meta_path,
            papers_dir=papers_dir,
            manifest_root=tmp_path,
        )

    assert deleted["status"] == "completed"
    assert not list(papers_dir.iterdir())
    assert kb_application.create_source_reader(meta_path=meta_path, papers_dir=papers_dir)
    with pytest.raises(kb_application.DocumentReadError) as error:
        kb_application.read_document_source(document_id, meta_path=meta_path, papers_dir=papers_dir)
    assert error.value.code == "DOCUMENT_NOT_FOUND"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Spec029 bridge is not implemented yet: ResearchDocumentLink/AcquisitionApproval/"
        "EvidenceUpgrade/AcquisitionEvent and their ResearchStore contracts are absent."
    ),
)
def test_research_task_acquisition_and_evidence_upgrade_contract_is_available():
    required_models = (
        "AcquisitionApproval",
        "ResearchDocumentLink",
        "EvidenceUpgrade",
        "AcquisitionEvent",
    )
    assert all(hasattr(research_models, name) for name in required_models)
    required_store_methods = (
        "create_acquisition_approval",
        "list_document_links",
        "save_evidence_upgrade",
        "append_acquisition_event",
    )
    assert all(hasattr(ResearchStore, name) for name in required_store_methods)
