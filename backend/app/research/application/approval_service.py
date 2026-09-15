"""Spec034 Task04 unified plan/approval command service.

Buttons and natural-language adapters call this service.  It is deliberately
free of HTTP concerns and uses the existing ResearchStore, MemoryRepository,
Skill Registry and Tool Registry; no capability is executed here.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from backend.app.research.application.plan_authoring import (
    PlanOutputInvalid,
    plan_output_hash,
    validate_research_plan_output,
    validate_safe_scope,
)
from backend.app.research.domain.contracts import SESSION_TERMINAL
from backend.app.research.domain.models import (
    ApprovalRequest,
    ResearchPlan,
    ResearchSessionPlan,
    ResearchTask,
    ResearchWorkItem,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ResearchCommandError(Exception):
    """Stable command error consumed by the HTTP adapter."""

    STATUS = {
        "RESEARCH_SESSION_NOT_FOUND": 404,
        "INTAKE_INCOMPLETE": 400,
        "PLAN_VERSION_STALE": 409,
        "APPROVAL_STALE": 409,
        "APPROVAL_CONFLICT": 409,
        "CAPABILITY_NOT_AUTHORIZED": 403,
        "SKILL_DISABLED": 403,
        "TASK_TERMINAL_CONFLICT": 409,
        "INVALID_STATE_TRANSITION": 409,
        "TASK_MODEL_LIMIT_REACHED": 429,
        "TASK_TIME_LIMIT_REACHED": 429,
        "SOURCE_UNAVAILABLE": 503,
    }

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.http_status = self.STATUS.get(code, 400)
        self.message = message or code
        super().__init__(self.message)


class PlanApprovalService:
    """Author plans and apply all six commands with owner/version/idempotency checks."""

    def __init__(
        self,
        *,
        store,
        memory_repository=None,
        skill_registry=None,
        tool_registry=None,
        research_service=None,
    ) -> None:
        self.store = store
        self.memory_repository = memory_repository
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        # The approval boundary only owns plan/session persistence.  Starting
        # an approved task is delegated to the already-composed ResearchService
        # so Orchestrator/Runner remain the single execution path.
        self.research_service = research_service

    def get_session(self, session_id: str, owner_id: str):
        session = self.store.get_session(session_id, owner_id)
        if session is None:
            raise ResearchCommandError("RESEARCH_SESSION_NOT_FOUND", "研究会话不存在")
        return session

    def author_plan(self, session_id: str, owner_id: str, output: dict[str, Any]) -> dict[str, Any]:
        """Persist a validated plan version and its pending plan approval."""
        session = self.get_session(session_id, owner_id)
        draft = self.store.get_intake_draft(session_id, owner_id)
        if draft is None or draft.status != "complete":
            raise ResearchCommandError("INTAKE_INCOMPLETE", "研究主题、目标和时间范围仍未完整确认")
        version = int(session.current_plan_version or 0) + 1
        try:
            normalized = validate_research_plan_output(output, expected_version=version)
        except PlanOutputInvalid as exc:
            raise ResearchCommandError("AGENT_OUTPUT_INVALID", str(exc)) from exc
        normalized["capabilities"] = self._normalize_capabilities(normalized["capabilities"])
        normalized["budget"] = self._normalize_budget(normalized["budget"])
        if session.status == "intake_pending":
            self.store.update_session_status(session_id, owner_id, "plan_generating")
        elif session.status not in {"plan_generating", "plan_pending_approval"}:
            raise ResearchCommandError("INVALID_STATE_TRANSITION", f"当前会话状态不允许生成计划：{session.status}")
        now = _utcnow()
        plan = ResearchSessionPlan(
            research_session_id=session_id,
            version=version,
            schema_version=normalized["schema_version"],
            output_hash=normalized["output_hash"],
            objective=normalized["objective"],
            scope_json=_dump(normalized["scope"]),
            work_items_json=_dump(normalized["work_items"]),
            capabilities_json=_dump(normalized["capabilities"]),
            budget_json=_dump(normalized["budget"]),
            report_structure_json=_dump(normalized["report_structure"]),
            safety_summary_json=_dump(normalized["safe_summary"]),
            status="proposed",
            created_at=now,
        )
        if hasattr(self.store, "create_session_plan_cas"):
            result = self.store.create_session_plan_cas(
                plan,
                owner_id,
                expected_current_version=session.current_plan_version,
            )
            if result is None:
                raise ResearchCommandError("PLAN_VERSION_STALE", "计划版本已更新，请刷新计划卡")
            plan, _saved_session = result
        else:
            self.store.create_session_plan(plan, owner_id)
            self.store.update_session_links(session_id, owner_id, current_plan_version=version)
        self.store.supersede_session_plans(session_id, owner_id, version)
        self.store.supersede_approvals(session_id, owner_id, before_version=version)
        approval = self.store.create_approval(
            ApprovalRequest(
                approval_request_id=uuid.uuid4().hex,
                owner_id=owner_id,
                research_session_id=session_id,
                kind="plan",
                subject_id=session_id,
                subject_version=version,
                requested_scope_json=_dump({"plan_version": version, "output_hash": normalized["output_hash"]}),
                idempotency_key=f"plan-approval:{session_id}:{version}",
                created_at=now,
            )
        )
        current = self.store.get_session(session_id, owner_id)
        if current.status == "plan_generating":
            current = self.store.update_session_status(session_id, owner_id, "plan_pending_approval")
        return self._response(current, approval, plan=plan)

    create_plan = author_plan

    def command(self, session_id: str, owner_id: str, *, command: str, subject_version: int,
                scope_json: dict[str, Any], idempotency_key: str, decided_by_message_id: str | None = None) -> dict[str, Any]:
        """Apply one command; repeated idempotency keys return the durable decision."""
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
            raise ResearchCommandError("APPROVAL_STALE", "幂等键无效")
        session = self.get_session(session_id, owner_id)
        if command not in {
            "approve_plan", "revise_plan", "cancel_research",
            "approve_capability", "approve_resource_extension", "decline_request",
        }:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "未知研究命令")
        record = self.store.get_command_result_record(idempotency_key, owner_id)
        if record is not None:
            identity = (record.get("research_session_id"), record.get("command"), int(record.get("subject_version", 0)))
            requested = (session_id, command, int(subject_version))
            if identity == requested:
                return json.loads(record["response_json"])
            if identity[0] != session_id or identity[1] != command:
                raise ResearchCommandError("APPROVAL_CONFLICT", "幂等键身份冲突")
            raise ResearchCommandError("APPROVAL_STALE", "幂等键绑定了旧计划版本")
        # Idempotent replay is checked before the current plan version.  A
        # durable response from an older plan is still the response for that
        # exact command key; only a new key must satisfy the current version.
        if int(subject_version) != int(session.current_plan_version):
            raise ResearchCommandError("PLAN_VERSION_STALE", "计划版本已更新，请刷新计划卡")
        self._validate_scope(scope_json, command)
        if command == "approve_plan":
            response = self._approve_plan(session, owner_id, scope_json, idempotency_key, decided_by_message_id)
        elif command == "revise_plan":
            response = self._revise_plan(session, owner_id, scope_json, idempotency_key)
        elif command == "cancel_research":
            response = self._cancel(session, owner_id, idempotency_key)
        elif command == "approve_capability":
            response = self._approve_capability(session, owner_id, scope_json, idempotency_key, decided_by_message_id)
        elif command == "approve_resource_extension":
            response = self._approve_resource(session, owner_id, scope_json, idempotency_key, decided_by_message_id)
        else:
            response = self._decline(session, owner_id, scope_json, idempotency_key, decided_by_message_id)
        return self.store.save_command_result(
            owner_id=owner_id, research_session_id=session_id, subject_version=subject_version, idempotency_key=idempotency_key,
            command=command, response=response,
        )

    execute_command = command

    def _approve_plan(self, session, owner_id, scope, key, message_id):
        plan = self.store.get_session_plan(session.research_session_id, owner_id, session.current_plan_version)
        existing_outbox = self.store.get_activity_outbox(
            owner_id=owner_id, research_session_id=session.research_session_id,
            subject_version=session.current_plan_version, command_idempotency_key=key,
        )
        if existing_outbox is not None:
            approval = next((item for item in self.store.list_approvals(session.research_session_id, owner_id, subject_version=session.current_plan_version) if item.kind == "plan"), None)
            task = self.store.get_task(existing_outbox["research_task_id"], owner_id)
            # Even a completed outbox may precede a process crash before the
            # Session link was committed; replay the link step idempotently.
            return self._resume_activity(session, owner_id, existing_outbox, approval, task, plan=plan)
        activation = self.store.get_plan_activation(
            owner_id=owner_id, research_session_id=session.research_session_id,
            subject_version=session.current_plan_version, command_idempotency_key=key,
        )
        approval = self._pending(session, owner_id, "plan")
        if plan is None or approval is None:
            if activation is not None and plan is not None:
                # A crash may have committed the approval before the process
                # reached the task/outbox steps.  The activation anchor makes
                # that same command key recoverable.
                activation_approval = next((item for item in self.store.list_approvals(session.research_session_id, owner_id, subject_version=session.current_plan_version) if item.kind == "plan" and item.status == "approved"), None)
                if activation_approval is not None:
                    task = self._activate_task(session, owner_id, plan, activation)
                    outbox = self.store.get_activity_outbox(
                        owner_id=owner_id, research_session_id=session.research_session_id,
                        subject_version=plan.version, command_idempotency_key=key,
                    )
                    if outbox is None:
                        raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究活动记录暂时不可用")
                    return self._resume_activity(session, owner_id, outbox, activation_approval, task, plan=plan)
            if any(a.kind == "plan" and a.status in {"approved", "rejected", "cancelled", "superseded"} for a in self.store.list_approvals(session.research_session_id, owner_id, subject_version=session.current_plan_version)):
                raise ResearchCommandError("APPROVAL_CONFLICT", "计划审批已由其它窗口决策")
            raise ResearchCommandError("APPROVAL_STALE", "计划审批已过期")
        if session.status != "plan_pending_approval":
            if session.status in SESSION_TERMINAL:
                raise ResearchCommandError("TASK_TERMINAL_CONFLICT", "研究会话已结束")
            raise ResearchCommandError("INVALID_STATE_TRANSITION", "当前状态不能批准计划")
        self._validate_plan_scope(scope, plan)
        try:
            activation = self.store.create_plan_activation(
                owner_id=owner_id, research_session_id=session.research_session_id,
                subject_version=plan.version, command_idempotency_key=key,
            )
        except Exception as exc:
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究激活记录暂时不可用") from exc
        decided = self.store.decide_approval(
            approval.approval_request_id, owner_id, "approved", approved_scope_json=_dump(scope),
            decided_by_message_id=message_id, subject_version=session.current_plan_version,
        )
        task = self._activate_task(session, owner_id, plan, activation)
        outbox = self.store.get_activity_outbox(
            owner_id=owner_id, research_session_id=session.research_session_id,
            subject_version=plan.version, command_idempotency_key=key,
        )
        if outbox is None:
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究活动记录暂时不可用")
        return self._resume_activity(session, owner_id, outbox, decided, task, plan=plan)

    def _resume_activity(self, session, owner_id, outbox, approval, task, *, plan=None):
        """Complete the cross-database activity Saga without duplicate messages."""
        if task is None:
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究任务待补偿")
        activity_id = outbox.get("activity_message_id")
        if activity_id and self.memory_repository is not None:
            existing = self.memory_repository.get_message(activity_id, owner_id)
            if existing is None:
                activity_id = None
        if activity_id is None:
            if self.memory_repository is None:
                with suppress(Exception):
                    self.store.update_activity_outbox(outbox["outbox_id"], status="failed", error_code="SOURCE_UNAVAILABLE")
                raise ResearchCommandError("SOURCE_UNAVAILABLE", "会话消息存储暂时不可用")
            try:
                activity_key = f"research-activity:{session.research_session_id}:{outbox['subject_version']}:{outbox['command_idempotency_key']}"
                activity = self.memory_repository.create_activity_message(
                    session.conversation_id, owner_id, "研究执行已获批准，正在排队。",
                    activity_idempotency_key=activity_key, status="pending", model="research", mode="research",
                    parent_message_id=session.trigger_message_id,
                )
                activity_id = activity.message_id
            except Exception as exc:
                with suppress(Exception):
                    self.store.update_activity_outbox(outbox["outbox_id"], status="failed", error_code="SOURCE_UNAVAILABLE")
                raise ResearchCommandError("SOURCE_UNAVAILABLE", "会话消息存储暂时不可用") from exc
        try:
            self.store.update_activity_outbox(outbox["outbox_id"], status="completed", activity_message_id=activity_id)
        except Exception as exc:
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究活动记录暂时不可用") from exc
        links = {"research_task_id": task.research_task_id, "current_plan_version": session.current_plan_version}
        links["activity_message_id"] = activity_id
        try:
            updated = self.store.update_session_links(session.research_session_id, owner_id, **links)
            if updated.status != "queued":
                updated = self.store.update_session_status(session.research_session_id, owner_id, "queued")
        except Exception as exc:
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究会话链接暂时不可用") from exc
        if self.research_service is not None:
            try:
                # ResearchService owns the executor and the unique
                # Orchestrator instance.  Its in-flight guard makes this safe
                # when a crash-recovery replay reaches the same outbox twice.
                self.research_service.start(task.research_task_id, owner_id)
            except Exception as exc:
                with suppress(Exception):
                    self.store.update_activity_outbox(
                        outbox["outbox_id"], status="failed", error_code="SOURCE_UNAVAILABLE"
                    )
                raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究运行时暂时不可用") from exc
        return self._response(updated, approval, task=task, plan=plan)

    def _activate_task(self, session, owner_id, plan, activation) -> ResearchTask:
        data = json.loads(plan.budget_json or "{}")
        quality = data.get("quality_profile", "balanced")
        target = max(1, min(int(data.get("target_paper_count", 12)), 20))
        now = _utcnow()
        # Materialization must preserve the conversation's project binding;
        # never silently turn a project-scoped Session into an unbound Task.
        conversation = self.memory_repository.get_conversation(session.conversation_id, owner_id) if self.memory_repository is not None else None
        if conversation is None:
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究会话所属会话不可用")
        task = ResearchTask(
            research_task_id=activation["research_task_id"], owner_id=owner_id,
            project_id=conversation.project_id, conversation_id=session.conversation_id, goal=plan.objective,
            language=str(data.get("language", "zh")), quality_profile=quality,
            review_plan_first=True, target_paper_count=target,
            soft_budget_seconds=int(data.get("soft_budget_seconds", 1500)),
            status="draft", current_plan_version=plan.version, created_at=now, updated_at=now,
        )
        items = []
        # The public plan deliberately uses short, human-readable WorkItem
        # IDs (for example ``s1`` and ``e1``), while the research store uses
        # task-scoped IDs as the primary key.  Materialize dependencies in
        # that same namespace or the Orchestrator will never find a completed
        # upstream item after activation.
        raw_work_items = json.loads(plan.work_items_json or "[]")
        work_item_ids = {
            raw["id"]: f"{task.research_task_id}:{raw['id']}"
            for raw in raw_work_items
        }
        for raw in raw_work_items:
            dependencies = [
                work_item_ids.get(dependency, f"{task.research_task_id}:{dependency}")
                for dependency in raw.get("depends_on", [])
            ]
            items.append(ResearchWorkItem(
                work_item_id=f"{task.research_task_id}:{raw['id']}", research_task_id=task.research_task_id,
                plan_version=plan.version, task_type=raw["task_type"], role=raw["role"],
                depends_on_json=_dump(dependencies), input_json=_dump(raw.get("params", {})),
                status="queued", attempt=0, created_at=now, updated_at=now,
            ))
        try:
            materialized, _outbox = self.store.activate_plan(
                activation=activation,
                task=task,
                plan=ResearchPlan(
                    research_task_id=task.research_task_id, version=plan.version,
                    planner_model="research-plan-authoring", rationale_summary=plan.objective,
                    facets_json=_dump(json.loads(plan.scope_json or {}).get("facets", [])), status="active", created_at=now,
                ),
                items=items,
                outbox_key=activation["command_idempotency_key"],
            )
            return materialized
        except ResearchCommandError:
            raise
        except Exception as exc:
            with suppress(Exception):
                self.store.update_plan_activation(activation["activation_id"], status="failed", error_code="SOURCE_UNAVAILABLE")
            raise ResearchCommandError("SOURCE_UNAVAILABLE", "研究任务激活暂时不可用") from exc

    def _revise_plan(self, session, owner_id, scope, key):
        old = self.store.get_session_plan(session.research_session_id, owner_id, session.current_plan_version)
        if old is None:
            raise ResearchCommandError("PLAN_VERSION_STALE", "计划不存在")
        revised = {
            "schema_version": old.schema_version, "plan_version": old.version + 1,
            "objective": scope.get("objective", old.objective),
            "scope": scope.get("scope", json.loads(old.scope_json)),
            "work_items": scope.get("work_items", json.loads(old.work_items_json)),
            "capabilities": scope.get("capabilities", json.loads(old.capabilities_json)),
            "budget": scope.get("budget", json.loads(old.budget_json)),
            "report_structure": scope.get("report_structure", json.loads(old.report_structure_json)),
            "safe_summary": json.loads(old.safety_summary_json), "source_refs": scope.get("source_refs", []),
        }
        revised["output_hash"] = plan_output_hash(revised)
        return self.author_plan(session.research_session_id, owner_id, revised)

    def _cancel(self, session, owner_id, key):
        if session.status in SESSION_TERMINAL:
            raise ResearchCommandError("TASK_TERMINAL_CONFLICT", "研究会话已结束")
        updated, task, _cancelled_count = self.store.cancel_session_research(session.research_session_id, owner_id)
        return self._response(updated, None, task=task)

    def _approve_capability(self, session, owner_id, scope, key, message_id):
        self._assert_capabilities(scope)
        return self._decide_pending(session, owner_id, "capability_override", scope, key, message_id)

    def _approve_resource(self, session, owner_id, scope, key, message_id):
        for name, cap in (("model_loops", 640), ("tool_calls", 2560), ("seconds", 21600)):
            if name in scope and (not isinstance(scope[name], int) or scope[name] < 0 or scope[name] > cap):
                raise ResearchCommandError("TASK_MODEL_LIMIT_REACHED" if name != "seconds" else "TASK_TIME_LIMIT_REACHED", f"{name} 超出绝对上限")
        return self._decide_pending(session, owner_id, "resource_extension", scope, key, message_id)

    def _decline(self, session, owner_id, scope, key, message_id):
        approval = self._find_pending(session, owner_id, scope)
        if approval is None:
            raise ResearchCommandError("APPROVAL_STALE", "没有可拒绝的待处理审批")
        decided = self.store.decide_approval(approval.approval_request_id, owner_id, "rejected", approved_scope_json=_dump(scope), decided_by_message_id=message_id, subject_version=session.current_plan_version)
        return self._response(session, decided)

    def _decide_pending(self, session, owner_id, kind, scope, key, message_id):
        approval = self._pending(session, owner_id, kind)
        if approval is None:
            if any(a.kind == kind and a.status != "pending" for a in self.store.list_approvals(session.research_session_id, owner_id, subject_version=session.current_plan_version)):
                raise ResearchCommandError("APPROVAL_CONFLICT", "审批已由其它窗口决策")
            raise ResearchCommandError("APPROVAL_STALE", "审批已过期或不存在")
        decided = self.store.decide_approval(approval.approval_request_id, owner_id, "approved", approved_scope_json=_dump(scope), decided_by_message_id=message_id, subject_version=session.current_plan_version)
        return self._response(session, decided)

    def _pending(self, session, owner_id, kind):
        return next((a for a in self.store.list_approvals(session.research_session_id, owner_id, subject_version=session.current_plan_version) if a.kind == kind and a.status == "pending"), None)

    def _find_pending(self, session, owner_id, scope):
        requested = scope.get("approval_request_id") if isinstance(scope, dict) else None
        if requested:
            approval = self.store.get_approval(requested, owner_id)
            return approval if approval and approval.research_session_id == session.research_session_id and approval.status == "pending" else None
        return next((a for a in self.store.list_approvals(session.research_session_id, owner_id) if a.status == "pending"), None)

    def _assert_capabilities(self, scope):
        if self.skill_registry is None or self.tool_registry is None:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "能力注册表不可用")
        skill_name = scope.get("skill") or scope.get("skill_name")
        tool_names = scope.get("tools", [])
        if not isinstance(skill_name, str) or not isinstance(tool_names, list):
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "能力范围必须包含 Skill 与 Tool")
        skill = self.skill_registry.get_skill(skill_name)
        if skill is None:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "Skill 未注册")
        if not skill.enabled:
            raise ResearchCommandError("SKILL_DISABLED", "Skill 已禁用")
        if any(name not in skill.tools for name in tool_names):
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "Tool 不在 Skill 声明范围")
        for name in tool_names:
            tool = self.tool_registry.get_tool(name)
            if tool is None or not tool.enabled or not tool.entry or any(word in tool.entry.casefold() for word in ("shell", "python")):
                raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "Tool 未注册、已禁用或不可执行")

    def _normalize_capabilities(self, capabilities):
        """Resolve plan capabilities to immutable Registry snapshots."""
        if not capabilities:
            return []
        if self.skill_registry is None or self.tool_registry is None:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "能力注册表不可用")
        snapshots = []
        try:
            for capability in capabilities:
                if not isinstance(capability, dict):
                    raise ValueError("capability must be an object")
                skill_name = capability.get("skill") or capability.get("skill_name")
                tools = capability.get("tools", [])
                if not isinstance(skill_name, str) or not isinstance(tools, list):
                    raise ValueError("capability requires skill and tools")
                skill = self.skill_registry.get_skill(skill_name)
                if skill is None:
                    raise ValueError("skill is not registered")
                if not skill.enabled:
                    raise ResearchCommandError("SKILL_DISABLED", "Skill 已禁用")
                skill_snapshot = {
                    "name": skill.name, "version": "1", "schema_version": "1",
                    "content_hash": hashlib.sha256(skill.body.encode("utf-8")).hexdigest(),
                    "enabled": True, "source_ref": skill.name, "tools": list(skill.tools),
                }
                tool_snapshots = []
                for name in tools:
                    if not isinstance(name, str) or name not in skill.tools:
                        raise ValueError("tool is outside Skill declaration")
                    tool = self.tool_registry.get_tool(name)
                    if tool is None or not tool.enabled or not tool.entry:
                        raise ValueError("tool is unavailable")
                    if any(word in tool.entry.casefold() for word in ("shell", "python")):
                        raise ValueError("executable tool is forbidden")
                    params_hash = hashlib.sha256(_dump(tool.parameters).encode("utf-8")).hexdigest()
                    # Canonical runtime enum shared with RoleCapabilityRegistry:
                    # read_only tools may fan out; side_effect tools stay ordered.
                    side_effect = "side_effect" if any(word in name.casefold() for word in ("import", "download")) else "read_only"
                    tool_snapshots.append({
                        "name": tool.name, "version": "1", "parameters_hash": params_hash,
                        "content_hash": params_hash, "source_ref": tool.entry or tool.name,
                        "parameters": tool.parameters, "enabled": True, "side_effect_class": side_effect,
                        "entry": tool.entry,
                    })
                snapshots.append({"skill": skill_snapshot, "tools": tool_snapshots})
        except ResearchCommandError:
            raise
        except Exception as exc:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "能力注册表解析失败") from exc
        return snapshots

    @staticmethod
    def _normalize_budget(budget):
        if not isinstance(budget, dict) or len(budget) > 16:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "预算结构无效")
        result = dict(budget)
        try:
            result["quality_profile"] = str(result.get("quality_profile", "balanced"))
            result["target_paper_count"] = max(1, min(int(result.get("target_paper_count", 12)), 20))
            result["soft_budget_seconds"] = max(1, min(int(result.get("soft_budget_seconds", 1500)), 21600))
        except (TypeError, ValueError) as exc:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "预算结构无效") from exc
        result["resource_limits"] = {
            "max_model_loops": 160, "max_tool_calls": 640,
            "task_max_model_loops": 640, "task_max_tool_calls": 2560,
            "max_seconds": 21600, "max_extensions": 3,
        }
        return result

    @staticmethod
    def _validate_plan_scope(scope, plan):
        if not isinstance(scope, dict):
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "批准范围必须是对象")
        allowed = {"plan_version", "output_hash"}
        if set(scope) - allowed:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "批准范围不能扩大计划权限")
        if "plan_version" in scope and int(scope["plan_version"]) != plan.version:
            raise ResearchCommandError("PLAN_VERSION_STALE", "批准范围版本已过期")
        if "output_hash" in scope and scope["output_hash"] != plan.output_hash:
            raise ResearchCommandError("PLAN_VERSION_STALE", "批准范围哈希已过期")

    @staticmethod
    def _validate_scope(scope, command):
        try:
            validate_safe_scope(scope)
        except PlanOutputInvalid as exc:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", str(exc)) from exc
        allowed = {
            "approve_plan": {"plan_version", "output_hash"},
            "revise_plan": {"objective", "scope", "work_items", "capabilities", "budget", "report_structure", "source_refs"},
            "cancel_research": set(),
            "approve_capability": {"skill", "skill_name", "tools", "approval_request_id"},
            "approve_resource_extension": {"model_loops", "tool_calls", "seconds", "approval_request_id"},
            "decline_request": {"approval_request_id"},
        }[command]
        if set(scope) - allowed:
            raise ResearchCommandError("CAPABILITY_NOT_AUTHORIZED", "scope_json 超出命令允许范围")

    @staticmethod
    def _response(session, approval, *, plan=None, task=None):
        result = {"research_session_id": session.research_session_id, "status": session.status, "subject_version": session.current_plan_version, "approval": approval.to_dict() if approval is not None else None}
        if plan is not None:
            result["plan"] = plan.to_dict()
        if task is not None:
            result["research_task_id"] = task.research_task_id
            result["task"] = task.to_dict()
        return result


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


ResearchPlanAuthoringService = PlanApprovalService

__all__ = ["PlanApprovalService", "ResearchPlanAuthoringService", "ResearchCommandError"]
