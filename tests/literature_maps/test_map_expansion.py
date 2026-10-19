import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_literature_maps
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.models import MapEdge, MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SemanticScholarGraphPage,
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)


class PreviewClient:
    def batch(self, identifiers, *, fields=None):
        return SemanticScholarRequestResult(
            payload={
                "data": [
                    {
                        "paperId": identifier,
                        "title": "A refreshed paper",
                        "authors": [{"name": "Author"}],
                        "year": 2024,
                    }
                    for identifier in identifiers
                ]
            }
        )

    def search_relevance(self, query, *, limit=20, fields=None):
        return SemanticScholarRequestResult(
            payload={
                "data": [
                    {
                        "paperId": "s2-new",
                        "title": "A new paper",
                        "authors": [{"name": "Author"}],
                        "year": 2024,
                    }
                ]
            }
        )

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        return SemanticScholarRequestResult(
            graph_page=SemanticScholarGraphPage(
                relation,
                paper_id,
                (SemanticScholarMetadata("s2-ref", "A cited paper", ("Author",), 2023),),
                0,
                None,
                1,
            )
        )


class RefreshBudgetClient:
    def __init__(self):
        self.batch_calls = 0
        self.graph_calls = 0

    def batch(self, identifiers, *, fields=None):
        self.batch_calls += 1
        return SemanticScholarRequestResult(
            payload={
                "data": [
                    {"paperId": identifier, "title": f"Refreshed {identifier}", "year": 2024}
                    for identifier in identifiers
                ]
            }
        )

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        self.graph_calls += 1
        return SemanticScholarRequestResult(
            graph_page=SemanticScholarGraphPage(relation, paper_id, (), 0, None, 0)
        )


class RefreshApplyClient:
    def __init__(self, *, missing_fields: bool = False, empty_graph: bool = False):
        self.missing_fields = missing_fields
        self.empty_graph = empty_graph

    def batch(self, identifiers, *, fields=None):
        data = []
        for identifier in identifiers:
            row = {
                "paperId": identifier,
                "title": "Source refreshed" if identifier == "s2-source" else "Target refreshed",
                "authors": [{"name": "New Author"}],
                "year": 2024,
                "abstract": "New abstract",
                "venue": "New Venue",
                "citationCount": 99,
            }
            if self.missing_fields:
                row.update({"authors": [], "year": None, "abstract": None, "venue": "", "citationCount": None})
            data.append(row)
        return SemanticScholarRequestResult(payload={"data": data})

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        items = ()
        if not self.empty_graph and paper_id == "s2-source":
            items = (SemanticScholarMetadata("s2-target", "Target", ("Author",), 2023),)
        return SemanticScholarRequestResult(
            graph_page=SemanticScholarGraphPage(relation, paper_id, items, 0, None, len(items))
        )


def _service(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    return store, LiteratureMapService(store=store, client=PreviewClient(), executor=None)


def test_topic_preview_is_persistent_and_apply_adds_only_selected_candidates(tmp_path):
    store, service = _service(tmp_path)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)

    preview = service.create_preview(
        item.map_id,
        "owner-a",
        kind="topic",
        query="fuzzing",
        idempotency_key="preview-1",
    )
    assert preview.status == "completed"
    assert store.list_nodes(item.map_id, "owner-a") == []
    assert preview.candidates[0]["already_present"] is False

    applied = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[preview.candidates[0]["candidate_id"]],
        idempotency_key="apply-1",
    )
    assert len(applied["added_node_ids"]) == 1
    assert len(store.list_nodes(item.map_id, "owner-a")) == 1
    repeated = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[preview.candidates[0]["candidate_id"]],
        idempotency_key="apply-1",
    )
    assert repeated["added_node_ids"] == applied["added_node_ids"]
    assert len(store.list_nodes(item.map_id, "owner-a")) == 1


def test_remove_restore_uses_tombstone_and_revision_cas(tmp_path):
    store, service = _service(tmp_path)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    preview = service.create_preview(item.map_id, "owner-a", kind="topic", idempotency_key="p")
    candidate_id = preview.candidates[0]["candidate_id"]
    applied = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[candidate_id],
        idempotency_key="a",
    )
    node_id = applied["added_node_ids"][0]
    removed = service.remove_node(item.map_id, node_id, "owner-a", expected_revision=1, idempotency_key="r")
    assert removed["map"]["revision"] == 2
    assert store.get_node(item.map_id, node_id, "owner-a").removed is True
    restored = service.restore_node(item.map_id, node_id, "owner-a", expected_revision=2, idempotency_key="rr")
    assert restored["map"]["revision"] == 3
    assert restored["job"]["operation"] == "restore"
    assert store.get_node(item.map_id, node_id, "owner-a").removed is False


