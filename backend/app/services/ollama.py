import time
from dataclasses import dataclass
from typing import Iterator, List, Optional

import httpx
from langchain_ollama import ChatOllama

from backend.app.core.config import OLLAMA_BASE_URL, OLLAMA_ROUTE
from backend.app.services.ollama_direct import OllamaChatResult, OllamaTimings, chat_direct_stream


def get_available_models() -> List[str]:
    response = httpx.get(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags",
        timeout=5,
        trust_env=False,
    )
    response.raise_for_status()
    return [item["name"] for item in response.json().get("models", [])]


def create_chat_model(model_name: str, *, reasoning: bool = True) -> ChatOllama:
    """创建本地 Ollama 会话模型。

    `trust_env=False` 是必须的：httpx 默认会读取 macOS 系统代理配置，
    把指向 localhost:11434 的请求也送去代理，代理返回 503，表现为「无法连接 Ollama」。
    """
    return ChatOllama(
        model=model_name,
        base_url=OLLAMA_BASE_URL,
        client_kwargs={"trust_env": False},
        async_client_kwargs={"trust_env": False},
        sync_client_kwargs={"trust_env": False},
        reasoning=reasoning,
    )


@dataclass
class ChatRun:
    """一次聊天的执行句柄。

    route：实际使用的链路（"langchain" | "direct"）；
    events：可迭代，产出 {"type": "token"|"thinking", "content": str}；
    result：迭代结束（或失败）后可用的 OllamaChatResult。
    """

    route: str
    events: "Iterator[dict]" = None
    result: Optional[OllamaChatResult] = None

    def __iter__(self) -> "Iterator[dict]":
        return iter(self.events)

    def __next__(self) -> dict:
        return next(self.events)


def _langchain_drive(run: "ChatRun", model: str, prompt: str, reasoning: bool):
    """默认链路驱动器：事件产出与改动前完全一致，并在结束后合成 OllamaChatResult。

    `prompt` 是实际发给模型的文本（KB 链路传入 build_prompt 的结果，否则等于原始问题）；
    合成结果的 timings_available 恒为 False（langchain 丢弃了原生耗时字段），
    并记录首片段延迟与总墙钟供埋点使用。
     """
    # create_chat_model 是本模块全局函数，直接引用即可：
    # 测试 patch `backend.app.services.ollama.create_chat_model` 才能生效。
    # 切勿改成 `import backend.app.api.routes as routes` 再从 routes 上取函数 ——
    # 那会形成 services→api→services 的运行时循环依赖，并把 patch 点转移到 routes
    # 命名空间，导致单测的 mock 全部失效、意外打到真实模型（曾让 9 个单测耗时 42 秒）。
    from backend.app.graphs.chat import build_chat_graph

    chat_model = create_chat_model(model) if reasoning else create_chat_model(model, reasoning=False)
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
    ChatOllama 未暴露该开关）。受控耗时采样需要它：思考时间会淹没 load/prefill 差异。
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
