"""Spec047 追加范围二：当前部署版本真实 API E2E（非 mock，直接打活服务）。

产物：docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).with_name("evaluation-metrics-api-e2e.json")
MODEL = "qwen3.5:9b"


def call(method: str, path: str, body: dict | None = None, timeout: int = 320) -> dict:
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read().decode("utf-8")
    elapsed = round(time.monotonic() - started, 3)
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = {"raw": raw}
    return {
        "request": {"method": method, "url": url, "body": body},
        "response": {"http_status": status, "elapsed_seconds": elapsed, "body": parsed},
    }


def score(strategy: str, dataset: str, max_items: int = 2) -> dict:
    return call(
        "POST",
        "/api/evaluation/score",
        {"strategy_id": strategy, "model": MODEL, "dataset_id": dataset, "max_items": max_items},
    )


def main() -> None:
    records: list[dict] = []
    run_ids: dict[str, str] = {}

    def add(label: str, record: dict) -> None:
        records.append({"label": label, **record})
        print(f"[{label}] HTTP={record['response']['http_status']} time={record['response']['elapsed_seconds']}s", flush=True)
        body = record["response"]["body"]
        if isinstance(body, dict) and body.get("run_id"):
            run_ids[label] = body["run_id"]
            print(f"[{label}] run_id={body['run_id']} metrics={len(body.get('metrics', []))}", flush=True)

    add("health", call("GET", "/api/health", timeout=20))
    add("options", call("GET", "/api/evaluation/options", timeout=30))
    add("score-rag-baseline", score("baseline", "rag-retrieval"))
    add("score-rag-topk10", score("topk-10", "rag-retrieval"))
    add("score-intent-baseline", score("baseline", "intent-classification"))
    add("score-chat-quality", score("baseline", "chat-quality"))
    add("runs-list", call("GET", "/api/evaluation/runs", timeout=30))

    rag_a = run_ids.get("score-rag-baseline")
    rag_b = run_ids.get("score-rag-topk10")
    if rag_a:
        add("run-detail", call("GET", f"/api/evaluation/runs/{rag_a}", timeout=30))
    if rag_a and rag_b:
        add("compare-same-dataset", call("GET", f"/api/evaluation/compare?a={rag_a}&b={rag_b}", timeout=30))
    chat = run_ids.get("score-chat-quality")
    if rag_a and chat:
        add("compare-cross-dataset", call("GET", f"/api/evaluation/compare?a={rag_a}&b={chat}", timeout=30))
    add("invalid-option", call("POST", "/api/evaluation/score", {"strategy_id": "nope", "model": MODEL, "dataset_id": "rag-retrieval"}, timeout=30))

    summary = {
        "spec": "047",
        "scope": "追加范围二：评测指标体系细化（22 指标 / 5 分组）",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "service": BASE,
        "service_start_command": "RERANKER_ENABLED=false ./deploy/start.sh -d",
        "model_under_test": MODEL,
        "judge_model": "qwen3.5:9b (backend/eval_042/config.py::PRIMARY_JUDGE)",
        "run_ids": run_ids,
        "records": records,
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}", flush=True)


if __name__ == "__main__":
    main()
