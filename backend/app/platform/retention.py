"""事件表 retention 的唯一编排入口（由 ``main.lifespan`` 启动钩子调用）。

设计约束（F14/F15）：
- 当前三张事件表行数很小（raw_events 12 / processing_steps 74 /
  research_events 66），retention 是**面向未来增长**的保守清理，不是修复现有故障；
  不迁移、不主动删除现有历史数据。
- 只复用 ``MemoryRepository.prune_event_tables`` 与 ``ResearchStore.prune_events``
  两套既有 store 能力，本模块不实现第二套 SQL / 连接 / 配置读取。
- 触发时机由 ``main.lifespan`` 提供（启动低峰、未接流量）；每个库独立
  ``try/except``，异常只记日志（fail-open），绝不影响服务启动与业务读取。
- VACUUM 仅在确实删除了行之后执行，且用独立 autocommit 连接，避免改动两 store
  的既有连接/事务语义；VACUUM 失败同样只记日志。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.platform import config
from backend.app.platform.bootstrap import get_provider

logger = logging.getLogger(__name__)

# 与 repository.connection() 同量级：拿不到锁就快速放弃，不与长跑任务争锁。
_VACUUM_TIMEOUT_SECONDS = 5.0


def _vacuum(path: Path) -> None:
    """VACUUM 不能在事务内执行，故用独立的 autocommit 连接。"""
    connection = sqlite3.connect(str(path), timeout=_VACUUM_TIMEOUT_SECONDS, isolation_level=None)
    try:
        connection.execute("VACUUM")
    finally:
        connection.close()


def _deleted_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(int(item) for item in value.values())
    return int(value)


def run_event_retention(
    *,
    max_age_days: int | None = None,
    max_rows: int | None = None,
    now: datetime | None = None,
    vacuum: bool | None = None,
    memory_repository: Any | None = None,
    research_store: Any | None = None,
) -> dict[str, Any]:
    """跑一次保守清理；返回值仅用于日志/测试观察，异常一律不向外抛。

    ``max_age_days`` / ``max_rows`` / ``now`` / ``vacuum`` 为显式覆盖入口，
    未指定时由各 store 读取 ``platform.config`` 的 env 可配默认值。
    """
    summary: dict[str, Any] = {
        "enabled": config.EVENT_RETENTION_ENABLED,
        "deleted": {},
        "vacuumed": [],
        "errors": [],
    }
    if not summary["enabled"]:
        return summary

    try:
        memory = memory_repository if memory_repository is not None else get_provider("memory_repository")
        research = research_store if research_store is not None else get_provider("research_store")
    except Exception:
        logger.exception("[retention] 组合根解析失败（已忽略）")
        summary["errors"].append("providers")
        return summary

    prune_args = {"max_age_days": max_age_days, "max_rows": max_rows, "now": now}
    for name, store, method in (
        ("memory", memory, "prune_event_tables"),
        ("research", research, "prune_events"),
    ):
        try:
            summary["deleted"][name] = getattr(store, method)(**prune_args)
        except Exception:
            # fail-open：清理失败只记日志，服务启动与业务读取不受影响。
            logger.exception("[retention] %s 事件清理失败（已忽略）", name)
            summary["errors"].append(name)

    should_vacuum = config.EVENT_RETENTION_VACUUM if vacuum is None else bool(vacuum)
    if should_vacuum:
        for name, store in (("memory", memory), ("research", research)):
            deleted = summary["deleted"].get(name)
            if deleted is None or _deleted_count(deleted) <= 0:
                continue
            path = Path(store.database_path)
            try:
                _vacuum(path)
                summary["vacuumed"].append(str(path))
            except Exception:
                logger.warning("[retention] %s VACUUM 失败（已忽略）", name, exc_info=True)
                summary["errors"].append(f"{name}:vacuum")
    return summary
