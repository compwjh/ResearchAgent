"""spec-042 Task 02 评测配置（本地离线，仅指向本机服务，不触外网）。

注意：pk/sk 为 spec-042 文档明文给出的本地 dev 占位凭据（pk-lf-local-dev-0001 /
sk-lf-local-dev-0001），非真实密钥；仅用于本机 Langfuse 只读导出与回写。
"""
from __future__ import annotations

import os

# ---------- 本机服务端点（全部 loopback，离线前提） ----------
LANGFUSE_BASE = os.getenv("LANGFUSE_BASE", "http://127.0.0.1:3000")
LANGFUSE_PK = os.getenv("LANGFUSE_PK", "pk-lf-local-dev-0001")
LANGFUSE_SK = os.getenv("LANGFUSE_SK", "sk-lf-local-dev-0001")
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")

# 离线出口白名单：本评测只允许访问这两个 loopback 主机，任何其它主机一律拒绝。
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}

# ---------- 判官模型（Q3=B 主用 9b，Q8=A 回退 27b） ----------
PRIMARY_JUDGE = os.getenv("PRIMARY_JUDGE", "qwen3.5:9b")
FALLBACK_JUDGE = os.getenv("FALLBACK_JUDGE", "qwen3.8:27b")
REPEATS = 3  # 同一条温度 0 重复评分次数（判官自一致门禁）

# 判官自一致门禁：3 次标签完全一致的项占比 >= 此值才算「稳定」
SELF_CONSISTENCY_THRESHOLD = 0.90

# ---------- 枚举标签 -> 0..1 分数映射（判官只输出枚举，分数由本脚本映射，避免弱模型打数值分） ----------
QUALITY_ENUMS = {"good": 1.0, "partial": 0.5, "poor": 0.0}
MEMORY_ENUMS = {
    "remembered": 1.0,
    "partially_remembered": 0.6,
    "forgotten": 0.2,
    "fabricated": 0.0,
}
ENUM_MAPS = {"chat_quality": QUALITY_ENUMS, "memory_correctness": MEMORY_ENUMS}

# ---------- R4 判官 prompt 范式：强制 Explanation / Answer 两行，Answer 限枚举 ----------
PROMPTS = {
    "chat_quality": {
        "system": (
            "You are a strict LLM-as-judge for ANSWER QUALITY. "
            "Output EXACTLY two lines, no more:\n"
            "Explanation: <one short sentence>\n"
            "Answer: <one of: good|partial|poor>"
        ),
        "user_tmpl": (
            "Question:\n{q}\n\nAnswer:\n{a}\n\n"
            "Judge the answer's relevance and completeness. "
            "good=fully relevant & complete; partial=relevant but incomplete/wrong detail; "
            "poor=irrelevant, refuses, or nonsensical."
        ),
    },
    "memory_correctness": {
        "system": (
            "You are a strict LLM-as-judge for MEMORY CORRECTNESS. "
            "Output EXACTLY two lines, no more:\n"
            "Explanation: <one short sentence>\n"
            "Answer: <one of: remembered|partially_remembered|forgotten|fabricated>"
        ),
        "user_tmpl": (
            "User instruction / prior context:\n{q}\n\nAgent answer:\n{a}\n\n"
            "Judge whether the agent correctly recalled a user-stated preference or fact: "
            "remembered=correctly recalled; partially_remembered=recalled with gaps; "
            "forgotten=failed to recall a stated preference/fact; "
            "fabricated=invented a preference/fact not stated. "
            "If no memory signal is present, output forgotten."
        ),
    },
}

# Intke 文案（技能路由劫持）标记：命中即 SKIPPED，不评分
INTAKE_MARKERS = ("研究 Intake", "Intake 已保存", "研究 intake", "intake 已保存")
MIN_ANSWER_CHARS = 1  # 仅空/空白或 Intake 文案才 SKIP；真实短回答（如 Hi there）仍评分
