from backend.app.paper_discovery.application.catalog_search_graph import CatalogSearchGraph
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper, SearchJob
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SemanticScholarEnrichment,
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)


class _Store:
    def __init__(self, papers):
        self.papers = list(papers)
        self.provenance = []
        self.records = []
        self.units = []

    def list_catalog_papers(self, conference_ids=None, years=None, *, index_status=None):
        values = self.papers
        if conference_ids:
            values = [paper for paper in values if paper.conference_id in conference_ids]
        if years:
            values = [paper for paper in values if paper.year in years]
        return list(values)

    def upsert_catalog_paper(self, paper, now=None):
        self.papers = [item for item in self.papers if item.catalog_paper_id != paper.catalog_paper_id]
        self.papers.append(paper)
        return True

    def save_field_provenance(self, paper_id, field_name, source_id, **kwargs):
        self.provenance.append((paper_id, field_name, source_id))
        return True

    def ensure_fetch_unit(self, unit, now=None):
        self.units.append(unit)
        return True

    def get_fetch_unit(self, unit_id):
        return next((unit for unit in self.units if unit.fetch_unit_id == unit_id), None)

    def save_fetch_unit(self, unit, now=None):
        self.units = [item for item in self.units if item.fetch_unit_id != unit.fetch_unit_id]
        self.units.append(unit)

    def save_source_record(self, record, now=None):
        self.records.append(record)

    def append_search_event(self, event):
        return None


class _Client:
    def __init__(self, metadata):
        self.metadata = metadata
        self.enrich_calls = 0
        self.recall_calls = 0

    def enrich(self, candidates):
        self.enrich_calls += 1
        return tuple(SemanticScholarEnrichment(item.catalog_paper_id, self.metadata) for item in candidates)

    def search_bulk(self, query, *, limit):
        self.recall_calls += 1
        return SemanticScholarRequestResult(payload={"data": [{
            "paperId": self.metadata.paper_id,
            "title": self.metadata.title,
            "authors": [{"name": name} for name in self.metadata.authors],
            "year": self.metadata.year,
            "abstract": self.metadata.abstract,
            "externalIds": {"DOI": self.metadata.doi, "ArXiv": self.metadata.arxiv_id},
            "venue": self.metadata.venue,
        }]})

    @staticmethod
    def parse_search_results(payload):
        return (_METADATA,)


_METADATA = SemanticScholarMetadata(
    paper_id="s2-id", title="Budget Recycling Differential Privacy",
    authors=("Ada Lovelace",), year=2024, doi="10.1109/SP54263.2024.00212",
    arxiv_id="2403.11445", abstract="A privacy abstract.", venue="IEEE S&P",
)


def _job():
    return SearchJob(
        "search-1", "privacy", ["usenix-security"], [2024], "running",
        "catalog-search-v1", False, None, 0, "2026-01-01T00:00:00Z", None,
        None, "2099-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
    )


def test_metadata_enrichment_only_fills_missing_fields(monkeypatch):
    paper = CatalogPaper(
        "catalog-1", "usenix-security", 2024, _METADATA.title, "budget recycling differential privacy",
        list(_METADATA.authors), None, [], _METADATA.doi, None, "published", None, None, None,
        _METADATA.arxiv_id, "old-hash", "pending", 0, "", "",
    )
    store = _Store([paper])
    client = _Client(_METADATA)
    graph = object.__new__(CatalogSearchGraph)
    graph.store = store
    graph.source_scope = "all"
    graph.semantic_scholar_client = client
    graph.semantic_scholar_enabled_override = True
    graph._event = lambda *args, **kwargs: None

    graph._enrich_catalog_metadata(_job())

    assert store.papers[0].abstract == "A privacy abstract."
    assert store.papers[0].doi == _METADATA.doi
    assert store.provenance == [("catalog-1", "abstract", "semantic_scholar")]
    assert client.enrich_calls == 1


def test_bulk_recall_persists_aggregate_candidate_and_evidence(monkeypatch):
    store = _Store([])
    client = _Client(_METADATA)
    graph = object.__new__(CatalogSearchGraph)
    graph.store = store
    graph.source_scope = "all"
    graph.semantic_scholar_client = client
    graph._event = lambda *args, **kwargs: None
    monkeypatch.setenv("SEMANTIC_SCHOLAR_BULK_RECALL_ENABLED", "true")

    graph._recall_semantic_scholar_candidates(_job())

    assert len(store.papers) == 1
    assert store.records[0].source_kind == "semantic_scholar"
    assert store.units[0].source_kind == "semantic_scholar"
    assert any(field == "abstract" and source == "semantic_scholar" for _, field, source in store.provenance)
    assert client.recall_calls == 1


def test_bulk_recall_reuses_completed_fetch_unit_without_request_or_duplicate_writes(monkeypatch):
    store = _Store([])
    client = _Client(_METADATA)
    graph = object.__new__(CatalogSearchGraph)
    graph.store = store
    graph.source_scope = "all"
    graph.semantic_scholar_client = client
    graph._event = lambda *args, **kwargs: None
    monkeypatch.setenv("SEMANTIC_SCHOLAR_BULK_RECALL_ENABLED", "true")

    graph._recall_semantic_scholar_candidates(_job())
    graph._recall_semantic_scholar_candidates(_job())

    assert client.recall_calls == 1
    assert len(store.papers) == 1
    assert len(store.records) == 1
    assert len(store.units) == 1
    assert store.units[0].status == "completed"
    assert store.units[0].paper_count == 1
