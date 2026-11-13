"""P2③ 在线实时评测契约测试（离线优先 + 显式开关默认关闭 + 异步旁路）。

覆盖定稿口径：默认关闭零评分 / 开关打开且采样命中异步写 score / 判官失败不记 0 分
且不冒泡 / 同步链路不增加调用；另覆盖配置默认值与边界、采样门、熔断、独立超时。
全部离线：判官/回写用 fake，不连真实 Ollama / Langfuse。
"""
from __future__ import annotations

import threading
import time
import urllib.error
from urllib.parse import unquote, urlsplit

import pytest

from backend.app.platform import config as platform_config
from backend.eval_042 import langfuse_export, online_eval, runner


class _FakeLangfuse:
    """内存 Langfuse：/traces/{id} 返回已完成 trace；scores 支持 exact-ID GET/POST。"""

    def __init__(self):
        self.posts: list = []
        self.scores: dict = {}
        self.traces: dict = {}
        self.gets: list = []

    def get(self, url):
        path = urlsplit(url).path
        self.gets.append(path)
        tail = unquote(path.rstrip("/").rsplit("/", 1)[-1])
        if "/traces/" in path:
            return dict(self.traces.get(tail, {"id": tail, "input": "q", "output": "a real complete answer"}))
        if tail in self.scores:
            return dict(self.scores[tail])
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    def post(self, url, body):
        self.posts.append(dict(body))
        score_id = body.get("id") or f"auto-{len(self.posts)}"
        score = {"id": score_id, "traceId": body["traceId"], "name": body["name"], "value": body["value"]}
        self.scores[score_id] = score
        return dict(score)


def _install(monkeypatch, service):
    monkeypatch.setattr(langfuse_export, "_get", service.get)
    monkeypatch.setattr(langfuse_export, "_post", service.post)
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)


def _settings(**kw):
    base = {"enabled": False, "sample_rate": 0.0, "judge_timeout_s": 30.0,
            "max_traces_per_tick": 20, "circuit_threshold": 3}
    base.update(kw)
    return online_eval.OnlineEvalSettings(**base)


def _scored_judge(model, task, question, answer, repeats, *, ctx=None):
    return [{"status": "scored", "label": "good", "score": 1.0,
             "explanation": "fully relevant"} for _ in range(repeats)]


def _unavailable_judge(model, task, question, answer, repeats, *, ctx=None):
    return [{"status": "unavailable", "label": None, "score": None,
             "explanation": "", "error": "judge down"} for _ in range(repeats)]


# ---- 配置：默认关闭 / 边界回退 / 不动 LANGFUSE_SAMPLE_RATE ----------------
def test_config_switches_default_off_and_langfuse_sample_rate_untouched():
    assert hasattr(platform_config, "EVAL_ONLINE_ENABLED")
    assert platform_config.EVAL_ONLINE_ENABLED is False
    assert platform_config.EVAL_ONLINE_SAMPLE_RATE == 0.0
    assert platform_config.EVAL_ONLINE_JUDGE_TIMEOUT_S == 30.0
    assert platform_config.EVAL_ONLINE_MAX_TRACES_PER_TICK == 20
    assert platform_config.EVAL_ONLINE_CIRCUIT_THRESHOLD == 3
    # 观测上报采样率纪律未被改动
    assert isinstance(platform_config.LANGFUSE_SAMPLE_RATE_RAW, str)
    settings = online_eval.load_settings()
    assert settings.enabled is False and settings.sample_rate == 0.0


def test_env_unit_interval_bounds_and_fallback(monkeypatch):
    for raw, expected in [("0.5", 0.5), ("0", 0.0), ("1", 1.0)]:
        monkeypatch.setenv("X_UNIT", raw)
        assert platform_config._env_unit_interval("X_UNIT", 0.0) == expected
    for raw in ("1.5", "-0.1", "nan", "abc"):
        monkeypatch.setenv("X_UNIT", raw)
        with pytest.warns(RuntimeWarning):
            assert platform_config._env_unit_interval("X_UNIT", 0.0) == 0.0
    monkeypatch.delenv("X_UNIT", raising=False)
    assert platform_config._env_unit_interval("X_UNIT", 0.25) == 0.25


def test_load_settings_reads_config_module(monkeypatch):
    class _Cfg:
        EVAL_ONLINE_ENABLED = True
        EVAL_ONLINE_SAMPLE_RATE = 0.4
        EVAL_ONLINE_JUDGE_TIMEOUT_S = 7.0
        EVAL_ONLINE_MAX_TRACES_PER_TICK = 3
        EVAL_ONLINE_CIRCUIT_THRESHOLD = 2

    s = online_eval.load_settings(_Cfg())
    assert (s.enabled, s.sample_rate, s.judge_timeout_s) == (True, 0.4, 7.0)
    assert (s.max_traces_per_tick, s.circuit_threshold) == (3, 2)


