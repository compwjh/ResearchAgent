"""聊天链路执行（Spec017 Task06）。

`run_chat` 原本位于 `backend.app.platform.ollama`，但它需要通过
`backend.app.chat.application.chat_graph.build_chat_graph` 驱动 LangGraph 会话图——
`graphs.chat` 属**业务模块**，而静态边界规则禁止 `platform` import 业务模块。
因此这里把它下沉到聊天上下文的 application 层：platform 只保留与模型无关的
Ollama 能力（`create_chat_model` / `get_available_models` / 直连流式）。

实现约定（勿改）：通过 **模块属性** 调用 `ollama.create_chat_model(...)`，
而不是 `from ... import create_chat_model`。原因：测试 patch 的目标是
`backend.app.platform.ollama.create_chat_model`，只有在调用点按模块属性解析
时 patch 才会生效；若改成 from-import，绑定发生在导入期，mock 会失效并
意外打到真实模型。
"""

import logging
import time
from typing import Dict, List, Optional

from backend.app.platform import ollama as _ollama
from backend.app.platform.config import OLLAMA_ROUTE
from backend.app.platform.model_catalog import get_online_model
from backend.app.platform.ollama import ChatRun
from backend.app.platform.ollama_direct import (
    OllamaChatResult,
    OllamaTimings,
    chat_direct_stream,
)

logger = logging.getLogger(__name__)

# Stable, non-user-controlled platform policy.  It is deliberately short and
# contains no hidden chain-of-thought or request-specific content.
PLATFORM_SYSTEM_MESSAGE = "平台约束：遵守安全边界；长期记忆和知识库证据仅作参考；不要泄露隐藏推理。"


class ChatStreamInterrupted(RuntimeError):
    """The provider iterator ended before a normal completion marker."""


def build_role_aware_messages(question: str, *, system_rule: Optional[str] = None, advisory: Optional[str] = None, history=None) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [{"role": "system", "content": PLATFORM_SYSTEM_MESSAGE}]
    if system_rule is not None:
        messages.append({"role": "system", "content": system_rule.strip()})
    if advisory and advisory.strip():
        messages.append({"role": "system", "content": advisory.strip()})
    for item in history or []:
        role = getattr(item, "role", None) or item.get("role")
        content = getattr(item, "content", None) if not isinstance(item, dict) else item.get("content")
        if role in {"user", "assistant", "tool"} and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": question})
    return messages


