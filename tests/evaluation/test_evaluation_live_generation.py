"""被测模型真实参与 chat_quality 的契约测试（离线 fake 注入，不触网）。

spec-047 追加范围三：逐条生成 / 逐条判官改为按批（B=20）链路，本文件断言：
- judge_metrics 把所选被测模型名真实送进批量生成调用，评分对象是实时生成文本；
- 生成失败如实 degraded，不回退冻结 output、不静默记 0；
- 失败批次只影响该批，其余批照常出分，sample_count 如实写实际条数；
- chat_quality 分数仍走 ENUM_MAPS[chat_quality] + enum_to_score，judge_mode 如实标注。
"""
from __future__ import annotations

import json
from functools import partial

from batch_transport_doubles import batch_transport

from backend.app.evaluation import metrics
from backend.app.evaluation.contracts import JUDGE_MODEL, get_strategy
from backend.app.skills.intent import SkillDecision


def _chat_items(count: int = 3) -> list[dict]:
    return [
        {"trace_id": f"c{i}", "input": f"q{i}", "output": f"FROZEN-{i}", "prior_context": None}
        for i in range(1, count + 1)
    ]


def test_judge_metrics_passes_under_test_model_into_batched_live_generation(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        metrics, "call_ollama", partial(batch_transport, calls=calls), raising=False
    )

    result = metrics.judge_metrics(_chat_items(3), 3, "model-A")
    chat = result["chat_quality"]

    gen_calls = [call for call in calls if "BATCH GENERATION" in call["system"]]
    judge_calls = [call for call in calls if "BATCH ANSWER QUALITY" in call["system"]]
    assert len(gen_calls) == 1 and gen_calls[0]["size"] == 3  # 3 条合成 1 批
    assert gen_calls[0]["model"] == "model-A"
    assert gen_calls[0]["num_predict"] is not None
    assert gen_calls[0]["timeout"] is not None and gen_calls[0]["timeout"] > 0
    assert len(judge_calls) == 1 and judge_calls[0]["model"] == JUDGE_MODEL
    assert "FROZEN" not in json.dumps(result)  # 判官拿到的是实时生成文本

    assert chat["status"] == "computed"
    assert chat["value"] == 1.0
    assert chat["sample_count"] == 3
    assert chat["detail"]["judge_sample_count"] == 3
    assert chat["detail"]["total_items"] == 3
    detail = chat["detail"]
    assert detail["answer_source"] == "live_generation"
    assert detail["generation_model_used"] is True
    assert detail["under_test_model"] == "model-A"
    assert detail["judge_model"] == JUDGE_MODEL
    assert detail["generated_count"] == 3
    assert detail["generation_failures"] == 0
    assert detail["judge_mode"] == "batch-enumeration-single-pass"
    assert "多数投票" not in detail["judge_mode"]
    assert detail["score_mapping"] == "backend/eval_042/config.py::ENUM_MAPS[chat_quality]"
    assert "实时生成" in detail["answer_source_note"]
    assert "frozen_fixture_output" not in json.dumps(detail)


def test_judge_metrics_generation_failure_degrades_without_frozen_output_fallback(monkeypatch):
    attempts: list[str] = []

    def failing_call_ollama(model, messages, timeout=None, num_predict=None):
        attempts.append(model)
        raise OSError("model not available locally")

    monkeypatch.setattr(metrics, "call_ollama", failing_call_ollama, raising=False)

    chat = metrics.judge_metrics(_chat_items(2), 2, "online-model")["chat_quality"]

    assert attempts == ["online-model"]  # 真实尝试了生成，而不是直接跳过
    assert chat["status"] == "degraded"
    assert chat["value"] is None
    assert isinstance(chat["detail"]["reason"], str) and chat["detail"]["reason"]
    assert "OSError" in chat["detail"]["reason"]
    assert chat["detail"]["generation_failures"] == 2
    assert chat["detail"]["generated_count"] == 0
    assert chat["detail"]["answer_source"] == "live_generation"
    assert chat["detail"]["under_test_model"] == "online-model"
    assert "FROZEN" not in json.dumps(chat)


def test_failed_generation_batch_only_removes_its_own_samples(monkeypatch):
    monkeypatch.setattr(metrics, "BATCH_SIZE", 1)  # 3 条分 3 批，隔离第 2 批
    state = {"n": 0}

    def flaky_call_ollama(model, messages, timeout=None, num_predict=None, **kwargs):
        if "BATCH GENERATION" in messages[0]["content"]:
            state["n"] += 1
            if state["n"] == 2:
                raise TimeoutError("generation timed out")
        return batch_transport(model, messages, timeout=timeout, num_predict=num_predict, **kwargs)

    monkeypatch.setattr(metrics, "call_ollama", flaky_call_ollama, raising=False)

    chat = metrics.judge_metrics(_chat_items(3), 3, "model-A")["chat_quality"]

    assert state["n"] == 3  # 三批都真实尝试生成
    assert chat["status"] == "computed" and chat["value"] is not None
    assert chat["sample_count"] == 2  # 只去掉失败那一批，其余照常出分
    assert chat["detail"]["judge_sample_count"] == 2
    assert chat["detail"]["total_items"] == 3
    assert chat["detail"]["generation_failures"] == 1
    assert "TimeoutError" in chat["detail"]["reason"]
    assert "FROZEN" not in json.dumps(chat)


def test_intent_and_retrieval_metrics_mark_selected_model_not_participating(monkeypatch):
    monkeypatch.setattr(
        metrics, "detect_skill", lambda message, skills: SkillDecision(status="none")
    )
    monkeypatch.setattr(metrics, "hybrid_search", lambda *args, **kwargs: [])

    rag = metrics.retrieval_metrics(
        [{"question": "Q1", "relevant_doc_ids": [{"paper_id": "p1", "chunker": "v1", "chunk_index": 1}]}],
        get_strategy("baseline"),
        3,
    )
    for key in ("recall@k", "precision@k", "mrr@k"):
        detail = rag[key]["detail"]
        assert detail["model_participates"] is False
        assert isinstance(detail["model_participates_reason"], str) and detail["model_participates_reason"]

    intent = metrics.intent_metrics([{"message": "hello", "expected_intent": "none"}], 3)
    detail = intent["intent_accuracy"]["detail"]
    assert detail["model_participates"] is False
    assert isinstance(detail["model_participates_reason"], str) and detail["model_participates_reason"]
