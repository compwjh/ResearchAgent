"""Spec029 Task06: durable catalog snapshot-handle bridge contracts."""

from __future__ import annotations

import json

from backend.app.api.routes_research import _task_summary
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.search_catalog_adapter import (
    CatalogSearchAdapter,
    SearchOutcome,
    SearchWorker,
)
from backend.app.research.domain.models import ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


def _task(task_id: str = "task-029-search") -> ResearchTask:
    return ResearchTask(
        research_task_id=task_id,
        owner_id="owner",
        conversation_id="conversation",
        goal="goal",
        language="en",
        quality_profile="balanced",
        review_plan_first=False,
        target_paper_count=1,
        soft_budget_seconds=60,
        status="running",
        current_plan_version=1,
        created_at="",
        updated_at="",
    )


def _search_item(task_id: str) -> ResearchWorkItem:
    return ResearchWorkItem(
        work_item_id="search-item",
        research_task_id=task_id,
        plan_version=1,
        task_type="search_catalog",
        role="search-worker",
        depends_on_json="[]",
        input_json=json.dumps({"query": "supply chain", "source": "usenix"}),
        status="queued",
        attempt=0,
        created_at="",
        updated_at="",
    )


def test_search_handle_is_durable_first_writer_wins_and_exposed_in_summary(tmp_path):
    path = tmp_path / "research.sqlite3"
    store = ResearchStore(path)
    task = store.create_task(_task())

    saved = store.set_task_search_id(task.research_task_id, "snapshot-1")
    retained = store.set_task_search_id(task.research_task_id, "snapshot-2")
    reopened = ResearchStore(path).get_task(task.research_task_id, "owner")

    assert saved.search_id == retained.search_id == reopened.search_id == "snapshot-1"
    assert _task_summary(reopened)["search_id"] == "snapshot-1"


def test_search_worker_carries_server_snapshot_handle_without_guessing_one():
    adapter = CatalogSearchAdapter(
        searcher=lambda _request: SearchOutcome(
            ("paper-1",), 1, False, None, search_id="snapshot-1"
        )
    )

    output = SearchWorker(adapter=adapter).run({"query": "supply chain", "work_item_id": "wi-1"})

    assert output["search_id"] == "snapshot-1"
    assert output["source_refs"] == ["search:snapshot-1"]

    invalid = SearchWorker(
        adapter=CatalogSearchAdapter(
            searcher=lambda _request: SearchOutcome(("paper-1",), 1, False, None, search_id="https://client.invalid")
        )
    ).run({"query": "supply chain", "work_item_id": "wi-1"})
    assert "search_id" not in invalid
    assert invalid["source_refs"] == ["search:wi-1"]


def test_orchestrator_persists_handle_and_emits_same_event_source(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = store.create_task(_task())
    item = store.create_work_items(task.research_task_id, [_search_item(task.research_task_id)])[0]
    adapter = CatalogSearchAdapter(
        searcher=lambda _request: SearchOutcome(
            ("paper-1",), 1, False, None, search_id="snapshot-1"
        )
    )

    paper_ids, error_code = Orchestrator(store=store, search_adapter=adapter)._run_search(
        task.research_task_id, item, "search-slot-1"
    )

    assert paper_ids == ["paper-1"]
    assert error_code is None
    assert store.get_task(task.research_task_id, "owner").search_id == "snapshot-1"
    completed = [
        json.loads(event.safe_payload_json)
        for event in store.list_events(task.research_task_id)
        if event.event_type == "worker" and json.loads(event.safe_payload_json).get("status") == "completed"
    ]
    assert completed and completed[-1]["search_id"] == "snapshot-1"


def test_local_catalog_hit_persists_importable_search_snapshot(tmp_path):
    discovery = PaperDiscoveryStore(tmp_path / "paper-search.sqlite3")
    discovery.upsert_catalog_paper(CatalogPaper(
        catalog_paper_id="catalog-local-1",
        conference_id="usenix-security",
        year=2026,
        title="Local catalog paper",
        normalized_title="local catalog paper",
        authors=["Author"],
        abstract="An indexed local paper.",
        official_page_url="https://www.usenix.org/paper/local",
        official_pdf_url="https://www.usenix.org/system/files/local.pdf",
        metadata_hash="metadata-hash",
        index_status="indexed",
    ))

    class _Rag:
        def retrieve_and_rerank(self, query, rows, **kwargs):
            return [{"catalog_paper_id": row.catalog_paper_id, "final_score": 1.0} for row in rows]

    outcome = CatalogSearchAdapter(store=discovery, rag=_Rag()).search(
        query="local", sources=("usenix",), max_results=1, years=(2026,)
    )

    assert outcome.search_id
    job = discovery.get_search_job(outcome.search_id)
    results = discovery.get_search_results(outcome.search_id)
    assert job is not None and job.status == "completed"
    assert [item.catalog_paper_id for item in results] == ["catalog-local-1"]
    assert results[0].snapshot["candidate_id"] == "catalog-local-1"
    assert results[0].snapshot["search_id"] == outcome.search_id
    assert results[0].snapshot["pdf_url"].endswith("local.pdf")
