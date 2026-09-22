"""ResearchEvent -> conversation ``processing_steps`` projection.

ResearchStore remains the source of truth for events and MemoryRepository is
the sole writer for conversation processing steps.  This module only adapts
the two existing seams and provides parent resolution/replay orchestration;
it does not introduce another event log or processing-step repository.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from backend.app.memory.models import ProcessingStep
from backend.app.memory.repository import MemoryRepository
from backend.app.research.domain.models import ResearchEvent
from backend.app.research.infrastructure.research_store import ResearchStore, canonical_research_event_id

_NODE_TYPES = {"phase", "agent", "skill", "tool", "operation"}
_TERMINAL_STATUSES = {"completed", "failed", "skipped", "interrupted"}
_STATUS_MAP = {
    "done": "completed",
    "success": "completed",
    "error": "failed",
    "cancelled": "interrupted",
    "canceled": "interrupted",
    "partial": "completed",
    "planning": "running",
    "queued": "running",
    "pending": "running",
    "waiting_approval": "running",
    "plan_pending_approval": "running",
    "intake_pending": "running",
}

# detail_json is a display projection, not an event archive.  Keep this list
# deliberately narrow so a future event producer cannot accidentally persist a
# prompt, URL, credential or model reasoning field in the conversation DB.
_SAFE_DETAIL_KEYS = {
    "code", "error_code", "event_type", "phase", "task_type", "work_item_id",
    "role", "skill_name", "tool_name", "status", "reason", "display_order",
    "model_tier", "resolved_model", "worker_slot", "source_ref", "result_id",
    "result_length", "content_hash", "selected_count", "counts", "facets",
    "reason_code", "from_provider", "to_provider", "from_model", "to_model",
}
_SENSITIVE_KEY_PARTS = {
    "prompt", "cot", "reasoning", "credential", "password", "secret",
    "token", "authorization", "cookie", "api_key", "access_key", "url",
}
_MAX_DETAIL_JSON_CHARS = 4000


def _safe_key(key: object) -> bool:
    lowered = str(key).casefold()
    return not any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _safe_detail(value: object, *, depth: int = 0) -> object:
    """Recursively retain small, JSON-safe display values only."""
    if depth > 2:
        return None
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key not in _SAFE_DETAIL_KEYS and depth == 0:
                continue
            if not _safe_key(key):
                continue
            cleaned = _safe_detail(item, depth=depth + 1)
            if cleaned is not None:
                result[str(key)[:80]] = cleaned
        return result
    if isinstance(value, list):
        return [_safe_detail(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:500] if isinstance(value, str) else value
    return None


def _safe_detail_json(value: object) -> str | None:
    cleaned = _safe_detail(value)
    if not cleaned:
        return None
    encoded = json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
    return encoded if len(encoded) <= _MAX_DETAIL_JSON_CHARS else '{"truncated":true}'


def _as_event(event: ResearchEvent | dict[str, Any]) -> ResearchEvent:
    if isinstance(event, ResearchEvent):
        return event
    if not isinstance(event, dict):
        raise ValueError("projection event must be a ResearchEvent")
    required = ("research_task_id", "event_seq", "event_type")
    if any(key not in event for key in required):
        raise ValueError("projection event is missing identity")
    payload = event.get("safe_payload_json", "{}")
    if isinstance(payload, dict):
        payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return ResearchEvent(
        str(event["research_task_id"]), int(event["event_seq"]), str(event["event_type"]),
        str(payload or "{}"), str(event.get("created_at") or ""),
    )


def _payload(event: ResearchEvent) -> dict[str, Any]:
    try:
        value = json.loads(event.safe_payload_json or "{}")
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def _status(value: object) -> str:
    normalized = str(value or "completed").strip().casefold()
    normalized = _STATUS_MAP.get(normalized, normalized)
    return normalized if normalized in {"running", *_TERMINAL_STATUSES} else "completed"


def _node_type(event_type: str, value: object) -> str:
    candidate = str(value or "").strip().casefold()
    if candidate == "work_item":
        candidate = "agent"
    if candidate in _NODE_TYPES:
        return candidate
    return {
        "task": "phase", "plan": "phase", "coverage": "phase", "report": "phase",
        "worker": "agent", "model": "skill", "terminal": "phase",
    }.get(event_type, "operation")


def _node_key(event: ResearchEvent, payload: dict[str, Any]) -> str:
    supplied = payload.get("node_key")
    if isinstance(supplied, str) and supplied.strip():
        return supplied.strip()[:240]
    event_type = event.event_type
    suffix = payload.get("work_item_id") or payload.get("phase") or payload.get("role")
    if not suffix:
        suffix = "research" if event_type in {"task", "terminal"} else event_type
    return f"{_node_type(event_type, payload.get('node_type'))}:{str(suffix)[:180]}"


class ProcessingStepProjector:
    """Project durable ResearchEvents into one assistant message's tree."""

    def __init__(self, research_store: ResearchStore, memory_repository: MemoryRepository) -> None:
        self.research_store = research_store
        self.memory_repository = memory_repository

    def project_event(
        self,
        message_id: str,
        owner_id: str,
        event: ResearchEvent | dict[str, Any],
        *,
        research_session_id: str | None = None,
    ) -> ProcessingStep:
        """Project one event; retries and canonical identity are repository-owned."""
        item = _as_event(event)
        source_event_id = canonical_research_event_id(item.research_task_id, item.event_seq)
        repository_attempted = False
        try:
            task = self.research_store.get_task(item.research_task_id, owner_id)
            message = self.memory_repository.get_message(message_id, owner_id)
            if task is None or message is None:
                raise LookupError("research task or activity message not found")
            if task.conversation_id != message.conversation_id or message.role != "assistant":
                raise PermissionError("research task and activity message are not bound")
            session = self.research_store.get_session_by_task(item.research_task_id, owner_id)
            payload = _payload(item)
            explicit_session_id = research_session_id or payload.get("research_session_id")
            # Events emitted before Task07 did not carry a session id.  Once
            # the task/session binding is verified, they may be read through
            # the broad compatibility path while new bound events remain
            # strict because their caller supplies the session explicitly.
            effective_session_id = explicit_session_id or (session.research_session_id if session is not None else None)
            if session is not None:
                if not effective_session_id or str(effective_session_id) != session.research_session_id:
                    raise PermissionError("research session binding is required")
                if session.activity_message_id != message_id:
                    raise PermissionError("target message is not the research activity message")
                if session.research_task_id not in {None, item.research_task_id}:
                    raise PermissionError("research session and task are not bound")
            elif effective_session_id:
                raise PermissionError("research session not found")

            supplied_source = payload.get("source_event_id")
            if supplied_source is not None and str(supplied_source) != source_event_id:
                raise ValueError("event source_event_id is not canonical")

            parent_step_id = payload.get("parent_step_id")
            parent_source = payload.get("parent_source_event_id")
            parent_key = payload.get("parent_node_key")
            if parent_source and parent_key:
                existing = self.memory_repository.list_processing_steps(message_id, owner_id)
                by_source = next((step for step in existing if step.source_event_id == str(parent_source)), None)
                by_key = next((step for step in existing if step.node_key == str(parent_key)), None)
                if by_source is None or by_key is None or by_source.step_id != by_key.step_id:
                    raise ValueError("parent source_event_id and node_key conflict")
                parent_step_id = by_source.step_id
            elif parent_step_id is None and (parent_source or parent_key):
                existing = self.memory_repository.list_processing_steps(message_id, owner_id)
                parent = next(
                    (
                        step for step in existing
                        if (parent_source and step.source_event_id == str(parent_source))
                        or (parent_key and step.node_key == str(parent_key))
                    ),
                    None,
                )
                if parent is None:
                    raise ValueError("processing step parent is not projected")
                parent_step_id = parent.step_id

            node_type = _node_type(item.event_type, payload.get("node_type"))
            detail_json = _safe_detail_json(payload)
            repository_attempted = True
            return self.memory_repository.project_research_event_step(
                message_id,
                owner_id,
                node_key=_node_key(item, payload),
                source_event_id=source_event_id,
                kind=str(payload.get("kind") or item.event_type)[:120],
                status=_status(payload.get("status")),
                label=str(payload.get("label") or payload.get("phase") or item.event_type)[:240],
                summary=str(payload.get("summary") or payload.get("reason") or "")[:500] or None,
                parent_step_id=str(parent_step_id) if parent_step_id else None,
                node_type=node_type,
                display_order=int(payload.get("display_order", item.event_seq) or item.event_seq),
                detail_json=detail_json,
                research_session_id=str(effective_session_id) if effective_session_id else None,
                strict_tree=bool(explicit_session_id),
            )
        except Exception as exc:
            # Parent resolution and cross-store validation happen before the
            # repository call, so explicitly use the same marker seam here.
            if not repository_attempted:
                self.memory_repository.mark_processing_projection_retry(source_event_id, message_id, str(exc))
            raise

    def project_events(
        self,
        research_task_id: str,
        message_id: str,
        owner_id: str,
        events: Iterable[ResearchEvent | dict[str, Any]] | None = None,
        *,
        research_session_id: str | None = None,
    ) -> list[ProcessingStep]:
        """Replay persisted events parent-first; failures remain retryable."""
        if events is not None:
            persisted = [_as_event(item) for item in events]
        else:
            persisted = []
            after_seq = 0
            target_seq = self.research_store.last_event_seq(research_task_id)
            while after_seq < target_seq:
                page = self.research_store.list_events(research_task_id, after_seq=after_seq, limit=1000)
                if not page:
                    break
                persisted.extend(page)
                next_seq = page[-1].event_seq
                if next_seq <= after_seq:
                    raise RuntimeError("research event pagination cursor did not advance")
                after_seq = next_seq
        steps: list[ProcessingStep] = []

        def project(item: ResearchEvent) -> ProcessingStep:
            step = self.project_event(message_id, owner_id, item, research_session_id=research_session_id)
            steps.append(step)
            return step

        # An explicit research_session_id opts into the strict Phase → Agent
        # → Skill/Tool contract.  Legacy/unbound event history (including old
        # model events) remains readable through the broad v1 path.
        self.research_store.replay_persisted_events(
            research_task_id, persisted, projector=project,
            strict_tree=bool(research_session_id),
        )
        return steps

    replay = project_events

    def drain_pending(
        self, research_task_id: str, message_id: str, owner_id: str,
        *, research_session_id: str | None = None,
    ) -> int:
        """Run one bounded retry-drain pass; callers schedule the next cycle."""
        pending = self.research_store.list_projection_retries(research_task_id, pending_only=True)
        memory_pending = self.memory_repository.list_processing_projection_retries(pending_only=True)
        if not pending and not any(row.get("message_id") == message_id for row in memory_pending):
            return 0
        # project_events performs cursor-based paging to the current tail and
        # clears both durable markers after each successful callback.  Exactly
        # one pass prevents a malformed event from causing a busy loop.
        steps = self.project_events(
            research_task_id, message_id, owner_id,
            research_session_id=research_session_id,
        )
        return len(steps)

    @staticmethod
    def as_sse_upsert(step: ProcessingStep) -> dict[str, Any]:
        """Return the incremental REST/SSE upsert envelope."""
        return {"type": "processing_step", "operation": "upsert", "step": step.to_dict()}


__all__ = ["ProcessingStepProjector"]
