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

import time
from typing import List, Optional

from backend.app.platform.config import OLLAMA_ROUTE
from backend.app.platform import ollama as _ollama
from backend.app.platform.ollama import ChatRun
from backend.app.platform.ollama_direct import (
    OllamaChatResult,
    OllamaTimings,
    chat_direct_stream,
)


def _langchain_drive(run: "ChatRun", model: str, prompt: str, reasoning: bool):
    """默认链路驱动器：事件产出与改动前完全一致，并在结束后合成 OllamaChatResult。

    `prompt` 是实际发给模型的文本（KB 链路传入 build_prompt 的结果，否则等于原始问题）；
    合成结果的 timings_available 恒为 False（langchain 丢弃了原生耗时字段），
    并记录首片段延迟与总墙钟供埋点使用。
    """
    chat_model = (
        _ollama.create_chat_model(model)
        if reasoning
        else _ollama.create_chat_model(model, reasoning=False)
    )
    from backend.app.chat.application.chat_graph import build_chat_graph

    graph = build_chat_graph(chat_model)
    start = time.perf_counter()
    first_token_ms = 0.0
    first_seen = False
    parts: List[str] = []
    try:
        for event in graph.stream({"question": prompt}, stream_mode="custom"):
            if not first_seen:
                first_seen = True
                first_token_ms = (time.perf_counter() - start) * 1000.0
            parts.append(event.get("content") or "")
            yield event
    finally:
        client_wall_ms = (time.perf_counter() - start) * 1000.0
        run.result = OllamaChatResult(
            content="".join(parts),
            thinking="",
            timings=OllamaTimings(),
            timings_available=False,
            first_token_ms=first_token_ms,
            client_wall_ms=client_wall_ms,
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

    text = prompt if prompt is not None else question

    if resolved == "direct":
        stream = chat_direct_stream([{"role": "user", "content": text}], model, think=think)
        run = ChatRun(route="direct")
        run.events = iter(_direct_drive(run, stream))
        return run

    run = ChatRun(route="langchain")
    run.events = iter(_langchain_drive(run, model, text, think))
    return run
