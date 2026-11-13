"""批量判官 JSON 协议解析契约：正常 / 围栏 / 缺字段 / 非法枚举 / 非 JSON 一律诚实失败。

批量生成、批量 7-rubric、批量 chat_quality 只认「索引字符串 -> 值」的严格 JSON
object；解析失败向上抛 ValueError，由上层整批 degraded + reason，绝不逐维度编造分数。
"""
from __future__ import annotations

import json

import pytest

from backend.app.evaluation import rubrics
from backend.app.evaluation.contracts import RUBRIC_ENUM_MAPS
from backend.eval_042.config import ENUM_MAPS
from backend.eval_042.judge_client import enum_to_score

RUBRIC7 = dict.fromkeys(rubrics.RUBRIC_KEYS, "good")


def _batch(values) -> str:
    return json.dumps({str(index): value for index, value in enumerate(values)})


@pytest.mark.parametrize(
    "text",
    [
        _batch(["a1", "a2"]),
        "```json\n" + _batch(["a1", "a2"]) + "\n```",
        "判官说明\n" + _batch(["a1", "a2"]) + "\n结束",
    ],
)
def test_parse_batch_generation_accepts_strict_indices_and_fences(text):
    assert rubrics.parse_batch_generation_response(text, 2) == ["a1", "a2"]


def test_parse_batch_generation_single_item_needs_no_index_wrapper():
    assert rubrics.parse_batch_generation_response("LIVE::q1", 1) == ["LIVE::q1"]


@pytest.mark.parametrize(
    "text,count",
    [
        ("not json", 2), ("", 2), ("[]", 2),
        (_batch(["a1"]), 2),              # 缺一条
        (_batch(["a1", "  "]), 2),        # 空回答
        (_batch(["a1", 3]), 2),           # 非字符串答案
    ],
)
def test_parse_batch_generation_rejects_incomplete_or_empty_batches(text, count):
    with pytest.raises(ValueError):
        rubrics.parse_batch_generation_response(text, count)


@pytest.mark.parametrize(
    "text",
    [
        _batch([RUBRIC7, RUBRIC7]),
        "```json\n" + _batch([RUBRIC7, RUBRIC7]) + "\n```",
    ],
)
def test_parse_batch_rubric_maps_all_seven_enums(text):
    scores = rubrics.parse_batch_rubric_response(text, 2)
    assert len(scores) == 2
    for entry in scores:
        assert set(entry) == set(rubrics.RUBRIC_KEYS)
        assert all(value == 1.0 for value in entry.values())


def test_parse_batch_rubric_single_item_accepts_legacy_seven_key_object():
    assert rubrics.parse_batch_rubric_response(json.dumps(RUBRIC7), 1) == [
        dict.fromkeys(rubrics.RUBRIC_KEYS, 1.0)
    ]


@pytest.mark.parametrize(
    "payload",
    [
        _batch([RUBRIC7]),                                                    # 缺一批
        _batch([{**RUBRIC7, "conciseness": "excellent"}, RUBRIC7]),            # 非法枚举
        _batch([{k: v for k, v in RUBRIC7.items() if k != "helpfulness"}, RUBRIC7]),  # 缺字段
        _batch([RUBRIC7, 5]),                                                  # 非 dict
        "judge output is not json",
    ],
)
def test_parse_batch_rubric_rejects_any_invalid_dimension_for_whole_batch(payload):
    with pytest.raises(ValueError):
        rubrics.parse_batch_rubric_response(payload, 2)


def test_parse_batch_chat_quality_labels_still_map_through_enum_to_score():
    labels = rubrics.parse_batch_chat_quality_response(_batch(["good", "partial", "poor"]), 3)
    assert labels == ["good", "partial", "poor"]
    assert [enum_to_score("chat_quality", label) for label in labels] == [1.0, 0.5, 0.0]
    assert set(ENUM_MAPS["chat_quality"]) == {"good", "partial", "poor"}


def test_parse_batch_chat_quality_rejects_invalid_enum_or_non_json():
    with pytest.raises(ValueError):
        rubrics.parse_batch_chat_quality_response(_batch(["good", "excellent"]), 2)
    with pytest.raises(ValueError):
        rubrics.parse_batch_chat_quality_response("no json", 2)


def test_batch_messages_carry_string_indices_and_all_rubric_names():
    rubric_messages = rubrics.build_batch_rubric_messages(
        [{"question": "q0", "answer": "a0", "context": "c0"},
         {"question": "q1", "answer": "a1", "context": "c1"}]
    )
    assert set(json.loads(rubric_messages[-1]["content"])) == {"0", "1"}
    assert "JSON" in rubric_messages[0]["content"]
    assert all(key in rubric_messages[0]["content"] for key in rubrics.RUBRIC_KEYS)

    generation_messages = rubrics.build_batch_generation_messages(["q0", "q1"])
    assert set(json.loads(generation_messages[-1]["content"])) == {"0", "1"}

    chat_messages = rubrics.build_batch_chat_quality_messages(
        [{"question": "q0", "answer": "a0"}, {"question": "q1", "answer": "a1"}]
    )
    assert set(json.loads(chat_messages[-1]["content"])) == {"0", "1"}
    assert RUBRIC_ENUM_MAPS == {"good": 1.0, "mixed": 0.5, "poor": 0.0}
