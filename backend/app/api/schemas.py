from typing import Literal

from pydantic import BaseModel

from backend.app.core.config import MODEL_NAME


class ChatRequest(BaseModel):
    question: str
    mode: Literal["normal", "developer"] = "normal"
    model: str = MODEL_NAME


class KBAskRequest(BaseModel):
    """知识库问答请求（spec-011 / spec-012）。

    模型由用户从顶部 modelSelect 自选；`chunker` 为 spec-012 新增的切分版本
    选择，默认 `v1`，仅允许 `v1` / `v2`。
    """

    question: str
    model: str = MODEL_NAME
    top_k: int = 5
    chunker: Literal["v1", "v2"] = "v1"


class KBReindexRequest(BaseModel):
    """重建索引请求（spec-012）：不传 `chunker` 时重建全部版本。"""

    chunker: Literal["v1", "v2", "all"] = "all"
