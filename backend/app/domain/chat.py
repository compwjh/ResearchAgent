from typing import TypedDict


class ConversationState(TypedDict, total=False):
    question: str
    answer: str
