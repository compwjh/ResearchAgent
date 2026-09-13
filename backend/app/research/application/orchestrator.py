"""Spec027 稳定受控骨架编排器（Task05 增量）。

编排流固定为 Spec027 §编排架构：
`plan -> fan-out search_catalog(>=2 并行) -> fan-in evaluate_papers -> check_coverage
-> bounded replan/search/evaluate/coverage -> synthesize_preliminary_report`。

约束（spec-027 §编排架构 / §Planner、Critic 与停止合同 / §动态模型和 Worker）：
- 状态变更**只能**走 ``store.update_task_status`` / ``store.update_work_item_status``
  （内部走 domain.state_machine 状态机），禁止任何直接 UPDATE。
- 每阶段前重新读 task：已处终态（如 cancelled）立即收尾返回，做到「取消后不再新增节点」。
- 9B Worker 并发额度经 ``ResourceProbe.arbitrate`` 裁决，无论成功失败都在 finally 里 release。
- 论文元数据不复制：选集只存 catalog_paper_id + relevance + facets_json + evidence_level。
- Re-plan 只在 coverage 有缺口时按 ``BUDGET_CAPS['max_replan_rounds']`` 有界生成新计划版本；
  已完成版本的 WorkItem 不回写。
- 禁止 paused 状态（Spec027 状态集无该态）；无 paused 相关分支。
- 论文文本一律视为不可信证据：本模块不做任何 LLM 调用，评估与覆盖判定只用确定性规则
  （排序与打分见 ``_evaluate_papers`` docstring），因此注入文本无法改变计划或工具集。
- 事件类型全部取自 ``contracts.EVENT_TYPES``；event_seq 由 store 原子领号，保证连续无洞。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from backend.app.research.application.planner import Planner
from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter
from backend.app.research.domain.contracts import BUDGET_CAPS, EVENT_TYPES, TASK_TERMINAL
from backend.app.research.domain.models import (
    PreliminaryReport,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchWorkItem,
)
from backend.app.research.domain.plan_validator import PlanRejected
from backend.app.research.domain.state_machine import InvalidStateTransition

# Spec027 只产生 catalog 级证据（不下载/分析全文，见 §明确不做）。
_EVIDENCE_LEVEL = "catalog"

# 检索失败时写回 WorkItem 的兜底错误码（adapter 已给码时优先用它）。
_DEFAULT_SEARCH_ERROR = "SOURCE_UNAVAILABLE"

# 报告状态（阶段报告）。
_REPORT_STATUS = "preliminary"


def _utcnow() -> str:
    """当前 UTC 时间戳，格式与 research_store._utcnow 一致：`YYYY-MM-DDTHH:MM:SSZ`。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class OrchestratorResult:
    """一次编排运行的收尾结果（不暴露内部异常细节）。"""

    research_task_id: str
    status: str  # 终态（completed/partial/failed/...）或当前状态
    plan_version: int
    selected_count: int
    report_id: str | None
    coverage_gaps: tuple[str, ...]
    degraded: bool
    error_code: str | None