# ---- 1. 默认关闭时零评分 -------------------------------------------------
def test_default_off_produces_zero_scoring():
    called = []

    def spy_runner(**kwargs):
        called.append(kwargs)
        return {"status": "completed"}

    ev = online_eval.OnlineEvaluator(
        settings=_settings(), runner_fn=spy_runner, background=False,
    )
    status = ev.submit_completed_trace("trace-off")
    results = ev.process_pending()

    assert status == "disabled"
    assert results == []
    assert called == []                       # 判官/回写零调用
    assert ev.status()["queued"] == 0


def test_disabled_never_enqueues_even_with_full_sampling():
    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=False, sample_rate=1.0),
        runner_fn=lambda **k: pytest.fail("must not run"),
        background=False,
    )
    assert ev.submit_completed_trace("t") == "disabled"
    assert ev.status()["queued"] == 0


# ---- 采样门 ---------------------------------------------------------------
def test_sample_rate_gate():
    ev_off = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=0.0),
        runner_fn=lambda **k: None, background=False,
    )
    assert ev_off.submit_completed_trace("t") == "not_sampled"

    ev_full = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        runner_fn=lambda **k: None, background=False,
    )
    assert ev_full.submit_completed_trace("t") == "queued"

    seq = iter([0.2, 0.9])
    ev_half = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=0.5),
        runner_fn=lambda **k: None, background=False, rng=lambda: next(seq),
    )
    assert ev_half.submit_completed_trace("t1") == "queued"   # 0.2 < 0.5
    assert ev_half.submit_completed_trace("t2") == "not_sampled"  # 0.9 >= 0.5


# ---- 2. 开关打开且采样命中时（复用 runner）写 score ---------------------
def test_enabled_sampled_writes_score_via_existing_runner(tmp_path, monkeypatch):
    service = _FakeLangfuse()
    _install(monkeypatch, service)
    monkeypatch.setattr(runner.judge_client, "judge_repeats", _scored_judge)

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        background=False, output_dir=tmp_path / "report",
        fetch_trace=lambda tid: {"id": tid, "input": "question", "output": "a complete answer"},
    )
    assert ev.submit_completed_trace("trace-scored") == "queued"
    results = ev.process_pending()

    assert len(results) == 1
    assert results[0]["status"] == "SCORED"
    assert len(service.posts) == 1                     # 真实经 post_score 回写
    assert service.posts[0]["name"] == "chat_quality"
    assert service.posts[0]["value"] == 1.0
    assert service.posts[0]["traceId"] == "trace-scored"
    assert results[0]["score_id"] == service.posts[0]["id"]


# ---- 4. 同步链路不增加调用（判官全在后台线程，submit 立即返回）----------
def test_background_worker_is_async_and_submit_adds_no_sync_calls():
    runner_entered = threading.Event()
    release = threading.Event()
    calls = []

    def slow_runner(**kwargs):
        runner_entered.set()
        release.wait(2.0)
        calls.append(kwargs)
        return {"status": "completed", "document": {"status": "completed", "summary": {"scored": 1},
                "items": [{"trace_id": "t-async", "status": "scored", "score": 1.0,
                           "written": True, "score_id": "s1"}]}}

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        runner_fn=slow_runner, background=True,
    )
    started = time.perf_counter()
    status = ev.submit_completed_trace("t-async")
    elapsed = time.perf_counter() - started

    assert status == "queued"
    assert elapsed < 0.5                              # 同步链路零延迟增量（不等判官）
    assert runner_entered.wait(1.0)                  # 判官确实在后台线程跑起来了
    assert calls == []                               # submit 返回时判官尚未完成/未同步调用
    release.set()
    assert ev.wait_idle(2.0)
    assert len(calls) == 1
    ev.shutdown()


def test_synchronous_submit_never_invokes_runner():
    called = []
    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        runner_fn=lambda **k: called.append(k), background=False,
    )
    status = ev.submit_completed_trace("t")
    assert status == "queued"
    assert called == []                              # 只入队，零同步判官调用
    assert ev.status()["queued"] == 1


