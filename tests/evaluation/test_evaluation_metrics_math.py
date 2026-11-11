"""评测指标的可复算数学契约：不依赖知识库 / Ollama / 网络。

这些用例用可控 fixture 断言 recall@k / precision@k / mrr@k、意图准确率与
判官均分的数学结果，防止产品代码以硬编码分数冒充真实计算。
"""
from __future__ import annotations

from backend.app.evaluation.metrics import (
    RetrievalCase,
    aggregate_retrieval,
    intent_accuracy,
    judge_average,
)


def _key(paper: str, chunker: str, index: int) -> tuple[str, str, int]:
    return (paper, chunker, index)


def test_aggregate_retrieval_recall_precision_mrr_with_controlled_hits():
    # 三个问题，每题一个相关片段；top-k=3 的命中身份可控。
    # Q1 相关片段在 rank1；Q2 在 rank3；Q3 未命中（负例）。
    cases = [
        RetrievalCase(
            relevant_keys={_key("p1", "v1", 1)},
            hit_keys=[_key("p1", "v1", 1), _key("p9", "v1", 2), _key("p8", "v1", 3)],
        ),
        RetrievalCase(
            relevant_keys={_key("p2", "v1", 7)},
            hit_keys=[_key("p7", "v1", 4), _key("p6", "v1", 5), _key("p2", "v1", 7)],
        ),
        RetrievalCase(
            relevant_keys={_key("p3", "v1", 2)},
            hit_keys=[_key("p5", "v1", 1), _key("p4", "v1", 8), _key("p1", "v1", 9)],
        ),
    ]
    result = aggregate_retrieval(cases, k=3)
    assert result["sample_count"] == 3
    # recall = 平均(命中相关数 / 标注相关数) = (1 + 1 + 0) / 3
    assert result["recall"] == 2 / 3
    # precision = 平均(命中相关数 / k) = (1 + 1 + 0) / (3 * 3)
    assert result["precision"] == 2 / 9
    # mrr = 平均(1 / 第一个相关片段的 rank) = (1 + 1/3 + 0) / 3
    assert result["mrr"] == (1 + 1 / 3) / 3
    assert result["matched_items"] == 2
    assert result["first_relevant_ranks"] == [1, 3, None]


def test_aggregate_retrieval_k_is_bounded_by_top_k():
    # k 不能超过实际 top-k 列表长度；越界按真实返回条数收敛，不凭空补命中。
    cases = [
        RetrievalCase(
            relevant_keys={_key("p1", "v1", 1), _key("p1", "v1", 2)},
            hit_keys=[_key("p1", "v1", 1), _key("p1", "v1", 2)],
        )
    ]
    result = aggregate_retrieval(cases, k=5)
    assert result["recall"] == 1.0
    assert result["precision"] == 2 / 2  # 只有 2 条真实命中，不是 2/5
    assert result["mrr"] == 1.0
    assert result["effective_k"] == 2


def test_aggregate_retrieval_empty_judgments_returns_zero_samples():
    result = aggregate_retrieval([], k=5)
    assert result["sample_count"] == 0
    assert result["recall"] is None
    assert result["precision"] is None
    assert result["mrr"] is None


def test_intent_accuracy_counts_only_exact_matches():
    assert intent_accuracy(["kb_search", "none", "kb_ask"], ["kb_search", "none", "session_search"]) == 2 / 3
    assert intent_accuracy([], []) is None
    assert intent_accuracy([None, None], ["none", "none"]) == 0.0


def test_judge_average_ignores_unavailable_calls():
    assert judge_average([1.0, 0.5, 0.0]) == 0.5
    assert judge_average([1.0, None, 0.0]) == 0.5
    assert judge_average([None, None]) is None
