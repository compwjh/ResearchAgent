from typing import Literal

from pydantic import BaseModel

from backend.app.core.config import MODEL_NAME


class ChatRequest(BaseModel):
    question: str
    mode: Literal["normal", "developer"] = "normal"
    model: str = MODEL_NAME
