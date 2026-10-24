"""BUG-05（spec-020 第 3 批）：空库首次部署的代际自动初始化。

覆盖两条硬边界：
1. 空库（首次部署）在显式 opt-in 时自动 bootstrap 初始代际，且幂等；
2. 非空库**绝不**自动重建——marker 缺失时一律 fail-closed 返回 INDEX_REBUILD_REQUIRED。
"""

import hashlib
import inspect
import json

import pytest

from backend.app import main
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    ManifestStoreError,
)


def test_empty_library_bootstraps_generation_and_is_idempotent(tmp_path):
    store = FinalizeBundleStore(tmp_path)
    live = tmp_path / "data" / "kb"

    marker = store.require_generation(allow_bootstrap=True)

    assert marker["schema_version"] == "index-generation-v1"
    assert marker["alias_name"] == "papers"
    assert marker["alias_target"].startswith("papers_rebuild_")
    assert (live / "index-generation.json").exists()
    assert (live / "papers.json").read_text(encoding="utf-8") == "[]"
    # 生成的 marker 必须通过自身后续校验（metadata/manifests 摘要一致）
    assert store.require_generation(allow_bootstrap=True) == marker
    # 以及不带 opt-in 的读取路径同样可用
    assert store.require_generation() == marker


def test_empty_library_stays_fail_closed_without_opt_in(tmp_path):
    """读路径（启动自检、状态、检查清单）不得产生任何副作用。"""
    store = FinalizeBundleStore(tmp_path)

    with pytest.raises(ManifestStoreError) as error:
        store.require_generation()

    assert error.value.code == "INDEX_REBUILD_REQUIRED"
    assert error.value.status == 409
    assert not (tmp_path / "data" / "kb").exists()


def test_non_empty_library_never_bootstraps(tmp_path):
    """有数据却缺 marker 只能靠授权的全库重建，绝不自动修复。"""
    live = tmp_path / "data" / "kb"
    live.mkdir(parents=True)
    (live / "papers.json").write_text('[{"document_id": "doc-1"}]', encoding="utf-8")
    store = FinalizeBundleStore(tmp_path)

    with pytest.raises(ManifestStoreError) as error:
        store.require_generation(allow_bootstrap=True)

    assert error.value.code == "INDEX_REBUILD_REQUIRED"
    assert not (live / "index-generation.json").exists()


def test_finalize_pending_still_reports_503(tmp_path):
    store = FinalizeBundleStore(tmp_path)

    with pytest.raises(ManifestStoreError) as error:
        store.require_generation(finalize_pending=True, allow_bootstrap=True)

    assert error.value.code == "INDEX_FINALIZE_REQUIRED"
    assert error.value.status == 503


def test_bootstrap_rejects_paired_target_and_fingerprint_tampering(tmp_path):
    """The bootstrap target is fixed; a paired forged fingerprint is not valid."""
    store = FinalizeBundleStore(tmp_path)
    store.require_generation(allow_bootstrap=True)
    marker_path = tmp_path / "data" / "kb" / "index-generation.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    forged_target = "papers_rebuild_forged"
    marker["alias_target"] = forged_target
    marker["collection_fingerprint"] = hashlib.sha256(forged_target.encode("utf-8")).hexdigest()
    marker_path.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "data" / "kb" / "papers.json").write_text("[]\n", encoding="utf-8")

    with pytest.raises(ManifestStoreError) as error:
        store.require_generation(allow_stale_metadata=True)

    assert error.value.code == "INDEX_FINALIZE_REQUIRED"


def test_startup_gate_does_not_opt_in_to_bootstrap():
    """启动必须保持只读（既有约束：startup 不得产生 KB 持久化写入）。"""
    source = inspect.getsource(main.lifespan)
    assert "allow_bootstrap" not in source
