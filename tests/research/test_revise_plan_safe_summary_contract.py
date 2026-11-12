"""revise_plan writes back safe_summary (degraded strategy) from command scope.

Regression contract for the research plan field display task: the existing
``command=revise_plan`` path must accept a new ``safe_summary`` dict, persist
it on the new plan version, keep every other plan field intact, and preserve
the previous behaviour when the field is absent or is not a dict.
"""

from __future__ import annotations

import json

import pytest

from backend.app.research.application.approval_service import (
    PlanApprovalService,
    ResearchCommandError,
)
from tests.research.test_research_plan_approval_contract import OWNER, _output, _setup


def _plan(store, session, version):
    return store.get_session_plan(session.research_session_id, OWNER, version)


def _fields(plan):
    return {
        "objective": plan.objective,
        "scope": json.loads(plan.scope_json),
        "work_items": json.loads(plan.work_items_json),
        "capabilities": json.loads(plan.capabilities_json),
        "budget": json.loads(plan.budget_json),
        "report_structure": json.loads(plan.report_structure_json),
    }


def test_revise_plan_persists_safe_summary_from_scope(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    old = _plan(store, session, 1)
    assert json.loads(old.safety_summary_json) == {"decision": "bounded"}
    old_fields = _fields(old)

    new_summary = {
        "decision": "降级为仅目录检索",
        "notes": "外部来源不可用时改用已缓存目录",
        "constraints": ["不访问外部网络"],
        "degraded": ["在线检索"],
    }
    try:
        service.command(
            session.research_session_id,
            OWNER,
            command="revise_plan",
            subject_version=1,
            scope_json={"safe_summary": new_summary},
            idempotency_key="revise-safe-summary",
        )
    except ResearchCommandError as exc:
        pytest.fail(f"revise_plan with safe_summary must not be rejected: {exc.code} / {exc.message}")

    assert store.get_session(session.research_session_id, OWNER).current_plan_version == 2
    new = _plan(store, session, 2)
    assert new is not None
    assert json.loads(new.safety_summary_json) == new_summary
    assert _fields(new) == old_fields


def test_revise_plan_without_safe_summary_keeps_old_value(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    old = _plan(store, session, 1)

    service.command(
        session.research_session_id,
        OWNER,
        command="revise_plan",
        subject_version=1,
        scope_json={"objective": "修订后的研究目标"},
        idempotency_key="revise-without-safe-summary",
    )

    new = _plan(store, session, 2)
    assert new is not None
    assert json.loads(new.safety_summary_json) == json.loads(old.safety_summary_json) == {"decision": "bounded"}
    assert new.objective == "修订后的研究目标"


def test_revise_plan_ignores_non_dict_safe_summary(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    old = _plan(store, session, 1)

    service.command(
        session.research_session_id,
        OWNER,
        command="revise_plan",
        subject_version=1,
        scope_json={"safe_summary": "不是对象"},
        idempotency_key="revise-non-dict-safe-summary",
    )

    new = _plan(store, session, 2)
    assert new is not None
    assert json.loads(new.safety_summary_json) == json.loads(old.safety_summary_json)
