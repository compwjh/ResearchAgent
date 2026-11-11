"""P2②（spec-047 Task 05）单向分数映射：业务 quality_score -> Langfuse score。

定稿口径（技术评审 §4.2 / task-05）：
- **单向**：``research_model_outcomes.quality_score`` -> Langfuse score
  ``research_quality_score``（NUMERIC）。本模块只读业务 outcome、只写 Langfuse，
  **不持有任何业务 store / DB 连接**，因此结构上不可能反向覆盖业务表；
  不新增业务端点、不建映射表、不迁历史数据，只处理调用方传入的本次运行新样本。
- **复用**：写侧复用 :func:`langfuse_export.post_score_idempotent`（其内部正是
  :func:`langfuse_export.post_score` + :func:`langfuse_export.find_score_by_id`
  的「先 exact-ID 回查后确定性 score_id 写入」幂等组合），不建第二套回写/框架。
  确定性 ``score_id`` 由 ``decision_id`` 经 ``extra`` 派生，重跑 delta=0。
- **NUMERIC**：沿用既有 ``post_score`` 的四字段 body（value 传 Python float）；
  Langfuse 依据数值型 value 推断 ``dataType=NUMERIC``（当前部署版本已实测）。
  不改 ``post_score`` body，避免触碰 045 已签字的幂等键与 score 契约。
- **fail-open**：quality_score 缺失/非法、trace 缺失、任意写入异常都只记日志并
  返回 ``skipped`` / ``failed`` 结果，绝不抛异常、绝不冒泡影响主链路。
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from typing import Any

from . import langfuse_export

logger = logging.getLogger(__name__)

SCORE_NAME = "research_quality_score"
# 说明性常量：Langfuse 由数值型 value 推断 NUMERIC；既有 post_score 不显式发
# dataType 字段（保持 045 的四字段 body 契约与确定性幂等键不变）。
SCORE_DATA_TYPE = "NUMERIC"
MAPPING_VERSION = "research-quality-score-map-v1"


def _get_field(outcome: Any, name: str) -> Any:
    """只读取值：同时兼容 Mapping 与 ModelOutcome 这类属性对象。"""
    if isinstance(outcome, Mapping):
        return outcome.get(name)
    return getattr(outcome, name, None)


def normalize_quality_score(value: Any) -> float | None:
    """校验并返回 0..1 的有限浮点；缺失/非法一律返回 None。

    非法包括：None、bool、字符串/容器、NaN、inf、以及越界（<0 或 >1）。
    """
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        return None
    return score


def build_score_comment(decision_id: Any) -> str:
    """comment 记录来源 decision_id + 映射版本（不含任何 trace 原文/凭据）。"""
    did = "" if decision_id is None else str(decision_id)
    return (
        "source=research_model_outcomes.quality_score; "
        f"decision_id={did}; map_version={MAPPING_VERSION}"
    )


def _result(
    status: str,
    *,
    reason: str | None = None,
    value: float | None = None,
    trace_id: str | None = None,
    decision_id: Any = None,
    score_id: str | None = None,
) -> dict:
    return {
        "status": status,
        "reason": reason,
        "name": SCORE_NAME,
        "value": value,
        "trace_id": trace_id,
        "decision_id": decision_id,
        "score_id": score_id,
    }


def map_quality_score(
    outcome: Any,
    trace_id: str | None,
    *,
    score_writer: Callable[..., Mapping] | None = None,
) -> dict:
    """把一条业务 outcome 的 quality_score 单向映射为一条 Langfuse NUMERIC score。

    ``outcome`` 为只读的业务样本（``ModelOutcome`` / Mapping，含 ``quality_score``
    与 ``decision_id``）；``trace_id`` 为该决策关联的真实 Langfuse trace。
    返回结构化结果 dict（status = mapped / skipped / failed），永不抛异常。
    """
    writer = (
        score_writer
        if score_writer is not None
        else langfuse_export.post_score_idempotent
    )
    decision_id: Any = None
    score: float | None = None
    try:
        decision_id = _get_field(outcome, "decision_id")
        score = normalize_quality_score(_get_field(outcome, "quality_score"))
        if score is None:
            return _result(
                "skipped", reason="missing_or_invalid_quality_score",
                trace_id=trace_id, decision_id=decision_id,
            )
        # outcome 与 trace 无关联时记 skip，绝不伪造 traceId。
        if not isinstance(trace_id, str) or not trace_id.strip():
            return _result(
                "skipped", reason="missing_trace_id",
                value=score, trace_id=trace_id, decision_id=decision_id,
            )
        posted = writer(
            name=SCORE_NAME,
            value=score,
            trace_id=trace_id,
            comment=build_score_comment(decision_id),
            report_version=MAPPING_VERSION,
            task=SCORE_NAME,
            extra=f"decision_id:{decision_id}",
        )
        score_id = posted.get("id") if isinstance(posted, Mapping) else None
        if not isinstance(score_id, str) or not score_id.strip():
            return _result(
                "failed", reason="score_write_failed",
                value=score, trace_id=trace_id, decision_id=decision_id,
            )
        return _result(
            "mapped", value=score, trace_id=trace_id,
            decision_id=decision_id, score_id=score_id,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open，绝不冒泡影响主链路
        # 只记异常类型名，不落原始异常文本（回归清单：payload 只放稳定码）。
        logger.warning(
            "quality_score -> %s 映射失败（fail-open，已忽略）：%s",
            SCORE_NAME, type(exc).__name__,
        )
        return _result(
            "failed", reason="score_write_failed",
            value=score, trace_id=trace_id, decision_id=decision_id,
        )


def map_decision_quality_score(
    store: Any,
    *,
    decision_id: str,
    owner_id: str,
    trace_id: str,
    score_writer: Callable[..., Mapping] | None = None,
) -> dict:
    """读侧走 ``research_store`` 既有 ``get_model_outcome``（只读），再单向映射。

    ``store`` 为鸭子类型（``ResearchStore`` 或其只读替身）；本函数只调用读方法，
    不调用任何写方法，保证「业务表未被反写」。
    """
    try:
        outcome = store.get_model_outcome(decision_id, owner_id=owner_id)
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("读取 ModelOutcome 失败（fail-open，已忽略）：%s", type(exc).__name__)
        return _result(
            "failed", reason="score_write_failed",
            trace_id=trace_id, decision_id=decision_id,
        )
    if outcome is None:
        return _result(
            "skipped", reason="missing_or_invalid_quality_score",
            trace_id=trace_id, decision_id=decision_id,
        )
    return map_quality_score(outcome, trace_id, score_writer=score_writer)
