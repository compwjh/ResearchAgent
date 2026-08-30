from typing import List

import httpx
from langchain_ollama import ChatOllama

from backend.app.core.config import OLLAMA_BASE_URL


def get_available_models() -> List[str]:
    response = httpx.get(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags",
        timeout=5,
        trust_env=False,
    )
    response.raise_for_status()
    return [item["name"] for item in response.json().get("models", [])]


def create_chat_model(model_name: str) -> ChatOllama:
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
    )
