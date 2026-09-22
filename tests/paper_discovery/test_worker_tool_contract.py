import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.paper_discovery.application.catalog_runtime import CatalogSourceRuntime
from backend.app.paper_discovery.application.worker_tool import (
    PAPER_DISCOVERY_TOOL_NAME,
    PaperDiscoveryToolFacade,
    WorkerToolResult,
)
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry


@pytest.mark.parametrize(
    "operation,status",
    [("discover", "running"), ("import", "cached")],
)
def test_worker_tool_result_rejects_statuses_outside_operation_contract(operation, status):
    with pytest.raises(ValueError, match="unsupported worker result status"):
        WorkerToolResult(
            tool=PAPER_DISCOVERY_TOOL_NAME,
            operation=operation,
            source_id="usenix",
            status=status,
            provenance={},
        )


def test_worker_import_uses_server_catalog_snapshot_instead_of_caller_candidate():
    catalog_paper = SimpleNamespace(
        catalog_paper_id="paper-1",
        conference_id="ndss",
        year=2024,
        title="Trusted catalog title",
        authors=["Trusted Author"],
        abstract="Trusted abstract",
        keywords=["security"],
        doi="10.1000/trusted",
        dblp_key=None,
        publication_stage="published",
        official_page_url="https://www.ndss-symposium.org/paper/1",
        official_pdf_url="https://www.ndss-symposium.org/paper/1.pdf",
        prepublication_pdf_url=None,
        arxiv_id=None,
    )

    class Store:
        def get_catalog_paper(self, candidate_id):
            return catalog_paper if candidate_id == "paper-1" else None

        def get_catalog_source_kinds(self, candidate_id):
            return ["ndss"] if candidate_id == "paper-1" else []

    facade = PaperDiscoveryToolFacade(store=Store(), registry=SourceRegistry(store=Store()))
    caller_candidate = {
        "candidate_id": "paper-1",
        "source_id": "ndss",
        "title": "Forged title",
        "year": 2099,
        "doi": "10.9999/attacker",
        "pdf_url": "https://attacker.example/evil.pdf",
        "article_url": "https://attacker.example/landing",
        "source_links": [{"url": "https://attacker.example/evil.pdf"}],
    }
    imported_candidates = []

    class ImportResult:
        paper_id = "document-1"
        error_code = None

    def import_trusted(candidate, **kwargs):
        imported_candidates.append((candidate, kwargs))
        return ImportResult()

    with patch("backend.app.paper_discovery.application.paper_import.import_candidate", side_effect=import_trusted), \
         patch("backend.app.api.common._paper_candidate_hosts", return_value={"www.ndss-symposium.org"}), \
         patch("backend.app.platform.settings.settings_repository.load_article_settings", return_value=object()):
        result = facade.import_candidate("ndss", caller_candidate)

    assert result.status == "completed"
    assert result.candidate_id == "paper-1"
    trusted_candidate, kwargs = imported_candidates[0]
    assert trusted_candidate["title"] == "Trusted catalog title"
    assert trusted_candidate["year"] == 2024
    assert trusted_candidate["doi"] == "10.1000/trusted"
    assert trusted_candidate["pdf_url"] == "https://www.ndss-symposium.org/paper/1.pdf"
    assert trusted_candidate["candidate_id"] == "paper-1"
    assert "attacker.example" not in str(trusted_candidate)
    assert kwargs["allowed_hosts"] == {"www.ndss-symposium.org"}


