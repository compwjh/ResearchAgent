"""Task06 regression: expose the durable evaluation selection through events."""

import json

from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.domain.models import ResearchWorkItem
from backend.app.research.infrastructure.research_store import _safe_event_payload


def _item() -> ResearchWorkItem:
    return ResearchWorkItem(
        work_item_id="evaluate-1",
        research_task_id="task-1",
        plan_version=1,
        task_type="evaluate_papers",
        role="paper-evaluator",
        depends_on_json="[]",
        input_json="{}",
        status="completed",
        attempt=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:01Z",
    )


def test_evaluation_completion_event_exposes_selected_ids_only():
    payload = Orchestrator._worker_event_payload(
        _item(),
        "completed",
        selected_count=2,
        selected_paper_ids=["paper-a", "paper-b"],
        title="must not be persisted",
        abstract="must not be persisted",
        reasoning="must not be persisted",
    )

    safe = _safe_event_payload(payload)

    assert safe["selected_count"] == 2
    assert safe["selected_paper_ids"] == ["paper-a", "paper-b"]
    assert "title" not in safe
    assert "abstract" not in safe
    assert "reasoning" not in safe
    # Keep the assertion explicit: this event is a reference bridge to the
    # existing selection snapshot, not a second metadata/evaluation store.
    assert json.dumps(safe, ensure_ascii=False).find("must not be persisted") == -1
