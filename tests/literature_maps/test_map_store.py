from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.literature_maps.domain.models import MapEdge, MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore


def test_store_uses_wal_incremental_schema_and_owner_scoped_revision(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created = store.create_map("owner-a", topic="fuzzing", name="Fuzzing")
    assert store.schema_version >= 1
    assert store.journal_mode == "wal"
    assert created.revision == 0
    node = MapPaper.new(
        created.map_id,
        semantic_scholar_id="s2-a",
        title="A paper",
        authors=("A",),
    )
    store.add_nodes(created.map_id, "owner-a", [node])
    edge = MapEdge("edge", created.map_id, "citation", node.node_id, node.node_id)
    try:
        store.add_edges(created.map_id, "owner-a", [edge])
    except ValueError as error:
        assert "self" in str(error)
    else:
        raise AssertionError("self-loop should be rejected")
    assert store.get_map(created.map_id, "owner-b") is None
    assert store.update_view(created.map_id, "owner-a", expected_revision=0, positions=[], viewport=None, filters=None, layers=None).revision == 1


def test_store_delete_is_tombstone_for_jobs_and_does_not_recreate_map(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created = store.create_map("owner-a", topic="fuzzing", name="Fuzzing")
    job = store.create_job(created.map_id, "owner-a", operation="create")
    store.delete_map(created.map_id, "owner-a")
    assert store.get_map(created.map_id, "owner-a") is None
    assert store.job_can_write(job.job_id, created.map_id, "owner-a") is False
    assert store.get_job(job.job_id, created.map_id, "owner-a") is None
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM literature_map_jobs WHERE map_id=?", (created.map_id,)).fetchone()[0] == 0


def test_store_project_detach_is_owner_scoped(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    own = store.create_map("owner-a", topic="one", project_id="project")
    other = store.create_map("owner-b", topic="two", project_id="project")
    assert store.detach_project("project", "owner-a") == 1
    assert store.get_map(own.map_id, "owner-a").project_id is None
    assert store.get_map(other.map_id, "owner-b").project_id == "project"


def test_atomic_map_and_job_idempotency_allows_one_winner(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")

    def create():
        return store.create_map_with_job(
            "owner-a",
            topic="fuzzing",
            name="Fuzzing",
            idempotency_key="same-request",
            params_hash="params-v1",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert sum(result[2] for result in results) == 1
    assert len({result[0].map_id for result in results}) == 1
    assert len({result[1].job_id for result in results}) == 1
    with pytest.raises(ValueError, match="idempotency conflict"):
        store.create_map_with_job(
            "owner-a",
            topic="different",
            idempotency_key="same-request",
            params_hash="params-v2",
        )


def test_request_cache_only_reuses_successful_versioned_requests(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    key = store.request_cache_key(
        provider="semantic_scholar",
        operation="search",
        query="fuzzing",
        identifier="",
        filters={"year_start": 2020},
        page=0,
        fields=("title", "year"),
        version="literature-map-v1",
    )
    assert store.put_request_cache(key, {"data": []}, ttl_seconds=86400, status="success") is True
    assert store.get_request_cache(key) == {"data": []}
    failed_key = store.request_cache_key(provider="semantic_scholar", operation="references", identifier="s2-a", version="literature-map-v1")
    assert store.put_request_cache(failed_key, {"data": []}, status="failed") is False
    assert store.get_request_cache(failed_key) is None
    assert store.put_request_cache(key, {"data": ["expired"]}, ttl_seconds=0, status="success") is True
    assert store.get_request_cache(key) is None


def test_node_import_result_and_embedding_validation_are_scoped(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(created.map_id, semantic_scholar_id="s2-a", title="A paper")
    store.add_nodes(created.map_id, "owner-a", [node])
    updated = store.update_node_import_result(
        created.map_id,
        node.node_id,
        "owner-a",
        document_id="doc-1",
        download_status="indexed",
    )
    assert updated.document_id == "doc-1"
    assert updated.download_status == "indexed"
    with pytest.raises(LookupError):
        store.update_node_import_result(created.map_id, node.node_id, "owner-b", document_id="leak")
    with pytest.raises(ValueError, match="embedding"):
        store.put_embedding(model_version="m", basis="title", content_hash="nan", vector=[float("nan"), 1.0])
    with pytest.raises(ValueError, match="embedding"):
        store.put_embedding(model_version="m", basis="title", content_hash="zero", vector=[0.0, 0.0])
    with pytest.raises(ValueError, match="embedding"):
        store.put_embedding(model_version="m", basis="title", content_hash="empty", vector=[])


def test_node_import_diagnostics_are_provenance_scoped_and_cleared_on_success(tmp_path):
    database_path = tmp_path / "maps.sqlite3"
    store = LiteratureMapStore(database_path)
    created = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(
        created.map_id,
        semantic_scholar_id="s2-a",
        title="A paper",
        provenance={"provider": "semantic_scholar", "catalog_snapshot": {"catalog_paper_id": "catalog-1"}},
    )
    store.add_nodes(created.map_id, "owner-a", [node])

    failed = store.update_node_import_result(
        created.map_id,
        node.node_id,
        "owner-a",
        import_result={
            "status": "failed",
            "error_code": "PDF_NOT_FOUND",
            "resolver_code": "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
            "resolver_codes": ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"],
            "provider_exception": "https://secret.example/key=bad",
        },
    )
    assert failed.provenance["provider"] == "semantic_scholar"
    assert failed.provenance["catalog_snapshot"] == {"catalog_paper_id": "catalog-1"}
    assert failed.provenance["import_diagnostics"] == {
        "error_code": "PDF_NOT_FOUND",
        "resolver_code": "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
        "resolver_codes": ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"],
        "retryable": True,
    }
    assert "secret.example" not in str(failed.provenance)

    reopened = LiteratureMapStore(database_path)
    persisted = reopened.get_node(created.map_id, node.node_id, "owner-a")
    assert persisted is not None
    assert persisted.provenance["import_diagnostics"]["error_code"] == "PDF_NOT_FOUND"

    cleared = reopened.update_node_import_result(
        created.map_id,
        node.node_id,
        "owner-a",
        import_result={"status": "indexed", "document_id": "doc-1"},
    )
    assert cleared.document_id == "doc-1"
    assert "import_diagnostics" not in cleared.provenance
    assert cleared.provenance["catalog_snapshot"] == {"catalog_paper_id": "catalog-1"}

    reopened_again = LiteratureMapStore(database_path)
    persisted_again = reopened_again.get_node(created.map_id, node.node_id, "owner-a")
    assert persisted_again is not None
    assert "import_diagnostics" not in persisted_again.provenance


def test_legacy_duplicate_idempotency_bindings_are_migrated_deterministically(tmp_path):
    database_path = tmp_path / "maps.sqlite3"
    store = LiteratureMapStore(database_path)
    first_map = store.create_map("owner-a", topic="first")
    first_job = store.create_job(first_map.map_id, "owner-a", operation="create", idempotency_key="legacy", params_hash="params")
    store.bind_map_idempotency(first_map.map_id, "owner-a", "legacy", "params", first_job.job_id)
    second_map = store.create_map("owner-a", topic="second")
    second_job = store.create_job(second_map.map_id, "owner-a", operation="create", idempotency_key="legacy", params_hash="params")
    with store.connection() as db:
        db.execute("DROP INDEX idx_literature_map_idempotency_owner_key")
    store.bind_map_idempotency(second_map.map_id, "owner-a", "legacy", "params", second_job.job_id)

    reopened = LiteratureMapStore(database_path)
    with reopened.connection() as db:
        binding = db.execute("SELECT map_id,job_id FROM literature_map_idempotencies WHERE owner_id=? AND idempotency_key=?", ("owner-a", "legacy")).fetchone()
        assert binding["map_id"] == first_map.map_id
        assert binding["job_id"] == first_job.job_id
        assert db.execute("SELECT COUNT(*) FROM literature_maps WHERE owner_id=?", ("owner-a",)).fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM literature_map_jobs WHERE map_id IN (?,?)", (first_map.map_id, second_map.map_id)).fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM literature_map_idempotency_migration_log").fetchone()[0] == 1
