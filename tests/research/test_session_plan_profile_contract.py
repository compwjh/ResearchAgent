"""契约测试：``build_session_plan_output`` 消费 4 个 Intake profile（契约 2.6）。

锁定：
- capabilities / budget / report_structure / safe_summary 四块随用户选择变化，
  不再是硬编码默认值；
- 老会话无新字段时逐字回落到原有硬编码默认值，计划结果不变；
- 任何组合生成的 payload 都能通过 ``validate_research_plan_output`` 护栏
  （不引入更深嵌套、URL 字符串或键名为 url 的字符串值）。
"""
from __future__ import annotations

import json

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.plan_authoring import (
    validate_research_plan_output,
)
from backend.app.research.application.session_plan_generation import (
    build_session_plan_output,
)
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import ResearchStore

OWNER = "local-user"
BASE_FIELDS = {
    "topic": "agent security",
    "objective": "总结 agent security",
    "time_range": {"from": 2020, "to": 2024},
    "language": "zh",
    "sources": ["usenix"],
    "depth": "balanced",
    "output": "markdown",
    "citations": "inline",
    "constraints": ["target_paper_count:5"],
}
LEGACY_DECISION = "已根据确认的 Intake 生成首版计划，等待用户批准"
LEGACY_NOTES = "首版计划使用确定性 Planner；批准后才会创建 ResearchTask 并执行搜索。"
LEGACY_SECTIONS = ["研究问题", "方法与来源", "主要发现", "局限与后续工作"]


def _build(tmp_path, overrides=None):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    conversation, user, _ = memory.create_conversation_messages(
        OWNER, "深度研究", None, "m", "normal"
    )
    session = ResearchSession(
        "session-1", OWNER, conversation.conversation_id,
        user.message_id, "draft-1", "intake_pending",
    )
    store.create_session(session, memory_repository=memory)
    values = {**BASE_FIELDS, **(overrides or {})}
    for field_name, value in values.items():
        store.upsert_intake_field(
            IntakeField(
                "draft-1", field_name, json.dumps(value, ensure_ascii=False),
                "user_explicit", 1.0, "confirmed", "", user.message_id,
            ),
            OWNER,
        )
    store.update_intake_status("draft-1", OWNER, "complete")
    return store, session


# ---------------------------------------------------------------------------
# 老会话回落：计划结果逐字不变
# ---------------------------------------------------------------------------
class TestLegacyFallback:
    def test_legacy_session_without_profiles_keeps_original_hardcoded_defaults(self, tmp_path):
        store, session = _build(tmp_path)
        output = build_session_plan_output(store, session, OWNER)
        assert len(output["capabilities"]) == 4
        assert output["capabilities"][0]["skill"] == "usenix-catalog-orchestration"
        assert output["budget"] == {
            "quality_profile": "balanced",
            "target_paper_count": 5,
            "soft_budget_seconds": 1500,
            "language": "zh",
        }
        assert output["report_structure"] == {
            "sections": LEGACY_SECTIONS,
            "format": "markdown",
            "citations": "inline",
            "language": "zh",
            "title": "深度研究报告",
        }
        assert output["safe_summary"]["decision"] == LEGACY_DECISION
        assert output["safe_summary"]["notes"] == LEGACY_NOTES
        assert output["safe_summary"]["degraded"] == []
        validate_research_plan_output(output, expected_version=1)