class Orchestrator:
    """稳定受控骨架：plan -> search -> evaluate -> coverage -> bounded re-plan -> synthesize。"""

    def __init__(
        self, *, store, search_adapter=None, model_router=None, planner=None, probe=None, monotonic=None, agent_runner=None
    ) -> None:
        self._store = store
        # 检索唯一出口：Spec015 CatalogSearchAdapter（未注入时走其内部惰性装配）。
        self._adapter = search_adapter or CatalogSearchAdapter()
        # Task03 确定性骨架不调用 LLM；router 仅作为「记录实际模型/档位」的接缝保留。
        self._router = model_router
        # The Orchestrator is the sole owner of Runner dispatch.  Existing
        # deterministic Spec027 pipeline remains unchanged until a WorkItem is
        # explicitly handed to run_agent by the approved Task05+ integration.
        self._agent_runner = agent_runner
        self._planner = planner or Planner()
        self._monotonic = monotonic or time.monotonic
        # probe 默认 ResourceProbe()；惰性导入避免编排器模块在导入期就拉起 ollama 依赖。
        if probe is None:
            from backend.app.platform.ollama import ResourceProbe

            probe = ResourceProbe()
        self._probe = probe

    def run_agent(self, run_input):
        """Dispatch one approved WorkItem through the sole Runner seam."""
        if self._agent_runner is None:
            raise RuntimeError("agent runner is not configured")
        return self._agent_runner.run(run_input)

    # ------------------------------------------------------------------ #
    # 对外入口
    # ------------------------------------------------------------------ #

    def run(self, research_task_id: str, owner_id: str) -> OrchestratorResult:
        """执行一次完整编排；任何阶段已终态（取消/中断）都立即收尾返回。"""
        task = self._store.get_task(research_task_id, owner_id)
        if task is None:
            return self._result(research_task_id, "failed", 0, 0, None, (), False, "TASK_NOT_FOUND")
        # 终态不得回到 running：已终态任务原样返回（取消后不再新增节点）。
        if task.status in TASK_TERMINAL:
            return self._result(research_task_id, task.status, task.current_plan_version, 0, None, (), False, None)
        try:
            return self._run_pipeline(
                research_task_id,
                owner_id,
                plan_version=1,
                started_at=self._monotonic(),
            )
        except InvalidStateTransition:
            # 任务被取消/并发改态导致转移失败：不吞错，读出当前态原样返回。
            current = self._store.get_task(research_task_id, owner_id)
            status = current.status if current is not None else "failed"
            version = current.current_plan_version if current is not None else 0
            return self._result(research_task_id, status, version, 0, None, (), False, "INVALID_STATE_TRANSITION")
        except PlanRejected as exc:
            return self._reject(research_task_id, owner_id, 1, exc.code)

    def _reject(self, research_task_id: str, owner_id: str, plan_version: int, code: str) -> OrchestratorResult:
        """计划被拒：收敛为 failed 并发出 terminal 事件（不留 running 悬空）。"""
        self._emit(research_task_id, "terminal", {"status": "failed", "error_code": code})
        with suppress(InvalidStateTransition):
            self._store.update_task_status(research_task_id, owner_id, "failed")
        return self._result(research_task_id, "failed", plan_version, 0, None, (), False, code)

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #

    def _run_pipeline(
        self,
        research_task_id: str,
        owner_id: str,
        plan_version: int,
        *,
        started_at: float | None = None,
    ) -> OrchestratorResult:
        store = self._store
        started_at = self._monotonic() if started_at is None else started_at

        # 阶段 2：draft -> planning -> running（每阶段前重读 task，已终态即收尾）。
        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        # 幂等推进：服务层可能已同步推进过状态（create_task 的 planning、approve 后的 running），
        # 此时 planning->planning / running->planning 属非法转移，不得因此中断编排；已到位或
        # 不可转移就跳过（终态仍由 _refresh 拦住，绝不会从终态回到 running）。
        with suppress(InvalidStateTransition):
            store.update_task_status(research_task_id, owner_id, "planning")
            self._emit(research_task_id, "task", {"status": "planning"})
        with suppress(InvalidStateTransition):
            store.update_task_status(research_task_id, owner_id, "running")
            self._emit(research_task_id, "task", {"status": "running"})

        # 阶段 3：plan —— 确定性 Planner 产出受校验计划并落库。
        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        draft = self._planner.build_plan(
            goal=task.goal,
            quality_profile=task.quality_profile,
            target_paper_count=task.target_paper_count,
            language=task.language,
        )
        now = _utcnow()
        # review_plan_first 预建计划后由 approve 恢复运行时复用同一计划版本：plan v1 已存在
        # 就沿用（create_plan 重复会抛 ResearchPlanConflict，版本不可覆盖），不重建计划、
        # 不覆盖已产出证据，只补齐该版本下缺失的 WorkItem。
        existing_plan = store.get_current_plan(research_task_id)
        if existing_plan is not None and existing_plan.version == plan_version:
            draft = replace(draft, facets=self._parsed_facets(existing_plan.facets_json) or draft.facets)
        else:
            store.create_plan(
                ResearchPlan(
                    research_task_id=research_task_id,
                    version=plan_version,
                    planner_model=draft.planner_model,
                    rationale_summary=draft.rationale_summary,
                    facets_json=json.dumps(list(draft.facets), ensure_ascii=False),
                    status="active",
                    created_at=now,
                )
            )
        # 计划版本指针回写任务（store 白名单字段，非状态变更，状态仍只走 update_task_status），
        # 否则「取消后收尾」路径读到的 current_plan_version 会停在 0。
        store.update_task(research_task_id, owner_id, current_plan_version=plan_version)
        # WorkItem id 在库内必须唯一（`research_work_items.work_item_id` 是主键）：Planner 产出的
        # "s1"/"e1" 是**计划内**短 id，跨任务直接落库会撞 UNIQUE 约束，故统一加
        # research_task_id 前缀，dependencies 按同一映射改写（依赖只引用同任务节点）。
        id_map = {item["id"]: f"{research_task_id}-{item['id']}" for item in draft.work_items}
        # 复用计划时该版本可能已有 WorkItem（预建场景由 Planner 产出后落库过），有则跳过。
        if not store.list_work_items(research_task_id, plan_version=plan_version):
            store.create_work_items(
                research_task_id,
                [
                    ResearchWorkItem(
                        work_item_id=id_map[item["id"]],
                        research_task_id=research_task_id,
                        plan_version=plan_version,
                        task_type=item["task_type"],
                        role=item["role"],
                        depends_on_json=json.dumps(
                            [id_map.get(dep, dep) for dep in item["depends_on"]], ensure_ascii=False
                        ),
                        input_json=json.dumps(item["params"], ensure_ascii=False),
                        status="queued",
                        attempt=0,
                        created_at=now,
                        updated_at=now,
                    )
                    for item in draft.work_items
                ],
            )
        self._emit(
            research_task_id,
            "plan",
            {
                "plan_version": plan_version,
                "replan_round": 0,
                "stop_reason": "replan_pending",
                "facets": list(draft.facets),
                "items": [
                    {"id": id_map[item["id"]], "task_type": item["task_type"], "role": item["role"]}
                    for item in draft.work_items
                ],
            },
        )

        # Task05 production path: each WorkItem is executed exactly once by
        # the sole AgentRun Runner. The deterministic Spec027 search/state
        # pipeline remains available for callers that do not inject a Runner.
        if self._agent_runner is not None and self._store.get_session_by_task(research_task_id, owner_id) is not None:
            return self._run_agent_work_items(
                task=task,
                owner_id=owner_id,
                plan_version=plan_version,
            )

        candidates: list[str] = []  # 保序去重的候选 catalog_paper_id
        facets_by_paper: dict[str, list[str]] = {}
        degraded_sources: list[str] = []
        current_plan_version = plan_version
        replan_round = 0
        selected: list[dict] = []
        gaps: tuple[str, ...] = ()
        stop_reason = "coverage_satisfied"

        while True:
            if self._soft_budget_exhausted(started_at, task.soft_budget_seconds):
                current_task = self._refresh(research_task_id, owner_id)
                if isinstance(current_task, OrchestratorResult):
                    return current_task
                gaps = self._coverage_gaps(draft.facets, selected, facets_by_paper)
                stop_reason = "budget_exhausted"
                self._emit(
                    research_task_id,
                    "coverage",
                    {
                        "gaps": list(gaps),
                        "selected_count": len(selected),
                        "round": replan_round + 1,
                        "replan_round": replan_round,
                        "stop_reason": stop_reason,
                    },
                )
                break
            round_result = self._run_search_evaluate_coverage(
                research_task_id=research_task_id,
                owner_id=owner_id,
                plan_version=current_plan_version,
                facets=draft.facets,
                candidates=candidates,
                facets_by_paper=facets_by_paper,
                degraded_sources=degraded_sources,
                round_number=replan_round + 1,
            )
            if isinstance(round_result, OrchestratorResult):
                return round_result
            selected, gaps, new_candidate_count = round_result

            available_searches = BUDGET_CAPS["max_search_items"] - sum(
                item.task_type == "search_catalog" for item in store.list_work_items(research_task_id)
            )
            if self._soft_budget_exhausted(started_at, task.soft_budget_seconds):
                stop_reason = "budget_exhausted"
            elif not gaps:
                stop_reason = "coverage_satisfied"
            elif replan_round > 0 and new_candidate_count == 0:
                stop_reason = "no_new_evidence"
            elif replan_round >= BUDGET_CAPS["max_replan_rounds"]:
                stop_reason = "replan_limit"
            elif available_searches <= 0:
                stop_reason = "search_item_cap"
            else:
                stop_reason = "replan_pending"
            self._emit(
                research_task_id,
                "coverage",
                {
                    "gaps": list(gaps),
                    "selected_count": len(selected),
                    "round": replan_round + 1,
                    "replan_round": replan_round,
                    "stop_reason": stop_reason,
                },
            )
            # 首轮缺口也允许先尝试一次补搜；后续若没有新增 catalog 证据则收敛为 partial。
            if stop_reason != "replan_pending":
                break

            current_task = self._refresh(research_task_id, owner_id)
            if isinstance(current_task, OrchestratorResult):
                return current_task
            next_version = current_plan_version + 1
            next_gaps = gaps[:available_searches]
            self._create_replan(
                research_task_id=research_task_id,
                previous_plan_version=current_plan_version,
                next_plan_version=next_version,
                draft=draft,
                task=current_task,
                gaps=next_gaps,
                round_number=replan_round + 1,
            )
            current_plan_version = next_version
            replan_round += 1

        # 阶段 7：synthesize_preliminary_report（catalog 证据；局限写入 limitations_json）。
        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        markdown = self._build_report(
            goal=task.goal,
            facets=draft.facets,
            selected=selected,
            facets_by_paper=facets_by_paper,
            gaps=gaps,
        )
        limitations = {
            "missing_facets": list(gaps),
            "degraded_sources": degraded_sources,
            "evidence_level": _EVIDENCE_LEVEL,
            "replan_round": replan_round,
            "stop_reason": stop_reason,
        }
        report = PreliminaryReport(
            report_id=f"report-{research_task_id}-v{current_plan_version}",
            research_task_id=research_task_id,
            plan_version=current_plan_version,
            status=_REPORT_STATUS,
            markdown=markdown,
            limitations_json=json.dumps(limitations, ensure_ascii=False),
            created_at=_utcnow(),
        )
        store.save_report(report)
        completed_task = self._refresh(research_task_id, owner_id)
        if isinstance(completed_task, OrchestratorResult):
            return completed_task
        current_plan = store.get_plan(research_task_id, current_plan_version)
        if current_plan is not None and current_plan.status == "active":
            store.update_plan_status(research_task_id, current_plan_version, "completed")
        syn_item = self._find_item(research_task_id, current_plan_version, "synthesize_preliminary_report")
        if syn_item is not None:
            running_item = store.update_work_item_status(
                syn_item.work_item_id,
                "running",
                **self._model_kwargs(
                    syn_item.role,
                    research_task_id=research_task_id,
                    task_type=syn_item.task_type,
                ),
            )
            self._emit(
                research_task_id,
                "worker",
                self._worker_event_payload(running_item, "running"),
            )
            completed_item = store.update_work_item_status(syn_item.work_item_id, "completed")
            self._emit(
                research_task_id,
                "worker",
                self._worker_event_payload(completed_item, "completed"),
            )
        self._emit(
            research_task_id,
            "report",
            {
                "report_id": report.report_id,
                "plan_version": current_plan_version,
                "replan_round": replan_round,
                "stop_reason": stop_reason,
            },
        )

        # 阶段 8：收尾（无入选 / 有缺口 / 有降级来源 -> partial，否则 completed）。
        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        degraded = bool(gaps) or bool(degraded_sources) or stop_reason == "budget_exhausted"
        final_status = "partial" if (not selected or degraded) else "completed"
        store.update_task_status(research_task_id, owner_id, final_status)
        self._emit(
            research_task_id,
            "terminal",
            {
                "status": final_status,
                "selected_count": len(selected),
                "gaps": list(gaps),
                "replan_round": replan_round,
                "stop_reason": stop_reason,
            },
        )
        return self._result(
            research_task_id,
            final_status,
            current_plan_version,
            len(selected),
            report.report_id,
            gaps,
            degraded,
            None,
        )

    def _run_agent_work_items(self, *, task, owner_id: str, plan_version: int) -> OrchestratorResult:
        """Create and dispatch one complete AgentRunInput per WorkItem."""
        from backend.app.research.application.agent_runtime import ROLE_SKILL_DEFAULTS, AgentRunInput

        session = self._store.get_session_by_task(task.research_task_id, owner_id)
        if session is None:
            with suppress(InvalidStateTransition):
                self._store.update_task_status(task.research_task_id, owner_id, "failed")
            return self._result(task.research_task_id, "failed", plan_version, 0, None, (), False, "SESSION_NOT_FOUND")
        approved_capabilities: dict[str, dict] = {}
        budget_snapshot: dict = {}
        session_plan = self._store.get_session_plan(session.research_session_id, owner_id, plan_version)
        if session_plan is not None:
            try:
                raw_capabilities = json.loads(session_plan.capabilities_json or "[]")
            except (TypeError, ValueError):
                raw_capabilities = []
            for envelope in raw_capabilities if isinstance(raw_capabilities, list) else ():
                skill = envelope.get("skill") if isinstance(envelope, dict) else None
                if isinstance(skill, dict) and skill.get("name"):
                    approved_capabilities[skill["name"]] = envelope
            try:
                decoded_budget = json.loads(session_plan.budget_json or "{}")
                if isinstance(decoded_budget, dict):
                    budget_snapshot = decoded_budget
            except (TypeError, ValueError):
                budget_snapshot = {}
        role_map = {
            "search-worker": "search_worker", "paper-evaluator": "paper_evaluator",
            "research-critic": "research_critic", "synthesizer": "synthesizer",
        }
        failures = 0
        items = self._store.list_work_items(task.research_task_id, plan_version=plan_version)
        for item in items:
            role = role_map.get(item.role, item.role)
            skill_name = ROLE_SKILL_DEFAULTS.get(role)
            capability = approved_capabilities.get(skill_name) if skill_name else None
            try:
                work_item_input = json.loads(item.input_json or "{}")
            except (TypeError, ValueError):
                work_item_input = {}
            run_id = f"{item.work_item_id}:run-{max(1, item.attempt + 1)}"
            try:
                result = self.run_agent(AgentRunInput(
                    agent_run_id=run_id,
                    research_session_id=session.research_session_id,
                    research_task_id=task.research_task_id,
                    work_item_id=item.work_item_id,
                    owner_id=owner_id,
                    role=role,
                    work_item_input=work_item_input if isinstance(work_item_input, dict) else {},
                    skill_snapshot=capability,
                    tool_snapshot=capability.get("tools", ()) if capability else None,
                    budget_snapshot=budget_snapshot,
                    attempt=max(1, item.attempt + 1),
                    resolved_model=item.resolved_model or "",
                    reasoning_effort="off",
                ))
            except Exception:
                failures += 1
                with suppress(Exception):
                    failed_item = self._store.update_work_item_status(item.work_item_id, "failed", error_code="AGENT_RUN_FAILED")
                    self._emit(task.research_task_id, "worker", self._worker_event_payload(failed_item, "failed", error_code="AGENT_RUN_FAILED"))
                continue
            terminal = result.status if result.status in {"completed", "failed", "cancelled", "limit_reached"} else "failed"
            if terminal != "completed":
                failures += 1
            error_code = result.error_code
            output_json = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)[:100000]
            with suppress(Exception):
                updated = self._store.update_work_item_status(
                    item.work_item_id,
                    "completed" if terminal == "completed" else ("cancelled" if terminal == "cancelled" else "failed"),
                    output_json=output_json,
                    error_code=error_code,
                    resolved_model=result.model_metadata.get("model") if result.model_metadata else None,
                )
                self._emit(task.research_task_id, "worker", self._worker_event_payload(updated, terminal, error_code=error_code) )
        final_status = "completed" if items and failures == 0 else "partial"
        with suppress(InvalidStateTransition):
            self._store.update_task_status(task.research_task_id, owner_id, final_status)
        self._emit(task.research_task_id, "terminal", {"status": final_status, "selected_count": 0, "error_code": None if failures == 0 else "AGENT_RUN_FAILED"})
        return self._result(task.research_task_id, final_status, plan_version, 0, None, (), failures > 0, None if failures == 0 else "AGENT_RUN_FAILED")

    def _run_search_evaluate_coverage(
        self,
        *,
        research_task_id: str,
        owner_id: str,
        plan_version: int,
        facets: tuple[str, ...],
        candidates: list[str],
        facets_by_paper: dict[str, list[str]],
        degraded_sources: list[str],
        round_number: int,
    ):
        """执行一个计划版本的 search -> evaluate -> coverage 轮次。"""
        store = self._store
        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        search_items = [
            item
            for item in store.list_work_items(research_task_id, plan_version=plan_version)
            if item.task_type == "search_catalog"
        ]
        requested = len(search_items)
        before_candidates = len(candidates)
        try:
            granted, probe_code = self._probe.arbitrate(research_task_id, requested)
            if probe_code is not None:
                self._emit(research_task_id, "worker", {"code": probe_code, "granted": granted})
            if probe_code:
                degraded_sources.append(f"probe:{probe_code}")
            slots = max(1, granted)
            if requested and granted > 0:
                with ThreadPoolExecutor(max_workers=slots) as pool:
                    futures = [
                        (item, pool.submit(self._run_search, research_task_id, item, f"w{index % slots}"))
                        for index, item in enumerate(search_items)
                    ]
                    for item, future in futures:
                        ids, error_code = self._collect_search(future)
                        if not ids:
                            degraded_sources.append(f"{item.work_item_id}:{error_code}")
                            continue
                        facet = self._facet_of(item)
                        for paper_id in ids:
                            if paper_id not in facets_by_paper:
                                facets_by_paper[paper_id] = []
                                candidates.append(paper_id)
                            if facet and facet not in facets_by_paper[paper_id]:
                                facets_by_paper[paper_id].append(facet)
            elif requested:
                for item in search_items:
                    updated_item = store.update_work_item_status(
                        item.work_item_id, "failed", error_code="RESOURCE_PROBE_FAILED"
                    )
                    self._emit(
                        research_task_id,
                        "worker",
                        self._worker_event_payload(
                            updated_item,
                            "failed",
                            error_code="RESOURCE_PROBE_FAILED",
                        ),
                    )
                    degraded_sources.append(f"{item.work_item_id}:RESOURCE_PROBE_FAILED")
        finally:
            self._probe.release(research_task_id)

        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        # Prefer real CatalogPaper snapshots for Task06 evaluation.  Offline
        # Spec027 fakes intentionally have ID-only candidates, so retain the
        # old stable-rank fallback when no snapshot exists.
        # The research store intentionally keeps only catalog IDs.  A real
        # Task06 adapter may expose the existing PaperDiscoveryStore after its
        # first search; ID-only Spec027 fakes must retain the old fallback.
        catalog_store = getattr(self._adapter, "_store", None)
        get_catalog_paper = getattr(catalog_store, "get_catalog_paper", None)
        catalog_rows = [get_catalog_paper(paper_id) for paper_id in candidates] if callable(get_catalog_paper) else []
        catalog_rows = [row for row in catalog_rows if row is not None]
        if catalog_rows:
            from backend.app.research.application.search_catalog_adapter import PaperEvaluator

            eval_output = PaperEvaluator(threshold=0.2, soft_floor=0.1).evaluate(
                [
                    {"catalog_paper_id": row.catalog_paper_id, "title": row.title,
                     "abstract": row.abstract or "", "keywords": row.keywords}
                    for row in catalog_rows
                ],
                query=task.goal,
            )
            kept_ids = {item["candidate_id"] for item in eval_output["kept"]}
            selected = self._evaluate_papers(
                [paper_id for paper_id in candidates if paper_id in kept_ids],
                facets_by_paper,
                task.target_paper_count,
            )
            evaluations = eval_output["evaluations"]
            evaluation_statistics = eval_output["statistics"]
        else:
            selected = self._evaluate_papers(candidates, facets_by_paper, task.target_paper_count)
            selected_by_id = {item["catalog_paper_id"]: item for item in selected}
            evaluations = [
                {
                    "candidate_id": paper_id,
                    "relevance_score": float(selected_by_id.get(paper_id, {}).get("relevance", 0.0)),
                    "keep": paper_id in selected_by_id,
                    "reason": "selected by facet coverage and stable rank" if paper_id in selected_by_id
                    else "not selected: target paper capacity reached",
                    "evidence_refs": [f"catalog:{paper_id}"],
                }
                for paper_id in candidates
            ]
            evaluation_statistics = {
                "candidates": len(candidates), "kept": len(selected),
                "eliminated": max(0, len(candidates) - len(selected)),
                "threshold": 0.2, "effective_threshold": 0.2,
            }
        eval_item = self._find_item(research_task_id, plan_version, "evaluate_papers")
        if eval_item is not None:
            running_item = store.update_work_item_status(
                eval_item.work_item_id,
                "running",
                **self._model_kwargs(
                    eval_item.role,
                    research_task_id=research_task_id,
                    task_type=eval_item.task_type,
                ),
            )
            self._emit(research_task_id, "worker", self._worker_event_payload(running_item, "running"))
            completed_item = store.update_work_item_status(
                eval_item.work_item_id,
                "completed",
                output_json=json.dumps(
                    {
                        "selected": [item["catalog_paper_id"] for item in selected],
                        "candidate_count": len(candidates),
                        "evaluations": evaluations,
                        "statistics": evaluation_statistics,
                    },
                    ensure_ascii=False,
                ),
            )
            self._emit(
                research_task_id,
                "worker",
                self._worker_event_payload(completed_item, "completed", selected_count=len(selected)),
            )
        store.replace_selections(
            research_task_id,
            [
                ResearchPaperSelection(
                    research_task_id=research_task_id,
                    catalog_paper_id=item["catalog_paper_id"],
                    relevance=item["relevance"],
                    facets_json=json.dumps(item["facets"], ensure_ascii=False),
                    evidence_level=item["evidence_level"],
                    created_at=_utcnow(),
                )
                for item in selected
            ],
        )

        task = self._refresh(research_task_id, owner_id)
        if isinstance(task, OrchestratorResult):
            return task
        gaps = self._coverage_gaps(facets, selected, facets_by_paper)
        cov_item = self._find_item(research_task_id, plan_version, "check_coverage")
        if cov_item is not None:
            running_item = store.update_work_item_status(
                cov_item.work_item_id,
                "running",
                **self._model_kwargs(
                    cov_item.role,
                    research_task_id=research_task_id,
                    task_type=cov_item.task_type,
                ),
            )
            self._emit(research_task_id, "worker", self._worker_event_payload(running_item, "running"))
            completed_item = store.update_work_item_status(
                cov_item.work_item_id,
                "completed",
                output_json=json.dumps(
                    {
                        "coverage": {
                            "facets": list(facets),
                            "covered": [facet for facet in facets if facet not in gaps],
                        },
                        "gaps": [{"facet": gap, "reason": "no selected evidence"} for gap in gaps],
                        "recommendations": list(gaps[:2]),
                        "bounded_replan": bool(gaps),
                        "approval_required": False,
                    },
                    ensure_ascii=False,
                ),
            )
            self._emit(research_task_id, "worker", self._worker_event_payload(completed_item, "completed"))
        return selected, gaps, len(candidates) - before_candidates

    def _create_replan(
        self,
        *,
        research_task_id: str,
        previous_plan_version: int,
        next_plan_version: int,
        draft,
        task,
        gaps: tuple[str, ...],
        round_number: int,
    ) -> None:
        """为 coverage 缺口创建不可覆盖的新计划版本及最小补搜链路。"""
        store = self._store
        now = _utcnow()
        prefix = f"{research_task_id}-v{next_plan_version}-r{round_number}"
        replan_id = f"{prefix}-replan"
        search_ids = [f"{prefix}-s{index}" for index in range(1, len(gaps) + 1)]
        evaluate_id = f"{prefix}-e1"
        coverage_id = f"{prefix}-c1"
        synthesize_id = f"{prefix}-syn"
        previous_coverage = self._find_item(research_task_id, previous_plan_version, "check_coverage")
        search_items = [
            {
                "id": search_id,
                "task_type": "search_catalog",
                "role": "search-worker",
                "depends_on": [],
                "params": {
                    "query": f"{task.goal} {gap}",
                    "facets": [gap],
                    "max_results": max(1, task.target_paper_count // max(1, len(gaps))),
                    "language": task.language,
                },
            }
            for search_id, gap in zip(search_ids, gaps, strict=True)
        ]
        work_items = [
            ResearchWorkItem(
                work_item_id=replan_id,
                research_task_id=research_task_id,
                plan_version=next_plan_version,
                task_type="replan",
                role="planner",
                depends_on_json=json.dumps(
                    [previous_coverage.work_item_id] if previous_coverage is not None else [],
                    ensure_ascii=False,
                ),
                input_json=json.dumps(
                    {
                        "rationale": "coverage gaps require bounded catalog search",
                        "add_search_for_facets": list(gaps),
                    },
                    ensure_ascii=False,
                ),
                status="queued",
                attempt=0,
                created_at=now,
                updated_at=now,
            ),
            *[
                ResearchWorkItem(
                    work_item_id=item["id"],
                    research_task_id=research_task_id,
                    plan_version=next_plan_version,
                    task_type=item["task_type"],
                    role=item["role"],
                    depends_on_json=json.dumps(item["depends_on"], ensure_ascii=False),
                    input_json=json.dumps(item["params"], ensure_ascii=False),
                    status="queued",
                    attempt=0,
                    created_at=now,
                    updated_at=now,
                )
                for item in search_items
            ],
            ResearchWorkItem(
                work_item_id=evaluate_id,
                research_task_id=research_task_id,
                plan_version=next_plan_version,
                task_type="evaluate_papers",
                role="paper-evaluator",
                depends_on_json=json.dumps(search_ids, ensure_ascii=False),
                input_json=json.dumps(
                    {"catalog_paper_ids": [], "relevance_threshold": 0.2, "facets": list(draft.facets)},
                    ensure_ascii=False,
                ),
                status="queued",
                attempt=0,
                created_at=now,
                updated_at=now,
            ),
            ResearchWorkItem(
                work_item_id=coverage_id,
                research_task_id=research_task_id,
                plan_version=next_plan_version,
                task_type="check_coverage",
                role="research-critic",
                depends_on_json=json.dumps([evaluate_id], ensure_ascii=False),
                input_json=json.dumps({"goal": task.goal, "gap_threshold": 0.3}, ensure_ascii=False),
                status="queued",
                attempt=0,
                created_at=now,
                updated_at=now,
            ),
            ResearchWorkItem(
                work_item_id=synthesize_id,
                research_task_id=research_task_id,
                plan_version=next_plan_version,
                task_type="synthesize_preliminary_report",
                role="synthesizer",
                depends_on_json=json.dumps([coverage_id], ensure_ascii=False),
                input_json=json.dumps(
                    {
                        "goal": task.goal,
                        "selected_paper_ids": [],
                        "language": task.language,
                        "evidence_level": _EVIDENCE_LEVEL,
                    },
                    ensure_ascii=False,
                ),
                status="queued",
                attempt=0,
                created_at=now,
                updated_at=now,
            ),
        ]
        store.create_plan(
            ResearchPlan(
                research_task_id=research_task_id,
                version=next_plan_version,
                planner_model=draft.planner_model,
                rationale_summary=f"bounded re-plan round {round_number}: coverage gaps",
                facets_json=json.dumps(list(draft.facets), ensure_ascii=False),
                status="active",
                created_at=now,
            )
        )
        store.update_plan_status(research_task_id, previous_plan_version, "superseded")
        store.update_task(research_task_id, task.owner_id, current_plan_version=next_plan_version)
        store.create_work_items(research_task_id, work_items)
        self._emit(
            research_task_id,
            "plan",
            {
                "plan_version": next_plan_version,
                "previous_plan_version": previous_plan_version,
                "replan_round": round_number,
                "stop_reason": "replan_pending",
                "facets": list(gaps),
                "items": [
                    {"id": item.work_item_id, "task_type": item.task_type, "role": item.role}
                    for item in work_items
                ],
            },
        )
        replan_item = store.update_work_item_status(
            replan_id,
            "running",
            **self._model_kwargs(
                "planner",
                research_task_id=research_task_id,
                task_type="replan",
            ),
        )
        self._emit(research_task_id, "worker", self._worker_event_payload(replan_item, "running"))
        completed_replan = store.update_work_item_status(
            replan_id,
            "completed",
            output_json=json.dumps({"add_search_for_facets": list(gaps)}, ensure_ascii=False),
        )
        self._emit(
            research_task_id,
            "worker",
            self._worker_event_payload(completed_replan, "completed"),
        )

    # ------------------------------------------------------------------ #
    # 内部：单个 search worker
    # ------------------------------------------------------------------ #

    def _run_search(self, research_task_id: str, item: ResearchWorkItem, slot: str) -> tuple[list[str], str | None]:
        """执行单条 search_catalog：queued -> running -> completed/failed，并 emit worker 事件。

        返回 ``(catalog_paper_ids, error_code)``；成功时 error_code 为 None。
        检索唯一出口是 ``CatalogSearchAdapter``（Spec015），本方法不自建第二套检索。
        """
        store = self._store
        running_item = store.update_work_item_status(
            item.work_item_id,
            "running",
            worker_slot=slot,
            **self._model_kwargs(
                item.role,
                research_task_id=research_task_id,
                task_type=item.task_type,
            ),
        )
        self._emit(
            research_task_id,
            "worker",
            self._worker_event_payload(running_item, "running"),
        )
        params = item.input_params
        try:
            # Search Worker is the structured application seam; it delegates
            # to the same CatalogSearchAdapter/Spec015 graph and does not add
            # another source or model client.
            from backend.app.research.application.search_catalog_adapter import SearchWorker

            worker_output = SearchWorker(adapter=self._adapter).run(
                {**params, "work_item_id": item.work_item_id}
            )
            ids = list(worker_output.get("candidates") or ())
            error_code = worker_output.get("refresh_diagnostics", {}).get("error_code")
        except Exception:
            worker_output = None
            ids, error_code = [], None
        if not ids:
            # 拿不到结果不伪造：写失败码（adapter 已给码优先，否则 SOURCE_UNAVAILABLE）。
            error_code = error_code or _DEFAULT_SEARCH_ERROR
            failed_item = store.update_work_item_status(item.work_item_id, "failed", error_code=error_code)
            self._emit(
                research_task_id,
                "worker",
                self._worker_event_payload(failed_item, "failed", error_code=error_code),
            )
            return [], error_code
        completed_item = store.update_work_item_status(
            item.work_item_id,
            "completed",
            output_json=json.dumps(
                {"catalog_paper_ids": ids, "search_worker": worker_output or {}},
                ensure_ascii=False,
            ),
        )
        self._emit(
            research_task_id,
            "worker",
            self._worker_event_payload(completed_item, "completed", catalog_paper_ids=ids),
        )
        return ids, None

    def _collect_search(self, future) -> tuple[list[str], str]:
        """取 search future 结果；线程内异常一律视为检索失败（不冒泡、不伪造结果）。"""
        try:
            return future.result()
        except Exception:
            return [], _DEFAULT_SEARCH_ERROR

    # ------------------------------------------------------------------ #
    # 内部：确定性评估 / 覆盖 / 报告（不调用 LLM）
    # ------------------------------------------------------------------ #

    def _evaluate_papers(
        self, candidates: list[str], facets_by_paper: dict[str, list[str]], target_paper_count: int
    ) -> list[dict]:
        """确定性评估（无 LLM）：按「命中 facet 数 + 出现顺序」排序后取前 N 篇。

        评分规则（可复现、可审计，写进 docstring 以便评审）：
        - 命中 facet 数 = 该 catalog_paper_id 被多少路 facet 检索召回（``facets_by_paper``）；
        - 先按命中数降序，命中数相同按候选出现顺序（保序去重后的下标）升序；
        - ``relevance = round(max(0.0, 1.0 - rank / max(1, total)), 4)``，rank 为排序后下标，
          total 为候选总数；
        - 取前 ``min(target_paper_count, BUDGET_CAPS["max_selected"])`` 篇；
        - ``evidence_level`` 恒为 catalog（Spec027 不下载全文）。

        之所以不读取论文标题/摘要等元数据：Spec027 禁止把论文元数据复制到 027 的表，且论文
        文本是不可信证据——读入即等于引入注入面。
        """
        total = max(1, len(candidates))
        cap = min(int(target_paper_count), BUDGET_CAPS["max_selected"])
        ordered = sorted(
            enumerate(candidates),
            key=lambda pair: (-len(facets_by_paper.get(pair[1], ())), pair[0]),
        )
        selected: list[dict] = []
        for rank, (_index, paper_id) in enumerate(ordered[:cap]):
            selected.append(
                {
                    "catalog_paper_id": paper_id,
                    "relevance": round(max(0.0, 1.0 - rank / total), 4),
                    "facets": list(facets_by_paper.get(paper_id, [])),
                    "evidence_level": _EVIDENCE_LEVEL,
                }
            )
        return selected

    @staticmethod
    def _coverage_gaps(
        facets: tuple[str, ...], selected: list[dict], facets_by_paper: dict[str, list[str]]
    ) -> tuple[str, ...]:
        """覆盖缺口 = 没有任何入选论文命中的 facet。"""
        covered: set[str] = set()
        for item in selected:
            covered.update(facets_by_paper.get(item["catalog_paper_id"], ()))
        return tuple(facet for facet in facets if facet not in covered)

    def _build_report(
        self,
        *,
        goal: str,
        facets: tuple[str, ...],
        selected: list[dict],
        facets_by_paper: dict[str, list[str]],
        gaps: tuple[str, ...],
    ) -> str:
        """生成 markdown 报告：goal、facet 小标题、按 facet 列出 catalog_paper_id 引用、局限段。

        引用一律用 ``catalog_paper_id``（Spec015 全局目录引用），不复制任何论文元数据。
        """
        lines = [
            "# 初步研究报告（Spec027 动态编排 MVP）",
            "",
            f"**研究目标**：{goal}",
            "",
            f"**证据等级**：{_EVIDENCE_LEVEL}（仅目录/摘要，未下载全文；论文文本视为不可信证据）",
            "",
            f"**入选论文数**：{len(selected)}",
            "",
            "## 研究子方向",
        ]
        lines.extend(f"- {facet}" for facet in facets)
        lines.append("")
        lines.append("## 各子方向相关论文")
        for facet in facets:
            lines.append(f"### {facet}")
            refs = [
                item["catalog_paper_id"]
                for item in selected
                if facet in facets_by_paper.get(item["catalog_paper_id"], ())
            ]
            if refs:
                lines.extend(f"- `{paper_id}`（catalog 引用，relevance 见论文选集）" for paper_id in refs)
            else:
                lines.append("- （该子方向未获得入选论文）")
            lines.append("")
        lines.append("## 局限")
        if gaps:
            lines.append(f"- 以下子方向未获得入选论文：{'、'.join(gaps)}。")
        else:
            lines.append("- 各子方向均有入选论文支撑。")
        lines.append("- 证据等级为 catalog：未下载或分析全文，结论不可据此推断方法与实验细节。")
        lines.append("- 仅执行有界 catalog 补搜；仍未覆盖的子方向保留在本报告与 limitations 中。")
        lines.append("")
        lines.append("> 所有结论均须带论文引用；此处仅以 catalog_paper_id 引用 Spec015 全局目录，不复制元数据。")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 内部：读 task / 找 item / 事件与结果
    # ------------------------------------------------------------------ #

    def _refresh(self, research_task_id: str, owner_id: str):
        """重读 task；不存在返回 TASK_NOT_FOUND 结果，已终态返回当前态结果，否则返回 task。"""
        task = self._store.get_task(research_task_id, owner_id)
        if task is None:
            return self._result(research_task_id, "failed", 0, 0, None, (), False, "TASK_NOT_FOUND")
        if task.status in TASK_TERMINAL:
            return self._result(research_task_id, task.status, task.current_plan_version, 0, None, (), False, None)
        return task

    def _find_item(self, research_task_id: str, plan_version: int, task_type: str):
        """取本计划版本下某类型的第一个 WorkItem（本骨架每类型唯一）。"""
        for item in self._store.list_work_items(research_task_id, plan_version=plan_version):
            if item.task_type == task_type:
                return item
        return None

    @staticmethod
    def _parsed_facets(raw: str) -> tuple[str, ...]:
        """解析计划 facets_json；空值/非法 JSON/非 list 返回空元组（复用计划时回退 Planner facets）。"""
        if not raw:
            return ()
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return ()
        if not isinstance(value, list):
            return ()
        return tuple(str(item) for item in value)

    @staticmethod
    def _facet_of(item: ResearchWorkItem) -> str:
        """取 search_catalog 参数里的 facet（params.facets[0]）；缺失返回空串。"""
        facets = item.input_params.get("facets") or []
        return facets[0] if facets else ""

    def _soft_budget_exhausted(self, started_at: float, soft_budget_seconds: int) -> bool:
        """返回软预算是否已到达；仅在阶段边界阻止尚未开始的新工作。"""
        return self._monotonic() - started_at >= max(0, int(soft_budget_seconds))

    def _model_kwargs(self, role: str, *, research_task_id: str | None = None, task_type: str | None = None) -> dict:
        """解析实际模型并转发安全的 router 事件；未注入 router 时保持确定性骨架。

        Runner 是唯一模型执行出口；此处只解析 WorkItem 的展示/审计字段，绝不执行模型。
        """
        if self._router is None:
            return {}
        resolve = getattr(self._router, "resolve", None)
        if callable(resolve):
            choice = resolve(role=role, task_type=task_type)
            return {"model_tier": choice.tier, "resolved_model": choice.model}
        # Preserve the Spec027 router seam used by existing offline tests and
        # older adapters while keeping model events safe and structured.
        execute = getattr(self._router, "execute", None)
        if callable(execute):
            choice, _result, events = execute(role=role, task_type=task_type, invoke=lambda _model: None)
            for event in events or ():
                safe = self._safe_model_event_payload(event)
                if safe is not None and research_task_id:
                    self._emit(research_task_id, "model", safe)
            return {"model_tier": choice.tier, "resolved_model": choice.model}
        raise AttributeError("model router does not expose resolve or execute")

    @staticmethod
    def _safe_model_event_payload(event: object) -> dict | None:
        """只接受升级事件的稳定字段，拒绝 prompt/论文文本等任意 router 扩展字段。"""
        if not isinstance(event, dict) or event.get("code") != "MODEL_ESCALATED":
            return None
        if event.get("from_tier") != "fast" or event.get("to_tier") != "strong":
            return None
        return {
            "code": "MODEL_ESCALATED",
            "from_tier": "fast",
            "to_tier": "strong",
            "reason": "fast output invalid after one retry",
        }

    @staticmethod
    def _worker_event_payload(item: ResearchWorkItem, status: str, **extra) -> dict:
        """从状态更新后的 WorkItem 构造安全 worker 事件，不包含 Prompt 或思维链。"""
        payload = {
            "work_item_id": item.work_item_id,
            "task_type": item.task_type,
            "role": item.role,
            "status": status,
        }
        for field in ("model_tier", "resolved_model", "worker_slot"):
            value = getattr(item, field, None)
            if value is not None:
                payload[field] = value
        payload.update(extra)
        return payload

    def _emit(self, research_task_id: str, event_type: str, payload: dict) -> None:
        """追加事件；event_type 必须来自 contracts.EVENT_TYPES（安全 payload 由 store 序列化）。"""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event_type}")
        self._store.append_event(research_task_id, event_type, payload)

    @staticmethod
    def _result(task_id, status, version, selected_count, report_id, gaps, degraded, error_code) -> OrchestratorResult:
        return OrchestratorResult(
            research_task_id=task_id,
            status=status,
            plan_version=version,
            selected_count=selected_count,
            report_id=report_id,
            coverage_gaps=tuple(gaps),
            degraded=degraded,
            error_code=error_code,
        )
