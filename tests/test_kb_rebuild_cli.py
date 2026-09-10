import hashlib
import json

from backend.app.knowledge_base import rebuild_index
from backend.app.knowledge_base.infrastructure import candidate_rebuild
from backend.app.knowledge_base.infrastructure.candidate_index import FakeQdrant


def test_dry_run_has_zero_embedding_collection_alias_metadata_source_manifest_runtime_lock_writes(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    papers.mkdir()
    source = papers / "doc.md"
    source.write_text("# dry run\n", encoding="utf-8")
    digest_before = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = tmp_path / "papers.json"
    metadata.write_text(json.dumps([{
        "document_id": "doc-1",
        "file_name": "doc.md",
        "stored_name": "doc.md",
        "media_type": "text/markdown",
        "source_sha256": digest_before,
    }]), encoding="utf-8")
    before_meta = metadata.read_bytes()
    qdrant = FakeQdrant(dense_dim=4)
    embed_calls = []
    monkeypatch.setattr(candidate_rebuild, "embed_texts", lambda texts: embed_calls.append(texts))

    exit_code = rebuild_index.main([
        "--dry-run",
        "--metadata-path", str(metadata),
        "--papers-dir", str(papers),
        "--runtime-root", str(tmp_path / "runtime"),
    ], index=qdrant)

    writes = {"ensure_collection", "upsert_document", "delete_collection", "create_alias", "delete_alias"}
    assert exit_code == 0
    assert embed_calls == []
    assert not any(operation in writes for operation, _target in qdrant.calls)
    assert metadata.read_bytes() == before_meta
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest_before
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "data" / "kb").exists()


def test_cli_rejects_confirm_replace_for_resume_without_explicit_gate():
    qdrant = FakeQdrant()
    assert rebuild_index.main(["--resume-switch", "run-1"], index=qdrant) == 2


def test_default_service_factory_receives_existing_ollama_boundary_judge(tmp_path, monkeypatch):
    captured = {}

    class SpyService:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, *, dry_run, confirm_replace):
            assert dry_run is True
            assert confirm_replace is False
            return {"status": "dry_run"}

    monkeypatch.setattr(rebuild_index, "CandidateRebuildService", SpyService)

    assert rebuild_index.main(
        [
            "--dry-run",
            "--metadata-path", str(tmp_path / "papers.json"),
            "--papers-dir", str(tmp_path / "papers"),
            "--runtime-root", str(tmp_path / "runtime"),
        ],
        index=FakeQdrant(),
    ) == 0
    assert captured["llm"] is rebuild_index.ollama_boundary_judge
