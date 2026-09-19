"""Spec025 Task02：token 计量与预算配置的单测与回归快照。

覆盖：
- estimate_tokens 空串/None 返回 0、纯中文、中英混排、超长。
- chars_for_tokens 向下取整与 estimate_tokens 互逆（偏差 <= 1）。
- CHAT_TOTAL_TOKEN_BUDGET=0/负数时 _env_positive_number 回退默认值并发告警。
- compose_chat_prompt 默认输出与「现状数值」(1500/6000/6000) 逐字符一致（回归快照）。
- 第 253 行项目指令按 CHAT_PROJECT_INSTR_CHARS(5000) 截断。
"""
import importlib
import os
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import backend.app.platform.config as config
from backend.app.chat.application.conversation_service import compose_chat_prompt
from backend.app.chat.application.token_budget import (
    CHARS_PER_TOKEN,
    chars_for_tokens,
    estimate_tokens,
)


def test_chat_per_token_constant_is_1_6():
    assert CHARS_PER_TOKEN == 1.6


def test_estimate_tokens_empty_and_none_return_zero():
    # spec 要求：空串 / None 返回 0（空白串按字符计，不在此列）。
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0


def test_estimate_tokens_pure_chinese():
    # ceil(2 / 1.6) = ceil(1.25) = 2
    assert estimate_tokens("中文") == 2
    # ceil(4 / 1.6) = ceil(2.5) = 3
    assert estimate_tokens("中文测试") == 3


def test_estimate_tokens_mixed_chinese_english():
    # "Hello中文" -> 7 字符 -> ceil(7 / 1.6) = ceil(4.375) = 5
    assert estimate_tokens("Hello中文") == 5
    # "AI 助手" -> 5 字符 -> ceil(5 / 1.6) = ceil(3.125) = 4
    assert estimate_tokens("AI 助手") == 4


def test_chars_for_tokens_floor_and_clamp():
    # 1 token -> 1.6 chars -> floor -> 1
    assert chars_for_tokens(1) == 1
    # 10 tokens -> 16.0 -> 16
    assert chars_for_tokens(10) == 16
    # 3 tokens -> 4.8 -> 4
    assert chars_for_tokens(3) == 4
    # 负数 / 零 clamp 到 0
    assert chars_for_tokens(0) == 0
    assert chars_for_tokens(-5) == 0
    assert chars_for_tokens(-3.7) == 0


def test_chars_for_tokens_inverse_consistency():
    # estimate_tokens("x" * chars_for_tokens(n)) 与 n 偏差 <= 1
    for n in range(1, 500):
        chars = chars_for_tokens(n)
        est = estimate_tokens("x" * chars)
        assert abs(est - n) <= 1, f"n={n} chars={chars} est={est}"


def test_positive_number_fallback_on_zero_and_negative():
    for bad in ("0", "-1", "-100"):
        with patch.dict(os.environ, {"CHAT_TOTAL_TOKEN_BUDGET": bad}, clear=False), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                reloaded = importlib.reload(config)
                # spec-038 P3：默认值由 8000 上调到 20000；非法值仍回退到该默认。
                assert reloaded.CHAT_TOTAL_TOKEN_BUDGET == 20000
                assert any(
                    issubclass(w.category, RuntimeWarning)
                    and "CHAT_TOTAL_TOKEN_BUDGET" in str(w.message)
                    for w in caught
                ), f"expected RuntimeWarning for CHAT_TOTAL_TOKEN_BUDGET={bad}"


def test_compose_defaults_match_status_quo_budgets():
    # 默认装配输出须与显式传入「当前默认数值」(summary=3000/rag=12000/history=6000) 逐字符一致。
    # spec-038 P3：summary 1500→3000、rag 6000→12000；history 仍为 6000。
    q = "当前问题"
    history = [
        SimpleNamespace(role="user", content="用户历史消息内容"),
        SimpleNamespace(role="assistant", content="助手历史消息内容"),
    ]
    memories = []
    project_instructions = "项目指令内容"
    summaries = []
    rag_hits = []

    out_default = compose_chat_prompt(
        q, history, memories, project_instructions, summaries, rag_hits=rag_hits
    )
    out_explicit = compose_chat_prompt(
        q, history, memories, project_instructions, summaries, rag_hits=rag_hits,
        summary_budget_chars=3000, rag_budget_chars=12000, history_budget_chars=6000,
    )
    assert out_default == out_explicit


def test_compose_project_instruction_truncated_to_5000():
    # 第 253 行项目指令须按 CHAT_PROJECT_INSTR_CHARS(5000) 截断。
    long_instr = "指" * 6000
    out = compose_chat_prompt("Q", [], [], long_instr, [])
    header = "项目明确指令（优先级高于长期记忆）：\n"
    parts = out.split("\n\n")
    assert parts[0] == header + "指" * 5000
