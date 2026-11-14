"""服务端默认任务策略（Spec050 Task03 运行时接线）。

scope 只能由服务端构造：请求体、模型文本、网页/PDF、工具结果与历史记忆
都不能传入或扩大 owner / task / allowed_capabilities / allowed_hosts。
分发收敛点在 check 之前调用 ensure_active()，由本模块注册服务端 scope 并
绑定 ContextVar；默认关闭时不做任何注册或绑定，保持零行为变化。
"""

from __future__ import annotations

import os
from typing import Any

from backend.app.guard.contracts import MUTATING_TOOLS, TaskScope

DEFAULT_TASK_ID = "local-session"
_HOSTS_ENV = "GUARD_ALLOWED_HOSTS"


def default_owner_id() -> str:
    """单机单 owner：复用 memory.repository.OWNER_ID（延迟 import 避免硬编码不一致）。"""
    from backend.app.memory.repository import OWNER_ID

    return OWNER_ID


def default_capabilities() -> frozenset[str]:
    """敏感动作至少全量在册；只读工具由 TaskScope.allow_read_only 放行。"""
    capabilities = set(MUTATING_TOOLS)
    try:
        from backend.app.skills import tool_dispatch
    except Exception:
        # 延迟 import 失败时只保留敏感动作能力，主链路不因接线失败中断。
        return frozenset(capabilities)
    capabilities.update(tool_dispatch._ADAPTERS)
    return frozenset(capabilities)


def default_hosts() -> frozenset[str]:
    """复用项目既有的论文来源主机白名单；找不到才回退环境变量。

    空白名单意味着敏感动作仍必须用户确认，但不做主机限制，属 MVP 默认，
    后续由来源白名单收紧。敏感动作不会因空白名单被静默放行：
    service.authorize() 仍要求单动作确认。
    """
    try:
        from backend.app.api.common import _paper_candidate_hosts

        hosts = _paper_candidate_hosts({})
    except Exception:
        hosts = ()
    resolved = {str(host).strip().casefold() for host in hosts if str(host).strip()}
    if resolved:
        return frozenset(resolved)
    configured = {
        item.strip().casefold()
        for item in os.getenv(_HOSTS_ENV, "").split(",")
        if item.strip()
    }
    return frozenset(configured)


def activate(task_id: str, *, owner_id: str = "") -> tuple[Any, Any] | None:
    """幂等注册服务端 TaskScope 并绑定上下文；返回供 hooks.reset 用的 tokens。"""
    from backend.app.guard import hooks, service

    if not service.guard_enabled():
        return None
    owner = owner_id or default_owner_id()
    resolved_task = task_id or DEFAULT_TASK_ID
    existing = service.get_scope(resolved_task)
    if existing is None or existing.owner_id != owner:
        service.register_scope(TaskScope(
            task_id=resolved_task,
            owner_id=owner,
            allowed_capabilities=default_capabilities(),
            allowed_hosts=default_hosts(),
            allow_read_only=True,
        ))
    return hooks.bind(owner, resolved_task)


def ensure_active(owner_id: str = "", task_id: str = "") -> tuple[Any, Any] | None:
    """当前上下文无 task 时激活默认策略；已有显式绑定一律不覆盖、不重复 bind。"""
    from backend.app.guard import hooks, service

    if not service.guard_enabled():
        return None
    context = hooks.current()
    if context.task_id:
        return None
    resolved_owner = owner_id or context.owner_id or default_owner_id()
    return activate(task_id or DEFAULT_TASK_ID, owner_id=resolved_owner)
