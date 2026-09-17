#!/usr/bin/env python3
"""Bounded, repeatable Ollama single-service topology probe for Spec031 Task02.

This is an artifact, not production code.  It uses one existing 9B model, a
fixed JSON request, a bounded number of waves, and no model download or server
configuration change.  The first request of each worker-count block is a
``cold`` sample after ``keep_alive=0``; later waves are warm samples.  A final
``keep_alive=0`` request releases the model before the next block.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


MODEL = "qwen3.5:9b"
PROMPT = 'Return exactly the JSON object {"ok":true} and nothing else.'
REQUEST_TIMEOUT = 60.0
PREDICT_TOKENS = 8


@dataclass
class Sample:
    worker_index: int
    phase: str
    wave_id: int
    ok: bool
    http_status: int | None
    error: str | None
    ttft_ms: float | None
    wall_ms: float
    total_ms: float | None
    load_ms: float | None
    prompt_eval_ms: float | None
    eval_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None


def _request(
    base_url: str, worker_index: int, phase: str, keep_alive: str | int, wave_id: int
) -> Sample:
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": True,
        "think": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": PREDICT_TOKENS},
        "keep_alive": keep_alive,
    }
    started = time.perf_counter()
    ttft_ms: float | None = None
    status: int | None = None
    timings: dict[str, Any] = {}
    error: str | None = None
    try:
        with httpx.stream(
            "POST",
            f"{base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=REQUEST_TIMEOUT,
            trust_env=False,
        ) as response:
            status = response.status_code
            if status >= 400:
                error = response.read().decode("utf-8", errors="replace")[:500]
            else:
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    message = event.get("message") or {}
                    if ttft_ms is None and (message.get("content") or message.get("thinking")):
                        ttft_ms = (time.perf_counter() - started) * 1000.0
                    if event.get("done"):
                        timings = event
    except Exception as exc:  # probe must report failures, never fabricate a result
        error = f"{type(exc).__name__}: {exc}"
    wall_ms = (time.perf_counter() - started) * 1000.0
    # Ollama's native durations are nanoseconds; retain milliseconds in report.
    def ms(name: str) -> float | None:
        value = timings.get(name)
        return float(value) / 1_000_000.0 if isinstance(value, (int, float)) else None

    return Sample(
        worker_index,
        phase,
        wave_id,
        error is None and status is not None and status < 400,
        status,
        error,
        ttft_ms,
        wall_ms,
        ms("total_duration"),
        ms("load_duration"),
        ms("prompt_eval_duration"),
        ms("eval_duration"),
        timings.get("prompt_eval_count"),
        timings.get("eval_count"),
    )


def _wave(
    base_url: str, workers: int, phase: str, keep_alive: str | int, wave_id: int = 0
) -> list[Sample]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_request, base_url, i, phase, keep_alive, wave_id)
            for i in range(workers)
        ]
        return [future.result() for future in futures]


def _ps(base_url: str) -> dict[str, Any]:
    """Read the existing service's resident-model snapshot (never infer memory)."""
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/ps", timeout=REQUEST_TIMEOUT, trust_env=False
        )
        response.raise_for_status()
        models = response.json().get("models") or []
        return {
            "ok": True,
            "models": [
                {"name": item.get("name"), "size_vram": item.get("size_vram") or 0}
                for item in models
            ],
        }
    except Exception as exc:  # memory evidence is explicit when unavailable
        return {"ok": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}


def _summary(samples: list[Sample]) -> dict[str, Any]:
    successful = [item for item in samples if item.ok]

    def median(field: str) -> float | None:
        values = [getattr(item, field) for item in successful if getattr(item, field) is not None]
        return round(statistics.median(values), 3) if values else None

    return {
        "requests": len(samples),
        "successes": len(successful),
        "failures": len(samples) - len(successful),
        "failure_rate": round((len(samples) - len(successful)) / len(samples), 4) if samples else None,
        "median_ttft_ms": median("ttft_ms"),
        "median_wall_ms": median("wall_ms"),
        "median_total_ms": median("total_ms"),
        "median_load_ms": median("load_ms"),
        "median_eval_ms": median("eval_ms"),
        "total_completion_tokens": sum(item.completion_tokens or 0 for item in successful),
        # Aggregate wave throughput uses wall time of the slowest request in
        # each concurrent wave, not the sum of parallel request durations.
        "throughput_completion_tokens_per_s": round(
            sum(item.completion_tokens or 0 for item in successful)
            / (
                sum(
                    max(
                        item.wall_ms
                        for item in successful
                        if item.phase == phase and item.wave_id == wave
                    )
                    for phase, wave in {
                        (item.phase, item.wave_id) for item in successful
                    }
                )
                / 1000.0
            ),
            3,
        )
        if successful
        and sum(
            max(
                item.wall_ms
                for item in successful
                if item.phase == phase and item.wave_id == wave
            )
            for phase, wave in {(item.phase, item.wave_id) for item in successful}
        )
        > 0
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--warm-waves", type=int, default=2)
    parser.add_argument("--workers", default="1,2,3,4")
    args = parser.parse_args()
    workers_list = [int(value) for value in args.workers.split(",")]
    started_at = datetime.now(timezone.utc).isoformat()
    all_blocks: list[dict[str, Any]] = []
    for workers in workers_list:
        # keep_alive=0 makes the first sample a reproducible cold-load boundary.
        cold = _wave(args.base_url, workers, "cold", 0, wave_id=0)
        # Keep the model resident for the warm waves; these exclude the prewarm cost.
        prewarm = _wave(args.base_url, 1, "prewarm", "30s", wave_id=0)
        ps_after_prewarm = _ps(args.base_url)
        warm: list[Sample] = []
        for _ in range(args.warm_waves):
            warm.extend(_wave(args.base_url, workers, "warm", "30s", wave_id=_ + 1))
        ps_after_warm = _ps(args.base_url)
        # Best-effort release; it is not a measured sample.
        _wave(args.base_url, 1, "cleanup", 0, wave_id=0)
        measured = cold + warm
        all_blocks.append(
            {
                "worker_count": workers,
                "cold": _summary(cold),
                "warm": _summary(warm),
                "measured": _summary(measured),
                "prewarm_ok": all(item.ok for item in prewarm),
                "ps_after_prewarm": ps_after_prewarm,
                "ps_after_warm": ps_after_warm,
                "peak_size_vram_bytes": max(
                    [
                        item.get("size_vram") or 0
                        for snapshot in (ps_after_prewarm, ps_after_warm)
                        for item in snapshot.get("models", [])
                    ],
                    default=0,
                ),
                "samples": [asdict(item) for item in measured],
            }
        )
    result = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "model": MODEL,
        "fixed_prompt": PROMPT,
        "think": False,
        "format": "json",
        "num_predict": PREDICT_TOKENS,
        "worker_counts": workers_list,
        "warm_waves": args.warm_waves,
        "blocks": all_blocks,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
