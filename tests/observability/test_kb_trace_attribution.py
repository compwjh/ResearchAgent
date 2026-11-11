"""kb-ask 链路「一次请求一条 trace」契约测试（spec-045 第 07 项）。

覆盖三类行为：
1. kb-ask 链路所有 observations（检索 / 生成 / 四段 phase span / 7 个 score /
   根 observation）归属同一 trace_id；
2. ``name=kb-ask`` 根 observation 存在且已结束（被创建、被 end）；
3. 跨 yield 的 ContextVar 复位后仍指向同一 trace。

这些是**链路级契约测试**：用真实 ``fastapi.testclient.TestClient`` 驱动真实
``/api/kb/ask`` SSE generator（TestClient 与线上同样经过 starlette 的
``iterate_in_threadpool``，每次 next() 都从父 context ``copy_context()``，
跨 yield 确实丢 ContextVar），业务侧重依赖（Qdrant / Ollama 生成）按既有测试
惯例替换；观测侧用**进程内录制 client**（不复刻任何 transport / HTTP / 批处理，
只记录 observation 会挂到哪个 trace_id 上）。

真实 SDK + 真实 Ollama + 真实 Langfuse 的端到端核对不在此文件内冒充，
见 ``docs/sdd/plans/045/runs/task-08/trace-attribution-fix.json``。

运行：
  .venv/bin/python -m pytest tests/observability/test_kb_trace_attribution.py -q
"""

import contextvars
import itertools
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability import request_id as rid_mod
from backend.app.platform.observability import spans as spans_mod
from backend.app.platform.observability import trace as trace_mod
from backend.app.platform.observability.request_id import (
    bind_request_id,
    get_request_id,
    reset_request_id,
)
from backend.app.platform.observability.trace import (
    end_trace,
    get_current_trace_id,
    start_trace,
)
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings

# --------------------------------------------------------------------------- #
# 进程内录制 client：只模拟 SDK 的 trace_id 归属规则，不模拟任何网络行为。
#   - trace_context={"trace_id": X} -> observation 挂到 X
#   - trace_context=None            -> SDK 新建一条 trace（fresh id）
# 这与 langfuse 4.15.1 的 start_as_current_observation 归属语义一致。
# --------------------------------------------------------------------------- #

class _FakeOtelSpan:
    def __init__(self):
        self._start_time = None


class _RecordingObservation:
    def __init__(self, client, kwargs, trace_id):
        self.client = client
        self.kwargs = kwargs
        self.name = kwargs.get("name")
        self.as_type = kwargs.get("as_type")
        self.trace_id = trace_id
        self.ended = False
        self._otel_span = _FakeOtelSpan()

    def __enter__(self):
        # 惰性 CM：只有 __enter__ 才真正"创建" observation（复刻真 SDK）
        self.client.observations.append(self)
        self.client._current.append(self.trace_id)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.ended = True
        if self.client._current:
            self.client._current.pop()
        return False

    def update(self, **kwargs):
        return None

    def score(self, **kwargs):
        self.client.scores.append({"name": kwargs.get("name"), "trace_id": self.trace_id})
        return None


class _RecordingPhaseSpan:
    def __init__(self, client, name, trace_id):
        self.client = client
        self.record = {"name": name, "trace_id": trace_id, "ended": False}

    def __enter__(self):
        self.client.phase_spans.append(self.record)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_attribute(self, *args, **kwargs):
        return None

    def set_attributes(self, *args, **kwargs):
        return None

    def end(self, *args, **kwargs):
        self.record["ended"] = True


class _RecordingTracer:
    def __init__(self, client):
        self.client = client

    def start_as_current_span(self, name, **kwargs):
        current = self.client._current
        return _RecordingPhaseSpan(self.client, name, current[-1] if current else None)


class _RecordingClient:
    def __init__(self):
        self.observations = []
        self.scores = []
        self.phase_spans = []
        self._current = []
        self._counter = itertools.count(1)
        self._otel_tracer = _RecordingTracer(self)

    def _fresh_id(self):
        return f"{next(self._counter):032x}"

    def create_trace_id(self):
        return self._fresh_id()

    def start_as_current_observation(self, *, trace_context=None, **kwargs):
        tid = (trace_context or {}).get("trace_id") or self._fresh_id()
        return _RecordingObservation(self, kwargs, tid)

    def flush(self):
        return None


