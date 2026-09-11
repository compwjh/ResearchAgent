"""spec-023 Task02 探测脚本 A — 原生 function calling 可行性。

用法（仓库根目录）：
    .venv/bin/python docs/sdd/plans/023/task-02-toolcall-feasibility/probe_toolcall.py

要点：
- httpx 必须 trust_env=False（macOS 系统代理会劫持到 192.168.31.180 的内网请求）。
- thinking 模型（qwen3.8:27b-mlx 的 capabilities 含 thinking）必须显式 think=False，否则 content 为空。
- 只读探测，不写 backend/** 业务代码。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://192.168.31.180:11434"
MODEL = "qwen3.8:27b-mlx"
CHAT_URL = f"{BASE_URL}/api/chat"

OUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUT_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 复用 .agents/skills/usenix-paper-catalog-search 的真实领域语义构造工具
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_paper_catalog",
            "description": "检索 USENIX Security 论文目录元数据（只返回元数据，不下载 PDF）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "研究方向或关键词"},
                    "year": {"type": "integer", "description": "会议年份，例如 2024"},
                    "page_size": {"type": "integer", "description": "每页条数，固定 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_and_import_paper",
            "description": "对已选定论文执行 PDF 安全验证、下载与个人知识库导入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_id": {"type": "string"},
                    "catalog_paper_id": {"type": "string"},
                },
                "required": ["search_id", "catalog_paper_id"],
            },
        },
    },
]

CASES = [
    {
        "id": "A1-bare-tools",
        "note": "无 system prompt，仅 tools，think=False",
        "messages": [{"role": "user", "content": "帮我找 2024 年 USENIX Security 关于 fuzzing 的论文。"}],
        "think": False,
    },
    {
        "id": "A2-system-tools",
        "note": "带 system prompt 说明 Skill 边界，tools，think=False",
        "system": (
            "你是 ResearchAgent。可用 Skill：usenix-paper-catalog-search（目录检索）、"
            "usenix-accepted-papers（下载导入）。需要时调用工具，不要臆造。"
        ),
        "messages": [{"role": "user", "content": "帮我找 2024 年 USENIX Security 关于 fuzzing 的论文。"}],
        "think": False,
    },
    {
        "id": "A3-tools-think-true",
        "note": "对照组：think=True（验证是否返回空/超时），tools 存在",
        "messages": [{"role": "user", "content": "帮我找 2024 年 USENIX Security 关于 fuzzing 的论文。"}],
        "think": True,
    },
    {
        "id": "A4-no-tool-needed",
        "note": "不需要工具的普通提问，确认不会乱调工具",
        "messages": [{"role": "user", "content": "你好，你能做什么？"}],
        "think": False,
    },
    {
        "id": "A5-explicit-skill-name",
        "note": "显式点名 Skill，是否映射到对应工具",
        "messages": [
            {"role": "user", "content": "使用 usenix-paper-catalog-search 技能，检索 2023 年 USENIX Security 的隐私相关论文。"}
        ],
        "think": False,
    },
    {
        "id": "A6-download-intent",
        "note": "下载意图应映射 download_and_import_paper",
        "messages": [
            {
                "role": "user",
                "content": "用 usenix-accepted-papers 技能，把搜索任务 search-abc 里的论文 catalog_paper_id=42 下载并导入知识库。",
            }
        ],
        "think": False,
    },
]


def call(payload: dict, timeout: float = 300.0) -> dict:
    """直连 /api/chat（非流式），返回带耗时与原始文本的结果。"""
    started = time.perf_counter()
    with httpx.Client(trust_env=False, timeout=timeout) as client:
        resp = client.post(CHAT_URL, json=payload)
    elapsed = time.perf_counter() - started
    out: dict = {"http_status": resp.status_code, "elapsed_s": round(elapsed, 2)}
    if resp.status_code != 200:
        out["body_text"] = resp.text[:2000]
        return out
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - 探测脚本，需记录原始失败形态
        out["json_error"] = f"{type(exc).__name__}: {exc}"
        out["body_text"] = resp.text[:2000]
        return out
    msg = (data or {}).get("message") or {}
    out["raw"] = data
    out["content"] = msg.get("content", "")
    out["thinking"] = msg.get("thinking", "")
    out["tool_calls"] = msg.get("tool_calls") or []
    out["done_reason"] = data.get("done_reason")
    out["eval_count"] = data.get("eval_count")
    out["prompt_eval_count"] = data.get("prompt_eval_count")
    return out


def classify(res: dict) -> str:
    if res.get("http_status") != 200:
        return "HTTP_ERROR"
    if res.get("json_error"):
        return "JSON_ERROR"
    if res.get("tool_calls"):
        return "TOOL_CALL_OK"
    content = (res.get("content") or "").strip()
    if not content:
        return "EMPTY_OUTPUT"
    return "TEXT_ONLY"


def main() -> int:
    summary = {
        "base_url": BASE_URL,
        "model": MODEL,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cases": [],
    }
    for case in CASES:
        payload = {
            "model": MODEL,
            "messages": (
                ([{"role": "system", "content": case["system"]}] if case.get("system") else [])
                + case["messages"]
            ),
            "stream": False,
            "think": case["think"],
        }
        if case["id"] not in {"A4-no-tool-needed"}:
            payload["tools"] = TOOLS
        print(f"[case] {case['id']} - {case['note']}", flush=True)
        try:
            res = call(payload)
        except Exception as exc:  # noqa: BLE001
            res = {"http_status": None, "error": f"{type(exc).__name__}: {exc}", "elapsed_s": None}
        verdict = classify(res)
        raw_path = RAW_DIR / f"{case['id']}.json"
        raw_path.write_text(
            json.dumps({"request": payload, "response": res}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        entry = {
            "id": case["id"],
            "note": case["note"],
            "think": case["think"],
            "has_tools": "tools" in payload,
            "verdict": verdict,
            "http_status": res.get("http_status"),
            "elapsed_s": res.get("elapsed_s"),
            "content_preview": (res.get("content") or "")[:300],
            "tool_calls": res.get("tool_calls"),
            "thinking_preview": (res.get("thinking") or "")[:200],
            "error": res.get("error"),
            "done_reason": res.get("done_reason"),
            "eval_count": res.get("eval_count"),
            "raw_file": str(raw_path.relative_to(OUT_DIR)),
        }
        summary["cases"].append(entry)
        print(f"  -> {verdict} ({entry['elapsed_s']}s)", flush=True)

    (OUT_DIR / "result_toolcall.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for c in summary["cases"] if c["verdict"] == "TOOL_CALL_OK")
    print(f"\nTOOL_CALL_OK {ok}/{len(summary['cases'])}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
