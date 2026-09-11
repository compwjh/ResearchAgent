import threading
from types import SimpleNamespace

import backend.app.paper_discovery.application.catalog_search_graph as catalog_graph_module
from backend.app.paper_discovery.application.catalog_search_graph import (
    CatalogRagAdapter,
    CatalogSearchGraph,
    reset_running_job_ids,
    reset_running_jobs,
)
from backend.app.paper_discovery.domain.paper_discovery import (
    CatalogPaper,
    SearchEvent,
    SearchJob,
    SourceFetchUnit,
)
from backend.app.paper_discovery.infrastructure.dblp_publication_source import DBLPPublicationResult
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


def _job(search_id="search-1", status="queued", years=None):
    return SearchJob(
        search_id, "security", ["usenix-security"], list(years or [2024]), status=status,
        expires_at="2099-01-01T00:00:00Z", created_at="2098-01-01T00:00:00Z",
    )


class _Accepted:
    store = None


class _DBLP:
    def __init__(self):
        self.calls = 0

    def search(self, source, query, years, limit):
        self.calls += 1
        return DBLPPublicationResult(({
            "info": {
                "title": "A DBLP Paper", "year": "2024", "abstract": "Abstract",
                "key": "conf/uss/a", "doi": "10.1000/a", "authors": ["Ada"],
            }
        },), ())


class _PartialDBLP:
    def search(self, source, query, years, limit):
        return DBLPPublicationResult(({
            "info": {
                "title": "A DBLP Paper", "year": "2024", "abstract": "Abstract",
                "key": "conf/uss/a", "doi": "10.1000/a", "authors": ["Ada"],
            }
        },), ("DBLP_TIMEOUT",), None)


def test_dblp_persists_fk_fetch_unit_and_skips_completed_unit(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = _job()
    store.create_search_job(job)
    dblp = _DBLP()
    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=dblp, dblp_enabled=True)

    first = graph.sync_dblp(job)
    second = graph.sync_dblp(job)

    assert first["status"] == "completed"
    assert second["status"] == "cached"
    assert dblp.calls == 1
    unit_id = "dblp|usenix-security|2024|stream"
    unit = store.get_fetch_unit(unit_id)
    assert unit is not None and unit.status == "completed"
    paper = store.list_catalog_papers(index_status=None)[0]
    with store._connect() as connection:
        row = connection.execute(
            "SELECT fetch_unit_id FROM catalog_source_records WHERE catalog_paper_id=?",
            (paper.catalog_paper_id,),
        ).fetchone()
    assert row[0] == unit_id


def test_dblp_multi_year_warning_is_partial_without_downgrading_success_year(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = _job("search-dblp-partial", years=[2023, 2024])
    store.create_search_job(job)
    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=_PartialDBLP(), dblp_enabled=True)

    result = graph.sync_dblp(job)

    assert result["status"] == "partial"
    assert result["error_code"] == "DBLP_TIMEOUT"
    assert store.get_fetch_unit("dblp|usenix-security|2023|stream").status == "partial"
    assert store.get_fetch_unit("dblp|usenix-security|2024|stream").status == "completed"
    progress = store.get_source_progress(job.search_id)
    dblp_progress = next(item for item in progress if item.source_kind == "dblp")
    assert dblp_progress.status in {"merging", "partial"}
    assert dblp_progress.error_code == "DBLP_TIMEOUT"
    assert {item["year"]: item["status"] for item in dblp_progress.completed_units} == {
        2023: "partial", 2024: "completed",
    }

    paper = store.list_catalog_papers(index_status=None)[0]
    store.mark_catalog_indexed(paper.catalog_paper_id)
    graph.freeze_search_results(
        job,
        [{"catalog_paper_id": paper.catalog_paper_id, "final_score": 1.0}],
        degraded=False,
        source_results=({"status": "completed"}, result),
    )
    assert store.get_search_job(job.search_id).status == "partial"


def test_inflight_dblp_unit_is_waiting_and_cannot_freeze_empty_results(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = _job("search-dblp-waiting")
    store.create_search_job(job)
    unit_id = "dblp|usenix-security|2024|stream"
    store.save_fetch_unit(SourceFetchUnit(
        unit_id, "dblp", "usenix-security", 2024, "conf/uss|2024", status="pending",
    ))
    assert store.acquire_fetch_unit(unit_id, "other-worker", 300, now="2099-01-01T00:00:00Z")
    dblp = _DBLP()
    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=dblp, dblp_enabled=True)

    result = graph.sync_dblp(job)

    assert result["status"] in {"waiting", "partial", "queued"}
    assert result["status"] != "cached"
    assert dblp.calls == 0
    graph.freeze_search_results(
        job, [], degraded=False,
        source_results=({"status": "completed"}, result),
    )
    assert store.get_search_job(job.search_id).status not in {"completed", "partial", "failed"}


