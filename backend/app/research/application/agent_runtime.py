"""Spec034 Task05: the bounded ResearchAgentRunner runtime contract.

This module is deliberately a small application-layer adapter.  Model calls are
injected (the production adapter is supplied by the existing Ollama platform
module), and tool execution is injected through the existing Spec023 executor.
It owns neither a model client nor a second registry.
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field, replace
from threading import Event
from typing import Any, Callable, Mapping, Sequence

from backend.app.research.application.plan_authoring import PlanOutputInvalid, validate_safe_scope
from backend.app.research.domain.contracts import AGENT_ROLES
from backend.app.research.domain.models import AgentCheckpoint, AgentRun, ResearchEvent
from backend.app.research.domain.state_machine import InvalidStateTransition
from backend.app.research.infrastructure.research_store import AgentRunWriteDiscarded
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.tool_executor import validate_arguments

RUN_MODEL_LOOP_LIMIT = 40
RUN_TOOL_CALL_LIMIT = 160
TASK_MODEL_LOOP_LIMIT = 160
TASK_TOOL_CALL_LIMIT = 640
TASK_TIME_LIMIT_SECONDS = 90 * 60
RUN_MODEL_LOOP_HARD_CAP = 160
RUN_TOOL_CALL_HARD_CAP = 640
TASK_MODEL_LOOP_HARD_CAP = 640
TASK_TOOL_CALL_HARD_CAP = 2560
TASK_TIME_HARD_CAP = 6 * 60 * 60
MAX_EXTENSIONS = 3

ROLE_SKILL_DEFAULTS = {
    "planner": "research-plan-authoring",
    "search_worker": "usenix-catalog-orchestration",
    "paper_evaluator": "research-paper-evaluation",
    "research_critic": "research-coverage-review",
    "synthesizer": "research-report-synthesis",
}

ROLE_OUTPUT_FIELDS = {
    "planner": ("plan_version", "objective", "scope", "work_items", "capabilities", "budget", "report_structure"),
    "search_worker": ("work_item_id", "queries", "source", "candidates", "refresh_diagnostics"),
    "paper_evaluator": ("candidate_id", "relevance_score", "keep", "reason", "evidence_refs"),
    "research_critic": ("coverage", "gaps", "recommendations", "bounded_replan"),
    "synthesizer": ("report_version", "sections", "citation_manifest", "artifact_ids"),
}


class AgentRuntimeError(ValueError):
    """Stable, user-safe runtime error; no provider details are exposed."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class BudgetSnapshot:
    """Run/task usage and limits captured by the deterministic Orchestrator."""

    model_loops: int = 0
    tool_calls: int = 0
    task_model_loops: int = 0
    task_tool_calls: int = 0
    elapsed_seconds: float = 0.0
    max_model_loops: int = RUN_MODEL_LOOP_LIMIT
    max_tool_calls: int = RUN_TOOL_CALL_LIMIT
    task_max_model_loops: int = TASK_MODEL_LOOP_LIMIT
    task_max_tool_calls: int = TASK_TOOL_CALL_LIMIT
    max_seconds: float = TASK_TIME_LIMIT_SECONDS
    extensions: int = 0

    @classmethod
    def from_value(
        cls,
        value: "BudgetSnapshot | Mapping[str, Any] | None",
        *,
        owner_id: str = "",
        research_session_id: str = "",
        research_task_id: str | None = None,
    ) -> "BudgetSnapshot":
        if value is None:
            return cls()
        if isinstance(value, cls):
            value = value.__dict__
        if not isinstance(value, Mapping):
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "budget snapshot must be an object")
        value = dict(value)
        approved_resource = value.get("resource_snapshot") or value.get("approved_resource_snapshot")
        if approved_resource is not None:
            if not isinstance(approved_resource, Mapping) or not approved_resource.get("approved", False):
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "resource snapshot is not approved")
            if (
                approved_resource.get("owner_id") != owner_id
                or approved_resource.get("research_session_id") != research_session_id
                or approved_resource.get("research_task_id") != research_task_id
            ):
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "resource snapshot binding is invalid")
            increments = approved_resource.get("increments", approved_resource.get("approved_increment", {}))
            if not isinstance(increments, Mapping):
                raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "resource increments are invalid")
            base_limits = approved_resource.get("base_limits", approved_resource.get("current_limits", {}))
            if not isinstance(base_limits, Mapping):
                raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "resource base limits are invalid")
            aliases_for_increment = {
                "model_loops": "max_model_loops", "tool_calls": "max_tool_calls",
                "run_model_loops": "max_model_loops", "run_tool_calls": "max_tool_calls",
                "task_model_loops": "task_max_model_loops", "task_tool_calls": "task_max_tool_calls",
                "seconds": "max_seconds",
            }
            try:
                for source, target in aliases_for_increment.items():
                    if source in increments:
                        value[target] = int(base_limits.get(target, 0)) + int(increments[source])
                for target in ("max_model_loops", "max_tool_calls", "task_max_model_loops", "task_max_tool_calls", "max_seconds"):
                    if target in increments:
                        value[target] = int(base_limits.get(target, 0)) + int(increments[target])
            except (TypeError, ValueError) as exc:
                raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "resource increments are invalid") from exc
            if "extensions" in approved_resource:
                value["extensions"] = approved_resource["extensions"]
        approved_limits = approved_resource is not None
        if isinstance(value.get("resource_limits"), Mapping):
            value = {**value["resource_limits"], **value}
        aliases = {
            "max_model_loops": "max_model_loops", "model_loops": "model_loops",
            "max_tool_calls": "max_tool_calls", "tool_calls": "tool_calls",
            "task_model_loops": "task_model_loops", "task_tool_calls": "task_tool_calls",
            "task_max_model_loops": "task_max_model_loops", "task_max_tool_calls": "task_max_tool_calls",
            "seconds": "max_seconds", "max_seconds": "max_seconds", "elapsed_seconds": "elapsed_seconds",
            "max_extensions": "extensions", "extensions": "extensions",
        }
        values: dict[str, Any] = {}
        for key, target in aliases.items():
            if key in value:
                values[target] = value[key]
        try:
            for key in ("model_loops", "tool_calls", "task_model_loops", "task_tool_calls", "extensions"):
                if key in values:
                    values[key] = int(values[key])
            for key in ("elapsed_seconds", "max_seconds"):
                if key in values:
                    values[key] = float(values[key])
            for key in ("max_model_loops", "max_tool_calls", "task_max_model_loops", "task_max_tool_calls"):
                if key in values:
                    values[key] = int(values[key])
        except (TypeError, ValueError) as exc:
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "budget snapshot values are invalid") from exc
        if not approved_limits:
            # A plan/caller may only tighten the initial allowance. Increases
            # require the owner-bound approved resource snapshot above.
            values["max_model_loops"] = min(values.get("max_model_loops", RUN_MODEL_LOOP_LIMIT), RUN_MODEL_LOOP_LIMIT)
            values["max_tool_calls"] = min(values.get("max_tool_calls", RUN_TOOL_CALL_LIMIT), RUN_TOOL_CALL_LIMIT)
            values["task_max_model_loops"] = min(values.get("task_max_model_loops", TASK_MODEL_LOOP_LIMIT), TASK_MODEL_LOOP_LIMIT)
            values["task_max_tool_calls"] = min(values.get("task_max_tool_calls", TASK_TOOL_CALL_LIMIT), TASK_TOOL_CALL_LIMIT)
            values["max_seconds"] = min(values.get("max_seconds", TASK_TIME_LIMIT_SECONDS), TASK_TIME_LIMIT_SECONDS)
        result = cls(**values)
        if any(getattr(result, key) < 0 for key in ("model_loops", "tool_calls", "task_model_loops", "task_tool_calls", "extensions")):
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "budget snapshot cannot be negative")
        if result.extensions > MAX_EXTENSIONS:
            raise AgentRuntimeError("TASK_MODEL_LIMIT_REACHED", "resource extension limit reached")
        # Caller-provided budgets are advisory only.  Never permit a request to
        # enlarge the absolute product caps.
        result = cls(
            **{**result.__dict__,
               "model_loops": min(result.model_loops, RUN_MODEL_LOOP_HARD_CAP),
               "tool_calls": min(result.tool_calls, RUN_TOOL_CALL_HARD_CAP),
               "task_model_loops": min(result.task_model_loops, TASK_MODEL_LOOP_HARD_CAP),
               "task_tool_calls": min(result.task_tool_calls, TASK_TOOL_CALL_HARD_CAP),
               "max_model_loops": min(result.max_model_loops, RUN_MODEL_LOOP_HARD_CAP),
               "max_tool_calls": min(result.max_tool_calls, RUN_TOOL_CALL_HARD_CAP),
               "task_max_model_loops": min(result.task_max_model_loops, TASK_MODEL_LOOP_HARD_CAP),
               "task_max_tool_calls": min(result.task_max_tool_calls, TASK_TOOL_CALL_HARD_CAP),
               "max_seconds": min(result.max_seconds, TASK_TIME_HARD_CAP)},
        )
        return result


