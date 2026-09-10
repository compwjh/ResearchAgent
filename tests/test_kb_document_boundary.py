import ast
import json
from pathlib import Path

import pytest

from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure import store
from backend.app.knowledge_base.infrastructure.candidate_index import (
    CandidateIndexError,
    FakeQdrant,
    QdrantCandidateIndexPort,
)
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore


def test_application_surface_does_not_export_unsafe_direct_write_symbols():
    retired = {
        "save_upload",
        "upsert_paper",
        "remove_paper",
        "index_paper",
        "index_paper_chunker",
        "delete_paper",
        "delete_paper_chunker",
        "run_index_task_sync",
        "submit_index_task",
        "mark_interrupted_on_startup",
        "mark_interrupted_tasks",
        "backfill_chunker_defaults",
    }
    assert retired.isdisjoint(set(application.__all__))


def test_metadata_only_update_has_no_source_or_index_side_effects(tmp_path, monkeypatch):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    document = application.create_uploaded_document(
        "boundary.md", "text/markdown", b"# boundary\n", meta_path=meta, papers_dir=papers
    )["document"]
    calls = []
    monkeypatch.setattr(store, "save_upload", lambda *args, **kwargs: calls.append("source"))
    monkeypatch.setattr(store, "remove_paper", lambda *args, **kwargs: calls.append("remove"))
    store.update_chunker_state(document["document_id"], "v1", status="pending", meta_path=meta)
    assert calls == []
    assert (papers / document["stored_name"]).read_bytes() == b"# boundary\n"


def test_legacy_write_symbols_remain_infrastructure_only():
    module = ast.parse(Path(store.__file__).read_text(encoding="utf-8"))
    names = {node.name for node in ast.walk(module) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"save_upload", "upsert_paper", "remove_paper"} <= names
    source = Path(application.__file__).read_text(encoding="utf-8")
    assert "from backend.app.knowledge_base.infrastructure.store import" in source


@pytest.mark.parametrize(
    "call",
    [
        lambda: index_module.ensure_collection(object()),
        lambda: index_module.upsert_chunks("doc", "x.md", [object()], client=object()),
        lambda: index_module.delete_paper_chunker("doc", "v1", client=object()),
        lambda: index_module.delete_paper("doc", client=object()),
        lambda: index_module.index_paper({}, "missing.pdf"),
        lambda: index_module.index_paper_chunker({}, "missing.pdf"),
    ],
)
def test_legacy_index_writes_require_explicit_destination(call):
    with pytest.raises(index_module.IndexWriteBoundaryError) as error:
        call()
    assert error.value.code == "DESTINATION_COLLECTION_REQUIRED"


@pytest.mark.parametrize("candidate", ["papers", "papers-alias", "legacy_collection", "papers_rebuild_"])
def test_candidate_binding_rejects_formal_or_invalid_candidate(candidate):
    for port in (FakeQdrant(), QdrantCandidateIndexPort(object())):
        with pytest.raises(CandidateIndexError) as error:
            port.bind_candidate(
                candidate,
                source_collection="papers",
                alias="papers",
                run_token="run-test",
                retire_capability=object(),
            )
        assert error.value.code in {"INVALID_CANDIDATE_NAME", "CANDIDATE_BOUNDARY_VIOLATION"}


def _write_generation_marker(meta: Path, target: str = "papers_rebuild_live") -> None:
    root = meta.parents[2]
    records = json.loads(meta.read_text(encoding="utf-8"))
    finalizer = FinalizeBundleStore(root)
    finalizer.stage(
        "generation-test",
        candidate_collection=target,
        metadata=records,
        manifests={},
        collection_fingerprint="a" * 64,
    )
    finalizer.commit("generation-test")


def test_reindex_explicit_destination_is_still_marker_bound(tmp_path):
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    document = application.create_uploaded_document(
        "boundary.md", "text/markdown", b"# boundary\n", meta_path=meta, papers_dir=papers
    )["document"]

    with pytest.raises(application.KnowledgeDocumentMigrationError) as missing:
        application.submit_document_reindex(
            document["document_id"], "v1", meta_path=meta, papers_dir=papers,
            destination_collection="papers_rebuild_test",
        )
    assert missing.value.code == "INDEX_REBUILD_REQUIRED"

    _write_generation_marker(meta)
    with pytest.raises(application.KnowledgeDocumentMigrationError) as mismatch:
        application.submit_document_reindex(
            document["document_id"], "v1", meta_path=meta, papers_dir=papers,
            destination_collection="papers_rebuild_test",
        )
    assert mismatch.value.code == "INDEX_TOPOLOGY_AMBIGUOUS"
