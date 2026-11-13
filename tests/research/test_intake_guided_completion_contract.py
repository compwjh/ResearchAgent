"""契约测试：联调裁决 5.1 / 5.2 —— 完成时机、/plans/generate 守卫、当前轮协议。

跨端契约 ``intake-guided-questions-contract.md`` 第 5 节：
- 5.1 ``_finalize_turn`` 置 complete 必须同时满足 ``not missing`` 且
  ``derive_guided_state(saved)["prompt"] is None``；首句说全 3 个 BLOCKING
  时 9 轮未收齐，draft 必须保持 collecting。
- 5.1 ``/plans/generate`` 必须以 ``prompt is None`` 为准，不得仅凭
  ``draft.status == "complete"`` 放行；未收齐返回 INTAKE_INCOMPLETE 且不落库计划。
- 5.1 老会话（not_required 字段、无 4 个新 profile）仍照常生成计划。
- 5.2 非 ``__all__`` 的回答 key 必须等于当前轮 ``prompt.key``；旧轮次 key 是 no-op。
"""
from __future__ import annotations

import json

from fastapi.responses import JSONResponse

from backend.app.api import routes_research as rr
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.config import BASE_DIR
from backend.app.research.application.approval_service import PlanApprovalService
from backend.app.research.application.intake import (
    ResearchIntakeCoordinator,
    derive_guided_state,
)
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.service import SkillRegistryService
from backend.app.skills.tool_service import ToolRegistryService

OWNER = OWNER_ID  # /plans/generate 端点硬编码 OWNER_ID，测试数据必须同源
# /plans/generate 守卫（9 轮引导未收齐）的对外文案；错误码 INTAKE_INCOMPLETE 不变。
# 逐字断言，防止复用「必填项缺失」的旧文案误导首句已说全 3 必填的用户。
INTAKE_INCOMPLETE_MESSAGE = "研究参数尚未逐项确认完成，请先完成逐项询问或选择『都按推荐』"
SKILL_BODY = "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody"
FULL_FIRST_TURN = (
    "帮我做一个深度研究，主题是 LLM 安全对齐，"
    "目标是梳理主流对齐方法与局限，时间范围是2023-2025。"
)
LEGACY_SECTIONS = ["研究问题", "方法与来源", "主要发现", "局限与后续工作"]
# 4 个计划偏好轮使用**非推荐**候选，用来证明计划读到的是用户选择而非默认值。
NON_RECOMMENDED = {
    "q_sources_capabilities": "catalog_only",
    "q_budget_depth": "deep",
    "q_report_structure": "brief",
    "q_degradation": "conservative",
}


