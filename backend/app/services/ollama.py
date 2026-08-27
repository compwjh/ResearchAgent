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
    return ChatOllama(model=model_name, base_url=OLLAMA_BASE_URL)
