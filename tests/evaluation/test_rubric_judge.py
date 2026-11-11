"""联合判官 rubric：唯一传输层复用、JSON 容错解析、解析失败整批降级。

反伪造红线：判官输出无法解析时，7 个新判官维度一律 degraded + value=null +
detail.reason，绝不逐维度编造分数、绝不静默记 0。
"""
from __future__ import annotations

import json

import pytest

from backend.app.evaluation import metrics, rubrics
from backend.app.evaluation.contracts import JUDGE_MODEL


def _valid_payload() -> dict:
    return dict.fromkeys(rubrics.RUBRIC_KEYS, "good")


def _chat_items(count: int = 2) -> list[dict]:
    return [
        {"trace_id": f"c{i}", "input": f"q{i}", "output": f"FROZEN-{i}", "prior_context": None}
        for i in range(1, count + 1)
    ]


def _hit_stub(text: str):
    from backend.app.knowledge_base.infrastructure.retrieve import Hit

    return Hit(paper_id="p1", file_name="p1.pdf", page=1, chunk_index=1, text=text, score=1.0)


def test_rubric_keys_are_exactly_the_seven_joint_dimensions():
    assert rubrics.RUBRIC_KEYS == (
        "answer_relevance",
        "conciseness",
        "helpfulness",
        "groundedness",
        "hallucination_free",
        "toxicity_free",
        "pii_leakage_free",
    )


def test_parse_rubric_response_accepts_plain_json_and_maps_enums():
    payload = _valid_payload()
    payload["conciseness"] = "mixed"
    payload["hallucination_free"] = "poor"
    scores = rubrics.parse_rubric_response(json.dumps(payload))
    assert set(scores) == set(rubrics.RUBRIC_KEYS)
    assert scores["answer_relevance"] == 1.0
    assert scores["conciseness"] == 0.5
    assert scores["hallucination_free"] == 0.0


@pytest.mark.parametrize(
    "text",
    [
        "```json\n" + json.dumps(_valid_payload()) + "\n```",
        "```\n" + json.dumps(_valid_payload()) + "\n```",
        "判官说明：\n" + json.dumps(_valid_payload()) + "\n以上为结果。",
    ],
)
def test_parse_rubric_response_tolerates_code_fences_and_surrounding_prose(text):
    assert rubrics.parse_rubric_response(text) == dict.fromkeys(rubrics.RUBRIC_KEYS, 1.0)


@pytest.mark.parametrize(
    "text",
    [
        "not a json object at all",
        "",
        "   ",
        "[]",
        json.dumps({"answer_relevance": "good"}),  # 缺关键字段
        json.dumps({**_valid_payload(), "toxicity_free": "excellent"}),  # 非法枚举
        json.dumps({**_valid_payload(), "conciseness": 1}),  # 非字符串枚举
        json.dumps({**_valid_payload(), "helpfulness": None}),
    ],
)
def test_parse_rubric_response_raises_value_error_on_invalid_payload(text):
    with pytest.raises(ValueError):
        rubrics.parse_rubric_response(text)


def test_parse_rubric_response_supports_custom_keys_for_batch_retrieval_relevance():
    assert rubrics.parse_rubric_response(
        '{"0": "poor", "1": "good"}', keys=("0", "1")
    ) == {"0": 0.0, "1": 1.0}
    with pytest.raises(ValueError):
        rubrics.parse_rubric_response('{"0": "good"}', keys=("0", "1"))


def test_judge_rubrics_uses_the_single_existing_ollama_transport(monkeypatch):
    calls: list[tuple] = []

    def fake_call_ollama(model, messages, timeout=180):
        calls.append((model, messages, timeout))
        return json.dumps(_valid_payload())

    monkeypatch.setattr(rubrics, "call_ollama", fake_call_ollama)
    scores = rubrics.judge_rubrics("question", "answer", "context", timeout=12.5)

    assert len(calls) == 1  # 一次调用出全部 7 个 rubric 标签
    assert calls[0][0] == JUDGE_MODEL  # 判官模型固定，与被测模型无关
    assert calls[0][2] == 12.5
    assert "JSON" in calls[0][1][0]["content"]
    assert all(key in calls[0][1][0]["content"] for key in rubrics.RUBRIC_KEYS)
    assert set(scores) == set(rubrics.RUBRIC_KEYS)


def test_judge_rubrics_propagates_parse_failure_instead_of_inventing_scores(monkeypatch):
    monkeypatch.setattr(rubrics, "call_ollama", lambda *a, **k: "I cannot decide")
    with pytest.raises(ValueError):
        rubrics.judge_rubrics("question", "answer", "context", timeout=10)


def test_joint_judge_failure_degrades_all_seven_dimensions_at_once(monkeypatch):
    def fake_call_ollama(model, messages, timeout=None, num_predict=None):
        system = messages[0]["content"]
        if "BATCH GENERATION" in system:
            payload = json.loads(messages[-1]["content"])
            return json.dumps({key: "LIVE::" + str(value) for key, value in payload.items()})
        return "judge output is not json"  # 判官整批不可解析

    monkeypatch.setattr(metrics, "call_ollama", fake_call_ollama, raising=False)
    monkeypatch.setattr(metrics, "hybrid_search", lambda *a, **k: [_hit_stub("real KB chunk")])

    result = metrics.answer_quality_metrics(_chat_items(2), 2, "model-A", deadline=None)

    for key in rubrics.RUBRIC_KEYS:
        metric = result[key]
        assert metric["status"] == "degraded"
        assert metric["value"] is None
        assert isinstance(metric["detail"]["reason"], str) and metric["detail"]["reason"]
        expected_group = "safety" if key in ("toxicity_free", "pii_leakage_free") else "answer_quality"
        assert metric["group"] == expected_group
    # 规则类与生成诊断仍基于真实生成结果出分，不受判官解析失败牵连。
    assert result["answer_exact_match"]["status"] == "computed"
    assert result["levenshtein_similarity"]["status"] == "computed"
    assert result["generation_success_rate"]["value"] == 1.0
    assert result["answer_length_avg"]["status"] == "computed"
