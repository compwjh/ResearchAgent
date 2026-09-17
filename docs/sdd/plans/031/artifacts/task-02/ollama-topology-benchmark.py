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
import hashlib
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


MODEL = "qwen3.5:9b"
PROMPT = 'Return exactly the JSON object {"ok":true} and nothing else.'
REQUEST_TIMEOUT = 60.0
PREDICT_TOKENS = 8
ARTIFACT_SCHEMA_VERSION = "spec031-task02-benchmark-v2"
RESOURCE_MARGIN_FRACTION = 0.20


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
    response_json_valid: bool
    response_text: str
    quality_error: str | None


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
    response_parts: list[str] = []
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
                    content = message.get("content")
                    if isinstance(content, str):
                        response_parts.append(content)
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

    response_text = "".join(response_parts)
    response_json_valid = False
    quality_error: str | None = None
    if error is None and status is not None and status < 400:
        try:
            response_json_valid = json.loads(response_text) == {"ok": True}
        except (TypeError, ValueError, json.JSONDecodeError):
            response_json_valid = False
        if not response_json_valid:
            quality_error = "QUALITY_ASSERTION_FAILED"
            error = quality_error

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
        response_json_valid,
        response_text,
        quality_error,
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


def _available_memory_bytes() -> int | None:
    """Read the same class of OS-level available-memory signal as ResourceProbe.

    This artifact deliberately keeps the probe read-only and dependency-free.  It
    records the raw input and an explicit failure instead of inventing a value.
    """
    if sys.platform == "linux":
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    if sys.platform == "darwin":
        try:
            completed = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=5, check=False
            )
            if completed.returncode != 0:
                return None
            page_size_match = re.search(r"page size of\s+(\d+)\s+bytes", completed.stdout)
            if not page_size_match:
                return None
            page_size = int(page_size_match.group(1))
            pages = 0
            for name in ("Pages free", "Pages speculative", "Pages inactive"):
                match = re.search(rf"^{re.escape(name)}:\s+(\d+)", completed.stdout, re.MULTILINE)
                if not match:
                    return None
                pages += int(match.group(1))
            return pages * page_size
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
    return None


def _resource_probe(base_url: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a replayable ResourceProbe evidence record from read-only inputs."""
    captured_at = datetime.now(timezone.utc).isoformat()
    available = _available_memory_bytes()
    models = snapshot.get("models") if snapshot.get("ok") else []
    models = models if isinstance(models, list) else []
    footprint = max((int(item.get("size_vram") or 0) for item in models), default=0)
    loaded_count = len(models)
    if available is None or available <= 0 or footprint <= 0:
        return {
            "status": "RESOURCE_PROBE_FAILED",
            "captured_at": captured_at,
            "available_memory_bytes": available,
            "model_footprint_bytes": footprint,
            "loaded_model_count": loaded_count,
            "max_safe_workers": 1,
            "error": "available memory or loaded model footprint unavailable",
        }
    usable = int(available * (1 - RESOURCE_MARGIN_FRACTION))
    return {
        "status": "ok",
        "captured_at": captured_at,
        "available_memory_bytes": available,
        "model_footprint_bytes": footprint,
        "loaded_model_count": loaded_count,
        "margin_fraction": RESOURCE_MARGIN_FRACTION,
        "usable_memory_bytes": usable,
        "max_safe_workers": max(1, usable // footprint),
        "error": None,
    }


def _tags_probe(url: str) -> dict[str, Any]:
    try:
        response = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=5, trust_env=False)
        payload = response.json() if response.content else {}
        return {
            "url": url,
            "http_status": response.status_code,
            "reachable": response.status_code < 400,
            "model_count": len(payload.get("models") or []) if isinstance(payload, dict) else 0,
            "error": None if response.status_code < 400 else "HTTP_ERROR",
        }
    except Exception as exc:
        return {
            "url": url,
            "http_status": 0,
            "reachable": False,
            "model_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _listener_probe(base_url: str, candidate_ports: list[int]) -> dict[str, Any]:
    """Capture listeners and read-only probes for the base and backup ports."""
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    scheme = parsed.scheme or "http"
    base_port = parsed.port or 11434
    try:
        completed = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        # Keep only the benchmark ports.  The raw artifact is tracked and must
        # not leak unrelated local applications, proxy ports, or user sessions.
        target_tokens = tuple(f":{port}" for port in [base_port, *candidate_ports])
        listener_lines = [
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip() and any(token in line for token in target_tokens)
        ]
        lsof = {
            "command": "lsof -nP -iTCP -sTCP:LISTEN",
            "exit_code": completed.returncode,
            "lines": listener_lines,
            "error": completed.stderr.strip() or None,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        lsof = {
            "command": "lsof -nP -iTCP -sTCP:LISTEN",
            "exit_code": None,
            "lines": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    port_probes = []
    for port in sorted(set([base_port, *candidate_ports])):
        port_probes.append(_tags_probe(f"{scheme}://{host}:{port}"))
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_port": base_port,
        "candidate_backup_ports": candidate_ports,
        "lsof": lsof,
        "port_probes": port_probes,
    }


def _git_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=False
        )
        return {
            "revision": revision.stdout.strip() or None,
            "revision_exit_code": revision.returncode,
            "working_tree_dirty": bool(dirty.stdout.strip()),
            "status_exit_code": dirty.returncode,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"revision": None, "working_tree_dirty": None, "error": f"{type(exc).__name__}: {exc}"}


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
    parser.add_argument("--output", help="write the JSON artifact to this path instead of stdout")
    args = parser.parse_args()
    workers_list = [int(value) for value in args.workers.split(",")]
    started_at = datetime.now(timezone.utc).isoformat()
    listener_probe = _listener_probe(args.base_url, [11435, 11436, 11437, 11438])
    all_blocks: list[dict[str, Any]] = []
    for workers in workers_list:
        # keep_alive=0 makes the first sample a reproducible cold-load boundary.
        cold = _wave(args.base_url, workers, "cold", 0, wave_id=0)
        # Keep the model resident for the warm waves; these exclude the prewarm cost.
        prewarm = _wave(args.base_url, 1, "prewarm", "30s", wave_id=0)
        ps_after_prewarm = _ps(args.base_url)
        resource_probe_after_prewarm = _resource_probe(args.base_url, ps_after_prewarm)
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
                "resource_probe_after_prewarm": resource_probe_after_prewarm,
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
        "schema_version": ARTIFACT_SCHEMA_VERSION,
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
        "provenance": {
            "captured_at": started_at,
            "script": "ollama-topology-benchmark.py",
            "script_schema_version": ARTIFACT_SCHEMA_VERSION,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "system": platform.system(),
            "machine": platform.machine(),
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
            "git": _git_provenance(),
            "fixed_prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
            "arguments": {
                "base_url": args.base_url,
                "workers": workers_list,
                "warm_waves": args.warm_waves,
            },
        },
        "listener_probe": listener_probe,
        "blocks": all_blocks,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
