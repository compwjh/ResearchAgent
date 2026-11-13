"""契约测试：深度研究 Intake「逐轮引导式询问」（9 轮目录 / 回答协议 / SSE 投影）。

按跨端契约 ``intake-guided-questions-contract.md`` 第 2、4 节锁定后端行为：
- 9 轮一问一答、候选含推荐、进度 index/total；
- ``[intake:key=value]`` 协议解析（use_recommended / use_all_recommended /
  choice_id / custom:<文本>）与安全拒绝；
- prompt / quick_actions / progress 经 projection 与 SSE 帧输出；
- 历史会话 not_required 不重问、active_conflict / draft complete / 意图分类器不回归。
"""
from __future__ import annotations

import json

import pytest

from backend.app.api import routes_conversations as rc
from backend.app.api.routes_research import _normalize_session_intake
from backend.app.memory.repository import MemoryRepository
from backend.app.research.application import intake as intake_mod
from backend.app.research.application.intake import (
    ResearchIntakeCoordinator,
    classify_intake_intent,
)
from backend.app.research.application.intake_projection import build_intake_projection
from backend.app.research.domain.models import IntakeField
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.service import SkillRegistryService

OWNER = "owner-a"
SKILL_BODY = "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody"
TOTAL = 9
EXPECTED_KEYS = (
    "q_topic", "q_objective", "q_time_range", "q_language",
    "q_sources_capabilities", "q_budget_depth", "q_paper_count",
    "q_report_structure", "q_degradation",
)


