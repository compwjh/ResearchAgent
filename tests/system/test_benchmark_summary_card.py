"""基准卡片 A 打通的后端契约测试（裁决 A，前端零改动）。

锁定四件事：
1. report → ``{warm?: {...}, cold?: {...}}`` 的四项指标改名、真实取值与前端
   ``boundedNumber`` 的 min/max 边界；
2. phase 按样本 ``is_cold_start`` 分组，failure_rate 按 phase 轮次计算；
3. 不传新增 CLI 参数时 ``--json`` stdout 与改动前逐字节一致；
4. ``--task-id`` 通道写入的 ``safe_payload_json`` 完整保留 benchmark_summary，
   且任务 status 不被改变（复用 ResearchStore.append_event 的 ``task`` 类型）。

全程不触达 Ollama：CLI 用例 patch ``bench.run_benchmark``，DB 用例用 tmp_path 独立库。
"""

from __future__ import annotations

import importlib
import json
import math
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import bench_ollama_routes as bench  # noqa: E402

from backend.app.memory.repository import OWNER_ID  # noqa: E402
from backend.app.research.domain.models import ResearchTask  # noqa: E402
from backend.app.research.infrastructure.research_store import (  # noqa: E402
    ResearchStore,
    _safe_event_payload,
)

research_store_module = importlib.import_module("backend.app.research.infrastructure.research_store")

# 前端 research-tasks.js:109-120 的四项正式键名与其 boundedNumber 边界（逐字对齐）。
EXPECTED_METRIC_NAMES = (
    "median_ttft_ms",
    "throughput_completion_tokens_per_s",
    "peak_memory_bytes",
    "failure_rate",
)
EXPECTED_BOUNDS = {
    "median_ttft_ms": (0.0, 600000.0),
    "throughput_completion_tokens_per_s": (0.0, 100000.0),
    "peak_memory_bytes": (0.0, 1e15),
    "failure_rate": (0.0, 1.0),
}
FIXED_PEAK_RSS = 123456789


@pytest.fixture(scope="module")
def summary_mod():
    """延迟导入被测模块，让 RED 阶段的失败定位到具体用例而非收集期。"""
    return importlib.import_module("backend.app.platform.benchmark_summary")


def _sample(ttft_ms, tokens_per_sec, *, cold=0.0):
    return {"ttft_ms": ttft_ms, "tokens_per_sec": tokens_per_sec, "is_cold_start": cold}


def _report(routes=None, *, runs=1):
    """与真实取证 benchmark-real.json 同形状（两链路各 1 轮、均 warm、errors 空）。"""
    default_routes = {
        "langchain": {"samples": [_sample(27756.266, 0.0)], "avg": {}, "errors": []},
        "direct": {"samples": [_sample(39960.904, 38.704)], "avg": {}, "errors": []},
    }
    return {
        "question": "用一句话说明什么是性能基准。",
        "model": "qwen3.5:9b",
        "runs": runs,
        "routes": default_routes if routes is None else routes,
        "diff": {
            "ttft_ms": -12204.638,
            "client_wall_ms": -12142.031,
            "overhead_ms": -8.533,
            "total_ms": -40584.774,
        },
    }


def _assert_frontend_bounded(summary, mod):
    """模拟前端 boundedNumber：数值有限且落在 [min, max]，否则前端会静默丢弃该项。"""
    assert summary
    for phase in ("warm", "cold"):
        if phase not in summary:
            continue
        for name, value in summary[phase].items():
            assert name in mod.METRIC_NAMES, name
            assert name in EXPECTED_BOUNDS, name
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
            assert math.isfinite(float(value))
            low, high = EXPECTED_BOUNDS[name]
            assert low <= value <= high, (name, value)


