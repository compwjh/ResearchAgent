"""Spec-043 第 7 项（Bug 修复，默认 A+B）：单篇全文 RAG 提问被误判为深度研究。

覆盖边界（每条对应 spec 验收）：
  ① A（结构化）：单篇论文会话（文献地图绑定）恒定走普通 RAG，跳过
     deep-research Intake 激活；
  ② B（文本兜底）：ResearchIntakeCoordinator.classify() 增加单篇负向特征，
     并收紧过宽的「研究/分析」动词正则，避免名词短语（研究问题/研究目标）误判；
  ③ 普通会话显式深度研究、开放式请求行为不变（现有 test_research_intake_intent_routing 硬门槛）；
  ④ binding 读取失败 fail-closed：单篇会话绝不静默降级为项目级检索、不泄露其它论文。

测试原则：用真实 ResearchIntakeCoordinator.classify() + 真实 _read_map_conversation_binding
读取 seam（含真实 literature_maps store 落盘 confirmed binding），不 mock 掉被修复的
判定函数冒充通过。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.app.api import routes_conversations
from backend.app.api.routes_conversations import _is_single_paper_conversation
from backend.app.api.schemas import ConversationMessageRequest
from backend.app.literature_maps.domain.analysis import MapConversationBinding
from backend.app.memory.repository import MemoryRepository, OWNER_ID
from backend.app.research.application.intake import ResearchIntakeCoordinator


# 复现 spec043 截图里的「关于本篇提问」完整草稿（含后续追加的「使用RAG的模式」）
SINGLE_PAPER_DRAFT = (
    "请帮我解读这篇论文。/ 标题：Graph Attention Networks / 作者：… / 年份：2017 "
    "/ 请重点回答：研究问题、方法、主要结论和局限。/ 证据等级：全文索引片段依据"
)
SINGLE_PAPER_DRAFT_WITH_RAG = SINGLE_PAPER_DRAFT + " 使用RAG的模式"


def _real_binding(conversation_id: str, evidence_level: str = "full") -> MapConversationBinding:
    return MapConversationBinding(
        binding_id="bind-1",
        owner_id=OWNER_ID,
        map_id="map-1",
        node_id="node-1",
        conversation_id=conversation_id,
        project_id_snapshot=None,
        evidence_level=evidence_level,
        source_version="v1",
        context={"title": "Graph Attention Networks"},
        status="confirmed",
        idempotency_key="idem-1",
    )


# ---------------------------------------------------------------------------
# B：ResearchIntakeCoordinator.classify() 单篇负向特征 + 收紧动词正则（真实分类器）
# ---------------------------------------------------------------------------
class TestClassifySinglePaperMarkers:
    def test_draft_with_research_noun_and_rag_is_ordinary(self):
        # 边界 1/3：完整草稿含「研究问题」「证据等级」「全文索引片段」「使用RAG」
        # → 归 ordinary，不激活 Intake（B 文本兜底）。
        assert ResearchIntakeCoordinator.classify(SINGLE_PAPER_DRAFT) == "ordinary"
        assert ResearchIntakeCoordinator.classify(SINGLE_PAPER_DRAFT_WITH_RAG) == "ordinary"

    def test_explicit_single_paper_markers_ordinary(self):
        # 边界 3：普通会话里粘贴单篇解读标记 → ordinary。
        for text in ("请帮我解读这篇论文", "基于全文分析", "使用rag", "关于本篇我们聊聊"):
            assert ResearchIntakeCoordinator.classify(text) == "ordinary", text

    def test_explicit_deep_research_unchanged(self):
        # 边界 2：普通会话显式深度研究行为完全不变（含「深度研究」子串）。
        assert ResearchIntakeCoordinator.classify("帮我做深度研究，研究侧信道攻击") == "explicit"
        assert ResearchIntakeCoordinator.classify("请做一份深度研究报告") == "explicit"
        assert ResearchIntakeCoordinator.classify("do a deep research on X") == "explicit"

    def test_open_research_request_still_explicit(self):
        # 边界 4：开放式请求仍可判 explicit，不被负向规则过度抑制。
        for text in (
            "帮我分析一下这个领域的研究现状",
            "请帮我研究下最近的检索增强生成进展",
            "帮我分析 Transformer 的发展脉络",
        ):
            assert ResearchIntakeCoordinator.classify(text) == "explicit", text

    def test_research_noun_phrase_not_explicit(self):
        # 收紧正则：研究/分析 作名词（研究问题/研究目标）不触发 explicit。
        for text in (
            "请列出本文的研究问题",
            "这篇综述的研究目标是什么",
            "帮我整理一下研究方法的分类",
        ):
            assert ResearchIntakeCoordinator.classify(text) != "explicit", text

    def test_ambiguous_and_ordinary_untouched(self):
        # 其它分支不受影响。
        assert ResearchIntakeCoordinator.classify("查一下侧信道攻击的论文") == "ambiguous"
        assert ResearchIntakeCoordinator.classify("你好") == "ordinary"


# ---------------------------------------------------------------------------
# A：单篇会话路由判定（真实 _is_single_paper_conversation + 真实 binding 读取 seam）
# ---------------------------------------------------------------------------
class TestSinglePaperRoutingDecision:
    def test_bound_conversation_is_single_paper(self, monkeypatch):
        binding = _real_binding("conv-bound")
        monkeypatch.setattr(
            routes_conversations, "_read_map_conversation_binding",
            lambda cid, oid: (binding, None),
        )
        assert _is_single_paper_conversation("conv-bound") is True

    def test_unbound_conversation_not_single_paper(self, monkeypatch):
        monkeypatch.setattr(
            routes_conversations, "_read_map_conversation_binding",
            lambda cid, oid: (None, None),
        )
        assert _is_single_paper_conversation("conv-unbound") is False

    def test_binding_read_failure_is_fail_closed(self, monkeypatch):
        # 边界 4/5：binding 读取失败时按 fail-closed 视为单篇会话，
        # 绝不静默放宽去激活 Intake。
        monkeypatch.setattr(
            routes_conversations, "_read_map_conversation_binding",
            lambda cid, oid: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert _is_single_paper_conversation("conv-fail") is True

    def test_none_conversation_id_not_single_paper(self):
        # 全新会话（无 conversation_id）不触发短路。
        assert _is_single_paper_conversation(None) is False

    def test_abstract_binding_also_routes_to_rag(self, monkeypatch):
        # 边界 5：evidence_level='abstract' 同样不触发 Intake（按绑定存在判定）。
        binding = _real_binding("conv-abstract", evidence_level="abstract")
        monkeypatch.setattr(
            routes_conversations, "_read_map_conversation_binding",
            lambda cid, oid: (binding, None),
        )
        assert _is_single_paper_conversation("conv-abstract") is True


# ---------------------------------------------------------------------------
# A：真实 literature_maps store 落盘 confirmed binding，验证真实 _read_map_conversation_binding
# ---------------------------------------------------------------------------
class TestSinglePaperRoutingRealStore:
    def test_real_binding_read_and_routing(self, tmp_path, monkeypatch):
        from backend.app.literature_maps.application.runtime import (
            default_database_path as _orig_ddp,
        )
        from backend.app.literature_maps.application.runtime import (
            read_map_conversation_binding,
        )
        from backend.app.literature_maps.infrastructure.store import LiteratureMapStore

        db_path = tmp_path / "maps.sqlite3"
        store = LiteratureMapStore(db_path)
        conv_id = "conv-real-bound"
        with store.connection() as db:
            db.execute(
                "INSERT INTO literature_map_conversation_bindings("
                "binding_id,owner_id,map_id,node_id,conversation_id,project_id_snapshot,"
                "evidence_level,source_version,context_json,status,idempotency_key,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "binding-real", OWNER_ID, "map-1", "node-1", conv_id, None,
                    "full", "v1", "{}", "confirmed", "idem-real",
                    "2026-11-06T00:00:00Z", "2026-11-06T00:00:00Z",
                ),
            )

        monkeypatch.setattr(
            "backend.app.literature_maps.application.runtime.default_database_path",
            lambda: db_path,
        )
        # 真实读取 seam
        binding, _service = read_map_conversation_binding(conv_id, OWNER_ID)
        assert binding is not None
        assert binding.conversation_id == conv_id
        # 真实路由判定
        assert _is_single_paper_conversation(conv_id) is True
        # 其它会话仍判定为普通
        assert _is_single_paper_conversation("conv-real-unbound") is False


# ---------------------------------------------------------------------------
# A 集成：真实 _start_message 路由 —— 单篇会话不调用 Intake handle_message
# ---------------------------------------------------------------------------
class TestStartMessageSinglePaperShortCircuit:
    def _fake_resolution(self):
        class _Caps:
            source = "cache"
        class _Resolution:
            effort = "medium"
            capabilities = _Caps()
        return _Resolution()

    def test_single_paper_skips_intake(self, tmp_path, monkeypatch):
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        conversation = repo.create_conversation(OWNER_ID, None)
        binding = _real_binding(conversation.conversation_id)

        recorded = MagicMock()
        recorded.handle_message.return_value = MagicMock(status="intake")
        monkeypatch.setattr(routes_conversations, "_repo", lambda: repo)
        monkeypatch.setattr(routes_conversations, "_validate_model", lambda model: None)
        monkeypatch.setattr(
            routes_conversations, "_resolve_request_effort",
            lambda *a, **k: self._fake_resolution(),
        )
        monkeypatch.setattr(routes_conversations, "get_provider", lambda name: recorded)
        monkeypatch.setattr(routes_conversations, "get_memory_analysis_worker", lambda r: MagicMock(enqueue=lambda j: None))
        monkeypatch.setattr(routes_conversations, "get_memory_evolution_worker", lambda r: None)
        monkeypatch.setattr(
            routes_conversations, "_read_map_conversation_binding",
            lambda cid, oid: (binding, None),
        )

        async def _noop():
            return
            yield  # pragma: no cover

        monkeypatch.setattr(routes_conversations, "_message_stream", lambda *a, **k: _noop())
        monkeypatch.setattr(routes_conversations, "_intake_stream", lambda *a, **k: _noop())

        payload = ConversationMessageRequest(content=SINGLE_PAPER_DRAFT_WITH_RAG)
        routes_conversations._start_message(payload, conversation.conversation_id)
        # 单篇会话：绝不调用 Intake 激活
        recorded.handle_message.assert_not_called()

    def test_normal_conversation_activates_intake(self, tmp_path, monkeypatch):
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        conversation = repo.create_conversation(OWNER_ID, None)

        recorded = MagicMock()
        recorded.handle_message.return_value = MagicMock(status="intake")
        monkeypatch.setattr(routes_conversations, "_repo", lambda: repo)
        monkeypatch.setattr(routes_conversations, "_validate_model", lambda model: None)
        monkeypatch.setattr(
            routes_conversations, "_resolve_request_effort",
            lambda *a, **k: self._fake_resolution(),
        )
        monkeypatch.setattr(routes_conversations, "get_provider", lambda name: recorded)
        monkeypatch.setattr(routes_conversations, "get_memory_analysis_worker", lambda r: MagicMock(enqueue=lambda j: None))
        monkeypatch.setattr(routes_conversations, "get_memory_evolution_worker", lambda r: None)
        # 普通会话：无绑定
        monkeypatch.setattr(
            routes_conversations, "_read_map_conversation_binding",
            lambda cid, oid: (None, None),
        )

        async def _noop():
            return
            yield  # pragma: no cover

        monkeypatch.setattr(routes_conversations, "_message_stream", lambda *a, **k: _noop())
        monkeypatch.setattr(routes_conversations, "_intake_stream", lambda *a, **k: _noop())

        payload = ConversationMessageRequest(content="帮我做深度研究，研究侧信道攻击")
        routes_conversations._start_message(payload, conversation.conversation_id)
        # 普通会话：显式深度研究仍走 Intake 激活（行为不变）
        recorded.handle_message.assert_called_once()
