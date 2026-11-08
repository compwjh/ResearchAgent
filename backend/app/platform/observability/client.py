"""Langfuse client 单例、降级与异步 flush 队列（spec-013 / spec-045 Task 05）。

未启用、未配 key、SDK 不可用时一律返回 None，调用方按"无需上报"处理。
`flush()` 保留同步语义（供直接调用与测试）；spec-045 新增 `enqueue_flush()`：
把 flush 交给后台有界队列，使 SSE 尾包不再被 Langfuse 上报阻塞。
"""

import contextlib
import logging
import queue
import threading
import time
from typing import Optional

from backend.app.platform import config
from backend.app.platform.observability import config as obs_config

logger = logging.getLogger(__name__)

_client: Optional[object] = None
_client_initialized = False
_warned_missing_credentials = False

# ---- spec-045 Task 05：后台 flush 队列（有界 + 超时熔断）----
# 把 flush 从 SSE 关键路径移出：路由只 `enqueue_flush()`（非阻塞），
# 单消费者后台线程批量 flush。队列满则丢弃并计数告警（绝不拖慢业务尾包）。
_FLUSH_QUEUE_MAXSIZE = 256
_flush_queue: "queue.Queue" = queue.Queue(maxsize=_FLUSH_QUEUE_MAXSIZE)
_flush_dropped = 0
_flush_lock = threading.Lock()
_flush_worker: Optional[threading.Thread] = None
# 超时熔断：连续失败达到阈值后打开，冷却期内丢弃 flush 任务。
_FLUSH_FAILURE_THRESHOLD = 3
_FLUSH_COOLDOWN_SECONDS = 30.0
_flush_consecutive_failures = 0
_flush_circuit_open_until = 0.0


def get_client() -> Optional[object]:
    """返回 Langfuse client 单例；不可用时返回 None。

    只初始化一次：失败后不再反复重试，避免每次请求都付一次异常开销。
    """
    global _client, _client_initialized, _warned_missing_credentials

    if not obs_config.enabled():
        return None

    if not obs_config.credentials_ready():
        if not _warned_missing_credentials:
            logger.info("观测已启用但缺少 Langfuse 凭据（LANGFUSE_PUBLIC_KEY / SECRET_KEY），跳过上报")
            _warned_missing_credentials = True
        return None

    if _client_initialized:
        return _client

    _client_initialized = True
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_HOST,
            timeout=config.LANGFUSE_TIMEOUT,
        )
        logger.info("Langfuse client 已初始化（host=%s）", config.LANGFUSE_HOST)
    except Exception as error:  # noqa: BLE001 — 初始化失败只降级
        logger.warning("Langfuse client 初始化失败，本次运行不再上报：%s", error)
        _client = None

    return _client


def flush() -> None:
    """同步把排队中的事件立即送出（保留同步语义，供直接调用与测试）。失败只记日志。"""
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as error:  # noqa: BLE001
        logger.warning("Langfuse flush 失败（已忽略）：%s", error)


def _flush_circuit_is_open() -> bool:
    """熔断是否处于打开态（冷却期内）。"""
    global _flush_circuit_open_until, _flush_consecutive_failures
    if _flush_circuit_open_until <= 0.0:
        return False
    if time.monotonic() >= _flush_circuit_open_until:
        # 冷却结束，半开恢复
        _flush_circuit_open_until = 0.0
        _flush_consecutive_failures = 0
        logger.info("观测 flush 熔断已恢复（半开）")
        return False
    return True


def _open_flush_circuit() -> None:
    global _flush_circuit_open_until
    _flush_circuit_open_until = time.monotonic() + _FLUSH_COOLDOWN_SECONDS
    logger.warning(
        "观测 flush 连续失败 %d 次，打开熔断 %.0fs（冷却期内丢弃 flush 任务，"
        "修复点唯一：backend/app/platform/observability/client.py）",
        _FLUSH_FAILURE_THRESHOLD, _FLUSH_COOLDOWN_SECONDS,
    )


def _do_flush() -> None:
    global _flush_consecutive_failures
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
        _flush_consecutive_failures = 0
    except Exception as error:  # noqa: BLE001
        _flush_consecutive_failures += 1
        if _flush_consecutive_failures >= _FLUSH_FAILURE_THRESHOLD:
            _open_flush_circuit()
        logger.warning("后台 flush 失败（已忽略）：%s", error)


def _flush_worker_loop() -> None:
    """单消费者后台线程：取出 flush 任务，有界批量 + 超时熔断地执行。"""
    while True:
        try:
            _flush_queue.get(block=True)
        except Exception:  # noqa: BLE001
            continue
        try:
            # 有界批量：一次性排空队列里其它待处理任务，一次 flush 覆盖全部 SDK 缓冲。
            try:
                while _flush_queue.get_nowait() is not None:
                    pass
            except queue.Empty:
                pass
            if _flush_circuit_is_open():
                # 熔断打开：丢弃（SDK 缓冲可能滞后，但不再阻塞业务）。
                logger.warning("观测 flush 熔断打开中，丢弃本次 flush 任务")
                continue
            _do_flush()
        except Exception:  # noqa: BLE001
            pass
        finally:
            with contextlib.suppress(ValueError):
                _flush_queue.task_done()


def _ensure_flush_worker() -> None:
    """确保后台 flush 消费者线程已启动（单例）。"""
    global _flush_worker
    with _flush_lock:
        if _flush_worker is None or not _flush_worker.is_alive():
            _flush_worker = threading.Thread(
                target=_flush_worker_loop, daemon=True, name="obs-flush-worker"
            )
            _flush_worker.start()


def enqueue_flush() -> None:
    """非阻塞地把 flush 任务交给后台队列。队列满则丢弃并计数告警，绝不拖慢业务。"""
    _ensure_flush_worker()
    try:
        _flush_queue.put_nowait(True)
    except queue.Full:
        global _flush_dropped
        _flush_dropped += 1
        logger.warning(
            "观测 flush 队列已满（上限 %d），丢弃一条 flush 任务（累计丢弃 %d）；"
            "Langfuse 上报可能滞后",
            _FLUSH_QUEUE_MAXSIZE, _flush_dropped,
        )


def reset_for_tests() -> None:
    """重置单例与队列状态（仅供测试使用）。"""
    global _client, _client_initialized, _warned_missing_credentials
    global _flush_dropped, _flush_consecutive_failures, _flush_circuit_open_until
    _client = None
    _client_initialized = False
    _warned_missing_credentials = False
    _flush_dropped = 0
    _flush_consecutive_failures = 0
    _flush_circuit_open_until = 0.0
    try:
        while _flush_queue.get_nowait() is not None:
            pass
    except queue.Empty:
        pass
