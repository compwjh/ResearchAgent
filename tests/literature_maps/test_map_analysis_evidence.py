import hashlib
import json

import pytest

from backend.app.chat.application.chat_runner import ChatRun
from backend.app.knowledge_base.infrastructure.inspection import build_inspection_manifest
from backend.app.knowledge_base.infrastructure.markdown import extract_markdown_provenance
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
from backend.app.knowledge_base.infrastructure.provenance import build_source_provenance_bundle
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings
from backend.app.literature_maps.application import analysis as analysis_module
from backend.app.literature_maps.application.analysis import MapAnalysisService
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.knowledge_base.infrastructure.retrieve import Hit


def _completed_run(text: str = "有依据的摘要") -> ChatRun:
    run = ChatRun(route="direct", events=iter(()))
    run.result = OllamaChatResult(
        content=text,
        thinking="",
        timings=OllamaTimings(),
        timings_available=False,
        first_token_ms=0,
        client_wall_ms=0,
        completed_normally=True,
    )
    return run


def test_abstract_analysis_persists_evidence_and_result_without_model_call_for_title_only(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="A paper", abstract="A real abstract")
    store.add_nodes(item.map_id, "owner-a", [node])
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return _completed_run()

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    analysis, job, _created = service.request_analysis(
        item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="same"
    )
    service.run_analysis_job(job.job_id, "owner-a")

    stored = store.get_analysis(analysis.analysis_id, item.map_id, "owner-a")
    assert stored is not None
    assert stored.status == "completed"
    assert stored.evidence_level == "abstract"
    assert stored.result["summary"] == "有依据的摘要"
    assert stored.result["citations"] == []
    assert calls


def test_title_without_abstract_is_rejected_before_generation(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="Title only")
    store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=store, executor=None, model_runner=lambda **_: _completed_run())

    try:
        service.request_analysis(item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="x")
    except Exception as error:
        assert str(error) == "MAP_ABSTRACT_UNAVAILABLE"
    else:
        raise AssertionError("title-only nodes must not be sent to the model")


def test_full_analysis_passes_only_verified_document_to_retrieval(tmp_path, monkeypatch):
    kb_dir, record = _real_manifest_fixture(tmp_path)
    monkeypatch.setattr(analysis_module, "KB_DIR", kb_dir)
    monkeypatch.setattr(analysis_module, "list_documents_for_project", lambda *_args, **_kwargs: [record])
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", project_id="project-a")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="A paper", document_id="doc-real")
    store.add_nodes(item.map_id, "owner-a", [node])
    seen = []

    def searcher(_question, **kwargs):
        seen.append(kwargs)
        return [Hit("doc-real", "paper.pdf", 2, 0, "real indexed evidence", 0.9)]

    service = MapAnalysisService(
        store=store,
        executor=None,
        model_runner=lambda **_: _completed_run("全文依据"),
        searcher=searcher,
    )
    analysis, job, _created = service.request_analysis(
        item.map_id, node.node_id, "owner-a", evidence_level="full", idempotency_key="full-1"
    )
    service.run_analysis_job(job.job_id, "owner-a")
    stored = store.get_analysis(analysis.analysis_id, item.map_id, "owner-a")
    assert stored.status == "completed"
    assert seen[0]["document_ids"] == ["doc-real"]
    assert stored.result["source_refs"][0]["document_id"] == "doc-real"


