from dataclasses import dataclass
from types import SimpleNamespace

from backend.app.literature_maps.application.catalog_adapter import CatalogRow, CatalogSourceAdapter
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SEMANTIC_SCHOLAR_METADATA_FIELDS,
    SemanticScholarEnrichment,
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)


@dataclass
class FakePaper:
    paper_id: str
    title: str
    abstract: str = ""
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors: tuple[str, ...] = ()
    venue: str | None = None
    citation_count: int | None = None
    source_url: str | None = None


class FakeClient:
    def __init__(self):
        self.calls = []

    def search_bulk(self, query, *, limit=20, year=None):
        self.calls.append(("search", query, limit, year))
        return SemanticScholarRequestResult(
            payload={
                "data": [
                    {"paperId": f"s2-{index}", "title": "Fuzzing vulnerability discovery", "abstract": "fuzzing", "year": 2024}
                    for index in range(60)
                ]
            }
        )

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0):
        self.calls.append(("graph", paper_id, relation, limit, offset))
        return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_RATE_LIMITED", retryable=True)


class RelevanceClient(FakeClient):
    def search_relevance(self, query, *, limit=20, fields=None):
        self.calls.append(("relevance", query, limit, fields))
        rows = [
            {"paperId": "z-provider-first", "title": "Graph attention networks core", "abstract": "graph attention networks", "year": 2024},
            {"paperId": "a-provider-second", "title": "Graph attention networks survey", "abstract": "graph attention networks", "year": 2023},
            {"paperId": "b-provider-third", "title": "Graph attention networks applications", "abstract": "graph attention networks", "year": 2022},
        ]
        return SemanticScholarRequestResult(payload={"data": rows})


class OfficialCatalog:
    def __init__(self):
        self.calls = []

    def search(self, *, query, source_ids, conference_ids, year_start=None, year_end=None, limit=30):
        self.calls.append({"query": query, "source_ids": tuple(source_ids), "conference_ids": tuple(conference_ids), "limit": limit})
        return [CatalogRow(
            metadata=SemanticScholarMetadata(
                paper_id="official-s2-1",
                title="Fuzzing vulnerability discovery",
                abstract="official conference metadata",
                year=2024,
                venue="USENIX Security",
            ),
            source_id="usenix",
            conference_id="usenix-security",
            catalog_paper_id="catalog-usenix-legacy",
        )]


class RichOfficialCatalog:
    def search(self, *, query, source_ids, conference_ids, year_start=None, year_end=None, limit=30):
        return [CatalogRow(
            metadata=SemanticScholarMetadata(
                paper_id="official-s2-1",
                title="Fuzzing vulnerability discovery",
                abstract="official conference metadata",
                year=2024,
                venue="USENIX Security",
                doi="10.5555/official",
                arxiv_id="2401.00001",
            ),
            source_id="usenix",
            conference_id="usenix-security",
            source_kind="usenix",
            catalog_paper_id="catalog-usenix-1",
            official_page_url="https://www.usenix.org/conference/paper-1",
            official_pdf_url="https://www.usenix.org/system/files/paper-1.pdf",
            prepublication_pdf_url="https://www.usenix.org/preprint/paper-1.pdf",
            doi="10.5555/official",
            arxiv_id="2401.00001",
            snapshot={
                "catalog_paper_id": "catalog-usenix-1",
                "official_page_url": "https://www.usenix.org/conference/paper-1",
                "official_pdf_url": "https://www.usenix.org/system/files/paper-1.pdf",
                "authorization": "must-not-leak",
            },
        )]


class SparseOfficialCatalog:
    def search(self, *, query, source_ids, conference_ids, year_start=None, year_end=None, limit=30):
        return [CatalogRow(
            metadata=SemanticScholarMetadata(
                paper_id="catalog-s2-1",
                title="A catalog-only paper",
                abstract="official scope row",
                year=2024,
            ),
            source_id="usenix",
            conference_id="usenix-security",
            catalog_paper_id="catalog-only-1",
        )]


