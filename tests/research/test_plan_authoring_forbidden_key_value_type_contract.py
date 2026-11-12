"""Regression contract: forbidden field names must not kill structured values.

4th backend blocker of the "research parameter recommendation write-back" flow:
``plan_authoring._walk_safe`` rejected any dict key whose name hit
``_FORBIDDEN_KEYS`` (or contained ``url``) **regardless of the value type**.  A
registry-normalized capability snapshot legitimately keeps a JSON-Schema
parameter definition under that exact name -- ``fetch_paper_detail`` stores::

    capabilities[].tools[].parameters.properties.url = {
        "type": "string", "description": "..."
    }

``revise_plan`` falls untouched capabilities back to that persisted snapshot
and re-validates the whole plan, so every session carrying the real
``fetch_paper_detail`` tool failed with ``AGENT_OUTPUT_INVALID / reasoning
fields are not allowed`` (previously masked by the stricter depth cap).

Fix contract: the key-name ban applies only when the value is a *string* (the
"hide a URL inside a field called url" shape).  Structured / non-string values
are walked recursively instead of being rejected, so nested strings are still
checked by ``_URL_RE`` and the credential markers.  Real URL strings and all
other forbidden-key strings remain rejected.
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
)
from backend.app.skills.registry import build_default_tool_registry
from tests.research.test_research_plan_approval_contract import OWNER, _output, _setup

SKILL_NAME = "paper-research"
REAL_TOOLS = build_default_tool_registry()
TOOL_BY_NAME = {tool.name: tool for tool in REAL_TOOLS}
TOOL_NAMES = [tool.name for tool in REAL_TOOLS]
FETCH_PAPER_DETAIL_PARAMETERS = TOOL_BY_NAME["fetch_paper_detail"].parameters

# Shaped exactly like registry.py:140-152 properties.url -- a *dict* holding a
# JSON-Schema parameter definition, never a URL string.  Kept URL-free so the
# pure key-name regression is isolated from the independent _URL_RE guard.
URL_PARAMETER_DEFINITION = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "USENIX 官方详情页地址（来自目录检索结果）"},
    },
    "required": ["url"],
}


def _plan_with_capabilities(capabilities, *, version=1):
    output = _output(version=version)
    output["capabilities"] = capabilities
    output["output_hash"] = plan_output_hash(output)
    return output


def _one_tool_capability(parameters):
    return [{"skill": SKILL_NAME, "tools": [{"name": "fetch_paper_detail", "parameters": parameters}]}]


# --- 负向：结构化 / 非字符串值不得被键名禁令误杀（修复前 forbidden_key） ---


def test_url_parameter_definition_dict_is_not_rejected_by_key_name():
    """修复前抛 forbidden_key，修复后放行且参数定义原样保留。"""
    output = _plan_with_capabilities(_one_tool_capability(URL_PARAMETER_DEFINITION))
    normalized = validate_research_plan_output(output)
    url_def = normalized["capabilities"][0]["tools"][0]["parameters"]["properties"]["url"]
    assert url_def == URL_PARAMETER_DEFINITION["properties"]["url"]


def test_real_fetch_paper_detail_parameters_are_allowed():
    """直接取真实 registry 的 fetch_paper_detail.parameters（含 properties.url dict）。"""
    normalized = validate_research_plan_output(
        _plan_with_capabilities(_one_tool_capability(FETCH_PAPER_DETAIL_PARAMETERS))
    )
    assert normalized["capabilities"][0]["tools"][0]["parameters"] == FETCH_PAPER_DETAIL_PARAMETERS


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("url", {"type": "string"}),
        ("article_url", [{"type": "string"}]),
        ("url", 7),
        ("url", None),
    ],
)
def test_non_string_values_under_url_like_keys_are_walked_not_banned(key, value):
    """dict / list / int / None 值均不得因键名被拒（只有字符串值才禁）。"""
    parameters = {"type": "object", "properties": {key: value}, "required": []}
    normalized = validate_research_plan_output(
        _plan_with_capabilities(_one_tool_capability(parameters))
    )
    assert normalized["capabilities"][0]["tools"][0]["parameters"]["properties"][key] == value


# --- 正向：护栏仍生效 ---


def test_string_url_in_url_field_is_still_rejected():
    """字符串值 URL 藏在 url 字段仍被拒（forbidden_key 或 url_value 皆可），且不回显原文。"""
    output = _plan_with_capabilities(
        [{"skill": SKILL_NAME, "tools": [{"name": "t", "url": "http://evil.example.com/phish"}]}]
    )
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(output)
    assert exc.value.code == "AGENT_OUTPUT_INVALID"
    assert exc.value.safety_classification in {"forbidden_key", "url_value"}
    assert "evil.example.com" not in str(exc.value)


def test_non_url_string_in_url_field_is_still_banned_by_key_name():
    """补盲拦截：值不是标准 URL，但藏在名为 url 的字符串字段里仍须拒绝。"""
    output = _plan_with_capabilities(
        [{"skill": SKILL_NAME, "tools": [{"name": "t", "url": "不是网址但仍禁止"}]}]
    )
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(output)
    assert exc.value.safety_classification == "forbidden_key"


def test_url_string_in_non_url_field_is_still_rejected_by_url_re():
    """_URL_RE 独立于键名禁令生效（修复不得触碰该正则）。"""
    output = _output()
    output["safe_summary"] = {"notes": "http://evil.example.com/phish"}
    output["output_hash"] = plan_output_hash(output)
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(output)
    assert exc.value.safety_classification == "url_value"


def test_url_string_hidden_inside_parameter_definition_is_still_rejected():
    """放行结构化值 ≠ 开洞：递归到内部字符串时仍被 _URL_RE 拦（url_value）。"""
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "https://evil.example.com/phish"}},
        "required": ["url"],
    }
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(_plan_with_capabilities(_one_tool_capability(parameters)))
    assert exc.value.safety_classification == "url_value"


# --- 端到端：完整真实 capabilities 快照下的 revise_plan 无回归 ---


def _real_registries():
    """用真实 build_default_tool_registry() 的 ToolEntry 装配 name->tool 查表。"""
    skill = SimpleNamespace(name=SKILL_NAME, body="safe", tools=list(TOOL_NAMES), enabled=True)
    return (
        SimpleNamespace(get_skill=lambda name: skill if name == SKILL_NAME else None),
        SimpleNamespace(get_tool=lambda name: TOOL_BY_NAME.get(name)),
    )


def _service(tmp_path):
    memory, store, session = _setup(tmp_path)
    skills, tools = _real_registries()
    service = PlanApprovalService(
        store=store, memory_repository=memory,
        skill_registry=skills, tool_registry=tools,
    )
    return store, session, service


def _plan(store, session, version):
    return store.get_session_plan(session.research_session_id, OWNER, version)


def _author_v1_with_full_real_capabilities(store, session, service):
    output = _output(version=1)
    output["capabilities"] = [{"skill": SKILL_NAME, "tools": list(TOOL_NAMES)}]
    output["output_hash"] = plan_output_hash(output)
    service.author_plan(session.research_session_id, OWNER, output)
    return _plan(store, session, 1)


def test_v1_persists_real_url_parameter_definition(tmp_path):
    """夹具自检：v1 落库快照确实含 properties.url dict 与全部 7 个 Tool（防静默失效）。"""
    store, session, service = _service(tmp_path)
    v1 = _author_v1_with_full_real_capabilities(store, session, service)
    caps = json.loads(v1.capabilities_json)
    persisted_tools = caps[0]["tools"]
    assert {tool["name"] for tool in persisted_tools} == set(TOOL_NAMES)
    fetch = next(tool for tool in persisted_tools if tool["name"] == "fetch_paper_detail")
    url_def = fetch["parameters"]["properties"]["url"]
    assert isinstance(url_def, dict) and url_def["type"] == "string"
    assert fetch["parameters"] == FETCH_PAPER_DETAIL_PARAMETERS


def test_revise_plan_budget_only_with_full_real_capabilities(tmp_path):
    """端到端：仅改 budget 成功写回，不再 reasoning fields / nesting limit。"""
    store, session, service = _service(tmp_path)
    v1 = _author_v1_with_full_real_capabilities(store, session, service)
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
            idempotency_key="revise-budget-full-real-caps",
        )
    except ResearchCommandError as exc:
        pytest.fail(f"revise_plan(budget) 不应被拒：{exc.code} / {exc.message}")

    assert store.get_session(session.research_session_id, OWNER).current_plan_version == 2
    v2 = _plan(store, session, 2)
    assert v2 is not None
    assert json.loads(v2.budget_json)["target_paper_count"] == 3
    assert json.loads(v2.capabilities_json) == old_caps
    assert json.loads(v2.safety_summary_json) == old_summary


def test_revise_plan_safe_summary_only_with_full_real_capabilities(tmp_path):
    """端到端：仅改 safe_summary 成功写回，capabilities 幂等保持。"""
    store, session, service = _service(tmp_path)
    v1 = _author_v1_with_full_real_capabilities(store, session, service)
    old_caps = json.loads(v1.capabilities_json)
    new_summary = {
        "decision": "来源降级先暂停并等待用户确认",
        "notes": "不扩大检索范围。",
        "constraints": ["不访问外部网络"],
        "degraded": [],
    }
    try:
        service.command(
            session.research_session_id, OWNER,
            command="revise_plan", subject_version=1,
            scope_json={"safe_summary": new_summary},
            idempotency_key="revise-summary-full-real-caps",
        )
    except ResearchCommandError as exc:
        pytest.fail(f"revise_plan(safe_summary) 不应被拒：{exc.code} / {exc.message}")

    v2 = _plan(store, session, 2)
    assert json.loads(v2.safety_summary_json) == new_summary
    assert json.loads(v2.capabilities_json) == old_caps
