"""spec-042 Task 04 eval_run 纯函数单测（无网络请求）。

覆盖：
1. classify_for_task 四分支：scored / empty_output / intake_text / no_prior_context
   （含 memory_correctness 有 prior_context 时应 scored）；
2. human_agree：全对 / 部分对 / 缺标注项不计入分母 / 混淆矩阵维度正确（3x3 good/partial/poor）。
"""
from __future__ import annotations

import pytest
from eval_042.eval_run import classify_for_task, human_agree

# ---------- classify_for_task ----------

def _item(output, prior_context=None, synthetic=False):
    return {
        "trace_id": "tid-x",
        "task": "chat_quality",
        "input": "q",
        "output": output,
        "prior_context": prior_context,
        "synthetic": synthetic,
    }


def test_classify_scored_normal():
    # 真实短回答仍判 scored
    assert classify_for_task(_item("Hi there"), "chat_quality") == ("scored", None)


def test_classify_empty_output():
    assert classify_for_task(_item(""), "chat_quality") == ("skipped", "empty_output")
    assert classify_for_task(_item(None), "chat_quality") == ("skipped", "empty_output")
    assert classify_for_task(_item("   "), "chat_quality") == ("skipped", "empty_output")


def test_classify_intake_text():
    out = "研究 Intake 已保存：已为你创建研究任务"
    assert classify_for_task(_item(out), "chat_quality") == ("skipped", "intake_text")


def test_classify_no_prior_context_memory():
    # 边界 9：memory_correctness 且无 prior_context -> skipped/no_prior_context
    it = _item("这是某条真实回答", prior_context=None)
    assert classify_for_task(it, "memory_correctness") == ("skipped", "no_prior_context")


def test_classify_memory_with_prior_context_scored():
    # memory_correctness 有有效 prior_context -> scored（不触发边界 9）
    it = _item("这是某条真实回答", prior_context="用户曾说：预算 5000 元")
    assert classify_for_task(it, "memory_correctness") == ("scored", None)


def test_classify_empty_takes_precedence_over_boundary9():
    # 空 output 优先于边界 9（先 classify_output，再边界 9）
    it = _item("", prior_context=None)
    assert classify_for_task(it, "memory_correctness") == ("skipped", "empty_output")


# ---------- human_agree ----------

def _rec(tid, label, comment="exp"):
    return {"trace_id": tid, "status": "scored", "label": label, "comment": comment}


def test_human_agree_all_match():
    results = [_rec("a", "good"), _rec("b", "partial"), _rec("c", "poor")]
    ref = {"a": "good", "b": "partial", "c": "poor"}
    out = human_agree(results, ref)
    assert out["n"] == 3
    assert out["agree_rate"] == 1.0
    assert out["verdict"] == "ok"
    assert out["disagreements"] == []
    # 混淆矩阵对角线各 +1
    assert out["confusion_matrix"]["good"]["good"] == 1
    assert out["confusion_matrix"]["partial"]["partial"] == 1
    assert out["confusion_matrix"]["poor"]["poor"] == 1


def test_human_agree_partial():
    # 3 条中 1 条不一致 -> agree_rate=2/3≈0.6667，落在 needs_calibration(0.60-0.70)
    results = [_rec("a", "good"), _rec("b", "partial"), _rec("c", "poor")]
    ref = {"a": "good", "b": "good", "c": "poor"}
    out = human_agree(results, ref)
    assert out["n"] == 3
    assert out["agree_rate"] == pytest.approx(2 / 3)
    assert out["verdict"] == "needs_calibration"
    assert len(out["disagreements"]) == 1
    assert out["disagreements"][0]["trace_id"] == "b"
    assert out["disagreements"][0]["human"] == "good"
    assert out["disagreements"][0]["judge"] == "partial"
    assert out["confusion_matrix"]["good"]["partial"] == 1
    assert out["confusion_matrix"]["good"]["good"] == 1
    assert out["confusion_matrix"]["poor"]["poor"] == 1


def test_human_agree_missing_annotation_excluded():
    # d 在 results 但不在 reference -> 不计入分母（n=3 而非 4）
    results = [
        _rec("a", "good"), _rec("b", "partial"),
        _rec("c", "poor"), _rec("d", "good"),
    ]
    ref = {"a": "good", "b": "partial", "c": "poor"}  # 无 d
    out = human_agree(results, ref)
    assert out["n"] == 3
    assert out["agree_rate"] == 1.0


def test_human_agree_skipped_excluded():
    # unavailable / skipped 记录不计入分母
    results = [
        _rec("a", "good"),
        {"trace_id": "e", "status": "unavailable", "label": None},
        {"trace_id": "f", "status": "skipped", "skip_reason": "empty_output", "label": None},
    ]
    ref = {"a": "good"}
    out = human_agree(results, ref)
    assert out["n"] == 1
    assert out["agree_rate"] == 1.0


def test_human_agree_confusion_dimensions():
    out = human_agree([], {})
    cm = out["confusion_matrix"]
    assert set(cm.keys()) == {"good", "partial", "poor"}
    for row in cm.values():
        assert set(row.keys()) == {"good", "partial", "poor"}


def test_human_agree_trigger_fallback_when_low():
    # 全错且 n=2 -> 0.0 < 0.60 -> trigger_fallback_review
    results = [_rec("a", "good"), _rec("b", "partial")]
    ref = {"a": "poor", "b": "good"}
    out = human_agree(results, ref)
    assert out["agree_rate"] == 0.0
    assert out["verdict"] == "trigger_fallback_review"
