import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.knowledge_base.infrastructure.candidate_rebuild as candidate_rebuild_module
import backend.app.knowledge_base.infrastructure.manifest_store as manifest_store_module
from backend.app.knowledge_base import rebuild_index
from backend.app.knowledge_base.infrastructure.candidate_index import (
    CandidateIndexError,
    FakeQdrant,
    QdrantCandidateIndexPort,
)
from backend.app.knowledge_base.infrastructure.candidate_rebuild import (
    CandidateRebuildService,
    RebuildError,
    RunState,
    _ExclusiveLock,
    _RuntimeStore,
    topology_inventory,
)
from backend.app.knowledge_base.infrastructure.chunkers import build_chunks_v2
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore


def _fixture(tmp_path: Path, *, text: str = "# Title\n\nFirst paragraph.\n\nSecond paragraph."):
    papers = tmp_path / "papers"
    papers.mkdir(parents=True, exist_ok=True)
    source = papers / "doc.md"
    source.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = tmp_path / "papers.json"
    metadata.write_text(json.dumps([{
        "paper_id": "doc-1",
        "file_name": "doc.md",
        "stored_name": "doc.md",
        "media_type": "text/markdown",
        "source_sha256": digest,
    }]), encoding="utf-8")
    return papers, metadata


def _service(tmp_path: Path, qdrant: FakeQdrant, *, llm=lambda _prompt: "[]", finalizer=None, embedder=None):
    papers, metadata = _fixture(tmp_path)
    return CandidateRebuildService(
        metadata_path=metadata,
        papers_dir=papers,
        runtime_root=tmp_path / "runtime",
        index=qdrant,
        dense_dim=4,
        embedder=embedder or (lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]),
        llm=llm,
        finalizer=finalizer,
        run_id_factory=lambda: "run-test",
    )


def test_markdown_v2_preserves_null_page_coordinates():
    chunks, _ = build_chunks_v2([(None, "first paragraph\n\nsecond paragraph")], llm=lambda _prompt: "[]")
    assert chunks
    assert all(chunk.page is None and chunk.page_end is None for chunk in chunks)


