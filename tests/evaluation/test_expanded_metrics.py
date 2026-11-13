"""扩展指标的真实计算契约：检索 5 项 / 意图 3 项 / 回答 11 项，以及既有 6 项语义不变。

所有外部依赖（hybrid_search / detect_skill / call_ollama）在用例内注入可控 fake，
产品代码仍必须真实调用，且不允许用冻结 output 冒充实时生成或人工真值。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from batch_transport_doubles import batch_transport

from backend.app.evaluation import metrics, rubrics
from backend.app.evaluation.contracts import JUDGE_MODEL, get_strategy
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.skills.intent import SkillDecision


def _hit(paper: str, index: int, text: str = "fixture chunk") -> Hit:
    return Hit(
        paper_id=paper,
        file_name=f"{paper}.pdf",
        page=1,
        chunk_index=index,
        text=text,
        score=1.0,
        chunker="v1",
    )


def _rag_items() -> list[dict]:
    return [
        {"question": "Q1", "relevant_doc_ids": [{"paper_id": "p1", "chunker": "v1", "chunk_index": 1}]},
        {"question": "Q2", "relevant_doc_ids": [{"paper_id": "p2", "chunker": "v1", "chunk_index": 2}]},
    ]


def _chat_items(count: int = 3) -> list[dict]:
    return [
        {"trace_id": f"c{i}", "input": f"q{i}", "output": f"FROZEN-{i}", "prior_context": None}
        for i in range(1, count + 1)
    ]


def _valid_rubric_json() -> str:
    return json.dumps(dict.fromkeys(rubrics.RUBRIC_KEYS, "good"))


def test_retrieval_metrics_returns_five_keys_with_legacy_values_unchanged(monkeypatch):
    table = {
        "Q1": [_hit("p1", 1), _hit("p9", 8), _hit("p8", 9)],
        "Q2": [_hit("p7", 3), _hit("p6", 4), _hit("p2", 2)],
    }
    monkeypatch.setattr(metrics, "hybrid_search", lambda q, **k: table.get(q, [])[: k.get("top_k") or 5])

    result = metrics.retrieval_metrics(_rag_items(), get_strategy("baseline"), 3)

    assert set(result) == {"recall@k", "precision@k", "mrr@k", "hit_rate@k", "ndcg@k"}
    assert result["recall@k"]["value"] == 1.0
    assert result["precision@k"]["value"] == 2 / 6
    assert result["mrr@k"]["value"] == (1 + 1 / 3) / 2
    assert result["hit_rate@k"]["value"] == 1.0
    assert result["ndcg@k"]["value"] == pytest.approx((1.0 + 0.5) / 2)
    assert all(entry["group"] == "retrieval" for entry in result.values())
    assert result["recall@k"]["detail"]["model_participates"] is False


def test_ndcg_metric_degrades_with_reason_when_ideal_dcg_is_zero(monkeypatch):
    monkeypatch.setattr(metrics, "hybrid_search", lambda q, **k: [_hit("p9", 8)])
    items = [{"question": "Q1", "relevant_doc_ids": []}]
    result = metrics.retrieval_metrics(items, get_strategy("baseline"), 3)
    ndcg = result["ndcg@k"]
    assert ndcg["status"] in ("degraded", "unavailable", "needs_ground_truth")
    assert ndcg["value"] is None
    assert "理想 DCG" in ndcg["detail"]["reason"]


def test_intent_metrics_returns_three_keys_and_calls_detector_once_per_item(monkeypatch):
    calls: list[str] = []
    table = {"m1": "kb_search", "m2": "none", "m3": "none"}

    def fake_detect(message, skills):
        calls.append(message)
        skill = table[message]
        return SkillDecision(status="matched" if skill != "none" else "none", skill=skill, source="rule")

    monkeypatch.setattr(metrics, "detect_skill", fake_detect)
    items = [
        {"message": "m1", "expected_intent": "kb_search"},
        {"message": "m2", "expected_intent": "none"},
        {"message": "m3", "expected_intent": "kb_search"},
    ]
    result = metrics.intent_metrics(items, 3)

    assert set(result) == {"intent_accuracy", "intent_macro_f1", "intent_confusion_count"}
    assert calls == ["m1", "m2", "m3"]  # 复用同一次 detect_skill 结果，不重复调用
    assert result["intent_accuracy"]["value"] == pytest.approx(2 / 3)
    assert result["intent_macro_f1"]["value"] == pytest.approx(2 / 3)
    assert result["intent_confusion_count"]["value"] == 1
    assert set(result["intent_macro_f1"]["detail"]["per_class"]) == {"kb_search", "none"}
    assert all(entry["group"] == "intent" for entry in result.values())


def test_answer_quality_metrics_generates_once_per_sample_with_selected_model(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        metrics, "call_ollama",
        lambda *args, **kwargs: batch_transport(*args, **kwargs, calls=calls),
        raising=False,
    )
    monkeypatch.setattr(metrics, "hybrid_search", lambda *a, **k: [_hit("p1", 1, "real KB chunk")])

    result = metrics.answer_quality_metrics(_chat_items(3), 3, "model-A", deadline=None)

    generation_calls = [call for call in calls if "BATCH GENERATION" in call["system"]]
    judge_calls = [call for call in calls if "BATCH RUBRIC" in call["system"]]
    assert len(generation_calls) == 1 and generation_calls[0]["size"] == 3  # 3 条合成 1 批
    assert generation_calls[0]["model"] == "model-A"
    assert generation_calls[0]["num_predict"] is not None
    assert all(call["timeout"] is not None and call["timeout"] > 0 for call in generation_calls)
    assert len(judge_calls) == 1  # 一次批量联合判官，7 维度共用
    assert judge_calls[0]["model"] == JUDGE_MODEL

    assert set(result) == {
        *rubrics.RUBRIC_KEYS,
        "answer_exact_match",
        "levenshtein_similarity",
        "generation_success_rate",
        "answer_length_avg",
    }
    assert "chat_quality" not in result and "memory_correctness" not in result
    for key in rubrics.RUBRIC_KEYS:
        assert result[key]["status"] == "computed"
        assert result[key]["value"] == 1.0
        assert result[key]["sample_count"] == 3
    assert "hybrid_search" in json.dumps(result["groundedness"]["detail"])
    assert result["generation_success_rate"]["value"] == 1.0
    assert result["answer_length_avg"]["value"] == pytest.approx(
        sum(len(f"LIVE::q{i}") for i in range(1, 4)) / 3
    )
    for key in ("answer_exact_match", "levenshtein_similarity"):
        detail = result[key]["detail"]
        assert detail["reference"] == "frozen-042-output"
        assert detail["note"] == "字面一致性，不代表回答质量"
    assert "人工标准答案" not in json.dumps(result, ensure_ascii=False)


def test_generation_failure_degrades_judge_dimensions_without_frozen_output_fallback(monkeypatch):
    def failing_call_ollama(model, messages, timeout=None, num_predict=None):
        raise OSError("model not available locally")

    monkeypatch.setattr(metrics, "call_ollama", failing_call_ollama, raising=False)
    monkeypatch.setattr(metrics, "hybrid_search", lambda *a, **k: [_hit("p1", 1)])

    result = metrics.answer_quality_metrics(_chat_items(2), 2, "model-A", deadline=None)

    for key in rubrics.RUBRIC_KEYS:
        assert result[key]["status"] == "degraded"
        assert result[key]["value"] is None
        assert result[key]["detail"]["reason"]
    assert result["generation_success_rate"]["value"] == 0.0  # 真实成功数 / 样本数
    assert result["generation_success_rate"]["detail"]["generation_failures"] == 2
    assert result["answer_length_avg"]["status"] != "computed"
    assert result["answer_length_avg"]["value"] is None
    for key in ("answer_exact_match", "levenshtein_similarity"):
        assert result[key]["status"] != "computed"
        assert result[key]["value"] is None
    assert "FROZEN" not in json.dumps(result)


def test_groundedness_degrades_alone_when_knowledge_base_unavailable(monkeypatch):
    def unavailable_search(*args, **kwargs):
        raise OSError("qdrant offline")

    monkeypatch.setattr(metrics, "call_ollama", batch_transport, raising=False)
    monkeypatch.setattr(metrics, "hybrid_search", unavailable_search)

    result = metrics.answer_quality_metrics(_chat_items(1), 1, "model-A", deadline=None)

    assert result["groundedness"]["status"] == "degraded"
    assert result["groundedness"]["value"] is None
    assert result["groundedness"]["detail"]["reason"]
    for key in set(rubrics.RUBRIC_KEYS) - {"groundedness"}:
        assert result[key]["status"] == "computed"


def test_retrieval_relevance_metrics_uses_one_batch_judge_call(monkeypatch):
    calls: list[tuple] = []

    def fake_call_ollama(model, messages, timeout=None, num_predict=None):
        calls.append((model, timeout))
        return json.dumps({"0": "good", "1": "mixed"})

    monkeypatch.setattr(metrics, "call_ollama", fake_call_ollama, raising=False)
    monkeypatch.setattr(metrics, "hybrid_search", lambda q, **k: [_hit("p1", 1, f"chunk for {q}")])

    result = metrics.retrieval_relevance_metrics(_rag_items(), get_strategy("baseline"), 3)

    assert set(result) == {"retrieval_relevance"}
    assert len(calls) == 1  # 整批 2 条样本一次判官调用
    assert calls[0][0] == JUDGE_MODEL
    assert calls[0][1] is not None and calls[0][1] > 0
    assert result["retrieval_relevance"]["status"] == "computed"
    assert result["retrieval_relevance"]["value"] == 0.75
    assert result["retrieval_relevance"]["group"] == "retrieval"


def test_retrieval_relevance_metrics_degrades_on_unparseable_judge(monkeypatch):
    monkeypatch.setattr(metrics, "call_ollama", lambda *a, **k: "no json here", raising=False)
    monkeypatch.setattr(metrics, "hybrid_search", lambda q, **k: [_hit("p1", 1)])
    result = metrics.retrieval_relevance_metrics(_rag_items(), get_strategy("baseline"), 3)
    metric = result["retrieval_relevance"]
    assert metric["status"] == "degraded"
    assert metric["value"] is None
    assert metric["detail"]["reason"]


def test_chat_quality_scores_still_use_enum_maps_and_enum_to_score(monkeypatch):
    judge_calls: list[tuple] = []

    def fake_judge_majority(model, task, question, answer, repeats=1, ctx=None):
        judge_calls.append((model, task, question, answer, repeats, ctx))
        return SimpleNamespace(majority="good")

    monkeypatch.setattr(metrics, "judge_majority", fake_judge_majority)
    score = metrics._judge_score("chat_quality", "question", "answer", None)
    assert score == 1.0  # 由 eval_042.config.ENUM_MAPS 映射，不改映射
    assert judge_calls[0][0] == JUDGE_MODEL
    assert judge_calls[0][1] == "chat_quality"

    monkeypatch.setattr(metrics, "call_ollama", batch_transport, raising=False)
    result = metrics.judge_metrics(_chat_items(2), 2, "model-A")
    assert set(result) == {"chat_quality", "memory_correctness"}
    chat = result["chat_quality"]
    assert chat["detail"]["answer_source"] == "live_generation"
    assert chat["detail"]["generation_model_used"] is True
    assert chat["detail"]["score_mapping"] == "backend/eval_042/config.py::ENUM_MAPS[chat_quality]"
    assert chat["value"] == 1.0
    assert chat["detail"]["judge_mode"] == "batch-enumeration-single-pass"
    assert result["memory_correctness"]["status"] == "needs_ground_truth"
