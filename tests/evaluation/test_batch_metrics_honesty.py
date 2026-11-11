"""批量打分链路的诚实性契约：批次数、sample_count、失败批次隔离、共用 deadline。

判官类 detail 必须如实给出 judge_sample_count / batch_count / total_items；
失败批次只影响该批，绝不写 100 冒充、绝不静默记 0、不把 null 当 0。
"""
from __future__ import annotations

import json
import time

import pytest

from backend.app.evaluation import metrics, rubrics, service
from backend.app.evaluation.contracts import EvaluationError
from backend.app.knowledge_base.infrastructure.retrieve import Hit

RUBRIC7 = dict.fromkeys(rubrics.RUBRIC_KEYS, "good")


def _hit_stub(text: str = "real KB chunk") -> Hit:
    return Hit(paper_id="p1", file_name="p1.pdf", page=1, chunk_index=1,
               text=text, score=1.0, chunker="v1")


def _chat_items(count: int = 100) -> list[dict]:
    return [
        {"trace_id": f"c{i}", "input": f"question {i}", "output": f"FROZEN-{i}",
         "prior_context": None}
        for i in range(1, count + 1)
    ]


def _install_transport(monkeypatch, calls, *, failed=()):
    """按批协议返回结构化响应；failed 里的 (kind, batch_index) 返回不可解析文本。"""
    counter = {"generation": 0, "rubric": 0, "chat": 0, "retrieval": 0}

    def fake(model, messages, timeout=None, num_predict=None):
        system = messages[0]["content"]
        payload = json.loads(messages[-1]["content"])
        if "BATCH GENERATION" in system:
            kind = "generation"
        elif "BATCH RUBRIC" in system:
            kind = "rubric"
        elif "BATCH ANSWER QUALITY" in system:
            kind = "chat"
        else:
            kind = "retrieval"
        index = counter[kind]
        counter[kind] += 1
        calls.append({"kind": kind, "model": model, "batch": index, "size": len(payload),
                      "num_predict": num_predict, "timeout": timeout})
        if (kind, index) in failed:
            return "judge batch output is not json"
        if kind == "generation":
            return json.dumps({key: f"LIVE::{value}" for key, value in payload.items()})
        if kind == "rubric":
            return json.dumps({key: dict(RUBRIC7) for key in payload})
        if kind == "chat":
            return json.dumps(dict.fromkeys(payload, "good"))
        return json.dumps(dict.fromkeys(payload, "good"))

    monkeypatch.setattr(metrics, "call_ollama", fake, raising=False)
    monkeypatch.setattr(metrics, "hybrid_search", lambda *a, **k: [_hit_stub()])


def _deadline() -> float:
    return time.monotonic() + 900.0


def test_100_items_are_scored_in_five_batches_with_honest_counts(monkeypatch):
    calls: list[dict] = []
    _install_transport(monkeypatch, calls)
    items = _chat_items(100)

    answer = metrics.answer_quality_metrics(items, 100, "model-A", deadline=_deadline())
    judged = metrics.judge_metrics(items, 100, "model-A", deadline=_deadline())

    assert metrics.BATCH_SIZE == 20
    for kind in ("generation", "rubric", "chat"):
        selected = [call for call in calls if call["kind"] == kind]
        assert len(selected) == (10 if kind == "generation" else 5)
        assert all(call["size"] == 20 for call in selected)
        assert all(call["num_predict"] is not None and call["num_predict"] >= 2048 for call in selected)
    assert all(call["timeout"] is not None and call["timeout"] > 0 for call in calls)

    for key in rubrics.RUBRIC_KEYS:
        metric = answer[key]
        assert metric["status"] == "computed" and metric["value"] is not None
        assert metric["sample_count"] == 100
        assert metric["detail"]["judge_sample_count"] == 100
        assert metric["detail"]["batch_count"] == 5
        assert metric["detail"]["total_items"] == 100
    for key in ("answer_exact_match", "levenshtein_similarity", "answer_length_avg",
                "generation_success_rate"):
        assert answer[key]["sample_count"] == 100
    chat = judged["chat_quality"]
    assert chat["status"] == "computed" and chat["value"] == 1.0
    assert chat["sample_count"] == 100
    assert chat["detail"]["judge_sample_count"] == 100
    assert chat["detail"]["batch_count"] == 5
    assert chat["detail"]["total_items"] == 100
    assert chat["detail"]["score_mapping"] == "backend/eval_042/config.py::ENUM_MAPS[chat_quality]"
    assert "batch" in chat["detail"]["judge_mode"].lower()
    assert "majority" not in chat["detail"]["judge_mode"].lower()
    assert "多数投票" not in chat["detail"]["judge_mode"]


def test_one_failed_batch_only_removes_its_own_samples(monkeypatch):
    calls: list[dict] = []
    _install_transport(monkeypatch, calls, failed={("rubric", 1)})
    answer = metrics.answer_quality_metrics(_chat_items(100), 100, "model-A", deadline=_deadline())

    for key in rubrics.RUBRIC_KEYS:
        metric = answer[key]
        assert metric["status"] == "computed"
        assert metric["value"] is not None
        assert metric["sample_count"] == 80
        assert metric["detail"]["judge_sample_count"] == 80
        assert metric["detail"]["total_items"] == 100
        assert isinstance(metric["detail"]["reason"], str) and metric["detail"]["reason"]
    # 无 LLM 维度不受判官批次失败牵连，仍对全部 100 条真实计算
    assert answer["answer_exact_match"]["sample_count"] == 100
    assert answer["generation_success_rate"]["sample_count"] == 100
    assert answer["answer_length_avg"]["sample_count"] == 100


def test_all_judge_batches_failed_degrades_without_zero(monkeypatch):
    calls: list[dict] = []
    _install_transport(monkeypatch, calls, failed={("rubric", i) for i in range(5)})
    answer = metrics.answer_quality_metrics(_chat_items(100), 100, "model-A", deadline=_deadline())

    for key in rubrics.RUBRIC_KEYS:
        metric = answer[key]
        assert metric["status"] == "degraded"
        assert metric["value"] is None
        assert isinstance(metric["detail"]["reason"], str) and metric["detail"]["reason"]
        assert metric["detail"]["judge_sample_count"] == 0
    assert answer["generation_success_rate"]["sample_count"] == 100


def test_every_batch_is_guarded_by_the_shared_deadline(monkeypatch):
    calls: list[dict] = []
    _install_transport(monkeypatch, calls)
    with pytest.raises(EvaluationError) as exc:
        metrics.answer_quality_metrics(
            _chat_items(100), 100, "model-A", deadline=time.monotonic() - 1.0
        )
    assert exc.value.code == "EVAL_SCORE_TIMEOUT"
    assert calls == []  # 截止已过，一批外部调用都不发


def test_cross_dataset_early_return_makes_zero_external_calls(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(metrics, "call_ollama", lambda *a, **k: calls.append(1), raising=False)
    monkeypatch.setattr(service.datasets, "load_chat_items", lambda: (_ for _ in ()).throw(AssertionError("must not load")))

    answer = service._answer_quality_metrics(
        dataset_id="rag-retrieval", max_items=100, model="model-A", deadline=_deadline()
    )
    judged = service._judge_metrics(
        dataset_id="rag-retrieval", max_items=100, model="model-A", deadline=_deadline()
    )
    assert calls == []
    assert len(answer) == 11 and len(judged) == 2
    assert all(entry["status"] == "needs_ground_truth" and entry["value"] is None
               for entry in (*answer.values(), *judged.values()))