def test_restore_does_not_recreate_edge_until_both_tombstoned_nodes_are_active(tmp_path):
    store, service = _service(tmp_path)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    source = MapPaper.new(item.map_id, semantic_scholar_id="s2-source", title="Source")
    target = MapPaper.new(item.map_id, semantic_scholar_id="s2-target", title="Target")
    store.add_nodes(item.map_id, "owner-a", [source, target])
    store.add_edges(item.map_id, "owner-a", [MapEdge.new(item.map_id, "citation", source.node_id, target.node_id)])

    service.remove_node(item.map_id, source.node_id, "owner-a", expected_revision=0)
    service.remove_node(item.map_id, target.node_id, "owner-a", expected_revision=1)
    service.restore_node(item.map_id, source.node_id, "owner-a", expected_revision=2)
    assert store.list_edges(item.map_id, "owner-a") == []

    service.restore_node(item.map_id, target.node_id, "owner-a", expected_revision=3)
    edges = store.list_edges(item.map_id, "owner-a")
    assert [(edge.source_id, edge.target_id) for edge in edges] == [(source.node_id, target.node_id)]


def test_deleting_map_with_preview_removes_preview_children_before_jobs(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    preview, job, _ = store.create_preview(
        item.map_id,
        "owner-a",
        kind="topic",
        base_revision=0,
        candidates=[],
        status="queued",
        idempotency_key="queued-preview",
        params_hash="queued-preview-hash",
    )

    assert store.delete_map(item.map_id, "owner-a") is True
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM literature_map_previews WHERE map_id=?", (item.map_id,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM literature_map_jobs WHERE map_id=?", (item.map_id,)).fetchone()[0] == 0
    assert preview.job_id == job.job_id


def test_refresh_preview_counts_batch_and_graph_calls_against_one_persistent_budget(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = RefreshBudgetClient()
    service = LiteratureMapService(store=store, client=client, executor=None)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    nodes = [
        MapPaper.new(item.map_id, semantic_scholar_id=f"s2-{index}", title=f"Paper {index}")
        for index in range(60)
    ]
    store.add_nodes(item.map_id, "owner-a", nodes)

    preview = service.create_preview(item.map_id, "owner-a", kind="refresh", idempotency_key="budget")
    _, job = service.get_preview(item.map_id, preview.preview_id, "owner-a")

    assert client.batch_calls == 1
    assert client.graph_calls == 59
    assert job.counts["provider_request_count"] == 60
    assert "MAP_GRAPH_BUDGET_EXCEEDED" in preview.warnings


def test_reference_preview_apply_preserves_citation_direction(tmp_path):
    store, service = _service(tmp_path)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    source = MapPaper.new(item.map_id, semantic_scholar_id="s2-source", title="Source paper")
    store.add_nodes(item.map_id, "owner-a", [source])
    preview = service.create_preview(item.map_id, "owner-a", kind="references", node_id=source.node_id, idempotency_key="p")
    applied = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[preview.candidates[0]["candidate_id"]],
        idempotency_key="a",
    )
    nodes = store.list_nodes(item.map_id, "owner-a")
    target = next(node for node in nodes if node.node_id != source.node_id)
    edge = next(edge for edge in store.list_edges(item.map_id, "owner-a") if edge.kind == "citation")
    assert edge.source_id == source.node_id
    assert edge.target_id == target.node_id
    assert applied["map"]["revision"] == 1


def test_preview_http_contract_round_trips_persisted_job_and_cas_apply(tmp_path):
    store, service = _service(tmp_path)
    item = store.create_map(routes_literature_maps.OWNER_ID, topic="fuzzing", requested_count=20)
    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=service):
        client = TestClient(app)
        response = client.post(f"/api/literature-maps/{item.map_id}/previews", json={"kind": "topic", "idempotency_key": "p"})
        assert response.status_code == 202
        body = response.json()
        assert body["preview"]["status"] == "completed"
        preview_id = body["preview_id"]
        fetched = client.get(f"/api/literature-maps/{item.map_id}/previews/{preview_id}")
        assert fetched.status_code == 200
        candidate_id = fetched.json()["preview"]["candidates"][0]["candidate_id"]
        applied = client.post(
            f"/api/literature-maps/{item.map_id}/previews/{preview_id}/apply",
            json={"expected_revision": 0, "selected_candidate_ids": [candidate_id], "idempotency_key": "a"},
        )
    assert applied.status_code == 202
    assert applied.json()["map"]["revision"] == 1


