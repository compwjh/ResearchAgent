"""批量生成 / 批量判官协议的离线替身，供既有契约测试复用（spec-047 追加范围三）。

产品代码不 mock 分数：替身只返回「枚举标签 / 实时生成文本」，分数仍由
ENUM_MAPS / RUBRIC_ENUM_MAPS 与真实聚合逻辑计算，调用链仍是唯一传输层 call_ollama。
文件名按能力命名，不含任何 spec / task 编号。
"""
from __future__ import annotations

import json
from typing import Any


def batch_transport(model, messages, timeout=None, num_predict=None, *, calls: list | None = None):
    """识别四类批量 system 提示，返回符合批量 JSON 协议的响应。"""
    system = str(messages[0]["content"])
    try:
        payload = json.loads(messages[-1]["content"])
    except (ValueError, TypeError):
        payload = {}
    if calls is not None:
        calls.append({
            "model": model, "system": system, "size": len(payload),
            "timeout": timeout, "num_predict": num_predict,
        })
    if "BATCH GENERATION" in system:
        return json.dumps({key: "LIVE::" + str(value) for key, value in payload.items()})
    if "BATCH RUBRIC" in system:
        from backend.app.evaluation.rubrics import RUBRIC_KEYS

        return json.dumps({key: dict.fromkeys(RUBRIC_KEYS, "good") for key in payload})
    if "BATCH ANSWER QUALITY" in system:
        return json.dumps(dict.fromkeys(payload, "good"))
    if "retrieval-relevance" in system:
        return json.dumps(dict.fromkeys(payload, "good"))
    return "LIVE::" + str(messages[-1]["content"])


def chat_items(count: int = 2) -> list[dict[str, Any]]:
    """P1-4 之后的 chat 集条目：status=scored + 非空 input/output + 两层来源标记。"""
    return [
        {
            "id": f"c{i}", "status": "scored", "input": f"q{i}", "output": f"a{i}",
            "synthetic": i % 2 == 0,
            "reference_source": "kb-chunk" if i % 2 == 0 else "frozen-042-trace",
            "prior_context": None,
        }
        for i in range(1, count + 1)
    ]