@pytest.mark.parametrize(
    "source_id,candidate,expected_error",
    [
        ("ndss", {"candidate_id": "missing"}, "CANDIDATE_NOT_FOUND"),
        ("ndss", {"candidate_id": "paper-1", "source_id": "ccs"}, "SOURCE_MISMATCH"),
    ],
)
def test_worker_import_rejects_unknown_or_mismatched_server_candidate(source_id, candidate, expected_error):
    catalog_paper = SimpleNamespace(
        catalog_paper_id="paper-1", conference_id="ndss", year=2024, title="Trusted title",
        authors=[], abstract=None, keywords=[], doi=None, dblp_key=None,
        publication_stage="published", official_page_url=None, official_pdf_url=None,
        prepublication_pdf_url=None, arxiv_id=None,
    )

    class Store:
        def get_catalog_paper(self, candidate_id):
            return catalog_paper if candidate_id == "paper-1" else None

        def get_catalog_source_kinds(self, candidate_id):
            return ["ndss"] if candidate_id == "paper-1" else []

    store = Store()
    facade = PaperDiscoveryToolFacade(store=store, registry=SourceRegistry(store=store))
    with patch("backend.app.paper_discovery.application.paper_import.import_candidate", side_effect=AssertionError("must not import")):
        result = facade.import_candidate(source_id, candidate)

    assert result.status == "failed"
    assert result.error_code == expected_error


def test_usenix_worker_discover_candidate_can_be_imported_from_server_catalog(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "worker-discover-import.sqlite3")
    registry = SourceRegistry(store=store)

    class UsenixSearchAdapter:
        def search(self, conference, query, years, limit):
            assert conference.conference_id == "usenix-security"
            assert query == "secure systems"
            assert years == [2024]
            return SimpleNamespace(records=[{
                "info": {
                    "title": "Discoverable catalog paper",
                    "authors": ["Trusted Author"],
                    "year": 2024,
                    "url": "https://www.usenix.org/conference/example/presentation/paper",
                    "pdf_url": "https://www.usenix.org/system/files/sec24-paper.pdf",
                    "publication_stage": "published",
                },
            }], error_code=None)

    adapter = UsenixSearchAdapter()
    facade = PaperDiscoveryToolFacade(store=store, registry=registry)
    imported_candidates = []

    class ImportResult:
        paper_id = "document-1"
        error_code = None

    def import_trusted(candidate, **kwargs):
        imported_candidates.append((candidate, kwargs))
        return ImportResult()

    with patch.object(registry, "adapter", return_value=adapter), \
         patch("backend.app.paper_discovery.application.paper_import.import_candidate", side_effect=import_trusted), \
         patch("backend.app.api.common._paper_candidate_hosts", return_value={"www.usenix.org"}), \
         patch("backend.app.platform.settings.settings_repository.load_article_settings", return_value=object()):
        discovery = facade.discover("usenix", {"query": "secure systems", "years": [2024]})
        candidate = discovery.payload["candidates"][0]
        imported = facade.import_candidate("usenix", {"candidate_id": candidate["candidate_id"]})

    catalog_paper = store.get_catalog_paper(candidate["candidate_id"])
    assert catalog_paper is not None
    assert catalog_paper.title == "Discoverable catalog paper"
    assert imported.status == "completed"
    assert imported_candidates[0][0]["candidate_id"] == catalog_paper.catalog_paper_id
    assert imported_candidates[0][0]["title"] == catalog_paper.title


def test_legacy_discover_does_not_mark_fetch_unit_completed_after_partial_write(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "worker-partial-persist.sqlite3")
    registry = SourceRegistry(store=store)

    class UsenixSearchAdapter:
        def search(self, conference, query, years, limit):
            return SimpleNamespace(records=[
                {"info": {"title": f"Paper {index}", "authors": [], "year": 2024,
                          "url": f"https://www.usenix.org/paper/{index}"}}
                for index in (1, 2)
            ], error_code=None)

    original_persist = CatalogSourceRuntime._persist_record
    calls = 0

    def fail_on_second(self, source_id, unit, record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated source record write failure")
        return original_persist(self, source_id, unit, record)

    facade = PaperDiscoveryToolFacade(store=store, registry=registry)
    with patch.object(registry, "adapter", return_value=UsenixSearchAdapter()), \
         patch.object(CatalogSourceRuntime, "_persist_record", new=fail_on_second):
        result = facade.discover("usenix", {"query": "systems", "years": [2024]})

    unit_id = f"usenix|worker-query|2024|{hashlib.sha256(b'systems').hexdigest()[:16]}"
    unit = store.get_fetch_unit(unit_id)
    assert result.status == "failed"
    assert unit is not None
    assert unit.status == "partial"
    assert unit.paper_count == 1
