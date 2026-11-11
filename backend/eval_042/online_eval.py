"""P2③（spec-047 Task 06）在线实时评测：离线优先 + 显式开关默认关闭 + 异步旁路。

定稿口径（技术评审 §3 风险 4 / §4.3 / §5、task-06）：
- **离线优先 + 默认关闭**：开关 ``EVAL_ONLINE_ENABLED`` 默认 ``False``（在
  ``backend/app/platform/config.py``），独立采样率 ``EVAL_ONLINE_SAMPLE_RATE``
  默认 ``0.0``。关闭时本模块零调用：不拉 trace、不启判官、不回写、不启后台线程。
  **绝不复用/改动** ``LANGFUSE_SAMPLE_RATE``（那是观测上报采样率，语义不同）。
- **不进 SSE / 同步零增量 / 不新增端点或 SSE 事件类型**：本模块是自包含的
  「后台有界队列 + worker」旁路（与 045 加固项 04「flush 出 SSE」同款解耦），
  由「已完成 trace」（Langfuse 中已落库的 trace）离线回放按采样自动触发，
  本质仍是 Q2=A 离线回放路径，只是触发时机从人工 CLI 改为按采样自动触发。
  触发入口 ``submit_completed_trace()`` 非阻塞（只 put_nowait），判官/回写全在
  后台线程；不改业务对话链路、不改观测上报、不改 ``spans.py``。
- **全部复用 eval_042**：通过 ``runner.run(export=...)`` 复用 judge / report /
  ``post_score`` 回写；判官失败由 runner 既有 ``UNAVAILABLE`` 语义保证「不记 0 分」。
  本模块不自建评分/判官/回写框架，不记 0 分、不冒泡（fail-open）。
- **独立超时 / 熔断**：``EVAL_ONLINE_JUDGE_TIMEOUT_S`` 独立包裹单次评分；连续失败
  达 ``EVAL_ONLINE_CIRCUIT_THRESHOLD`` 打开熔断，冷却期内跳过评测并记日志。
- **只处理新产生的已完成 trace**：调用方仅提交本次运行/本 tick 观察到的已完成
  trace_id，不扫历史、不回填。
"""
from __future__ import annotations

import logging
import queue
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from backend.app.platform import config as platform_config

from . import langfuse_export, runner

logger = logging.getLogger(__name__)

# 有界队列默认上限（与 client.py 的 _FLUSH_QUEUE_MAXSIZE 同款解耦）。
DEFAULT_MAX_QUEUE = 256
# 熔断冷却（秒）：连续失败达阈值后，冷却期内丢弃新提交，避免判官不可用时反复重试。
_CIRCUIT_COOLDOWN_S = 30.0


@dataclass(frozen=True)
class OnlineEvalSettings:
    """在线评测只读配置快照（默认关闭 / 离线优先）。"""

    enabled: bool = False
    sample_rate: float = 0.0
    judge_timeout_s: float = 30.0
    max_traces_per_tick: int = 20
    circuit_threshold: int = 3


def load_settings(config_module: Any = platform_config) -> OnlineEvalSettings:
    """从 config 模块读取只读开关（鸭子类型，便于测试注入）。"""
    return OnlineEvalSettings(
        enabled=bool(getattr(config_module, "EVAL_ONLINE_ENABLED", False)),
        sample_rate=float(getattr(config_module, "EVAL_ONLINE_SAMPLE_RATE", 0.0)),
        judge_timeout_s=float(getattr(config_module, "EVAL_ONLINE_JUDGE_TIMEOUT_S", 30.0)),
        max_traces_per_tick=int(getattr(config_module, "EVAL_ONLINE_MAX_TRACES_PER_TICK", 20)),
        circuit_threshold=int(getattr(config_module, "EVAL_ONLINE_CIRCUIT_THRESHOLD", 3)),
    )


def _default_bounded_runner(fn: Callable[[], Any], timeout_s: float) -> Any:
    """在独立守护线程执行 fn，超时抛 TimeoutError；异常原样冒泡给上层 fail-open。

    守护线程保证超时后不会阻塞进程退出；独立超时不影响任何同步链路。
    """
    box: dict = {}

    def target() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 — 捕获后在调用线程重抛
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True, name="online-eval-judge")
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        raise TimeoutError("online eval judge timeout")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _unavailable(trace_id: str, reason: str) -> dict:
    """判官不可用/失败/超时的统一降级结果：绝不记 0 分。"""
    return {
        "trace_id": trace_id,
        "status": "UNAVAILABLE",
        "score": None,
        "score_id": None,
        "reason": reason,
    }