def test_refresh_http_empty_apply_updates_metadata_and_survives_reopen(tmp_path):
    db_path = tmp_path / "maps.sqlite3"
    store = LiteratureMapStore(db_path)
    service = LiteratureMapService(store=store, client=RefreshApplyClient(), executor=None)
    item = store.create_map(routes_literature_maps.OWNER_ID, topic="fuzzing", requested_count=20)
    source = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-source",
        title="Source old",
        abstract="Old abstract",
        citation_count=10,
        document_id="doc-source",
        download_status="indexed",
        position={"x": 5, "y": 6},
        group_id="manual-group",
        provenance={"import_diagnostics": {"error_code": "RETRYABLE"}},
    )
    target = MapPaper.new(item.map_id, semantic_scholar_id="s2-target", title="Target old")
    store.add_nodes(item.map_id, routes_literature_maps.OWNER_ID, [source, target])

    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=service):
        client = TestClient(app)
        preview_response = client.post(
            f"/api/literature-maps/{item.map_id}/previews",
            json={"kind": "refresh", "idempotency_key": "http-refresh"},
        )
        assert preview_response.status_code == 202
        preview_id = preview_response.json()["preview_id"]
        apply_payload = {"expected_revision": 0, "selected_candidate_ids": [], "idempotency_key": "http-refresh-apply"}
        applied = client.post(f"/api/literature-maps/{item.map_id}/previews/{preview_id}/apply", json=apply_payload)
        assert applied.status_code == 202
        assert applied.json()["map"]["revision"] == 1
        repeated = client.post(f"/api/literature-maps/{item.map_id}/previews/{preview_id}/apply", json=apply_payload)
        assert repeated.status_code == 202
        assert repeated.json() == applied.json()
        stale = client.post(
            f"/api/literature-maps/{item.map_id}/previews/{preview_id}/apply",
            json={"expected_revision": 0, "selected_candidate_ids": [], "idempotency_key": "http-refresh-stale"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "MAP_CONFLICT"
        node_response = client.get(f"/api/literature-maps/{item.map_id}/nodes/{source.node_id}")
        assert node_response.status_code == 200
        assert node_response.json()["node"]["title"] == "Source refreshed"
        assert node_response.json()["node"]["abstract"] == "New abstract"

    reopened = LiteratureMapStore(db_path)
    persisted_map = reopened.get_map(item.map_id, routes_literature_maps.OWNER_ID)
    persisted_node = reopened.get_node(item.map_id, source.node_id, routes_literature_maps.OWNER_ID)
    assert persisted_map is not None and persisted_map.revision == 1
    assert persisted_node is not None
    assert persisted_node.title == "Source refreshed"
    assert persisted_node.abstract == "New abstract"
    assert persisted_node.document_id == "doc-source"
    assert persisted_node.download_status == "indexed"
    assert persisted_node.position == {"x": 5, "y": 6}
    assert persisted_node.group_id == "manual-group"
    assert persisted_node.provenance == source.provenance
    assert [(edge.source_id, edge.target_id) for edge in reopened.list_edges(item.map_id, routes_literature_maps.OWNER_ID)] == [(source.node_id, target.node_id)]


def test_refresh_preview_records_provider_metadata_diff_and_preserves_layout_and_import_state(tmp_path):
    store, service = _service(tmp_path)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-refresh",
        title="Old title",
        authors=("Author",),
        year=2020,
        position={"x": 10, "y": 20},
        group_id="manual-group",
        document_id="doc-1",
        download_status="indexed",
    )
    store.add_nodes(item.map_id, "owner-a", [node])
    preview = service.create_preview(item.map_id, "owner-a", kind="refresh", idempotency_key="refresh")
    assert preview.diff[0]["changes"]["title"] == {"from": "Old title", "to": "A refreshed paper"}
    result = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[preview.candidates[0]["candidate_id"]],
        idempotency_key="refresh-apply",
    )
    assert result["map"]["revision"] == 1
    refreshed = store.get_node(item.map_id, node.node_id, "owner-a")
    assert refreshed is not None
    assert refreshed.title == "A refreshed paper"
    assert refreshed.position == {"x": 10, "y": 20}
    assert refreshed.group_id == "manual-group"
    assert refreshed.document_id == "doc-1"
    assert refreshed.download_status == "indexed"