def test_four_metrics_renamed_and_within_frontend_bounds(summary_mod, monkeypatch):
    """真实 report → 四项改名、真实中位数、真实 RSS、failure_rate=0，全部通过前端边界。"""
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    summary = summary_mod.benchmark_summary_from_report(_report())

    assert summary_mod.METRIC_NAMES == EXPECTED_METRIC_NAMES
    assert summary_mod.METRIC_BOUNDS == EXPECTED_BOUNDS
    assert set(summary) == {"warm"}  # 本次两条链路 is_cold_start 均为 0，cold 允许缺省
    warm = summary["warm"]
    assert set(warm) == set(EXPECTED_METRIC_NAMES)
    # 脚本原名 ttft_ms/tokens_per_sec 不在前端别名表内，必须显式改名。
    assert "tokens_per_sec" not in warm and "ttft_ms" not in warm
    assert warm["median_ttft_ms"] == pytest.approx(33858.585)
    assert warm["throughput_completion_tokens_per_s"] == pytest.approx(19.352)
    assert warm["peak_memory_bytes"] == FIXED_PEAK_RSS  # 真实测量值，非占位/非 0 冒充
    assert warm["failure_rate"] == 0.0  # errors 为空的真实测量值
    _assert_frontend_bounded(summary, summary_mod)


def test_phase_grouping_uses_is_cold_start_and_omits_empty_phase(summary_mod, monkeypatch):
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    routes = {
        "warm-route": {
            "samples": [_sample(100.0, 10.0), _sample(300.0, 30.0)],
            "avg": {}, "errors": [],
        },
        "cold-route": {
            "samples": [_sample(900.0, 90.0, cold=1.0)],
            "avg": {}, "errors": [],
        },
    }
    summary = summary_mod.benchmark_summary_from_report(_report(routes))

    assert set(summary) == {"warm", "cold"}
    assert summary["warm"]["median_ttft_ms"] == pytest.approx(200.0)
    assert summary["warm"]["throughput_completion_tokens_per_s"] == pytest.approx(20.0)
    assert summary["cold"]["median_ttft_ms"] == pytest.approx(900.0)
    assert summary["cold"]["throughput_completion_tokens_per_s"] == pytest.approx(90.0)
    _assert_frontend_bounded(summary, summary_mod)


def test_only_cold_when_every_sample_is_cold(summary_mod, monkeypatch):
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    routes = {"r": {"samples": [_sample(500.0, 5.0, cold=1.0)], "avg": {}, "errors": []}}
    summary = summary_mod.benchmark_summary_from_report(_report(routes))
    assert set(summary) == {"cold"}
    assert "warm" not in summary
    _assert_frontend_bounded(summary, summary_mod)


def test_failure_rate_is_errors_over_phase_rounds(summary_mod, monkeypatch):
    """warm: 2 成功 + 1 失败 = 1/3；cold: 1 成功 + 1 失败 = 1/2，且落在 [0,1]。"""
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    routes = {
        "warm-route": {
            "samples": [_sample(100.0, 10.0), _sample(300.0, 30.0)],
            "avg": {}, "errors": ["RuntimeError: boom"],
        },
        "cold-route": {
            "samples": [_sample(900.0, 90.0, cold=1.0)],
            "avg": {}, "errors": ["TimeoutError: slow"],
        },
    }
    summary = summary_mod.benchmark_summary_from_report(_report(routes, runs=2))

    assert summary["warm"]["failure_rate"] == 0.333
    assert summary["cold"]["failure_rate"] == 0.5
    for phase in summary.values():
        assert 0.0 <= phase["failure_rate"] <= 1.0
    _assert_frontend_bounded(summary, summary_mod)


def test_peak_rss_bytes_converts_platform_units(summary_mod, monkeypatch):
    """macOS ru_maxrss 是 bytes（原值），Linux 是 KiB（×1024），按 sys.platform 换算。"""
    fake_usage = mock.Mock(ru_maxrss=4096)
    monkeypatch.setattr(summary_mod.resource, "getrusage", lambda _who: fake_usage)
    assert summary_mod.peak_rss_bytes("darwin") == 4096
    assert summary_mod.peak_rss_bytes("linux") == 4096 * 1024
    # 不显式传平台时取真实 sys.platform（而非硬编码某个平台）。
    expected_default = 4096 if sys.platform == "darwin" else 4096 * 1024
    assert summary_mod.peak_rss_bytes() == expected_default


