from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_literature_maps
from backend.app.literature_maps.application.analysis import MapAnalysisService, _hash_source
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.models import MapEdge, MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SemanticScholarGraphPage,
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)


PAGINATION = {"version": 1, "page_size": 50, "max_candidates": 500}


class ExpansionGraphClient:
    def __init__(self, records_by_relation):
        self.records_by_relation = records_by_relation
        self.calls = []

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        self.calls.append((paper_id, relation, limit, offset))
        records = self.records_by_relation[relation]
        return SemanticScholarRequestResult(
            graph_page=SemanticScholarGraphPage(
                relation,
                paper_id,
                tuple(records),
                offset,
                None,
                len(records),
            )
        )


class FailedAfterFirstPageClient:
    def __init__(self):
        self.calls = 0

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        self.calls += 1
        if self.calls == 1:
            return SemanticScholarRequestResult(
                graph_page=SemanticScholarGraphPage(
                    relation,
                    paper_id,
                    (_paper("s2-before-page-failure"),),
                    offset,
                    50,
                    100,
                )
            )
        return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_RATE_LIMITED", retryable=True)


class RecordingExecutor:
    def __init__(self, store):
        self.store = store
        self.submissions = []

    def submit(self, function, *args, **kwargs):
        with self.store.connection() as db:
            assert db.execute(
                "SELECT 1 FROM literature_map_analyses WHERE map_id=?",
                (args[0],),
            ).fetchone() is not None
        self.submissions.append((function, args, kwargs))


def _paper(identifier: str, *, abstract: str | None = "A useful abstract"):
    return SemanticScholarMetadata(identifier, f"Paper {identifier}", abstract=abstract)


def _preview(store, service, map_id, seed, kind, items, key):
    preview = service.create_preview(
        map_id,
        "owner-a",
        kind=kind,
        node_id=seed.node_id,
        idempotency_key=key,
        pagination=PAGINATION,
    )
    current_job = service.run_preview_page(preview.job_id, "owner-a")
    assert current_job is not None and current_job.status == "completed"
    stored, _ = service.get_preview(map_id, preview.preview_id, "owner-a")
    assert {item["external_ids"]["semantic_scholar"] for item in stored.candidates} == {
        item.paper_id for item in items
    }
    return stored


def _setup(tmp_path, refs, cites):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    graph = ExpansionGraphClient({"references": refs, "citations": cites})
    service = LiteratureMapService(store=store, client=graph, executor=None)
    map_item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed", title="Seed")
    store.add_nodes(map_item.map_id, "owner-a", [seed])
    previews = {}
    for kind, records in (("references", refs), ("citations", cites)):
        if records is not None:
            previews[kind] = _preview(
                store,
                service,
                map_item.map_id,
                seed,
                kind,
                records,
                f"create-{kind}",
            )
    return store, service, map_item, seed, previews


def _selection(preview, *candidate_ids):
    return {
        "preview_id": preview.preview_id,
        "expected_preview_revision": preview.preview_revision,
        "selected_candidate_ids": list(candidate_ids),
    }


