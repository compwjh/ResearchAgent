"""分发收敛点的执行前/执行后挂钩（Task03）。

供 `tool_dispatch` / `agent_runtime` / `worker_tool` 复用。
默认关闭时 `check()` 直接返回 None，对既有链路零行为变化。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Mapping

from backend.app.guard.contracts import GuardDecision, GuardOutcome

_current_owner: ContextVar[str] = ContextVar("guard_owner_id", default="")
_current_task: ContextVar[str] = ContextVar("guard_task_id", default="")

DEFAULT_OWNER_ID = "local-user"


@dataclass(frozen=True)
class GuardContext:
    owner_id: str
    task_id: str


def bind(owner_id: str, task_id: str) -> tuple[Any, Any]:
    """绑定服务端上下文；返回 token 供调用方在 finally 中 reset。"""
    return (
        _current_owner.set(owner_id or DEFAULT_OWNER_ID),
        _current_task.set(task_id or ""),
    )


def reset(tokens: tuple[Any, Any]) -> None:
    _current_owner.reset(tokens[0])
    _current_task.reset(tokens[1])


def current() -> GuardContext:
    return GuardContext(owner_id=_current_owner.get(), task_id=_current_task.get())


def check(tool_name: str, args: Mapping[str, Any]) -> GuardDecision | None:
    """返回 None 表示无需防护（默认关闭）；否则返回决策供调用方判定。"""
    from backend.app.guard import service

    if not service.guard_enabled():
        return None
    context = current()
    return service.authorize(
        tool_name, args,
        owner_id=context.owner_id or DEFAULT_OWNER_ID,
        task_id=context.task_id,
    )


def blocking_message(decision: GuardDecision) -> str:
    if decision.outcome is GuardOutcome.REQUIRE_CONFIRMATION:
        return f"需要确认该动作（{decision.reason_code}）：{decision.message}；确认后请重试。"
    return f"动作被阻止（{decision.reason_code}）：{decision.message}"


def record_outcome(decision: GuardDecision | None, *, succeeded: bool, result_unknown: bool = False) -> None:
    """执行完毕后消费一次性授权；失败/结果未知不记为成功防御。"""
    if decision is None or decision.action_ref is None:
        return
    from backend.app.guard import service

    service.consume(
        decision.action_ref,
        owner_id=current().owner_id or DEFAULT_OWNER_ID,
        succeeded=succeeded,
        result_unknown=result_unknown,
    )