def _run_cli(capsys, report, extra):
    with mock.patch.object(bench, "run_benchmark", return_value=report):
        code = bench.main(["--json", "--runs", "1", *extra])
    out = capsys.readouterr().out
    assert code == 0
    return out


def test_default_json_output_unchanged_and_new_flags_do_not_touch_stdout(capsys, tmp_path, monkeypatch):
    """默认 --json 逐字节等于 report 的 JSON；新增参数只落地副作用，不动 stdout。"""
    fake_store = mock.Mock()
    monkeypatch.setattr(research_store_module, "ResearchStore", lambda: fake_store)
    report = _report()

    baseline = _run_cli(capsys, report, [])
    assert baseline == json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    with_summary = _run_cli(capsys, report, ["--summary-output", str(tmp_path / "summary.json")])
    with_event = _run_cli(capsys, report, ["--task-id", "task-x"])
    assert with_summary == baseline
    assert with_event == baseline
    # diff = langchain - direct 口径与 report 结构均未被映射/新通道改动。
    assert json.loads(baseline)["diff"] == report["diff"]
    assert json.loads(baseline)["routes"] == report["routes"]
    assert json.loads(baseline)["diff"]["ttft_ms"] == -12204.638


def test_summary_output_writes_contract_shape(capsys, tmp_path, monkeypatch, summary_mod):
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    out_path = tmp_path / "nested" / "summary.json"
    report = _report()
    with mock.patch.object(bench, "run_benchmark", return_value=report):
        assert bench.main(["--json", "--summary-output", str(out_path)]) == 0
    capsys.readouterr()

    assert out_path.is_file()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written == summary_mod.benchmark_summary_from_report(report)
    assert set(written) == {"warm"}
    assert set(written["warm"]) == set(EXPECTED_METRIC_NAMES)


def test_safe_event_payload_keeps_full_summary_and_still_scrubs_sensitive_keys(summary_mod, monkeypatch):
    """透传只针对 benchmark_summary 子树，既有白名单/敏感 scrub 语义不变。"""
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    summary = summary_mod.benchmark_summary_from_report(_report())
    safe = _safe_event_payload({
        "benchmark_summary": summary,
        "status": "completed",
        "prompt": "do not leak",
        "token": "abc",
        "summary": "Authorization: Bearer abc",
    })

    assert safe["benchmark_summary"] == summary
    assert set(safe["benchmark_summary"]["warm"]) == set(EXPECTED_METRIC_NAMES)
    assert safe["status"] == "completed"
    assert "prompt" not in safe and "token" not in safe
    assert "[REDACTED]" in safe["summary"]


def test_task_id_channel_persists_full_payload_and_status_unchanged(
    capsys, tmp_path, monkeypatch, summary_mod
):
    monkeypatch.setattr(summary_mod, "peak_rss_bytes", lambda: FIXED_PEAK_RSS)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        uuid.uuid4().hex, OWNER_ID, uuid.uuid4().hex, "goal", "zh", "balanced",
        False, 2, 60, "completed", 1, "now", "now",
    )
    store.create_task(task)
    before = store.get_task(task.research_task_id, OWNER_ID).status
    monkeypatch.setattr(research_store_module, "ResearchStore", lambda: store)
    report = _report()

    with mock.patch.object(bench, "run_benchmark", return_value=report):
        assert bench.main(["--json", "--task-id", task.research_task_id]) == 0
    capsys.readouterr()

    events = store.list_events(task.research_task_id)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "task"
    payload = json.loads(event.safe_payload_json)
    assert payload["benchmark_summary"] == summary_mod.benchmark_summary_from_report(report)
    assert set(payload["benchmark_summary"]["warm"]) == set(EXPECTED_METRIC_NAMES)
    _assert_frontend_bounded(payload["benchmark_summary"], summary_mod)
    assert store.get_task(task.research_task_id, OWNER_ID).status == before
