"""Research Task / WorkItem 状态机（纯 Python，无 IO）。

转移校验顺序：先确认 state / nxt 均在合法状态集合内（不在则同样抛
InvalidStateTransition，未知状态不得静默放行），再查转移表。
"""

from __future__ import annotations

from .contracts import (
    TASK_STATUSES,
    TASK_TERMINAL,
    TASK_TRANSITIONS,
    WORKITEM_STATUSES,
    WORKITEM_TERMINAL,
    WORKITEM_TRANSITIONS,
)


class InvalidStateTransition(Exception):
    """非法状态转移异常；code 固定为 INVALID_STATE_TRANSITION。"""

    def __init__(self, code: str, frm: str, to: str):
        self.code = code
        self.frm = frm
        self.to = to
        super().__init__(f"{code}: {frm} -> {to}")


def transition_task(state: str, nxt: str) -> str:
    """校验 ResearchTask 状态转移；非法（含未知状态）抛 InvalidStateTransition。"""
    if state not in TASK_STATUSES or nxt not in TASK_STATUSES:
        raise InvalidStateTransition("INVALID_STATE_TRANSITION", state, nxt)
    if nxt not in TASK_TRANSITIONS.get(state, set()):
        raise InvalidStateTransition("INVALID_STATE_TRANSITION", state, nxt)
    return nxt


def transition_workitem(state: str, nxt: str) -> str:
    """校验 ResearchWorkItem 状态转移；非法（含未知状态）抛 InvalidStateTransition。"""
    if state not in WORKITEM_STATUSES or nxt not in WORKITEM_STATUSES:
        raise InvalidStateTransition("INVALID_STATE_TRANSITION", state, nxt)
    if nxt not in WORKITEM_TRANSITIONS.get(state, set()):
        raise InvalidStateTransition("INVALID_STATE_TRANSITION", state, nxt)
    return nxt


def is_task_terminal(state: str) -> bool:
    """ResearchTask 是否已处于终态。"""
    return state in TASK_TERMINAL


def is_workitem_terminal(state: str) -> bool:
    """ResearchWorkItem 是否已处于终态。"""
    return state in WORKITEM_TERMINAL


def can_transition_task(state: str, nxt: str) -> bool:
    """不抛异常地判断 ResearchTask 转移是否合法。"""
    if state not in TASK_STATUSES or nxt not in TASK_STATUSES:
        return False
    return nxt in TASK_TRANSITIONS.get(state, set())


def can_transition_workitem(state: str, nxt: str) -> bool:
    """不抛异常地判断 ResearchWorkItem 转移是否合法。"""
    if state not in WORKITEM_STATUSES or nxt not in WORKITEM_STATUSES:
        return False
    return nxt in WORKITEM_TRANSITIONS.get(state, set())
