"""直连 Ollama /api/chat 的流式采集器（spec-013）。

langchain 的 ChatOllama 会丢弃 Ollama 返回的原生耗时字段
（load_duration / prompt_eval_duration / eval_duration），而这些字段正是
诊断「首 token 慢」的关键。本模块绕过 langchain，直接用 httpx 流式读取
NDJSON 响应，并完整采集服务端耗时、token 计数与客户端视角延迟。
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

from backend.app.chat.application.reasoning import ReasoningStreamFilter, filter_reasoning

from backend.app.platform.config import OLLAMA_BASE_URL


@dataclass(frozen=True)
class OllamaTimings:
    """Ollama 服务端返回的各阶段耗时（毫秒）与 token 计数。"""

    load_ms: float = 0.0        # 模型加载
    prompt_eval_ms: float = 0.0  # 输入预填充
    eval_ms: float = 0.0         # 逐段解码
    total_ms: float = 0.0        # 服务端总耗时
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class OllamaChatResult:
    """一次流式对话的完整结果。"""

    content: str                       # 正式输出（累积）
    thinking: str                      # 思考过程（累积，可能为空串）
    timings: OllamaTimings
    timings_available: bool            # 响应里是否真的带回了耗时字段
    first_token_ms: float             # 客户端视角：发起请求到首个内容片段
    client_wall_ms: float            # 客户端墙钟总耗时
    chunk_intervals_ms: Tuple[float, ...] = field(default_factory=tuple)  # 相邻内容片段间隔
    tool_calls: Tuple[dict, ...] = ()  # function calling 结果（已合并增量），每项 {"name": str, "arguments": dict}
    interrupted: bool = False  # provider stream ended abnormally after partial output
    completed_normally: bool = False  # provider emitted an explicit final done marker


def _ms(nanoseconds: float) -> float:
    """纳秒 -> 毫秒（Ollama 耗时字段单位为纳秒）。"""
    return nanoseconds / 1_000_000.0


def _stream_chunks(
    messages: List[Dict[str, str]],
    model: str,
    timeout: float,
    think: bool | str = True,
    options: Optional[dict] = None,
    tools: Optional[List[dict]] = None,
    reasoning_effort: Optional[str] = None,
):
    """流式核心：逐块产出事件，结束时产出 OllamaChatResult。

    产出序列形如：若干 {"type": "token"/"thinking", "content": str} 事件，
    最后一定是一个 OllamaChatResult（含完整 timings 与客户端延迟）。
    thinking 与 content 分开累积；连接失败且尚未收到任何内容时抛 RuntimeError；
    流中途断开则保留已收内容并将结果标记为 interrupted。这是 chat_direct 与
    chat_direct_stream 的共同内核，调用方不得把部分流视为 completed。

    ``tools``：Ollama function-calling schema（Task07）。传入时启用原生工具调用，
    并在结束时把增量 ``tool_calls`` 合并为 ``{"name": str, "arguments": dict}`` 列表。
    """
    # trust_env=False 必须：否则 httpx 会读取 macOS 系统代理，把指向
    # localhost:11434 的请求截走并返回 503（见 ollama.py 注释）。
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload: Dict[str, object] = {
        "model": model,
        "messages": messages,
        "stream": True,
        # 思考模型（如 qwen3.5）默认会先吐出大量思考内容，首个"正式" token 要等思考结束，
        # 实测一次简单问答的思考就达 30+ 秒，会把 load/prefill 的差异完全淹没
        # （冷启动 4000ms vs 热调用 10ms 在 36 秒思考面前看不出来）。
        # 做受控耗时采样时必须能关掉。项目里已有先例：config.py 中 v2 切分模型即要求 think:false。
        "think": (
            False if reasoning_effort == "off"
            else True if reasoning_effort == "xhigh"
            else reasoning_effort
        ) if reasoning_effort is not None else think,
    }
    if options is not None:
        payload["options"] = options
    if tools is not None:
        payload["tools"] = tools

    start = time.perf_counter()
    first_token_at: Optional[float] = None
    last_chunk_at: Optional[float] = None
    intervals: List[float] = []
    content_parts: List[str] = []
    thinking_parts: List[str] = []
    thinking_filter = ReasoningStreamFilter()
    # tool_calls 增量合并：按 index 聚合 name 与 arguments（dict 增量合并）
    tool_calls_by_index: Dict[int, dict] = {}

    # 耗时字段只在最后一行出现，取最后看到的值
    load_ms = prompt_eval_ms = eval_ms = total_ms = 0.0
    prompt_tokens = completion_tokens = 0
    timings_available = False
    interrupted = False
    completed_normally = False

    duration_keys = ("load_duration", "prompt_eval_duration", "eval_duration", "total_duration")

    try:
        with httpx.stream("POST", url, json=payload, timeout=timeout, trust_env=False) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Ollama /api/chat 失败（HTTP {response.status_code}）")

            for raw in response.iter_lines():
                line = (raw or "").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message = event.get("message") or {}
                thinking = message.get("thinking")
                if thinking:
                    clean = thinking_filter.push(thinking)
                    if clean:
                        thinking_parts.append(clean)
                        # Keep the historical ``thinking`` type for direct
                        # callers; the conversation stream maps it to the
                        # public ``reasoning_delta`` event.
                        yield {"type": "thinking", "content": clean}

                chunk = message.get("content")
                if chunk:
                    now = time.perf_counter()
                    if first_token_at is None:
                        first_token_at = now
                    if last_chunk_at is not None:
                        intervals.append((now - last_chunk_at) * 1000.0)
                    last_chunk_at = now
                    content_parts.append(chunk)
                    yield {"type": "token", "content": chunk}

                # —— function calling：增量合并 tool_calls（Task07）——
                tc_raw = message.get("tool_calls")
                if tc_raw:
                    for tc in tc_raw:
                        if not isinstance(tc, dict):
                            continue
                        idx = tc.get("index", 0)
                        fn = tc.get("function") or {}
                        name = fn.get("name")
                        arguments = fn.get("arguments") or {}
                        slot = tool_calls_by_index.setdefault(
                            idx, {"name": name, "arguments": {}}
                        )
                        if name is not None:
                            slot["name"] = name
                        if isinstance(arguments, dict):
                            slot["arguments"].update(arguments)
                        elif isinstance(arguments, str) and not slot["arguments"]:
                            # 极少数情况下 arguments 以 JSON 字符串出现：尽力解析
                            try:
                                parsed = json.loads(arguments)
                                if isinstance(parsed, dict):
                                    slot["arguments"] = parsed
                            except json.JSONDecodeError:
                                pass

                if event.get("done"):
                    completed_normally = True
                if event.get("done") and any(key in event for key in duration_keys):
                    load_ms = _ms(event.get("load_duration", 0.0))
                    prompt_eval_ms = _ms(event.get("prompt_eval_duration", 0.0))
                    eval_ms = _ms(event.get("eval_duration", 0.0))
                    total_ms = _ms(event.get("total_duration", 0.0))
                    prompt_tokens = int(event.get("prompt_eval_count", 0))
                    completion_tokens = int(event.get("eval_count", 0))
                    timings_available = True
    except httpx.HTTPError as error:
        # 连接失败（尚未收到任何内容）仍是普通模型失败；中途断开必须
        # 显式标记为 interrupted，让会话层持久化中止终态而非 completed。
        if not content_parts and not thinking_parts and not tool_calls_by_index:
            raise RuntimeError(f"无法连接 Ollama：{error}") from error
        interrupted = True

    tail = thinking_filter.finish()
    if tail:
        thinking_parts.append(tail)
        yield {"type": "thinking", "content": tail}
    end = time.perf_counter()
    timings = OllamaTimings(
        load_ms=load_ms,
        prompt_eval_ms=prompt_eval_ms,
        eval_ms=eval_ms,
        total_ms=total_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    first_token_ms = (first_token_at - start) * 1000.0 if first_token_at is not None else 0.0
    client_wall_ms = (end - start) * 1000.0

    yield OllamaChatResult(
        content="".join(content_parts),
        thinking=filter_reasoning(thinking_parts)[0],
        timings=timings,
        timings_available=timings_available,
        first_token_ms=first_token_ms,
        client_wall_ms=client_wall_ms,
        chunk_intervals_ms=tuple(intervals),
        tool_calls=tuple(tool_calls_by_index.values()),
        interrupted=interrupted,
        completed_normally=completed_normally,
    )


def chat_direct(
    messages: List[Dict[str, str]],
    model: str,
    *,
    timeout: float = 300.0,
    think: bool | str = True,
    options: Optional[dict] = None,
    tools: Optional[List[dict]] = None,
    reasoning_effort: Optional[str] = None,
) -> OllamaChatResult:
    """直连 Ollama /api/chat 做流式调用，并采集原生耗时。

    复用 _stream_chunks 内核：消费完整流并返回最终的 OllamaChatResult。
    连接失败或 HTTP 非 2xx 时抛 RuntimeError；流中途断开时返回已收到的部分内容。

    `think=False` 可关闭思考模型的思维链输出（受控耗时采样用，详见 _stream_chunks 注释）。
    `options` 透传给 Ollama（如 ``{"temperature": 0.0}``），默认 None 不改动请求体。
    `tools` 为 function-calling schema（Task07），默认 None 不启用工具调用。
    """
    result: Optional[OllamaChatResult] = None
    for item in _stream_chunks(messages, model, timeout, think, options, tools, reasoning_effort):
        result = item  # 内核最后一定 yield 的正是 OllamaChatResult
    assert result is not None
    return result


class ChatDirectStream:
    """可迭代封装：逐块 yield token/thinking 事件，结束后暴露 .result。

    使用方式：
        stream = chat_direct_stream(messages, model)
        for event in stream:          # 每个 event 为 {"type": "token"/"thinking", "content": str}
            ...
        result = stream.result        # 迭代结束后为 OllamaChatResult，字段与 chat_direct 一致
    """

    def __init__(
        self,
        messages: List[Dict[str, str]],
        model: str,
        timeout: float = 300.0,
        think: bool | str = True,
        options: Optional[dict] = None,
        tools: Optional[List[dict]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        self._messages = messages
        self._model = model
        self._timeout = timeout
        self._think = think
        self._options = options
        self._tools = tools
        self._reasoning_effort = reasoning_effort
        self.result: Optional[OllamaChatResult] = None
        self._exhausted = False

    def __iter__(self):
        for item in _stream_chunks(
            self._messages, self._model, self._timeout, self._think, self._options, self._tools, self._reasoning_effort
        ):
            if isinstance(item, OllamaChatResult):
                self.result = item
                self._exhausted = True
                continue
            yield item
        if not self._exhausted:
            # 内核因异常提前结束、未产出结果时，补一个空结果，保证 .result 恒有值。
            self.result = OllamaChatResult(
                content="",
                thinking="",
                timings=OllamaTimings(),
                timings_available=False,
                first_token_ms=0.0,
                client_wall_ms=0.0,
                tool_calls=(),
                interrupted=True,
                completed_normally=False,
            )


def chat_direct_stream(
    messages: List[Dict[str, str]],
    model: str,
    *,
    timeout: float = 300.0,
    think: bool | str = True,
    options: Optional[dict] = None,
    tools: Optional[List[dict]] = None,
    reasoning_effort: Optional[str] = None,
) -> ChatDirectStream:
    """返回一个可迭代封装：逐块产出 token/thinking 事件，迭代结束后可读 .result。

    .result 为 OllamaChatResult，字段与 chat_direct 返回完全一致，供埋点使用。
    连接失败且尚未收到任何内容时，异常在首次迭代时抛出（沿用现有策略）。

    `think=False` 可关闭思考模型的思维链输出（受控耗时采样用）。
    `options` 透传给 Ollama（如 ``{"temperature": 0.0}``），默认 None 不改动请求体。
    `tools` 为 function-calling schema（Task07），默认 None 不启用工具调用。
    """
    return ChatDirectStream(messages, model, timeout, think, options, tools, reasoning_effort)