class MultiOfficialCatalog:
    def search(self, *, query, source_ids, conference_ids, year_start=None, year_end=None, limit=30):
        rows = []
        if "usenix" in source_ids and "usenix-security" in conference_ids:
            rows.append(CatalogRow(
                metadata=SemanticScholarMetadata(
                    paper_id="usenix-s2",
                    title="Fuzzing USENIX paper",
                    abstract="usenix scope",
                    year=2024,
                ),
                source_id="usenix",
                conference_id="usenix-security",
                catalog_paper_id="catalog-usenix",
            ))
        if "ccs" in source_ids and "ccs" in conference_ids:
            rows.append(CatalogRow(
                metadata=SemanticScholarMetadata(
                    paper_id="ccs-s2",
                    title="Fuzzing CCS paper",
                    abstract="ccs scope",
                    year=2024,
                ),
                source_id="ccs",
                conference_id="ccs",
                catalog_paper_id="catalog-ccs",
            ))
        return rows


@dataclass
class CatalogRecord:
    catalog_paper_id: str
    conference_id: str
    title: str
    doi: str
    official_page_url: str
    official_pdf_url: str
    prepublication_pdf_url: str | None = None
    arxiv_id: str | None = None
    year: int = 2024
    authors: tuple[str, ...] = ()


class CatalogStore:
    def __init__(self):
        self.papers = {
            "cat-usenix": CatalogRecord(
                "cat-usenix", "usenix-security", "Fuzzing USENIX paper", "10.5555/usenix",
                "https://www.usenix.org/paper/usenix", "https://www.usenix.org/paper/usenix.pdf",
            ),
            "cat-ccs": CatalogRecord(
                "cat-ccs", "ccs", "Fuzzing CCS paper", "10.5555/ccs",
                "https://dl.acm.org/paper/ccs", "https://dl.acm.org/paper/ccs.pdf",
            ),
        }

    def get_catalog_paper(self, paper_id):
        return self.papers.get(str(paper_id))

    def get_catalog_source_kinds(self, paper_id):
        return {"cat-usenix": ["usenix"], "cat-ccs": ["ccs"]}.get(str(paper_id), [])


class CatalogMetadataClient:
    def enrich(self, papers):
        return tuple(
            SemanticScholarEnrichment(
                paper.catalog_paper_id,
                metadata=SemanticScholarMetadata(
                    paper_id=f"s2-{paper.catalog_paper_id}",
                    title=paper.title,
                    year=paper.year,
                    doi=paper.doi,
                    authors=paper.authors,
                ),
            )
            for paper in papers
        )


def test_default_catalog_adapter_queries_each_scope_and_uses_recorded_identity(monkeypatch):
    calls = []

    class FakeSearch:
        def __init__(self, *, store=None):
            self._store = store

        def search(self, *, query, sources, max_results, years):
            calls.append(tuple(sources))
            ids = {"usenix": ("cat-usenix",), "ccs": ("cat-ccs",)}
            return SimpleNamespace(catalog_paper_ids=ids[sources[0]], error_code=None)

    import backend.app.research.application.search_catalog_adapter as search_module

    monkeypatch.setattr(search_module, "CatalogSearchAdapter", FakeSearch)
    adapter = CatalogSourceAdapter(semantic_client=CatalogMetadataClient(), catalog_store=CatalogStore())

    rows = adapter.search(
        query="fuzzing",
        source_ids=["usenix", "ccs"],
        conference_ids=["usenix-security", "ccs"],
        limit=20,
    )

    assert calls == [("usenix",), ("ccs",)]
    assert {(row.source_id, row.conference_id, row.catalog_paper_id) for row in rows} == {
        ("usenix", "usenix-security", "cat-usenix"),
        ("ccs", "ccs", "cat-ccs"),
    }


