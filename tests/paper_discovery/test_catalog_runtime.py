"""Spec032 Task08: source registry/runtime integration contracts."""

from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app.api import routes_paper
from backend.app.main import app
from backend.app.paper_discovery.application.catalog_runtime import CatalogSourceRuntime
from backend.app.paper_discovery.application.worker_tool import PAPER_DISCOVERY_TOOL_NAME, WorkerToolResult
from backend.app.paper_discovery.domain.paper_discovery import SearchJob, SourceFetchUnit
from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import (
    CrossrefCatalogAdapter,
    FetchUnit,
    OpenAlexCatalogAdapter,
    SourceRecord,
)
from backend.app.paper_discovery.infrastructure.ccs_publication_source import CcsPublicationSource
from backend.app.paper_discovery.infrastructure.dblp_publication_source import DBLPPublicationSource
from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import IeeeSpPublicationSource
from backend.app.paper_discovery.infrastructure.ndss_publication_source import NdssPublicationSource
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry
from backend.app.paper_discovery.infrastructure.usenix_publication_source import UsenixAcceptedSource
from backend.app.research.application.search_catalog_adapter import (
    CatalogSearchAdapter,
    CatalogSourceBundle,
    CatalogSourceFactory,
    SearchWorker,
)

NDSS_OFFICIAL_FIXTURE = Path(__file__).parents[1] / "fixtures" / "ndss" / "official-accepted-papers-2024.html"
NDSS_OFFICIAL_URL = "https://www.ndss-symposium.org/ndss2024/accepted-papers/"


def test_source_registry_adapter_factory_covers_all_seven_sources(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "paper-search.sqlite3")
    registry = SourceRegistry(store=store, timeout=3)
    expected = {
        "usenix": UsenixAcceptedSource,
        "dblp": DBLPPublicationSource,
        "ieee_sp": IeeeSpPublicationSource,
        "ccs": CcsPublicationSource,
        "ndss": NdssPublicationSource,
        "openalex": OpenAlexCatalogAdapter,
        "crossref": CrossrefCatalogAdapter,
    }

    for source_id, adapter_type in expected.items():
        adapter = registry.adapter(source_id)
        assert isinstance(adapter, adapter_type)
        assert adapter.source_id == source_id
        assert adapter is registry.adapter(source_id)


def test_source_sync_api_rejects_unknown_and_disabled_sources(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "paper-search.sqlite3")
    registry = SourceRegistry(store=store)
    registry.set_enabled("openalex", False)
    client = TestClient(app)

    with patch.object(routes_paper, "_paper_store", return_value=store), patch.object(
        routes_paper, "_source_registry", return_value=registry
    ):
        unknown = client.post("/api/papers/sources/not-a-source/sync", json={"scope": {"years": [2024]}})
        disabled = client.post("/api/papers/sources/openalex/sync", json={"scope": {"years": [2024]}})

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "SOURCE_NOT_FOUND"
    assert disabled.status_code == 422
    assert disabled.json()["code"] == "SOURCE_DISABLED"
    assert store.list_search_ids() == []


class _FakeOpenAlexAdapter:
    source_id = "openalex"

    def discover_units(self, scope):
        return [FetchUnit("openalex", str(year), {"filter": f"from_publication_date:{year}-01-01"})
                for year in scope.get("years", [])]

    def fetch_unit(self, unit, conditional_headers=None):
        del conditional_headers
        updated = unit.with_result(status="fetched", body=b"runtime-fixture")
        return updated, {"results": [{"title": "Runtime fixture", "publication_year": int(unit.scope_key)}]}

    def parse_catalog(self, response):
        assert response["results"]
        return [SourceRecord(
            source_id="openalex",
            source_record_id="openalex-record-1",
            authority_rank=30,
            title="Runtime fixture",
            abstract="A runtime fixture abstract.",
            authors=("Author One",),
            year=2024,
            doi="10.1000/runtime-fixture",
            provenance={"title": "openalex", "abstract": "openalex", "doi": "openalex"},
        )]