def test_concurrent_dblp_workers_only_one_fetches_and_other_waits(tmp_path):
    class BlockingDBLP:
        def __init__(self):
            self.calls = 0
            self.started = threading.Event()
            self.release = threading.Event()
            self.lock = threading.Lock()

        def search(self, source, query, years, limit):
            with self.lock:
                self.calls += 1
            self.started.set()
            assert self.release.wait(5)
            return DBLPPublicationResult((), ())

    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    first_job = _job("search-concurrent-a")
    second_job = _job("search-concurrent-b")
    store.create_search_job(first_job)
    store.create_search_job(second_job)
    source = BlockingDBLP()
    first_graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=source, dblp_enabled=True)
    second_graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=source, dblp_enabled=True)
    results = {}

    first = threading.Thread(target=lambda: results.setdefault("first", first_graph.sync_dblp(first_job)))
    first.start()
    assert source.started.wait(5)
    second = threading.Thread(target=lambda: results.setdefault("second", second_graph.sync_dblp(second_job)))
    second.start()
    second.join(5)
    source.release.set()
    first.join(5)

    assert not first.is_alive() and not second.is_alive()
    assert source.calls == 1
    assert results["second"]["status"] == "waiting"
    assert results["first"]["status"] == "completed"


def test_catalog_rag_payload_round_trips_catalog_ids_through_shared_rrf(tmp_path, monkeypatch):
    """Directory points must satisfy the shared Hit/RRF payload contract."""
    class FakeQdrant:
        def __init__(self):
            self.points = []

        def collection_exists(self, name):
            return bool(self.points)

        def upsert(self, *, collection_name, points):
            self.points = [SimpleNamespace(payload=point.payload, score=0.9 - i * 0.1)
                           for i, point in enumerate(points)]

        def query_points(self, **kwargs):
            return SimpleNamespace(points=self.points)

    client = FakeQdrant()
    monkeypatch.setattr(catalog_graph_module, "ensure_collection", lambda *args, **kwargs: None)
    adapter = CatalogRagAdapter(
        client=client,
        embedder=lambda texts: [[0.1, 0.2] for _ in texts],
        sparse_encoder=lambda text: {"indices": [0], "values": [1.0]},
        reranker=None,
    )
    papers = [
        CatalogPaper("catalog-a", "usenix-security", 2024, "Alpha", "alpha",
                     abstract="alpha abstract", metadata_hash="a", index_status="indexed"),
        CatalogPaper("catalog-b", "usenix-security", 2024, "Beta", "beta",
                     abstract="beta abstract", metadata_hash="b", index_status="indexed"),
    ]

    assert adapter.index(papers) is True
    assert {point.payload["paper_id"] for point in client.points} == {"catalog-a", "catalog-b"}
    assert all(point.payload["catalog_paper_id"] == point.payload["paper_id"] for point in client.points)
    assert all(point.payload["chunker"] == "catalog-v1" for point in client.points)

    ranked = adapter.retrieve_and_rerank("security", papers)
    assert {item["catalog_paper_id"] for item in ranked} == {"catalog-a", "catalog-b"}
    assert all(item["catalog_paper_id"] for item in ranked)

    # The graph's freeze boundary resolves ranked IDs back to indexed catalog
    # rows.  Keep this assertion in the same fake-Qdrant test so a regression
    # in the shared Hit/RRF contract cannot silently produce an empty snapshot.
    store = PaperDiscoveryStore(tmp_path / "catalog-rag-freeze.sqlite3")
    job = _job("search-rag-freeze")
    store.create_search_job(job)
    for paper in papers:
        store.upsert_catalog_paper(paper)
        store.mark_catalog_indexed(paper.catalog_paper_id)
    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=_DBLP())
    graph.freeze_search_results(
        job,
        ranked,
        degraded=False,
        source_results=({"status": "completed"}, {"status": "completed"}),
    )
    assert {row.catalog_paper_id for row in store.get_search_results("search-rag-freeze")} == {
        "catalog-a", "catalog-b",
    }


def test_catalog_listing_and_freeze_exclude_non_indexed_and_use_stable_order(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    job = _job("search-2", years=[2023, 2024, 2025, 2099])
    store.create_search_job(job)
    papers = [
        CatalogPaper("p-z", "usenix-security", 2024, "Zulu", "zulu", abstract="A", metadata_hash="z"),
        CatalogPaper("p-a", "usenix-security", 2023, "Alpha", "alpha", abstract="A", metadata_hash="a"),
        CatalogPaper("p-new", "usenix-security", 2025, "New", "new", abstract="A", metadata_hash="n"),
        CatalogPaper("p-failed", "usenix-security", 2099, "Failed", "failed", abstract="A", metadata_hash="f"),
    ]
    for paper in papers:
        store.upsert_catalog_paper(paper)
        if paper.catalog_paper_id == "p-failed":
            store.mark_catalog_index_failed(paper.catalog_paper_id)
        else:
            store.mark_catalog_indexed(paper.catalog_paper_id)

    visible = store.list_catalog_papers(["usenix-security"], [2023, 2024, 2025, 2099])
    assert [paper.catalog_paper_id for paper in visible] == ["p-a", "p-new", "p-z"]

    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=_DBLP())
    graph.freeze_search_results(
        job,
        [
            {"catalog_paper_id": "p-z", "final_score": 0.9, "retrieval_score": 0.5},
            {"catalog_paper_id": "p-failed", "final_score": 99, "retrieval_score": 99},
            {"catalog_paper_id": "p-a", "final_score": 0.9, "retrieval_score": 0.5},
            {"catalog_paper_id": "p-new", "final_score": 0.8, "retrieval_score": 0.8},
        ],
        degraded=False,
        source_results=({"status": "completed"}, {"status": "completed"}),
    )
    rows = store.get_search_results_page("search-2", 1, page_size=10)
    assert [(row.catalog_paper_id, row.rank) for row in rows] == [
        ("p-z", 1), ("p-a", 2), ("p-new", 3),
    ]


