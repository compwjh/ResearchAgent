"""本地 Ollama 判官客户端（直连，离线）。

- 强制 think:false + temperature 0（确定性），num_predict 限制长度以提速；
- R4 范式解析：抽取 Explanation / Answer 枚举标签；
- 判官只输出枚举，分数由 ENUM_MAPS 映射，避免弱模型打数值分；
- 任何调用异常/解析失败 -> status=unavailable（绝不安静记 0 分）。
"""
from __future__ import annotations

import re
import string
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from .config import ENUM_MAPS, JUDGE_SEED, OLLAMA_BASE, PROMPTS
from .offline_guard import http_post_json

_ANSWER_RE = re.compile(r"answer\s*:\s*([a-z_]+)", re.IGNORECASE)


# 平票裁决规则（与 dict 插入顺序无关、确定性）。记录在报告 metadata 的
# ``tie_break_rule`` 中，便于跨运行复现与历史结果对照。
TIE_BREAK_RULE = (
    "majority_label: among labels tied at the top count, prefer the label with "
    "the highest mapped score (per task ENUM_MAPS); ties broken alphabetically"
)


@dataclass
class JudgeResult:
    """Shared result of judging one item with one model (repeats calls)."""

    model: str
    task: str
    labels: list[str]
    scored_calls: list[dict]
    all_calls: list[dict]
    unavailable_count: int
    all_unavailable: bool
    majority: str | None


def _majority_label(labels: list[str], task: str | None = None) -> str | None:
    """多数投票标签，平票时与标签插入顺序无关（确定性）。

    规则：取计数最高的标签集合；若唯一直接返回；若平票则在候选中按
    (映射分数降序, 标签字母序) 排序取首个。
    """
    if not labels:
        return None
    counts = Counter(labels)
    top = max(counts.values())
    candidates = [label for label, count in counts.items() if count == top]
    if len(candidates) == 1:
        return candidates[0]
    enums = ENUM_MAPS.get(task, {})

    def sort_key(label: str) -> tuple[float, str]:
        score = enums.get(label)
        score_key = float(score) if isinstance(score, (int, float)) else float("-inf")
        return (-score_key, label)

    return sorted(candidates, key=sort_key)[0]


def judge_majority(
    model: str,
    task: str,
    question: str,
    answer: str,
    repeats: int = 3,
    ctx: str | None = None,
) -> JudgeResult:
    """共用 judge 编排入口：对单条用单模型重复评分，返回标签与多数票。

    runner / consistency / memory_probe 三处此前各写一份近似逻辑，现统一收敛
    到此处，保证平票裁决与不可用判定一致。``all_unavailable`` 仅在所有 repeats
    都不可用时为 True；否则 ``labels`` 为已成功评分的标签列表。
    """
    calls = judge_repeats(model, task, question, answer, repeats, ctx=ctx)
    labels: list[str] = []
    scored_calls: list[dict] = []
    unavailable_count = 0
    if isinstance(calls, list):
        for call in calls:
            if not isinstance(call, Mapping):
                unavailable_count += 1
                continue
            if call.get("status") == "scored":
                label = call.get("label")
                if isinstance(label, str):
                    labels.append(label)
                    scored_calls.append(call)
                else:
                    unavailable_count += 1
            else:
                unavailable_count += 1
    all_unavailable = isinstance(calls, list) and bool(calls) and unavailable_count == len(calls)
    majority = _majority_label(labels, task) if labels else None
    return JudgeResult(
        model=model,
        task=task,
        labels=labels,
        scored_calls=scored_calls,
        all_calls=calls if isinstance(calls, list) else [],
        unavailable_count=unavailable_count,
        all_unavailable=all_unavailable,
        majority=majority,
    )