@dataclass(frozen=True)
class AgentRunInput:
    agent_run_id: str
    research_session_id: str
    role: str
    work_item_input: Mapping[str, Any] | None = None
    skill_snapshot: Mapping[str, Any] | None = None
    tool_snapshot: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None
    checkpoint_ref: str | None = None
    checkpoint_hash: str | None = None
    budget_snapshot: BudgetSnapshot | Mapping[str, Any] | None = None
    cancellation_token: Any = None
    research_task_id: str | None = None
    work_item_id: str | None = None
    attempt: int = 1
    resolved_model: str = ""
    reasoning_effort: str = "off"
    owner_id: str = ""
    continued_from_agent_run_id: str | None = None
    parent_source_event_id: str | None = None


@dataclass(frozen=True)
class AgentRunOutput:
    status: str
    schema_version: str = "runtime-v1"
    output_json: Mapping[str, Any] | None = None
    output_hash: str = ""
    checkpoint_ref: str | None = None
    checkpoint_hash: str | None = None
    model_metadata: Mapping[str, Any] = field(default_factory=dict)
    usage: Mapping[str, int] = field(default_factory=dict)
    error_code: str | None = None
    approval_signal: Mapping[str, Any] | None = None
    tool_results: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "schema_version": self.schema_version,
            "output_json": dict(self.output_json) if self.output_json is not None else None,
            "output_hash": self.output_hash, "checkpoint_ref": self.checkpoint_ref,
            "checkpoint_hash": self.checkpoint_hash, "model_metadata": dict(self.model_metadata),
            "usage": dict(self.usage), "error_code": self.error_code,
            "approval_signal": dict(self.approval_signal) if self.approval_signal else None,
            "tool_results": [dict(item) for item in self.tool_results],
        }


@dataclass(frozen=True)
class RoleCapability:
    role: str
    skill: Mapping[str, Any]
    tools: tuple[Mapping[str, Any], ...]


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _safe_text(value: Any, limit: int = 256) -> str:
    text = str(value or "")
    # Never retain provider URLs, credentials or hidden prompt-like fields.
    lowered = text.casefold()
    if any(token in lowered for token in ("http://", "https://", "authorization", "bearer ", "api_key", "password", "secret", "token", "cookie", "prompt", "chain_of_thought", "<think>")):
        return "[REDACTED]"
    return text[:limit]


def _is_cancelled(token: Any) -> bool:
    if token is None:
        return False
    if isinstance(token, Event):
        return token.is_set()
    value = getattr(token, "is_cancelled", None)
    if callable(value):
        return bool(value())
    if value is not None:
        return bool(value)
    value = getattr(token, "cancelled", False)
    return bool(value() if callable(value) else value)


def _ollama_model_factory(model_name: str, effort: str) -> Any:
    """Build through the existing Ollama platform adapter only."""
    from backend.app.platform.ollama import create_chat_model, resolve_reasoning_effort

    resolution = resolve_reasoning_effort(model_name, effort)
    return _OllamaRunnerAdapter(
        create_chat_model(model_name, reasoning=resolution.provider_value),
        model_name=model_name,
        effort=getattr(resolution, "effort", effort),
    )


