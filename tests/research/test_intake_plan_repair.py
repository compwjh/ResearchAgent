"""Focused regression tests for automatic plan generation after Intake."""

import json

from backend.app.memory.repository import MemoryRepository
from backend.app.platform.config import BASE_DIR
from backend.app.research.application.plan_authoring import validate_research_plan_output
from backend.app.research.application.session_plan_generation import (
    _target_count,
    build_session_plan_output,
    ensure_session_plan,
    extract_paper_count_constraints,
    resolve_paper_count_constraints,
)
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.service import SkillRegistryService
from backend.app.skills.tool_service import ToolRegistryService


def _completed_session(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    conversation, user, _ = memory.create_conversation_messages(
        "local-user", "深度研究", None, "m", "normal"
    )
    session = ResearchSession(
        "session-1", "local-user", conversation.conversation_id,
        user.message_id, "draft-1", "intake_pending",
    )
    store.create_session(session, memory_repository=memory)
    values = {
        "topic": "agent security",
        "objective": "总结 agent security",
        "time_range": {"from": 2020, "to": 2024},
        "language": "zh",
        "sources": ["usenix"],
        "depth": "balanced",
        "constraints": ["target_paper_count: 5"],
    }
    for field_name, value in values.items():
        store.upsert_intake_field(
            IntakeField(
                "draft-1", field_name, json.dumps(value, ensure_ascii=False),
                "user_explicit", 1.0, "confirmed", "", user.message_id,
            ),
            "local-user",
        )
    store.update_intake_status("draft-1", "local-user", "complete")
    return store, session


def test_completed_intake_builds_valid_first_plan(tmp_path):
    store, session = _completed_session(tmp_path)
    output = build_session_plan_output(store, session, "local-user")
    normalized = validate_research_plan_output(output, expected_version=1)
    assert normalized["plan_version"] == 1
    assert normalized["budget"]["target_paper_count"] == 5
    assert len(normalized["work_items"]) >= 1


def test_plan_generation_is_idempotent_and_replays_existing_plan(tmp_path):
    store, session = _completed_session(tmp_path)
    calls = []

    def author(session_id, owner_id, output):
        calls.append(output["output_hash"])
        from backend.app.research.application.approval_service import PlanApprovalService

        service = PlanApprovalService(
            store=store,
            skill_registry=SkillRegistryService(BASE_DIR / ".agents" / "skills", tmp_path / "skill-state.json"),
            tool_registry=ToolRegistryService(build_default_tool_registry(), tmp_path / "skill-state.json"),
        )
        return service.author_plan(session_id, owner_id, output)

    first = ensure_session_plan(store, session, "local-user", author)
    second = ensure_session_plan(store, session, "local-user", author)
    assert first["status"] == "plan_pending_approval"
    assert second["subject_version"] == 1
    assert len(calls) == 1


def test_paper_count_constraints_keep_maximum_and_target_within_plan_budget():
    assert _target_count(["max_paper_count:5", "target_paper_count:5"]) == 5


def test_minimum_paper_count_is_not_treated_as_an_upper_bound():
    assert _target_count([]) == 12
    assert _target_count(["至少使用官方来源"]) == 12
    assert _target_count(["min_paper_count:5"]) == 12
    assert _target_count(["min_paper_count:15"]) == 15


def test_conflicting_paper_count_constraints_require_clarification():
    import pytest

    with pytest.raises(ValueError, match="paper count constraints"):
        _target_count(["max_paper_count:5", "min_paper_count:8"])


def test_oversized_paper_count_is_unparsed_instead_of_raising_or_defaulting():
    oversized = "9" * 5000

    extracted = extract_paper_count_constraints(f"最多{oversized}篇论文")
    assert extracted == ["paper_count_constraint:unparsed"]

    resolved = resolve_paper_count_constraints([f"max_paper_count:{oversized}"])
    assert resolved["valid"] is False
    assert resolved["reason"] == "paper count constraint is not parseable"


def test_maximum_only_constraints_cap_the_default_budget():
    assert _target_count(["max_paper_count:20"]) == 12
    assert _target_count(["max_paper_count:20", "min_paper_count:5"]) == 12
    assert _target_count(["max_paper_count:5"]) == 5