def test_batch_apply_deduplicates_across_directions_and_writes_both_edges_atomically(tmp_path):
    shared = _paper("s2-shared")
    store, service, map_item, seed, previews = _setup(tmp_path, [shared], [shared])
    ref_candidate = previews["references"].candidates[0]
    cite_candidate = previews["citations"].candidates[0]

    result = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="batch-shared",
        selections=[
            _selection(previews["references"], ref_candidate["candidate_id"]),
            _selection(previews["citations"], cite_candidate["candidate_id"]),
        ],
    )

    assert result["added_count"] == 1
    assert result["existing_count"] == 0
    assert result["revision"] == map_item.revision + 1
    assert len(result["node_ids"]) == 1
    nodes = {node.node_id: node for node in store.list_nodes(map_item.map_id, "owner-a")}
    added = nodes[result["node_ids"][0]]
    edges = store.list_edges(map_item.map_id, "owner-a")
    assert {(edge.source_id, edge.target_id) for edge in edges if edge.kind == "citation"} == {
        (seed.node_id, added.node_id),
        (added.node_id, seed.node_id),
    }
    assert result["batch_job_id"]
    batch = store.get_job(result["batch_job_id"], map_item.map_id, "owner-a")
    assert batch is not None and batch.operation == "expand_batch"
    assert batch.cursor["version"] == 1
    assert batch.cursor["seed_node_id"] == seed.node_id
    assert batch.cursor["new_node_ids"] == [added.node_id]
    assert batch.cursor["items"][added.node_id]["status"] == "analysis_queued"
    assert batch.cursor["items"][added.node_id]["analysis_id"]
    queue = store.get_analysis_queue(map_item.map_id, "owner-a")
    assert set(queue["counts"][key] for key in ("total",)) == {1}
    assert set(queue["counts"]["queued"] for _ in [0]) == {1}
    assert result["queue_job_id"] == queue["queue_job_id"]
    assert batch.cursor["items"][added.node_id]["source_version"] == _hash_source(
        {"title": added.title, "abstract": added.abstract or "", "external_ids": added.external_ids}
    )
    assert all(edge.kind != "similarity" for edge in edges)


def test_batch_apply_without_abstract_persists_metadata_pending_outbox(tmp_path):
    item = _paper("s2-no-abstract", abstract=None)
    store, service, map_item, seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    result = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="batch-metadata-pending",
        selections=[_selection(preview, preview.candidates[0]["candidate_id"])],
    )

    batch = store.get_job(result["batch_job_id"], map_item.map_id, "owner-a")
    assert batch is not None and batch.status == "queued"
    assert batch.step == "metadata"
    assert batch.cursor["items"][result["node_ids"][0]]["status"] == "metadata_pending"
    assert batch.cursor["items"][result["node_ids"][0]]["attempts"] == 0
    assert store.get_analysis_queue(map_item.map_id, "owner-a")["counts"]["total"] == 0
    assert len(service.client.calls) == 1


def test_batch_can_use_successful_candidates_while_another_page_is_failed(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = FailedAfterFirstPageClient()
    service = LiteratureMapService(store=store, client=client, executor=None)
    map_item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed", title="Seed")
    store.add_nodes(map_item.map_id, "owner-a", [seed])
    preview = service.create_preview(
        map_item.map_id,
        "owner-a",
        kind="references",
        node_id=seed.node_id,
        idempotency_key="failed-later-page-preview",
        pagination=PAGINATION,
    )
    assert service.run_preview_page(preview.job_id, "owner-a").status == "completed"
    ready, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    command = service.load_more_preview(
        map_item.map_id,
        preview.preview_id,
        "owner-a",
        expected_preview_revision=ready.preview_revision,
        retry_failed=False,
        idempotency_key="failed-later-page",
    )
    assert service.run_preview_page(command["job_id"], "owner-a").status == "failed"
    failed, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert failed.pagination["state"] == "failed"
    assert len(failed.candidates) == 1

    result = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="confirm-first-page",
        selections=[_selection(failed, failed.candidates[0]["candidate_id"])],
    )
    assert result["added_count"] == 1
    assert client.calls == 2


def test_batch_apply_idempotency_replays_before_stale_revision_and_rejects_changed_request(tmp_path):
    item = _paper("s2-idem")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    selection = _selection(preview, preview.candidates[0]["candidate_id"])
    first = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="batch-idem",
        selections=[selection],
    )
    replay = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="batch-idem",
        selections=[selection],
    )
    assert replay == first
    with store.connection() as db:
        batch_count = db.execute(
            "SELECT COUNT(*) FROM literature_map_jobs WHERE map_id=? AND operation='expand_batch'",
            (map_item.map_id,),
        ).fetchone()[0]
    assert batch_count == 1
    with pytest.raises(ValueError, match="MAP_IDEMPOTENCY_CONFLICT"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision + 1,
            idempotency_key="batch-idem",
            selections=[selection],
        )


