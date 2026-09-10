"""Ollama 模型接入（Spec017）：模型枚举与会话模型创建。

本模块位于 `platform` 跨业务适配层，**禁止 import 业务模块**（静态边界规则，
Task07 会用 AST 静态检查强制）。因此这里只保留与业务无关的 Ollama 能力：

- `get_available_models()`：枚举本地可用模型；
- `create_chat_model()`：创建 LangChain 的 ChatOllama 会话模型；
- `ChatRun`：一次聊天的执行句柄（数据结构）。

需要驱动 LangGraph 会话图的 `run_chat` 已下沉到聊天上下文
`backend.app.chat.application.chat_runner`，因为 `graphs.chat` 属业务模块，
留在 platform 会构成反向依赖。
"""

from dataclasses import dataclass
from typing import Iterator, List, Optional

import httpx
from langchain_ollama import ChatOllama

from backend.app.platform.config import OLLAMA_BASE_URL
from backend.app.platform.ollama_direct import OllamaChatResult


def get_available_models() -> List[str]:
    response = httpx.get(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags",
        timeout=5,
        trust_env=False,
    )
    response.raise_for_status()
    return [item["name"] for item in response.json().get("models", [])]


def create_chat_model(model_name: str, *, reasoning: Optional[bool] = None) -> ChatOllama:
    """创建本地 Ollama 会话模型。

    `trust_env=False` 是必须的：httpx 默认会读取 macOS 系统代理配置，
    把指向 localhost:11434 的请求也送去代理，代理返回 503，表现为「无法连接 Ollama」。

    `reasoning` 默认 **None（不下发开关）**，保持改动前行为：ChatOllama 会把该参数
    映射为请求体的 `think` 字段（langchain_ollama 中 `"think": kwargs.pop("reasoning",
    self.reasoning)`）。对不支持 thinking 的模型（如 `deepseek-coder-v2:16b`），下发
    `think: true` 会让 Ollama 返回 HTTP 400 `does not support thinking`；对思考模型
    （如 `qwen3.5:9b`）则会强制开启思维链、拖长响应。因此只有显式传入 True/False 时
    才下发该开关——KB 问答经 `run_chat(..., think=False)` 显式关闭思维链。
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
