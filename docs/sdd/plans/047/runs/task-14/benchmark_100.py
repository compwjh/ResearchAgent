#!/usr/bin/env python3
"""spec-047 追加范围三 Go/No-Go 真实基准（不 mock、不降采样、不靠 degraded 收场）。

对**重启后加载新代码**的服务发真实 HTTP ``POST /api/evaluation/score``：
    {"strategy_id": "baseline", "model": <本地可用模型>,
     "dataset_id": "chat-quality", "max_items": 100}

硬判据（spec §13.1 P1-1，唯一口径）：
  - 真实 100 条打分总耗时 <= 900s（300s 只是优化目标线，不是失败线）；
  - 22 项里所有 status=computed 的维度 sample_count >= 100 且 value 非 null；
  - HTTP 200、22 个 key 齐全、run_id 非空。
memory_correctness 按 P1-4 保持 needs_ground_truth（非 computed，不在判据内），
但脚本会如实列出所有非 computed 维度的 reason，绝不隐藏、不把 null 当 0。

用法（仓库根目录、已激活 .venv、服务已用 deploy/start.sh -d 重启）：
    .venv/bin/python docs/sdd/plans/047/runs/task-14/benchmark_100.py \
        --max-items 100 --output docs/sdd/plans/047/runs/task-14/go-no-go.json \
        --log docs/sdd/plans/047/runs/task-14/go-no-go.log
退出码：GO=0 / NO_GO=1 / 阻塞(服务不可用)=2。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
HARD_LIMIT_SECONDS = 900.0
OPTIMIZATION_TARGET_SECONDS = 300.0
EXPECTED_METRIC_COUNT = 22


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=None, help="默认从 /api/evaluation/options 取第一个本地模型")
    parser.add_argument("--dataset-id", default="chat-quality")
    parser.add_argument("--strategy-id", default="baseline")
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=960.0, help="客户端超时，须大于 900s 硬判据")
    parser.add_argument("--output", default=str(HERE / "go-no-go.json"))
    parser.add_argument("--log", default=str(HERE / "go-no-go.log"))
    return parser.parse_args()


def _metric_rows(payload: dict) -> list[dict[str, Any]]:
    rows = []
    for metric in payload.get("metrics", []):
        detail = metric.get("detail") or {}
        rows.append({
            "key": metric.get("key"),
            "status": metric.get("status"),
            "sample_count": metric.get("sample_count"),
            "value": metric.get("value"),
            "value_is_null": metric.get("value") is None,
            "reason": detail.get("reason"),
            "judge_sample_count": detail.get("judge_sample_count"),
            "batch_count": detail.get("batch_count"),
            "total_items": detail.get("total_items"),
            "judge_mode": detail.get("judge_mode"),
        })
    return rows


def _judge(rows: list[dict], http_status: int, elapsed: float, run_id: str | None,
           payload: dict) -> tuple[str, list[str]]:
    violations: list[str] = []
    if http_status != 200:
        violations.append(f"HTTP status {http_status} != 200")
    if not run_id:
        violations.append("run_id 为空")
    if len(rows) != EXPECTED_METRIC_COUNT:
        violations.append(f"metrics 只有 {len(rows)} 项，应为 {EXPECTED_METRIC_COUNT}")
    if elapsed > HARD_LIMIT_SECONDS:
        violations.append(f"总耗时 {elapsed:.3f}s > 硬判据 {HARD_LIMIT_SECONDS:.0f}s")
    computed = [row for row in rows if row["status"] == "computed"]
    for row in computed:
        if not isinstance(row["sample_count"], int) or row["sample_count"] < 100:
            violations.append(f"computed 维度 {row['key']} sample_count={row['sample_count']} < 100")
        if row["value_is_null"]:
            violations.append(f"computed 维度 {row['key']} value 为 null")
    if not computed:
        violations.append("没有任何 computed 维度，疑似靠 degraded 收场")
    degraded = [row["key"] for row in rows if row["status"] != "computed"]
    if degraded:
        # 非 computed 不自动判失败（memory_correctness 按 P1-4 允许），但必须留痕。
        print(f"INFO 非 computed 维度（如实标注，未隐藏）: {degraded}")
    return ("GO" if not violations else "NO_GO"), violations


def main() -> int:
    args = _parse_args()
    output = Path(args.output)
    log = Path(args.log)
    output.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30.0) as probe:
        try:
            health = probe.get(f"{args.base_url}/api/health")
            if health.status_code != 200:
                raise RuntimeError(f"/api/health={health.status_code}")
            model = args.model
            if not model:
                options = probe.get(f"{args.base_url}/api/evaluation/options").json()
                models = options.get("models") or []
                if not models:
                    raise RuntimeError("options.models 为空")
                model = str(models[0])
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            print(f"BLOCKED: 服务不可用或未重启加载新代码: {exc}")
            return 2

    body = {
        "strategy_id": args.strategy_id,
        "model": model,
        "dataset_id": args.dataset_id,
        "max_items": args.max_items,
    }
    print(f"POST /api/evaluation/score body={json.dumps(body, ensure_ascii=False)}")
    started = time.perf_counter()
    http_status = 0
    payload: dict = {}
    error_text = ""
    try:
        with httpx.Client(timeout=args.timeout) as client:
            response = client.post(f"{args.base_url}/api/evaluation/score", json=body)
            http_status = response.status_code
            raw_text = response.text
            try:
                payload = response.json()
            except ValueError:
                error_text = raw_text
    except httpx.HTTPError as exc:
        error_text = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    rows = _metric_rows(payload) if isinstance(payload, dict) else []
    run_id = payload.get("run_id") if isinstance(payload, dict) else None
    verdict, violations = _judge(rows, http_status, elapsed, run_id, payload)

    record = {
        "benchmark": "spec-047 追加范围三 Go/No-Go 真实 100 条基准",
        "hard_limit_seconds": HARD_LIMIT_SECONDS,
        "optimization_target_seconds": OPTIMIZATION_TARGET_SECONDS,
        "note": "900s 是硬判据；300s 仅为优化目标线，不是失败线（spec §13.1 P1-1）",
        "request": body,
        "http_status": http_status,
        "run_id": run_id,
        "total_elapsed_seconds": round(elapsed, 3),
        "metric_count": len(rows),
        "computed_count": sum(1 for row in rows if row["status"] == "computed"),
        "metrics": rows,
        "violations": violations,
        "verdict": verdict,
    }
    if error_text:
        record["transport_error"] = error_text
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.write_text(
        "=== RAW RESPONSE (verbatim) ===\n" + (
            json.dumps(payload, ensure_ascii=False, indent=2) if payload else error_text
        ) + "\n=== REQUEST ===\n" + json.dumps(body, ensure_ascii=False) + "\n"
        + f"=== HTTP {http_status} / elapsed {elapsed:.3f}s / verdict {verdict} ===\n",
        encoding="utf-8",
    )
    print(f"HTTP {http_status} run_id={run_id} elapsed={elapsed:.3f}s computed={record['computed_count']}/{len(rows)}")
    print(f"VERDICT: {verdict}")
    for violation in violations:
        print(f"  - {violation}")
    print(f"WROTE {output}")
    print(f"WROTE {log}")
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