@pytest.fixture(autouse=True)
def _clean_context():
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    rid_mod.reset_request_id()
    trace_mod._current_trace_id.set(None)
    trace_mod._trace_token.set(None)
    yield
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    rid_mod.reset_request_id()
    trace_mod._current_trace_id.set(None)
    trace_mod._trace_token.set(None)


def _enabled(recorder):
    """与既有 test_stream_context_isolation.py 相同的启用方式。"""
    return (
        mock.patch.object(config, "LANGFUSE_ENABLED", True),
        mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"),
        mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"),
        mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "1.0"),
        mock.patch.object(obs_client, "get_client", return_value=recorder),
        mock.patch("random.random", return_value=0.1),
    )


def _fake_hit():
    return SimpleNamespace(
        file_name="paper.pdf", page=3, page_end=0, start_line=None, end_line=None,
        chunk_index=0, paper_id="p-1", chunker="v1", score=0.8, text="片段内容",
    )


def _fake_run():
    timings = OllamaTimings(
        load_ms=10.0, prompt_eval_ms=20.0, eval_ms=30.0, total_ms=60.0,
        prompt_tokens=5, completion_tokens=10,
    )
    result = OllamaChatResult(
        content="答案", thinking="", timings=timings, timings_available=True,
        first_token_ms=15.0, client_wall_ms=100.0,
    )
    return SimpleNamespace(
        events=iter([{"type": "token", "content": "答"}, {"type": "token", "content": "案"}]),
        result=result, route="langchain",
    )


def _fake_hybrid_search(question, **kwargs):
    """复刻真实检索链路的三处 record_event 写入点（观测侧仍走生产函数）。"""
    spans_mod.record_event(name="kb.embedding", metadata={"status": "ok"})
    spans_mod.record_event(name="kb.retrieval", metadata={"hit_count": 1, "status": "ok"})
    spans_mod.record_event(name="kb.rerank", metadata={"status": "ok"})
    return [_fake_hit()]


def _drive_kb_ask(recorder):
    """用真实 TestClient 跑完整 /api/kb/ask SSE 链路，返回 SSE 事件类型序列。"""
    import contextlib
    import json

    from backend.app.api import routes_kb
    from backend.app.main import app

    patches = list(_enabled(recorder)) + [
        mock.patch.object(routes_kb, "get_available_models", return_value=["m1"]),
        mock.patch.object(routes_kb, "hybrid_search", side_effect=_fake_hybrid_search),
        mock.patch.object(routes_kb, "run_chat", return_value=_fake_run()),
        mock.patch.object(routes_kb, "read_user_memory_or_empty", return_value=""),
        mock.patch.object(routes_kb, "enqueue_flush"),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        response = TestClient(app).post(
            "/api/kb/ask",
            json={"question": "什么是检索增强生成？", "model": "m1", "top_k": 3, "chunker": "v1"},
        )
    assert response.status_code == 200, response.text
    events = []
    for line in response.text.split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:])["type"])
    return events


# --------------------------------------------------------------------------- #
# ① 一次 kb-ask 请求 -> 一条 trace：全部 observations / phase span / score 同 ID
# --------------------------------------------------------------------------- #

def test_kb_ask_all_observations_share_one_trace_id():
    recorder = _RecordingClient()
    events = _drive_kb_ask(recorder)

    # SSE 帧序列不因本修复改变
    assert events == ["meta", "stage", "citations", "token", "token", "debug", "done"]

    observations = recorder.observations
    # 先核对 trace 归属：修复前 retrieval 挂 rid、generation 另起一条 trace
    trace_ids = {o.trace_id for o in observations}
    trace_ids |= {s["trace_id"] for s in recorder.phase_spans}
    trace_ids |= {s["trace_id"] for s in recorder.scores}
    assert len(trace_ids) == 1, (
        f"一次请求应只有一条 trace，实际 {len(trace_ids)} 条：{sorted(trace_ids)}；"
        f"observations={[(o.name, o.trace_id) for o in observations]}"
    )

    names = [o.name for o in observations]
    assert "kb-ask" in names, "根 observation 应可查"
    assert "kb.generation" in names, "生成 observation 应存在"
    assert "kb.retrieval" in names and "kb.rerank" in names and "kb.embedding" in names

    unified = next(iter(trace_ids))
    # 四段 phase span + 7 个 score 齐全，且都在同一 trace 上
    phase_names = sorted(s["name"] for s in recorder.phase_spans)
    assert phase_names == ["phase:decode", "phase:load", "phase:overhead", "phase:prefill"]
    assert len(recorder.scores) == 7
    assert all(s["trace_id"] == unified for s in recorder.scores)


