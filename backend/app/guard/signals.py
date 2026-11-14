"""风险信号 → 执行防护的对接契约（Spec050 Task03 / Task08 并行接口）。

给 RAD / PIGuard 接入方（另一条开发线）的唯一入口：

    from backend.app.guard.signals import RiskSignal, report, mark_unavailable

    signal = RiskSignal(
        source_kind="pdf",            # web / pdf / tool_result / history / model_text
        source_ref="doc:abc#w3",      # 脱敏定位，禁止携带原文或凭据
        label=1,                      # 0=benign, 1=injection
        score=0.93,
        model_version="piguard-formal-v1",
        detector_version="3f284d8e",  # 权重或策略版本
        window_index=3, window_count=8,
        truncated=False, timed_out=False, uncovered_windows=0,
    )
    assessment = report(signal, owner_id=..., task_id=...)

语义（Spec050 决策第 2、7、11 条，不可放宽）：

1. 风险信号**只**是外部内容的注入风险证据，不能授予、扩大或替代任务授权。
   即使 label=0（benign），有副作用的动作仍须走单动作确认。
2. 信号进入既有 `guard-event-v1` 投影，不携带攻击原文、凭据或隐藏推理。
3. 检测器故障、超时或存在未覆盖窗口时，**必须核验的敏感动作暂停**，
   `assessment.requires_hold=True`；执行防护据此返回 GUARD_CHECK_UNAVAILABLE，
   不静默放行。普通问答可以降级，敏感动作不行。
4. 多窗口按最严重结论聚合；任何一窗故障即整体 hold。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from backend.app.guard import store
from backend.app.guard.contracts import EventStatus, GuardEvent

SOURCE_KINDS = frozenset({"web", "pdf", "tool_result", "history", "model_text"})
HOLD_REASON = "GUARD_CHECK_UNAVAILABLE"
INJECTION_REASON = "INJECTION_RISK_DETECTED"

__all__ = [
    "RiskSignal", "RiskAssessment", "SOURCE_KINDS", "HOLD_REASON",
    "INJECTION_REASON", "report", "mark_unavailable", "assessment_for",
    "validation_error",
]


@dataclass(frozen=True)
class RiskSignal:
    """单个有界窗口的检测结果。字段即对接契约，改动需双方同步。"""

    source_kind: str
    source_ref: str
    label: int
    score: float
    model_version: str
    detector_version: str
    window_index: int = 0
    window_count: int = 1
    truncated: bool = False
    timed_out: bool = False
    uncovered_windows: int = 0
    fault: str = ""

    @property
    def incomplete(self) -> bool:
        return bool(self.fault) or self.timed_out or self.uncovered_windows > 0


@dataclass(frozen=True)
class RiskAssessment:
    signal_id: str
    label: int
    requires_hold: bool
    reason_code: str
    evidence_ref: str

    def to_dict(self) -> dict[str, object]:
        return {
            "signal_id": self.signal_id,
            "label": self.label,
            "requires_hold": self.requires_hold,
            "reason_code": self.reason_code,
            "evidence_ref": self.evidence_ref,
        }


def validation_error(signal: RiskSignal) -> str:
    """对方接入时的自检入口；返回空串表示合法。"""
    if signal.source_kind not in SOURCE_KINDS:
        return f"source_kind must be one of {sorted(SOURCE_KINDS)}"
    if signal.label not in (0, 1):
        return "label must be 0 (benign) or 1 (injection)"
    if not 0.0 <= float(signal.score) <= 1.0:
        return "score must be within [0, 1]"
    if signal.window_count < 1 or not 0 <= signal.window_index < signal.window_count:
        return "window_index / window_count out of range"
    if signal.uncovered_windows < 0:
        return "uncovered_windows must be >= 0"
    if not signal.source_ref or not signal.model_version or not signal.detector_version:
        return "source_ref / model_version / detector_version are required"
    return ""


def _write(signal_id: str, *, owner_id: str, task_id: str,
           status: EventStatus, reason_code: str,
           model_version: str, evidence_ref: str,
           allowlist_count: int = 0) -> None:
    event = GuardEvent(
        event_id=signal_id,
        owner_id=owner_id,
        module="risk-detection",
        phase="external_content",
        status=status,
        reason_code=reason_code,
        task_id=task_id,
        model_actual=model_version,
        authorization_evidence_ref=evidence_ref,
        allowlist_count=allowlist_count,
        created_at=store.utc_now(),
    )
    store.append_event({
        "event_id": signal_id,
        "owner_id": owner_id,
        "payload": event.to_public(),
        "created_at": event.created_at,
    })


def report(signal: RiskSignal, *, owner_id: str, task_id: str) -> RiskAssessment:
    """登记一个窗口的检测结果，返回该任务当前的合并风险判定。"""
    error = validation_error(signal)
    if error:
        raise ValueError(error)

    signal_id = f"grs_{uuid.uuid4().hex}"
    incomplete = signal.incomplete
    status = (
        EventStatus.FAILED if incomplete
        else (EventStatus.BLOCKED if signal.label == 1 else EventStatus.EXECUTED)
    )
    reason = (
        "DETECTOR_FAULT" if signal.fault
        else "DETECTOR_TIMEOUT" if signal.timed_out
        else "UNCOVERED_WINDOWS" if signal.uncovered_windows
        else INJECTION_REASON if signal.label == 1
        else "BENIGN_DETECTED"
    )
    _write(
        signal_id, owner_id=owner_id, task_id=task_id, status=status,
        reason_code=reason, model_version=signal.model_version,
        evidence_ref=signal.source_ref,
        allowlist_count=signal.window_count,
    )
    return assessment_for(owner_id=owner_id, task_id=task_id, signal_id=signal_id)


def mark_unavailable(*, owner_id: str, task_id: str, fault: str,
                     model_version: str = "", detector_version: str = "") -> RiskAssessment:
    """检测器加载失败/超时/被禁用时由接入方调用；敏感动作必须暂停。"""
    signal_id = f"grs_{uuid.uuid4().hex}"
    _write(
        signal_id, owner_id=owner_id, task_id=task_id,
        status=EventStatus.FAILED, reason_code="DETECTOR_UNAVAILABLE",
        model_version=model_version or detector_version,
        evidence_ref="",
    )
    return RiskAssessment(
        signal_id=signal_id, label=1, requires_hold=True,
        reason_code=HOLD_REASON, evidence_ref="",
    )


def assessment_for(*, owner_id: str, task_id: str, signal_id: str = "") -> RiskAssessment:
    """聚合该任务最近的风险事件：任一故障或未覆盖窗口即整体 hold。"""
    records = [
        item for item in store.list_events(owner_id, limit=200)
        if item.get("module") == "risk-detection" and item.get("task_id") == task_id
    ]
    if not records:
        return RiskAssessment(
            signal_id=signal_id, label=0, requires_hold=False,
            reason_code="NO_RISK_SIGNAL", evidence_ref="",
        )
    fault_codes = {
        "DETECTOR_FAULT", "DETECTOR_TIMEOUT", "UNCOVERED_WINDOWS", "DETECTOR_UNAVAILABLE",
    }
    hold = any(item.get("reason_code") in fault_codes for item in records)
    injection = any(item.get("reason_code") == INJECTION_REASON for item in records)
    latest = records[0]
    return RiskAssessment(
        signal_id=signal_id or str(latest.get("event_id", "")),
        label=1 if injection else 0,
        requires_hold=hold,
        reason_code=(
            HOLD_REASON if hold
            else INJECTION_REASON if injection
            else "NO_RISK_ACTION"
        ),
        evidence_ref=str(latest.get("authorization_evidence_ref", "")),
    )
