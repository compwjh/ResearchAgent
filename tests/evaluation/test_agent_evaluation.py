"""spec-042 Task 02：评测模块纯函数单测（离线、无网络）。

覆盖：SKIPPED 分类（空/Intake 文案/真实短回答）、R4 解析、枚举->分数、离线出口守卫。
不触发任何网络调用；网络函数（collect_eval_items/judge_one）另有实证步骤验证。
"""
from backend.eval_042.judge_client import enum_to_score, parse_r4
from backend.eval_042.langfuse_export import build_eval_item, classify_output
from backend.eval_042.offline_guard import assert_loopback, is_loopback


def test_classify_empty_output_is_skipped():
    assert classify_output("") == ("skipped", "empty_output")
    assert classify_output(None) == ("skipped", "empty_output")
    assert classify_output("   \n") == ("skipped", "empty_output")


def test_classify_intake_text_is_skipped():
    intake = "研究 Intake 已保存：已为你创建研究任务，本消息由技能路由生成。"
    status, reason = classify_output(intake)
    assert status == "skipped" and reason == "intake_text"


def test_classify_real_short_answer_is_scored_not_skipped():
    # 真实短回答（如 Hi there）必须进入评分，由判官打 poor，而非被 SKIP 静默 0 分
    assert classify_output("Hi there") == ("scored", None)
    assert classify_output("好的。") == ("scored", None)


def test_build_eval_item_synthetic_intake_marker():
    it = build_eval_item(
        "synthetic-intake-1", "帮我研究一下 X",
        "研究 Intake 已保存：已创建研究任务。", synthetic=True)
    assert it.status == "skipped"
    assert it.skip_reason == "intake_text"
    assert it.synthetic is True


def test_parse_r4_valid_label():
    text = "Explanation: fully relevant.\nAnswer: good"
    label, exp = parse_r4(text, {"good", "partial", "poor"})
    assert label == "good"
    assert "fully relevant" in exp


def test_parse_r4_handles_punctuation_and_case():
    assert parse_r4("Answer: Good.", {"good", "partial", "poor"})[0] == "good"
    assert parse_r4("ANSWER: PARTIAL", {"good", "partial", "poor"})[0] == "partial"


def test_parse_r4_invalid_label_returns_none():
    assert parse_r4("Answer: excellent", {"good", "partial", "poor"})[0] is None
    assert parse_r4("no answer line here", {"good"})[0] is None


def test_enum_to_score_maps_and_rejects_unknown():
    assert enum_to_score("chat_quality", "good") == 1.0
    assert enum_to_score("chat_quality", "partial") == 0.5
    assert enum_to_score("chat_quality", "poor") == 0.0
    assert enum_to_score("memory_correctness", "remembered") == 1.0
    assert enum_to_score("memory_correctness", "fabricated") == 0.0
    assert enum_to_score("chat_quality", "bogus") is None
    assert enum_to_score("chat_quality", None) is None


def test_offline_guard_allows_loopback_blocks_external():
    assert is_loopback("http://localhost:11434/v1")
    assert is_loopback("http://127.0.0.1:3000/api/public/traces")
    # 外部主机必须被拒（离线硬约束）
    for bad in ("http://api.openai.com/v1", "http://8.8.8.8:80/x", "https://example.com"):
        try:
            assert_loopback(bad)
            raise AssertionError(f"expected OfflineGuardError for {bad}")
        except Exception as e:  # OfflineGuardError
            assert "offline guard" in str(e).lower()
