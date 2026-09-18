"""Spec-029/030/031 修复：研究会话 intake 意图路由与「收齐即停」回归测试。

覆盖两类修复：
  ① 收齐即停：draft 已 complete（参数齐全/计划已生成）后，后续用户消息不再进入抽取器；
  ② 意图判定：active 会话里，明确是提问/元问题/命令的消息不再喂抽取器，走普通对话/命令通道；
             默认归为「回答 intake」（fail-open，维持既有填写主流程）。

复用既有测试夹具风格（MemoryRepository + ResearchStore + SkillRegistryService）。
"""
from __future__ import annotations

import json

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.intake import (
    ResearchIntakeCoordinator,
    classify_intake_intent,
)
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.service import SkillRegistryService

OWNER = "owner-a"
SKILL_BODY = "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody"


def _setup(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation(OWNER, None, "intake")
    store = ResearchStore(tmp_path / "research.sqlite3")
    registry = SkillRegistryService(tmp_path / "skills", tmp_path / "skill-state.json")
    return memory, store, conversation, registry


def _register_skill(tmp_path):
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")


def _fields_by_name(store, draft_id, owner=OWNER):
    out = {}
    for item in store.list_intake_fields(draft_id, owner):
        try:
            value = json.loads(item.value_json)
        except (ValueError, TypeError):
            value = item.value_json
        out[item.field_name] = value
    return out


def _active_draft_status(store, session, owner=OWNER):
    draft = store.get_intake_draft(session.research_session_id, owner)
    return None if draft is None else draft.status


# ---------------------------------------------------------------------------
# ② 意图判定 —— 直接单测分类器
# ---------------------------------------------------------------------------
class TestClassifyIntakeIntent:
    def test_default_is_answer(self):
        # 未匹配任何 (b) 规则 → 默认归为「回答 intake」，维持既有主流程
        for text in ("", "研究目标：生成综述，时间范围是2020-2025", "主题是侧信道攻击",
                     "我想研究怎么防御", "再补充一点范围", "好的"):
            assert classify_intake_intent(text) == "answer", text

    def test_question_mark_is_b(self):
        assert classify_intake_intent("研究目标应该写什么？") == "question_or_command"
        assert classify_intake_intent("这个主题靠谱吗?") == "question_or_command"

    def test_leading_question_word_is_b(self):
        for text in ("哪些研究目标能给我选", "什么是侧信道攻击", "怎么取消研究",
                     "为什么选这个主题", "有没有更窄的范围", "如何开始"):
            assert classify_intake_intent(text) == "question_or_command", text

    def test_meta_question_is_b(self):
        for text in ("有哪些研究目标能给我选", "这是什么意思", "我刚才填的是什么",
                     "刚才填的内容是什么", "研究目标有什么区别"):
            assert classify_intake_intent(text) == "question_or_command", text

    def test_command_is_b(self):
        for text in ("取消", "重来", "停止", "重新开始", "换个主题", "结束研究", "算了"):
            assert classify_intake_intent(text) == "question_or_command", text

    def test_injection_replaces_classifier(self):
        coordinator = ResearchIntakeCoordinator(
            None, None, None, intent_classifier=lambda m: "question_or_command"
        )
        assert coordinator.intent_classifier("任何消息") == "question_or_command"


# ---------------------------------------------------------------------------
# ① + ② 端到端路由（经 handle_message，使用真实 store）
# ---------------------------------------------------------------------------
class TestIntakeIntentRouting:
    def _start_collecting_session(self, tmp_path, memory, store, conversation, registry, first=""):
        _register_skill(tmp_path)
        coordinator = ResearchIntakeCoordinator(store, memory, registry)
        _c, user, _a = memory.create_message_pair(conversation.conversation_id, OWNER, first)
        result = coordinator.handle_message(conversation.conversation_id, OWNER, user.message_id, user.content)
        return coordinator, user, result

    def test_clear_intake_answer_still_fed(self, tmp_path):
        """回归保护：明确的 intake 回答仍被喂给抽取器（走 intake 通道，不被 ② 误判为普通对话）。"""
        memory, store, conversation, registry = _setup(tmp_path)
        _register_skill(tmp_path)
        coordinator = ResearchIntakeCoordinator(store, memory, registry)
        _c, first_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, "帮我做深度研究，研究侧信道攻击"
        )
        coordinator.handle_message(conversation.conversation_id, OWNER, first_user.message_id, first_user.content)
        answer = "研究目标：生成综述，时间范围是2020-2025"
        # 这条明确是「回答 intake」的消息，意图分类必须仍为 (a)
        assert classify_intake_intent(answer) == "answer"
        _c, second_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, answer
        )
        result = coordinator.handle_message(
            conversation.conversation_id, OWNER, second_user.message_id, second_user.content
        )
        # 仍进入 intake 抽取分支，而非被误判为普通对话 (ordinary)
        assert result.status == "intake"

    def test_meta_question_not_absorbed(self, tmp_path):
        """② 元问题不喂抽取器，且不污染目标字段。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, _u, first = self._start_collecting_session(
            tmp_path, memory, store, conversation, registry, "帮我做深度研究，研究侧信道攻击"
        )
        assert first.missing and "objective" in first.missing
        _c, q_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, "有哪些研究目标能给我选"
        )
        result = coordinator.handle_message(
            conversation.conversation_id, OWNER, q_user.message_id, q_user.content
        )
        assert result.status == "ordinary"
        fields = _fields_by_name(store, first.session.intake_draft_id)
        # 目标字段不得被元问题污染
        assert "objective" not in fields or fields["objective"] in ("", [], None, "[]")

    def test_question_with_question_mark_routes_to_normal(self, tmp_path):
        """② 疑问句 + 问号走 (b)。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, _u, first = self._start_collecting_session(
            tmp_path, memory, store, conversation, registry, "帮我做深度研究，研究侧信道攻击"
        )
        _c, q_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, "研究目标应该写什么？"
        )
        result = coordinator.handle_message(
            conversation.conversation_id, OWNER, q_user.message_id, q_user.content
        )
        assert result.status == "ordinary"
        fields = _fields_by_name(store, first.session.intake_draft_id)
        assert "objective" not in fields or fields["objective"] in ("", [], None, "[]")

    def test_command_routes_to_normal(self, tmp_path):
        """② 命令（取消 / 换个主题）走 (b)。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, _u, first = self._start_collecting_session(
            tmp_path, memory, store, conversation, registry, "帮我做深度研究，研究侧信道攻击"
        )
        for cmd in ("取消", "换个主题"):
            _c, cmd_user, _a = memory.create_message_pair(conversation.conversation_id, OWNER, cmd)
            result = coordinator.handle_message(
                conversation.conversation_id, OWNER, cmd_user.message_id, cmd_user.content
            )
            assert result.status == "ordinary", cmd

    def test_completed_draft_stops_absorbing(self, tmp_path):
        """① 收齐即停：draft complete 后再来的消息不再被吸收。"""
        memory, store, conversation, registry = _setup(tmp_path)
        _register_skill(tmp_path)
        coordinator = ResearchIntakeCoordinator(store, memory, registry)
        _c, first_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, "帮我做深度研究，研究侧信道攻击"
        )
        coordinator.handle_message(conversation.conversation_id, OWNER, first_user.message_id, first_user.content)
        # 用抽取器可识别的回答收齐参数（目标是 / 时间范围）
        complete_msg = "目标是生成综述，时间范围是2020-2025"
        _c, second_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, complete_msg
        )
        completed = coordinator.handle_message(
            conversation.conversation_id, OWNER, second_user.message_id, second_user.content
        )
        assert _active_draft_status(store, completed.session) == "complete"
        objective_before = _fields_by_name(store, completed.session.intake_draft_id).get("objective")
        # complete 后再发一条「看似可吸收」的消息，也不应污染字段
        _c, after_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, "再补充一点范围"
        )
        result = coordinator.handle_message(
            conversation.conversation_id, OWNER, after_user.message_id, after_user.content
        )
        assert result.status == "ordinary"
        objective_after = _fields_by_name(store, completed.session.intake_draft_id).get("objective")
        assert objective_after == objective_before

    def test_ambiguous_defaults_to_answer(self, tmp_path):
        """⑥ 判定边界：模糊输入按默认取向（a，喂抽取器）处理。"""
        memory, store, conversation, registry = _setup(tmp_path)
        coordinator, _u, first = self._start_collecting_session(
            tmp_path, memory, store, conversation, registry, "帮我做深度研究，研究侧信道攻击"
        )
        _c, vague_user, _a = memory.create_message_pair(
            conversation.conversation_id, OWNER, "主题就用刚才那个吧"
        )
        result = coordinator.handle_message(
            conversation.conversation_id, OWNER, vague_user.message_id, vague_user.content
        )
        # 默认归为「回答 intake」→ 仍走 intake 通道（不污染字段，但不误判为普通对话）
        assert result.status == "intake"