def test_batch_apply_dispatches_new_abstract_queue_after_commit_and_replay_is_safe(tmp_path, monkeypatch):
    item = _paper("s2-dispatch")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    executor = RecordingExecutor(store)
    analysis = MapAnalysisService(store=store, queue_executor=executor)
    monkeypatch.setattr(
        analysis,
        "ensure_analysis_queue",
        lambda *_args, **_kwargs: pytest.fail("batch must not reconcile the full map queue"),
    )
    original_schedule = analysis._schedule_analysis_queue
    schedule_calls = []

    def record_schedule(map_id, owner_id, queue):
        schedule_calls.append((map_id, owner_id, queue["queue_job_id"]))
        return original_schedule(map_id, owner_id, queue)

    monkeypatch.setattr(analysis, "_schedule_analysis_queue", record_schedule)
    service.analysis_service = analysis
    request = {
        "expected_revision": map_item.revision,
        "idempotency_key": "batch-dispatch",
        "selections": [_selection(preview, preview.candidates[0]["candidate_id"])],
    }

    first = service.batch_apply_previews(map_item.map_id, "owner-a", **request)

    assert len(executor.submissions) == 1
    assert schedule_calls == [(map_item.map_id, "owner-a", first["queue_job_id"])]
    _function, args, _kwargs = executor.submissions[0]
    assert args == (map_item.map_id, "owner-a", first["queue_job_id"])
    assert store.get_analysis_queue(map_item.map_id, "owner-a")["counts"]["queued"] == 1
    assert service.batch_apply_previews(map_item.map_id, "owner-a", **request) == first
    assert len(schedule_calls) == 2
    assert len(executor.submissions) == 1
    assert len(store.list_analyses(map_item.map_id, first["node_ids"][0], "owner-a")) == 1


def test_batch_apply_does_not_dispatch_into_a_paused_analysis_queue(tmp_path):
    item = _paper("s2-dispatch-paused")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    executor = RecordingExecutor(store)
    analysis = MapAnalysisService(store=store, queue_executor=executor)
    analysis.ensure_analysis_queue(map_item.map_id, "owner-a", idempotency_key="initialize-paused-queue")
    analysis.pause_analysis_queue(map_item.map_id, "owner-a", idempotency_key="pause-before-expansion")
    service.analysis_service = analysis

    service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="batch-paused-queue",
        selections=[_selection(previews["references"], previews["references"].candidates[0]["candidate_id"])],
    )

    assert store.get_analysis_queue(map_item.map_id, "owner-a")["state"] == "paused"
    assert store.get_analysis_queue(map_item.map_id, "owner-a")["counts"]["queued"] == 1
    assert executor.submissions == []


def test_revalidate_updates_preview_base_and_revision_without_writing_graph(tmp_path):
    item = _paper("s2-revalidate")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    candidate = preview.candidates[0]
    before_nodes = store.list_nodes(map_item.map_id, "owner-a")
    before_edges = store.list_edges(map_item.map_id, "owner-a")
    store.update_map_details(map_item.map_id, "owner-a", expected_revision=map_item.revision, name="changed")

    result = service.revalidate_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision + 1,
        idempotency_key="revalidate-once",
        selections=[_selection(preview, candidate["candidate_id"])],
    )

    stored, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert result["revision"] == map_item.revision + 1
    assert stored.base_revision == result["revision"]
    assert stored.preview_revision == preview.preview_revision + 1
    assert result["invalid_selections"] == []
    assert store.list_nodes(map_item.map_id, "owner-a") == before_nodes
    assert store.list_edges(map_item.map_id, "owner-a") == before_edges


