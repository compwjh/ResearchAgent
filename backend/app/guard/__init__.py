"""Spec050 执行防护（Task03）：单动作授权与 guard-event-v1 事件。"""

from backend.app.guard.contracts import (
    ActionStatus,
    EventStatus,
    GuardDecision,
    GuardEvent,
    GuardOutcome,
    TaskScope,
)
from backend.app.guard.service import (
    authorize,
    consume,
    decide,
    events,
    guard_enabled,
    pending_actions,
    register_scope,
)

__all__ = [
    "ActionStatus",
    "EventStatus",
    "GuardDecision",
    "GuardEvent",
    "GuardOutcome",
    "TaskScope",
    "authorize",
    "consume",
    "decide",
    "events",
    "guard_enabled",
    "pending_actions",
    "register_scope",
]
