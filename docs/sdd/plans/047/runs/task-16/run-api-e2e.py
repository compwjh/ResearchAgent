#!/usr/bin/env python3
"""spec-047 追加范围三 task-16：最终部署版本的真实 API 端到端成功案例。

对重启后加载「共享批量生成修复」的服务发真实 HTTP 请求，逐字落盘请求 / 响应 /
HTTP 码 / run_id / 最终状态 / 耗时 / 产物路径。mock、内部函数或仅表单调用不替代本脚本。

用法：
    .venv/bin/python docs/sdd/plans/047/runs/task-16/run-api-e2e.py
产物（同目录）：
    evaluation-samples-api-e2e.json  所有 records + summary（逐字响应）
    api-e2e.log                     逐字原始响应 + 请求
    go-no-go-final.json             最终部署版本 100 条 Go/No-Go 硬判据结论
退出码：全部关键断言通过 = 0，否则 = 1。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8000"
MODEL = "qwen3.5:9b"
HARD_LIMIT_SECONDS = 900.0
EXPECTED_METRIC_COUNT = 22

records: list[dict[str, Any]] = []
run_ids: dict[str, str] = {}
go_no_go: dict[str, Any] = {}


def _record(step: str, method: str, path: str, request: Any,
            response: httpx.Response | None, elapsed: float,
            error: str = "") -> dict[str, Any]:
    try:
        payload = response.json() if response is not None else None
    except ValueError:
        payload = None
    entry = {
        "step": step,
        "method": method,
        "path": path,
        "request": request,
        "http_status": response.status_code if response is not None else 0,
        "elapsed_seconds": round(elapsed, 3),
        "response": payload,
        "response_text": response.text if response is not None else error,
    }
    records.append(entry)
    print(f"[{step}] {method} {path} -> HTTP {entry['http_status']} / {elapsed:.3f}s", flush=True)
    return entry


def _call(step: str, method: str, path: str, *, json_body: Any = None,
          params: dict[str, str] | None = None, timeout: float = 960.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                response = client.get(f"{BASE}{path}", params=params)
            else:
                response = client.post(f"{BASE}{path}", json=json_body)
        return _record(step, method, path, json_body if json_body is not None else params,
                       response, time.perf_counter() - started)
    except httpx.HTTPError as exc:
        return _record(step, method, path, json_body if json_body is not None else params,
                       None, time.perf_counter() - started, f"{type(exc).__name__}: {exc}")


def _metric_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    payload = entry.get("response")
    if not isinstance(payload, dict):
        return []
    rows = []
    for metric in payload.get("metrics", []):
        detail = metric.get("detail") or {}
        rows.append({
            "key": metric.get("key"),
            "group": metric.get("group"),
            "status": metric.get("status"),
            "sample_count": metric.get("sample_count"),
            "value": metric.get("value"),
            "reason": detail.get("reason"),
            "judge_sample_count": detail.get("judge_sample_count"),
            "batch_count": detail.get("batch_count"),
            "total_items": detail.get("total_items"),
        })
    return rows


def _judge_go_no_go(entry: dict[str, Any]) -> dict[str, Any]:
    rows = _metric_rows(entry)
    payload = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    violations: list[str] = []
    if entry.get("http_status") != 200:
        violations.append(f"HTTP {entry.get('http_status')} != 200")
    if not payload.get("run_id"):
        violations.append("run_id 为空")
    if len(rows) != EXPECTED_METRIC_COUNT:
        violations.append(f"metrics 只有 {len(rows)} 项，应为 {EXPECTED_METRIC_COUNT}")
    if entry.get("elapsed_seconds", 0) > HARD_LIMIT_SECONDS:
        violations.append(f"总耗时 {entry.get('elapsed_seconds')}s > 900s 硬判据")
    computed = [row for row in rows if row["status"] == "computed"]
    for row in computed:
        if not isinstance(row["sample_count"], int) or row["sample_count"] < 100:
            violations.append(f"computed 维度 {row['key']} sample_count={row['sample_count']} < 100")
        if row["value"] is None:
            violations.append(f"computed 维度 {row['key']} value 为 null")
    if not computed:
        violations.append("没有任何 computed 维度，疑似靠 degraded 收场")
    return {
        "benchmark": "最终部署版本（共享批量生成修复后）真实 100 条 Go/No-Go",
        "hard_limit_seconds": HARD_LIMIT_SECONDS,
        "note": "900s 为硬判据；300s 仅为优化目标线（spec §13.1 P1-1）",
        "request": entry.get("request"),
        "http_status": entry.get("http_status"),
        "run_id": payload.get("run_id"),
        "total_elapsed_seconds": entry.get("elapsed_seconds"),
        "metric_count": len(rows),
        "computed_count": len(computed),
        "non_computed": [row["key"] for row in rows if row["status"] != "computed"],
        "metrics": rows,
        "violations": violations,
        "verdict": "GO" if not violations else "NO_GO",
    }


def main() -> int:
    HERE.mkdir(parents=True, exist_ok=True)
    health = _call("01-health", "GET", "/api/health", timeout=30.0)
    options = _call("02-options", "GET", "/api/evaluation/options", timeout=30.0)
    if health["http_status"] != 200 or options["http_status"] != 200:
        print("BLOCKED: 服务不可用，未继续 E2E", flush=True)
        return 2

    opt = options["response"]
    datasets = {item["id"]: item["item_count"] for item in opt.get("datasets", [])}
    strategies = [item.get("id") for item in opt.get("strategies", []) if item.get("id")]
    strategy_b = "topk-10" if "topk-10" in strategies else (strategies[1] if len(strategies) > 1 else strategies[0])
    print(f"DATASETS={datasets} STRATEGY_B={strategy_b}", flush=True)

    def score(step: str, dataset_id: str, strategy_id: str, max_items: int) -> dict[str, Any]:
        body = {
            "strategy_id": strategy_id,
            "model": MODEL,
            "dataset_id": dataset_id,
            "max_items": max_items,
        }
        return _call(step, "POST", "/api/evaluation/score", json_body=body)

    first = score("03-score-chat-100-baseline", "chat-quality", "baseline", 100)
    go_no_go = _judge_go_no_go(first)
    if first["response"] and first["response"].get("run_id"):
        run_ids["a"] = first["response"]["run_id"]
    print(f"GO_NO_GO={go_no_go['verdict']} computed={go_no_go['computed_count']}/{go_no_go['metric_count']}",
          flush=True)

    intent = score("04-score-intent-100-baseline", "intent-classification", "baseline", 100)
    second = score("05-score-chat-100-second-strategy", "chat-quality", strategy_b, 100)
    if second["response"] and second["response"].get("run_id"):
        run_ids["b"] = second["response"]["run_id"]
    rag = score("06-score-rag-20-baseline", "rag-retrieval", "baseline", 20)
    small = score("07-score-max-items-1", "chat-quality", "baseline", 1)

    if "a" in run_ids and "b" in run_ids:
        _call("08-compare-same-dataset", "GET", "/api/evaluation/compare",
              params={"a": run_ids["a"], "b": run_ids["b"]}, timeout=60.0)
        _call("09-compare-cross-dataset-expect-409", "GET", "/api/evaluation/compare",
              params={"a": run_ids["a"], "b": (intent["response"] or {}).get("run_id", "")},
              timeout=60.0)
    _call("10-runs-list", "GET", "/api/evaluation/runs", timeout=60.0)
    if "a" in run_ids:
        _call("11-run-detail", "GET", f"/api/evaluation/runs/{run_ids['a']}", timeout=60.0)
    _call("12-invalid-option-expect-404", "POST", "/api/evaluation/score",
          json_body={"strategy_id": "not-exist", "model": MODEL,
                     "dataset_id": "chat-quality", "max_items": 1}, timeout=60.0)
    _call("13-invalid-dataset-expect-4xx", "POST", "/api/evaluation/score",
          json_body={"strategy_id": "baseline", "model": MODEL,
                     "dataset_id": "../etc/passwd", "max_items": 1}, timeout=60.0)

    checks = {
        "01_health_200": health["http_status"] == 200,
        "02_options_200": options["http_status"] == 200,
        "02_all_datasets_ge_100": all(isinstance(v, int) and v >= 100 for v in datasets.values()) and len(datasets) == 3,
        "03_chat_100_200": first["http_status"] == 200,
        "03_22_metrics": len(_metric_rows(first)) == 22,
        "03_go_no_go": go_no_go["verdict"] == "GO",
        "04_intent_100_200": intent["http_status"] == 200,
        "04_intent_group_computed": any(
            row["group"] == "intent" and row["status"] == "computed" and row["sample_count"] == 100
            for row in _metric_rows(intent)
        ),
        "05_second_chat_100_200": second["http_status"] == 200,
        "06_rag_20_200": rag["http_status"] == 200,
        "06_rag_group_computed": any(
            row["group"] == "retrieval" and row["status"] == "computed"
            for row in _metric_rows(rag)
        ),
        "07_max_items_1_200": small["http_status"] == 200,
        "08_compare_200": next((r["http_status"] == 200 for r in records if r["step"] == "08-compare-same-dataset"), False),
        "09_cross_dataset_409": next((r["http_status"] == 409 for r in records if r["step"] == "09-compare-cross-dataset-expect-409"), False),
        "10_runs_200": next((r["http_status"] == 200 for r in records if r["step"] == "10-runs-list"), False),
        "11_run_detail_200": next((r["http_status"] == 200 for r in records if r["step"] == "11-run-detail"), False),
        "12_invalid_option_404": next((r["http_status"] == 404 for r in records if r["step"] == "12-invalid-option-expect-404"), False),
        "13_invalid_dataset_4xx": next((400 <= r["http_status"] < 500 for r in records if r["step"] == "13-invalid-dataset-expect-4xx"), False),
    }
    summary = {
        "base_url": BASE,
        "model": MODEL,
        "datasets": datasets,
        "strategy_b": strategy_b,
        "run_ids": run_ids,
        "record_count": len(records),
        "checks": checks,
        "passed": sum(1 for value in checks.values() if value),
        "total_checks": len(checks),
        "failed_checks": [key for key, value in checks.items() if not value],
        "go_no_go": go_no_go["verdict"],
        "conclusion": "PASS" if all(checks.values()) else "FAIL",
    }
    out = HERE / "evaluation-samples-api-e2e.json"
    out.write_text(json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    (HERE / "go-no-go-final.json").write_text(
        json.dumps(go_no_go, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_lines = ["=== RAW RESPONSES (verbatim) ==="]
    for entry in records:
        log_lines.append(f"\n--- {entry['step']} {entry['method']} {entry['path']} ---")
        log_lines.append("REQUEST: " + json.dumps(entry["request"], ensure_ascii=False))
        log_lines.append(f"HTTP {entry['http_status']} / {entry['elapsed_seconds']}s")
        log_lines.append(entry["response_text"])
    log_lines.append("\n=== SUMMARY ===\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    (HERE / "api-e2e.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("SUMMARY=" + json.dumps(summary, ensure_ascii=False), flush=True)
    print(f"WROTE {out}", flush=True)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