def _setup(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation(OWNER, None, "intake")
    store = ResearchStore(tmp_path / "research.sqlite3")
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    registry = SkillRegistryService(tmp_path / "skills", tmp_path / "skill-state.json")
    return memory, store, conversation, registry


def _send(coordinator, memory, conversation, text):
    _, user, _ = memory.create_message_pair(conversation.conversation_id, OWNER, text)
    return coordinator.handle_message(conversation.conversation_id, OWNER, user.message_id, user.content)


def _start(memory, store, conversation, registry, text=FULL_FIRST_TURN):
    coordinator = ResearchIntakeCoordinator(store, memory, registry)
    return coordinator, _send(coordinator, memory, conversation, text)


def _draft(store, result):
    return store.get_intake_draft(result.session.research_session_id, OWNER)


def _snapshot(store, draft_id):
    """字段全量快照：任何写库（值 / 来源 / 确认状态 / message id）都会改变它。"""
    return [
        (item.field_name, item.value_json, item.source, item.confirmation_status, item.updated_by_message_id)
        for item in store.list_intake_fields(draft_id, OWNER)
    ]


def _guided(store, draft_id):
    return derive_guided_state(store.list_intake_fields(draft_id, OWNER))


def _answer_current_round(coordinator, memory, conversation, store, draft_id, value=None):
    prompt = _guided(store, draft_id)["prompt"]
    assert prompt is not None, "引导已收齐，不应再回答"
    answer = value or NON_RECOMMENDED.get(prompt["key"], "use_recommended")
    text = f"【研究参数】{prompt['label']}：{answer} [intake:{prompt['key']}={answer}]"
    return _send(coordinator, memory, conversation, text)


def _finish_all_rounds(coordinator, memory, conversation, store, draft_id, max_rounds=9):
    result = None
    for _ in range(max_rounds):
        if _guided(store, draft_id)["prompt"] is None:
            break
        result = _answer_current_round(coordinator, memory, conversation, store, draft_id)
    assert _guided(store, draft_id)["prompt"] is None, "9 轮应全部收齐"
    return result


def _approval_service(store, tmp_path):
    state_path = tmp_path / "skill-state.json"
    return PlanApprovalService(
        store=store,
        skill_registry=SkillRegistryService(BASE_DIR / ".agents" / "skills", state_path),
        tool_registry=ToolRegistryService(build_default_tool_registry(), state_path),
    )


def _generate(monkeypatch, store, memory, tmp_path, session_id):
    """直接调用 /plans/generate 端点函数；注入同源临时 store / memory / approval。"""
    service = _approval_service(store, tmp_path)
    monkeypatch.setattr(rr, "_approval_service", lambda: service)
    monkeypatch.setattr(rr, "_store", lambda: store)
    monkeypatch.setattr(rr, "_memory", lambda: memory)
    return rr.generate_research_session_plan(session_id)


def _error(response):
    assert isinstance(response, JSONResponse), f"期望错误响应，实际：{type(response).__name__} {response!r}"
    return response.status_code, json.loads(response.body)


def _legacy_session(store, memory, conversation):
    """改前创建的历史会话：9 个原始字段、无 4 个新 profile、draft=complete。"""
    _, user, _ = memory.create_message_pair(conversation.conversation_id, OWNER, "老会话研究")
    session = ResearchSession(
        "session-legacy", OWNER, conversation.conversation_id,
        user.message_id, "draft-legacy", "intake_pending",
    )
    store.create_session(session, memory_repository=memory)
    values = {
        "topic": "LLM 安全", "objective": "梳理现状",
        "time_range": {"from": 2020, "to": 2024},
        "language": "zh", "sources": ["usenix"], "depth": "balanced",
        "output": "markdown", "citations": "inline",
        "constraints": ["target_paper_count:5"],
    }
    explicit = {"topic", "objective", "time_range"}
    for name, value in values.items():
        store.upsert_intake_field(
            IntakeField(
                "draft-legacy", name, json.dumps(value, ensure_ascii=False),
                "user_explicit" if name in explicit else "system_default",
                1.0,
                "confirmed" if name in explicit else "not_required",
                "", user.message_id,
            ),
            OWNER,
        )
    store.update_intake_status("draft-legacy", OWNER, "complete")
    return session


# ---------------------------------------------------------------------------
# 契约 5.1：draft 完成时机 + /plans/generate 端点守卫
# ---------------------------------------------------------------------------
class TestFinalizeTurnCompletionGate:
    def test_first_turn_with_all_blocking_fields_stays_collecting_with_prompt(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        _coordinator, result = _start(memory, store, conversation, registry)
        assert result.missing == []  # 旧 missing 语义保持不变
        assert result.prompt is not None
        assert result.prompt["key"] == "q_language"  # 前 3 轮因 user_explicit 跳过
        assert result.progress == {"answered": 3, "total": 9}
        assert _draft(store, result).status == "collecting"
        assert _guided(store, result.session.intake_draft_id)["prompt"]["key"] == "q_language"

    def test_plans_generate_refuses_before_all_rounds_are_answered(self, tmp_path, monkeypatch):
        memory, store, conversation, registry = _setup(tmp_path)
        _coordinator, result = _start(memory, store, conversation, registry)
        session_id = result.session.research_session_id
        status, body = _error(_generate(monkeypatch, store, memory, tmp_path, session_id))
        assert status == 400
        assert body["error"]["code"] == "INTAKE_INCOMPLETE"
        assert body["error"]["message"] == INTAKE_INCOMPLETE_MESSAGE
        assert body["error"]["retryable"] is False
        assert store.get_session_plan(session_id, OWNER) is None

    def test_full_first_turn_with_unfinished_rounds_reports_guidance_message(self, tmp_path, monkeypatch):
        """首句说全 3 必填但 9 轮未收齐：文案须指向逐项确认，不得复述「必填项缺失」。"""
        memory, store, conversation, registry = _setup(tmp_path)
        _coordinator, result = _start(memory, store, conversation, registry)
        assert result.missing == []  # topic/objective/time_range 首句已说全
        assert result.prompt is not None  # 9 轮引导停在第 4/9 项
        assert result.progress == {"answered": 3, "total": 9}
        session_id = result.session.research_session_id
        status, body = _error(_generate(monkeypatch, store, memory, tmp_path, session_id))
        assert status == 400
        assert body["error"]["code"] == "INTAKE_INCOMPLETE"
        assert body["error"]["message"] == INTAKE_INCOMPLETE_MESSAGE
        assert store.get_session_plan(session_id, OWNER) is None

    def test_plans_generate_refuses_even_when_draft_status_was_forced_complete(self, tmp_path, monkeypatch):
        """守卫必须独立于 draft.status：仅凭 complete 放行会重演缓存默认计划的故障。"""
        memory, store, conversation, registry = _setup(tmp_path)
        _coordinator, result = _start(memory, store, conversation, registry)
        session_id = result.session.research_session_id
        store.update_intake_status(result.session.intake_draft_id, OWNER, "complete")
        status, body = _error(_generate(monkeypatch, store, memory, tmp_path, session_id))
        assert status == 400
        assert body["error"]["code"] == "INTAKE_INCOMPLETE"
        assert store.get_session_plan(session_id, OWNER) is None

    def test_use_all_recommended_completes_draft_and_generates_plan(self, tmp_path, monkeypatch):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        session_id = result.session.research_session_id
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]",
        )
        assert answered.prompt is None
        assert answered.missing == []
        assert _draft(store, answered).status == "complete"
        plan_result = _generate(monkeypatch, store, memory, tmp_path, session_id)
        assert isinstance(plan_result, dict)
        assert plan_result["status"] == "plan_pending_approval"
        assert store.get_session_plan(session_id, OWNER) is not None

    def test_rejected_generate_does_not_cache_default_plan_and_later_choices_win(self, tmp_path, monkeypatch):
        """首句说全 3 必填时不生成/不缓存计划；9 轮非推荐选择后计划才反映选择。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        session_id = result.session.research_session_id
        draft_id = result.session.intake_draft_id
        status, body = _error(_generate(monkeypatch, store, memory, tmp_path, session_id))
        assert status == 400
        assert body["error"]["code"] == "INTAKE_INCOMPLETE"
        assert store.get_session_plan(session_id, OWNER) is None
        final = _finish_all_rounds(coordinator, memory, conversation, store, draft_id)
        assert final.prompt is None
        assert _draft(store, final).status == "complete"
        plan_result = _generate(monkeypatch, store, memory, tmp_path, session_id)
        assert isinstance(plan_result, dict)
        persisted = store.get_session_plan(session_id, OWNER)
        assert persisted is not None
        assert len(json.loads(persisted.capabilities_json)) == 1
        assert json.loads(persisted.budget_json)["soft_budget_seconds"] == 3600
        assert len(json.loads(persisted.report_structure_json)["sections"]) < len(LEGACY_SECTIONS)
        assert "保守" in json.loads(persisted.safety_summary_json)["decision"]

    def test_legacy_session_without_profiles_still_generates_plan(self, tmp_path, monkeypatch):
        memory, store, conversation, _registry = _setup(tmp_path)
        session = _legacy_session(store, memory, conversation)
        assert _guided(store, session.intake_draft_id)["prompt"] is None
        plan_result = _generate(monkeypatch, store, memory, tmp_path, session.research_session_id)
        assert isinstance(plan_result, dict)
        assert plan_result["status"] == "plan_pending_approval"
        assert store.get_session_plan(session.research_session_id, OWNER) is not None


# ---------------------------------------------------------------------------
# 契约 5.2：只接受「当前轮 key」，旧轮次 key 一律安全 no-op
# ---------------------------------------------------------------------------
class TestProtocolCurrentRoundGate:
    def test_stale_round_key_is_noop_and_prompt_unchanged(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        draft_id = result.session.intake_draft_id
        current_key = result.prompt["key"]
        before = _snapshot(store, draft_id)
        stale = _send(
            coordinator, memory, conversation,
            "【研究参数】研究主题：误点旧消息按钮 [intake:q_topic=custom:污染字段]",
        )
        assert stale.status == "intake"
        assert stale.prompt is not None
        assert stale.prompt["key"] == current_key
        assert _snapshot(store, draft_id) == before
        assert _draft(store, stale).status == "collecting"

    def test_stale_use_recommended_key_is_noop(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        draft_id = result.session.intake_draft_id
        current_key = result.prompt["key"]
        before = _snapshot(store, draft_id)
        stale = _send(
            coordinator, memory, conversation,
            "【研究参数】时间范围：用推荐 [intake:q_time_range=use_recommended]",
        )
        assert stale.prompt is not None
        assert stale.prompt["key"] == current_key
        assert _snapshot(store, draft_id) == before

    def test_stale_key_after_partial_progress_is_noop(self, tmp_path):
        """推进一轮后点上一轮（旧消息）的按钮，同样不写库、不回退进度。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        draft_id = result.session.intake_draft_id
        first_key = result.prompt["key"]
        advanced = _send(
            coordinator, memory, conversation,
            f"【研究参数】报告语言：英文 [intake:{first_key}=en]",
        )
        assert advanced.prompt is not None
        assert advanced.prompt["key"] == "q_sources_capabilities"
        before = _snapshot(store, draft_id)
        stale = _send(
            coordinator, memory, conversation,
            f"【研究参数】报告语言：中文 [intake:{first_key}=zh]",
        )
        assert stale.prompt["key"] == "q_sources_capabilities"
        assert _snapshot(store, draft_id) == before

    def test_current_round_key_advances_to_next_round(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        current_key = result.prompt["key"]
        advanced = _answer_current_round(
            coordinator, memory, conversation, store, result.session.intake_draft_id, "en"
        )
        assert advanced.prompt is not None
        assert current_key == "q_language"
        assert advanced.prompt["key"] == "q_sources_capabilities"

    def test_use_all_recommended_still_collects_all_rounds(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]",
        )
        assert answered.prompt is None
        assert answered.progress == {"answered": 9, "total": 9}
        assert _draft(store, answered).status == "complete"

    def test_stale_key_after_all_rounds_completed_is_noop(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        draft_id = result.session.intake_draft_id
        _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]",
        )
        before = _snapshot(store, draft_id)
        stale = _send(
            coordinator, memory, conversation,
            "【研究参数】研究目标：收齐后误点旧按钮 [intake:q_objective=custom:污染]",
        )
        assert stale.prompt is None
        assert _snapshot(store, draft_id) == before