def _real_manifest_fixture(
    tmp_path,
    *,
    source_hash_state="verified",
    status="ready",
    manifest_mode="normal",
    record_project_id="project-a",
):
    root = tmp_path / "kb-root"
    kb_dir = root / "data" / "kb"
    source = b"# A paper\n\nIndexed evidence for the map analysis.\n"
    source_hash = hashlib.sha256(source).hexdigest()
    provenance = extract_markdown_provenance(source, document_id="doc-real", source_sha256=source_hash)
    bundle = build_source_provenance_bundle(provenance, chunker="markdown-block-v1")
    payloads = [
        {**chunk, "document_id": "doc-real", "chunker": "v1", "source_sha256": source_hash, "is_citation": False}
        for chunk in bundle.chunks
    ]
    manifest = build_inspection_manifest(
        {"document_id": "doc-real", "source_sha256": source_hash},
        bundle,
        payloads,
    ).to_dict()
    manifest["source_hash_state"] = source_hash_state
    manifest["status"] = status
    if source_hash_state == "legacy_unknown":
        manifest["status"] = "pending"
        manifest["indexed_source_sha256"] = None
        manifest["index_fingerprint"] = None
    manifests = {} if manifest_mode == "missing" else {("doc-real", "v1"): manifest}
    if manifest_mode == "mismatch":
        manifest["indexed_source_sha256"] = "b" * 64
    FinalizeBundleStore(root).stage(
        "map-generation",
        candidate_collection="papers_rebuild_map-generation",
        metadata=[{"document_id": "doc-real", "source_sha256": source_hash, "schema_version": "knowledge-document-v1"}],
        manifests=manifests,
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit("map-generation")
    return kb_dir, {"document_id": "doc-real", "source_sha256": source_hash, "project_id": record_project_id}


@pytest.mark.parametrize(
    ("source_hash_state", "status", "manifest_mode"),
    [
        ("legacy_unknown", "ready", "normal"),
        ("verified", "partial", "normal"),
        ("verified", "ready", "mismatch"),
        ("verified", "ready", "missing"),
    ],
)
def test_full_source_gate_requires_verified_ready_real_manifest(tmp_path, monkeypatch, source_hash_state, status, manifest_mode):
    kb_dir, record = _real_manifest_fixture(
        tmp_path,
        source_hash_state=source_hash_state,
        status=status,
        manifest_mode=manifest_mode,
    )
    monkeypatch.setattr(analysis_module, "KB_DIR", kb_dir)
    monkeypatch.setattr(analysis_module, "list_documents_for_project", lambda *_args, **_kwargs: [record])
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", project_id="project-a")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-real", title="Real", document_id="doc-real")
    store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=store, executor=None)
    assert service.source_status(item.map_id, node.node_id, "owner-a")["fulltext_ready"] is False


def test_full_source_gate_rejects_changed_generation_marker(tmp_path, monkeypatch):
    kb_dir, record = _real_manifest_fixture(tmp_path)
    monkeypatch.setattr(analysis_module, "KB_DIR", kb_dir)
    monkeypatch.setattr(analysis_module, "list_documents_for_project", lambda *_args, **_kwargs: [record])
    # Metadata drift after finalize makes the committed generation unusable.
    papers_path = kb_dir / "papers.json"
    papers_path.write_text(papers_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", project_id="project-a")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-generation", title="Generation", document_id="doc-real")
    store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=store, executor=None)
    assert service.source_status(item.map_id, node.node_id, "owner-a")["fulltext_ready"] is False


def test_shared_pool_full_analysis_and_conversation_keep_owner_scope(tmp_path, monkeypatch):
    kb_dir, record = _real_manifest_fixture(tmp_path, record_project_id=None)
    monkeypatch.setattr(analysis_module, "KB_DIR", kb_dir)
    monkeypatch.setattr(analysis_module, "list_documents_for_project", lambda *_args, **_kwargs: [record])
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="shared pool")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-shared", title="Shared", document_id="doc-real")
    store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=store, executor=None)
    status = service.source_status(item.map_id, node.node_id, "owner-a")
    assert status["fulltext_ready"] is True
    # The same verified source is valid for a map without a project binding;
    # this must not imply access to any other owner's/project's documents.
    binding_result = service.create_conversation(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="full",
        idempotency_key="shared-full",
    )
    binding = store.get_conversation_binding(binding_result["conversation_id"], "owner-a")
    context = service.conversation_context(binding, "owner-a", None)
    assert context["visible_document_ids"] == ["doc-real"]
    assert context["chunker"] == "v1"


def test_analysis_rechecks_source_after_generation_before_completion(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", project_id="project-a")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-race", title="Race", document_id="doc-race")
    store.add_nodes(item.map_id, "owner-a", [node])
    state = {"source_version": "v1"}

    def checker(_map, _node, _owner):
        return {"document_id": "doc-race", "source_version": state["source_version"], "chunker": "v1"}

    def runner(**_kwargs):
        state["source_version"] = "v2"
        return _completed_run("stale")

    service = MapAnalysisService(
        store=store,
        executor=None,
        model_runner=runner,
        source_checker=checker,
        searcher=lambda *_args, **_kwargs: [Hit("doc-race", "paper.pdf", 1, 0, "evidence", 0.9)],
    )
    analysis, job, _ = service.request_analysis(
        item.map_id, node.node_id, "owner-a", evidence_level="full", idempotency_key="race"
    )
    service.run_analysis_job(job.job_id, "owner-a")
    stored = store.get_analysis(analysis.analysis_id, item.map_id, "owner-a")
    assert stored.status == "failed"
    assert stored.error["code"] == "MAP_ANALYSIS_SOURCE_CHANGED"
