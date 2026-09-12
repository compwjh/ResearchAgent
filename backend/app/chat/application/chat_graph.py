from langchain_ollama import ChatOllama
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from backend.app.chat.domain.chat import ConversationState
from backend.app.chat.application.reasoning import ReasoningStreamFilter, extract_reasoning


def build_chat_graph(model: ChatOllama):
    def ask_model(state: ConversationState) -> ConversationState:
        writer = get_stream_writer()
        answer_parts = []
        reasoning_filter = ReasoningStreamFilter()
        payload = state.get("messages", [])
        for chunk in model.stream(payload):
            reasoning = reasoning_filter.push(extract_reasoning(chunk))
            if reasoning:
                writer({"type": "thinking", "content": reasoning})
            content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
            if not content:
                continue
            answer_parts.append(content)
            writer({"type": "token", "content": content})
        tail = reasoning_filter.finish()
        if tail:
            writer({"type": "thinking", "content": tail})
        return {"answer": "".join(answer_parts)}

    graph = StateGraph(ConversationState)
    graph.add_node("ask_model", ask_model)
    graph.add_edge(START, "ask_model")
    graph.add_edge("ask_model", END)
    return graph.compile()