def test_revalidate_replays_before_revision_and_rejects_same_key_with_changed_expected_revision(tmp_path):
    item = _paper("s2-revalidate-idempotency")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    selection = _selection(preview, preview.candidates[0]["candidate_id"])
    first = service.revalidate_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="revalidate-replay",
        selections=[selection],
    )
    replay = service.revalidate_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="revalidate-replay",
        selections=[selection],
    )
    assert replay == first
    with pytest.raises(ValueError, match="MAP_IDEMPOTENCY_CONFLICT"):
        service.revalidate_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision + 1,
            idempotency_key="revalidate-replay",
            selections=[selection],
        )
    current, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert current.preview_revision == preview.preview_revision + 1


def test_batch_checks_owner_seed_direction_and_candidate_membership(tmp_path):
    ref_record = _paper("s2-ref-scope")
    cite_record = _paper("s2-cite-scope")
    store, service, map_item, seed, previews = _setup(tmp_path, [ref_record], [cite_record])
    ref = previews["references"]
    cite = previews["citations"]
    request = [
        _selection(ref, ref.candidates[0]["candidate_id"]),
        _selection(cite, cite.candidates[0]["candidate_id"]),
    ]
    with pytest.raises(LookupError):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-b",
            expected_revision=map_item.revision,
            idempotency_key="wrong-owner",
            selections=request,
        )
    with pytest.raises(ValueError, match="INVALID_PREVIEW_CANDIDATE"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision,
            idempotency_key="unknown-candidate",
            selections=[_selection(ref, "candidate-from-another-preview")],
        )

    second_seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed-2", title="Second seed")
    store.add_nodes(map_item.map_id, "owner-a", [second_seed])
    other_seed_citations = _preview(
        store,
        service,
        map_item.map_id,
        second_seed,
        "citations",
        [cite_record],
        "second-seed-citations",
    )
    with pytest.raises(ValueError, match="MAP_SEED_UNAVAILABLE"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision,
            idempotency_key="different-seeds",
            selections=[
                _selection(ref, ref.candidates[0]["candidate_id"]),
                _selection(other_seed_citations, other_seed_citations.candidates[0]["candidate_id"]),
            ],
        )

    second_refs = _preview(
        store,
        service,
        map_item.map_id,
        seed,
        "references",
        [ref_record],
        "second-references",
    )
    with pytest.raises(ValueError, match="PREVIEW_SELECTIONS_INVALID"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision,
            idempotency_key="duplicate-directions",
            selections=[
                _selection(ref, ref.candidates[0]["candidate_id"]),
                _selection(second_refs, second_refs.candidates[0]["candidate_id"]),
            ],
        )


def test_batch_rejects_tombstoned_identity_and_stale_map_revision(tmp_path):
    item = _paper("s2-tombstone")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    candidate = preview.candidates[0]
    tombstone = MapPaper.new(
        map_item.map_id,
        external_ids=candidate["external_ids"],
        title=candidate["title"],
    )
    store.add_nodes(map_item.map_id, "owner-a", [tombstone])
    current = store.get_map(map_item.map_id, "owner-a")
    assert current is not None
    store.remove_node(
        map_item.map_id,
        tombstone.node_id,
        "owner-a",
        expected_revision=current.revision,
    )
    live_revision = store.get_map(map_item.map_id, "owner-a").revision
    revalidated = service.revalidate_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=live_revision,
        idempotency_key="revalidate-tombstone",
        selections=[_selection(preview, candidate["candidate_id"])],
    )
    current_preview, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert revalidated["invalid_selections"][0]["reason"] == "MAP_NODE_REMOVED"
    with pytest.raises(ValueError, match="MAP_NODE_REMOVED"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=live_revision,
            idempotency_key="batch-tombstone",
            selections=[_selection(current_preview, candidate["candidate_id"])],
        )

    second_path = tmp_path / "second"
    second_path.mkdir()
    fresh_store, fresh_service, fresh_map, _fresh_seed, fresh_previews = _setup(second_path, [_paper("s2-stale")], None)
    fresh_preview = fresh_previews["references"]
    fresh_store.update_map_details(
        fresh_map.map_id,
        "owner-a",
        expected_revision=fresh_map.revision,
        name="new revision",
    )
    with pytest.raises(ValueError, match="MAP_PREVIEW_VERSION_CONFLICT|revision conflict"):
        fresh_service.batch_apply_previews(
            fresh_map.map_id,
            "owner-a",
            expected_revision=fresh_map.revision,
            idempotency_key="batch-stale",
            selections=[_selection(fresh_preview, fresh_preview.candidates[0]["candidate_id"])],
        )


