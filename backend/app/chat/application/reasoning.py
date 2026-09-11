"""Shared reasoning extraction, filtering and SSE sequencing primitives."""

from __future__ import annotations

import json
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

REASONING_EFFORTS = ("off", "low", "medium", "high", "xhigh")
MAX_REASONING_CODEPOINTS = 20_000
_TEMPLATE_MARKERS = (
    "<|assistant|>", "<|user|>", "<|system|>", "<|tool|>",
    "<|endoftext|>", "<|im_start|>", "<|im_end|>", "<|eot_id|>",
)
_TERMINAL = {"completed", "failed", "interrupted"}


def filter_reasoning(chunks: Iterable[object], limit: int = MAX_REASONING_CODEPOINTS) -> tuple[str, bool]:
    """Normalize and sanitize reasoning chunks before exposing or persisting them."""
    raw = unicodedata.normalize("NFC", "".join(str(chunk or "") for chunk in chunks))
    for marker in _TEMPLATE_MARKERS:
        raw = raw.replace(marker, "")
    raw = "".join(char for char in raw if char in "\n\t" or unicodedata.category(char) != "Cc")
    limit = max(0, int(limit))
    if len(raw) <= limit:
        return raw, False
    marker = "[…中间思考已省略…]"
    if limit <= len(marker):
        return marker[:limit], True
    head = (limit - len(marker)) // 2
    tail = limit - len(marker) - head
    return raw[:head] + marker + raw[-tail:], True


def filter_reasoning_delta(value: object) -> str:
    """Filter one delta without allowing protocol/control text through."""
    return filter_reasoning([value], limit=MAX_REASONING_CODEPOINTS)[0]


class ReasoningStreamFilter:
    """Streaming sanitizer that holds marker prefixes across provider chunks."""

    def __init__(self) -> None:
        self._carry = ""

    def push(self, value: object) -> str:
        raw = self._carry + str(value or "")
        self._carry = ""
        for marker in _TEMPLATE_MARKERS:
            for size in range(min(len(marker) - 1, len(raw)), 0, -1):
                if raw.endswith(marker[:size]):
                    self._carry = raw[-size:]
                    raw = raw[:-size]
                    break
            if self._carry:
                break
        return filter_reasoning([raw])[0]

    def finish(self) -> str:
        carry, self._carry = self._carry, ""
        return filter_reasoning([carry])[0]


def filter_reasoning_chunks(chunks: Iterable[object], limit: int = MAX_REASONING_CODEPOINTS) -> tuple[str, bool]:
    stream = ReasoningStreamFilter()
    emitted = [stream.push(chunk) for chunk in chunks]
    emitted.append(stream.finish())
    return filter_reasoning(emitted, limit=limit)


def extract_reasoning(chunk: object) -> str:
    """Read provider/LangChain reasoning fields without exposing raw payloads."""
    if chunk is None:
        return ""
    if isinstance(chunk, dict):
        additional = chunk.get("additional_kwargs") or {}
        return filter_reasoning_delta(
            chunk.get("reasoning_content")
            or chunk.get("thinking")
            or additional.get("reasoning_content")
            or additional.get("thinking")
            or (chunk.get("message") or {}).get("thinking")
        )
    additional = getattr(chunk, "additional_kwargs", {}) or {}
    return filter_reasoning_delta(
        getattr(chunk, "reasoning_content", None)
        or getattr(chunk, "thinking", None)
        or additional.get("reasoning_content")
        or additional.get("thinking")
    )


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class EventSequencer:
    """Single-assistant-message event sequencer with terminal-state guard."""

    message_id: str
    event_seq: int = 0
    status: str = "created"

    def accept(self, event: dict) -> bool:
        """Accept an adapter-provided envelope only when it is contiguous."""
        if self.status in _TERMINAL:
            return False
        seq = event.get("event_seq")
        if seq is None:
            return True
        seq = int(seq)
        if seq <= self.event_seq:
            return False
        if seq != self.event_seq + 1:
            raise ValueError("EVENT_SEQUENCE_GAP")
        self.event_seq = seq
        return True

    def emit(self, event_type: str, **payload: object) -> str:
        if self.status in _TERMINAL:
            return ""
        self.event_seq += 1
        if event_type == "done":
            self.status = str(payload.get("status") or "completed")
        elif event_type == "error":
            # Error is not itself terminal; done follows it in the contract.
            self.status = self.status if self.status not in {"created"} else "answering"
        elif event_type == "reasoning_started":
            self.status = "reasoning_running"
        elif event_type == "reasoning_completed":
            self.status = "reasoning_completed"
        elif event_type == "token":
            self.status = "answering"
        envelope = {
            "type": event_type,
            "message_id": self.message_id,
            "event_seq": self.event_seq,
            "timestamp": utc_timestamp(),
            **payload,
        }
        return f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n"


def monotonic_ms(start: Optional[float]) -> Optional[float]:
    return None if start is None else max(0.0, (time.monotonic() - start) * 1000.0)
