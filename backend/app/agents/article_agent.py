import json
import re
from typing import Tuple, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.domain.article import ArticleTask

# 强下载触发词：命中则直接判为 download_paper，跳过模型调用（性能优化）。
STRONG_DOWNLOAD_WORDS = (
    "下载论文", "下载文章", "下载这篇", "下载该", "获取论文", "获取文章",
    "download paper", "download the paper", "download this paper",
)
# 意图分类所用模型（轻量、快速）；不可用时回退 chat。
INTENT_MODEL = "qwen3.5:9b"

INTENT_PROMPT = (
    "你是意图分类器。只输出一个 JSON 对象，不要输出多余文字。\n"
    '格式：{"intent": "download_paper" 或 "chat", "confidence": 0到1之间的数字}\n'
    "规则：普通问答、创作、解释、闲聊、写代码、写文案、写故事等默认归为 chat；"
    "仅当用户明确要下载或获取某篇论文（例如提供了论文标题并要求下载/获取）时才归为 download_paper。"
)


class IntentState(TypedDict, total=False):
    query: str
    normalized_query: str
    intent: str
    confidence: float


def normalize_query(query: str) -> str:
    normalized = re.sub(r"[\t\r\n ]+", " ", query.strip())
    normalized = re.sub(r"[，,]+", ",", normalized)
    normalized = re.sub(r"[。]+$", "", normalized)
    return normalized


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _classify_with_llm(normalized_query: str) -> Tuple[str, float]:
    from backend.app.services.ollama import create_chat_model

    try:
        response = create_chat_model(INTENT_MODEL).invoke(
            INTENT_PROMPT + f"\n用户请求：{normalized_query}"
        )
        data = _extract_json(getattr(response, "content", "") or "")
        intent = data.get("intent")
        confidence = data.get("confidence")
        if intent == "download_paper":
            return "download_paper", float(confidence if isinstance(confidence, (int, float)) else 0.9)
        if intent == "chat":
            return "chat", float(confidence if isinstance(confidence, (int, float)) else 0.9)
    except Exception:
        pass
    # 兜底：无法判断时一律归为普通问答，不返回 unsupported。
    return "chat", 0.5


def classify_intent(normalized_query: str) -> Tuple[str, float]:
    lowered = normalized_query.lower()
    if any(word in lowered for word in STRONG_DOWNLOAD_WORDS):
        return "download_paper", 0.96
    return _classify_with_llm(normalized_query)


def build_intent_graph():
    def normalize_node(state: IntentState) -> IntentState:
        return {"normalized_query": normalize_query(state["query"])}

    def intent_node(state: IntentState) -> IntentState:
        intent, confidence = classify_intent(state["normalized_query"])
        return {"intent": intent, "confidence": confidence}

    graph = StateGraph(IntentState)
    graph.add_node("normalize_question", normalize_node)
    graph.add_node("identify_intent", intent_node)
    graph.add_edge(START, "normalize_question")
    graph.add_edge("normalize_question", "identify_intent")
    graph.add_edge("identify_intent", END)
    return graph.compile()


def build_task(task_id: str, query: str) -> ArticleTask:
    result = build_intent_graph().invoke({"query": query})
    return ArticleTask(
        task_id=task_id,
        query=query,
        normalized_query=result["normalized_query"],
        intent=result["intent"],
        intent_confidence=result["confidence"],
        status="searching" if result["intent"] == "download_paper" else "completed",
    )
