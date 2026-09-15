"""Spec034 Task06 contracts: real catalog seam, evaluation and coverage review."""

from types import SimpleNamespace

from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper, CatalogSourceRecord, SourceFetchUnit
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.research.application.search_catalog_adapter import (
    CatalogSearchAdapter,
    CatalogSourceBundle,
    CatalogSourceFactory,
    CoverageCritic,
    PaperEvaluator,
    SearchWorker,
    map_catalog_tool_args,
)
from backend.app.research.application.orchestrator import Orchestrator


def test_catalog_source_factory_injects_existing_store_and_sources(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "catalog.sqlite3")
    accepted, dblp = object(), object()
    bundle = CatalogSourceFactory(store=store, accepted_source=accepted, dblp_source=dblp).build()
    assert bundle.store is store
    assert bundle.accepted_source is accepted
    assert bundle.dblp_source is dblp
    assert bundle.graph is not None


def test_search_worker_maps_scope_and_preserves_diagnostics():
    seen = {}

    def search(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(catalog_paper_ids=("p1",), count=1, degraded=False, error_code=None,
                               diagnostics={"cache_hit": 1, "remote_refresh": 0})

    worker = SearchWorker(adapter=CatalogSearchAdapter(searcher=search))
    output = worker.run({"work_item_id": "w1", "query": "supply chain", "sources": ["usenix"],
                         "time_range": {"years": [2024]}, "max_results": 4,
                         "publication_scope": "accepted"})
    assert output["candidates"] == ["p1"]
    assert output["refresh_diagnostics"]["cache_hit"] == 1
    assert seen == {"query": "supply chain", "sources": ("usenix",), "years": (2024,),
                    "max_results": 4, "publication_scope": "accepted"}


def test_tool_mapping_uses_first_source_and_does_not_leak_extra_params():
    mapped = map_catalog_tool_args({"sources": ["dblp", "usenix"], "query": "q",
                                    "time_range": {"years": [2022, 2023]}, "max_results": 7,
                                    "publication_scope": "published", "facets": ["ignored"]})
    assert mapped == {"source": "dblp", "query": "q", "years": [2022, 2023], "limit": 7,
                      "publication_scope": "published"}


def test_evaluator_keeps_soft_threshold_boundary_and_rejection_reasons():
    evaluator = PaperEvaluator(threshold=0.7, soft_floor=0.3)
    result = evaluator.evaluate([
        {"catalog_paper_id": "keep", "title": "Supply chain defense", "abstract": "defense"},
        {"catalog_paper_id": "drop", "title": "Cooking recipes", "abstract": "food"},
    ], query="supply chain defense")
    assert result["kept"] and result["kept"][0]["candidate_id"] == "keep"
    assert result["eliminated"][0]["reason"]
    assert result["statistics"]["eliminated"] == 1
    assert "threshold" in result["diagnostics"]


def test_evaluator_keeps_five_catalog_backed_candidates_when_threshold_is_strict():
    evaluator = PaperEvaluator(threshold=1.0, soft_floor=0.1)
    rows = [
        {"catalog_paper_id": f"paper-{index}", "title": "unrelated", "abstract": ""}
        for index in range(5)
    ]

    result = evaluator.evaluate(rows, query="supply chain defense")

    assert [item["candidate_id"] for item in result["kept"]] == [
        "paper-0", "paper-1", "paper-2", "paper-3", "paper-4"
    ]
    assert all(item["evidence_refs"] == [f"catalog:paper-{index}"] for index, item in enumerate(result["kept"]))
    assert all(item["reason"] == "retained to satisfy minimum report candidate floor" for item in result["kept"])
    assert result["statistics"]["minimum_floor_applied"] is True


def test_orchestrator_selection_floor_only_applies_to_large_candidate_pools():
    orchestrator = Orchestrator.__new__(Orchestrator)
    five = [f"paper-{index}" for index in range(5)]
    fewer = five[:4]

    assert len(orchestrator._evaluate_papers(five, {}, target_paper_count=1)) == 5
    assert len(orchestrator._evaluate_papers(fewer, {}, target_paper_count=1)) == 1


def test_critic_bounds_replan_and_rejects_scope_expansion():
    critic = CoverageCritic(max_replan_rounds=2)
    first = critic.review(facets=["attacks", "defense"], selected=[], round_number=0)
    assert first["bounded_replan"] is True
    assert len(first["recommendations"]) <= 2
    expanded = critic.review(facets=["attacks"], selected=[], round_number=1,
                             proposed_facets=["attacks", "new-topic"])
    assert expanded["bounded_replan"] is False
    assert expanded["approval_required"] is True


def test_no_source_is_not_empty_success():
    outcome = CatalogSearchAdapter(searcher=lambda **_: (_ for _ in ()).throw(RuntimeError())).search(
        query="q", sources=("usenix",), years=(2024,))
    assert outcome.catalog_paper_ids == ()
    assert outcome.error_code == "SOURCE_UNAVAILABLE"
    assert outcome.degraded is True


def test_default_adapter_is_local_first_when_catalog_has_enough_indexed_rows(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "catalog.sqlite3")
    store.upsert_catalog_paper(CatalogPaper(
        "local-1", "usenix-security", 2024, "Supply chain defense", "supply chain defense",
        abstract="defense", metadata_hash="h", index_status="indexed",
    ))

    class LocalRag:
        def retrieve_and_rerank(self, query, papers, **kwargs):
            assert kwargs["years"] == (2024,)
            return [{"catalog_paper_id": papers[0].catalog_paper_id, "final_score": 1.0}]

    class NoRefresh:
        def build(self):
            raise AssertionError("a full local result must not refresh remote sources")

    outcome = CatalogSearchAdapter(store=store, rag=LocalRag(), source_factory=NoRefresh()).search(
        query="supply chain", sources=("usenix",), years=(2024,), max_results=1,
    )
    assert outcome.catalog_paper_ids == ("local-1",)
    assert outcome.diagnostics["cache_hit"] == 1


def test_source_scope_factory_and_search_job_keep_dblp_isolated(tmp_path):
    """A DBLP request must not use the USENIX scope or USENIX-only rows."""
    store = PaperDiscoveryStore(tmp_path / "catalog.sqlite3")
    now = "2026-09-13T00:00:00Z"
    for source_kind, paper_id in (("usenix", "official"), ("dblp", "dblp-only")):
        store.upsert_catalog_paper(CatalogPaper(
            paper_id, "usenix-security", 2024, paper_id, paper_id,
            abstract="supply chain", metadata_hash=paper_id, index_status="indexed",
        ))
        unit_id = f"{source_kind}|usenix-security|2024|sample"
        store.save_fetch_unit(SourceFetchUnit(
            unit_id, source_kind, "usenix-security", 2024, unit_id,
            status="completed", created_at=now, updated_at=now,
        ), now)
        store.save_source_record(CatalogSourceRecord(
            f"record-{source_kind}", paper_id, unit_id, source_kind, paper_id,
            observed_at=now,
        ), now)

    seen = []

    class LocalRag:

        def retrieve_and_rerank(self, query, papers, **kwargs):
            seen.extend(paper.catalog_paper_id for paper in papers)
            return [{"catalog_paper_id": paper.catalog_paper_id, "final_score": 1.0}
                    for paper in papers]

    class NoRemoteFactory:
        def build(self, **kwargs):
            raise AssertionError("the DBLP local hit must not refresh remote sources")

    outcome = CatalogSearchAdapter(store=store, rag=LocalRag(), source_factory=NoRemoteFactory()).search(
        query="supply chain", sources=("dblp",), years=(2024,), max_results=1,
    )
    assert outcome.catalog_paper_ids == ("dblp-only",)
    assert seen == ["dblp-only"]

    bundle = CatalogSourceFactory(store=store, accepted_source=object(), dblp_source=object()).build(
        source_scope="dblp"
    )
    assert bundle.graph.source_scope == "dblp"


def test_source_scope_contract_maps_usenix_dblp_and_all(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "catalog.sqlite3")
    factory = CatalogSourceFactory(store=store, accepted_source=object(), dblp_source=object())
    usenix = factory.build(source_scope="usenix")
    dblp = factory.build(source_scope="dblp")
    all_sources = factory.build(source_scope="all")
    assert usenix.graph.source_scope == "usenix"
    assert dblp.graph.source_scope == "dblp"
    assert all_sources.graph.source_scope == "all"
    assert usenix.graph is not dblp.graph is not all_sources.graph
    assert usenix.store is dblp.store is all_sources.store is store
    assert usenix.accepted_source is dblp.accepted_source is all_sources.accepted_source
    assert usenix.dblp_source is dblp.dblp_source is all_sources.dblp_source
    assert usenix.rag is dblp.rag is all_sources.rag


def test_dblp_refresh_persists_dblp_scope_job_only(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "catalog.sqlite3")
    calls = {}

    class Graph:
        def run(self, search_id):
            calls["search_id"] = search_id

    class RefreshFactory:
        def build(self, *, source_scope):
            calls["scope"] = source_scope
            return CatalogSourceBundle(store, object(), object(), LocalRag(), Graph())

    class LocalRag:
        def retrieve_and_rerank(self, query, papers, **kwargs):
            return []

    outcome = CatalogSearchAdapter(
        store=store, rag=LocalRag(), source_factory=RefreshFactory()
    ).search(query="q", sources=("dblp",), years=(2024,), max_results=1)
    job = store.get_search_job(calls["search_id"])
    assert calls["scope"] == "dblp"
    assert job.conference_ids == ["dblp"]
    assert outcome.catalog_paper_ids == ()


def test_graph_scope_skips_opposite_source_node_without_touching_store():
    from backend.app.paper_discovery.application.catalog_search_graph import CatalogSearchGraph
    from backend.app.paper_discovery.domain.paper_discovery import SearchJob

    class ProbeStore:
        def __init__(self):
            self.touched = []

        def save_source_progress(self, progress):
            self.touched.append(("progress", progress.source_kind, progress.message_code))

        def append_search_event(self, event):
            self.touched.append(("event", event.source_kind, event.event_type))

        def list_conferences(self):
            raise AssertionError("opposite source must not inspect conference configuration")

    store = ProbeStore()
    job = SearchJob("scope-probe", "q", ["dblp"], [2024])
    graph = CatalogSearchGraph(store=store, accepted_source=object(), dblp_source=object(),
                               source_scope="dblp")
    result = graph.sync_usenix(job)
    assert result["status"] == "skipped"
    assert all(item[1] == "usenix" for item in store.touched)


def test_long_lived_adapter_refreshes_with_matching_graph_per_scope(tmp_path):
    """A single adapter must not route a later request through the first Graph."""
    class SharedRag:
        def retrieve_and_rerank(self, query, papers, **kwargs):
            return []

    class RecordingFactory:
        def __init__(self, store):
            self.store = store
            self.built_scopes = []
            self.run_scopes = []

        def build(self, *, source_scope):
            self.built_scopes.append(source_scope)
            factory = self

            class Graph:
                def run(self, search_id):
                    factory.run_scopes.append(source_scope)

            rag = SharedRag()
            return CatalogSourceBundle(self.store, object(), object(), rag, Graph())

    for sequence in (("usenix", "dblp", "all"), ("all", "dblp")):
        store = PaperDiscoveryStore(tmp_path / ("-".join(sequence) + ".sqlite3"))
        factory = RecordingFactory(store)
        adapter = CatalogSearchAdapter(store=store, rag=SharedRag(), source_factory=factory)
        for source in sequence:
            outcome = adapter.search(query="scope probe", sources=(source,), years=(2024,), max_results=1)
            assert outcome.error_code == "SOURCE_DEGRADED"
        assert factory.built_scopes == list(sequence)
        assert factory.run_scopes == list(sequence)