def test_batch_transaction_rolls_back_nodes_edges_jobs_and_queue_on_late_failure(tmp_path, monkeypatch):
    item = _paper("s2-rollback")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    preview = previews["references"]
    before_nodes = store.list_nodes(map_item.map_id, "owner-a")
    before_edges = store.list_edges(map_item.map_id, "owner-a")

    executor = RecordingExecutor(store)
    service.analysis_service = MapAnalysisService(store=store, queue_executor=executor)
    original_append = store._append_event

    def fail_batch_event(db, job, *, event_type="progress", error_code=None):
        if event_type == "expansion_batch_queued":
            raise RuntimeError("forced event failure")
        return original_append(db, job, event_type=event_type, error_code=error_code)

    monkeypatch.setattr(store, "_append_event", fail_batch_event)
    with pytest.raises(RuntimeError, match="forced event failure"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision,
            idempotency_key="batch-rollback",
            selections=[_selection(preview, preview.candidates[0]["candidate_id"])],
        )
    assert store.list_nodes(map_item.map_id, "owner-a") == before_nodes
    assert store.list_edges(map_item.map_id, "owner-a") == before_edges
    assert store.get_analysis_queue(map_item.map_id, "owner-a")["counts"]["total"] == 0
    assert executor.submissions == []
    with store.connection() as db:
        batch_count = db.execute(
            "SELECT COUNT(*) FROM literature_map_jobs WHERE map_id=? AND operation='expand_batch'",
            (map_item.map_id,),
        ).fetchone()[0]
    assert batch_count == 0


def test_batch_appends_new_analysis_items_without_replacing_old_queue_items(tmp_path):
    new_record = _paper("s2-new-for-queue")
    old_record = _paper("s2-old", abstract="Old abstract")
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    graph = ExpansionGraphClient({"references": [new_record, old_record]})
    service = LiteratureMapService(store=store, client=graph, executor=None)
    map_item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed", title="Seed")
    old = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-old", title="Old", abstract="Old abstract")
    unused = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-unselected", title="Unselected", abstract="Unused")
    store.add_nodes(map_item.map_id, "owner-a", [seed, old, unused])
    store.ensure_analysis_queue(
        map_item.map_id,
        "owner-a",
        idempotency_key="old-queue",
        candidates=[
            {
                "node_id": old.node_id,
                "abstract_available": True,
                "source_version": "old-source-version",
                "model_id": "test-model",
                "idempotency_key": "old-analysis",
            }
        ],
    )
    preview = _preview(store, service, map_item.map_id, seed, "references", [new_record, old_record], "queue-new")
    ids = {candidate["external_ids"]["semantic_scholar"]: candidate["candidate_id"] for candidate in preview.candidates}
    result = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="queue-new-batch",
        selections=[_selection(preview, ids["s2-new-for-queue"], ids["s2-old"])],
    )

    with store.connection() as db:
        row = db.execute(
            "SELECT cursor_json FROM literature_map_jobs WHERE map_id=? AND operation='analysis_queue'",
            (map_item.map_id,),
        ).fetchone()
    items = json.loads(row["cursor_json"])["items"]
    assert set(items) == {old.node_id, result["node_ids"][0]}
    assert unused.node_id not in items
    assert items[old.node_id]["analysis_id"]