# ---------------------------------------------------------------------------
# 历史会话兼容：derive_guided_state 是端点守卫与投影的共同事实来源
# ---------------------------------------------------------------------------
class TestGuidedStateLegacyCompatibility:
    def test_legacy_fields_without_profiles_yield_no_prompt(self, tmp_path):
        memory, store, conversation, _registry = _setup(tmp_path)
        session = _legacy_session(store, memory, conversation)
        state = _guided(store, session.intake_draft_id)
        assert state["prompt"] is None
        assert state["progress"] == {"answered": 9, "total": 9}

    def test_all_not_required_fields_yield_no_prompt(self):
        fields = [
            IntakeField("d", name, json.dumps("x"), "system_default", 1.0, "not_required", "", "legacy")
            for name in (
                "topic", "objective", "time_range", "language", "sources", "depth",
                "output", "citations", "constraints", "capability_profile",
                "budget_profile", "report_profile", "degradation_policy",
            )
        ]
        state = derive_guided_state(fields)
        assert state["prompt"] is None
        assert state["progress"] == {"answered": 9, "total": 9}

    def test_fresh_session_with_unconfirmed_defaults_still_has_prompt(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        _coordinator, result = _start(memory, store, conversation, registry)
        state = _guided(store, result.session.intake_draft_id)
        assert state["prompt"] is not None
        assert state["prompt"]["key"] == "q_language"

    def test_empty_fields_yield_first_round(self):
        state = derive_guided_state([])
        assert state["prompt"]["key"] == "q_topic"
        assert state["progress"] == {"answered": 0, "total": 9}


# ---------------------------------------------------------------------------
# 端点稳定性（regression-guard 第 11 条）：新增 store 调用异常 → 稳定错误体
# ---------------------------------------------------------------------------
class TestPlansGenerateErrorBody:
    def test_store_failure_returns_503_with_stable_code_not_bare_500(self, tmp_path, monkeypatch):
        memory, store, conversation, registry = _setup(tmp_path)
        _coordinator, result = _start(memory, store, conversation, registry)
        session_id = result.session.research_session_id

        class _FailingStore:
            def list_intake_fields(self, *_args, **_kwargs):
                raise RuntimeError("db broken")

        service = _approval_service(store, tmp_path)
        monkeypatch.setattr(rr, "_approval_service", lambda: service)
        monkeypatch.setattr(rr, "_store", lambda: _FailingStore())
        monkeypatch.setattr(rr, "_memory", lambda: memory)
        status, body = _error(rr.generate_research_session_plan(session_id))
        assert status == 503
        assert body["error"]["code"] == "SOURCE_UNAVAILABLE"
        assert body["error"]["message"] == "计划服务暂时不可用"
        assert store.get_session_plan(session_id, OWNER) is None

    def test_non_all_round_key_with_use_all_value_is_rejected(self, tmp_path):
        """非 __all__ 的旧轮次 key 即使携带 use_all_recommended 值也必须 no-op。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, result = _start(memory, store, conversation, registry)
        draft_id = result.session.intake_draft_id
        current_key = result.prompt["key"]
        before = _snapshot(store, draft_id)
        stale = _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:q_topic=use_all_recommended]",
        )
        assert stale.prompt is not None
        assert stale.prompt["key"] == current_key
        assert _snapshot(store, draft_id) == before