def _render(tmpl: str, q: str, a: str, ctx: str | None = None) -> str:
    """安全渲染用户模板：仅填充模板中实际存在的占位符。

    - 对没有 {ctx} 占位符的模板（如 chat_quality），即使传入 ctx 也不注入，
      行为与改动前完全一致（向后兼容）；
    - 对 {ctx} 占位符，仅当 ctx 非 None 时填充，避免 KeyError。
    """
    fields = {name for _, name, _, _ in string.Formatter().parse(tmpl) if name}
    kwargs: dict = {}
    if "q" in fields:
        kwargs["q"] = q
    if "a" in fields:
        kwargs["a"] = a
    if "ctx" in fields:
        kwargs["ctx"] = ctx if ctx is not None else ""
    return tmpl.format(**kwargs)


def parse_r4(text: str, allowed_labels: set[str]) -> tuple[str | None, str]:
    """抽取 (label, explanation)。label 不在 allowed_labels 时返回 (None, explanation)。"""
    if not text:
        return None, ""
    explanation = ""
    m_exp = re.search(r"explanation\s*:\s*(.+)", text, re.IGNORECASE)
    if m_exp:
        explanation = m_exp.group(1).strip()
    m = _ANSWER_RE.search(text)
    if not m:
        return None, explanation
    label = m.group(1).lower()
    if label not in allowed_labels:
        return None, explanation
    return label, explanation


def enum_to_score(task: str, label: str | None) -> float | None:
    if label is None:
        return None
    return ENUM_MAPS.get(task, {}).get(label)


def call_ollama(model: str, messages: list[dict], timeout: int = 180,
                num_predict: int | None = None) -> str:
    """唯一传输层。``num_predict`` 是 spec-047 §13.1 P1-3 允许的唯一例外：

    不传时 body 的 ``options.num_predict`` **仍为 160**（默认行为逐字不变），
    只有批量生成 / 批量判官调用才显式传入更大的输出上限，避免 B=20 的 JSON 被截断。
    ``ENUM_MAPS`` / ``PROMPTS`` / ``judge_one`` / ``judge_majority`` 行为不变。
    """
    body = {
        "model": model,
        "think": False,
        "seed": JUDGE_SEED,
        "messages": messages,
        "options": {"temperature": 0, "num_predict": 160 if num_predict is None else num_predict},
        "stream": False,
    }
    data = http_post_json(
        f"{OLLAMA_BASE}/api/chat",
        body,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    if not isinstance(data, dict):
        raise ValueError(f"Ollama response must be a JSON object, got {type(data).__name__}")
    return (data.get("message", {}) or {}).get("content", "") or ""


def judge_one(model: str, task: str, question: str, answer: str,
              ctx: str | None = None) -> dict:
    """对单条单次评分。返回结构化结果，含 status=scored|unavailable。

    ctx：可选，先前陈述上下文（memory_correctness 用）；不传时行为与改动前一致。
    """
    allowed = set(ENUM_MAPS.get(task, {}).keys())
    prompt = PROMPTS[task]
    messages = [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": _render(prompt["user_tmpl"], question, answer, ctx)},
    ]
    try:
        raw = call_ollama(model, messages)
        label, explanation = parse_r4(raw, allowed)
        if label is None:
            return {
                "status": "unavailable", "label": None, "score": None,
                "explanation": explanation, "raw": raw, "model": model, "task": task,
                "error": "parse_failed_no_valid_label",
            }
        return {
            "status": "scored", "label": label, "score": enum_to_score(task, label),
            "explanation": explanation, "raw": raw, "model": model, "task": task,
            "error": None,
        }
    except Exception as exc:  # 网络/超时/任何异常 -> unavailable，不记 0
        return {
            "status": "unavailable", "label": None, "score": None,
            "explanation": "", "raw": "", "model": model, "task": task,
            "error": f"{type(exc).__name__}: {exc}",
        }


def judge_repeats(model: str, task: str, question: str, answer: str,
                  repeats: int = 3, ctx: str | None = None) -> list[dict]:
    return [judge_one(model, task, question, answer, ctx=ctx) for _ in range(repeats)]
