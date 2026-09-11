from typing import Dict, List, TypedDict


class ConversationState(TypedDict, total=False):
    messages: List[Dict[str, str]]
    answer: str
