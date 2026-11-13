"""chat-quality 打分链路共享一次批量实时生成的契约（NO_GO 后范围内性能修复）。

首轮 100 条 Go/No-Go 超时（EVAL_SCORE_TIMEOUT）的根因是 ``judge_metrics`` 与
``answer_quality_metrics`` 各自调用一次 ``generate_live_answers``，100 条被所选
被测模型实时生成两遍（10 批而非 5 批）。本文件断言修复后经 ``service.score()``
一次请求只生成一遍（5 批），两个指标族拿到同一批 answers / failure_types，
且 sample_count / batch_count / total_items 与反伪造红线逐字不变。

所有传输层调用都用既有 ``batch_transport_doubles`` 离线替身，不触网、不发真实 HTTP。
"""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pytest
from batch_transport_doubles import batch_transport

from backend.app.api import routes_models
from backend.app.evaluation import datasets, metrics, service, store
from backend.app.evaluation.contracts import METRIC_GROUPS, METRIC_KEYS
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.skills.intent import SkillDecision

CHAT = "chat-quality"
INTENT = "intent-classification"
MODEL = "fake-model"

RUBRIC_KEYS = (
    "answer_relevance", "conciseness", "helpfulness", "groundedness",
    "hallucination_free", "toxicity_free", "pii_leakage_free",
)
ANSWER_QUALITY_NEW_KEYS = (
    *RUBRIC_KEYS, "answer_exact_match", "levenshtein_similarity",
    "generation_success_rate", "answer_length_avg",
)


def _chat_items(count: int = 100) -> list[dict]:
    """output 用 FROZEN 前缀，便于断言没有回退冻结输出冒充实时生成答案。"""
    return [
        {
            "id": f"c{i}", "status": "scored", "input": f"q{i}", "output": f"FROZEN-{i}",
            "synthetic": True, "reference_source": "frozen-042-trace", "prior_context": None,
        }
        for i in range(1, count + 1)
    ]


def _gold(dataset_id: str, items: list[dict]) -> dict:
    return {
        "dataset_id": dataset_id,
        "schema_version": "builtin-evaluation-dataset-v1",
        "source": "builtin-fixture",
        "synthetic": True,
        "label_source": "kb-derived + frozen-042-trace",
        "items": items,
    }


def _hit() -> Hit:
    return Hit(paper_id="p1", file_name="p1.pdf", page=1, chunk_index=1,
               text="real KB chunk", score=1.0, chunker="v1")