# --------------------------------------------------------------------------- #
# ② 根 observation 存在且已结束（生命周期收口）
# --------------------------------------------------------------------------- #

def test_kb_ask_root_observation_exists_and_is_ended():
    recorder = _RecordingClient()
    _drive_kb_ask(recorder)

    roots = [o for o in recorder.observations if o.name == "kb-ask"]
    assert len(roots) == 1, (
        "name=kb-ask 根 observation 应可查（修复前 start_as_current_observation "
        "未被 enter，根 observation 根本不会创建）"
    )
    root = roots[0]
    assert root.ended is True, "根 observation 必须已结束（end/flush）"
    assert root.as_type == "span"
    assert root.trace_id and root.trace_id == recorder.observations[0].trace_id
    assert root.kwargs.get("metadata", {}).get("request_id") == root.trace_id


# --------------------------------------------------------------------------- #
# ③ 跨 yield 的 ContextVar 一致性绑定：复位后仍指向同一 trace
# --------------------------------------------------------------------------- #

def test_cross_yield_contextvar_reset_still_points_to_same_trace():
    binder = getattr(trace_mod, "bind_trace_context", None)
    assert binder is not None, "缺少跨 yield 的 ContextVar 一致性绑定入口"

    recorder = _RecordingClient()
    state = {}

    def sse_like_generator():
        rid = bind_request_id()
        tid = start_trace("kb-ask", tags=["kb"])
        state["rid"], state["tid"] = rid, tid
        assert tid == rid, "trace_id 应与统一 request_id 同源"
        yield "meta"
        # 新段：starlette 每次 next() 都从父 context copy_context()，两个 ID 全丢
        assert get_request_id() is None
        assert get_current_trace_id() is None
        binder(rid)
        assert get_request_id() == rid
        assert get_current_trace_id() == tid
        assert spans_mod._trace_context() == {"trace_id": tid}
        yield "citations"
        # 再跨一段，重复绑定必须幂等且仍指向同一 trace
        binder(rid)
        assert get_current_trace_id() == tid
        assert spans_mod._trace_context() == {"trace_id": tid}
        yield "done"

    import contextlib
    with contextlib.ExitStack() as stack:
        for p in _enabled(recorder):
            stack.enter_context(p)
        gen = sse_like_generator()
        # 每次 next() 都在父 context 的独立副本中执行，跨 yield 不回写
        assert contextvars.copy_context().run(next, gen) == "meta"
        assert contextvars.copy_context().run(next, gen) == "citations"
        assert contextvars.copy_context().run(next, gen) == "done"
        contextvars.copy_context().run(gen.close)

    assert state["rid"] == state["tid"]
    # 父 context 始终干净（不得污染其他并发请求）
    assert get_current_trace_id() is None
    assert get_request_id() is None
    end_trace()
    reset_request_id()


# --------------------------------------------------------------------------- #
# ④ 非回归护栏：chat 链路只重绑 request_id，不得凭空产生 trace_context
# --------------------------------------------------------------------------- #

def test_request_id_rebind_alone_does_not_create_trace_context():
    """chat/article/conversations 从不调 start_trace；bind_request_id 不得改其语义。"""
    rid = bind_request_id()
    assert get_current_trace_id() is None
    assert spans_mod._trace_context() is None

    bind_request_id(rid)
    assert get_request_id() == rid
    assert get_current_trace_id() is None
    assert spans_mod._trace_context() is None, "chat 链路的 trace_id 仍应由 SDK 自行生成"

    reset_request_id()
