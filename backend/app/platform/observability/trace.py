"""调用级 trace 上下文（spec-013）。

让一次知识库 RAG 调用的多个阶段（embedding / retrieval / generation）
归到同一个 Langfuse trace。

机制：
- 用 `contextvars.ContextVar` 保存「当前 trace_id」（32 位小写 hex）。
- `start_trace()` 生成 trace id、写入 ContextVar，并创建一个根 observation
  （span）作为该 trace 的入口；同时把 `ContextVar.set` 返回的 token 存好。
- 之后 `spans.record_event` / `record_ollama_generation` 在创建 observation 时，
  若 `get_current_trace_id()` 非 None，就自动把 observation 挂到该 trace 上。
- `end_trace()` 用保存的 token 把 ContextVar 复位回 None。

设计原则与观测层一致：**观测永远不影响业务**。
未启用、client 不可用或任何异常，都退化为 no-op。
"""

import contextvars
import logging
from typing import List, Optional

from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability.request_id import (
    bind_request_id,
    get_request_id,
)
from backend.app.platform.observability.safe import safe_call

logger = logging.getLogger(__name__)

# 当前调用链的 trace id（32 位小写 hex）；None 表示没有活动 trace。
_current_trace_id = contextvars.ContextVar("obs_current_trace_id", default=None)

# 保存 start_trace 中 `ContextVar.set` 返回的 token，供 end_trace 复位。
_trace_token = contextvars.ContextVar("obs_trace_token", default=None)


def get_current_trace_id() -> Optional[str]:
    """返回当前 ContextVar 中的 trace id；没有活动 trace 时为 None。"""
    return _current_trace_id.get()


def bind_trace_context(request_id: Optional[str] = None) -> str:
    """跨 yield 的 ContextVar 一致性绑定（spec-045 第 07 项）。

    starlette 的 ``iterate_in_threadpool`` 每次 ``next()`` 都从父 context
    ``copy_context()``，因此 ``start_trace()`` 写入的 ``_current_trace_id`` 在
    SSE 后续段会丢失；而 ``request_id.bind_request_id(rid)`` 只重绑
    ``_request_id``。生成阶段的 ``spans._trace_context()`` 于是返回 None，
    observation 另起一条 trace —— 一次请求出现两条 trace。

    本函数按**同一个**统一 ID 把 ``_request_id`` 与 ``_current_trace_id``
    （及复位 token）一起重绑，使 retrieval / generation / phase span / score
    全部归入同一 trace。幂等：同 ID 重复绑定不覆盖已有的 reset token。

    不改变 ``bind_request_id`` 的对外语义，也不触碰采样决策；仅供**已调用
    ``start_trace`` 的链路**（kb-ask）在跨段写入点使用。chat / article /
    conversations 未开 trace，不调用本函数，观测行为完全不变。
    """
    rid = bind_request_id(request_id)
    # 未启用观测时 start_trace 是 no-op；此处也必须退化为纯 request_id 重绑，
    # 绝不凭空制造一个活动 trace（保持开关关闭态的既有行为不变）。
    if not obs_config.enabled():
        return rid
    if _current_trace_id.get() == rid:
        return rid
    token = _current_trace_id.set(rid)
    # 同 context 内不覆盖 start_trace 保存的复位 token；SSE 复制段里原 token
    # 已丢失，此处补记，保证 end_trace() 的复位语义与入口一致。
    if _trace_token.get() is None:
        _trace_token.set(token)
    return rid


def create_trace_id() -> str:
    """生成一个合法的 32 位小写 hex trace id。

    优先使用 langfuse client 的 `create_trace_id()`（保证与服务端格式一致）；
    client 不可用或其方法异常时，回退到 `uuid.uuid4().hex`（同样是 32 hex）。
    观测层绝不因此抛异常。
    """
    try:
        client = obs_client.get_client()
    except Exception as error:  # noqa: BLE001 — 观测层必须兜住一切
        logger.warning("获取 langfuse client 失败，改用 uuid 生成 trace id：%s", error)
        client = None

    if client is not None:
        try:
            trace_id = client.create_trace_id()
            if trace_id:
                return str(trace_id)
        except Exception as error:  # noqa: BLE001
            logger.warning("langfuse create_trace_id 失败，改用 uuid：%s", error)

    import uuid

    return uuid.uuid4().hex


def start_trace(
    name: str = "trace",
    *,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """开启一个 trace：生成 trace id、写入 ContextVar、并创建根 observation。

    返回 trace id 字符串。观测未启用或 client 不可用时，返回空串 `""` 且
    不写 ContextVar（no-op），绝不影响业务。
    """
    if not obs_config.enabled():
        return ""

    client = obs_client.get_client()
    if client is None:
        return ""

    # spec-045 Task 06：复用请求入口绑定的统一 ID 作为 trace id；没有入口绑定时
    # 用 create_trace_id() 生成并反向写入 request_id ContextVar，使 Langfuse
    # trace 与自建 raw_events / research_events / 路由决策记录共用同一值。
    trace_id = get_request_id() or bind_request_id(create_trace_id())
    # spec-045 Task 05：在 trace 入口做出单次采样决策并缓存到 ContextVar，
    # 使本 trace 内各阶段（record_event / record_ollama_generation / phase span）
    # 共用同一决策，避免采样不一致撕碎瀑布图。
    obs_config.decide_sampling()
    # 先把 ContextVar 指向本 trace，使 start_trace 之后创建的 observation 自动归入。
    token = _current_trace_id.set(trace_id)
    _trace_token.set(token)

    extra_meta = dict(metadata or {})
    extra_meta["request_id"] = trace_id
    if session_id is not None:
        extra_meta["session_id"] = session_id
    if tags is not None:
        extra_meta["tags"] = tags
    if user_id is not None and "user_id" not in extra_meta:
        extra_meta["user_id"] = user_id

    def _open_root() -> None:
        # 把根 observation 显式挂到本 trace；as_type=span 作为入口容器。
        # SDK 的 start_as_current_observation 返回惰性 context manager：只有进入
        # with 才会真正创建 observation，退出才会 end/flush。此前只调用不 enter，
        # name=kb-ask 的根 observation 从未落库（public API 查询 0 条）。
        with client.start_as_current_observation(
            name=name,
            as_type="span",
            trace_context={"trace_id": trace_id},
            metadata=extra_meta or None,
        ):
            pass

    safe_call(_open_root)
    return trace_id


def end_trace() -> None:
    """结束当前 trace：用保存的 token 把 ContextVar 复位回 None。

    没有活动 trace 时安全（no-op）；复位异常也不冒泡。
    """
    # spec-045 Task 05：同时复位采样决策 ContextVar（与 trace id 同源的调用级状态）。
    obs_config.reset_sample_decision()
    token = _trace_token.get()
    if token is None:
        return
    try:
        _current_trace_id.reset(token)
    except Exception:  # noqa: BLE001 — 复位失败也不冒泡
        pass
    finally:
        _trace_token.set(None)