def _setup(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation(OWNER, None, "intake")
    store = ResearchStore(tmp_path / "research.sqlite3")
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    registry = SkillRegistryService(tmp_path / "skills", tmp_path / "skill-state.json")
    return memory, store, conversation, registry


def _coordinator(store, memory, registry):
    return ResearchIntakeCoordinator(store, memory, registry)


def _send(coordinator, memory, conversation, text):
    _c, user, _a = memory.create_message_pair(conversation.conversation_id, OWNER, text)
    return coordinator.handle_message(conversation.conversation_id, OWNER, user.message_id, user.content)


def _fields_by_name(store, draft_id):
    out = {}
    for item in store.list_intake_fields(draft_id, OWNER):
        try:
            out[item.field_name] = json.loads(item.value_json)
        except (ValueError, TypeError):
            out[item.field_name] = item.value_json
    return out


def _field_items(store, draft_id):
    return {item.field_name: item for item in store.list_intake_fields(draft_id, OWNER)}


def _prompt(result):
    return getattr(result, "prompt", None)


def _start_with_topic_and_objective(coordinator, memory, conversation):
    """只给「主题 + 目标」的研究请求：第 1/2 轮应自动跳过。"""
    return _send(
        coordinator, memory, conversation,
        "帮我做一个深度研究，主题是 LLM 安全对齐，目标是总结主流对齐方法与局限。",
    )


def _start_all_defaults(coordinator, memory, conversation):
    """通过显式 capability 建一个所有字段均为未确认默认值的会话。"""
    _c, user, _a = memory.create_message_pair(conversation.conversation_id, OWNER, "开始研究")
    return coordinator.begin_research_intake(
        conversation.conversation_id, OWNER, user.message_id, fields={}
    )


# ---------------------------------------------------------------------------
# 9 轮问题目录（契约 2.2 / 2.3）
# ---------------------------------------------------------------------------
class TestGuidedQuestionCatalog:
    def test_catalog_has_nine_rounds_in_contract_order(self):
        catalog = getattr(intake_mod, "GUIDED_QUESTIONS", None)
        assert catalog, "GUIDED_QUESTIONS 目录常量必须存在且非空"
        assert len(catalog) == TOTAL
        assert tuple(item["key"] for item in catalog) == EXPECTED_KEYS
        for position, item in enumerate(catalog, start=1):
            assert item["index"] == position
            assert item["total"] == TOTAL
            assert item["label"] and item["question"]
            assert item["allow_custom"] is True
            assert item["custom_label"]
            assert item["fields"], "每轮必须声明目标字段"
            # 目录常量内部用 tuple 保持不可变；对外的 prompt.choices 由
            # derive_guided_state 转成 list（契约 2.4）。
            assert isinstance(item["choices"], (list, tuple))
            # 契约 2.3：q_topic / q_objective 允许少于 3 个候选，其余 3 个
            expected_len = 2 if item["key"] in {"q_topic", "q_objective"} else 3
            assert len(item["choices"]) == expected_len, item["key"]
            assert sum(bool(c["recommended"]) for c in item["choices"]) == 1, item["key"]
            ids = [c["id"] for c in item["choices"]]
            assert len(ids) == len(set(ids)), item["key"]
            assert all(c["id"] and c["label"] for c in item["choices"])

    def test_catalog_choice_ids_are_stable(self):
        catalog = getattr(intake_mod, "GUIDED_QUESTIONS", None)
        assert catalog, "GUIDED_QUESTIONS 目录常量必须存在且非空"
        by_key = {item["key"]: [c["id"] for c in item["choices"]] for item in catalog}
        # 契约 2.4 明确给出的三个候选 id，不得改动
        assert by_key["q_sources_capabilities"] == ["full", "search_eval", "catalog_only"]
        assert by_key["q_time_range"] == ["recent_3y", "recent_5y", "all_time"]
        assert by_key["q_language"] == ["zh", "en", "bilingual"]
        assert by_key["q_budget_depth"] == ["balanced", "fast", "deep"]
        assert by_key["q_paper_count"] == ["p5", "p3", "p10"]
        assert by_key["q_report_structure"] == ["standard", "deep", "brief"]
        assert by_key["q_degradation"] == ["balanced", "conservative", "flexible"]
        assert by_key["q_topic"] == ["keep", "custom"]
        assert by_key["q_objective"] == ["keep", "custom"]

    def test_catalog_field_mapping_covers_all_intake_fields(self):
        from backend.app.research.domain.contracts import INTAKE_FIELDS

        catalog = getattr(intake_mod, "GUIDED_QUESTIONS", None)
        assert catalog, "GUIDED_QUESTIONS 目录常量必须存在且非空"
        mapped = {name for item in catalog for name in item["fields"]}
        assert mapped == set(INTAKE_FIELDS)
        assert len(mapped) == 13


# ---------------------------------------------------------------------------
# 逐轮推导（契约 2.1 / 2.2 / 验收点 1、2）
# ---------------------------------------------------------------------------
class TestRoundByRoundPrompt:
    def test_first_turn_skips_topic_and_objective_and_starts_at_time_range(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        prompt = _prompt(result)
        assert prompt is not None, "首句给全主题/目标后仍应给出当前轮 prompt"
        assert prompt["key"] == "q_time_range"
        assert prompt["index"] == 3
        assert prompt["total"] == TOTAL
        assert getattr(result, "progress", None) == {"answered": 2, "total": TOTAL}
        fields = _fields_by_name(store, result.session.intake_draft_id)
        assert fields["topic"] == "LLM 安全对齐"
        assert fields["objective"] == "总结主流对齐方法与局限"

    def test_first_turn_with_only_topic_starts_at_objective(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _send(
            coordinator, memory, conversation,
            "帮我做一个深度研究，主题是软件供应链攻击",
        )
        prompt = _prompt(result)
        assert prompt is not None
        assert prompt["key"] == "q_objective"
        assert prompt["index"] == 2
        assert getattr(result, "progress", None) == {"answered": 1, "total": TOTAL}

    def test_prompt_is_one_question_not_all_nine_at_once(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        prompt = _prompt(result)
        assert isinstance(prompt, dict)
        assert len(prompt["choices"]) in (2, 3)
        # 只呈现当前一轮，不把 9 个标签一次列全
        assert "报告语言" not in prompt["question"]
        assert "降级策略" not in prompt["question"]
        # 旧 question 键语义不变（收齐 BLOCKING 后为 None）；当前轮问句由
        # prompt.question 承载，供前端引导区块渲染。
        full = _send(
            coordinator, memory, conversation,
            "【研究参数】时间范围：不限 [intake:q_time_range=all_time]",
        )
        assert _prompt(full)["key"] == "q_language"
        assert full.question is None
        assert _prompt(full)["question"] == "报告希望用什么语言撰写？"

    def test_prompt_advances_one_round_per_answer(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        assert _prompt(result)["key"] == "q_time_range"
        sequence = [
            ("q_time_range", "all_time", "q_language"),
            ("q_language", "zh", "q_sources_capabilities"),
            ("q_sources_capabilities", "full", "q_budget_depth"),
            ("q_budget_depth", "balanced", "q_paper_count"),
            ("q_paper_count", "p5", "q_report_structure"),
            ("q_report_structure", "standard", "q_degradation"),
        ]
        for index, (key, choice_id, next_key) in enumerate(sequence, start=3):
            answered = _send(
                coordinator, memory, conversation,
                f"【研究参数】{key}：{choice_id} [intake:{key}={choice_id}]",
            )
            prompt = _prompt(answered)
            assert prompt["key"] == next_key, key
            assert prompt["index"] == index + 1
            assert getattr(answered, "progress", None)["answered"] == index
        assert _prompt(answered)["total"] == TOTAL


# ---------------------------------------------------------------------------
# 回答消息协议（契约 2.5 / 验收点 3、4、5、6）
# ---------------------------------------------------------------------------
class TestAnswerProtocol:
    def test_specific_choice_writes_user_explicit_and_advances(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        draft_id = result.session.intake_draft_id
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】时间范围：近 5 年 [intake:q_time_range=recent_5y]",
        )
        items = _field_items(store, draft_id)
        assert json.loads(items["time_range"].value_json) == {"from": 2021, "to": 2026}
        assert items["time_range"].source == "user_explicit"
        assert items["time_range"].confirmation_status == "confirmed"
        assert _prompt(answered)["key"] == "q_language"
        assert _prompt(answered)["index"] == 4

    def test_constraints_choice_keeps_existing_encoding(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        for key, choice_id in (("q_time_range", "recent_3y"), ("q_language", "zh"),
                               ("q_sources_capabilities", "full"), ("q_budget_depth", "balanced")):
            _send(coordinator, memory, conversation,
                  f"【研究参数】[intake:{key}={choice_id}]")
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】目标论文数：5 篇 [intake:q_paper_count=p5]",
        )
        fields = _fields_by_name(store, result.session.intake_draft_id)
        assert fields["constraints"] == ["target_paper_count:5"]
        assert json.loads(_field_items(store, result.session.intake_draft_id)["time_range"].value_json) == {"from": 2023, "to": 2026}
        assert _prompt(answered)["key"] == "q_report_structure"

    def test_use_recommended_writes_recommended_value_and_confirms(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        draft_id = result.session.intake_draft_id
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】时间范围：用推荐 [intake:q_time_range=use_recommended]",
        )
        items = _field_items(store, draft_id)
        assert json.loads(items["time_range"].value_json) == {"from": 2023, "to": 2026}
        assert items["time_range"].source == "system_default"
        assert items["time_range"].confirmation_status == "confirmed"
        assert _prompt(answered)["key"] == "q_language"

    def test_use_all_recommended_collects_all_rounds_in_one_turn(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        draft_id = result.session.intake_draft_id
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]",
        )
        assert _prompt(answered) is None
        assert getattr(answered, "progress", None) == {"answered": TOTAL, "total": TOTAL}
        assert answered.missing == []
        assert store.get_intake_draft(answered.session.research_session_id, OWNER).status == "complete"
        items = _field_items(store, draft_id)
        for item in items.values():
            assert item.confirmation_status in {"confirmed", "not_required"}, item.field_name
        fields = _fields_by_name(store, draft_id)
        assert fields["constraints"] == ["target_paper_count:5"]
        assert fields["capability_profile"] == "full"
        assert fields["budget_profile"] == "balanced"
        assert fields["report_profile"] == "standard"
        assert fields["degradation_policy"] == "balanced"

    def test_custom_input_writes_the_declared_round_field(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_all_defaults(coordinator, memory, conversation)
        draft_id = result.session.intake_draft_id
        assert _prompt(result)["key"] == "q_topic"
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】研究主题：LLM 安全对齐 [intake:q_topic=custom:LLM 安全对齐]",
        )
        items = _field_items(store, draft_id)
        assert json.loads(items["topic"].value_json) == "LLM 安全对齐"
        assert items["topic"].source == "user_explicit"
        assert items["topic"].confirmation_status == "confirmed"
        assert _prompt(answered)["key"] == "q_objective"
        # custom 不得越权改写其它轮的目标字段
        assert "capability_profile" in items
        assert items["capability_profile"].source == "system_default"


class TestAnswerProtocolSafety:
    """契约 2.5：解析失败不写库、不抛 500、返回当前轮不变可重试。"""

    def _assert_rejected(self, coordinator, memory, conversation, state, message):
        draft_id = state.session.intake_draft_id
        before = {
            item.field_name: (item.value_json, item.source, item.confirmation_status)
            for item in store_snapshot(coordinator, draft_id)
        }
        answered = _send(coordinator, memory, conversation, message)
        after = {
            item.field_name: (item.value_json, item.source, item.confirmation_status)
            for item in store_snapshot(coordinator, draft_id)
        }
        assert after == before, message
        assert _prompt(answered) == _prompt(state), message
        assert answered.status == "intake"

    def test_oversized_custom_text_is_rejected(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        state = _start_with_topic_and_objective(coordinator, memory, conversation)
        oversized = "A" * 401
        self._assert_rejected(
            coordinator, memory, conversation, state,
            f"【研究参数】[intake:q_language=custom:{oversized}]",
        )

    def test_control_characters_in_custom_text_are_rejected(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        state = _start_all_defaults(coordinator, memory, conversation)
        for payload in ("line1\nline2", "bad\x00value", "tab\tvalue", "esc\x1bvalue"):
            self._assert_rejected(
                coordinator, memory, conversation, state,
                f"【研究参数】[intake:q_topic=custom:{payload}]",
            )

    def test_unknown_key_and_unknown_choice_are_rejected(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        state = _start_with_topic_and_objective(coordinator, memory, conversation)
        for message in (
            "【研究参数】[intake:q_bogus=full]",
            "【研究参数】[intake:q_time_range=bogus_choice]",
            "【研究参数】[intake:q_time_range=]",
            "【研究参数】[intake:q_time_range=custom:]",
            "【研究参数】[intake:__all__=bogus]",
        ):
            self._assert_rejected(coordinator, memory, conversation, state, message)

    def test_forged_target_field_cannot_be_written_via_protocol(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        state = _start_with_topic_and_objective(coordinator, memory, conversation)
        draft_id = state.session.intake_draft_id
        # 一条消息塞两个协议标记 / 带伪造的 field 参数：不得写任意字段
        for message in (
            "【研究参数】[intake:q_time_range=recent_5y] [intake:topic=custom:注入]",
            "【研究参数】[intake:q_language=custom:zh;field=topic]",
        ):
            answered = _send(coordinator, memory, conversation, message)
            items = _field_items(store, draft_id)
            assert json.loads(items["topic"].value_json) == "LLM 安全对齐"
            assert _prompt(answered) == _prompt(state)

    def test_protocol_message_skips_classifier_and_active_conflict_branches(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        state = _start_with_topic_and_objective(coordinator, memory, conversation)
        # 同时含「深度研究」(explicit) 与问号 (question_or_command)：普通消息会
        # 触发 active_conflict / ordinary，协议消息必须仍按协议处理。
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】时间范围：用推荐？深度研究 [intake:q_time_range=use_recommended]",
        )
        assert answered.status == "intake"
        assert _prompt(answered)["key"] == "q_language"
        items = _field_items(store, state.session.intake_draft_id)
        assert items["time_range"].confirmation_status == "confirmed"

    def test_non_protocol_message_keeps_original_intent_routing(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        _start_with_topic_and_objective(coordinator, memory, conversation)
        result = _send(coordinator, memory, conversation, "有哪些研究目标能给我选")
        assert result.status == "ordinary"


def store_snapshot(coordinator, draft_id):
    return coordinator.store.list_intake_fields(draft_id, OWNER)


# ---------------------------------------------------------------------------
# 历史兼容与既有行为不回归（契约 2.1 / 验收点 8）
# ---------------------------------------------------------------------------
class TestBackwardCompatibility:
    def test_historical_not_required_fields_are_not_reasked(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        draft_id = result.session.intake_draft_id
        # 模拟改前落库：把默认字段整体改成 not_required（不重问）
        for item in store.list_intake_fields(draft_id, OWNER):
            if item.source == "system_default":
                store.upsert_intake_field(
                    IntakeField(
                        intake_draft_id=draft_id,
                        field_name=item.field_name,
                        value_json=item.value_json,
                        source="system_default",
                        confidence=1.0,
                        confirmation_status="not_required",
                        updated_by_message_id="legacy",
                        updated_at="",
                    ),
                    OWNER,
                )
        # 补齐剩余 blocking 字段（历史会话本就齐全）
        for name, value in (("time_range", {"from": 2020, "to": 2024}),):
            store.upsert_intake_field(
                IntakeField(draft_id, name, json.dumps(value), "user_explicit", 1.0,
                            "confirmed", "", "legacy"),
                OWNER,
            )
        from backend.app.research.application.intake import derive_guided_state

        state = derive_guided_state(store.list_intake_fields(draft_id, OWNER))
        assert state["prompt"] is None
        assert state["progress"] == {"answered": TOTAL, "total": TOTAL}

    def test_active_conflict_choices_are_unchanged(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        _start_with_topic_and_objective(coordinator, memory, conversation)
        conflict = _send(
            coordinator, memory, conversation,
            "帮我做深度研究，研究云安全",
        )
        assert conflict.status == "active_conflict"
        assert [c["id"] for c in conflict.choices] == [
            "modify_current", "cancel_then_new", "new_conversation"
        ]
        assert _prompt(conflict) is None

    def test_draft_complete_stops_absorbing_non_protocol_messages(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        _send(
            coordinator, memory, conversation,
            "帮我做深度研究，研究侧信道攻击",
        )
        _send(
            coordinator, memory, conversation,
            "目标是生成综述，时间范围是2020-2025",
        )
        # 契约 5.1：补完 BLOCKING 但 9 轮引导未收齐时 draft 仍 collecting；
        # 收齐后 draft 才 complete，此后非协议消息不进抽取器（本用例原意图）。
        completed = _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]",
        )
        assert completed.prompt is None
        assert store.get_intake_draft(completed.session.research_session_id, OWNER).status == "complete"
        after = _send(coordinator, memory, conversation, "再补充一点范围")
        assert after.status == "ordinary"

    def test_intent_classifier_contract_is_unchanged(self):
        assert classify_intake_intent("研究目标：生成综述，时间范围是2020-2025") == "answer"
        assert classify_intake_intent("研究目标应该写什么？") == "question_or_command"
        assert classify_intake_intent("取消") == "question_or_command"
        assert classify_intake_intent("") == "answer"


# ---------------------------------------------------------------------------
# 契约 2.4：投影结构、SSE 帧、历史回放、白名单
# ---------------------------------------------------------------------------
class TestProjectionContract:
    def test_four_new_intake_fields_and_defaults_are_registered(self):
        from backend.app.research.domain.contracts import INTAKE_FIELDS

        new_fields = {"capability_profile", "budget_profile", "report_profile", "degradation_policy"}
        assert new_fields <= set(INTAKE_FIELDS)
        assert new_fields <= set(intake_mod.DEFAULT_FIELDS)
        assert intake_mod.DEFAULT_FIELDS["capability_profile"] == "full"
        assert intake_mod.DEFAULT_FIELDS["budget_profile"] == "balanced"
        assert intake_mod.DEFAULT_FIELDS["report_profile"] == "standard"
        assert intake_mod.DEFAULT_FIELDS["degradation_policy"] == "balanced"

    def test_build_intake_projection_matches_contract_shape(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        projection = build_intake_projection(result)
        # 旧键：类型与语义一律不变
        assert projection["schema_version"] == "task03-intake-v1"
        assert projection["status"] == "intake"
        assert isinstance(projection["fields"], list)
        assert isinstance(projection["missing"], list)
        assert isinstance(projection["choices"], list)
        # 旧 question 键在 BLOCKING 尚未齐全时沿用既有「请补充：…」文案（既有契约）
        assert projection["question"] == "请补充：时间范围"
        assert projection["skill"]["skill_id"] == "deep-research-orchestration"
        assert projection["research_session"]["research_session_id"] == result.session.research_session_id
        # 新键
        prompt = projection["prompt"]
        assert prompt["key"] == "q_time_range"
        assert prompt["index"] == 3 and prompt["total"] == TOTAL
        assert prompt["label"] and prompt["question"]
        assert prompt["allow_custom"] is True and prompt["custom_label"]
        assert isinstance(prompt["choices"], list)
        assert [c["id"] for c in prompt["choices"]] == ["recent_3y", "recent_5y", "all_time"]
        assert [c["recommended"] for c in prompt["choices"]] == [True, False, False]
        assert [a["id"] for a in projection["quick_actions"]] == [
            "use_recommended", "use_all_recommended"
        ]
        assert projection["progress"] == {"answered": 2, "total": TOTAL}

    def test_projection_choices_still_only_carry_active_conflict(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        _start_with_topic_and_objective(coordinator, memory, conversation)
        conflict = _send(coordinator, memory, conversation, "帮我做深度研究，研究云安全")
        projection = build_intake_projection(conflict)
        assert [c["id"] for c in projection["choices"]] == [
            "modify_current", "cancel_then_new", "new_conversation"
        ]
        assert projection["prompt"] is None

    def test_projection_prompt_is_null_when_all_rounds_answered(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        _start_with_topic_and_objective(coordinator, memory, conversation)
        answered = _send(
            coordinator, memory, conversation,
            "【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]",
        )
        projection = build_intake_projection(answered)
        assert projection["prompt"] is None
        assert projection["missing"] == []
        assert projection["progress"]["answered"] == TOTAL
        assert projection["status"] == "intake"

    def test_sse_intake_frame_carries_new_keys(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        _c, user, assistant = memory.create_message_pair(
            conversation.conversation_id, OWNER,
            "帮我做一个深度研究，主题是 LLM 安全对齐，目标是总结主流对齐方法与局限。",
        )
        result = coordinator.handle_message(
            conversation.conversation_id, OWNER, user.message_id, user.content
        )
        frames = "".join(
            rc._intake_stream(memory, conversation, user, assistant, result, "model", "normal", "off")
        )
        events = [json.loads(line[6:]) for line in frames.splitlines() if line.startswith("data: ")]
        intake_frame = next(event for event in events if event["type"] == "intake")
        assert intake_frame["prompt"]["key"] == "q_time_range"
        assert [a["id"] for a in intake_frame["quick_actions"]] == [
            "use_recommended", "use_all_recommended"
        ]
        assert intake_frame["progress"] == {"answered": 2, "total": TOTAL}

    def test_history_replay_carries_new_keys(self, tmp_path):
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator = _coordinator(store, memory, registry)
        result = _start_with_topic_and_objective(coordinator, memory, conversation)
        replay = rc._safe_intake_projection(build_intake_projection(result))
        assert replay is not None
        assert replay["prompt"]["key"] == "q_time_range"
        assert replay["progress"] == {"answered": 2, "total": TOTAL}
        assert [a["id"] for a in replay["quick_actions"]] == [
            "use_recommended", "use_all_recommended"
        ]

    def test_legacy_projection_without_new_keys_still_replays(self):
        legacy = {
            "schema_version": "task03-intake-v1",
            "status": "intake",
            "fields": [], "missing": [], "choices": [], "question": None,
            "skill": None, "research_session": None,
        }
        replay = rc._safe_intake_projection(legacy)
        assert replay is not None
        assert replay["prompt"] is None
        assert replay["quick_actions"] == []
        assert replay["progress"] is None

    def test_normalize_session_intake_accepts_four_new_profile_fields(self):
        payload = {
            "topic": "LLM 安全对齐",
            "capability_profile": "catalog_only",
            "budget_profile": "deep",
            "report_profile": "brief",
            "degradation_policy": "flexible",
        }
        normalized = _normalize_session_intake(payload)
        assert normalized == payload
        with pytest.raises(ValueError, match="unknown intake fields"):
            _normalize_session_intake({"not_a_profile": "x"})