class _OllamaRunnerAdapter:
    """Translate the isolated Runner contract to the existing chat API."""

    def __init__(self, model: Any, *, model_name: str, effort: str) -> None:
        self.model = model
        self.model_name = model_name
        self.reasoning_effort = effort

    def invoke(self, context: Mapping[str, Any], tools: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        bound = self.model
        if tools and callable(getattr(bound, "bind_tools", None)):
            schemas = [
                {
                    "type": "function",
                    "function": {
                        "name": item.get("name"),
                        "description": item.get("description", ""),
                        "parameters": item.get("parameters", {}),
                    },
                }
                for item in tools
            ]
            bound = bound.bind_tools(schemas)
        response = bound.invoke([{"role": "user", "content": json.dumps(dict(context), ensure_ascii=False, sort_keys=True)}])
        raw_calls = getattr(response, "tool_calls", ()) or ()
        calls = []
        for call in raw_calls:
            if isinstance(call, Mapping):
                function = call.get("function", call)
                calls.append({
                    "id": call.get("id"),
                    "name": function.get("name"),
                    "arguments": function.get("arguments", function.get("args", {})),
                })
        content = getattr(response, "content", response if isinstance(response, str) else "")
        output_json = None
        if isinstance(content, Mapping):
            output_json = dict(content)
        elif isinstance(content, str):
            with suppress(ValueError):
                parsed = json.loads(content)
                if isinstance(parsed, Mapping):
                    output_json = dict(parsed)
        return {"output_json": output_json, "tool_calls": calls}


class RoleCapabilityRegistry:
    """Adapter over Spec023 Skill/Tool registry snapshots; never a new registry."""

    def __init__(
        self,
        *,
        skills: Sequence[Any] | None = None,
        tools: Sequence[Any] | None = None,
        skill_registry: Any | None = None,
        tool_registry: Any | None = None,
        resolver: Callable[..., Any] | None = None,
    ) -> None:
        self._skills = list(skills or self._snapshot_skills(skill_registry))
        self._tools = list(tools or self._snapshot_tools(tool_registry) or build_default_tool_registry())
        self._resolver = resolver

    @classmethod
    def _snapshot_skills(cls, registry: Any | None) -> list[dict[str, Any]]:
        """Detach approved fields from the existing SkillRegistryService."""
        if registry is None:
            return []
        snapshots = []
        for summary in registry.list_skills():
            detail = registry.get_skill(summary.name)
            if detail is None:
                continue
            body = str(getattr(detail, "body", ""))
            snapshots.append({
                "name": detail.name,
                "version": "1",
                "schema_version": "1",
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "source_ref": detail.name,
                "enabled": bool(detail.enabled),
                "tools": list(detail.tools),
            })
        return snapshots

    @classmethod
    def _snapshot_tools(cls, registry: Any | None) -> list[dict[str, Any]]:
        """Detach schema/entry/state from the existing ToolRegistryService."""
        if registry is None:
            return []
        snapshots = []
        for tool in registry.list_tools():
            item = cls._as_dict(tool)
            item.update({
                "version": "1",
                "schema_version": "1",
                "parameters_hash": _hash(item.get("parameters", {})),
                "side_effect_class": cls._side_effect_for(item.get("name", "")),
            })
            snapshots.append(item)
        return snapshots

    @staticmethod
    def _side_effect_for(name: str) -> str:
        return "side_effect" if any(word in str(name).casefold() for word in ("import", "download")) else "read_only"

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            result = dict(value)
            result.setdefault("version", "1")
            result.setdefault("schema_version", result["version"])
            return result
        if hasattr(value, "to_dict"):
            result = dict(value.to_dict())
            for key in ("entry", "parameters", "side_effect_class", "execute", "call"):
                if hasattr(value, key):
                    result[key] = getattr(value, key)
            if "parameters" in result:
                result["parameters_hash"] = _hash(result["parameters"])
                result["content_hash"] = result["parameters_hash"]
            result.setdefault("source_ref", result.get("entry") or result.get("name"))
            result.setdefault("version", "1")
            result.setdefault("schema_version", result["version"])
            return result
        result = {key: getattr(value, key) for key in ("name", "description", "enabled", "entry", "parameters", "side_effect_class", "execute", "call") if hasattr(value, key)}
        if "parameters" in result:
            result["parameters_hash"] = _hash(result["parameters"])
            result["content_hash"] = result["parameters_hash"]
        result.setdefault("source_ref", result.get("entry") or result.get("name"))
        result.setdefault("enabled", True)
        result.setdefault("version", "1")
        result.setdefault("schema_version", result["version"])
        return result

    def resolve(self, role: str, skill_snapshot: Mapping[str, Any] | None, tool_snapshot: Any) -> RoleCapability:
        if role not in AGENT_ROLES:
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "unknown role")
        if self._resolver is not None:
            result = self._resolver(role, skill_snapshot, tool_snapshot)
            if isinstance(result, RoleCapability):
                return result
            if isinstance(result, Mapping):
                return RoleCapability(role, dict(result["skill"]), tuple(dict(item) for item in result.get("tools", ())))
        # PlanApprovalService persists ``{"skill": ..., "tools": [...]}``;
        # accept that envelope as the canonical application hand-off while
        # retaining the lower-level fields for direct contract tests.
        approved_envelope = isinstance(skill_snapshot, Mapping) and isinstance(skill_snapshot.get("skill"), Mapping)
        if approved_envelope:
            envelope = skill_snapshot
            if tool_snapshot is None:
                tool_snapshot = envelope.get("tools", ())
            skill_snapshot = envelope["skill"]
        skill = dict(skill_snapshot or {})
        if skill_snapshot is not None and (
            not skill.get("name") or not skill.get("schema_version", skill.get("version")) or not skill.get("content_hash", skill.get("hash")) or not skill.get("source_ref") or "enabled" not in skill
        ):
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "skill snapshot is incomplete")
        if skill and "version" in skill and "schema_version" not in skill:
            skill["schema_version"] = skill["version"]
        if skill and "version" not in skill and "schema_version" in skill:
            skill["version"] = skill["schema_version"]
        if skill and "hash" in skill and "content_hash" not in skill:
            skill["content_hash"] = skill["hash"]
        if skill and "content_hash" not in skill:
            skill["content_hash"] = _hash(skill.get("body", ""))
        if not skill:
            expected = ROLE_SKILL_DEFAULTS[role]
            for item in self._skills:
                candidate = self._as_dict(item)
                if candidate.get("name") == expected:
                    skill = candidate
                    break
            if not skill:
                # An explicit snapshot must be compared with an approved
                # registry entry.  There is no safe default for a missing
                # registry, so fail closed instead of trusting caller metadata.
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "approved skill snapshot is unavailable")
        if skill.get("name") != ROLE_SKILL_DEFAULTS[role] and not skill.get("approved", False):
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "skill does not match role")
        if skill.get("enabled") is False:
            raise AgentRuntimeError("SKILL_DISABLED", "skill is disabled")
        known_skill = next((self._as_dict(item) for item in self._skills if self._as_dict(item).get("name") == skill.get("name")), None)
        if skill_snapshot is not None and known_skill is None and not skill.get("approved", False):
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "approved skill snapshot is unavailable")
        if known_skill is not None:
            expected_skill = {
                "name": known_skill.get("name"),
                "version": known_skill.get("version", known_skill.get("schema_version", "1")),
                "schema_version": known_skill.get("schema_version", known_skill.get("version", "1")),
                "content_hash": known_skill.get("content_hash", known_skill.get("hash", _hash(known_skill.get("body", "")))),
                "source_ref": known_skill.get("source_ref", known_skill.get("name")),
                "enabled": bool(known_skill.get("enabled", True)),
            }
            if "version" not in skill:
                skill["version"] = skill.get("schema_version")
            supplied_skill = {key: skill.get(key) for key in expected_skill}
            if supplied_skill != expected_skill:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "skill snapshot drift")
        raw_tools = tool_snapshot or []
        if isinstance(raw_tools, Mapping):
            raw_tools = raw_tools.get("tools", list(raw_tools.values()) if "name" not in raw_tools else [raw_tools])
        tools = tuple(self._as_dict(item) for item in raw_tools)
        known = {self._as_dict(item).get("name"): self._as_dict(item) for item in self._tools}
        for item in tools:
            name = item.get("name")
            registered = known.get(name)
            if registered is None:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool is not registered")
            if "enabled" not in item:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool snapshot is incomplete")
            if item.get("enabled", registered.get("enabled", True)) is False or registered.get("enabled", True) is False:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool is disabled")
            registered_parameters = registered.get("parameters", {})
            if "parameters" in item and item["parameters"] != registered_parameters:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "caller schema is not registered schema")
            for snapshot_field in ("version", "schema_version"):
                expected_version = registered.get(snapshot_field, registered.get("version", "1"))
                if item.get(snapshot_field) != expected_version:
                    raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool snapshot version drift")
            parameters = registered_parameters
            expected_hash = _hash(parameters)
            supplied_hash = item.get("parameters_hash", item.get("schema_hash"))
            if not supplied_hash or supplied_hash != expected_hash:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool schema hash drift")
            expected_entry = registered.get("entry", "")
            if item.get("entry", expected_entry) != expected_entry:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool entry drift")
            expected_source_ref = registered.get("source_ref", expected_entry or name)
            expected_content_hash = registered.get("content_hash", registered.get("parameters_hash", expected_hash))
            if item.get("source_ref") != expected_source_ref or item.get("content_hash") != expected_content_hash:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool snapshot provenance drift")
            expected_side_effect = registered.get("side_effect_class")
            if expected_side_effect is None:
                expected_side_effect = self._side_effect_for(name)
            if item.get("side_effect_class", expected_side_effect) != expected_side_effect:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool side-effect scope drift")
            item.setdefault("parameters", parameters)
            item.setdefault("parameters_hash", expected_hash)
            item.setdefault("schema_hash", expected_hash)
            item.setdefault("entry", registered.get("entry", ""))
            item.setdefault("side_effect_class", expected_side_effect)
        declared_tools = skill.get("tools", [])
        if not isinstance(declared_tools, (list, tuple)) or any(not isinstance(name, str) for name in declared_tools):
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "skill tool allowlist is invalid")
        if {item.get("name") for item in tools} - set(declared_tools):
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool is outside skill allowlist")
        return RoleCapability(role, skill, tools)