def test_dry_run_has_no_write_side_effects(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    embed_calls = []
    service = _service(tmp_path, qdrant, embedder=lambda texts: embed_calls.append(list(texts)) or [])
    before = service.metadata_path.read_text(encoding="utf-8")
    result = service.run()
    write_ops = {"ensure_collection", "upsert_document", "delete_collection", "create_alias", "delete_alias"}
    assert result["status"] == "completed"
    assert result["dry_run"] is True
    assert not (tmp_path / "runtime").exists()
    assert not embed_calls
    assert not any(operation in write_ops for operation, _target in qdrant.calls)
    assert service.metadata_path.read_text(encoding="utf-8") == before


def test_build_validate_and_first_physical_switch(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    service = _service(tmp_path, qdrant)
    result = service.run(dry_run=False, confirm_replace=True)
    candidate = result["candidate_collection"]
    assert result["status"] == "completed"
    assert result["point_counts"]["v1"] > 0
    assert result["point_counts"]["v2"] > 0
    assert result["validation"]["status"] == "passed"
    assert qdrant.aliases == {"papers": candidate}
    assert "papers" not in qdrant.collections
    state = json.loads((tmp_path / "runtime" / "run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["new_fingerprint"]["validation_artifact_sha256"] == hashlib.sha256((tmp_path / "runtime" / "run-test" / "validation.json").read_bytes()).hexdigest()
    assert state["new_fingerprint"]["topology_artifact_sha256"] == hashlib.sha256((tmp_path / "runtime" / "run-test" / "topology.json").read_bytes()).hexdigest()
    points = qdrant.collections[candidate]
    assert all("document_id" in item.payload and "paper_id" not in item.payload for item in points)
    events = (tmp_path / "runtime" / "run-test" / "events.jsonl").read_text(encoding="utf-8")
    assert '"event":"intent"' in events and '"event":"observed"' in events


def test_default_finalize_publishes_generation_marker(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    result = _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)

    marker = FinalizeBundleStore(tmp_path).require_generation()
    bundle = json.loads((tmp_path / ".sdd" / "runtime" / "spec-018" / "rebuild" / "run-test" / "finalize" / "bundle.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert marker["run_id"] == "run-test"
    assert marker["alias_target"] == result["candidate_collection"]
    assert marker["bundle_sha256"] == bundle["bundle_sha256"]
    assert marker["collection_fingerprint"] == result["validation"]["collection_fingerprint"]


def test_default_finalize_marker_failure_enters_pending_and_resumes(tmp_path, monkeypatch):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    original_atomic_bytes = manifest_store_module._atomic_bytes

    def fail_marker(path, payload):
        if Path(path).name == "index-generation.json":
            raise manifest_store_module.ManifestStoreError(
                "ATOMIC_WRITE_FAILED", status=503
            )
        return original_atomic_bytes(path, payload)

    monkeypatch.setattr(manifest_store_module, "_atomic_bytes", fail_marker)
    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "ATOMIC_WRITE_FAILED"
    state = json.loads((tmp_path / "runtime" / "run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "finalize_pending"
    assert not (tmp_path / "data" / "kb" / "index-generation.json").exists()

    monkeypatch.setattr(manifest_store_module, "_atomic_bytes", original_atomic_bytes)
    result = _service(tmp_path, qdrant).resume_finalize("run-test")
    assert result["status"] == "completed"
    assert FinalizeBundleStore(tmp_path).require_generation()["run_id"] == "run-test"


def test_v2_rules_only_failure_cleans_candidate(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    service = _service(tmp_path, qdrant, llm=None)
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "V2_RULES_ONLY_LLM_NOT_USED"
    assert not qdrant.collections


def test_alias_switch_failure_preserves_validated_candidate(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    qdrant.inject_failure("create_alias", times=1)
    service = _service(tmp_path, qdrant)
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "INJECTED_FAILURE"
    assert any(name.startswith("papers_rebuild_") for name in qdrant.collections)
    state = json.loads((tmp_path / "runtime" / "run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "switching"


def test_alias_switch_failure_stages_finalize_bundle_for_new_service(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    qdrant.inject_failure("create_alias", times=1)
    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "INJECTED_FAILURE"
    bundle = FinalizeBundleStore(tmp_path).read_bundle("run-test")
    assert bundle["candidate_collection"] == "papers_rebuild_run-test"
    assert not (tmp_path / "data" / "kb").exists()

    result = _service(tmp_path, qdrant).resume_switch("run-test")
    assert result["status"] == "completed"
    assert FinalizeBundleStore(tmp_path).require_generation()["run_id"] == "run-test"


def test_finalize_pending_can_resume(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    service = _service(tmp_path, qdrant, finalizer=lambda _state: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "FINALIZE_FAILED"
    resumed = _service(tmp_path, qdrant, finalizer=lambda _state: None)
    result = resumed.resume_finalize("run-test")
    assert result["status"] == "completed"


def test_failed_cleanup_pending_can_be_retried(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.inject_failure("delete_collection", times=1)
    service = _service(tmp_path, qdrant, llm=None)
    with pytest.raises(RebuildError):
        service.run(dry_run=False, confirm_replace=True)
    state = json.loads((tmp_path / "runtime" / "run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "cleanup_pending"
    resumed = _service(tmp_path, qdrant, llm=None)
    result = resumed.cleanup_failed("run-test")
    assert result["status"] == "cleaned"


def test_empty_authoritative_metadata_does_not_create_candidate(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "orphan.pdf").write_bytes(b"orphan")
    metadata = tmp_path / "papers.json"
    metadata.write_text("[]", encoding="utf-8")
    qdrant = FakeQdrant()
    service = CandidateRebuildService(metadata_path=metadata, papers_dir=papers, runtime_root=tmp_path / "runtime", index=qdrant)
    with pytest.raises(RebuildError) as caught:
        service.run()
    assert caught.value.code == "NO_DOCUMENTS_TO_REBUILD"
    assert not qdrant.collections


def test_topology_inventory_fails_closed_for_multiple_candidates():
    qdrant = FakeQdrant()
    qdrant.seed_collection("papers_rebuild_a", dense_dim=4)
    qdrant.seed_collection("papers_rebuild_b", dense_dim=4)
    inventory = topology_inventory(qdrant)
    assert inventory["matrix"]["candidate_state"] == "ambiguous"
    assert inventory["matrix"]["safe_to_switch"] is False


def test_candidate_port_allowlist_rejects_current_after_binding(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    with pytest.raises(CandidateIndexError) as unbound:
        qdrant.ensure_collection("papers", dense_dim=4)
    assert unbound.value.code == "CANDIDATE_PORT_NOT_BOUND"
    with pytest.raises(CandidateIndexError) as unbound_delete:
        qdrant.delete_collection("papers")
    assert unbound_delete.value.code == "CANDIDATE_PORT_NOT_BOUND"
    qdrant.seed_collection("papers", dense_dim=4)
    capability = object()
    qdrant.bind_candidate("papers_rebuild_run", source_collection="papers", alias="papers", run_token="run-test", retire_capability=capability)
    with pytest.raises(CandidateIndexError):
        qdrant.ensure_collection("papers", dense_dim=4)
    with pytest.raises(CandidateIndexError):
        qdrant.delete_collection("papers")
    with pytest.raises(Exception) as caught:
        qdrant.upsert_document("papers", "doc", [])
    assert getattr(caught.value, "code", "") == "CANDIDATE_DESTINATION_FORBIDDEN"
    qdrant.authorize_retire("papers", run_token="run-test", expected_target="papers", capability=capability)
    qdrant.delete_collection("papers")


def test_destination_write_requires_explicit_temporary_collection_and_document_id():
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    capability = object()
    qdrant.bind_candidate(
        "papers_rebuild_run",
        source_collection="papers",
        alias="papers",
        run_token="run-test",
        retire_capability=capability,
    )
    point = candidate_rebuild_module.CandidatePoint(
        "point-1", {"dense": [1, 0, 0, 0], "sparse": {"indices": [1], "values": [1.0]}},
        {"document_id": "doc-1"},
    )
    with pytest.raises(CandidateIndexError) as current:
        qdrant.upsert_document("papers", "doc-1", [point])
    assert current.value.code == "CANDIDATE_DESTINATION_FORBIDDEN"
    qdrant.ensure_collection("papers_rebuild_run", dense_dim=4)
    qdrant.upsert_document("papers_rebuild_run", "doc-1", [point])
    assert qdrant.collections["papers"] == []
    assert qdrant.collections["papers_rebuild_run"][0].payload["document_id"] == "doc-1"


def test_candidate_rebuild_writes_only_candidate_and_keeps_metadata(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    papers, metadata = _fixture(tmp_path)
    before = metadata.read_bytes()
    service = CandidateRebuildService(
        metadata_path=metadata,
        papers_dir=papers,
        runtime_root=tmp_path / "runtime",
        index=qdrant,
        dense_dim=4,
        embedder=lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts],
        llm=lambda _prompt: "[]",
        run_id_factory=lambda: "destination-test",
    )
    result = service.run(dry_run=False, confirm_replace=True)
    writes = [(operation, target) for operation, target in qdrant.calls if operation in {"ensure_collection", "upsert_document"}]
    assert writes
    assert all(target.startswith("papers_rebuild_") for _operation, target in writes)
    assert metadata.read_bytes() == before
    assert result["candidate_collection"] == "papers_rebuild_destination-test"


def test_subsequent_alias_switch_removes_previous_collection(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("old", dense_dim=4)
    qdrant.aliases["papers"] = "old"
    service = _service(tmp_path, qdrant)
    result = service.run(dry_run=False, confirm_replace=True)
    assert qdrant.aliases["papers"] == result["candidate_collection"]
    assert "old" not in qdrant.collections


def test_post_success_alias_error_resume_removes_previous(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("old", dense_dim=4)
    qdrant.aliases["papers"] = "old"
    qdrant.inject_post_failure("create_alias")
    service = _service(tmp_path, qdrant)
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "INJECTED_POST_FAILURE"
    resumed = _service(tmp_path, qdrant)
    resumed.resume_switch("run-test")
    assert "old" not in qdrant.collections
    assert qdrant.aliases["papers"] == "papers_rebuild_run-test"
    validation = json.loads((tmp_path / "runtime" / "run-test" / "validation.json").read_text(encoding="utf-8"))
    commit = json.loads((tmp_path / "runtime" / "run-test" / "commit.json").read_text(encoding="utf-8"))
    assert commit["collection_fingerprint"] == validation["collection_fingerprint"]


def test_cleanup_rejects_alias_referenced_candidate(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.inject_failure("delete_collection", times=1)
    service = _service(tmp_path, qdrant, llm=None)
    with pytest.raises(RebuildError):
        service.run(dry_run=False, confirm_replace=True)
    candidate = "papers_rebuild_run-test"
    qdrant.aliases["other"] = candidate
    resumed = _service(tmp_path, qdrant, llm=None)
    with pytest.raises(RebuildError) as caught:
        resumed.cleanup_failed("run-test")
    assert caught.value.code == "INDEX_TOPOLOGY_AMBIGUOUS"
    assert candidate in qdrant.collections


def test_resume_finalize_accepts_finalizing_state(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    service = _service(tmp_path, qdrant, finalizer=lambda _state: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RebuildError):
        service.run(dry_run=False, confirm_replace=True)
    state_path = tmp_path / "runtime" / "run-test" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "finalizing"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    resumed = _service(tmp_path, qdrant, finalizer=lambda _state: None)
    assert resumed.resume_finalize("run-test")["status"] == "completed"


def test_lock_schema_and_explicit_stale_recovery(tmp_path):
    first = _ExclusiveLock(tmp_path, run_id="run-1", command="test")
    first.acquire()
    lock_data = json.loads((tmp_path / "rebuild.lock").read_text(encoding="utf-8"))
    assert {"schema_version", "run_id", "owner", "pid", "host", "token", "command", "started_at", "heartbeat_at"} <= set(lock_data)
    with pytest.raises(RebuildError) as caught:
        _ExclusiveLock(tmp_path, run_id="run-2", command="test", recover_stale_run_id="run-1", recovery_check=lambda _value: None).acquire()
    assert caught.value.code == "REBUILD_LOCK_AMBIGUOUS"
    first.release()


def test_cli_resume_requires_confirm_and_supports_injected_index(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    result = rebuild_index.main(["--resume-switch", "run-test", "--runtime-root", str(tmp_path / "runtime")], index=qdrant)
    assert result == 2
    assert rebuild_index.main(["--resume-switch", "run-test", "--recover-stale-lock", "other-run", "--confirm-replace"], index=qdrant) == 2


def test_two_concurrent_dry_runs_have_no_write_side_effects(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    services = [_service(tmp_path / name, qdrant) for name in ("one", "two")]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda service: service.run(), services))
    assert [result["status"] for result in results] == ["completed", "completed"]
    assert not any(operation in {"ensure_collection", "upsert_document", "delete_collection", "create_alias", "delete_alias"} for operation, _target in qdrant.calls)


def test_dry_run_fails_closed_when_lock_is_present(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    service = _service(tmp_path, qdrant)
    lock = _ExclusiveLock(tmp_path / "runtime", run_id="other-run", command="test")
    lock.acquire()
    try:
        with pytest.raises(RebuildError) as caught:
            service.run()
        assert caught.value.code == "PREFLIGHT_STALE"
    finally:
        lock.release()


def test_confirm_replace_fails_before_any_write_when_lock_is_held(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    service = _service(tmp_path, qdrant)
    lock = _ExclusiveLock(tmp_path / "runtime", run_id="other-run", command="test")
    lock.acquire()
    try:
        with pytest.raises(RebuildError) as caught:
            service.run(dry_run=False, confirm_replace=True)
        assert caught.value.code == "REBUILD_LOCK_HELD"
        assert not qdrant.collections
    finally:
        lock.release()


@pytest.mark.parametrize(
    "aliases",
    [
        [{"alias": "papers", "targets": []}],
        [{"alias": "papers", "targets": ["papers", "other"]}],
        [{"alias": "papers", "targets": ["missing"]}],
    ],
)
def test_malformed_alias_topology_fails_closed(aliases):
    class MalformedTopology(FakeQdrant):
        def collection_inventory(self):
            return {
                "collections": [
                    {"name": "papers", "kind": "physical", "exists": True, "point_count": 0, "vector_names": []},
                    {"name": "other", "kind": "physical", "exists": True, "point_count": 0, "vector_names": []},
                ],
                "aliases": aliases,
            }

    with pytest.raises(RebuildError) as caught:
        topology_inventory(MalformedTopology())
    assert caught.value.code == "INDEX_TOPOLOGY_AMBIGUOUS"


def test_alias_inventory_exception_fails_closed():
    class BrokenTopology(FakeQdrant):
        def collection_inventory(self):
            raise RuntimeError("qdrant unavailable")

    with pytest.raises(RebuildError) as caught:
        topology_inventory(BrokenTopology())
    assert caught.value.code == "INDEX_TOPOLOGY_AMBIGUOUS"


def test_non_finite_candidate_vector_is_rejected_by_validation(tmp_path):
    class MaliciousVector(FakeQdrant):
        def __init__(self):
            super().__init__(dense_dim=4)
            self.tampered = False

        def scroll_points(self, destination, *, offset=None, limit=256):
            points, next_offset = super().scroll_points(destination, offset=offset, limit=limit)
            if points and not self.tampered:
                points[0].vector["dense"][0] = float("nan")
                self.tampered = True
            return points, next_offset

    qdrant = MaliciousVector()
    service = _service(tmp_path, qdrant)
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "CANDIDATE_VALIDATION_FAILED"
    assert not qdrant.collections


@pytest.mark.parametrize("tamper", ["text", "dense", "anchor", "config"])
def test_candidate_payload_vector_and_config_tamper_is_rejected(tmp_path, tamper):
    class TamperedCandidate(FakeQdrant):
        def __init__(self):
            super().__init__(dense_dim=4)
            self.tampered = False

        def scroll_points(self, destination, *, offset=None, limit=256):
            points, next_offset = super().scroll_points(destination, offset=offset, limit=limit)
            if points and not self.tampered:
                point = points[0]
                if tamper == "text":
                    point.payload["text"] = str(point.payload["text"]) + " tampered"
                elif tamper == "dense":
                    point.vector["dense"][0] = float(point.vector["dense"][0]) + 1.0
                elif tamper == "anchor":
                    point.payload["anchor_digest"] = "0" * 64
                else:
                    point.payload["chunker_config_fingerprint"] = "0" * 64
                self.tampered = True
            return points, next_offset

    service = _service(tmp_path, TamperedCandidate())
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "CANDIDATE_VALIDATION_FAILED"


def test_malformed_sparse_dict_is_stable_candidate_validation_failure(tmp_path):
    class MalformedSparse(FakeQdrant):
        def __init__(self):
            super().__init__(dense_dim=4)
            self.tampered = False

        def scroll_points(self, destination, *, offset=None, limit=256):
            points, next_offset = super().scroll_points(destination, offset=offset, limit=limit)
            if points and not self.tampered:
                points[0].vector["sparse"] = {"indices": [2, 2, 1], "values": [0.1, float("nan"), 0.2]}
                self.tampered = True
            return points, next_offset

    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, MalformedSparse()).run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "CANDIDATE_VALIDATION_FAILED"


def test_resume_switch_rejects_tampered_validation_artifact(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("old", dense_dim=4)
    qdrant.aliases["papers"] = "old"
    qdrant.inject_post_failure("create_alias")
    with pytest.raises(RebuildError):
        _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)
    validation_path = tmp_path / "runtime" / "run-test" / "validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["collection_fingerprint"] = "0" * 64
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, qdrant).resume_switch("run-test")
    assert caught.value.code == "VALIDATION_ARTIFACT_MISMATCH"


def test_weak_port_without_retire_authorizer_fails_closed(tmp_path):
    class WeakPort(FakeQdrant):
        authorize_retire = None

    qdrant = WeakPort(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "CANDIDATE_RETIRE_AUTHORIZATION_REQUIRED"
    assert "papers" in qdrant.collections


def test_noop_retire_delete_fails_closed_before_finalize(tmp_path):
    class NoOpRetirePort(FakeQdrant):
        def authorize_retire(self, collection, *, run_token, expected_target, capability):
            # A malicious adapter can claim authorization without enforcing it.
            return None

        def delete_collection(self, destination):
            # It can also report success while leaving the target untouched.
            self.calls.append(("delete_collection", destination))

    finalizer_calls = []
    qdrant = NoOpRetirePort(dense_dim=4)
    qdrant.seed_collection("papers", dense_dim=4)
    service = _service(tmp_path, qdrant, finalizer=lambda value: finalizer_calls.append(value))
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "RETIRE_EFFECT_NOT_OBSERVED"
    assert "papers" in qdrant.collections
    assert "papers" not in qdrant.aliases
    assert finalizer_calls == []
    state = json.loads((tmp_path / "runtime" / "run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "switching"
    assert state["error_code"] == "RETIRE_EFFECT_NOT_OBSERVED"
    assert state["observed"]["outcome"] == "error"


def test_retire_requires_fresh_topology_observation(tmp_path):
    class InventoryFailsAfterDelete(FakeQdrant):
        def __init__(self):
            super().__init__(dense_dim=4)
            self.fail_inventory = False

        def collection_inventory(self):
            if self.fail_inventory:
                raise RuntimeError("topology unavailable")
            return super().collection_inventory()

        def delete_collection(self, destination):
            super().delete_collection(destination)
            self.fail_inventory = True

    finalizer_calls = []
    qdrant = InventoryFailsAfterDelete()
    qdrant.seed_collection("papers", dense_dim=4)
    service = _service(tmp_path, qdrant, finalizer=lambda value: finalizer_calls.append(value))
    with pytest.raises(RebuildError) as caught:
        service.run(dry_run=False, confirm_replace=True)
    assert caught.value.code == "ACTION_RESULT_UNKNOWN"
    assert "papers" not in qdrant.collections
    assert finalizer_calls == []
    state = json.loads((tmp_path / "runtime" / "run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "switching"
    assert state["error_code"] == "ACTION_RESULT_UNKNOWN"
    assert state["observed"]["outcome"] == "unknown"


def test_resume_switch_rejects_external_alias_drift_without_deleting_other(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("old", dense_dim=4)
    qdrant.seed_collection("other", dense_dim=4)
    qdrant.aliases["papers"] = "old"
    qdrant.inject_post_failure("create_alias")
    with pytest.raises(RebuildError):
        _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)
    qdrant.aliases["papers"] = "other"
    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, qdrant).resume_switch("run-test")
    assert caught.value.code == "RESUME_TOPOLOGY_DRIFT"
    assert "other" in qdrant.collections


def test_resume_recomputes_candidate_after_coordinated_state_artifact_tamper(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    qdrant.seed_collection("old", dense_dim=4)
    qdrant.aliases["papers"] = "old"
    qdrant.inject_post_failure("create_alias")
    with pytest.raises(RebuildError):
        _service(tmp_path, qdrant).run(dry_run=False, confirm_replace=True)
    run_dir = tmp_path / "runtime" / "run-test"
    validation_path = run_dir / "validation.json"
    state_path = run_dir / "state.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    validation["collection_fingerprint"] = "0" * 64
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    state["new_fingerprint"]["sha256"] = "0" * 64
    state["new_fingerprint"]["validation_artifact_sha256"] = hashlib.sha256(validation_path.read_bytes()).hexdigest()
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RebuildError) as caught:
        _service(tmp_path, qdrant).resume_switch("run-test")
    assert caught.value.code == "CANDIDATE_VALIDATION_FAILED"


def test_directory_fsync_failure_blocks_state_artifact_and_lock_success(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    original_open = candidate_rebuild_module.os.open

    def fail_directory_open(path, *args, **kwargs):
        if Path(path) == runtime or Path(path) == runtime / "run-test":
            raise OSError("directory fsync unavailable")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(candidate_rebuild_module.os, "open", fail_directory_open)
    store = _RuntimeStore(runtime, "run-test")
    state = RunState(run_id="run-test", source_collection="papers", candidate_collection="papers_rebuild_run-test", dry_run=False)
    with pytest.raises(RebuildError) as state_error:
        store.initialize(state)
    assert state_error.value.code == "RUNTIME_FSYNC_FAILED"
    with pytest.raises(RebuildError) as artifact_error:
        store.write_json("artifact.json", {"ok": True})
    assert artifact_error.value.code == "RUNTIME_FSYNC_FAILED"
    lock = _ExclusiveLock(runtime, run_id="run-test", command="test")
    with pytest.raises(RebuildError) as lock_error:
        lock.acquire()
    assert lock_error.value.code == "RUNTIME_FSYNC_FAILED"
    assert not (runtime / "rebuild.lock").exists()


def test_runtime_store_replace_fsyncs_directory(tmp_path, monkeypatch):
    fsync_paths = []
    monkeypatch.setattr(candidate_rebuild_module, "_fsync_directory", lambda path: fsync_paths.append(path))
    store = _RuntimeStore(tmp_path / "runtime", "run-test")
    store.initialize(RunState(run_id="run-test", source_collection="papers", candidate_collection="papers_rebuild_run-test", dry_run=False))
    store.write_json("probe.json", {"ok": True})
    assert len(fsync_paths) >= 2


def test_action_unknown_observation_cannot_complete(tmp_path):
    qdrant = FakeQdrant(dense_dim=4)
    service = _service(tmp_path, qdrant)
    state = RunState(run_id="run-test", source_collection="papers", candidate_collection="papers_rebuild_run-test", dry_run=False)
    service._state = state
    service._store = _RuntimeStore(tmp_path / "runtime", "run-test")
    service._store.initialize(state)
    service._observe_topology = lambda: {}
    with pytest.raises(RebuildError) as caught:
        service._action("unknown_probe", "noop", lambda: None)
    assert caught.value.code == "ACTION_RESULT_UNKNOWN"
    assert service._state.observed["outcome"] == "unknown"
    assert service._state.status != "completed"


def test_qdrant_alias_update_uses_api_compatible_keyword():
    class ClientStub:
        def __init__(self):
            self.collections = {"papers_rebuild_run"}
            self.updates = []
            self.aliases = [SimpleNamespace(alias_name="papers", collection_name="papers_rebuild_run")]

        def get_collections(self):
            return SimpleNamespace(collections=[SimpleNamespace(name=name) for name in sorted(self.collections)])

        def collection_exists(self, name):
            return name in self.collections

        def count(self, collection_name):
            return SimpleNamespace(count=0)

        def get_collection(self, name):
            return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors={"dense": object(), "sparse": object()})))

        def get_aliases(self):
            return SimpleNamespace(aliases=self.aliases)

        def update_collection_aliases(self, **kwargs):
            self.updates.append(kwargs)

    client = ClientStub()
    port = QdrantCandidateIndexPort(client, dense_dim=4)
    port.bind_candidate("papers_rebuild_run", source_collection="papers", alias="papers", run_token="run-test", retire_capability=object())
    port.create_alias("papers", "papers_rebuild_run")
    assert list(client.updates[0]) == ["change_aliases_operations"]
    assert isinstance(client.updates[0]["change_aliases_operations"], list)
    port.delete_alias("papers")
    assert all(isinstance(update["change_aliases_operations"], list) for update in client.updates)
