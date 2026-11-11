"""新增纯函数指标的可复算契约：不依赖知识库 / Ollama / 网络。

覆盖 hit_rate、二值 nDCG（含理想 DCG=0 不除零）、宏 F1、归一化编辑相似度，
并断言 aggregate_retrieval 追加字段不改既有六项语义。
"""
from __future__ import annotations

import math

import pytest

from backend.app.evaluation import metrics


def _key(paper: str, index: int) -> tuple[str, str, int]:
    return (paper, "v1", index)


def test_hit_rate_from_ranks_counts_samples_with_any_relevant_hit():
    assert metrics.hit_rate_from_ranks([1, None, 3]) == 2 / 3
    assert metrics.hit_rate_from_ranks([None, None]) == 0.0
    assert metrics.hit_rate_from_ranks([2, 1]) == 1.0
    assert metrics.hit_rate_from_ranks([]) is None


def test_binary_ndcg_returns_none_when_ideal_dcg_is_zero():
    # 无标注相关片段或返回条数为 0 时理想 DCG=0，绝不除零、绝不出 0.0000 假分。
    assert metrics.binary_ndcg([], set()) is None
    assert metrics.binary_ndcg([_key("p1", 1)], set()) is None
    assert metrics.binary_ndcg([], {_key("p1", 1)}) is None


def test_binary_ndcg_is_recomputable_with_binary_gains():
    relevant = {_key("p1", 1)}
    assert metrics.binary_ndcg([_key("p1", 1), _key("p9", 2)], relevant) == pytest.approx(1.0)
    # 相关片段落在 rank2：DCG=1/log2(3)，理想 DCG=1。
    assert metrics.binary_ndcg([_key("p9", 2), _key("p1", 1)], relevant) == pytest.approx(
        1.0 / math.log2(3)
    )
    # 两个相关片段只召回一个：理想 DCG=1+1/log2(3)，DCG=1。
    two_relevant = {_key("p1", 1), _key("p2", 2)}
    assert metrics.binary_ndcg([_key("p1", 1), _key("p9", 9)], two_relevant) == pytest.approx(
        1.0 / (1.0 + 1.0 / math.log2(3))
    )


def test_aggregate_retrieval_appends_two_keys_without_changing_legacy_results():
    cases = [
        metrics.RetrievalCase(
            relevant_keys={_key("p1", 1)},
            hit_keys=[_key("p1", 1), _key("p9", 2), _key("p8", 3)],
        ),
        metrics.RetrievalCase(
            relevant_keys={_key("p2", 7)},
            hit_keys=[_key("p7", 4), _key("p6", 5), _key("p2", 7)],
        ),
        metrics.RetrievalCase(
            relevant_keys={_key("p3", 2)},
            hit_keys=[_key("p5", 1), _key("p4", 8), _key("p1", 9)],
        ),
    ]
    result = metrics.aggregate_retrieval(cases, k=3)
    # 既有六项语义逐字不动（与 test_evaluation_metrics_math.py 同一 fixture 同值）。
    assert result["sample_count"] == 3
    assert result["recall"] == 2 / 3
    assert result["precision"] == 2 / 9
    assert result["mrr"] == (1 + 1 / 3) / 3
    assert result["matched_items"] == 2
    assert result["first_relevant_ranks"] == [1, 3, None]
    assert result["effective_k"] == 3
    # 新增字段：hit_rate=2/3；nDCG 只统计理想 DCG>0 的样本。
    assert result["hit_rate"] == 2 / 3
    assert result["ndcg"] == pytest.approx((1.0 + 1.0 / math.log2(4)) / 3)
    assert result["ndcg_valid_cases"] == 3
    assert result["ndcg_skipped_cases"] == 0


def test_aggregate_retrieval_empty_cases_keeps_legacy_nulls_and_no_fake_zero():
    result = metrics.aggregate_retrieval([], k=5)
    assert result["sample_count"] == 0
    assert result["recall"] is None
    assert result["precision"] is None
    assert result["mrr"] is None
    assert result["hit_rate"] is None
    assert result["ndcg"] is None
    assert result["ndcg_valid_cases"] == 0
    assert result["effective_k"] == 0


def test_intent_macro_f1_is_recomputable_per_class():
    predictions = ["a", "b", "a", "c"]
    expected = ["a", "b", "b", "c"]
    # a: tp1 fp1 fn0 -> p=.5 r=1  f1=2/3
    # b: tp1 fp0 fn1 -> p=1  r=.5 f1=2/3
    # c: tp1 fp0 fn0 -> p=1  r=1  f1=1
    assert metrics.intent_macro_f1(predictions, expected) == pytest.approx(7 / 9)
    assert metrics.intent_macro_f1(["x", "x"], ["x", "x"]) == 1.0
    assert metrics.intent_macro_f1([], []) is None


def test_levenshtein_similarity_is_normalized_and_handles_empty_strings():
    assert metrics.levenshtein_similarity("", "") == 1.0
    assert metrics.levenshtein_similarity("abc", "") == 0.0
    assert metrics.levenshtein_similarity("", "abc") == 0.0
    assert metrics.levenshtein_similarity("abc", "abc") == 1.0
    assert metrics.levenshtein_similarity("kitten", "sitting") == pytest.approx(1 - 3 / 7)
    assert 0.0 <= metrics.levenshtein_similarity("abcd", "ab") <= 1.0
