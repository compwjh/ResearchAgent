"""Spec050 执行防护公共契约（Task03）。

服务端持有的授权数据；网页、PDF、工具结果、历史记忆与模型生成文字
均不能构造或扩大这些对象。事件投影只保留白名单字段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActionStatus(str, Enum):
    PENDING = "pending"
    ALLOWED = "allowed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class GuardOutcome(str, Enum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"


class EventStatus(str, Enum):
    EXECUTED = "executed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


POLICY_VERSION = "guard-policy-v1"
STRATEGY_VERSION = "guard-strategy-v1"
EVENT_SCHEMA_VERSION = "guard-event-v1"

MUTATING_TOOLS = frozenset({"download_and_import_paper"})


@dataclass(frozen=True)
class TaskScope:
    """服务端保存的任务授权范围，不接受请求体或模型文本注入。"""

    task_id: str
    owner_id: str
    allowed_capabilities: frozenset[str] = frozenset()
    allowed_hosts: frozenset[str] = frozenset()
    scope_version: str = "scope-v1"

    def permits(self, tool_name: str) -> bool:
        return tool_name in self.allowed_capabilities


@dataclass(frozen=True)
class GuardDecision:
    outcome: GuardOutcome
    reason_code: str
    action_ref: str | None = None
    message: str = ""

    @property
    def blocking(self) -> bool:
        return self.outcome is not GuardOutcome.ALLOW


@dataclass(frozen=True)
class GuardEvent:
    """白名单投影字段；刻意不含攻击原文、凭据、隐藏推理。"""

    event_id: str
    owner_id: str
    module: str
    phase: str
    status: EventStatus
    reason_code: str = ""
    request_id: str = ""
    message_id: str = ""
    step_id: str = ""
    task_id: str = ""
    model_actual: str = ""
    policy_version: str = POLICY_VERSION
    strategy_version: str = STRATEGY_VERSION
    duration_ms: int = 0
    allowlist_count: int = 0
    authorization_evidence_ref: str = ""
    created_at: str = ""

    def to_public(self) -> dict[str, object]:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": self.event_id,
            "request_id": self.request_id,
            "message_id": self.message_id,
            "step_id": self.step_id,
            "task_id": self.task_id,
            "module": self.module,
            "phase": self.phase,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "model_actual": self.model_actual,
            "policy_version": self.policy_version,
            "strategy_version": self.strategy_version,
            "duration_ms": self.duration_ms,
            "allowlist_count": self.allowlist_count,
            "authorization_evidence_ref": self.authorization_evidence_ref,
            "created_at": self.created_at,
        }


@dataclass
class EventDraft:
    module: str = "action-guard"
    phase: str = "pre_dispatch"
    status: EventStatus = EventStatus.BLOCKED
    reason_code: str = ""
    duration_ms: int = 0
    allowlist_count: int = 0
    authorization_evidence_ref: str = ""
    context: dict[str, str] = field(default_factory=dict)