def test_source_sync_api_reports_real_terminal_and_persists_job_progress(tmp_path):
    database_path = tmp_path / "paper-search.sqlite3"
    store = PaperDiscoveryStore(database_path)
    registry = SourceRegistry(store=store)
    adapter = _FakeOpenAlexAdapter()
    client = TestClient(app)

    def run_now(runtime, sync_id, source_id, years):
        runtime.run(sync_id, source_id, years)
        return True

    with patch.object(routes_paper, "_paper_store", return_value=store), patch.object(
        routes_paper, "_source_registry", return_value=registry
    ), patch.object(registry, "adapter", return_value=adapter), patch.object(
        routes_paper, "submit_catalog_source_sync", side_effect=run_now
    ):
        queued = client.post("/api/papers/sources/openalex/sync", json={"scope": {"years": [2024]}})
        assert queued.status_code == 202
        sync_id = queued.json()["sync_id"]
        terminal = client.get(f"/api/papers/sources/openalex/sync/{sync_id}")

    assert queued.json()["status"] == "queued"
    assert terminal.status_code == 200
    payload = terminal.json()
    assert payload["status"] == "completed"
    assert payload["error_code"] is None
    assert payload["progress"]["status"] == "completed"
    assert payload["progress"]["paper_count"] == 1
    assert payload["progress"]["message_code"] == "SOURCE_COMPLETED"
    assert [item["unit_id"] for item in payload["progress"]["completed_units"]] == ["openalex|2024"]

    job = store.get_search_job(sync_id)
    assert job is not None
    assert job.status == "completed"
    assert job.graph_version == "catalog-source-sync-v1"
    assert job.total_results == 1
    progress = store.get_source_progress(sync_id)
    assert len(progress) == 1
    assert progress[0].source_kind == "openalex"
    assert progress[0].status == "completed"
    assert store.get_fetch_unit("openalex|2024").status == "completed"

    restarted = PaperDiscoveryStore(database_path)
    assert restarted.get_search_job(sync_id).status == "completed"
    assert restarted.get_source_progress(sync_id)[0].status == "completed"


def test_source_sync_progress_keeps_failed_units_out_of_completed_units(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "partial-runtime.sqlite3")
    store.create_search_job(SearchJob(
        "partial-runtime", "partial", ["openalex"], [2024, 2025],
        expires_at="2099-01-01T00:00:00Z", created_at="2026-09-20T00:00:00Z",
    ))

    class PartialAdapter(_FakeOpenAlexAdapter):
        def fetch_unit(self, unit, conditional_headers=None):
            del conditional_headers
            if unit.scope_key == "2025":
                return unit.with_result(status="failed"), None
            return super().fetch_unit(unit)

    registry = SourceRegistry(store=store)
    with patch.object(registry, "adapter", return_value=PartialAdapter()):
        result = CatalogSourceRuntime(store=store, registry=registry).run(
            "partial-runtime", "openalex", [2024, 2025]
        )

    assert result.status == "partial"
    progress = store.get_source_progress("partial-runtime")[0]
    assert progress.status == "merging"
    assert [item["unit_id"] for item in progress.completed_units] == ["openalex|2024"]
    assert progress.cached_units == []


def test_source_sync_progress_reports_cached_unit_id(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "cached-runtime.sqlite3")
    for search_id in ("cached-first", "cached-second"):
        store.create_search_job(SearchJob(
            search_id, "cached", ["openalex"], [2024],
            expires_at="2099-01-01T00:00:00Z", created_at="2026-09-20T00:00:00Z",
        ))
    registry = SourceRegistry(store=store)
    adapter = _FakeOpenAlexAdapter()
    with patch.object(registry, "adapter", return_value=adapter):
        runtime = CatalogSourceRuntime(store=store, registry=registry)
        assert runtime.run("cached-first", "openalex", [2024]).status == "completed"
        assert runtime.run("cached-second", "openalex", [2024]).status == "completed"

    progress = store.get_source_progress("cached-second")[0]
    assert progress.status == "cached"
    assert [item["unit_id"] for item in progress.cached_units] == ["openalex|2024"]
    assert [item["unit_id"] for item in progress.completed_units] == ["openalex|2024"]


def test_catalog_runtime_uses_ndss_official_2024_route_and_keeps_other_years_fallback(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "ndss-runtime.sqlite3")
    store.create_search_job(SearchJob(
        "ndss-runtime", "ndss official", ["ndss"], [2024, 2025],
        expires_at="2099-01-01T00:00:00Z", created_at="2026-09-20T00:00:00Z",
    ))
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert not request.url.path.endswith(".pdf")
        if str(request.url) == NDSS_OFFICIAL_URL:
            return httpx.Response(200, content=NDSS_OFFICIAL_FIXTURE.read_bytes())
        assert request.url.host == "api.crossref.org"
        assert "2025-01-01" in str(request.url)
        return httpx.Response(200, json={"message": {"items": [], "total-results": 0}})

    source = NdssPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: ["93.184.216.34"],
        rate_limit_seconds=0.0,
        sleep=lambda _seconds: None,
    )
    registry = SourceRegistry(store=store)
    with patch.object(registry, "adapter", return_value=source):
        result = CatalogSourceRuntime(store=store, registry=registry).run(
            "ndss-runtime", "ndss", [2024, 2025]
        )

    assert result.status == "completed"
    assert calls[0] == NDSS_OFFICIAL_URL
    assert len(calls) == 2
    unit = store.get_fetch_unit("ndss|ndss|2024|official")
    assert unit is not None
    assert unit.unit_key == "ndss:2024:official"
    assert unit.paper_count == 3


