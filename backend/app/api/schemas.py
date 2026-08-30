from typing import Literal

from pydantic import BaseModel

from backend.app.core.config import MODEL_NAME


class ChatRequest(BaseModel):
    question: str
    mode: Literal["normal", "developer"] = "normal"
    model: str = MODEL_NAME


class KBAskRequest(BaseModel):
    """知识库问答请求（spec-011）：模型由用户从顶部 modelSelect 自选。"""

    question: str
    model: str = MODEL_NAME
    top_k: int = 5
