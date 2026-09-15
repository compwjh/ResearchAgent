"""启动预热编排 + 就绪度登记（首屏就绪优化，spec 优化项 P1）。

背景
----
基线实测（docs/sdd/notes/startup-perf-baseline.md）：
- ``/api/kb/health`` 因「健康检查里做真实向量化」耗时 155s；
- jieba 首次分词、Ollama ``/api/tags``、稠密向量化、Qdrant 连通性这些冷启动成本
  当前都落在「请求路径」上，首屏姗姗来迟。

本模块把这些成本移出请求路径：服务启动时 ``start_warmup()`` 起一个**非阻塞**
daemon 线程，依次预热各项；每项状态登记进线程安全的注册表，供
``/api/ready`` 与 ``/api/kb/health`` 的 embedding 探测读取（短路，避免再次承担
完整往返代价）。

硬约束（fail-open）
------------------
- 任一预热项异常只记日志并标 ``failed``，**绝不向上抛、绝不阻塞启动**；
- 全部复用既有能力，禁止第二套 embedding / Qdrant / 模型列表实现；
- 注册表用 ``Lock`` 保护，线程安全。

预热项
------
- ``jieba``：调用一次 ``tokenize``，预热前缀词典（轻量，先做）；
- ``ollama_tags``：``refresh_available_models()`` 强制回源（轻量，先做）；
- ``embedding``：``embed_texts(["预热"])`` 稠密向量化（重量，后台做，带整体超时）；
- ``qdrant``：``get_client()`` + ``count_points`` 验证本地向量库连通（重量，后台做）。
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from backend.app.knowledge_base.application import count_points, get_client
from backend.app.knowledge_base.infrastructure.embed import embed_texts, tokenize
from backend.app.platform.config import (
    WARMUP_EMBEDDING_TIMEOUT_SECONDS,
    WARMUP_ENABLED,
    WARMUP_QDRANT_TIMEOUT_SECONDS,
)
from backend.app.platform.ollama import refresh_available_models

logger = logging.getLogger(__name__)

# 预热项键（顺序即执行顺序：轻量项先做，重量项后做）
WARMUP_ITEMS: List[str] = ["jieba", "ollama_tags", "embedding", "qdrant"]

# 终态集合：达到其一即视为该项「已有结论」
_TERMINAL_STATUSES = ("ready", "failed")


@dataclass
class _ItemState:
    status: str = "unknown"  # unknown | loading | ready | failed
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None


class _WarmupRegistry:
    """线程安全的就绪度登记表。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = False
        self._items: Dict[str, _ItemState] = {key: _ItemState() for key in WARMUP_ITEMS}

    def set_started(self, value: bool) -> None:
        with self._lock:
            self._started = value

    def is_started(self) -> bool:
        with self._lock:
            return self._started

    def mark_loading(self, key: str) -> None:
        with self._lock:
            self._items[key].status = "loading"

    def mark_done(self, key: str, *, ok: bool, elapsed_ms: float, error: Optional[str] = None) -> None:
        with self._lock:
            item = self._items[key]
            item.status = "ready" if ok else "failed"
            item.elapsed_ms = elapsed_ms
            item.error = error

    def snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return {
                key: {
                    "status": item.status,
                    "elapsed_ms": item.elapsed_ms,
                    "error": item.error,
                }
                for key, item in self._items.items()
            }

    def all_terminal(self) -> bool:
        with self._lock:
            return all(item.status in _TERMINAL_STATUSES for item in self._items.values())

    def reset(self) -> None:
        with self._lock:
            self._started = False
            self._items = {key: _ItemState() for key in WARMUP_ITEMS}


_registry = _WarmupRegistry()


def readiness_snapshot() -> Dict[str, dict]:
    """返回各预热项就绪度登记表（供 /api/ready 与 health 探测复用）。"""
    return _registry.snapshot()


def is_warmup_started() -> bool:
    return _registry.is_started()


def reset_warmup() -> None:
    """仅供测试与运维：清空登记表并允许再次 start（不中断正在跑的线程）。"""
    _registry.reset()


def _run_item(key: str, fn: Callable[[], None], *, timeout: Optional[float] = None) -> None:
    """执行单项预热；用 ``timeout`` 包裹重量项，超时即记 failed 而不挂起。

    ``fn`` 成功（正常返回）记 ``ready``，抛异常或超时记 ``failed``。任何异常都被
    吞掉，绝不向上抛。
    """
    _registry.mark_loading(key)
    started = time.perf_counter()
    ok = False
    error: Optional[str] = None
    if timeout is None:
        try:
            fn()
            ok = True
        except Exception as exc:  # 绝不向上抛
            error = f"{type(exc).__name__}: {exc}"
    else:
        box: Dict[str, bool] = {}

        def _work() -> None:
            try:
                fn()
                box["ok"] = True
            except Exception:
                # 失败明细在 _run_item 外层记录；此处只标记未完成。
                pass

        worker = threading.Thread(target=_work, daemon=True)
        worker.start()
        worker.join(timeout=timeout)
        ok = box.get("ok", False)
        if not ok and worker.is_alive():
            error = f"timeout after {timeout}s"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    _registry.mark_done(key, ok=ok, elapsed_ms=elapsed_ms, error=error)
    if ok:
        logger.info("[warmup] %s ready (%.1f ms)", key, elapsed_ms)
    else:
        logger.warning("[warmup] %s failed (%.1f ms): %s", key, elapsed_ms, error)


# ---------- 单项预热实现（全部复用既有能力，禁止第二套实现）----------


def _warm_jieba() -> None:
    # 调一次分词即可触发 jieba 首次构建前缀词典（基线 0.84s），后续请求 0ms。
    tokenize("预热")


def _warm_ollama_tags() -> None:
    # 强制回源刷新模型列表缓存（30s TTL + 5s 负缓存 + 单飞），首屏不再逐个请求都打满 5s。
    refresh_available_models()


def _warm_embedding() -> None:
    # 复用 embed_texts；整体超时由调用方 _run_item(timeout=WARMUP_EMBEDDING_TIMEOUT_SECONDS) 包裹，
    # 不可达时后台线程最多挂起这么久即记为 failed，注册表尽快收敛到终态。
    embed_texts(["预热"])


def _warm_qdrant() -> None:
    # 复用既有 get_client / count_points 验证本地向量库连通（不重复造轮子）。
    client = get_client()
    count_points(client)


def _runner() -> None:
    # 轻量项先做：jieba / ollama tags；重量项后台做：embedding / qdrant。
    _run_item("jieba", _warm_jieba)
    _run_item("ollama_tags", _warm_ollama_tags)
    _run_item("embedding", _warm_embedding, timeout=WARMUP_EMBEDDING_TIMEOUT_SECONDS)
    _run_item("qdrant", _warm_qdrant, timeout=WARMUP_QDRANT_TIMEOUT_SECONDS)
    snapshot = _registry.snapshot()
    logger.info(
        "[warmup] 完成：%s",
        {k: {"status": v["status"], "elapsed_ms": v["elapsed_ms"]} for k, v in snapshot.items()},
    )


def start_warmup() -> None:
    """起一个非阻塞 daemon 线程做预热编排；重复调用幂等。"""
    if not WARMUP_ENABLED:
        logger.info("[warmup] 已禁用（WARMUP_ENABLED=false）")
        return
    if _registry.is_started():
        return
    _registry.set_started(True)
    thread = threading.Thread(target=_runner, name="warmup", daemon=True)
    thread.start()
