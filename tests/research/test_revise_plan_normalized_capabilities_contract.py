"""Regression contract: ``revise_plan`` on a persisted normalized capability snapshot.

Two independent pre-existing defects made every ``revise_plan`` fail as soon as a
plan carried registry-normalized capabilities (the production default):

1. ``plan_authoring._walk_safe`` capped nesting at 6, but a persisted
   ``capabilities[].tools[].parameters.properties.limit`` snapshot reaches
   depth 7..11 (measured max with the real ``build_default_tool_registry`` is 11).
   ``_revise_plan`` falls the untouched capabilities back to that snapshot and
   re-validates the *whole* plan, so the depth guard rejected even a scope that
   contained only ``safe_summary`` (depth <= 3).
2. ``approval_service._normalize_capabilities`` was not re-entrant: the
   fallback snapshot uses ``{"skill": <dict>, "tools": [dict, ...]}`` while the
   function only accepted ``{"skill": <str>, "tools": [str, ...]}``.

Fix contract: legal normalized plans pass; ``revise_plan`` writes back the
requested field; unknown capability names are still refused; pathological
nesting (50 levels) is still rejected by the depth guard.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.app.research.application.approval_service import (
    PlanApprovalService,
    ResearchCommandError,
)
from backend.app.research.application.plan_authoring import (
    PlanOutputInvalid,
    plan_output_hash,
    validate_research_plan_output,
    validate_safe_scope,
)
from tests.research.test_research_plan_approval_contract import OWNER, _output, _setup

PYTHON_FQN = (
    "backend.app.paper_discovery.application.paper_discovery_search."
    "PaperDiscoverySearchService.search"
)
TOOL_NAME = "paper_discovery"
SKILL_NAME = "paper-discovery"
# Mirrors the deepest real JSON-Schema in build_default_tool_registry():
# parameters.properties.candidate.properties.source_links.items (depth 11).
PARAMETERS = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "query": {"type": "string"},
        "candidate": {
            "type": "object",
            "properties": {
                "source_links": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "required": ["query"],
}


def _registries():
    skill = SimpleNamespace(name=SKILL_NAME, body="safe", tools=[TOOL_NAME], enabled=True)
    tool = SimpleNamespace(name=TOOL_NAME, enabled=True, entry=PYTHON_FQN, parameters=PARAMETERS)
    return (
        SimpleNamespace(get_skill=lambda name: skill if name == SKILL_NAME else None),
        SimpleNamespace(get_tool=lambda name: tool if name == TOOL_NAME else None),
    )


def _normalized_snapshot():
    """The exact shape persisted by ``_normalize_capabilities`` (tools=list[dict])."""
    return {
        "skill": {
            "name": SKILL_NAME, "version": "1", "schema_version": "1",
            "content_hash": "a" * 64, "enabled": True, "source_ref": SKILL_NAME,
            "tools": [TOOL_NAME],
        },
        "tools": [{
            "name": TOOL_NAME, "version": "1", "parameters_hash": "b" * 64,
            "content_hash": "b" * 64, "source_ref": PYTHON_FQN,
            "parameters": PARAMETERS, "enabled": True,
            "side_effect_class": "read_only", "entry": PYTHON_FQN,
        }],
    }


def _nesting_depth(value, depth=0):
    best = depth
    if isinstance(value, dict):
        for child in value.values():
            best = max(best, _nesting_depth(child, depth + 1))
    elif isinstance(value, list):
        for child in value:
            best = max(best, _nesting_depth(child, depth + 1))
    return best


def _service(tmp_path):
    memory, store, session = _setup(tmp_path)
    skills, tools = _registries()
    service = PlanApprovalService(
        store=store, memory_repository=memory,
        skill_registry=skills, tool_registry=tools,
    )
    return memory, store, session, service


def _plan(store, session, version):
    return store.get_session_plan(session.research_session_id, OWNER, version)


def _author_v1_with_deep_capabilities(store, session, service):
    output = _output(version=1)
    output["capabilities"] = [{"skill": SKILL_NAME, "tools": [TOOL_NAME]}]
    output["output_hash"] = plan_output_hash(output)
    service.author_plan(session.research_session_id, OWNER, output)
    return _plan(store, session, 1)


def test_v1_persists_deep_normalized_capability_snapshot(tmp_path):
    """夹具自检：确保测试确实构造了深层归一化快照，避免断言静默失效。"""
    _memory, store, session, service = _service(tmp_path)
    v1 = _author_v1_with_deep_capabilities(store, session, service)
    caps = json.loads(v1.capabilities_json)
    assert isinstance(caps[0]["skill"], dict)
    assert caps[0]["tools"][0]["name"] == TOOL_NAME  # tools 为 list[dict]
    assert "limit" in caps[0]["tools"][0]["parameters"]["properties"]
    assert _nesting_depth({"capabilities": caps}) >= 11


def test_legal_normalized_plan_passes_full_validation(tmp_path):
    """depth 修复：合法归一化 plan 不再被 depth_limit 误杀（与 normalize 修复解耦）。"""
    _memory, store, session, service = _service(tmp_path)
    v1 = _author_v1_with_deep_capabilities(store, session, service)
    revised = {
        "schema_version": v1.schema_version, "plan_version": 2,
        "objective": v1.objective,
        "scope": json.loads(v1.scope_json),
        "work_items": json.loads(v1.work_items_json),
        "capabilities": json.loads(v1.capabilities_json),
        "budget": json.loads(v1.budget_json),
        "report_structure": json.loads(v1.report_structure_json),
        "safe_summary": json.loads(v1.safety_summary_json),
        "source_refs": [],
    }
    revised["output_hash"] = plan_output_hash(revised)
    normalized = validate_research_plan_output(revised)
    assert normalized["plan_version"] == 2
    assert normalized["capabilities"][0]["tools"][0]["parameters"]["properties"]["limit"] == PARAMETERS["properties"]["limit"]


def test_revise_plan_budget_only_on_deep_capabilities(tmp_path):
    """端到端：仅改 budget，revise_plan 成功写回，capabilities/safe_summary/objective 不变。"""
    _memory, store, session, service = _service(tmp_path)
    v1 = _author_v1_with_deep_capabilities(store, session, service)
    old_caps = json.loads(v1.capabilities_json)
    old_summary = json.loads(v1.safety_summary_json)
    new_budget = {
        "quality_profile": "fast", "target_paper_count": 3,
        "soft_budget_seconds": 900, "language": "zh",
    }
    try:
        service.command(
            session.research_session_id, OWNER,
            command="revise_plan", subject_version=1,
            scope_json={"budget": new_budget},
            idempotency_key="revise-budget-deep-caps",
        )
    except ResearchCommandError as exc:
        pytest.fail(f"revise_plan(budget) 不应被拒：{exc.code} / {exc.message}")

    assert store.get_session(session.research_session_id, OWNER).current_plan_version == 2
    v2 = _plan(store, session, 2)
    assert v2 is not None
    budget = json.loads(v2.budget_json)
    assert budget["target_paper_count"] == 3
    assert budget["quality_profile"] == "fast"
    assert budget["soft_budget_seconds"] == 900
    assert json.loads(v2.capabilities_json) == old_caps
    assert json.loads(v2.safety_summary_json) == old_summary
    assert v2.objective == v1.objective


def test_revise_plan_safe_summary_only_on_deep_capabilities(tmp_path):
    """端到端：scope 仅 1 个键 safe_summary（用户实测场景），必须成功写回。"""
    _memory, store, session, service = _service(tmp_path)
    v1 = _author_v1_with_deep_capabilities(store, session, service)
    old_caps = json.loads(v1.capabilities_json)
    new_summary = {
        "decision": "任何来源降级立即暂停并提示用户确认后再继续",
        "notes": "来源降级先暂停，等待用户确认。",
        "constraints": ["不扩大检索范围"],
        "degraded": [],
    }
    try:
        service.command(
            session.research_session_id, OWNER,
            command="revise_plan", subject_version=1,
            scope_json={"safe_summary": new_summary},
            idempotency_key="revise-summary-deep-caps",
        )
    except ResearchCommandError as exc:
        pytest.fail(f"revise_plan(safe_summary) 不应被拒：{exc.code} / {exc.message}")

    v2 = _plan(store, session, 2)
    assert json.loads(v2.safety_summary_json) == new_summary
    assert json.loads(v2.capabilities_json) == old_caps
    assert json.loads(v2.budget_json) == json.loads(v1.budget_json)


def test_normalize_capabilities_is_reentrant_for_tool_snapshots(tmp_path):
    """重入：tools 为 list[dict] 时不抛 CAPABILITY_NOT_AUTHORIZED，结果仍是合法快照。"""
    _memory, store, _session, service = _service(tmp_path)
    snapshot = _normalized_snapshot()
    for tools in (
        snapshot["tools"],                                   # 完整持久化快照
        [{"name": TOOL_NAME, "entry": PYTHON_FQN}],           # 简化 dict（仅 name/entry）
    ):
        result = service._normalize_capabilities([{"skill": snapshot["skill"], "tools": tools}])
        assert len(result) == 1
        assert result[0]["skill"]["name"] == SKILL_NAME
        tool = result[0]["tools"][0]
        assert tool["name"] == TOOL_NAME
        assert tool["entry"] == PYTHON_FQN
        assert tool["parameters"] == PARAMETERS
        assert tool["parameters_hash"]


def test_normalize_capabilities_still_rejects_unregistered_names(tmp_path):
    """回归防护：真实未注册的能力名字符串仍必须被拒，修复不得削弱授权。"""
    _memory, store, _session, service = _service(tmp_path)
    with pytest.raises(ResearchCommandError) as unknown_skill:
        service._normalize_capabilities([{"skill": "missing-skill", "tools": ["missing-tool"]}])
    assert unknown_skill.value.code == "CAPABILITY_NOT_AUTHORIZED"
    with pytest.raises(ResearchCommandError) as unknown_tool:
        service._normalize_capabilities([{"skill": SKILL_NAME, "tools": ["missing-tool"]}])
    assert unknown_tool.value.code == "CAPABILITY_NOT_AUTHORIZED"


def _deep_nested(levels):
    root = {}
    current = root
    for _ in range(levels):
        current["level"] = {}
        current = current["level"]
    return root


def test_pathologically_nested_plan_is_still_rejected_by_depth_guard():
    """回归防护：50 层嵌套 plan 仍被拒，且明确由 depth 护栏（非别的错误）拦截。"""
    output = _output(version=1)
    output["capabilities"] = [{"skill": "s", "tools": [{"parameters": _deep_nested(50)}]}]
    output["output_hash"] = plan_output_hash(output)
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(output)
    assert exc.value.safety_classification == "depth_limit"


def test_pathologically_nested_scope_is_still_rejected_by_depth_guard():
    """回归防护：command scope 入口（validate_safe_scope）同样保留 depth 上限。"""
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_safe_scope({"capabilities": [_deep_nested(50)]})
    assert exc.value.safety_classification == "depth_limit"
