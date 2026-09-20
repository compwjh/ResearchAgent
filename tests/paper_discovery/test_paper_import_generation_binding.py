"""代次绑定（generation binding）在并发写 papers.json 时的行为契约。

背景：并发的导入 / 索引任务写 ``papers.json`` 期间，generation marker 里的
``metadata_sha256`` 会瞬时对不上，``require_generation()`` 抛 ``INDEX_FINALIZE_REQUIRED``。
这本来是「元数据与向量索引是否仍然对齐」的护栏，但写方稍后会刷新摘要，所以这个窗口是
**瞬时竞态而非真正的代次切换**。此前导入路径在 ``create_immutable_document`` 里用的是严格
断言，于是并发导入会随机失败成 ``KB_IMPORT_FAILED``。

本文件锁住两点：
1. 摘要过期（代次没换）→ 导入照常成功；
2. 代次真的换了（alias_target 变了）→ 仍然必须被 ``INDEX_GENERATION_DRIFT`` 拦下。
"""

import json
from pathlib import Path

import pytest

from backend.app.knowledge_base.application import (
    KnowledgeDocumentMigrationError,
    create_paper_import_port,
)
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
from backend.app.platform.ports import PaperImportErrorCode, PaperImportRequest

PDF = b"%PDF-1.7\ngeneration-binding-fixture"


def _root_with_generation(tmp_path: Path, run_id: str, collection: str) -> tuple[Path, Path, Path]:
    root = tmp_path / "project"
    meta = root / "data" / "kb" / "papers.json"
    papers = root / "data" / "kb" / "papers"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text("[]", encoding="utf-8")
    FinalizeBundleStore(root).stage(
        run_id,
        candidate_collection=collection,
        metadata=[],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit(run_id)
    return root, meta, papers


def _port(tmp_path: Path, source: Path, papers: Path, meta: Path):
    return create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda _record, _path: {"status": "indexed"},
    )


def test_stale_metadata_digest_does_not_fail_import(tmp_path):
    """摘要过期但代次没换：并发写的瞬时窗口，导入必须照常成功。"""
    _root, meta, papers = _root_with_generation(tmp_path, "gen-one", "papers_rebuild_one")
    first = tmp_path / "first.pdf"
    first.write_bytes(PDF + b"-first")
    second = tmp_path / "second.pdf"
    second.write_bytes(PDF + b"-second")

    port = _port(tmp_path, first, papers, meta)
    seeded = port.import_paper(
        PaperImportRequest(
            {"title": "Seed", "year": 2026, "conference_id": "ccs", "doi": "10/seed"},
            first,
        )
    )
    assert seeded.index_status.value == "indexed", seeded

    # 模拟并发写：直接改 papers.json 的一个字段，使 marker 摘要过期，
    # 但结构仍然符合迁移后的 schema（不能手写裸记录，否则会被判未迁移）。
    records = json.loads(meta.read_text(encoding="utf-8"))
    payload = records["papers"] if isinstance(records, dict) else records
    payload[0]["title"] = "Seed (concurrently edited)"
    meta.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    result = port.import_paper(
        PaperImportRequest(
            {"title": "Stale Digest", "year": 2026, "conference_id": "ccs", "doi": "10/stale"},
            second,
        )
    )

    assert result.index_status.value == "indexed", result
    assert result.error_code is None
    assert result.paper_id


def test_real_generation_switch_still_raises_drift(tmp_path, monkeypatch):
    """代次真的切换了（集合换掉）：即使放宽摘要，也必须被 DRIFT 拦下。"""
    import backend.app.knowledge_base.application as application_module

    _root, meta, papers = _root_with_generation(tmp_path, "gen-one", "papers_rebuild_one")
    source = tmp_path / "switched.pdf"
    source.write_bytes(PDF)
    current = {"collection": "papers_rebuild_one"}

    def active_generation(_meta_path, *, allow_stale_metadata=False):
        return current["collection"]

    def indexer(_record, _path):
        # 索引过程中提交了新的代次：这是真正的漂移，不是摘要过期。
        current["collection"] = "papers_rebuild_two"
        return {"status": "indexed"}

    monkeypatch.setattr(application_module, "_active_generation_collection", active_generation)

    port = create_paper_import_port(papers_dir=papers, meta_path=meta, indexer=indexer)
    result = port.import_paper(
        PaperImportRequest(
            {"title": "Switched", "year": 2026, "conference_id": "ccs", "doi": "10/switched"},
            source,
        )
    )

    assert result.index_status.value == "failed"
    assert result.error_code == PaperImportErrorCode.KB_IMPORT_FAILED
    assert result.paper_id


def test_read_path_remains_fail_closed_on_stale_digest(tmp_path):
    """读取路径不放宽：摘要过期时 require_generation 仍然要报错。"""
    from backend.app.knowledge_base.infrastructure.manifest_store import ManifestStoreError

    root, meta, _papers = _root_with_generation(tmp_path, "gen-one", "papers_rebuild_one")
    meta.write_text(json.dumps([{"paper_id": "seed"}]), encoding="utf-8")

    with pytest.raises(ManifestStoreError) as exc:
        FinalizeBundleStore(root).require_generation()
    assert getattr(exc.value, "code", "") == "INDEX_FINALIZE_REQUIRED"


def test_assert_generation_binding_tolerates_stale_but_catches_drift(tmp_path):
    import backend.app.knowledge_base.application as application_module

    _root, meta, _papers = _root_with_generation(tmp_path, "gen-one", "papers_rebuild_one")

    # 摘要一致但集合变了 -> 无论是否放宽都必须报 DRIFT
    for allow in (False, True):
        with pytest.raises(KnowledgeDocumentMigrationError) as exc:
            application_module._assert_generation_binding(
                meta, "papers_rebuild_other", allow_stale_metadata=allow
            )
        assert exc.value.code == "INDEX_GENERATION_DRIFT"

    # 摘要过期 + 集合未变 -> 严格模式报错，放宽后通过
    meta.write_text(json.dumps([{"paper_id": "seed"}]), encoding="utf-8")
    with pytest.raises(KnowledgeDocumentMigrationError) as exc:
        application_module._assert_generation_binding(meta, "papers_rebuild_one")
    assert exc.value.code == "INDEX_FINALIZE_REQUIRED"
    application_module._assert_generation_binding(
        meta, "papers_rebuild_one", allow_stale_metadata=True
    )

    # 摘要过期 + 集合也变了 -> 放宽后仍要报 DRIFT，不能被摘要错误掩盖
    with pytest.raises(KnowledgeDocumentMigrationError) as exc:
        application_module._assert_generation_binding(
            meta, "papers_rebuild_other", allow_stale_metadata=True
        )
    assert exc.value.code == "INDEX_GENERATION_DRIFT"