@pytest.fixture
def transport_calls(monkeypatch, tmp_path: Path) -> list[dict]:
    """离线替身：唯一传输层 call_ollama 不触网；gold / run 目录隔离到 tmp。"""
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "builtin-chat-quality.json").write_text(
        json.dumps(_gold(CHAT, _chat_items(100))), encoding="utf-8"
    )
    (gold / "builtin-intent-classification.json").write_text(
        json.dumps(_gold(INTENT, [{"message": "m1", "expected_intent": "kb_search"}])),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(datasets, "GOLD_DIR", gold)
    monkeypatch.setattr(store, "RUNS_DIR", runs)
    monkeypatch.setattr(routes_models, "_build_local_models", lambda: [{"id": MODEL}])
    monkeypatch.setattr(routes_models, "_build_online_models", lambda *a, **k: [])
    monkeypatch.setattr(
        metrics, "reranker_health",
        lambda *a, **k: {"enabled": True, "available": False, "reason": "offline"},
    )
    monkeypatch.setattr(metrics, "hybrid_search", lambda *a, **k: [_hit()])
    monkeypatch.setattr(metrics, "detect_skill", lambda message, skills: SkillDecision(status="none"))
    calls: list[dict] = []
    monkeypatch.setattr(metrics, "call_ollama", partial(batch_transport, calls=calls), raising=False)
    return calls


def _body(**overrides) -> dict:
    body = {"strategy_id": "baseline", "model": MODEL, "dataset_id": CHAT, "max_items": 100}
    body.update(overrides)
    return body


def _metric(document: dict, key: str) -> dict:
    return next(entry for entry in document["metrics"] if entry["key"] == key)


def _generation_calls(calls: list[dict]) -> list[dict]:
    return [call for call in calls if "BATCH GENERATION" in call["system"]]


def test_one_score_request_runs_a_single_five_batch_generation_sequence(transport_calls):
    """100 条只生成一遍：5 批 × 20 条，而不是两遍 10 批。"""
    document = service.score(_body())

    gen_calls = _generation_calls(transport_calls)
    assert metrics.BATCH_SIZE == 20
    assert len(gen_calls) == 5
    assert [call["size"] for call in gen_calls] == [20] * 5
    assert all(call["model"] == MODEL for call in gen_calls)
    assert all(call["num_predict"] == metrics.BATCH_NUM_PREDICT for call in gen_calls)
    assert all(call["timeout"] is not None and call["timeout"] > 0 for call in gen_calls)
    assert len(document["metrics"]) == len(METRIC_KEYS) == 22


def test_judge_and_answer_quality_receive_the_same_live_answers(transport_calls, monkeypatch):
    """两个指标族拿到同一个生成结果对象（同一批 answers 与 failure_types）。"""
    real_generate = metrics.generate_live_answers
    real_judge = metrics.judge_metrics
    real_answer = metrics.answer_quality_metrics
    generated: list[tuple] = []
    seen_live: list[tuple[str, object]] = []

    def spy_generate(questions, under_test_model, deadline):
        result = real_generate(questions, under_test_model, deadline)
        generated.append(result)
        return result

    def spy_judge(*args, **kwargs):
        seen_live.append(("judge", kwargs.get("live")))
        return real_judge(*args, **kwargs)

    def spy_answer(*args, **kwargs):
        seen_live.append(("answer", kwargs.get("live")))
        return real_answer(*args, **kwargs)

    monkeypatch.setattr(metrics, "generate_live_answers", spy_generate)
    monkeypatch.setattr(metrics, "judge_metrics", spy_judge)
    monkeypatch.setattr(metrics, "answer_quality_metrics", spy_answer)

    service.score(_body())

    assert len(generated) == 1
    assert [name for name, _ in seen_live] == ["judge", "answer"]
    judge_live, answer_live = seen_live[0][1], seen_live[1][1]
    assert judge_live is not None and answer_live is not None
    assert judge_live is generated[0]
    assert answer_live is generated[0]
    assert judge_live[0] is answer_live[0]
    assert len(judge_live[0]) == 100


def test_shared_generation_keeps_counts_and_anti_forgery_detail(transport_calls):
    """共享生成后计数 / 分数映射 / 反伪造标注逐字不变，且不回退冻结 output。"""
    document = service.score(_body())

    chat = _metric(document, "chat_quality")
    assert chat["status"] == "computed"
    assert chat["sample_count"] == 100
    assert chat["detail"]["judge_sample_count"] == 100
    assert chat["detail"]["batch_count"] == 5
    assert chat["detail"]["total_items"] == 100
    assert chat["detail"]["generated_count"] == 100
    assert chat["detail"]["generation_failures"] == 0
    assert chat["detail"]["answer_source"] == "live_generation"
    assert chat["detail"]["generation_model_used"] is True
    assert chat["detail"]["score_mapping"] == "backend/eval_042/config.py::ENUM_MAPS[chat_quality]"
    assert "batch" in chat["detail"]["judge_mode"].lower()

    for key in ANSWER_QUALITY_NEW_KEYS:
        metric = _metric(document, key)
        assert metric["status"] == "computed"
        assert metric["sample_count"] == 100
        assert metric["detail"]["answer_source"] == "live_generation"

    # 实时答案 LIVE::qN 与冻结 FROZEN-N 不同：0 条字面匹配，证明没有拿冻结 output 冒充。
    assert _metric(document, "answer_exact_match")["value"] == 0.0


def test_shared_generation_failures_degrade_both_families_honestly(transport_calls, monkeypatch):
    """生成失败只尝试一遍，failure_types 也被共享，两族都如实 degraded、不静默记 0。"""
    def offline_generation(model, messages, timeout=None, num_predict=None):
        if "BATCH GENERATION" in messages[0]["content"]:
            transport_calls.append({
                "model": model, "system": messages[0]["content"],
                "size": len(json.loads(messages[-1]["content"])),
                "timeout": timeout, "num_predict": num_predict,
            })
            raise OSError("model offline")
        return batch_transport(model, messages, timeout=timeout, num_predict=num_predict)

    monkeypatch.setattr(metrics, "call_ollama", offline_generation, raising=False)

    document = service.score(_body())

    gen_calls = _generation_calls(transport_calls)
    assert len(gen_calls) == 5  # 失败路径仍只尝试一遍（5 批），不是 10 批

    chat = _metric(document, "chat_quality")
    assert chat["status"] == "degraded"
    assert chat["value"] is None
    assert chat["detail"]["generation_failures"] == 100
    assert chat["detail"]["generated_count"] == 0
    assert "OSError" in chat["detail"]["reason"]

    for key in RUBRIC_KEYS:
        metric = _metric(document, key)
        assert metric["status"] == "degraded"
        assert metric["value"] is None
        assert metric["detail"]["generation_failures"] == 100
        # 既有 degraded 文案逐字：该分支只列失败条数与反伪造声明，不列异常类型名。
        assert "被测模型实时生成失败 100/100 条，无评分对象" in metric["detail"]["reason"]
        assert "不回退冻结输出、不记 0" in metric["detail"]["reason"]
    assert _metric(document, "answer_exact_match")["status"] == "degraded"


def test_non_chat_dataset_skips_shared_generation_entirely(transport_calls):
    """跨 dataset 早退分支零外部调用：不加载 chat 轨迹、不启动任何实时生成。"""
    document = service.score(_body(dataset_id=INTENT))

    assert [entry["key"] for entry in document["metrics"]] == list(METRIC_KEYS)
    assert all(entry["group"] == METRIC_GROUPS[entry["key"]] for entry in document["metrics"])
    assert _generation_calls(transport_calls) == []
    for key in ANSWER_QUALITY_NEW_KEYS:
        assert _metric(document, key)["status"] == "needs_ground_truth"