def test_empty_refresh_apply_persists_all_server_diffs_and_relations_after_reopen(tmp_path):
    db_path = tmp_path / "maps.sqlite3"
    store = LiteratureMapStore(db_path)
    service = LiteratureMapService(store=store, client=RefreshApplyClient(), executor=None)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    source = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-source",
        title="Source old",
        authors=("Old Author",),
        year=2020,
        venue="Old Venue",
        abstract="Old abstract",
        keywords=("keep",),
        citation_count=10,
        source_url="https://papers.example/source",
        provenance={"import_diagnostics": {"error_code": "RETRYABLE"}, "keep": "yes"},
        catalog_paper_id="catalog-source",
        document_id="doc-source",
        download_status="indexed",
        position={"x": 10, "y": 20},
        group_id="manual-group",
    )
    target = MapPaper.new(item.map_id, semantic_scholar_id="s2-target", title="Target old")
    store.add_nodes(item.map_id, "owner-a", [source, target])

    preview = service.create_preview(item.map_id, "owner-a", kind="refresh", idempotency_key="refresh-all")
    assert any(change["node_id"] == source.node_id for change in preview.diff)
    assert any(change["changes"].get("relations", {}).get("added") for change in preview.diff)

    applied = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[],
        idempotency_key="refresh-all-apply",
    )
    assert applied["map"]["revision"] == 1
    assert applied["job"]["counts"]["updated_count"] >= 1
    assert applied["job"]["counts"]["relation_count"] >= 1
    refreshed = store.get_node(item.map_id, source.node_id, "owner-a")
    assert refreshed is not None
    assert refreshed.title == "Source refreshed"
    assert refreshed.abstract == "New abstract"
    assert refreshed.citation_count == 99
    assert refreshed.external_ids == source.external_ids
    assert refreshed.source_url == source.source_url
    assert refreshed.provenance == source.provenance
    assert refreshed.catalog_paper_id == source.catalog_paper_id
    assert refreshed.document_id == source.document_id
    assert refreshed.download_status == source.download_status
    assert refreshed.position == source.position
    assert refreshed.group_id == source.group_id
    assert [(edge.source_id, edge.target_id) for edge in store.list_edges(item.map_id, "owner-a")] == [(source.node_id, target.node_id)]

    reopened = LiteratureMapStore(db_path)
    persisted = reopened.get_node(item.map_id, source.node_id, "owner-a")
    assert persisted is not None
    assert persisted.title == "Source refreshed"
    assert persisted.abstract == "New abstract"
    assert persisted.provenance == source.provenance
    assert [(edge.source_id, edge.target_id) for edge in reopened.list_edges(item.map_id, "owner-a")] == [(source.node_id, target.node_id)]

    repeated = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[],
        idempotency_key="refresh-all-apply",
    )
    assert repeated == applied
    assert reopened.get_map(item.map_id, "owner-a").revision == 1


def test_refresh_apply_preserves_existing_values_when_provider_omits_fields_or_edges(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, client=RefreshApplyClient(missing_fields=True, empty_graph=True), executor=None)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    source = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-source",
        title="Source changed",
        authors=("Keep Author",),
        year=2020,
        venue="Keep Venue",
        abstract="Keep abstract",
        citation_count=10,
        source_url="https://papers.example/source",
        provenance={"import_diagnostics": {"resolver_code": "RETRYABLE"}},
    )
    target = MapPaper.new(item.map_id, semantic_scholar_id="s2-target", title="Target")
    store.add_nodes(item.map_id, "owner-a", [source, target])
    store.add_edges(item.map_id, "owner-a", [MapEdge.new(item.map_id, "citation", source.node_id, target.node_id)])

    preview = service.create_preview(item.map_id, "owner-a", kind="refresh", idempotency_key="missing-fields")
    applied = service.apply_preview(
        item.map_id,
        preview.preview_id,
        "owner-a",
        expected_revision=0,
        selected_candidate_ids=[],
        idempotency_key="missing-fields-apply",
    )
    assert applied["map"]["revision"] == 1
    refreshed = store.get_node(item.map_id, source.node_id, "owner-a")
    assert refreshed is not None
    assert refreshed.title == "Source refreshed"
    assert refreshed.authors == source.authors
    assert refreshed.year == source.year
    assert refreshed.venue == source.venue
    assert refreshed.abstract == source.abstract
    assert refreshed.citation_count == source.citation_count
    assert [(edge.source_id, edge.target_id) for edge in store.list_edges(item.map_id, "owner-a")] == [(source.node_id, target.node_id)]