def _interpret(trace_id: str, result: Any) -> dict:
    """把 runner.run 结果规约为单条在线评测结果，不记 0 分、不放原始异常文本。"""
    if not isinstance(result, Mapping):
        return _unavailable(trace_id, "no_runner_result")
    document = result.get("document")
    items = document.get("items") if isinstance(document, Mapping) else None
    if not isinstance(items, list):
        return _unavailable(trace_id, "no_items")
    for item in items:
        if isinstance(item, Mapping) and item.get("status") == "scored" and item.get("written"):
            return {
                "trace_id": trace_id,
                "status": "SCORED",
                "score": item.get("score"),
                "score_id": item.get("score_id"),
                "reason": None,
            }
    # skipped / unavailable / failed 一律降级为 UNAVAILABLE（不写 score、不记 0）。
    return _unavailable(trace_id, "judge_unavailable")


class OnlineEvaluator:
    """后台有界队列触发器：采样命中的已完成 trace 异步复用 eval_042 评分。

    ``background=False`` 时仅入队，由 ``process_pending()`` 显式排空（供测试/受控
    窗口确定性验证）；``background=True`` 时首次成功入队懒启动单消费者守护线程。
    任何评分异常都被吞掉并记为 UNAVAILABLE（fail-open，绝不冒泡到业务链路）。
    """

    def __init__(
        self,
        *,
        settings: OnlineEvalSettings | None = None,
        runner_fn: Callable[..., Any] | None = None,
        background: bool = False,
        output_dir: Any = None,
        fetch_trace: Callable[[str], Mapping] | None = None,
        bounded_runner: Callable[[Callable[[], Any], float], Any] | None = None,
        rng: Callable[[], float] | None = None,
        max_queue: int | None = None,
        list_trace_ids: Callable[[int], list] | None = None,
        cooldown_s: float = _CIRCUIT_COOLDOWN_S,
    ) -> None:
        self._settings = settings or load_settings()
        self._runner_fn = runner_fn or runner.run
        self._fetch_trace = fetch_trace or langfuse_export.fetch_trace
        self._bounded_runner = bounded_runner or _default_bounded_runner
        self._rng = rng or random.random
        self._list_trace_ids = list_trace_ids or (
            lambda limit: langfuse_export.list_ollama_chat_trace_ids(limit=limit)
        )
        self._output_dir = output_dir
        self._background = background
        self._queue: "queue.Queue[str]" = queue.Queue(
            maxsize=max_queue if max_queue is not None else DEFAULT_MAX_QUEUE
        )
        self._lock = threading.Lock()
        self._inflight = 0
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._cooldown_s = cooldown_s
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._poller: threading.Thread | None = None
        self._first_score = threading.Event()
        self._stats = {
            "submitted": 0, "sampled_out": 0, "processed": 0,
            "scored": 0, "unavailable": 0,
        }

    # ---- 配置 / 状态 -----------------------------------------------------
    @property
    def settings(self) -> OnlineEvalSettings:
        return self._settings

    def status(self) -> dict:
        with self._lock:
            circuit_open = self._circuit_open()
            return {
                "enabled": self._settings.enabled,
                "queued": self._queue.qsize(),
                "inflight": self._inflight,
                "circuit_open": circuit_open,
                "consecutive_failures": self._consecutive_failures,
                "worker_alive": bool(self._worker and self._worker.is_alive()),
                **dict(self._stats),
            }

    # ---- 熔断 -----------------------------------------------------------
    def _circuit_open(self) -> bool:
        if self._circuit_open_until <= 0.0:
            return False
        if time.monotonic() >= self._circuit_open_until:
            self._circuit_open_until = 0.0
            self._consecutive_failures = 0
            logger.info("在线评测熔断冷却结束，恢复半开")
            return False
        return True

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._stats["unavailable"] += 1
            if self._consecutive_failures >= max(1, self._settings.circuit_threshold):
                self._circuit_open_until = time.monotonic() + self._cooldown_s
                logger.warning(
                    "在线评测连续失败 %d 次，打开熔断 %.0fs（判官不可用，跳过评测）",
                    self._consecutive_failures, self._cooldown_s,
                )

    def _record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._circuit_open_until = 0.0
            self._stats["scored"] += 1
        self._first_score.set()

    # ---- 采样门 ---------------------------------------------------------
    def _sampled(self) -> bool:
        rate = self._settings.sample_rate
        if rate <= 0.0:
            return False
        if rate >= 1.0:
            return True
        return self._rng() < rate

    # ---- 异步旁路触发入口（非阻塞、同步零增量）-------------------------
    def submit_completed_trace(self, trace_id: str) -> str:
        """trace 完成后的异步旁路入口。返回状态字符串，绝不调用判官/回写。"""
        if not self._settings.enabled:
            return "disabled"
        if not isinstance(trace_id, str) or not trace_id.strip():
            return "invalid_trace"
        with self._lock:
            if self._circuit_open():
                return "circuit_open"
        if not self._sampled():
            with self._lock:
                self._stats["sampled_out"] += 1
            return "not_sampled"
        try:
            self._queue.put_nowait(trace_id)
        except queue.Full:
            logger.warning("在线评测队列已满，丢弃一条已完成 trace 提交（不阻塞业务）")
            return "queue_full"
        with self._lock:
            self._stats["submitted"] += 1
        if self._background:
            self._ensure_worker()
        return "queued"

    def poll_completed_traces(self) -> list[str]:
        """离线回放「自动触发」：拉取已完成 trace，按独立采样提交，单批有界。"""
        if not self._settings.enabled:
            return []
        with self._lock:
            if self._circuit_open():
                return []
        try:
            ids = self._list_trace_ids(self._settings.max_traces_per_tick)
        except Exception as exc:  # noqa: BLE001 — fail-open
            logger.warning("拉取已完成 trace 失败（已忽略）：%s", type(exc).__name__)
            return []
        submitted: list[str] = []
        for trace_id in list(ids)[: max(1, self._settings.max_traces_per_tick)]:
            if self.submit_completed_trace(trace_id) == "queued":
                submitted.append(trace_id)
            if len(submitted) >= max(1, self._settings.max_traces_per_tick):
                break
        return submitted

    # ---- 排空 / worker --------------------------------------------------
    def _evaluate_one(self, trace_id: str) -> dict:
        """单条评分：复用 runner.run(export=...)，独立超时 + fail-open。"""
        def export():
            trace = self._fetch_trace(trace_id)
            inp, out = langfuse_export.extract_io(trace)
            return [langfuse_export.build_eval_item(trace_id, inp, out, task="chat_quality")]

        def invoke():
            return self._runner_fn(
                export=export,
                output_dir=self._output_dir,
                task="chat_quality",
            )

        try:
            result = self._bounded_runner(invoke, self._settings.judge_timeout_s)
            record = _interpret(trace_id, result)
        except BaseException as exc:  # noqa: BLE001 — 绝不冒泡到业务链路
            logger.warning(
                "在线评测评分失败（fail-open，已忽略）：%s", type(exc).__name__,
            )
            record = _unavailable(trace_id, type(exc).__name__)
        if record["status"] == "SCORED":
            self._record_success()
        else:
            self._record_failure()
        with self._lock:
            self._stats["processed"] += 1
        return record

    def process_pending(self, *, max_traces: int | None = None) -> list[dict]:
        """同步排空队列（测试 / 受控窗口确定性验证 / worker 复用）。"""
        limit = max_traces if max_traces is not None else self._settings.max_traces_per_tick
        results: list[dict] = []
        for _ in range(max(1, limit)):
            try:
                trace_id = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                results.append(self._evaluate_one(trace_id))
            finally:
                self._queue.task_done()
        return results

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop = threading.Event()
            self._worker = threading.Thread(
                target=self._worker_loop, daemon=True, name="online-eval-worker",
            )
            self._worker.start()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                trace_id = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            with self._lock:
                self._inflight += 1
            try:
                self._evaluate_one(trace_id)
            finally:
                self._queue.task_done()
                with self._lock:
                    self._inflight -= 1

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """等待后台队列排空（测试 / 受控取证用），超时返回 False。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if (self._queue.qsize() == 0 and self._inflight == 0
                        and self._stats["submitted"] == self._stats["processed"]):
                    return True
            time.sleep(0.01)
        return False

    def start_background_poller(self, *, interval_s: float = 5.0) -> bool:
        """启动自包含后台 poll 线程：周期性拉取已完成 trace 并异步评分。

        这是「trace 完成后按采样自动触发」的最小落点：完全独立于 SSE / 业务对话
        链路 / 观测上报，不新增端点或 SSE 事件类型，也不改 ``spans.py``。
        **默认关闭时直接返回 False，绝不启动任何线程**（离线优先、零增量）。
        """
        if not self._settings.enabled:
            return False
        with self._lock:
            if self._poller is not None and self._poller.is_alive():
                return True
            self._stop = threading.Event()
            self._poller = threading.Thread(
                target=self._poller_loop, args=(interval_s,),
                daemon=True, name="online-eval-poller",
            )
            self._poller.start()
        return True

    def _poller_loop(self, interval_s: float) -> None:
        while not self._stop.is_set():
            try:
                # 单 tick：拉取已完成 trace（按独立采样）→ 排空队列评分。
                # 两份工作都在本后台线程完成，不占用业务/ SSE 线程。
                self.poll_completed_traces()
                self.process_pending()
            except Exception as exc:  # noqa: BLE001 — fail-open，绝不冒泡
                logger.warning("在线评测后台 tick 异常（已忽略）：%s", type(exc).__name__)
            self._stop.wait(max(0.01, interval_s))

    def wait_for_first_score(self, timeout: float = 5.0) -> bool:
        """等待首条评分完成（测试 / 受控取证用），超时返回 False。"""
        return self._first_score.wait(timeout)

    def shutdown(self) -> None:
        """停止后台 worker / poller（幂等；守护线程不阻塞进程退出）。"""
        self._stop.set()
        for thread in (self._worker, self._poller):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
