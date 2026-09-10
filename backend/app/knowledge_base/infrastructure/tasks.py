"""异步索引任务（spec-012）。

**为什么是单线程池（max_workers=1）**：

1. Ollama 侧：v2 用 `qwen3.8-27b-q4`（约 17GB）做结构分析，向量化用 `bge-m3`，
   两者同时跑会抢显存；
2. Qdrant 侧：本地文件模式有写锁，并发写入不安全；
3. 论文量级（个人知识库，数十篇）不需要并行，串行足够且可预测。

因此本模块用一个模块级单线程池串行执行所有异步索引任务，
并提供**任务去重**（同一 `paper_id + chunker` 不重复跑）与
**重启残留处理**（启动时把仍为 indexing 的版本标记失败）。
"""

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional, Tuple

from backend.app.knowledge_base.infrastructure import store

# 单线程是硬要求，见模块 docstring。
_MAX_WORKERS = 1

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()

# 进行中的任务：(paper_id, chunker) -> Future
_running: Dict[Tuple[str, str], Future] = {}
_running_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    """懒加载单线程池。"""
    global _executor
    with _executor_lock:
        if _executor is None or _executor._shutdown:  # noqa: SLF001
            _executor = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS, thread_name_prefix="kb-index"
            )
        return _executor


def submit_index_task(
    paper_id: str,
    chunker: str,
    runner: Callable[[Callable[[int], None]], object],
) -> bool:
    """提交一个异步索引任务；已在跑则返回 False（去重，不重复跑）。

    `runner` 签名为 `runner(progress) -> object`，其中 `progress` 是
    `Callable[[int], None]`，接收 0-100 的进度值。
    `runner` 内部应自行收敛异常（参见 `index.index_paper_chunker`）；
    本模块仍有兜底，防止线程带异常退出后状态永远卡在 `indexing`。
    """
    key = (paper_id, chunker)
    with _running_lock:
        existing = _running.get(key)
        if existing is not None and not existing.done():
            return False
        future = get_executor().submit(_guarded_run, key, runner)
        _running[key] = future
        return True


def run_index_task_sync(
    paper_id: str,
    chunker: str,
    runner: Callable[[Callable[[int], None]], object],
    timeout: Optional[float] = None,
) -> object:
    """提交到同一单线程池并**同步等待**结果（spec-012 R1）。

    给 v1 上传路径使用：既保持「上传返回时 v1 已建好索引」的产品行为，
    又让 v1 与 v2 异步任务共用同一个单线程队列，避免 bge-m3 向量化与
    27B 结构分析抢显存——R1 明确禁止对这份竞争"默认无视"。

    若同版本任务已在跑，则直接等待它而不重复执行（与 `submit_index_task` 一致）。
    """
    key = (paper_id, chunker)
    with _running_lock:
        existing = _running.get(key)
        if existing is not None and not existing.done():
            future = existing
        else:
            future = get_executor().submit(_guarded_run, key, runner)
            _running[key] = future
    try:
        return future.result(timeout=timeout)
    except Exception as error:  # runner 内部应已收敛，这里只兜底
        return {"error": f"索引任务异常：{error}"}


def _guarded_run(key: Tuple[str, str], runner: Callable[[Callable[[int], None]], object]) -> None:
    try:
        runner(_make_progress_writer(key))
    except Exception as error:  # 兜底：确保状态不会永远停在 indexing
        store.update_chunker_state(
            key[0],
            key[1],
            status=store.STATUS_FAILED,
            progress=0,
            error=f"索引任务异常终止：{error}",
        )
    finally:
        with _running_lock:
            _running.pop(key, None)


def _make_progress_writer(key: Tuple[str, str]) -> Callable[[int], None]:
    def _write(value: int) -> None:
        store.update_chunker_state(
            key[0],
            key[1],
            progress=max(0, min(100, int(value))),
        )

    return _write


def is_running(paper_id: str, chunker: Optional[str] = None) -> bool:
    """是否存在进行中的任务；`chunker` 为 None 时判断该论文任一版本。"""
    with _running_lock:
        if chunker is not None:
            future = _running.get((paper_id, chunker))
            return future is not None and not future.done()
        return any(
            future is not None and not future.done()
            for (pid, _), future in _running.items()
            if pid == paper_id
        )


def running_count() -> int:
    """当前进行中的任务数（供健康检查与单测使用）。"""
    with _running_lock:
        return sum(1 for future in _running.values() if not future.done())


def mark_interrupted_on_startup(reason: str = "服务重启导致中断") -> int:
    """启动时调用：把残留的 `indexing` 标记失败，返回被标记数量。

    异步任务无法跨进程存活，残留的 indexing 会让进度条永远卡住，
    必须由用户点「重建索引」重新触发。
    """
    return store.mark_interrupted_tasks(reason=reason)


def shutdown(wait: bool = False) -> None:
    """关闭线程池（主要用于测试）。"""
    global _executor
    with _executor_lock:
        if _executor is not None and not _executor._shutdown:  # noqa: SLF001
            _executor.shutdown(wait=wait)
        _executor = None
    with _running_lock:
        _running.clear()