def test_refresh_apply_rejects_stale_empty_selection_without_writing(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, client=RefreshApplyClient(), executor=None)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    source = MapPaper.new(item.map_id, semantic_scholar_id="s2-source", title="Source old")
    target = MapPaper.new(item.map_id, semantic_scholar_id="s2-target", title="Target old")
    store.add_nodes(item.map_id, "owner-a", [source, target])
    preview = service.create_preview(item.map_id, "owner-a", kind="refresh", idempotency_key="stale-refresh")
    service.apply_preview(item.map_id, preview.preview_id, "owner-a", expected_revision=0, selected_candidate_ids=[], idempotency_key="stale-apply")
    current = store.get_node(item.map_id, source.node_id, "owner-a")
    assert current is not None
    with pytest.raises(ValueError, match="revision conflict"):
        service.apply_preview(item.map_id, preview.preview_id, "owner-a", expected_revision=0, selected_candidate_ids=[], idempotency_key="stale-replay")
    assert store.get_map(item.map_id, "owner-a").revision == 1
    assert store.get_node(item.map_id, source.node_id, "owner-a").title == current.title


def test_preview_uses_durable_queued_job_with_executor_and_can_be_recovered(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        service = LiteratureMapService(store=store, client=PreviewClient(), executor=executor)
        queued = service.create_preview(item.map_id, "owner-a", kind="topic", idempotency_key="queued")
        assert queued.status == "queued"
        for _ in range(50):
            preview, job = service.get_preview(item.map_id, queued.preview_id, "owner-a")
            if preview.status == "completed":
                break
            time.sleep(0.01)
        assert preview.status == "completed"
        assert job.status == "completed"
        assert preview.candidates
    finally:
        executor.shutdown(wait=True)

def test_recover_requeues_persisted_preview_without_repeating_map_mutation(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    preview, _, _ = store.create_preview(
        item.map_id,
        "owner-a",
        kind="topic",
        base_revision=0,
        candidates=[],
        node_id=None,
        query="fuzzing",
        status="queued",
        idempotency_key="persisted",
        params_hash="persisted-hash",
    )
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        service = LiteratureMapService(store=store, client=PreviewClient(), executor=executor)
        assert service.recover("owner-a") == 1
        for _ in range(50):
            recovered, job = service.get_preview(item.map_id, preview.preview_id, "owner-a")
            if recovered.status == "completed":
                break
            time.sleep(0.01)
        assert recovered.status == "completed"
        assert job.status == "completed"
    finally:
        executor.shutdown(wait=True)


def test_recover_reuses_completed_preview_checkpoint_without_provider_call(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    preview, job, _ = store.create_preview(
        item.map_id,
        "owner-a",
        kind="topic",
        base_revision=0,
        candidates=[],
        status="queued",
        idempotency_key="checkpointed",
        params_hash="checkpointed-hash",
    )
    assert store.claim_job(job.job_id, item.map_id, "owner-a") is not None
    candidate = {"candidate_id": "candidate-checkpoint", "identity_key": "semantic_scholar:s2-checkpoint", "title": "Checkpoint", "authors": [], "year": 2024, "external_ids": {"semantic_scholar": "s2-checkpoint"}, "already_present": False, "removed": False}
    store.save_unit_checkpoint(job.job_id, item.map_id, "owner-a", unit_key="preview:calculate", status="completed", payload={"candidates": [candidate], "diff": [], "warnings": []})
    client = PreviewClient()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        service = LiteratureMapService(store=store, client=client, executor=executor)
        assert service.recover("owner-a") == 1
        for _ in range(50):
            recovered, final_job = service.get_preview(item.map_id, preview.preview_id, "owner-a")
            if recovered.status == "completed":
                break
            time.sleep(0.01)
        assert recovered.candidates == [candidate]
        assert final_job.status == "completed"
    finally:
        executor.shutdown(wait=True)
