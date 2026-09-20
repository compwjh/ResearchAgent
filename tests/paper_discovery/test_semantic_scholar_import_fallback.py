from pathlib import Path

from backend.app.paper_discovery.application.paper_import import import_candidate
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult, PaperDownloadError
from backend.app.paper_discovery.infrastructure.semantic_scholar_adapter import (
    SemanticScholarMatch,
    SemanticScholarResult,
)
from backend.app.platform.ports import ImportIndexStatus
from backend.app.platform.ports import PaperImportResult as PortImportResult
from backend.app.platform.settings.settings_repository import ArticleSettings


def test_import_retries_the_existing_importer_with_semantic_scholar_oa(monkeypatch, tmp_path):
    attempts = []

    def downloader(candidate, _settings, allowed_hosts, **_kwargs):
        attempts.append((candidate, set(allowed_hosts)))
        if len(attempts) == 1:
            raise PaperDownloadError("DOWNLOAD_BLOCKED", "primary unavailable")
        path = Path(tmp_path) / "paper.pdf"
        path.write_bytes(b"%PDF-1.7\ncontent")
        return DownloadResult(str(path), path.stat().st_size, "checksum", candidate["pdf_url"])

    class FakeSemanticScholar:
        def lookup(self, _candidate, *, allowed_hosts):
            assert "arxiv.org" in allowed_hosts
            return SemanticScholarResult(
                match=SemanticScholarMatch(
                    paper_id="s2-paper-id", title="Budget Recycling Differential Privacy",
                    authors=("Ada Lovelace",), year=2024, doi="10.1109/example",
                    arxiv_id="2403.11445", abstract="abstract",
                    source_page_url="https://www.semanticscholar.org/paper/s2-paper-id",
                    pdf_url="https://arxiv.org/pdf/2403.11445", open_access_status="GREEN",
                )
            )

    class Port:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, request):
            return PortImportResult(
                paper_id="paper-1", index_status=ImportIndexStatus.INDEXED,
                error_code=None, stored_name="2024-CCS-Budget-Recycling.pdf",
            )

    monkeypatch.setattr(
        "backend.app.paper_discovery.infrastructure.semantic_scholar_adapter.SemanticScholarFallbackAdapter",
        FakeSemanticScholar,
    )
    candidate = {
        "title": "Budget Recycling Differential Privacy", "authors": ["Ada Lovelace"],
        "year": 2024, "doi": "10.1109/example", "conference_id": "ccs",
        "conference_name": "ACM CCS", "pdf_url": "https://papers.example/paper.pdf",
    }
    result = import_candidate(
        candidate, ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
        downloader=downloader, paper_import_port=Port(), temp_dir=tmp_path,
    )

    assert result.paper_id == "paper-1"
    assert len(attempts) == 2
    assert attempts[1][0]["pdf_url"] == "https://arxiv.org/pdf/2403.11445"
    assert "arxiv.org" in attempts[1][1]
