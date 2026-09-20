"""Spec032 Task13: carryover boundaries for IDE Skill and conversation Skill state."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.routes_conversations import _catalog_search_fallback, _resolve_sticky_skill
from backend.app.chat.application.conversation_service import stop_all_workers
from backend.app.main import app
from backend.app.memory.repository import MemoryRepository
from backend.app.skills.intent import SkillDecision
from backend.app.skills.models import SkillSummary, ToolEntry
from backend.app.skills.tool_dispatch import build_default_dispatch
from backend.app.skills.tool_executor import DispatchResult, ModelResponse, ToolLoop


class _Detail:
    def __init__(self, name: str, body: str):
        self.name = name
        self.body = body


class _Registry:
    def __init__(self, skills: list[SkillSummary], bodies: dict[str, str]):
        self.skills = skills
        self.bodies = bodies

    def list_skills(self):
        return list(self.skills)

    def get_skill(self, name: str):
        body = self.bodies.get(name)
        return _Detail(name, body) if body is not None else None


class _ToolRegistry:
    def __init__(self, tools):
        self.tools = list(tools)

    def list_tools(self):
        return list(self.tools)


def _conversation(repo: MemoryRepository, owner: str, title: str):
    project = repo.create_project(owner, title)
    return repo.create_conversation(owner, project.project_id, title=title)


def test_sticky_skill_is_conversation_and_owner_scoped(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    first = _conversation(repo, "local-user", "first")
    second = _conversation(repo, "local-user", "second")
    skill = SkillSummary("usenix-catalog-orchestration", "", ["search_paper_catalog"])
    registry = _Registry([skill], {skill.name: "product skill body"})

    matched, body = _resolve_sticky_skill(
        repo, registry, first.conversation_id, "使用 usenix-catalog-orchestration", SkillDecision("matched", skill.name, "rule")
    )
    assert matched.skill == skill.name and body == "product skill body"
    assert repo.get_conversation_active_skill(first.conversation_id, "local-user").skill_name == skill.name

    sticky, sticky_body = _resolve_sticky_skill(
        repo, registry, first.conversation_id, "就下载第一篇吧", SkillDecision("none")
    )
    assert sticky.source == "sticky" and sticky.skill == skill.name and sticky_body == "product skill body"
    assert repo.get_conversation_active_skill(second.conversation_id, "local-user") is None
    assert repo.get_conversation_active_skill(first.conversation_id, "owner-b") is None


def test_sticky_skill_switch_exit_and_disabled_cleanup(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = _conversation(repo, "local-user", "switch")
    first = SkillSummary("first-skill", "", [])
    second = SkillSummary("second-skill", "", [])
    registry = _Registry([first, second], {first.name: "first", second.name: "second"})
    _resolve_sticky_skill(repo, registry, conversation.conversation_id, "use first", SkillDecision("matched", first.name, "rule"))

    switched, switched_body = _resolve_sticky_skill(
        repo, registry, conversation.conversation_id, "use second", SkillDecision("matched", second.name, "rule")
    )
    assert switched.skill == second.name and switched_body == "second"
    assert repo.get_conversation_active_skill(conversation.conversation_id, "local-user").skill_name == second.name

    exited, exited_body = _resolve_sticky_skill(
        repo, registry, conversation.conversation_id, "结束技能，回到普通对话", SkillDecision("none")
    )
    assert exited.status == "none" and exited_body is None
    assert repo.get_conversation_active_skill(conversation.conversation_id, "local-user") is None

    repo.set_conversation_active_skill(conversation.conversation_id, "local-user", first.name)
    disabled_registry = _Registry([SkillSummary(first.name, "", [], enabled=False)], {first.name: "first"})
    fallback, fallback_body = _resolve_sticky_skill(
        repo, disabled_registry, conversation.conversation_id, "继续", SkillDecision("none")
    )
    assert fallback.status == "none" and fallback_body is None
    assert repo.get_conversation_active_skill(conversation.conversation_id, "local-user") is None


def test_catalog_search_fallback_requires_explicit_query_and_never_accepts_url():
    tool = ToolEntry(
        "search_paper_catalog", "search", True,
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["usenix", "dblp", "all"]},
                "query": {"type": "string"},
            },
            "required": ["source", "query"],
        },
    )

    assert _catalog_search_fallback(
        "使用 usenix-catalog-orchestration 搜索 AttackGNN 论文", [tool]
    ) == ("search_paper_catalog", {"source": "usenix", "query": "AttackGNN"})
    assert _catalog_search_fallback("介绍一下 USENIX Security", [tool]) is None
    assert _catalog_search_fallback("搜索 https://example.invalid/paper", [tool]) is None


def test_native_tool_then_natural_language_does_not_repeat_fallback():
    tool = ToolEntry(
        "search_paper_catalog", "search", True,
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    responses = iter([
        ModelResponse(
            content="",
            tool_calls=[{"name": "search_paper_catalog", "arguments": {"query": "AttackGNN"}}],
        ),
        ModelResponse(content="已完成检索", tool_calls=[]),
    ])
    calls = []

    def model_call(_messages, _tools):
        return next(responses)

    def dispatch(name, args):
        calls.append((name, args))
        return DispatchResult(ok=True, name=name, output="候选结果")

    events = list(ToolLoop(
        tools=[tool],
        model_call=model_call,
        dispatch=dispatch,
    ).run(
        system_prompt="SYS",
        user_question="搜索 AttackGNN",
        fallback_tool_call=("search_paper_catalog", {"query": "AttackGNN"}),
    ))

    assert calls == [("search_paper_catalog", {"query": "AttackGNN"})]
    assert {"type": "token", "content": "已完成检索"} in events


def test_ide_scripts_report_service_unavailable_without_traceback():
    root = Path(__file__).resolve().parents[2]
    scripts = (
        (root / ".codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py", ["--query", "agent", "--years", "2024"]),
        (root / ".codebuddy/skills/usenix-paper-assistant/scripts/download_paper.py", ["--search-id", "s", "--candidate-id", "c"]),
    )
    for script, args in scripts:
        result = subprocess.run(
            [sys.executable, str(script), *args, "--base-url", "http://127.0.0.1:9"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert "无法连接本地 ResearchAgent 服务" in result.stderr
        assert "127.0.0.1:9" in result.stderr
        assert "Traceback" not in result.stderr


def test_conversation_second_turn_keeps_product_skill_and_tool(tmp_path):
    """The route carries the product Skill into a second turn without IDE state."""
    repo_path = tmp_path / "conversation.sqlite3"
    skill = SkillSummary("usenix-catalog-orchestration", "", ["search_paper_catalog"])
    registry = _Registry([skill], {skill.name: "product skill body"})
    tool = ToolEntry(
        "search_paper_catalog", "search", True,
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    )

    class FakeRun:
        route = "langchain"
        result = None

        @property
        def events(self):
            yield {"type": "token", "content": "普通回答"}

    calls = []

    def dispatch(name, args):
        calls.append((name, args))
        return DispatchResult(ok=True, name=name, output="第一篇论文")

    responses = [
        ModelResponse(content="", tool_calls=[{"name": "search_paper_catalog", "arguments": {"query": "agent"}}]),
        ModelResponse(content="已找到第一篇", tool_calls=[]),
    ]

    def model_factory(*_args, **_kwargs):
        return lambda _messages, _tools: responses.pop(0)

    with patch("backend.app.memory.repository.default_database_path", return_value=repo_path), \
         patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
         patch("backend.app.api.routes_conversations.get_skill_registry", return_value=registry), \
         patch("backend.app.api.routes_conversations.get_tool_registry", side_effect=[_ToolRegistry([]), _ToolRegistry([tool])]), \
         patch("backend.app.api.routes_conversations.detect_skill", side_effect=[SkillDecision("matched", skill.name, "rule"), SkillDecision("none")]), \
         patch("backend.app.api.routes_conversations.run_chat", return_value=FakeRun()), \
         patch("backend.app.skills.tool_executor.make_model_call", side_effect=model_factory), \
         patch("backend.app.skills.tool_dispatch.build_default_dispatch", return_value=dispatch):
        client = TestClient(app)
        first = client.post("/api/conversations/messages", json={"content": "使用技能", "model": "model", "reasoning_effort": "off"})
        assert first.status_code == 200
        conversation_id = next(
            json.loads(line[6:])["conversation_id"]
            for line in first.text.split("\n\n")
            if line.startswith("data: ") and '"type": "meta"' in line
        )
        second = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "就下载第一篇吧", "model": "model", "reasoning_effort": "off"},
        )
    stop_all_workers()
    assert second.status_code == 200
    assert '"skill": "usenix-catalog-orchestration"' in second.text
    assert "已找到第一篇" in second.text
    assert calls == [("search_paper_catalog", {"query": "agent"})]


def test_sticky_download_handoff_excludes_session_search_and_keeps_duplicate_failure(tmp_path):
    repo_path = tmp_path / "download-handoff.sqlite3"
    catalog = SkillSummary(
        "usenix-catalog-orchestration", "",
        ["paper_discovery", "search_paper_catalog", "fetch_paper_detail"],
    )
    download = SkillSummary("usenix-download-orchestration", "", ["download_and_import_paper"])
    registry = _Registry(
        [catalog, download],
        {catalog.name: "catalog body", download.name: "download body"},
    )
    search_tool = ToolEntry(
        "search_paper_catalog", "search", True,
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    download_tool = ToolEntry(
        "download_and_import_paper", "download", True,
        parameters={
            "type": "object",
            "properties": {
                "candidate": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                }
            },
            "required": ["candidate"],
        },
    )
    session_tool = ToolEntry(
        "session_search", "memory", True,
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    paper_discovery_tool = ToolEntry(
        "paper_discovery", "worker", True,
        parameters={"type": "object", "properties": {}, "required": []},
    )
    detail_tool = ToolEntry(
        "fetch_paper_detail", "detail", True,
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    )
    responses = [
        # Reproduce the provider failure mode: explicit catalog intent, but
        # the first model response is ordinary prose with no tool_call.
        ModelResponse(content="我会检索 AttackGNN 论文", tool_calls=[]),
        ModelResponse(content="检索已完成", tool_calls=[]),
        ModelResponse(
            # Reproduce the second provider failure mode: sticky download
            # intent is clear, but the model only says it will call the tool.
            content="将调用 download_and_import_paper",
            tool_calls=[],
        ),
        ModelResponse(content="论文已在知识库中", tool_calls=[]),
    ]
    schemas_seen = []
    messages_seen = []
    calls = []

    def model_factory(*_args, **_kwargs):
        def call(_messages, tools):
            schemas_seen.append([item["function"]["name"] for item in (tools or [])])
            messages_seen.append([dict(item) for item in _messages])
            return responses.pop(0)

        return call

    def dispatch(name, args):
        calls.append((name, args))
        if name == "search_paper_catalog":
            return DispatchResult(
                ok=True,
                name=name,
                    output=(
                        "1. AttackGNN\n"
                        "catalog_paper_id: attack-1\n"
                        'candidate: {"title":"AttackGNN","catalog_paper_id":"attack-1",'
                        '"source_page_url":"https://www.usenix.org/conference/usenixsecurity24/presentation/attackgnn",'
                        '"source_links":["https://www.usenix.org/conference/usenixsecurity24/presentation/attackgnn"]}'
                    ),
            )
        return DispatchResult(ok=False, name=name, error="论文已在知识库中")

    with patch("backend.app.memory.repository.default_database_path", return_value=repo_path), \
         patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
         patch("backend.app.api.routes_conversations.get_skill_registry", return_value=registry), \
         patch(
             "backend.app.api.routes_conversations.get_tool_registry",
             return_value=_ToolRegistry([
                 paper_discovery_tool, search_tool, detail_tool, download_tool, session_tool,
             ]),
         ), \
         patch(
             "backend.app.api.routes_conversations.detect_skill",
             side_effect=[SkillDecision("matched", catalog.name, "rule"), SkillDecision("none")],
         ), \
         patch("backend.app.skills.tool_executor.make_model_call", side_effect=model_factory), \
         patch("backend.app.skills.tool_dispatch.build_default_dispatch", return_value=dispatch):
        client = TestClient(app)
        first = client.post(
            "/api/conversations/messages",
            json={"content": "使用 usenix-catalog-orchestration 搜索 AttackGNN 论文", "model": "model", "reasoning_effort": "off"},
        )
        assert first.status_code == 200
        conversation_id = next(
            json.loads(line[6:])["conversation_id"]
            for line in first.text.split("\n\n")
            if line.startswith("data: ") and '"type": "meta"' in line
        )
        second = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "就下载第一篇吧", "model": "model", "reasoning_effort": "off"},
        )
    stop_all_workers()

    assert second.status_code == 200
    assert '"source": "sticky"' in second.text
    assert "论文已在知识库中" in second.text
    assert calls == [
        ("search_paper_catalog", {"query": "AttackGNN"}),
        (
            "download_and_import_paper",
            {
                "candidate": {
                    "title": "AttackGNN",
                    "catalog_paper_id": "attack-1",
                    "source_page_url": "https://www.usenix.org/conference/usenixsecurity24/presentation/attackgnn",
                    "source_links": [
                        "https://www.usenix.org/conference/usenixsecurity24/presentation/attackgnn"
                    ],
                }
            },
        ),
    ]
    assert "session_search" not in schemas_seen[0]
    assert "session_search" not in schemas_seen[2]
    assert set(schemas_seen[2]) == {"search_paper_catalog", "download_and_import_paper"}
    second_model_context = "\n".join(
        str(item.get("content") or "") for item in messages_seen[2]
    )
    assert "attack-1" in second_model_context
    assert "source_links" in second_model_context


def test_download_dispatch_preserves_duplicate_candidate_failure(monkeypatch):
    from backend.app.api import common
    from backend.app.paper_discovery.application import paper_import

    monkeypatch.setattr(common, "_paper_candidate_hosts", lambda _candidate: ())
    monkeypatch.setattr(
        paper_import,
        "import_candidate",
        lambda *_args, **_kwargs: SimpleNamespace(ok=False, code="PAPER_ALREADY_EXISTS"),
    )
    monkeypatch.setattr(
        "backend.app.platform.settings.settings_repository.load_article_settings",
        lambda: SimpleNamespace(),
    )

    result = build_default_dispatch()(
        "download_and_import_paper", {"candidate": {"title": "AttackGNN"}}
    )

    assert result.ok is False
    assert result.error == "论文已在知识库中"


def test_sticky_download_recovers_candidate_from_capped_processing_summary():
    from backend.app.api.routes_conversations import _safe_catalog_candidate

    summary = (
        "检索完成：来源=USENIX Security。\n"
        'candidate: {"title":"AttackGNN","catalog_paper_id":"attack-1",'
        '"conference_id":"usenix-security","year":2024,'
        '"source_page_url":"https://www.usenix.org/conference/usenixsecurity24/presentation/attackgnn",'
        '"source_links":["https://www.u'
    )[:500]

    assert _safe_catalog_candidate(summary) == {
        "title": "AttackGNN",
        "catalog_paper_id": "attack-1",
        "conference_id": "usenix-security",
        "year": 2024,
        "source_page_url": "https://www.usenix.org/conference/usenixsecurity24/presentation/attackgnn",
    }
