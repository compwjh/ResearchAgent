"""SSE 客户端中断与并发请求下的 ContextVar 隔离回归（plans/013/task-05 历史缺口）。

覆盖：
① 流中断后 trace_id / request_id / reset token 正确复位（同一 context 与 SSE 式
   copy_context 两种驱动方式）；
② 并发请求下 ContextVar 不串线，每个任务拿到各自的 trace_id / request_id。

均为链路级契约测试：用真实 start_trace / end_trace / bind_request_id /
reset_request_id / decide_sampling 等生产函数，仅把 Langfuse client 换成不联网的
桩对象；不冒充真实 E2E（真实 E2E 见 runs/task-08/sdk-smoke.json）。

运行：
  .venv/bin/python -m pytest tests/observability/test_stream_context_isolation.py -q
"""

import contextvars
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import pytest

from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability import request_id as rid_mod
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


class _StubClient:
    """只提供 start_trace 需要的两个入口，不发网络请求。"""

    def create_trace_id(self):
        return "a" * 32

    def start_as_current_observation(self, **kwargs):
        return SimpleNamespace()


@pytest.fixture(autouse=True)
def _clean_context():
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    rid_mod.reset_request_id()
    yield
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    rid_mod.reset_request_id()


def _enabled(*, sample_rate="0.5"):
    """启用观测 + 固定采样随机源（0.1 < 0.5 → 采样决策被缓存到 ContextVar）。"""
    return (
        mock.patch.object(config, "LANGFUSE_ENABLED", True),
        mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"),
        mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"),
        mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", sample_rate),
        mock.patch.object(obs_client, "get_client", return_value=_StubClient()),
        mock.patch("random.random", return_value=0.1),
    )


def _sse_like_generator(frames=("meta", "token", "done")):
    """复刻 routes_kb.generate() 的上下文生命周期：入口绑定 → start_trace →
    逐帧 yield → finally 复位。客户端中断由 generator.close() 触发 GeneratorExit。"""
    rid = bind_request_id()
    try:
        bind_request_id(rid)
        start_trace("kb-ask", tags=["kb"])
        for frame in frames:
            bind_request_id(rid)  # 与生产一致：跨 yield 按同一 rid 幂等重绑
            yield frame
    finally:
        end_trace()
        reset_request_id()


# ---------------------------------------------------------------- ① 流中断复位

def test_client_interrupt_resets_trace_request_and_tokens_in_same_context():
    """同一 context 下中断：trace_id / request_id / 三类 token 全部复位。"""
    import contextlib

    with contextlib.ExitStack() as stack:
        for patch in _enabled():
            stack.enter_context(patch)

        gen = _sse_like_generator()
        assert next(gen) == "meta"
        assert get_current_trace_id(), "start_trace 后应有活动 trace"
        assert get_request_id() == get_current_trace_id()
        assert obs_config._sample_decision.get() is True, "采样决策应被 trace 级缓存"
        assert trace_mod._trace_token.get() is not None
        assert rid_mod._request_token.get() is not None

        # 模拟客户端在第 1 帧后断开连接
        gen.close()

        assert get_current_trace_id() is None, "中断后 trace_id 必须复位"
        assert get_request_id() is None, "中断后 request_id 必须复位"
        assert trace_mod._trace_token.get() is None, "trace reset token 必须清空"
        assert rid_mod._request_token.get() is None, "request reset token 必须清空"
        assert obs_config._sample_decision.get() is None, "采样决策必须复位"
        assert obs_config._sample_token.get() is None, "采样 reset token 必须清空"


def test_second_request_after_interrupt_gets_fresh_trace_id():
    """中断后的下一次请求不得复用残留 trace_id。"""
    import contextlib

    with contextlib.ExitStack() as stack:
        for patch in _enabled():
            stack.enter_context(patch)

        first = _sse_like_generator()
        next(first)
        first_id = get_current_trace_id()
        first.close()

        second = _sse_like_generator()
        next(second)
        second_id = get_current_trace_id()
        second.close()

        assert first_id and second_id
        assert first_id != second_id, "中断后不应残留上一次的 trace_id"


def test_sse_copied_contexts_interrupt_leaves_parent_clean_and_no_exception():
    """SSE 真实形态：starlette 每次 next() 都从父 context copy_context()。

    每个 next() 在独立副本中执行，跨 yield 后 ContextVar 不会回写父 context；
    generator.close() 的 finally 里用「别的 context 的 token」复位时必须被吞掉，
    不得把 GeneratorExit 变成异常，也不得污染父 context。
    """
    import contextlib

    with contextlib.ExitStack() as stack:
        for patch in _enabled():
            stack.enter_context(patch)

        gen = _sse_like_generator(frames=("meta", "token", "done"))
        # 只取 2 帧，模拟客户端中途断开
        assert contextvars.copy_context().run(next, gen) == "meta"
        assert contextvars.copy_context().run(next, gen) == "token"

        # 父 context 必须干净（每次 next 都在副本里）
        assert get_current_trace_id() is None
        assert get_request_id() is None

        # close 在一个新副本里跑 finally；token 来自别的 context，必须 fail-open
        contextvars.copy_context().run(gen.close)

        assert get_current_trace_id() is None, "父 context 不得残留 trace_id"
        assert get_request_id() is None, "父 context 不得残留 request_id"
        assert obs_config._sample_decision.get() is None
        assert not gen.gi_frame, "generator 应已关闭"