def test_merge_catalog_metadata_accumulates_fields_across_multiple_duplicates():
    base = CatalogPaper(
        "official", "usenix-security", 2024, "Same Paper", "same paper",
        authors=["Ada"], abstract=None, keywords=[], publication_stage="accepted",
    )
    first = CatalogPaper(
        "dblp-a", "usenix-security", 2024, "Same Paper", "same paper",
        abstract="abstract from first duplicate", keywords=[], publication_stage="published",
    )
    second = CatalogPaper(
        "dblp-b", "usenix-security", 2024, "Same Paper", "same paper",
        abstract=None, keywords=["security"], publication_stage="published",
    )

    class MergeStore:
        def __init__(self):
            self.merged = None

        def list_catalog_papers(self, *_args, **_kwargs):
            return [base, first, second]

        def get_catalog_source_kinds(self, paper_id):
            return ["usenix"] if paper_id == "official" else ["dblp"]

        def merge_catalog_paper(self, canonical, duplicate_ids):
            self.merged = (canonical, duplicate_ids)

    store = MergeStore()
    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=_DBLP())
    graph._merge_existing_catalog_duplicates(_job("merge-duplicates"))

    assert store.merged is not None
    canonical, duplicate_ids = store.merged
    assert canonical.abstract == "abstract from first duplicate"
    assert canonical.keywords == ["security"]
    assert duplicate_ids == ["dblp-a", "dblp-b"]


def test_merge_catalog_duplicates_links_doi_row_to_no_doi_usenix_title_row():
    official = CatalogPaper(
        "official-no-doi", "usenix-security", 2024, "Same Paper", "same paper",
        authors=["Ada"], abstract="official abstract", publication_stage="accepted",
    )
    dblp = CatalogPaper(
        "dblp-with-doi", "usenix-security", 2024, "Same Paper", "same paper",
        authors=["Ada"], abstract="dblp abstract", doi="10.1000/same-paper",
        dblp_key="conf/uss/same", publication_stage="published",
    )

    class MergeStore:
        def __init__(self):
            self.merged = None

        def list_catalog_papers(self, *_args, **_kwargs):
            return [official, dblp]

        def get_catalog_source_kinds(self, paper_id):
            return ["usenix"] if paper_id == official.catalog_paper_id else ["dblp"]

        def merge_catalog_paper(self, canonical, duplicate_ids):
            self.merged = (canonical, duplicate_ids)

    store = MergeStore()
    graph = CatalogSearchGraph(store=store, accepted_source=_Accepted(), dblp_source=_DBLP())
    graph._merge_existing_catalog_duplicates(_job("merge-doi-title"))

    canonical, duplicate_ids = store.merged
    assert canonical.catalog_paper_id == official.catalog_paper_id
    assert canonical.doi == "10.1000/same-paper"
    assert canonical.abstract == "official abstract"
    assert duplicate_ids == [dblp.catalog_paper_id]


def test_search_event_payload_is_allowlisted_and_sanitized(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    store.create_search_job(_job("search-3"))
    store.append_search_event(SearchEvent(
        0, "search-3", "sync_dblp", "dblp", "SOURCE_FAILED", "failed",
        {
            "unit_id": "https://evil.example/?token=secret",
            "source_kind": "dblp",
            "count": "-4",
            "error_code": "ValueError: secret details",
            "message_code": "SOURCE_FAILED",
            "page": "https://evil.example/page",
            "exception": "ValueError: secret details",
        },
    ))
    payload = store.get_search_events("search-3")[0].safe_payload
    assert payload == {
        "source_kind": "dblp", "count": 0,
        "error_code": "SEARCH_WORKFLOW_FAILED", "message_code": "SOURCE_FAILED",
    }


def test_reset_running_jobs_preserves_integer_api_and_exposes_ids(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    store.create_search_job(_job("running-1", status="running"))
    store.create_search_job(_job("running-2", status="running"))
    assert reset_running_jobs(store) == 2
    assert reset_running_jobs(store, return_search_ids=True) == []

    store.create_search_job(_job("running-3", status="running"))
    assert reset_running_job_ids(store) == ["running-3"]
    assert store.get_search_job("running-3").status == "queued"
