"""`_validated_evaluator_candidates` 的回归测试（spec-032 task-01 P0 修复）。

核心修复：聚合形 evaluator 产出的候选合法性，必须来自 Search Worker 的召回白名单，
而**不依赖** catalog_metadata 是否齐全。metadata 缺失时不得丢弃候选；模型自造的 ID
绝不被接受（fail-closed）。
"""

from backend.app.research.application.orchestrator import (
    _recalled_candidate_ids,
    _validated_evaluator_candidates,
)


def _aggregate(refs, *, keep=True):
    """构造一条聚合形 evaluator 记录：candidate_id 为 null，候选全在 evidence_refs。"""
    return {"candidate_id": None, "keep": keep, "evidence_refs": list(refs)}


def test_a_aggregate_with_metadata_expands_to_n_records():
    """a) 聚合形 + 元数据齐全 -> 展开为 N 条记录（历史行为不变）。"""
    outputs = [{"kept": [_aggregate(["catalog:c1", "catalog:c2"])]}]
    metadata = {"c1": {"title": "P1"}, "c2": {"title": "P2"}}
    records = _validated_evaluator_candidates(outputs, metadata)
    assert [r["candidate_id"] for r in records] == ["c1", "c2"]
    assert [r["evidence_refs"] for r in records] == [["catalog:c1"], ["catalog:c2"]]
    assert [r["title"] for r in records] == ["P1", "P2"]
    assert all(r["verified"] is True for r in records)


def test_b_aggregate_without_metadata_but_in_allowlist_still_expands():
    """b) 聚合形 + 元数据为空 + 白名单含该 ID -> 仍展开为 N 条记录（本次修复点）。"""
    outputs = [{"kept": [_aggregate(["catalog:c1", "catalog:c2"])]}]
    records = _validated_evaluator_candidates(outputs, {}, allowed_candidate_ids={"c1", "c2"})
    assert [r["candidate_id"] for r in records] == ["c1", "c2"]
    # 缺失元数据时记录仍必须生成，且字段完整（candidate_id + evidence_refs + verified）。
    for r in records:
        assert r["candidate_id"]
        assert r["evidence_refs"] == [f"catalog:{r['candidate_id']}"]
        assert r["verified"] is True
        assert "title" not in r  # metadata 缺失 -> 不补该字段，但不丢弃记录


def test_c_aggregate_without_metadata_and_id_not_in_allowlist_is_empty():
    """c) 聚合形 + 元数据为空 + 白名单不含该 ID -> 返回空（fail-closed 不退化）。"""
    outputs = [{"kept": [_aggregate(["catalog:c1"])]}]
    records = _validated_evaluator_candidates(outputs, {}, allowed_candidate_ids={"c9"})
    assert records == []


def test_d_non_catalog_refs_are_ignored():
    """d) 非 catalog: 前缀的 ref 被忽略（search:/arxiv: 等一律不成为候选）。"""
    outputs = [{"kept": [_aggregate(["catalog:c1", "arxiv:c1", "search:x", "catalog:c2"])]}]
    records = _validated_evaluator_candidates(outputs, {}, allowed_candidate_ids={"c1", "c2"})
    assert {r["candidate_id"] for r in records} == {"c1", "c2"}


def test_e_no_allowlist_behaves_identical_to_before():
    """e) 不传白名单时行为与修改前完全一致（元数据决定接受与否）。"""
    # 元数据齐全：返回记录
    outputs_ok = [{"kept": [_aggregate(["catalog:c1"])]}]
    meta = {"c1": {"title": "P1"}}
    explicit = _validated_evaluator_candidates(outputs_ok, meta, allowed_candidate_ids=None)
    default = _validated_evaluator_candidates(outputs_ok, meta)
    assert explicit == default
    assert [r["candidate_id"] for r in explicit] == ["c1"]

    # 元数据缺失且未传白名单：返回空（与修复前一致，不静默接受）
    outputs_missing = [{"kept": [_aggregate(["catalog:cz"])]}]
    assert _validated_evaluator_candidates(outputs_missing, {}) == []
    assert _validated_evaluator_candidates(outputs_missing, {}, allowed_candidate_ids=None) == []


def test_allowlist_prefers_allowlist_over_metadata_gap():
    """白名单命中但元数据部分缺失：只被白名单命中的记录生成，元数据仍仅补字段。"""
    outputs = [{"kept": [_aggregate(["catalog:c1", "catalog:c2"])]}]
    # 只有 c1 有元数据，c2 缺失
    records = _validated_evaluator_candidates(outputs, {"c1": {"title": "P1"}}, allowed_candidate_ids={"c1", "c2"})
    by_id = {r["candidate_id"]: r for r in records}
    assert set(by_id) == {"c1", "c2"}
    assert by_id["c1"]["title"] == "P1"
    assert "title" not in by_id["c2"]


def test_recalled_candidate_ids_uses_search_worker_candidates():
    """召回白名单来自 search-worker 的 candidates 字段，与 catalog_metadata 无关。"""

    class _Item:
        def __init__(self, role):
            self.role = role

    completed_outputs = {
        "s1": {"candidates": ["paper-1", "paper-2"]},
        "e1": {"candidates": ["paper-1"]},
        "other": {"candidates": ["paper-9"]},
    }
    item_by_id = {
        "s1": _Item("search-worker"),
        "e1": _Item("paper-evaluator"),
        "other": _Item("search-worker"),
    }
    recalled = _recalled_candidate_ids(completed_outputs, item_by_id)
    # 仅 search-worker 的 candidates 计入，evaluator 的 candidates 不计。
    assert recalled == {"paper-1", "paper-2", "paper-9"}
