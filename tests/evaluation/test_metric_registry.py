"""评测指标注册表契约：22 个 key、中文 label、5 组映射、build_metric 约束。

注册表是 score 响应与 compare deltas 的唯一遍历源；任一 key 缺 label 会在
build_metric 直接 KeyError，任一 key 缺 group 会破坏前端按组渲染。
"""
from __future__ import annotations

import pytest

from backend.app.evaluation import contracts

LEGACY_KEYS = (
    "recall@k",
    "precision@k",
    "mrr@k",
    "intent_accuracy",
    "chat_quality",
    "memory_correctness",
)
NEW_KEYS = (
    "hit_rate@k",
    "ndcg@k",
    "retrieval_relevance",
    "intent_macro_f1",
    "intent_confusion_count",
    "answer_relevance",
    "conciseness",
    "helpfulness",
    "groundedness",
    "hallucination_free",
    "answer_exact_match",
    "levenshtein_similarity",
    "generation_success_rate",
    "answer_length_avg",
    "toxicity_free",
    "pii_leakage_free",
)
EXPECTED_GROUPS = {
    "recall@k": "retrieval",
    "precision@k": "retrieval",
    "mrr@k": "retrieval",
    "hit_rate@k": "retrieval",
    "ndcg@k": "retrieval",
    "retrieval_relevance": "retrieval",
    "intent_accuracy": "intent",
    "intent_macro_f1": "intent",
    "intent_confusion_count": "intent",
    "chat_quality": "answer_quality",
    "memory_correctness": "answer_quality",
    "answer_relevance": "answer_quality",
    "conciseness": "answer_quality",
    "helpfulness": "answer_quality",
    "groundedness": "answer_quality",
    "hallucination_free": "answer_quality",
    "answer_exact_match": "answer_quality",
    "levenshtein_similarity": "answer_quality",
    "generation_success_rate": "generation",
    "answer_length_avg": "generation",
    "toxicity_free": "safety",
    "pii_leakage_free": "safety",
}


def test_registry_has_22_unique_keys_and_keeps_legacy_prefix():
    assert len(contracts.METRIC_KEYS) == 22
    assert len(set(contracts.METRIC_KEYS)) == 22
    assert contracts.METRIC_KEYS[:6] == LEGACY_KEYS
    assert set(contracts.METRIC_KEYS[6:]) == set(NEW_KEYS)
    assert len(NEW_KEYS) == 16


def test_every_key_has_chinese_label_and_legal_group():
    assert set(contracts.METRIC_LABELS) == set(contracts.METRIC_KEYS)
    assert set(contracts.METRIC_GROUPS) == set(contracts.METRIC_KEYS)
    allowed = {"retrieval", "intent", "answer_quality", "generation", "safety"}
    for key in contracts.METRIC_KEYS:
        assert isinstance(contracts.METRIC_LABELS[key], str) and contracts.METRIC_LABELS[key].strip()
        assert contracts.METRIC_GROUPS[key] in allowed


def test_group_mapping_matches_spec_table():
    assert contracts.METRIC_GROUPS == EXPECTED_GROUPS


def test_build_metric_injects_group_without_new_required_parameters():
    metric = contracts.build_metric("ndcg@k", value=0.75, sample_count=3)
    assert metric["key"] == "ndcg@k"
    assert metric["group"] == "retrieval"
    assert metric["value"] == 0.75
    assert metric["sample_count"] == 3
    assert metric["label"] == contracts.METRIC_LABELS["ndcg@k"]


def test_all_22_keys_construct_without_keyerror_for_computed_and_uncomputed():
    for key in contracts.METRIC_KEYS:
        computed = contracts.build_metric(key, value=0.5, sample_count=1)
        assert computed["group"] == EXPECTED_GROUPS[key]
        degraded = contracts.uncomputed_metric(key, contracts.DEGRADED, "dependency failed")
        assert degraded["group"] == EXPECTED_GROUPS[key]
        assert degraded["value"] is None
        assert degraded["detail"]["reason"] == "dependency failed"


def test_non_computed_constraint_is_unchanged():
    with pytest.raises(ValueError, match="must carry detail.reason"):
        contracts.build_metric("hit_rate@k", value=0.9, status=contracts.DEGRADED, detail={})
    forced = contracts.build_metric(
        "hit_rate@k", value=0.9, status=contracts.DEGRADED, detail={"reason": "no truth"}
    )
    assert forced["value"] is None
    assert forced["group"] == "retrieval"


def test_constants_and_error_specs_are_not_expanded():
    # spec-047 追加范围三 §13.1 P1-2：三常量收敛为单一真源的新取值。
    assert contracts.SCORE_TIMEOUT_SECONDS == 900.0
    assert contracts.DEFAULT_MAX_ITEMS == 100
    assert contracts.MAX_ITEMS == 200
    assert set(contracts.ERROR_SPECS) == {
        "EVAL_OPTION_NOT_FOUND",
        "EVAL_DATASET_INVALID",
        "EVAL_BACKEND_UNAVAILABLE",
        "EVAL_SCORE_TIMEOUT",
        "EVAL_NOT_COMPARABLE",
    }
    assert set(contracts.STRATEGIES) == {"baseline", "chunker-v2", "topk-10", "rerank-on"}


def test_rubric_enum_map_is_registered_in_contracts():
    assert contracts.RUBRIC_ENUM_MAPS == {"good": 1.0, "mixed": 0.5, "poor": 0.0}
