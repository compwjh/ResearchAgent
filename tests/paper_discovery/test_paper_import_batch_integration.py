"""Isolated batch-to-KB adapter compensation integration contracts."""

from pathlib import Path

import backend.app.api.common as common
from backend.app.knowledge_base.application import create_paper_import_port
from backend.app.paper_discovery.application.paper_import import import_candidate
from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchService
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import PaperImportBatchStore
from backend.app.platform.bootstrap import override_provider
from backend.app.platform.settings.settings_repository import ArticleSettings

PDF = b"%PDF-1.7\nbatch-adapter-compensation-fixture"


def test_batch_uses_real_kb_port_compensator_after_index_failure(tmp_path):
    papers = tmp_path / "papers"
    metadata = tmp_path / "papers.json"
    download_root = tmp_path / "downloads"
    settings = ArticleSettings(article_download_dir=str(download_root))
    index_calls = {"count": 0}

    def indexer(_record, path: Path):
        index_calls["count"] += 1
        if index_calls["count"] == 1:
            raise RuntimeError("isolated index failure")
        assert path.is_file()
        return {"status": "indexed"}

    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=metadata,
        indexer=indexer,
    )

    def downloader(candidate, _settings, _allowed_hosts, *, temp_dir=None, **_kwargs):
        target = Path(temp_dir or download_root) / "batch-download.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(PDF)
        return DownloadResult(str(target), len(PDF), "fixture", candidate.pdf_url or "https://papers.example/paper.pdf")

    candidate = PaperCandidate(
        "batch-candidate", "batch-search", "Batch adapter paper", "usenixsec", "USENIX Security",
        year=2025, pdf_url="https://papers.example/paper.pdf",
    )
    service = PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "batch.sqlite3"),
        importer=lambda candidate, settings, allowed_hosts, **kwargs: import_candidate(
            candidate,
            settings,
            allowed_hosts,
            downloader=downloader,
            paper_import_port=port,
            **kwargs,
        ),
        compensator=port.compensate_import,
        settings=settings,
        allowed_hosts=("papers.example",),
    )
    batch = service.create_batch(
        "batch-search",
        [candidate.candidate_id],
        search_session=SearchSession("batch-search", "security", "2099-01-01T00:00:00Z"),
        candidates=[candidate],
    )

    failed = service.run_batch(batch.batch_id)
    item = service.store.get_items(failed.batch_id)[0]
    assert item.status == "failed"
    assert item.cleanup_status == "cleanup_pending"
    assert item.resource_capability
    assert item.resource_capability["owner"] == item.attempt_owner
    assert item.resource_capability["token"] == item.attempt_token

    # The fail-closed adapter deliberately retains the verified source until
    # an independently reviewed maintenance action removes it.  Simulate that
    # maintenance outcome, then exercise the real adapter compensator.
    (papers / item.resource_capability["stored_name"]).unlink()
    captured = {}
    original_submit = service.submit_batch

    def capture_submit(batch_id, *, candidates=None):
        future = original_submit(batch_id, candidates=candidates)
        captured["future"] = future
        return future

    service.submit_batch = capture_submit
    retried = service.retry_item(item.item_id)
    assert retried.status == "queued"
    assert captured["future"].result(timeout=5) is not None
    assert service.store.get_item(item.item_id).status == "completed"
    assert index_calls["count"] == 2


def test_default_composition_binds_the_same_kb_port_compensator(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    metadata = tmp_path / "papers.json"
    port = create_paper_import_port(papers_dir=papers, meta_path=metadata)
    discovery_store = object()
    monkeypatch.setattr(common, "_paper_store", lambda: discovery_store)
    monkeypatch.setattr(
        common,
        "article_settings",
        ArticleSettings(paper_discovery_db_path=str(tmp_path / "batch.sqlite3")),
    )
    monkeypatch.setattr(common, "paper_import_batch_service", None)
    monkeypatch.setattr(common, "paper_import_batch_store_path", None)

    with override_provider("paper_import_port", port):
        service = common._build_paper_batch_service()

    assert service.compensator.__self__ is port
