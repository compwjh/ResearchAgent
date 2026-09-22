from __future__ import annotations

import sqlite3

from backend.app.paper_discovery.application.catalog_search_graph import CatalogSearchGraph
from backend.app.paper_discovery.domain.paper_discovery import SearchJob
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)

_METADATA = SemanticScholarMetadata(
    paper_id="s2-persistence-id",
    title="Persistent Differential Privacy",
    authors=("Ada Lovelace",),
    year=2024,
    doi="10.1109/SP54263.2024.00212",
    arxiv_id="2403.11445",
    abstract="A persisted privacy abstract.",
    venue="IEEE S&P",
)


class _BulkClient:
    def __init__(self) -> None:
        self.calls = 0
        self.metadata = _METADATA

    def search_bulk(self, query: str, *, limit: int) -> SemanticScholarRequestResult:
        self.calls += 1
        item = self.metadata
        return SemanticScholarRequestResult(payload={
            "data": [{
                "paperId": item.paper_id,
                "title": item.title,
                "authors": [{"name": author} for author in item.authors],
                "year": item.year,
                "abstract": item.abstract,
                "externalIds": {"DOI": item.doi, "ArXiv": item.arxiv_id},
                "venue": item.venue,
            }],
        })

    @staticmethod
    def parse_search_results(payload):
        return (_METADATA,)


def _job() -> SearchJob:
    return SearchJob(
        "search-persistence",
        "privacy",
        ["usenix-security"],
        [2024],
        "running",
        "catalog-search-v1",
        False,
        None,
        0,
        "2026-01-01T00:00:00Z",
        None,
        None,
        "2099-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    )


def _graph(store: PaperDiscoveryStore, client: _BulkClient) -> CatalogSearchGraph:
    graph = object.__new__(CatalogSearchGraph)
    graph.store = store
    graph.source_scope = "all"
    graph.semantic_scholar_client = client
    graph._event = lambda *args, **kwargs: None
    return graph


def test_bulk_recall_persists_and_reuses_sqlite_state_after_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_BULK_RECALL_ENABLED", "true")
    database_path = tmp_path / "paper-search.sqlite3"
    client = _BulkClient()

    first_store = PaperDiscoveryStore(database_path)
    _graph(first_store, client)._recall_semantic_scholar_candidates(_job())

    with first_store._connect() as connection:
        unit_id = connection.execute(
            "SELECT fetch_unit_id FROM source_fetch_units WHERE source_kind=?",
            ("semantic_scholar",),
        ).fetchone()[0]
    unit = first_store.get_fetch_unit(unit_id)
    assert unit is not None
    assert unit.source_kind == "semantic_scholar"
    assert unit.status == "completed"
    assert unit.paper_count == 1

    papers = first_store.list_catalog_papers(["usenix-security"], [2024], index_status=None)
    assert len(papers) == 1
    paper_id = papers[0].catalog_paper_id
    assert first_store.get_catalog_source_kinds(paper_id) == ["semantic_scholar"]
    provenance = first_store.get_field_provenance(paper_id)
    assert provenance["abstract"]["source_id"] == "semantic_scholar"
    assert provenance["abstract"]["source_record_id"].startswith("semantic_scholar|")

    # A fresh store instance represents a process restart.  The completed unit
    # is durable, so the same query must not call Academic Graph again.
    restarted_store = PaperDiscoveryStore(database_path)
    _graph(restarted_store, client)._recall_semantic_scholar_candidates(_job())

    assert client.calls == 1
    assert len(restarted_store.list_catalog_papers(["usenix-security"], [2024], index_status=None)) == 1
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog_source_records WHERE source_kind=?",
            ("semantic_scholar",),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM field_provenance WHERE source_id=?",
            ("semantic_scholar",),
        ).fetchone()[0] >= 1