def test_end_trace_is_idempotent_after_interrupt():
    """复位后再调用 end_trace / reset_request_id 不得抛异常（token 已清空）。"""
    import contextlib

    with contextlib.ExitStack() as stack:
        for patch in _enabled():
            stack.enter_context(patch)
        gen = _sse_like_generator()
        next(gen)
        gen.close()
        end_trace()
        end_trace()
        reset_request_id()
        assert get_current_trace_id() is None
        assert get_request_id() is None


# ---------------------------------------------------------------- ② 并发不串线

def test_concurrent_requests_keep_distinct_trace_ids_without_cross_talk():
    """8 个并发任务在 barrier 处强制重叠，各自 trace_id/request_id 不串线。"""
    import contextlib

    workers = 8
    barrier = threading.Barrier(workers)
    lock = threading.Lock()
    results = {}

    with contextlib.ExitStack() as stack:
        for patch in _enabled(sample_rate="1.0"):
            stack.enter_context(patch)

        def worker(index):
            ctx = contextvars.copy_context()

            def task():
                rid = bind_request_id()
                tid = start_trace("kb-ask", tags=["kb"])
                assert tid == rid, "trace_id 应与 request_id 同源"
                # 强制所有任务同时进入临界点：若用全局变量必然在这里串线
                barrier.wait(timeout=15)
                own_trace = get_current_trace_id()
                own_request = get_request_id()
                return rid, tid, own_trace, own_request

            try:
                value = ctx.run(task)
                with lock:
                    results[index] = value
            finally:
                ctx.run(end_trace)
                ctx.run(reset_request_id)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(worker, range(workers)))

    assert len(results) == workers, "所有并发任务都必须完成"
    rids = [v[0] for v in results.values()]
    tids = [v[1] for v in results.values()]
    assert len(set(rids)) == workers, "request_id 不能重复"
    assert len(set(tids)) == workers, "trace_id 不能重复"
    for index, (rid, tid, own_trace, own_request) in results.items():
        assert own_trace == tid == rid, f"任务 {index} 的 trace_id 串线"
        assert own_request == rid, f"任务 {index} 的 request_id 串线"

    # 线程池结束不得污染父 context
    assert get_current_trace_id() is None
    assert get_request_id() is None


def test_concurrent_end_trace_does_not_reset_other_tasks_decision():
    """并发下 A 任务 end_trace 不得清掉 B 任务的采样决策（token 归属于各自 context）。"""
    import contextlib

    barrier = threading.Barrier(2)
    seen = {}
    lock = threading.Lock()

    with contextlib.ExitStack() as stack:
        for patch in _enabled(sample_rate="0.5"):
            stack.enter_context(patch)

        def worker(tag, do_reset):
            ctx = contextvars.copy_context()

            def task():
                bind_request_id()
                start_trace("kb-ask")
                barrier.wait(timeout=15)
                before = obs_config.should_sample()
                if do_reset:
                    end_trace()
                    reset_request_id()
                barrier.wait(timeout=15)  # 等 A 复位后 B 再读自己的决策
                after_holder = obs_config._sample_decision.get()
                return before, after_holder

            value = ctx.run(task)
            with lock:
                seen[tag] = value

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda a: worker(*a), [("reset", True), ("hold", False)]))

    # A 复位后自己的采样决策为空；B 未复位，仍持有自己的决策，未被 A 清掉
    assert seen["reset"][1] is None, "复位方应清空自己的采样决策"
    assert seen["hold"][1] is True, "未复位方的采样决策不应被并发任务清掉"


def test_sample_decision_is_shared_within_one_trace():
    """同一 trace 内各阶段共用一次采样决策（加固项 03 的 ContextVar 契约）。"""
    import contextlib

    with contextlib.ExitStack() as stack:
        for patch in _enabled(sample_rate="0.5"):
            stack.enter_context(patch)
        # 交替随机源：若未缓存，结果会在 True/False 间跳动
        with mock.patch("random.random", side_effect=itertools.cycle([0.9, 0.05])):
            bind_request_id()
            start_trace("kb-ask")
            decisions = [obs_config.should_sample() for _ in range(8)]
            assert len(set(decisions)) == 1, f"同一 trace 决策必须一致，实际 {decisions}"
            end_trace()
            reset_request_id()