# ---------------------------------------------------------------------------
# 4 块随用户选择变化（验收点 7）
# ---------------------------------------------------------------------------
class TestProfileDrivenPlan:
    def test_capability_profile_selects_capability_subset(self, tmp_path):
        store, session = _build(tmp_path, {"capability_profile": "catalog_only"})
        output = build_session_plan_output(store, session, OWNER)
        assert output["capabilities"] != [
            {"skill": "usenix-catalog-orchestration", "tools": ["search_paper_catalog", "fetch_paper_detail"]},
            {"skill": "research-paper-evaluation", "tools": []},
            {"skill": "research-coverage-review", "tools": []},
            {"skill": "research-report-synthesis", "tools": []},
        ]
        assert len(output["capabilities"]) == 1
        assert output["capabilities"][0]["skill"] == "usenix-catalog-orchestration"
        validate_research_plan_output(output, expected_version=1)

    def test_search_eval_capability_profile_keeps_evaluation(self, tmp_path):
        store, session = _build(tmp_path, {"capability_profile": "search_eval"})
        output = build_session_plan_output(store, session, OWNER)
        skills = [item["skill"] for item in output["capabilities"]]
        assert "research-paper-evaluation" in skills
        assert "research-coverage-review" not in skills
        validate_research_plan_output(output, expected_version=1)

    def test_budget_profile_and_depth_and_constraints_drive_budget(self, tmp_path):
        store, session = _build(tmp_path, {
            "budget_profile": "deep",
            "depth": "quality",
            "constraints": ["target_paper_count:10"],
        })
        output = build_session_plan_output(store, session, OWNER)
        budget = output["budget"]
        assert budget["soft_budget_seconds"] == 3600
        assert budget["soft_budget_seconds"] != 1500
        assert budget["quality_profile"] == "quality"
        assert budget["target_paper_count"] == 10
        assert output["scope"]["constraints"] == ["target_paper_count:10"]
        validate_research_plan_output(output, expected_version=1)

    def test_fast_budget_profile_shortens_budget(self, tmp_path):
        store, session = _build(tmp_path, {"budget_profile": "fast", "depth": "speed"})
        output = build_session_plan_output(store, session, OWNER)
        assert output["budget"]["soft_budget_seconds"] == 600
        assert output["budget"]["quality_profile"] == "speed"
        validate_research_plan_output(output, expected_version=1)

    def test_report_profile_and_output_citations_drive_report_structure(self, tmp_path):
        store, session = _build(tmp_path, {
            "report_profile": "brief",
            "output": "html",
            "citations": "footnotes",
        })
        output = build_session_plan_output(store, session, OWNER)
        report = output["report_structure"]
        assert report["sections"] != LEGACY_SECTIONS
        assert len(report["sections"]) < len(LEGACY_SECTIONS)
        assert report["format"] == "html"
        assert report["citations"] == "footnotes"
        validate_research_plan_output(output, expected_version=1)

    def test_deep_report_profile_expands_sections(self, tmp_path):
        store, session = _build(tmp_path, {"report_profile": "deep"})
        output = build_session_plan_output(store, session, OWNER)
        assert len(output["report_structure"]["sections"]) > len(LEGACY_SECTIONS)
        validate_research_plan_output(output, expected_version=1)

    def test_degradation_policy_drives_safe_summary(self, tmp_path):
        store, session = _build(tmp_path, {"degradation_policy": "conservative"})
        output = build_session_plan_output(store, session, OWNER)
        assert output["safe_summary"]["decision"] != LEGACY_DECISION
        assert output["safe_summary"]["notes"] != LEGACY_NOTES
        assert "保守" in output["safe_summary"]["decision"]
        validate_research_plan_output(output, expected_version=1)

    def test_flexible_degradation_policy_is_distinct(self, tmp_path):
        store, session = _build(tmp_path, {"degradation_policy": "flexible"})
        output = build_session_plan_output(store, session, OWNER)
        assert "弹性" in output["safe_summary"]["decision"]
        validate_research_plan_output(output, expected_version=1)

    def test_all_four_profiles_together_are_reflected(self, tmp_path):
        store, session = _build(tmp_path, {
            "capability_profile": "catalog_only",
            "budget_profile": "deep",
            "report_profile": "brief",
            "degradation_policy": "conservative",
        })
        output = build_session_plan_output(store, session, OWNER)
        assert len(output["capabilities"]) == 1
        assert output["budget"]["soft_budget_seconds"] == 3600
        assert len(output["report_structure"]["sections"]) < len(LEGACY_SECTIONS)
        assert "保守" in output["safe_summary"]["decision"]
        validate_research_plan_output(output, expected_version=1)


# ---------------------------------------------------------------------------
# 护栏：未知 / 恶意 profile 值回落，不破坏 plan 校验
# ---------------------------------------------------------------------------
class TestGuardrails:
    @pytest.mark.parametrize("overrides", [
        {"capability_profile": "https://evil.example/path"},
        {"budget_profile": "unknown"},
        {"report_profile": "url"},
        {"degradation_policy": "http://localhost:8080/admin"},
        {"output": "https://evil.example"},
        {"citations": "anything goes"},
    ])
    def test_unknown_or_unsafe_values_fall_back_and_pass_validation(self, tmp_path, overrides):
        store, session = _build(tmp_path, overrides)
        output = build_session_plan_output(store, session, OWNER)
        normalized = validate_research_plan_output(output, expected_version=1)
        assert normalized["plan_version"] == 1
        assert normalized["budget"]["target_paper_count"] == 5

    def test_no_new_nested_keys_or_url_valued_keys_are_introduced(self, tmp_path):
        store, session = _build(tmp_path, {
            "capability_profile": "full",
            "budget_profile": "balanced",
            "report_profile": "standard",
            "degradation_policy": "balanced",
        })
        output = build_session_plan_output(store, session, OWNER)
        assert set(output["budget"]) <= {
            "quality_profile", "target_paper_count", "soft_budget_seconds", "language"
        }
        assert set(output["report_structure"]) <= {
            "sections", "format", "citations", "language", "title"
        }
        assert set(output["safe_summary"]) <= {"decision", "notes", "constraints", "degraded"}


class TestAuthorPlanEndToEnd:
    def test_profile_driven_plan_passes_author_plan_guardrails(self, tmp_path):
        """契约硬约束：4 块改造后的 payload 仍能走 author_plan 落库。"""
        from backend.app.platform.config import BASE_DIR
        from backend.app.research.application.approval_service import PlanApprovalService
        from backend.app.skills.registry import build_default_tool_registry
        from backend.app.skills.service import SkillRegistryService
        from backend.app.skills.tool_service import ToolRegistryService

        store, session = _build(tmp_path, {
            "capability_profile": "catalog_only",
            "budget_profile": "deep",
            "report_profile": "brief",
            "degradation_policy": "conservative",
        })
        output = build_session_plan_output(store, session, OWNER)
        service = PlanApprovalService(
            store=store,
            skill_registry=SkillRegistryService(
                BASE_DIR / ".agents" / "skills", tmp_path / "skill-state.json"
            ),
            tool_registry=ToolRegistryService(
                build_default_tool_registry(), tmp_path / "skill-state.json"
            ),
        )
        result = service.author_plan(session.research_session_id, OWNER, output)
        assert result["status"] == "plan_pending_approval"
        persisted = store.get_session_plan(session.research_session_id, OWNER)
        assert json.loads(persisted.budget_json)["soft_budget_seconds"] == 3600
        assert len(json.loads(persisted.capabilities_json)) == 1
        assert "保守" in json.loads(persisted.safety_summary_json)["decision"]
