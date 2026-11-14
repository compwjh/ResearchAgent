"""Spec050 执行防护（Task03）：单动作授权与 guard-event-v1 事件。"""

from backend.app.guard.contracts import (
    ActionStatus,
    EventStatus,
    GuardDecision,
    GuardEvent,
    GuardOutcome,
    TaskScope,
)
from backend.app.guard.runtime import activate, ensure_active
from backend.app.guard.service import (
    authorize,
    consume,
    decide,
    events,
    guard_enabled,
    pending_actions,
    register_scope,
)
from backend.app.guard.signals import (
    RiskAssessment,
    RiskSignal,
    assessment_for,
    mark_unavailable,
    report,
)

__all__ = [
    "ActionStatus",
    "EventStatus",
    "GuardDecision",
    "GuardEvent",
    "GuardOutcome",
    "TaskScope",
    "RiskAssessment",
    "RiskSignal",
    "assessment_for",
    "activate",
    "authorize",
    "consume",
    "decide",
    "ensure_active",
    "events",
    "guard_enabled",
    "mark_unavailable",
    "pending_actions",
    "register_scope",
    "report",
]
