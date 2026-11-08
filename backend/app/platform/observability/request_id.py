"""spec-045 Task 06：请求级统一 ID（``request_id`` / ``trace_id`` 同源）。

用 ``contextvars.ContextVar`` 在**请求入口**（沿用手工埋点，不新增全局 middleware）
生成并保存一个 ID，Langfuse trace metadata、自建 ``raw_events`` / ``research_events``
上层记录、路由决策记录共用同一值。

与 ``trace.py`` 的关系：``start_trace()`` 复用这里已绑定的 ID 作为 Langfuse trace id，
或在没有绑定时反向写入，保证 Langfuse 未启用（默认关闭）时仍有统一 ID。

SSE 注意：starlette 的 ``iterate_in_threadpool`` 每次 ``next()`` 都从父 context
``copy_context()``，实测 generator 内 ContextVar 跨 ``yield`` 会丢失。因此各链路
在跨段写入点前用 ``bind_request_id(rid)`` 按同一 ID 重新绑定（幂等，不产生新 ID）。
"""

from __future__ import annotations

import contextvars
import uuid
from contextvars import Token
from typing import Optional

# 当前请求的统一 ID（32 位小写 hex，与 Langfuse trace id 格式兼容）。
_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "obs_request_id", default=None
)
# 保存 ``ContextVar.set`` 返回的 token，供请求结束时复位。
_request_token: contextvars.ContextVar[Optional[Token]] = contextvars.ContextVar(
    "obs_request_token", default=None
)


def new_request_id() -> str:
    """生成 32 位小写 hex；不依赖 Langfuse client，观测层绝不因此抛异常。"""
    return uuid.uuid4().hex


def get_request_id() -> Optional[str]:
    """返回当前请求的统一 ID；未绑定时为 None。"""
    return _request_id.get()


def bind_request_id(request_id: Optional[str] = None) -> str:
    """绑定（或重新绑定）统一 ID，返回该 ID。

    - 无参：已绑定则返回原值，未绑定则生成新 ID（请求入口 / 写入点 lazy 兜底）。
    - 有参：按给定值绑定，用于 SSE 跨 ``yield`` 的新段重新绑定同一 ID。
    - 同段内重复绑定相同值不再 ``set``，保证 reset 用的 token 不被覆盖。
    """
    current = _request_id.get()
    if request_id:
        if current == request_id:
            return request_id
        rid = request_id
    elif current:
        return current
    else:
        rid = new_request_id()

    token = _request_id.set(rid)
    _request_token.set(token)
    return rid


def ensure_request_id() -> str:
    """写入点调用：保证一定能拿到一个稳定的 ID（同 context 内不变）。"""
    return bind_request_id()


def reset_request_id() -> None:
    """请求结束时复位；跨 context reset 或异常都不得影响业务。"""
    token = _request_token.get()
    try:
        if token is not None:
            _request_id.reset(token)
    except (ValueError, RuntimeError):
        # token 来自其它 Context（例如 SSE 跨段），忽略即可，父 context 值不受影响。
        pass
    finally:
        _request_token.set(None)
