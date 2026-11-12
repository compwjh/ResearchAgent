"""Regression contract: plan-safety URL detection must not reject Python FQNs.

``_URL_RE``'s bare-domain branch used to match the tail of a Python fully
qualified name (``...PaperDiscoverySearchService.search`` read as ``label.TLD``),
so ``author_plan``/``revise_plan`` rejected otherwise valid plans with
``AGENT_OUTPUT_INVALID`` / ``url_value``.

The fix keeps every real URL blocked (scheme, www, localhost, bare domain,
bare domain + path, URL embedded in prose) while leaving structured
identifiers alone -- and without turning structured field names into a URL
bypass (hence no field-name exemption).
"""

from __future__ import annotations

import pytest

from backend.app.research.application.plan_authoring import (
    PlanOutputInvalid,
    plan_output_hash,
    validate_research_plan_output,
    validate_safe_scope,
)
from tests.research.test_research_plan_approval_contract import _output

PYTHON_FQN = (
    "backend.app.paper_discovery.application.paper_discovery_search."
    "PaperDiscoverySearchService.search"
)


def _plan_with_tool(**overrides):
    tool = {
        "name": "paper_discovery_search",
        "entry": PYTHON_FQN,
        "source_ref": PYTHON_FQN,
    }
    tool.update(overrides)
    output = _output()
    output["capabilities"] = [{"skill": "paper-discovery", "tools": [tool]}]
    output["output_hash"] = plan_output_hash(output)
    return output


def test_python_fqn_in_capability_tool_refs_is_not_classified_as_url():
    """负向：修复前抛 url_value，修复后返回规范化 plan 且标识符原样保留。"""
    normalized = validate_research_plan_output(_plan_with_tool())
    tool = normalized["capabilities"][0]["tools"][0]
    assert tool["source_ref"] == PYTHON_FQN
    assert tool["entry"] == PYTHON_FQN


@pytest.mark.parametrize(
    "fqn",
    [
        PYTHON_FQN,
        "backend.app.paper_discovery.application.paper_discovery_search.PaperDiscoverySearchService",
        "backend.app.research.application.plan_authoring.validate_research_plan_output",
    ],
)
def test_python_fqn_in_command_scope_is_not_classified_as_url(fqn):
    """负向：command scope 路径（validate_safe_scope）同样不得误杀 FQN。"""
    validate_safe_scope({"source_ref": fqn, "entry": fqn, "skill": fqn})
    # 对照：同一入口对真实 URL 必须仍拒绝，避免「不抛即通过」的恒真断言。
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_safe_scope({"source_ref": "https://evil.example.com/phish"})
    assert exc.value.safety_classification == "url_value"


@pytest.mark.parametrize(
    "fqn",
    [
        "backend.catalog.search",
        "some.module.Service.run",
        "backend.app.research.application.plan_authoring.validate_safe_scope",
    ],
)
def test_short_dotted_python_identifiers_are_not_bare_domains(fqn):
    """负向：纯点分短标识符也不得被裸域名分支读成 ``label.TLD``。"""
    output = _plan_with_tool(source_ref=fqn, entry=fqn)
    normalized = validate_research_plan_output(output)
    tool = normalized["capabilities"][0]["tools"][0]
    assert tool["source_ref"] == fqn
    assert tool["entry"] == fqn


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "https://evil.example.com/phish",
        "http://evil.example.com/phish",
        "ftp://evil.example.com/x",
        "www.example.com/path",
        "localhost:8080/admin",
        "example.com/path",
        "evil.example",
        "see example https://evil.example",
    ],
)
def test_real_urls_are_still_rejected(unsafe_value):
    """正向：收紧正则后，真实 URL 仍被 url_value 拦截。"""
    output = _output()
    output["safe_summary"] = {"notes": unsafe_value}
    output["output_hash"] = plan_output_hash(output)
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(output)
    assert exc.value.safety_classification == "url_value"


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "https://evil.example.com/phish",
        "www.example.com/path",
        "example.com/path",
        "evil.example",
    ],
)
def test_real_url_in_structured_tool_field_is_still_rejected(unsafe_value):
    """正向：结构化字段名不是 URL 绕过点（不采用字段名豁免的护栏）。"""
    output = _plan_with_tool(source_ref=unsafe_value)
    with pytest.raises(PlanOutputInvalid) as exc:
        validate_research_plan_output(output)
    assert exc.value.safety_classification == "url_value"