def test_catalog_runtime_keeps_official_and_doi_provenance_distinct(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "route-provenance.sqlite3")
    runtime = CatalogSourceRuntime(store=store, registry=SourceRegistry(store=store))
    official_unit = SourceFetchUnit(
        "ndss|ndss|2024|official", "ndss", "ndss", 2024, "ndss:2024:official",
    )
    doi_unit = SourceFetchUnit(
        "ndss|ndss|2024", "ndss", "ndss", 2024, "ndss:2024",
    )
    runtime._save_unit(official_unit)
    runtime._save_unit(doi_unit)
    official = {
        "title": "Route-separated paper", "authors": ["Official Author"], "year": 2024,
        "provenance": {"title": "ndss", "authors": "ndss"},
    }
    doi = {
        "title": "Route-separated paper", "authors": ["DOI Author"], "year": 2024,
        "doi": "10.14722/route-separated", "provenance": {
            "title": "crossref", "authors": "crossref", "doi": "crossref",
        },
    }

    paper_id = runtime._persist_record("ndss", official_unit, official)
    assert paper_id
    assert runtime._persist_record("ndss", doi_unit, doi) == paper_id

    provenance = store.get_field_provenance(paper_id)
    assert provenance["title"]["source_id"] == "ndss:official"
    assert provenance["authors"]["source_id"] == "ndss:official"
    assert provenance["doi"]["source_id"] == "crossref"
    assert store.save_field_provenance(paper_id, "title", "openalex") is False
    assert store.get_field_provenance(paper_id)["title"]["source_id"] == "ndss:official"

    with store._connect() as connection:
        rows = connection.execute(
            "SELECT source_key FROM catalog_source_records WHERE catalog_paper_id=? ORDER BY source_key",
            (paper_id,),
        ).fetchall()
    assert len(rows) == 2
    assert any("ndss:official" in row[0] for row in rows)


def test_non_legacy_catalog_search_uses_worker_envelope_and_freezes_provenance(tmp_path):
    """Planner-selected OpenAlex must use paper_discovery, not the legacy graph."""
    store = PaperDiscoveryStore(tmp_path / "worker-search.sqlite3")
    calls = []

    class Worker:
        def discover(self, source_id, scope):
            calls.append((source_id, scope))
            return WorkerToolResult(
                tool=PAPER_DISCOVERY_TOOL_NAME,
                operation="discover",
                source_id="openalex",
                status="completed",
                provenance={
                    "openalex:candidate-1": {
                        "title": "openalex", "abstract": "openalex", "doi": "openalex",
                    }
                },
                payload={"candidates": [{
                    "candidate_id": "openalex:candidate-1",
                    "source_id": "openalex",
                    "title": "Worker-backed paper",
                    "abstract": "A worker-backed abstract.",
                    "authors": ["Researcher"],
                    "year": 2024,
                    "doi": "10.1000/worker-backed",
                    "provenance": {"title": "openalex", "abstract": "openalex", "doi": "openalex"},
                }]},
            )

    class Rag:
        def index(self, papers):
            assert papers[0].catalog_paper_id == "openalex:candidate-1"
            return True

        def retrieve_and_rerank(self, query, papers, **kwargs):
            assert query == "worker-backed"
            assert kwargs["conference_ids"] == ["openalex"]
            return [{"catalog_paper_id": papers[0].catalog_paper_id, "final_score": 0.9}]

    class Factory:
        def build(self, *, source_scope):
            assert source_scope == "openalex"
            return CatalogSourceBundle(store, object(), object(), Rag(), None, Worker())

    adapter = CatalogSearchAdapter(source_factory=Factory())
    output = SearchWorker(adapter=adapter).run({
        "work_item_id": "planner-openalex",
        "query": "worker-backed",
        "source_ids": ["openalex"],
        "scope": {"years": [2024]},
        "max_results": 3,
    })

    assert calls == [("openalex", {"query": "worker-backed", "years": [2024], "limit": 3})]
    assert output["candidates"] == ["openalex:candidate-1"]
    search_id = output["search_id"]
    frozen = store.get_search_job(search_id)
    assert frozen is not None
    assert frozen.status == "completed"
    assert frozen.conference_ids == ["openalex"]
    assert store.get_catalog_paper("openalex:candidate-1").title == "Worker-backed paper"
    assert store.get_catalog_source_kinds("openalex:candidate-1") == ["openalex"]
    assert store.get_field_provenance("openalex:candidate-1")["abstract"]["source_id"] == "openalex"


def test_catalog_source_factory_exposes_worker_for_non_legacy_scope(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "worker-factory.sqlite3")
    bundle = CatalogSourceFactory(store=store).build(source_scope="openalex")

    assert bundle.graph is None
    assert bundle.worker_tool is not None