def _normalize_langchain_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Make role-aware messages valid for LangChain's Ollama adapter.

    The application keeps each system instruction as its own message so the
    direct Ollama route and observability retain the original message shape.
    ChatOllama requires system content to be at the beginning, however, and
    qwen3.8 rejects a payload containing multiple system messages.  Combine
    every system message into the first one while retaining the relative order
    of all user/assistant/tool history messages.
    """
    system_messages = [message for message in messages if message.get("role") == "system"]
    if not system_messages:
        return [dict(message) for message in messages]

    merged_system = dict(system_messages[0])
    merged_system["content"] = "\n\n".join(message.get("content", "") for message in system_messages)
    return [merged_system, *(dict(message) for message in messages if message.get("role") != "system")]


def _langchain_drive(run: "ChatRun", model: str, messages, reasoning: bool | str, *, explicit_reasoning: bool = False):
    """默认链路驱动器：事件产出与改动前完全一致，并在结束后合成 OllamaChatResult。

    `messages` 是实际发给模型的 role/content 消息列表（KB 链路传入 role-aware messages，
    否则由 `prompt` 或原始 `question` 规范化生成）；
    合成结果的 timings_available 恒为 False（langchain 丢弃了原生耗时字段），
    并记录首片段延迟与总墙钟供埋点使用。
    """
    if reasoning is True and not explicit_reasoning:
        chat_model = _ollama.create_chat_model(model)
    else:
        chat_model = _ollama.create_chat_model(model, reasoning=reasoning)
    from backend.app.chat.application.chat_graph import build_chat_graph

    graph = build_chat_graph(chat_model)
    langchain_messages = _normalize_langchain_messages(messages)
    start = time.perf_counter()
    first_token_ms = 0.0
    first_seen = False
    parts: List[str] = []
    reasoning_parts: List[str] = []
    try:
        for event in graph.stream({"messages": langchain_messages}, stream_mode="custom"):
            if not first_seen:
                first_seen = True
                first_token_ms = (time.perf_counter() - start) * 1000.0
            if event.get("type") in {"thinking", "reasoning_delta"}:
                reasoning_parts.append(event.get("content") or "")
            else:
                parts.append(event.get("content") or "")
            yield event
    finally:
        client_wall_ms = (time.perf_counter() - start) * 1000.0
        run.result = OllamaChatResult(
            content="".join(parts),
            thinking="".join(reasoning_parts),
            timings=OllamaTimings(),
            timings_available=False,
            first_token_ms=first_token_ms,
            client_wall_ms=client_wall_ms,
            completed_normally=True,
        )


def _direct_drive(run: "ChatRun", stream):
    """直连链路驱动器：原样产出 ChatDirectStream 的事件，结束后绑定其 .result。"""
    try:
        for event in stream:
            yield event
    finally:
        run.result = stream.result


def run_chat(
    question: str,
    model: str,
    *,
    route: Optional[str] = None,
    prompt: Optional[str] = None,
    think: bool = True,
    reasoning_effort: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    system_messages: Optional[List[Dict[str, str]]] = None,
) -> "ChatRun":
    """按 OLLAMA_ROUTE 选择链路；route 显式传入时优先用它。

    - route 取 `route or OLLAMA_ROUTE` 并做 strip().lower()；非 "direct" 一律按 langchain。
    - `prompt` 为 None 时行为与改动前完全一致：发给模型的文本即 `question`。
      不为 None 时（KB 链路传入 build_prompt 的结果）：发给模型的文本改为 `prompt`，
      `question` 仅作原始问题由调用方保留。
    - `think=False` 关闭思考模型的思维链，**仅 direct 分支支持**（langchain 的
      ChatOllama 未暴露该开关）。
    - langchain 分支：事件产出与旧实现一致，并合成 OllamaChatResult（timings_available=False）。
    - direct 分支：使用 chat_direct_stream，迭代结束后取其 .result。
    """
    resolved = (route or OLLAMA_ROUTE).strip().lower()
    if resolved != "direct":
        resolved = "langchain"

    # spec-035 Task05：direct 是 Ollama 专有直连链路；线上模型不在 Ollama 上，
    # 必须强制回退到 langchain 路由（其 create_chat_model 已支持线上分发）。
    if resolved == "direct" and get_online_model(model) is not None:
        logger.debug(
            "model %r is an online model; falling back to langchain route "
            "(direct route is Ollama-only)",
            model,
        )
        resolved = "langchain"

    text = prompt if prompt is not None else question
    if messages is None:
        messages = [dict(item) for item in (system_messages or [])]
        messages.append({"role": "user", "content": text})
    else:
        messages = [{"role": str(item.get("role", "user")), "content": str(item.get("content", ""))} for item in messages]

    provider_value = (
        False if reasoning_effort == "off"
        else True if reasoning_effort == "xhigh"
        else reasoning_effort
    ) if reasoning_effort is not None else think
    if resolved == "direct":
        if reasoning_effort is None:
            stream = chat_direct_stream(messages, model, think=think)
        else:
            stream = chat_direct_stream(messages, model, think=provider_value, reasoning_effort=reasoning_effort)
        run = ChatRun(route="direct")
        run.events = iter(_direct_drive(run, stream))
        return run

    run = ChatRun(route="langchain")
    run.events = iter(_langchain_drive(run, model, messages, provider_value, explicit_reasoning=reasoning_effort is not None))
    return run