# ---- 3. 判官失败不记 0 分且不冒泡 ---------------------------------------
def test_judge_unavailable_never_writes_zero_and_never_bubbles(tmp_path, monkeypatch):
    service = _FakeLangfuse()
    _install(monkeypatch, service)
    monkeypatch.setattr(runner.judge_client, "judge_repeats", _unavailable_judge)

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        background=False, output_dir=tmp_path / "report",
        fetch_trace=lambda tid: {"id": tid, "input": "q", "output": "a complete answer"},
    )
    ev.submit_completed_trace("trace-unavail")
    results = ev.process_pending()                  # 必须不抛异常

    assert results[0]["status"] == "UNAVAILABLE"
    assert results[0]["score"] is None               # 绝不记 0 分
    assert service.posts == []                       # 一条 score 都不写
    assert not any(p.get("value") == 0 for p in service.posts)


def test_runner_exception_marks_unavailable_and_never_bubbles():
    def exploding(**kwargs):
        raise RuntimeError("judge backend exploded")

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        runner_fn=exploding, background=False,
    )
    ev.submit_completed_trace("t")
    results = ev.process_pending()                 # 必须不抛异常
    assert results[0]["status"] == "UNAVAILABLE"
    assert results[0]["score"] is None


def test_independent_timeout_marks_unavailable_without_zero():
    def timed_out(fn, timeout_s):
        raise TimeoutError("judge timeout")

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0, judge_timeout_s=0.01),
        runner_fn=lambda **k: {"status": "completed"}, background=False,
        bounded_runner=timed_out,
    )
    ev.submit_completed_trace("t")
    results = ev.process_pending()
    assert results[0]["status"] == "UNAVAILABLE"
    assert results[0]["score"] is None
    assert results[0]["reason"] == "TimeoutError"


# ---- 熔断 / 有界队列 -----------------------------------------------------
def test_circuit_breaker_opens_after_consecutive_failures():
    def failing(**kwargs):
        raise RuntimeError("judge down")

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0, circuit_threshold=2),
        runner_fn=failing, background=False,
    )
    for _ in range(2):
        ev.submit_completed_trace("t")
        ev.process_pending()
    assert ev.status()["circuit_open"] is True
    assert ev.submit_completed_trace("t") == "circuit_open"  # 熔断后跳过
    assert ev.status()["queued"] == 0


def test_bounded_queue_drops_when_full_without_blocking():
    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0),
        runner_fn=lambda **k: None, background=False, max_queue=1,
    )
    assert ev.submit_completed_trace("t1") == "queued"
    assert ev.submit_completed_trace("t2") == "queue_full"   # 有界，不阻塞


def test_poll_completed_traces_is_noop_when_disabled():
    listed = []

    def list_ids(limit):
        listed.append(limit)
        return ["a", "b"]

    ev = online_eval.OnlineEvaluator(
        settings=_settings(), runner_fn=lambda **k: None, background=False,
        list_trace_ids=list_ids,
    )
    assert ev.poll_completed_traces() == []
    assert listed == []                              # 默认关闭连 trace 都不拉


def test_poll_completed_traces_submits_sampled_bounded(monkeypatch):
    service = _FakeLangfuse()
    _install(monkeypatch, service)
    monkeypatch.setattr(runner.judge_client, "judge_repeats", _scored_judge)

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0, max_traces_per_tick=2),
        runner_fn=lambda **k: None, background=False,
        list_trace_ids=lambda limit: ["a", "b", "c"],
    )
    submitted = ev.poll_completed_traces()
    assert len(submitted) == 2                       # 单批有界
    assert ev.status()["queued"] == 2


def test_background_poller_is_noop_when_disabled():
    ev = online_eval.OnlineEvaluator(
        settings=_settings(), runner_fn=lambda **k: pytest.fail("must not run"),
        background=False, list_trace_ids=lambda limit: pytest.fail("must not poll"),
    )
    assert ev.start_background_poller(interval_s=0.01) is False  # 默认关闭不启线程
    assert ev.status()["worker_alive"] is False
    ev.shutdown()


def test_background_poller_auto_triggers_when_enabled(tmp_path, monkeypatch):
    service = _FakeLangfuse()
    _install(monkeypatch, service)
    monkeypatch.setattr(runner.judge_client, "judge_repeats", _scored_judge)

    ev = online_eval.OnlineEvaluator(
        settings=_settings(enabled=True, sample_rate=1.0, max_traces_per_tick=1),
        background=False, output_dir=tmp_path / "report",
        fetch_trace=lambda tid: {"id": tid, "input": "q", "output": "a complete answer"},
        list_trace_ids=lambda limit: ["trace-poller"],
    )
    assert ev.start_background_poller(interval_s=0.05) is True
    assert ev.wait_for_first_score(timeout=3.0) is True
    ev.shutdown()
    assert ev.status()["scored"] >= 1
    assert service.posts and service.posts[0]["traceId"] == "trace-poller"