class FakeModel:
    """Deterministic model contract for tests: returns successive response values."""

    def __init__(self, responses: Sequence[Any] | Any):
        self.responses = list(responses) if isinstance(responses, (list, tuple)) else [responses]
        self.calls: list[tuple[Any, Any]] = []

    def invoke(self, context: Mapping[str, Any], tools: Sequence[Mapping[str, Any]] = ()) -> Any:
        self.calls.append((dict(context), tuple(tools)))
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]

    complete = invoke


class FakeTool:
    """Deterministic Tool contract matching a Spec023 ToolEntry shape."""

    def __init__(self, name: str, handler: Callable[[dict[str, Any]], Any] | None = None, *, parameters: dict | None = None, side_effect_class: str = "read_only"):
        self.name, self.handler = name, handler or (lambda args: {"result_id": _hash(args)[:16]})
        self.parameters, self.side_effect_class = parameters or {"type": "object", "properties": {}}, side_effect_class
        self.calls: list[dict[str, Any]] = []

    def execute(self, arguments: dict[str, Any]) -> Any:
        self.calls.append(dict(arguments))
        return self.handler(arguments)


def _response_parts(response: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if isinstance(response, Mapping):
        raw = response.get("output_json", response.get("output", response.get("content")))
        calls = response.get("tool_calls", ())
    else:
        raw = getattr(response, "output_json", getattr(response, "output", getattr(response, "content", None)))
        calls = getattr(response, "tool_calls", ())
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    calls = list(calls or ()) if isinstance(calls, (list, tuple)) else []
    return (dict(raw) if isinstance(raw, Mapping) else None), [dict(item) for item in calls if isinstance(item, Mapping)]


class ResearchAgentRunner:
    """Run one isolated sub-agent under deterministic budget/cancel barriers."""

    def __init__(self, *, store=None, model=None, model_factory=None, model_router=None, tool_executor=None, capability_registry=None, resource_probe=None, clock=None, event_sink: Callable[[ResearchEvent], None] | None = None):
        self.store = store
        self.model = model
        self.model_factory = model_factory or (_ollama_model_factory if model is None and model_router is not None else None)
        self.model_router = model_router
        self.tool_executor = tool_executor
        self.capabilities = capability_registry or RoleCapabilityRegistry()
        self.resource_probe = resource_probe
        self.clock = clock or time.monotonic
        # Orchestrator installs this callback after construction.  The runner
        # remains the only skill/tool execution seam; the callback only fans
        # durable events into the existing projection path.
        self.event_sink = event_sink
        self._checkpoints: dict[str, dict[str, Any]] = {}

    def _runtime_event(self, input: AgentRunInput, *, node_type: str, node_key: str, status: str, **payload: Any) -> None:
        """Append a stable skill/tool event and notify the owning orchestrator."""
        if self.store is None or not input.research_task_id:
            return
        safe = {
            "node_type": node_type,
            "node_key": node_key,
            "parent_node_key": f"agent:{input.work_item_id}" if input.work_item_id else None,
            "parent_source_event_id": input.parent_source_event_id,
            "status": status,
            **payload,
        }
        safe = {key: value for key, value in safe.items() if value is not None}
        try:
            event = self.store.append_event(input.research_task_id, "worker", safe)
            if callable(self.event_sink):
                self.event_sink(event)
        except Exception:
            # Event telemetry is best effort and must never alter the runner's
            # state machine or expose provider failures to callers.
            return

    def _persist(self, run: AgentRun, owner_id: str, *, create: bool = False) -> AgentRun:
        if self.store is None:
            return run
        if create:
            return self.store.create_agent_run(run, owner_id=owner_id)
        return self.store.update_agent_run_status(run.agent_run_id, owner_id, "running")

    def _set_work_item_status(self, run: AgentRun, status: str, *, error_code: str | None = None) -> None:
        """Best-effort WorkItem convergence; AgentRun CAS remains authoritative."""
        if self.store is None or not run.work_item_id:
            return
        try:
            current = self.store.get_work_item(run.work_item_id)
            if current is None:
                return
            if status == "running" and current.status != "queued":
                return
            if status != "running" and current.status not in {"queued", "running"}:
                return
            self.store.update_work_item_status(run.work_item_id, status, error_code=error_code)
        except Exception:
            # A concurrent cancellation can legitimately win the projection race.
            return

    def _save_counters(self, run_id: str, owner_id: str, **kwargs: Any) -> None:
        if self.store is not None:
            self.store.update_agent_run_counters(run_id, owner_id, **kwargs)

    def _record_model_metadata(self, run: AgentRun, owner: str, model: Any, resolved_model: str, effort: str) -> AgentRun:
        """Persist provider resolution under the same running-generation CAS."""
        provider = str(getattr(model, "provider", "ollama" if self.model_router is not None else "injected"))
        actual_model = str(getattr(model, "model_name", resolved_model) or resolved_model or "injected")
        actual_effort = str(getattr(model, "reasoning_effort", effort) or effort)
        if self.store is None or not owner:
            return run
        writer = getattr(self.store, "update_agent_run_model_metadata", None)
        if not callable(writer):
            return run
        try:
            return writer(
                run.agent_run_id,
                owner,
                resolved_model=actual_model,
                reasoning_effort=actual_effort,
                provider=provider,
                expected_generation=run.generation,
            )
        except AgentRunWriteDiscarded as exc:
            raise AgentRuntimeError("MODEL_UNAVAILABLE", "run generation is no longer active") from exc

    def _cancel(
        self, run: AgentRun, owner: str, *, status: str = "cancelled", error_code: str | None = None
    ) -> bool:
        if self.store is not None:
            with suppress(InvalidStateTransition, Exception):
                self.store.update_agent_run_status(run.agent_run_id, owner, status, error_code=error_code)
                if status != "running":
                    self._set_work_item_status(
                        run,
                        "cancelled" if status == "cancelled" else ("failed" if status in {"failed", "limit_reached"} else status),
                        error_code=error_code,
                    )
                return True
            return False
        return True

    def _release_lease(self, task_id: str | None, held: bool) -> bool:
        if held and task_id and self.resource_probe is not None:
            release = getattr(self.resource_probe, "release", None)
            if callable(release):
                with suppress(Exception):
                    release(task_id)
        return False

    def _start_retry_attempt(
        self,
        run: AgentRun,
        input: AgentRunInput,
        owner: str,
        attempts_used: int,
        summaries: Sequence[Mapping[str, Any]],
    ) -> tuple[AgentRun, str, str]:
        """Close an invalid attempt and persist the next independent Run link."""
        handoff = {"schema_version": "runtime-v1", "output": None, "tool_results": list(summaries)}
        handoff_hash = _hash(handoff)
        handoff_ref = f"checkpoint:{run.agent_run_id}:{handoff_hash[:16]}"
        self._checkpoints[handoff_ref] = handoff
        if self.store is not None:
            self.store.create_agent_checkpoint(
                AgentCheckpoint(
                    checkpoint_ref=handoff_ref,
                    owner_id=owner,
                    research_session_id=run.research_session_id,
                    research_task_id=run.research_task_id,
                    work_item_id=run.work_item_id,
                    agent_run_id=run.agent_run_id,
                    schema_version="runtime-v1",
                    content=json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    content_hash=handoff_hash,
                    continued_from_agent_run_id=run.continued_from_agent_run_id,
                ),
                expected_generation=run.generation,
            )
            self._save_counters(
                run.agent_run_id,
                owner,
                checkpoint_ref=handoff_ref,
                checkpoint_hash=handoff_hash,
                expected_generation=run.generation,
            )
            # Retryable attempts are represented by limit_reached so the
            # existing Store continuation contract can enforce the chain.
            self.store.update_agent_run_status(
                run.agent_run_id,
                owner,
                "limit_reached",
                error_code="AGENT_OUTPUT_INVALID",
            )
            next_run = replace(
                run,
                agent_run_id=f"{input.agent_run_id}:attempt-{attempts_used + 1}",
                attempt=input.attempt + attempts_used,
                continued_from_agent_run_id=run.agent_run_id,
                status="queued",
                model_loop_count=0,
                tool_call_count=0,
                checkpoint_ref=handoff_ref,
                checkpoint_hash=handoff_hash,
                output_hash="",
                error_code=None,
                started_at=None,
                ended_at=None,
                generation=0,
            )
            next_run = self._persist(next_run, owner, create=True)
            next_run = self._persist(next_run, owner)
            self._set_work_item_status(next_run, "running")
            return next_run, handoff_ref, handoff_hash
        return run, handoff_ref, handoff_hash

    def _invoke(self, model: Any, context: Mapping[str, Any], tools: Sequence[Mapping[str, Any]]) -> Any:
        fn = getattr(model, "invoke", None) or getattr(model, "complete", None)
        if fn is None and callable(model):
            fn = model
        if fn is None:
            raise AgentRuntimeError("MODEL_UNAVAILABLE")
        try:
            return fn(context, tools)
        except TypeError:
            return fn(context)
        except Exception as exc:
            raise AgentRuntimeError("MODEL_UNAVAILABLE") from exc

    @staticmethod
    def _tool_entry(capability: RoleCapability, name: str) -> Mapping[str, Any] | None:
        return next((item for item in capability.tools if item.get("name") == name), None)

    def _dispatch(self, entry: Mapping[str, Any], args: dict[str, Any]) -> Any:
        try:
            if self.tool_executor is None:
                method = entry.get("execute") or entry.get("call")
                if callable(method):
                    return method(args)
                # Production fallback is the existing Spec023 dispatch table;
                # injected FakeTool handlers still take precedence above.
                from backend.app.skills.tool_dispatch import build_default_dispatch

                return build_default_dispatch()(entry["name"], args)
            executor = self.tool_executor
            for method_name in ("execute", "dispatch", "call"):
                method = getattr(executor, method_name, None)
                if callable(method):
                    try:
                        return method(entry["name"], args)
                    except TypeError:
                        return method(args)
            if callable(executor):
                return executor(entry["name"], args)
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "invalid tool executor")
        except AgentRuntimeError:
            raise
        except Exception:
            return {"ok": False, "error_code": "TOOL_EXECUTION_FAILED", "summary": "tool execution failed"}

    def _safe_tool_result(self, entry: Mapping[str, Any], value: Any, *, error: str | None = None) -> dict[str, Any]:
        if not isinstance(value, Mapping) and hasattr(value, "ok"):
            ok = bool(getattr(value, "ok", False))
            value = {
                "ok": ok,
                "result_id": getattr(value, "name", None),
                "output": getattr(value, "output", ""),
                "error_code": None if ok else "TOOL_EXECUTION_FAILED",
            }
        if isinstance(value, Mapping):
            result_id = value.get("result_id", value.get("id"))
            status = "ok" if error is None and value.get("ok", True) else "error"
            error = error or value.get("error_code")
            raw = value.get("output", value.get("content", value.get("summary", "")))
        else:
            result_id, status, raw = None, "ok" if error is None else "error", value
        safe = {"name": entry.get("name"), "status": status, "error_code": error,
                "result_id": _safe_text(result_id, 80) if result_id else None,
                "length": len(str(raw or "")), "content_hash": _hash(_safe_text(raw))}
        if raw and not error:
            safe["summary"] = _safe_text(raw)
        return safe

    def _validate_calls(self, capability: RoleCapability, calls: Sequence[Mapping[str, Any]]) -> list[tuple[Mapping[str, Any], dict[str, Any]]]:
        from backend.app.research.application.search_catalog_adapter import map_catalog_tool_args

        validated = []
        for call in calls:
            name = call.get("name")
            if isinstance(call.get("function"), Mapping):
                function = call["function"]
                name = function.get("name", name)
                args = function.get("arguments", call.get("arguments", {}))
            else:
                args = call.get("arguments", call.get("args", {}))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError as exc:
                    raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "tool arguments are invalid") from exc
            entry = self._tool_entry(capability, name)
            if entry is None:
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "tool is not allowed")
            # WorkItem fields intentionally differ from the registered
            # Spec023 Tool fields.  Normalize at this single execution seam so
            # a model cannot smuggle facets/language or a second source into
            # the Tool call.
            if name == "search_paper_catalog" and isinstance(args, Mapping):
                try:
                    args = map_catalog_tool_args(args)
                except (TypeError, ValueError) as exc:
                    raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "catalog tool arguments are invalid") from exc
            normalized, error = validate_arguments(dict(entry.get("parameters") or {}), args)
            if error:
                raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "tool arguments failed schema validation")
            validated.append((entry, normalized or {}))
        return validated

    def _validate_output(self, role: str, output: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(output, Mapping):
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID")
        try:
            validate_safe_scope(dict(output))
        except PlanOutputInvalid:
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID") from None
        source_refs = output.get("source_refs", [])
        if not isinstance(source_refs, list) or any(not isinstance(ref, str) or not ref.strip() or not all(char.isalnum() or char in ":_-" for char in ref) for ref in source_refs):
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID")
        result = dict(output)
        if not isinstance(result.get("schema_version"), str) or not result.get("schema_version"):
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID")
        if not isinstance(result.get("safe_summary"), Mapping):
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID")
        result.setdefault("output_hash", _hash({key: value for key, value in result.items() if key != "output_hash"}))
        for key in ROLE_OUTPUT_FIELDS[role]:
            if key not in result:
                raise AgentRuntimeError("AGENT_OUTPUT_INVALID")
        return result

    def run(self, input: AgentRunInput) -> AgentRunOutput:
        try:
            budget = BudgetSnapshot.from_value(
                input.budget_snapshot,
                owner_id=input.owner_id,
                research_session_id=input.research_session_id,
                research_task_id=input.research_task_id,
            )
        except AgentRuntimeError as exc:
            if exc.code == "TASK_MODEL_LIMIT_REACHED":
                return AgentRunOutput(
                    "limit_reached", error_code=exc.code,
                    approval_signal={"kind": "resource_extension", "reason": exc.code},
                )
            return AgentRunOutput("failed", error_code=exc.code)
        owner = input.owner_id
        if input.role not in AGENT_ROLES or not input.agent_run_id or not input.research_session_id:
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "invalid run identity")
        if input.role != "planner" and (not input.research_task_id or not input.work_item_id):
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "execution run must bind task and work item")
        if input.attempt < 1 or input.attempt > 4:
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "attempt must be between 1 and 4")
        capability = self.capabilities.resolve(input.role, input.skill_snapshot, input.tool_snapshot)
        lease_held = False
        worker_grant = 1
        resource_metadata: dict[str, Any] = {}
        if self.resource_probe is not None and input.research_task_id:
            try:
                granted, resource_code = self.resource_probe.arbitrate(input.research_task_id, 1)
                if granted < 1:
                    raise AgentRuntimeError("RESOURCE_PROBE_FAILED")
                worker_grant = int(granted)
                resource_metadata = {"worker_grant": int(granted)}
                if resource_code:
                    resource_metadata["resource_probe_code"] = str(resource_code)
                lease_held = True
            except AgentRuntimeError:
                raise
            except Exception as exc:
                # ResourceProbe's public contract is a conservative single-worker
                # fallback; a provider failure must not fabricate parallelism.
                raise AgentRuntimeError("RESOURCE_PROBE_FAILED") from exc
        if bool(input.checkpoint_ref) != bool(input.checkpoint_hash):
            lease_held = self._release_lease(input.research_task_id, lease_held)
            raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "checkpoint ref/hash must be paired")
        saved = None
        if input.checkpoint_ref:
            if self.store is not None:
                try:
                    checkpoint = self.store.get_agent_checkpoint(input.checkpoint_ref, input.owner_id)
                except Exception as exc:
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "checkpoint lookup failed") from exc
                if checkpoint is None or checkpoint.content_hash != input.checkpoint_hash:
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "checkpoint is unknown or not owned")
                if checkpoint.research_session_id != input.research_session_id or checkpoint.research_task_id != input.research_task_id or checkpoint.work_item_id != input.work_item_id or checkpoint.agent_run_id != input.continued_from_agent_run_id:
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "checkpoint binding is invalid")
                try:
                    saved = json.loads(checkpoint.content)
                except (TypeError, ValueError) as exc:
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "checkpoint content is invalid") from exc
                if _hash(saved) != input.checkpoint_hash:
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    raise AgentRuntimeError("AGENT_OUTPUT_INVALID", "checkpoint hash mismatch")
            else:
                saved = self._checkpoints.get(input.checkpoint_ref)
                if saved is None or _hash(saved) != input.checkpoint_hash:
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "checkpoint is unknown")
        run = AgentRun(
            agent_run_id=input.agent_run_id, research_session_id=input.research_session_id,
            research_task_id=input.research_task_id, work_item_id=input.work_item_id,
            attempt=input.attempt, continued_from_agent_run_id=input.continued_from_agent_run_id,
            role=input.role, skill_name=str(capability.skill.get("name")),
            skill_schema_version=str(capability.skill.get("schema_version", "1")),
            skill_content_hash=str(capability.skill.get("content_hash", "")),
            resolved_model=input.resolved_model or "injected", reasoning_effort=input.reasoning_effort,
            allowed_tools_json=json.dumps([{key: value for key, value in dict(item).items() if key not in {"execute", "call"}} for item in capability.tools], sort_keys=True),
            owner_id=owner,
        )
        try:
            existing = self.store.get_agent_run(input.agent_run_id, owner) if self.store is not None and owner else None
            run = self._persist(run, owner, create=True) if existing is None else existing
            run = self._persist(run, owner)
            self._set_work_item_status(run, "running")
        except Exception as exc:
            lease_held = self._release_lease(input.research_task_id, lease_held)
            raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "run binding rejected") from exc
        skill_name = str(capability.skill.get("name") or ROLE_SKILL_DEFAULTS.get(input.role, input.role))
        skill_key = f"skill:{input.work_item_id}:{skill_name}"
        self._runtime_event(
            input, node_type="skill", node_key=skill_key, status="running",
            skill_name=skill_name,
        )
        start = self.clock()
        loops, calls = budget.model_loops, budget.tool_calls
        task_loops, task_calls = budget.task_model_loops, budget.task_tool_calls
        run_loops, run_calls = budget.model_loops, budget.tool_calls
        if self.store is not None and owner and callable(getattr(self.store, "get_agent_run_usage", None)):
            try:
                chain_usage = self.store.get_agent_run_usage(
                    owner, input.research_session_id, input.research_task_id,
                    chain_from_agent_run_id=input.continued_from_agent_run_id,
                ) if input.continued_from_agent_run_id else {"model_loops": 0, "tool_calls": 0}
                task_usage = self.store.get_agent_run_usage(owner, input.research_session_id, input.research_task_id)
            except Exception as exc:
                lease_held = self._release_lease(input.research_task_id, lease_held)
                raise AgentRuntimeError("CAPABILITY_NOT_AUTHORIZED", "budget usage lookup failed") from exc
            loops = max(loops, int(chain_usage.get("model_loops", 0)))
            calls = max(calls, int(chain_usage.get("tool_calls", 0)))
            task_loops = max(task_loops, int(task_usage.get("model_loops", 0)))
            task_calls = max(task_calls, int(task_usage.get("tool_calls", 0)))
        summaries: list[Mapping[str, Any]] = []
        last_checkpoint_ref: str | None = input.checkpoint_ref
        last_checkpoint_hash: str | None = input.checkpoint_hash
        model = self.model
        if self.model_factory and self.model_router is None:
            try:
                model = self.model_factory(input.resolved_model, input.reasoning_effort)
            except Exception:
                self._cancel(run, owner, status="failed", error_code="MODEL_UNAVAILABLE")
                lease_held = self._release_lease(input.research_task_id, lease_held)
                return AgentRunOutput(
                    "failed", error_code="MODEL_UNAVAILABLE",
                    model_metadata={"model": input.resolved_model or "injected", "reasoning_effort": input.reasoning_effort, **resource_metadata},
                )
        resolved_model = input.resolved_model or "injected"
        if model is None and self.model_router is None:
            self._cancel(run, owner, status="failed", error_code="MODEL_UNAVAILABLE")
            lease_held = self._release_lease(input.research_task_id, lease_held)
            return AgentRunOutput("failed", error_code="MODEL_UNAVAILABLE", model_metadata={"model": input.resolved_model, "reasoning_effort": input.reasoning_effort})
        if model is not None or self.model_router is None:
            try:
                run = self._record_model_metadata(run, owner, model, resolved_model, input.reasoning_effort)
            except AgentRuntimeError as exc:
                self._cancel(run, owner, status="failed", error_code=exc.code)
                lease_held = self._release_lease(input.research_task_id, lease_held)
                return AgentRunOutput("failed", error_code=exc.code)
        context = {"role": input.role, "work_item_input": dict(input.work_item_input or {}), "checkpoint_ref": input.checkpoint_ref, "skill": dict(capability.skill)}
        if isinstance(saved, Mapping):
            # Resume only the verified minimum handoff, never hidden history.
            context["checkpoint"] = {"output": saved.get("output"), "tool_results": saved.get("tool_results", ())}
        try:
            attempts_used = 0
            while True:
                if _is_cancelled(input.cancellation_token):
                    self._cancel(run, owner)
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    return AgentRunOutput("cancelled", checkpoint_ref=last_checkpoint_ref, checkpoint_hash=last_checkpoint_hash, error_code="CANCELLED", usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                if self.clock() - start + budget.elapsed_seconds >= budget.max_seconds:
                    code = "TASK_TIME_LIMIT_REACHED"
                    self._cancel(run, owner, status="limit_reached")
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    signal = {"kind": "resource_extension", "reason": code, "increment_seconds": 90 * 60}
                    return AgentRunOutput("limit_reached", checkpoint_ref=last_checkpoint_ref, checkpoint_hash=last_checkpoint_hash, error_code=code, approval_signal=signal, usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                if loops >= budget.max_model_loops or task_loops >= budget.task_max_model_loops:
                    code = "MODEL_LOOP_LIMIT_REACHED" if loops >= budget.max_model_loops else "TASK_MODEL_LIMIT_REACHED"
                    self._cancel(run, owner, status="limit_reached")
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    return AgentRunOutput("limit_reached", checkpoint_ref=last_checkpoint_ref, checkpoint_hash=last_checkpoint_hash, error_code=code, approval_signal={"kind": "resource_extension", "reason": code, "increment_model_loops": 40, "increment_task_model_loops": 160}, usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                loops += 1
                task_loops += 1
                run_loops += 1
                self._save_counters(run.agent_run_id, owner, model_loop_count=run_loops, tool_call_count=run_calls, expected_generation=run.generation)
                attempts_used += 1
                if self.model_router is not None:
                    router_role = {"search_worker": "search-worker", "paper_evaluator": "paper-evaluator", "research_critic": "research-critic"}.get(input.role, input.role)
                    tier = "strong" if attempts_used >= 4 else "fast"
                    try:
                        choice = self.model_router.resolve(role=router_role, tier=tier)
                        resolved_model = choice.model or resolved_model
                        if self.model_factory:
                            model = self.model_factory(resolved_model, input.reasoning_effort)
                        run = self._record_model_metadata(run, owner, model, resolved_model, input.reasoning_effort)
                    except Exception as exc:
                        raise AgentRuntimeError("MODEL_UNAVAILABLE") from exc
                response = self._invoke(model, context, capability.tools)
                if _is_cancelled(input.cancellation_token):
                    self._cancel(run, owner)
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    return AgentRunOutput("cancelled", error_code="CANCELLED", usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                output, raw_calls = _response_parts(response)
                if raw_calls:
                    if calls + len(raw_calls) > budget.max_tool_calls or task_calls + len(raw_calls) > budget.task_max_tool_calls:
                        code = "TOOL_CALL_LIMIT_REACHED" if calls + len(raw_calls) > budget.max_tool_calls else "TASK_TOOL_CALL_LIMIT_REACHED"
                        self._cancel(run, owner, status="limit_reached")
                        lease_held = self._release_lease(input.research_task_id, lease_held)
                        return AgentRunOutput("limit_reached", checkpoint_ref=last_checkpoint_ref, checkpoint_hash=last_checkpoint_hash, error_code=code, approval_signal={"kind": "resource_extension", "reason": code, "increment_tool_calls": 160, "increment_task_tool_calls": 640}, usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                    # Atomic validation: no dispatch happens until every call passes.
                    validated = self._validate_calls(capability, raw_calls)
                    calls += len(validated)
                    task_calls += len(validated)
                    run_calls += len(validated)
                    readonly = all(str(entry.get("side_effect_class", "side_effect")) in {"read_only", "none"} for entry, _ in validated)
                    tool_keys = []
                    for entry, args in validated:
                        tool_key = f"tool:{input.work_item_id}:{entry.get('name')}:{_hash(args)[:12]}"
                        tool_keys.append(tool_key)
                        self._runtime_event(
                            input, node_type="tool", node_key=tool_key, status="running",
                            tool_name=_safe_text(entry.get("name"), 80),
                            parent_node_key=f"agent:{input.work_item_id}",
                        )
                    if readonly and len(validated) > 1:
                        with ThreadPoolExecutor(max_workers=min(len(validated), worker_grant)) as pool:
                            values = list(pool.map(lambda pair: self._dispatch(*pair), validated))
                    else:
                        values = [self._dispatch(entry, args) for entry, args in validated]
                    for index, ((entry, _), value) in enumerate(zip(validated, values, strict=True)):
                        result = self._safe_tool_result(entry, value)
                        summaries.append(result)
                        self._runtime_event(
                            input, node_type="tool", node_key=tool_keys[index],
                            status="completed" if result.get("status") == "ok" else "failed",
                            tool_name=_safe_text(entry.get("name"), 80),
                            result_id=result.get("result_id"),
                            result_length=result.get("length"),
                            content_hash=result.get("content_hash"),
                            summary=result.get("summary"),
                            error_code=result.get("error_code"),
                        )
                    if _is_cancelled(input.cancellation_token):
                        self._cancel(run, owner)
                        lease_held = self._release_lease(input.research_task_id, lease_held)
                        return AgentRunOutput("cancelled", checkpoint_ref=last_checkpoint_ref, checkpoint_hash=last_checkpoint_hash, error_code="CANCELLED", usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                    if any(item.get("status") == "error" for item in summaries[-len(validated):]):
                        self._cancel(run, owner, status="failed", error_code="TOOL_EXECUTION_FAILED")
                        lease_held = self._release_lease(input.research_task_id, lease_held)
                        return AgentRunOutput("failed", error_code="TOOL_EXECUTION_FAILED", usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                    checkpoint = {"schema_version": "runtime-v1", "output": None, "tool_results": summaries}
                    checkpoint_hash = _hash(checkpoint)
                    checkpoint_ref = f"checkpoint:{input.agent_run_id}:{checkpoint_hash[:16]}"
                    self._checkpoints[checkpoint_ref] = checkpoint
                    if self.store is not None:
                        self.store.create_agent_checkpoint(AgentCheckpoint(
                            checkpoint_ref=checkpoint_ref, owner_id=owner,
                            research_session_id=input.research_session_id,
                            research_task_id=input.research_task_id, work_item_id=input.work_item_id,
                            agent_run_id=run.agent_run_id, schema_version="runtime-v1",
                            content=json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            content_hash=checkpoint_hash,
                            continued_from_agent_run_id=run.continued_from_agent_run_id,
                            ), expected_generation=run.generation)
                    last_checkpoint_ref, last_checkpoint_hash = checkpoint_ref, checkpoint_hash
                    self._save_counters(run.agent_run_id, owner, model_loop_count=run_loops, tool_call_count=run_calls, checkpoint_ref=checkpoint_ref, checkpoint_hash=checkpoint_hash, expected_generation=run.generation)
                    context = {**context, "tool_results": summaries[-len(validated):]}
                    continue
                try:
                    validated_output = self._validate_output(input.role, output or {})
                except AgentRuntimeError:
                    # The contract permits three fast attempts followed by one
                    # strong attempt.  Fake models can therefore deterministically
                    # return invalid → invalid → valid without a provider/router.
                    if attempts_used < 4:
                        run, last_checkpoint_ref, last_checkpoint_hash = self._start_retry_attempt(
                            run, input, owner, attempts_used, summaries
                        )
                        run_loops, run_calls = 0, 0
                        context = {
                            **context,
                            "checkpoint_ref": last_checkpoint_ref,
                            "checkpoint": {"output": None, "tool_results": list(summaries)},
                        }
                        continue
                    raise
                output_hash = _hash({key: value for key, value in validated_output.items() if key != "output_hash"})
                checkpoint = {"schema_version": validated_output.get("schema_version", "runtime-v1"), "output": validated_output, "tool_results": summaries}
                checkpoint_hash = _hash(checkpoint)
                checkpoint_ref = f"checkpoint:{input.agent_run_id}:{checkpoint_hash[:16]}"
                self._checkpoints[checkpoint_ref] = checkpoint
                if _is_cancelled(input.cancellation_token):
                    self._cancel(run, owner)
                    lease_held = self._release_lease(input.research_task_id, lease_held)
                    return AgentRunOutput("cancelled", error_code="CANCELLED", usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                if self.store is not None:
                    self.store.create_agent_checkpoint(AgentCheckpoint(
                        checkpoint_ref=checkpoint_ref, owner_id=owner,
                        research_session_id=input.research_session_id,
                        research_task_id=input.research_task_id, work_item_id=input.work_item_id,
                        agent_run_id=run.agent_run_id, schema_version=str(checkpoint["schema_version"]),
                        content=json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        content_hash=checkpoint_hash,
                        continued_from_agent_run_id=run.continued_from_agent_run_id,
                        ), expected_generation=run.generation)
                self._save_counters(run.agent_run_id, owner, model_loop_count=run_loops, tool_call_count=run_calls, output_hash=output_hash, checkpoint_ref=checkpoint_ref, checkpoint_hash=checkpoint_hash, expected_generation=run.generation)
                if not self._cancel(run, owner, status="completed"):
                    current = self.store.get_agent_run(run.agent_run_id, owner) if self.store is not None else None
                    return AgentRunOutput(current.status if current else "cancelled", error_code="CANCELLED", usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
                lease_held = self._release_lease(input.research_task_id, lease_held)
                self._runtime_event(input, node_type="skill", node_key=skill_key, status="completed", skill_name=skill_name)
                return AgentRunOutput("completed", output_json=validated_output, output_hash=output_hash, checkpoint_ref=checkpoint_ref, checkpoint_hash=checkpoint_hash, model_metadata={"provider": getattr(model, "provider", "ollama" if self.model_router is not None else "injected"), "model": getattr(model, "model_name", resolved_model), "reasoning_effort": getattr(model, "reasoning_effort", input.reasoning_effort), "attempt": input.attempt, "attempts_used": attempts_used, **resource_metadata}, usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
        except AgentRuntimeError as exc:
            self._runtime_event(input, node_type="skill", node_key=skill_key, status="failed", skill_name=skill_name, error_code=exc.code)
            self._cancel(run, owner, status="failed", error_code=exc.code)
            lease_held = self._release_lease(input.research_task_id, lease_held)
            return AgentRunOutput("failed", error_code=exc.code, model_metadata={"provider": getattr(model, "provider", "ollama" if self.model_router is not None else "injected"), "model": getattr(model, "model_name", resolved_model), "reasoning_effort": getattr(model, "reasoning_effort", input.reasoning_effort), **resource_metadata}, usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))
        except Exception:
            self._runtime_event(input, node_type="skill", node_key=skill_key, status="failed", skill_name=skill_name, error_code="MODEL_UNAVAILABLE")
            # A failing Store read must not bypass the lease release barrier.
            try:
                current = self.store.get_agent_run(run.agent_run_id, owner) if self.store is not None and owner else None
            except Exception:
                current = None
            if current is None or current.status == "running":
                self._cancel(run, owner, status="failed", error_code="MODEL_UNAVAILABLE")
            lease_held = self._release_lease(input.research_task_id, lease_held)
            return AgentRunOutput(current.status if current and current.status != "running" else "failed", error_code=current.error_code if current and current.status != "running" and current.error_code else ("CANCELLED" if current and current.status != "running" else "MODEL_UNAVAILABLE"), model_metadata={"provider": getattr(model, "provider", "ollama" if self.model_router is not None else "injected"), "model": getattr(model, "model_name", resolved_model), "reasoning_effort": getattr(model, "reasoning_effort", input.reasoning_effort), **resource_metadata}, usage={"model_loops": loops, "tool_calls": calls}, tool_results=tuple(summaries))


__all__ = ["AgentRunInput", "AgentRunOutput", "AgentRuntimeError", "BudgetSnapshot", "FakeModel", "FakeTool", "RoleCapability", "RoleCapabilityRegistry", "ResearchAgentRunner"]