def test_discovery_truncates_provider_rows_and_persists_partial_source_failure(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = FakeClient()
    service = LiteratureMapService(store=store, client=client, executor=None, embedder=lambda texts: [[1.0, 0.0] for _ in texts])
    result = service.create_map(owner_id="owner-a", topic="fuzzing", name="Fuzz", requested_count=20)
    service.run_job(result.job.job_id)
    graph = service.graph(result.map.map_id, "owner-a")

    assert graph["map"]["status"] == "partial"
    assert graph["latest_job"]["counts"]["provider_count"] == 60
    assert graph["latest_job"]["counts"]["accepted_count"] == 20
    assert len(graph["nodes"]) == 20
    assert graph["layers"]["citation"]["status"] == "partial"
    assert graph["layers"]["citation"]["error_code"] == "SEMANTIC_SCHOLAR_RATE_LIMITED"
    assert all(node["catalog_paper_id"] is None for node in graph["nodes"])


def test_unscoped_discovery_preserves_relevance_order_and_separates_cache_operation(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = RelevanceClient()
    service = LiteratureMapService(
        store=store,
        client=client,
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    result = service.create_map(owner_id="owner-a", topic="graph attention networks", requested_count=20)
    service.run_job(result.job.job_id)
    graph = service.graph(result.map.map_id, "owner-a")

    assert [call[0] for call in client.calls[:1]] == ["relevance"]
    assert [node["external_ids"]["semantic_scholar"] for node in graph["nodes"]] == [
        "z-provider-first",
        "a-provider-second",
        "b-provider-third",
    ]
    relevance_key = store.request_cache_key(
        provider="semantic_scholar",
        operation="search_relevance",
        query="graph attention networks",
        filters={"year_start": None, "year_end": None, "limit": 20},
        page=0,
        fields=SEMANTIC_SCHOLAR_METADATA_FIELDS,
        version="literature-map-v1",
    )
    bulk_key = store.request_cache_key(
        provider="semantic_scholar",
        operation="search",
        query="graph attention networks",
        filters={"year_start": None, "year_end": None, "limit": 20},
        page=0,
        fields=SEMANTIC_SCHOLAR_METADATA_FIELDS,
        version="literature-map-v1",
    )
    assert store.get_request_cache(relevance_key) is not None
    assert store.get_request_cache(bulk_key) is None


def test_create_map_idempotency_reuses_map_and_rejects_parameter_change(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, client=FakeClient(), executor=None, embedder=lambda texts: [[1.0, 0.0] for _ in texts])
    first = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20, idempotency_key="same")
    second = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20, idempotency_key="same")
    assert first.map.map_id == second.map.map_id
    try:
        service.create_map(owner_id="owner-a", topic="different", requested_count=20, idempotency_key="same")
    except ValueError as error:
        assert "idempotency" in str(error)
    else:
        raise AssertionError("same idempotency key with different parameters must fail")


def test_running_job_resume_reuses_persisted_nodes_without_searching_again(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = FakeClient()
    service = LiteratureMapService(store=store, client=client, executor=None, embedder=lambda texts: [[1.0, 0.0] for _ in texts])
    created = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20)
    service.run_job(created.job.job_id)
    store.update_job(created.job.job_id, created.map.map_id, "owner-a", status="running", step="references", counts={"provider_count": 60, "accepted_count": 20, "node_count": 20, "provider_request_count": 61})
    before = len([call for call in client.calls if call[0] == "search"])
    resumed = service.run_job(created.job.job_id, "owner-a")
    after = len([call for call in client.calls if call[0] == "search"])
    assert after == before
    assert resumed is not None and resumed.status in {"completed", "partial"}


def test_conference_scope_uses_official_catalog_and_excludes_unscoped_provider_rows(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = FakeClient()
    catalog = OfficialCatalog()
    service = LiteratureMapService(
        store=store,
        client=client,
        catalog_adapter=catalog,
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    result = service.create_map(
        owner_id="owner-a",
        topic="fuzzing",
        requested_count=20,
        source_ids=["usenix"],
        conference_ids=["usenix-security"],
    )
    service.run_job(result.job.job_id, "owner-a")
    graph = service.graph(result.map.map_id, "owner-a")

    assert catalog.calls == [{
        "query": "fuzzing",
        "source_ids": ("usenix",),
        "conference_ids": ("usenix-security",),
        "limit": 20,
    }]
    assert [node["external_ids"]["semantic_scholar"] for node in graph["nodes"]] == ["official-s2-1"]
    assert graph["nodes"][0]["provenance"]["source"] == "usenix"


def test_catalog_snapshot_keeps_official_provenance_separate_from_s2_identity(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = FakeClient()
    service = LiteratureMapService(
        store=store,
        client=client,
        catalog_adapter=RichOfficialCatalog(),
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    result = service.create_map(
        owner_id="owner-a",
        topic="fuzzing",
        requested_count=20,
        source_ids=["usenix"],
        conference_ids=["usenix-security"],
    )
    service.run_job(result.job.job_id, "owner-a")
    node = service.graph(result.map.map_id, "owner-a")["nodes"][0]

    assert node["catalog_paper_id"] == "catalog-usenix-1"
    assert node["external_ids"]["semantic_scholar"] == "official-s2-1"
    assert node["external_ids"]["doi"] == "10.5555/official"
    assert node["source_url"] == "https://www.usenix.org/conference/paper-1"
    assert node["provenance"]["source_kind"] == "usenix"
    assert node["provenance"]["official_pdf_url"].endswith("paper-1.pdf")
    assert node["provenance"]["prepublication_pdf_url"].endswith("paper-1.pdf")
    assert "authorization" not in node["provenance"]["catalog_snapshot"]
    assert any(call[0] == "search" and call[2] == 19 for call in client.calls)
    assert service.graph(result.map.map_id, "owner-a")["latest_job"]["counts"]["provider_count"] == 61
    assert service.graph(result.map.map_id, "owner-a")["latest_job"]["counts"]["provider_truncated"] == 1


def test_catalog_gap_does_not_admit_unattested_s2_rows(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(
        store=store,
        client=FakeClient(),
        catalog_adapter=SparseOfficialCatalog(),
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    result = service.create_map(
        owner_id="owner-a",
        topic="fuzzing",
        requested_count=20,
        source_ids=["usenix"],
        conference_ids=["usenix-security"],
    )
    service.run_job(result.job.job_id, "owner-a")
    graph = service.graph(result.map.map_id, "owner-a")

    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["catalog_paper_id"] == "catalog-only-1"
    assert graph["latest_job"]["status"] == "partial"
    assert graph["latest_job"]["counts"]["provider_count"] == 61


def test_unknown_scope_is_rejected_before_a_map_is_created(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, client=FakeClient(), executor=None)

    try:
        service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20, source_ids=["untrusted-source"])
    except ValueError as error:
        assert str(error) == "INVALID_MAP_SCOPE"
    else:
        raise AssertionError("unknown source must not be persisted")


def test_multiple_scopes_use_actual_catalog_attestations_with_or_semantics(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(
        store=store,
        client=FakeClient(),
        catalog_adapter=MultiOfficialCatalog(),
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    result = service.create_map(
        owner_id="owner-a",
        topic="fuzzing",
        requested_count=20,
        source_ids=["usenix", "ccs"],
        conference_ids=["usenix-security", "ccs"],
    )
    service.run_job(result.job.job_id, "owner-a")
    nodes = service.graph(result.map.map_id, "owner-a")["nodes"]

    assert {node["catalog_paper_id"] for node in nodes} == {"catalog-usenix", "catalog-ccs"}
    assert {node["provenance"]["source"] for node in nodes} == {"usenix", "ccs"}


def test_incompatible_scope_combination_is_rejected_before_creation(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, client=FakeClient(), executor=None)

    try:
        service.create_map(
            owner_id="owner-a",
            topic="fuzzing",
            requested_count=20,
            source_ids=["usenix"],
            conference_ids=["ccs"],
        )
    except ValueError as error:
        assert str(error) == "INVALID_MAP_SCOPE"
    else:
        raise AssertionError("incompatible source/conference scope must fail closed")


def test_successful_metadata_request_is_reused_across_maps(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = FakeClient()
    service = LiteratureMapService(
        store=store,
        client=client,
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    first = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20)
    service.run_job(first.job.job_id, "owner-a")
    second = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20)
    service.run_job(second.job.job_id, "owner-a")

    assert len([call for call in client.calls if call[0] == "search"]) == 1