def test_existing_active_paper_is_counted_without_duplicate_node_or_analysis(tmp_path):
    record = _paper("s2-already-active", abstract=None)
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    graph = ExpansionGraphClient({"references": [record]})
    service = LiteratureMapService(store=store, client=graph, executor=None)
    map_item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed", title="Seed")
    existing = MapPaper.new(map_item.map_id, semantic_scholar_id=record.paper_id, title=record.title)
    store.add_nodes(map_item.map_id, "owner-a", [seed, existing])
    store.add_edges(map_item.map_id, "owner-a", [MapEdge.new(map_item.map_id, "citation", seed.node_id, existing.node_id)])
    preview = _preview(store, service, map_item.map_id, seed, "references", [record], "existing-preview")
    executor = RecordingExecutor(store)
    service.analysis_service = MapAnalysisService(store=store, queue_executor=executor)
    result = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="existing-only-batch",
        selections=[_selection(preview, preview.candidates[0]["candidate_id"])],
    )

    assert result["added_count"] == 0
    assert result["existing_count"] == 1
    assert result["revision"] == map_item.revision
    assert result["node_ids"] == []
    assert result["queue_job_id"] is None
    assert len(store.list_nodes(map_item.map_id, "owner-a")) == 2
    assert store.get_analysis_queue(map_item.map_id, "owner-a")["counts"]["total"] == 0
    assert executor.submissions == []


def test_batch_enforces_raw_and_unique_candidate_caps(tmp_path):
    twenty_one = [_paper(f"s2-raw-{index}") for index in range(21)]
    store, service, map_item, _seed, previews = _setup(tmp_path, twenty_one, None)
    preview = previews["references"]
    with pytest.raises(ValueError, match="PREVIEW_BATCH_LIMIT"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision,
            idempotency_key="raw-21",
            selections=[_selection(preview, *(candidate["candidate_id"] for candidate in preview.candidates))],
        )

    second_path = tmp_path / "second-unique"
    second_path.mkdir()
    refs = [_paper(f"s2-unique-ref-{index}") for index in range(11)]
    cites = [_paper(f"s2-unique-cite-{index}") for index in range(10)]
    store, service, map_item, _seed, previews = _setup(second_path, refs, cites)
    with pytest.raises(ValueError, match="PREVIEW_BATCH_LIMIT"):
        service.batch_apply_previews(
            map_item.map_id,
            "owner-a",
            expected_revision=map_item.revision,
            idempotency_key="unique-21",
            selections=[
                _selection(previews["references"], *(item["candidate_id"] for item in previews["references"].candidates)),
                _selection(previews["citations"], *(item["candidate_id"] for item in previews["citations"].candidates)),
            ],
        )


def test_batch_accepts_twenty_unique_candidates_shared_across_directions(tmp_path):
    shared = [_paper(f"s2-shared-{index}") for index in range(20)]
    store, service, map_item, _seed, previews = _setup(tmp_path, shared, shared)
    result = service.batch_apply_previews(
        map_item.map_id,
        "owner-a",
        expected_revision=map_item.revision,
        idempotency_key="twenty-shared",
        selections=[
            _selection(previews["references"], *(item["candidate_id"] for item in previews["references"].candidates)),
            _selection(previews["citations"], *(item["candidate_id"] for item in previews["citations"].candidates)),
        ],
    )
    assert result["added_count"] == 20
    assert len(result["node_ids"]) == 20
    assert result["revision"] == map_item.revision + 1
    citation_edges = [edge for edge in store.list_edges(map_item.map_id, "owner-a") if edge.kind == "citation"]
    assert len(citation_edges) == 40


