"""本地 Ollama 判官客户端（直连，离线）。

- 强制 think:false + temperature 0（确定性），num_predict 限制长度以提速；
- R4 范式解析：抽取 Explanation / Answer 枚举标签；
- 判官只输出枚举，分数由 ENUM_MAPS 映射，避免弱模型打数值分；
- 任何调用异常/解析失败 -> status=unavailable（绝不安静记 0 分）。
"""
from __future__ import annotations

import json
import re
import string
import urllib.request

from .config import ENUM_MAPS, OLLAMA_BASE, PROMPTS
from .offline_guard import assert_loopback

_ANSWER_RE = re.compile(r"answer\s*:\s*([a-z_]+)", re.IGNORECASE)


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


def call_ollama(model: str, messages: list[dict], timeout: int = 180) -> str:
    assert_loopback(OLLAMA_BASE)
    body = {
        "model": model,
        "think": False,
        "messages": messages,
        "options": {"temperature": 0, "num_predict": 160},
        "stream": False,
    }
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
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
