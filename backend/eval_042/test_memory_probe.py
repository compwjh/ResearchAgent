"""spec-042 Task 03 记忆探针纯函数单测（无网络请求）。

覆盖：
1. 探针集结构自检（20 条 / 4 类各 5 / gold 合法 / probe_id 唯一 / synthetic 全 True）；
2. build_probe_dataset 产出与 EvalItem 兼容的 dict；
3. judge_client.parse_r4 对四类标签的解析（含大小写/多余空白）；
4. langfuse_export.classify_output 的 SKIPPED 边界不回归。
"""
from __future__ import annotations

import pytest
from eval_042 import config
from eval_042.judge_client import parse_r4
from eval_042.langfuse_export import classify_output
from eval_042.memory_probe import MEMORY_PROBES, MemoryProbe, build_probe_dataset

VALID_GOLDS = {"remembered", "partially_remembered", "forgotten", "fabricated"}


def test_probe_count_is_20():
    assert len(MEMORY_PROBES) == 20


def test_probe_gold_four_classes_each_5():
    from collections import Counter
    cnt = Counter(p.gold for p in MEMORY_PROBES)
    assert set(cnt.keys()) == VALID_GOLDS
    for g, n in cnt.items():
        assert n == 5, f"gold 类 {g} 应为 5 条，实为 {n}"


def test_probe_gold_values_valid():
    for p in MEMORY_PROBES:
        assert p.gold in VALID_GOLDS, f"{p.probe_id} gold 非法: {p.gold}"


def test_probe_ids_unique():
    ids = [p.probe_id for p in MEMORY_PROBES]
    assert len(ids) == len(set(ids)), "probe_id 存在重复"


def test_probe_synthetic_all_true():
    for p in MEMORY_PROBES:
        assert p.synthetic is True, f"{p.probe_id} synthetic 应为 True"


def test_probe_is_dataclass_with_fields():
    p = MEMORY_PROBES[0]
    assert isinstance(p, MemoryProbe)
    for f in ("probe_id", "prior_context", "question", "answer", "gold", "synthetic"):
        assert hasattr(p, f), f"MemoryProbe 缺字段 {f}"


def test_build_probe_dataset_compat():
    ds = build_probe_dataset()
    assert len(ds) == 20
    for i, item in enumerate(ds, start=1):
        assert item["task"] == "memory_correctness"
        assert item["trace_id"] == f"synthetic-memory-probe-{i}"
        assert item["status"] == "scored"
        assert item["synthetic"] is True
        assert item["gold"] in VALID_GOLDS
        # input 必须含 prior_context 与「追问：」标记，output 为 answer
        assert item["input"].startswith(MEMORY_PROBES[i - 1].prior_context)
        assert "追问：" in item["input"]
        assert item["output"] == MEMORY_PROBES[i - 1].answer


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Answer: remembered", "remembered"),
        ("Explanation: 复述了偏好\nAnswer: partially_remembered", "partially_remembered"),
        ("ANSWER:   FORGOTTEN  ", "forgotten"),
        ("answer:\tfabricated", "fabricated"),
        ("Answer: REMEMBERED.", "remembered"),  # 尾点不应污染
    ],
)
def test_parse_r4_four_labels(raw, expected):
    label, _ = parse_r4(raw, VALID_GOLDS)
    assert label == expected


def test_parse_r4_invalid_label_returns_none():
    label, _ = parse_r4("Answer: unknown_label", VALID_GOLDS)
    assert label is None


def test_parse_r4_empty_returns_none():
    label, _ = parse_r4("", VALID_GOLDS)
    assert label is None


def test_classify_output_empty_is_skipped():
    assert classify_output("") == ("skipped", "empty_output")
    assert classify_output(None) == ("skipped", "empty_output")
    assert classify_output("   ") == ("skipped", "empty_output")


def test_classify_output_intake_is_skipped():
    txt = "研究 Intake 已保存：已为你创建研究任务"
    assert classify_output(txt) == ("skipped", "intake_text")


def test_classify_output_normal_is_scored():
    assert classify_output("Hi there") == ("scored", None)
    assert classify_output("根据您的偏好推荐美式咖啡") == ("scored", None)


def test_chat_quality_config_unchanged():
    # 回归护栏：chat_quality 的 prompt 不应被本 Task 改动
    tmpl = config.PROMPTS["chat_quality"]["user_tmpl"]
    assert "{q}" in tmpl and "{a}" in tmpl
    assert "{ctx}" not in tmpl  # chat_quality 仍不依赖 ctx


def test_memory_config_thresholds_present():
    assert config.GOLD_ACC_THRESHOLD == 0.80
    assert config.CROSS_AGREE_THRESHOLD == 0.80
    assert config.SELF_CONSISTENCY_THRESHOLD == 0.90
