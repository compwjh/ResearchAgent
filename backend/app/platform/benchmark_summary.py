"""基准卡片（裁决 A）的 report → 前端契约映射，单一事实来源。

只做一件事：把 ``scripts/bench_ollama_routes.py::run_benchmark()`` 的 report
映射为 ``frontend/research-tasks.js`` 的 ``benchmarkSummaryFromState()`` 能消费的
``{warm?: {...}, cold?: {...}}`` 形状。纯函数，不写库、不发事件、不新增端点。

四项指标名逐字对齐 ``research-tasks.js:109-120`` 的 BENCHMARK_METRICS：
脚本原名 ``tokens_per_sec`` **不在** BENCHMARK_METRIC_ALIASES 的吞吐别名里，
必须显式改名为 ``throughput_completion_tokens_per_s``，否则前端会静默丢弃该项。
输出值按前端 ``boundedNumber`` 的 min/max 校验，越界直接不输出
（不钳制、不伪造、不用 0 冒充缺失数据；0 只能是真实测量值）。
"""

from __future__ import annotations

import math
import resource
import statistics
import sys
from collections.abc import Mapping
from typing import Any

PHASES = ("warm", "cold")

# 正式键名（不是脚本里的 ttft_ms / tokens_per_sec）。
METRIC_NAMES = (
    "median_ttft_ms",
    "throughput_completion_tokens_per_s",
    "peak_memory_bytes",
    "failure_rate",
)

# 与 frontend/research-tasks.js:110-113 BENCHMARK_METRICS 的 min/max 逐项一致。
METRIC_BOUNDS = {
    "median_ttft_ms": (0.0, 600000.0),
    "throughput_completion_tokens_per_s": (0.0, 100000.0),
    "peak_memory_bytes": (0.0, 1e15),
    "failure_rate": (0.0, 1.0),
}

_ROUND = 3  # 与 bench_ollama_routes 的指标精度一致


def peak_rss_bytes(platform_name: str | None = None) -> int:
    """基准进程真实峰值 RSS（``getrusage(RUSAGE_SELF).ru_maxrss``），单位 bytes。

    平台换算必须显式按 ``sys.platform`` 判定，不能靠数值大小猜平台：
    - macOS / Darwin：``ru_maxrss`` 返回 **bytes**，原值即可；
    - Linux：``ru_maxrss`` 返回 **KiB（KB，1024 bytes）**，须乘 1024。

    不使用 ``/api/ps`` 的 ``size_vram``：本机实测返回 ``{"models":[]}``，
    来源不稳定，且显存不等于基准进程 RSS。这里禁止任何占位值。
    """
    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    name = sys.platform if platform_name is None else platform_name
    if name == "darwin":
        return rss
    return rss * 1024


def _as_number(value: Any) -> float | None:
    """只接受有限数值（含纯数字字符串）；非法/NaN/Inf 返回 None（不伪造）。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _phase_of(sample: Mapping[str, Any]) -> str:
    """按样本 is_cold_start 分组：1 → cold，其余（含缺失/非法）→ warm。"""
    return "cold" if _as_number(sample.get("is_cold_start")) == 1.0 else "warm"


def _dominant_phase(phases: list[str]) -> str:
    """失败轮次没有样本、也就没有 is_cold_start 信息。

    归到同一 route 成功样本的多数 phase；平票或无成功样本归 warm（默认 phase）。
    本次真实基准两条链路 errors 均为空，此规则只影响 failure_rate 分母归属，
    不改动任何既有指标口径。
    """
    if phases.count("cold") > phases.count("warm"):
        return "cold"
    return "warm"


def _within_bounds(name: str, value: float) -> bool:
    """前端 boundedNumber 的等价校验：有限数值且落在 [min, max]。"""
    low, high = METRIC_BOUNDS[name]
    return math.isfinite(float(value)) and low <= value <= high


def benchmark_summary_from_report(
    report: Mapping[str, Any],
    *,
    peak_memory_bytes: int | None = None,
) -> dict[str, dict[str, float | int]]:
    """把 run_benchmark() 的 report 映射成前端契约形状；空 phase 不输出。

    - phase：按各样本 ``is_cold_start`` 分组（1 → cold，其余 → warm）；
    - ``median_ttft_ms``：该 phase 样本 ``ttft_ms`` 的中位数；
    - ``throughput_completion_tokens_per_s``：该 phase 样本 ``tokens_per_sec``
      的中位数（**原名不在前端别名表内，显式改名**）；
    - ``peak_memory_bytes``：基准进程真实峰值 RSS，禁止占位值；
    - ``failure_rate``：该 phase 失败轮次 / 该 phase 总轮次（成功样本 + 失败轮次）。

    ``peak_memory_bytes`` 参数仅供测试注入；不传时实时读取真实 RSS。
    """
    if not isinstance(report, Mapping):
        return {}
    memory = peak_rss_bytes() if peak_memory_bytes is None else int(peak_memory_bytes)

    ttft: dict[str, list[float]] = {phase: [] for phase in PHASES}
    throughput: dict[str, list[float]] = {phase: [] for phase in PHASES}
    rounds: dict[str, int] = dict.fromkeys(PHASES, 0)
    failures: dict[str, int] = dict.fromkeys(PHASES, 0)

    routes = report.get("routes")
    if not isinstance(routes, Mapping):
        routes = {}
    for data in routes.values():
        if not isinstance(data, Mapping):
            continue
        samples = data.get("samples")
        errors = data.get("errors")
        sample_list = samples if isinstance(samples, (list, tuple)) else ()
        error_list = errors if isinstance(errors, (list, tuple)) else ()

        route_phases: list[str] = []
        for sample in sample_list:
            if not isinstance(sample, Mapping):
                continue
            phase = _phase_of(sample)
            route_phases.append(phase)
            rounds[phase] += 1
            ttft_value = _as_number(sample.get("ttft_ms"))
            if ttft_value is not None:
                ttft[phase].append(ttft_value)
            tps_value = _as_number(sample.get("tokens_per_sec"))
            if tps_value is not None:
                throughput[phase].append(tps_value)

        failure_phase = _dominant_phase(route_phases)
        for _ in error_list:
            rounds[failure_phase] += 1
            failures[failure_phase] += 1

    summary: dict[str, dict[str, float | int]] = {}
    for phase in PHASES:
        metrics: dict[str, float | int] = {}
        if ttft[phase]:
            metrics["median_ttft_ms"] = round(statistics.median(ttft[phase]), _ROUND)
        if throughput[phase]:
            # 显式改名：tokens_per_sec 不在前端 BENCHMARK_METRIC_ALIASES 内。
            metrics["throughput_completion_tokens_per_s"] = round(
                statistics.median(throughput[phase]), _ROUND
            )
        if rounds[phase]:
            metrics["peak_memory_bytes"] = memory
            metrics["failure_rate"] = round(failures[phase] / rounds[phase], _ROUND)
        bounded = {name: value for name, value in metrics.items() if _within_bounds(name, value)}
        if bounded:
            summary[phase] = bounded
    return summary