@pytest.mark.parametrize(("active_count", "should_fail"), [(199, False), (200, True)])
def test_batch_respects_active_map_capacity(tmp_path, active_count, should_fail):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    graph = ExpansionGraphClient({"references": [_paper(f"s2-cap-{active_count}")]})
    service = LiteratureMapService(store=store, client=graph, executor=None)
    map_item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed", title="Seed")
    extra_nodes = [
        MapPaper.new(map_item.map_id, semantic_scholar_id=f"s2-existing-{index}", title=f"Existing {index}")
        for index in range(active_count - 1)
    ]
    store.add_nodes(map_item.map_id, "owner-a", [seed, *extra_nodes])
    map_item = store.update_map_details(map_item.map_id, "owner-a", expected_revision=0, name="capacity check")
    preview = _preview(store, service, map_item.map_id, seed, "references", [_paper(f"s2-cap-{active_count}")], f"cap-{active_count}")
    request = dict(
        expected_revision=map_item.revision,
        idempotency_key=f"cap-batch-{active_count}",
        selections=[_selection(preview, preview.candidates[0]["candidate_id"])],
    )
    if should_fail:
        with pytest.raises(ValueError, match="MAP_NODE_LIMIT"):
            service.batch_apply_previews(map_item.map_id, "owner-a", **request)
    else:
        result = service.batch_apply_previews(map_item.map_id, "owner-a", **request)
        assert result["added_count"] == 1
        assert len(store.list_nodes(map_item.map_id, "owner-a")) == 200


def test_expansion_command_payloads_reject_unknown_fields_boolean_revisions_and_duplicate_directions(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_literature_maps, "OWNER_ID", "owner-a")
    client = TestClient(app)
    valid_selection = {
        "preview_id": "preview-a",
        "expected_preview_revision": 1,
        "selected_candidate_ids": ["candidate-a"],
    }
    base = "/api/literature-maps/map-a/previews"
    invalid_payloads = [
        {
            "expected_revision": True,
            "idempotency_key": "key",
            "selections": [valid_selection],
        },
        {
            "expected_revision": 1,
            "idempotency_key": "key",
            "extra": "forbidden",
            "selections": [valid_selection],
        },
        {
            "expected_revision": 1,
            "idempotency_key": "key",
            "selections": [valid_selection, valid_selection],
        },
    ]
    for payload in invalid_payloads:
        assert client.post(f"{base}/batch-apply", json=payload).status_code == 422

    revalidate_payload = {
        "expected_revision": True,
        "idempotency_key": "key",
        "selections": [valid_selection],
    }
    assert client.post(f"{base}/revalidate", json=revalidate_payload).status_code == 422


def test_public_revalidate_and_batch_apply_routes_return_frozen_envelope(tmp_path, monkeypatch):
    item = _paper("s2-public-route")
    store, service, map_item, _seed, previews = _setup(tmp_path, [item], None)
    monkeypatch.setattr(routes_literature_maps, "OWNER_ID", "owner-a")
    monkeypatch.setattr(routes_literature_maps, "get_literature_map_service", lambda: service)
    client = TestClient(app)
    preview = previews["references"]
    base = f"/api/literature-maps/{map_item.map_id}/previews"
    revalidated = client.post(
        f"{base}/revalidate",
        json={
            "expected_revision": map_item.revision,
            "idempotency_key": "public-revalidate",
            "selections": [_selection(preview, preview.candidates[0]["candidate_id"])],
        },
    )
    assert revalidated.status_code == 200
    body = revalidated.json()
    assert body["schema_version"] == "literature-map-v1"
    new_preview_revision = body["previews"][0]["preview_revision"]
    batch = client.post(
        f"{base}/batch-apply",
        json={
            "expected_revision": map_item.revision,
            "idempotency_key": "public-batch",
            "selections": [
                {
                    "preview_id": preview.preview_id,
                    "expected_preview_revision": new_preview_revision,
                    "selected_candidate_ids": [preview.candidates[0]["candidate_id"]],
                }
            ],
        },
    )
    assert batch.status_code == 202
    assert batch.json()["added_count"] == 1
    assert batch.json()["batch_job_id"]
    assert store.get_map(map_item.map_id, "owner-a").revision == map_item.revision + 1

