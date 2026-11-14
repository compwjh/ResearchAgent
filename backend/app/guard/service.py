"""单动作授权状态机与 guard-event-v1 事件服务（Task03）。

状态：pending -> allowed / rejected / expired -> consumed。
硬规则：拒绝越权目标；只读工具放行；有副作用的工具须显式确认。
确认只使用一次，参数变化、取消、重复确认、已消费均不得触发新执行。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from typing import Any, Mapping
from urllib.parse import urlparse

from backend.app.guard import store
from backend.app.guard.contracts import (
    MUTATING_TOOLS,
    ActionStatus,
    EventDraft,
    EventStatus,
    GuardDecision,
    GuardEvent,
    GuardOutcome,
    TaskScope,
)

_ENABLED_ENV = "GUARD_ACTION_AUTHORIZATION_ENABLED"
_lock = threading.RLock()
_scopes: dict[str, TaskScope] = {}


def guard_enabled() -> bool:
    """默认关闭。Spec050：通过验收后单独决定启用。"""
    return os.getenv(_ENABLED_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}


def set_guard_enabled(enabled: bool) -> None:
    os.environ[_ENABLED_ENV] = "true" if enabled else "false"


def register_scope(scope: TaskScope) -> None:
    with _lock:
        _scopes[scope.task_id] = scope


def get_scope(task_id: str) -> TaskScope | None:
    with _lock:
        return _scopes.get(task_id)


def clear_scopes() -> None:
    with _lock:
        _scopes.clear()


_VOLATILE_KEYS = frozenset({"request_id", "timestamp", "ts", "nonce", "trace_id"})


def normalize_args(args: Mapping[str, Any]) -> dict[str, Any]:
    """规范化参数：去掉易变字段、递归排序，保证同一动作哈希稳定。"""
    def _clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(k): _clean(v)
                for k, v in sorted(value.items(), key=lambda item: str(item[0]))
                if str(k).casefold() not in _VOLATILE_KEYS
            }
        if isinstance(value, (list, tuple)):
            return [_clean(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    cleaned = _clean(args)
    return cleaned if isinstance(cleaned, dict) else {}


def args_hash(normalized: Mapping[str, Any]) -> str:
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def target_summary(tool_name: str, args: Mapping[str, Any]) -> str:
    """只暴露目标摘要，不内联攻击原文或完整 URL。"""
    candidate = args.get("candidate")
    if isinstance(candidate, Mapping):
        url = candidate.get("pdf_url") or candidate.get("article_url") or ""
        host = urlparse(str(url)).hostname or ""
        title = str(candidate.get("title") or "")[:120]
        return f"{tool_name}:{host}:{title}" if host else f"{tool_name}:{title}"
    source = args.get("source_id") or args.get("query") or ""
    return f"{tool_name}:{str(source)[:120]}"


def target_hosts(args: Mapping[str, Any]) -> set[str]:
    hosts: set[str] = set()
    candidate = args.get("candidate")
    if isinstance(candidate, Mapping):
        for key in ("pdf_url", "article_url", "url"):
            value = candidate.get(key)
            if isinstance(value, str) and value:
                host = urlparse(value).hostname
                if host:
                    hosts.add(host.casefold())
    return hosts


def _host_allowed(host: str, allowed_hosts: frozenset[str]) -> bool:
    """精确匹配或子域匹配；`evil-usenix.org` 不得借后缀放行。"""
    for allowed in allowed_hosts:
        candidate = allowed.casefold().lstrip(".")
        if host == candidate or host.endswith("." + candidate):
            return True
    return False


def _emit(draft: EventDraft, *, owner_id: str) -> GuardEvent:
    event = GuardEvent(
        event_id=f"gev_{uuid.uuid4().hex}",
        owner_id=owner_id,
        module=draft.module,
        phase=draft.phase,
        status=draft.status,
        reason_code=draft.reason_code,
        request_id=draft.context.get("request_id", ""),
        message_id=draft.context.get("message_id", ""),
        step_id=draft.context.get("step_id", ""),
        task_id=draft.context.get("task_id", ""),
        model_actual=draft.context.get("model_actual", ""),
        duration_ms=draft.duration_ms,
        allowlist_count=draft.allowlist_count,
        authorization_evidence_ref=draft.authorization_evidence_ref,
        created_at=store.utc_now(),
    )
    store.append_event({
        "event_id": event.event_id,
        "owner_id": owner_id,
        "payload": event.to_public(),
        "created_at": event.created_at,
    })
    return event


def _context(task_id: str, **extra: str) -> dict[str, str]:
    base = {"task_id": task_id}
    base.update({k: v for k, v in extra.items() if v})
    return base


def authorize(
    tool_name: str,
    args: Mapping[str, Any],
    *,
    owner_id: str,
    task_id: str,
) -> GuardDecision:
    """执行前校验。返回 REQUIRE_CONFIRMATION 时调用方**不得**执行动作。"""
    if not guard_enabled():
        return GuardDecision(GuardOutcome.ALLOW, "GUARD_DISABLED")

    normalized = normalize_args(args)
    digest = args_hash(normalized)
    scope = get_scope(task_id)

    # 硬规则 1：未注册的任务范围不放行任何有副作用的动作。
    if scope is None or scope.owner_id != owner_id:
        _emit(EventDraft(
            status=EventStatus.BLOCKED, reason_code="SCOPE_MISSING",
            context=_context(task_id),
        ), owner_id=owner_id)
        return GuardDecision(GuardOutcome.DENY, "SCOPE_MISSING", message="任务授权范围不存在或不属于当前用户")

    if not scope.permits(tool_name):
        _emit(EventDraft(
            status=EventStatus.BLOCKED, reason_code="CAPABILITY_NOT_ALLOWED",
            context=_context(task_id),
        ), owner_id=owner_id)
        return GuardDecision(GuardOutcome.DENY, "CAPABILITY_NOT_ALLOWED", message="该工具不在本次任务允许能力内")

    # 硬规则 2：目标主机必须在服务端白名单内。
    hosts = target_hosts(args)
    if hosts and scope.allowed_hosts:
        unknown = {h for h in hosts if not _host_allowed(h, scope.allowed_hosts)}
        if unknown:
            _emit(EventDraft(
                status=EventStatus.BLOCKED, reason_code="TARGET_NOT_ALLOWED",
                context=_context(task_id), allowlist_count=len(scope.allowed_hosts),
            ), owner_id=owner_id)
            return GuardDecision(GuardOutcome.DENY, "TARGET_NOT_ALLOWED", message="目标不在服务端允许范围")

    if tool_name not in MUTATING_TOOLS:
        _emit(EventDraft(
            status=EventStatus.EXECUTED, reason_code="READ_ONLY_ALLOWED",
            context=_context(task_id), allowlist_count=len(scope.allowed_hosts),
        ), owner_id=owner_id)
        return GuardDecision(GuardOutcome.ALLOW, "READ_ONLY_ALLOWED")

    # 风险信号只影响「必须核验的敏感动作」的可用性，不授予或替代授权。
    # 检测器故障/超时/未覆盖窗口时暂停敏感动作，不静默放行。
    from backend.app.guard import signals as _signals

    assessment = _signals.assessment_for(owner_id=owner_id, task_id=task_id)
    if assessment.requires_hold:
        _emit(EventDraft(
            status=EventStatus.BLOCKED, reason_code=_signals.HOLD_REASON,
            context=_context(task_id), authorization_evidence_ref=assessment.signal_id,
        ), owner_id=owner_id)
        return GuardDecision(
            GuardOutcome.DENY, _signals.HOLD_REASON,
            message="注入检测不可用，必须核验的动作已暂停；请重试或稍后再试",
        )

    # 只复用仍活跃的授权；终态（拒绝/取消/已消费/失效）后允许重新发起确认，
    # 否则用户在一次拒绝后无法按提示重试同一动作。
    with _lock:
        for status, outcome, reason in (
            (ActionStatus.ALLOWED.value, GuardOutcome.ALLOW, "ACTION_ALLOWED"),
            (ActionStatus.PENDING.value, GuardOutcome.REQUIRE_CONFIRMATION, "CONFIRMATION_REQUIRED"),
        ):
            for row in store.list_actions(owner_id, status=status):
                if row["task_id"] == task_id and row["tool_name"] == tool_name and row["args_hash"] == digest:
                    if outcome is GuardOutcome.ALLOW:
                        return GuardDecision(outcome, reason, action_ref=row["action_ref"])
                    action_ref = row["action_ref"]
                    _emit(EventDraft(
                        status=EventStatus.BLOCKED, reason_code=reason,
                        context=_context(task_id), authorization_evidence_ref=action_ref,
                    ), owner_id=owner_id)
                    return GuardDecision(
                        outcome, reason, action_ref=action_ref,
                        message="该动作需要用户确认具体目标与范围",
                    )

        # 新建一次性待确认记录；幂等键绑定本次 action_ref，终态后可重新发起。
        action_ref = f"gact_{uuid.uuid4().hex}"
        store.create_action({
            "action_ref": action_ref,
            "owner_id": owner_id,
            "task_id": task_id,
            "tool_name": tool_name,
            "normalized_args": normalized,
            "args_hash": digest,
            "target_summary": target_summary(tool_name, normalized),
            "status": ActionStatus.PENDING.value,
            "scope_version": scope.scope_version,
            "idempotency_key": f"{task_id}:{tool_name}:{digest}:{action_ref}",
            "created_at": store.utc_now(),
        })
    _emit(EventDraft(
        status=EventStatus.BLOCKED, reason_code="CONFIRMATION_REQUIRED",
        context=_context(task_id), authorization_evidence_ref=action_ref,
    ), owner_id=owner_id)
    return GuardDecision(
        GuardOutcome.REQUIRE_CONFIRMATION, "CONFIRMATION_REQUIRED",
        action_ref=action_ref, message="该动作需要用户确认具体目标与范围",
    )


def decide(action_ref: str, *, owner_id: str, choice: str, expected_args_hash: str) -> GuardDecision:
    """用户确认或拒绝；参数变化、取消、重复决策、已消费均失效。"""
    record = store.get_action(action_ref)
    if record is None or record["owner_id"] != owner_id:
        return GuardDecision(GuardOutcome.DENY, "ACTION_NOT_FOUND")
    if record["status"] != ActionStatus.PENDING.value:
        return GuardDecision(GuardOutcome.DENY, "ACTION_NOT_PENDING", action_ref=action_ref)
    if expected_args_hash and record["args_hash"] != expected_args_hash:
        store.update_action_status(action_ref, ActionStatus.EXPIRED.value, column="decided_at")
        _emit(EventDraft(
            phase="confirmation", status=EventStatus.SKIPPED, reason_code="ARGS_CHANGED",
            context=_context(record["task_id"]), authorization_evidence_ref=action_ref,
        ), owner_id=owner_id)
        return GuardDecision(GuardOutcome.DENY, "ARGS_CHANGED", action_ref=action_ref)

    if choice not in {"allow", "reject", "cancel"}:
        return GuardDecision(GuardOutcome.DENY, "INVALID_CHOICE", action_ref=action_ref)

    if choice == "allow":
        new_status, outcome, reason = ActionStatus.ALLOWED, GuardOutcome.ALLOW, "ACTION_ALLOWED"
    elif choice == "reject":
        new_status, outcome, reason = ActionStatus.REJECTED, GuardOutcome.DENY, "ACTION_REJECTED"
    else:
        new_status, outcome, reason = ActionStatus.EXPIRED, GuardOutcome.DENY, "ACTION_CANCELLED"

    # CAS：只有仍处于 pending 的记录能被转换，防并发重复确认。
    if not _transition(action_ref, new_status.value):
        return GuardDecision(GuardOutcome.DENY, "ACTION_ALREADY_DECIDED", action_ref=action_ref)

    _emit(EventDraft(
        phase="confirmation",
        status=EventStatus.EXECUTED if choice == "allow" else EventStatus.SKIPPED,
        reason_code=reason, context=_context(record["task_id"]),
        authorization_evidence_ref=action_ref,
    ), owner_id=owner_id)
    return GuardDecision(outcome, reason, action_ref=action_ref)


def _transition(action_ref: str, status: str) -> bool:
    with _lock:
        current = store.get_action(action_ref)
        if current is None or current["status"] != ActionStatus.PENDING.value:
            return False
        return store.update_action_status(action_ref, status, column="decided_at")


def consume(action_ref: str, *, owner_id: str, succeeded: bool, result_unknown: bool = False) -> GuardDecision:
    """执行完毕后消费一次性授权；结果未知时不得重放已成功的副作用。"""
    with _lock:
        record = store.get_action(action_ref)
        if record is None or record["owner_id"] != owner_id:
            return GuardDecision(GuardOutcome.DENY, "ACTION_NOT_FOUND")
        if record["status"] != ActionStatus.ALLOWED.value:
            return GuardDecision(GuardOutcome.DENY, "ACTION_NOT_ALLOWED_OR_CONSUMED", action_ref=action_ref)
        store.update_action_status(action_ref, ActionStatus.CONSUMED.value, column="consumed_at")
    status = EventStatus.FAILED if result_unknown or not succeeded else EventStatus.EXECUTED
    reason = "RESULT_UNKNOWN" if result_unknown else ("EXECUTION_FAILED" if not succeeded else "ACTION_CONSUMED")
    _emit(EventDraft(
        phase="post_dispatch", status=status, reason_code=reason,
        context=_context(record["task_id"]), authorization_evidence_ref=action_ref,
    ), owner_id=owner_id)
    return GuardDecision(GuardOutcome.ALLOW, reason, action_ref=action_ref)


def pending_actions(owner_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """确认 UI 用的最小投影，不含原始参数；附风险信号供用户判断。"""
    from backend.app.guard import signals as _signals

    assessments: dict[str, Any] = {}
    result = []
    for row in store.list_actions(owner_id, status=ActionStatus.PENDING.value, limit=limit):
        task_id = row["task_id"]
        if task_id not in assessments:
            assessments[task_id] = _signals.assessment_for(owner_id=owner_id, task_id=task_id)
        risk = assessments[task_id]
        result.append({
            "action_ref": row["action_ref"],
            "task_id": task_id,
            "tool_name": row["tool_name"],
            "target_summary": row["target_summary"],
            "args_hash": row["args_hash"],
            "status": row["status"],
            "scope_version": row["scope_version"],
            "created_at": row["created_at"],
            "risk": {
                "label": risk.label,
                "reason_code": risk.reason_code,
                "requires_hold": risk.requires_hold,
                "evidence_ref": risk.evidence_ref,
            },
        })
    return result


def events(owner_id: str, *, limit: int = 50) -> dict[str, Any]:
    return {"schema_version": "guard-event-v1", "records": store.list_events(owner_id, limit=limit)}
