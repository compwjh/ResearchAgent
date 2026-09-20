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
- paused 是 Spec028 的持久化调度闸门；暂停时不派发新节点，恢复仍复用本编排器。
- 论文文本一律视为不可信证据：本模块不做任何 LLM 调用，评估与覆盖判定只用确定性规则
  （排序与打分见 ``_evaluate_papers`` docstring），因此注入文本无法改变计划或工具集。
- 事件类型全部取自 ``contracts.EVENT_TYPES``；event_seq 由 store 原子领号，保证连续无洞。
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from backend.app.research.application.planner import Planner
from backend.app.research.application.report_synthesis import (
    ReportDeliveryService,
    ReportSynthesisError,
    ReportSynthesizer,
    ResearchNotificationService,
    validate_report_synthesis_output,
)
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

logger = logging.getLogger(__name__)

# Spec027 只产生 catalog 级证据（不下载/分析全文，见 §明确不做）。
_EVIDENCE_LEVEL = "catalog"

# 检索失败时写回 WorkItem 的兜底错误码（adapter 已给码时优先用它）。
_DEFAULT_SEARCH_ERROR = "SOURCE_UNAVAILABLE"

# 报告状态（阶段报告）。
_REPORT_STATUS = "preliminary"

# Keep a minimally useful evidence set when the catalog already returned at
# least five candidates.  This does not create candidates or download papers;
# it only raises the deterministic selection cap within the existing pool.
_MIN_REPORT_CANDIDATES = 5


def _utcnow() -> str:
    """当前 UTC 时间戳，格式与 research_store._utcnow 一致：`YYYY-MM-DDTHH:MM:SSZ`。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _work_item_output(value) -> dict:
    """Read only the safe structured output persisted by AgentRunner."""
    raw = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except (TypeError, ValueError):
            return {}
    if isinstance(raw, dict) and isinstance(raw.get("output_json"), dict):
        return dict(raw["output_json"])
    return dict(raw) if isinstance(raw, dict) else {}


def _recall_allowlist_from_search_outputs(search_outputs: Iterable[Mapping[str, Any]]) -> set[str]:
    """Collect the catalog IDs the Search Workers actually recalled.

    ``search_outputs`` are the already-sanitized per-Worker outputs as held in
    ``completed_outputs``.  This set is the sole authority for expanding
    aggregate evaluator refs — it is read from ``candidates`` / ``evidence_refs``
    / ``citation_allowlist`` exactly as the synthesizer branch did inline.  The
    local catalog directory may only backfill *metadata* for these IDs (never
    enlarge the recall set) in ``_validated_evaluator_candidates``.

    Note: a Search Worker's stored ``output_json`` is the AgentRun wrapper; the
    inner ``output_json.output_json`` (extracted by ``_work_item_output``) carries
    ``candidates``.  The orchestrator always passes the extracted inner dict here.
    """
    allowlist: set[str] = set()
    for output in search_outputs:
        if not isinstance(output, Mapping):
            continue
        for paper_id in output.get("candidates", ()) if isinstance(output.get("candidates"), list) else ():
            if isinstance(paper_id, str) and paper_id:
                allowlist.add(paper_id)
        for ref in output.get("evidence_refs", ()) if isinstance(output.get("evidence_refs"), list) else ():
            if isinstance(ref, str) and ref.startswith("catalog:"):
                allowlist.add(ref.split(":", 1)[1])
        for ref in output.get("citation_allowlist", ()) if isinstance(output.get("citation_allowlist"), list) else ():
            ref_value = ref.get("citation_ref", "") if isinstance(ref, dict) else ref
            if isinstance(ref_value, str) and ref_value.startswith("catalog:"):
                allowlist.add(ref_value.split(":", 1)[1])
    return allowlist


def _catalog_evidence_view(output: Mapping[str, Any], tool_results: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Build the bounded Search→Evaluator evidence handoff.

    Search Worker output intentionally carries stable catalog IDs rather than
    copying paper metadata.  The Runner's already-sanitized catalog ToolResult
    is the only permitted source for the small amount of title/abstract context
    the Evaluator needs to make a relevance decision.  Keep this view local to
    the next WorkItem; it is not a new retrieval path or a persisted raw
    response, and candidate/ref IDs remain bound to the Search output.
    """
    candidate_ids = {
        str(value).strip()
        for value in output.get("candidates", ())
        if isinstance(value, str) and value.strip()
    }
    if not candidate_ids:
        return []
    evidence: list[dict] = []
    for result in tool_results or ():
        if not isinstance(result, Mapping):
            continue
        if result.get("name") != "search_paper_catalog" or result.get("status") != "ok":
            continue
        ids = [
            str(value).strip()
            for value in result.get("catalog_paper_ids", ())
            if isinstance(value, str) and value.strip() in candidate_ids
        ]
        summary = result.get("summary")
        if not ids and not isinstance(summary, str):
            continue
        entry = {
            "candidate_ids": list(dict.fromkeys(ids)),
            "evidence_refs": [f"catalog:{value}" for value in dict.fromkeys(ids)],
            # Search summaries are untrusted presentation text.  Keep the
            # bounded diagnostic, but redact URLs before passing it to the
            # evaluator or report synthesizer.
            "summary": re.sub(r"https?://[^\s<>\"']+", "[已隐藏链接]", summary[:4096]) if isinstance(summary, str) else "",
        }
        metadata = result.get("catalog_metadata")
        if isinstance(metadata, (list, tuple)):
            bounded: list[dict[str, Any]] = []
            for item in metadata:
                if not isinstance(item, Mapping):
                    continue
                candidate_id = item.get("candidate_id", item.get("catalog_paper_id"))
                if candidate_id not in ids:
                    continue
                clean = {"candidate_id": candidate_id}
                for field in ("title", "abstract", "keywords", "summary", "method", "methods", "topic", "topics", "facets"):
                    if field in item:
                        value = item[field]
                        if isinstance(value, str):
                            clean[field] = value[:8000]
                        elif field == "keywords" and isinstance(value, (list, tuple)):
                            clean[field] = [str(keyword)[:160] for keyword in value[:24] if isinstance(keyword, str)]
                bounded.append(clean)
            if bounded:
                entry["catalog_metadata"] = bounded
        evidence.append(entry)
    return evidence


def _validated_evaluator_candidates(
    outputs,
    metadata_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    recall_allowlist: set[str] | None = None,
    metadata_resolver: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> list[dict]:
    """Normalize evaluator evidence into one record per catalog candidate.

    The evaluator contract permits an aggregate decision (``candidate_id`` may
    be null while ``evidence_refs`` lists all retained papers).  Earlier code
    treated that shape as having no validated evidence, so the synthesizer was
    skipped even though the Search Workers had supplied a complete catalog
    allowlist.  Expand only literal ``catalog:<id>`` references that are
    present in the already-sanitized metadata index *or* have been proven
    recalled by a Search Worker.

    ``recall_allowlist`` is the set of catalog IDs the Search Workers actually
    returned (the recall set).  It is the sole authority for whether a
    ``catalog:<id>`` reference may expand into a candidate; a reference absent
    from it is dropped even when ``metadata_resolver`` could return a row —
    this keeps the binding fail-closed on the Search recall set and prevents
    the local directory from enlarging the allowlist.

    ``metadata_resolver`` is the *only* sanctioned backfill for missing
    metadata.  It must resolve from the already-cleaned local catalog
    directory (e.g. ``PaperDiscoveryStore.get_catalog_paper``) and is consulted
    exclusively for recall-whitelisted IDs.  Evaluator model output is never
    used as metadata.  When even the local directory lacks the row, the
    candidate is still accepted (recall proves it was returned) with empty
    metadata — metadata is supplementary presentation text, not a gating fact.
    """
    METADATA_FIELDS = ("title", "abstract", "keywords", "summary", "method", "methods", "topic", "topics", "facets")
    records: list[dict] = []
    seen: set[str] = set()
    if recall_allowlist is not None:
        recall_allowlist = set(recall_allowlist)
    effective_metadata: dict[str, Mapping[str, Any]] = dict(metadata_by_id or {})

    def resolve_metadata(ref_id: str) -> Mapping[str, Any] | None:
        # Prefer already-indexed metadata.  Otherwise backfill from the local
        # catalog directory — but only for IDs the Search Workers recalled.
        if ref_id in effective_metadata:
            return effective_metadata[ref_id]
        if recall_allowlist is not None and ref_id not in recall_allowlist:
            return None
        backfilled = metadata_resolver(ref_id) if metadata_resolver is not None else None
        if backfilled is not None:
            effective_metadata[ref_id] = backfilled
        return backfilled

    for output in outputs:
        kept = output.get("kept") if isinstance(output.get("kept"), list) else [output]
        for item in kept:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("candidate_id", item.get("catalog_paper_id"))
            # Aggregate evaluator output (candidate_id is null) is a single
            # retained set, not a per-candidate keep/reject vote.  It is NOT
            # gated on a ``keep``/``verified`` flag: the model emits one batch
            # object whose top-level ``keep`` only marks "this is the
            # consolidated decision", and its retained candidates live in
            # ``evidence_refs``.  Requiring ``keep is True`` silently drops
            # every batch evaluator that kept N of M candidates (P0
            # spec029/030/031; real task 81241f3f01885e2c8f0490123f2215f3
            # emitted ``keep: false`` while retaining 6/12).  A per-candidate
            # record (candidate_id present) still requires an explicit
            # keep/verified signal so an explicit reject is honored.
            if candidate_id and item.get("keep") is not True and item.get("verified") is not True:
                continue
            refs = item.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                # Some evaluator responses put the catalog allowlist in the
                # top-level/source_refs field and omit evidence_refs.  Treat
                # only catalog refs as evidence; skill names and free-form
                # provenance labels are never promoted to citations.
                refs = item.get("source_refs")
            if not isinstance(refs, list) or not refs:
                # The runtime schema also permits the aggregate explanation
                # under safe_summary.source_refs.  It is still model output,
                # so it must pass the same catalog metadata allowlist below.
                summary = item.get("safe_summary")
                refs = summary.get("source_refs") if isinstance(summary, Mapping) else None
            if not isinstance(refs, list) or not refs:
                continue
            refs = [ref for ref in refs if isinstance(ref, str) and ref.startswith("catalog:")]
            if not refs:
                continue
            candidate_ids: list[str] = []
            if candidate_id:
                candidate_ids = [str(candidate_id)]
            else:
                # Aggregate evaluator output: derive IDs exclusively from
                # catalog references.  Accept a ref when its metadata is
                # already known OR when the ID is in the Search recall
                # allowlist (the local directory may backfill its metadata).
                # Rejected otherwise — never trusting the resolver to enlarge
                # the recall set.
                for ref in refs:
                    if not isinstance(ref, str) or not ref.startswith("catalog:"):
                        continue
                    ref_id = ref.split(":", 1)[1].strip()
                    if not ref_id:
                        continue
                    resolve_metadata(ref_id)
                    if ref_id in effective_metadata or (recall_allowlist is not None and ref_id in recall_allowlist):
                        candidate_ids.append(ref_id)
            for normalized_id in candidate_ids:
                if not normalized_id or normalized_id in seen:
                    continue
                candidate_refs = list(refs) if candidate_id else [f"catalog:{normalized_id}"]
                record = {"candidate_id": normalized_id, "verified": True, "evidence_refs": candidate_refs}
                # Metadata is copied only from the already-sanitized Search Worker
                # catalog handoff or the local catalog directory backfill, never
                # from model evaluator output.
                metadata = effective_metadata.get(normalized_id)
                if isinstance(metadata, Mapping):
                    for field in METADATA_FIELDS:
                        if field in metadata:
                            record[field] = metadata[field]
                records.append(record)
                seen.add(normalized_id)
    return records


def _sanitize_evaluator_binding(output: Mapping[str, Any], allowed_refs: set[str]) -> dict:
    """Drop evaluator provenance labels that are outside Search evidence.

    The evaluator skill may identify itself in ``source_refs`` (for example
    ``research-paper-evaluation``) or place catalog refs there instead of in
    ``evidence_refs``.  The orchestrator owns the binding, so retain only the
    allowlisted catalog refs and copy them into ``evidence_refs`` when a kept
    aggregate record omitted that field.
    """
    normalized = dict(output)
    valid_refs = lambda value: [
        ref for ref in value
        if isinstance(ref, str) and ref in allowed_refs and ref.startswith("catalog:")
    ] if isinstance(value, list) else []
    if "source_refs" in normalized:
        normalized["source_refs"] = valid_refs(normalized.get("source_refs"))
    summary = normalized.get("safe_summary")
    summary_refs: list[str] = []
    if isinstance(summary, Mapping):
        clean_summary = dict(summary)
        summary_refs = valid_refs(clean_summary.get("source_refs"))
        if "source_refs" in clean_summary:
            clean_summary["source_refs"] = summary_refs
        normalized["safe_summary"] = clean_summary
    for field in ("kept", "eliminated", "evaluations"):
        entries = normalized.get(field)
        if not isinstance(entries, list):
            continue
        clean_entries = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                clean_entries.append(entry)
                continue
            clean = dict(entry)
            refs = valid_refs(clean.get("evidence_refs"))
            if not refs:
                refs = valid_refs(clean.get("source_refs"))
            if refs:
                clean["evidence_refs"] = refs
            if "source_refs" in clean:
                clean["source_refs"] = valid_refs(clean.get("source_refs"))
            clean_entries.append(clean)
        normalized[field] = clean_entries
    refs = valid_refs(normalized.get("evidence_refs"))
    if not refs:
        refs = valid_refs(normalized.get("source_refs"))
    if not refs:
        refs = summary_refs
    if "evidence_refs" in normalized or refs:
        normalized["evidence_refs"] = refs
    return normalized


def _catalog_metadata_index(evidence: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index safe directory metadata by candidate ID for report delivery."""
    indexed: dict[str, dict[str, Any]] = {}
    for entry in evidence:
        if not isinstance(entry, Mapping):
            continue
        for item in entry.get("catalog_metadata", ()) if isinstance(entry.get("catalog_metadata"), (list, tuple)) else ():
            if not isinstance(item, Mapping):
                continue
            candidate_id = item.get("candidate_id", item.get("catalog_paper_id"))
            if not isinstance(candidate_id, str) or candidate_id in indexed:
                continue
            indexed[candidate_id] = dict(item)
    return indexed


def _recalled_candidate_ids(
    completed_outputs: Mapping[str, Any],
    item_by_id: Mapping[str, Any] | None = None,
) -> set[str]:
    """Catalog IDs actually recalled by Search Workers in this task.

    This is the canonical recall allowlist for evaluator/synthesizer binding.
    It is derived from each Search Worker's ``candidates`` handoff (the
    authoritative recall list), never from model evaluator output and never
    from catalog metadata completeness.  A missing/empty ``catalog_metadata``
    therefore can never invalidate an otherwise-legitimate candidate, while a
    model-fabricated ID is still rejected because it is never in the recall set.

    ``item_by_id`` is used to restrict the union to Search Worker WorkItems;
    when it is ``None`` every completed output is consulted.
    """
    recalled: set[str] = set()
    for dep_id, dep_output in completed_outputs.items():
        if not isinstance(dep_output, Mapping):
            continue
        if item_by_id is not None:
            dep_item = item_by_id.get(dep_id)
            if dep_item is None or getattr(dep_item, "role", None) != "search-worker":
                continue
        candidates = dep_output.get("candidates")
        if not isinstance(candidates, list):
            continue
        for pid in candidates:
            if isinstance(pid, str) and pid.strip():
                recalled.add(pid.strip())
    return recalled


def _evaluator_records(output) -> list[dict]:
    """Normalize evaluator output without accepting truthy/non-boolean flags."""
    kept = output.get("kept") if isinstance(output.get("kept"), list) else [output]
    return [item for item in kept if isinstance(item, dict)]


def _validate_evaluator_scope(
    output: dict,
    allowed_candidates: set[str],
    allowed_refs: set[str],
    allowed_sources: set[str] | None = None,
    allowed_source_refs: set[str] | None = None,
) -> bool:
    if allowed_sources is None:
        allowed_sources = {"usenix", "dblp", "all"}
    if allowed_source_refs is None:
        allowed_source_refs = set()
    def source_ref_allowed(ref: object) -> bool:
        if not isinstance(ref, str):
            return False
        if ref.startswith("search:"):
            return ref in allowed_source_refs
        if ref.startswith("catalog:"):
            return ref.split(":", 1)[1] in allowed_candidates
        return ref in allowed_source_refs or ref in allowed_refs

    source = output.get("source")
    if source is not None and source not in allowed_sources:
        return False
    source_refs = output.get("source_refs")
    if source_refs is not None and (
        not isinstance(source_refs, list)
        or any(
            not isinstance(ref, str)
            or not source_ref_allowed(ref)
            for ref in source_refs
        )
    ):
        return False
    records: list[dict] = []
    for field in ("kept", "eliminated", "evaluations"):
        value = output.get(field)
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    if isinstance(output.get("candidate_id"), str):
        records.append(output)
    top_manifest = output.get("citation_manifest")
    if isinstance(top_manifest, list) and any(
        not isinstance(ref, dict)
        or ref.get("candidate_id") not in allowed_candidates
        or ref.get("citation_ref") not in allowed_refs
        for ref in top_manifest
    ):
        return False
    for item in records:
        candidate_id = item.get("candidate_id", item.get("catalog_paper_id"))
        refs = item.get("evidence_refs")
        if candidate_id is not None and (not isinstance(candidate_id, str) or candidate_id not in allowed_candidates):
            return False
        if refs is not None and (not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in allowed_refs for ref in refs)):
            return False
        if item.get("source") is not None and item.get("source") not in allowed_sources:
            return False
        item_source_refs = item.get("source_refs")
        if item_source_refs is not None and (
            not isinstance(item_source_refs, list)
            or any(not source_ref_allowed(ref) for ref in item_source_refs)
        ):
            return False
        manifest = item.get("citation_manifest")
        if isinstance(manifest, list) and any(
            not isinstance(ref, dict)
            or ref.get("candidate_id") not in allowed_candidates
            or ref.get("citation_ref") not in allowed_refs
            for ref in manifest
        ):
            return False
    return True


def _canonicalize_search_worker_binding(output: dict, *, work_item_id: str) -> dict:
    """Replace the model-owned binding field with the runtime-owned item ID."""
    normalized = dict(output)
    normalized["work_item_id"] = work_item_id
    return normalized


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
        self, *, store, search_adapter=None, model_router=None, planner=None, probe=None, monotonic=None, agent_runner=None, processing_projector=None, memory_repository=None
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
        self._processing_projector = processing_projector
        self._memory_repository = memory_repository or getattr(processing_projector, "memory_repository", None)
        self._owner_by_task: dict[str, str] = {}
        if self._agent_runner is not None:
            # Install the callback on the already-constructed runner so skill
            # activation and tool calls use this same event/projection seam.
            with suppress(Exception):
                self._agent_runner.event_sink = self._on_runtime_event
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
        # 终态不得回到 running；paused 同样必须原样返回，避免后台线程在
        # 用户暂停后继续派发新节点。
        if task.status in TASK_TERMINAL or task.status == "paused":
            return self._result(research_task_id, task.status, task.current_plan_version, 0, None, (), False, None)
        self._owner_by_task[research_task_id] = owner_id
        try:
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
        finally:
            self._owner_by_task.pop(research_task_id, None)

    def _reject(self, research_task_id: str, owner_id: str, plan_version: int, code: str) -> OrchestratorResult:
        """计划被拒：收敛为 failed 并发出 terminal 事件（不留 running 悬空）。"""
        self._emit(research_task_id, "terminal", {"status": "failed", "error_code": code})
        with suppress(InvalidStateTransition):
            self._store.update_task_status(research_task_id, owner_id, "failed")
        session = self._store.get_session_by_task(research_task_id, owner_id)
        if session is not None:
            with suppress(Exception):
                ResearchNotificationService(store=self._store).emit(
                    owner_id=owner_id, research_session_id=session.research_session_id,
                    research_task_id=research_task_id, notification_kind="failed",
                    subject_version=plan_version, payload={"report_version": plan_version, "error_code": code},
                    idempotency_key=f"research-report:{research_task_id}:{plan_version}:failed",
                )
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
        synthesis_artifact_id = None
        synthesis_error = None
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
            session = store.get_session_by_task(research_task_id, owner_id)
            if session is not None:
                synthesis_run_id = self._synthesis_run_id(
                    task=task, session=session, work_item=syn_item, owner_id=owner_id
                )
                synthesis_artifact_id, synthesis_error = self._deliver_synthesized_report(
                    task=task,
                    session=session,
                    owner_id=owner_id,
                    plan_version=current_plan_version,
                    selected=selected,
                    facets=draft.facets,
                    gaps=gaps,
                    generated_by_agent_run_id=synthesis_run_id,
                )
                if synthesis_error:
                    self._emit_synthesis_failure_notification(
                        task=task, session=session, owner_id=owner_id,
                        version=current_plan_version, code=synthesis_error,
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
        degraded = bool(gaps) or bool(degraded_sources) or stop_reason == "budget_exhausted" or bool(synthesis_error)
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
            synthesis_error,
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
        synthesis_run_id = None
        synthesis_output: dict | None = None
        synthesis_attempts = 1
        synthesis_error: str | None = None
        evaluator_outputs: list[dict] = []
        evaluator_outputs_by_id: dict[str, dict] = {}
        selected_count = 0
        items = self._store.list_work_items(task.research_task_id, plan_version=plan_version)
        # Store order is not a scheduling contract.  Topologically order the
        # existing WorkItems so a producer always runs before its consumer;
        # the status checks below still fail closed on missing/failed deps.
        pending = {item.work_item_id: item for item in items}
        ordered_items = []
        while pending:
            ready = []
            for item in pending.values():
                try:
                    deps = json.loads(item.depends_on_json or "[]")
                except (TypeError, ValueError):
                    deps = []
                if isinstance(deps, list) and all(str(dep) not in pending for dep in deps):
                    ready.append(item)
            if not ready:
                ordered_items.extend(pending.values())
                break
            for item in ready:
                ordered_items.append(item)
                pending.pop(item.work_item_id, None)
        items = ordered_items
        completed_ids: set[str] = set()
        failed_ids: set[str] = set()
        completed_outputs: dict[str, dict] = {}
        completed_search_evidence: dict[str, list[dict]] = {}
        item_by_id = {item.work_item_id: item for item in items}
        for item in items:
            # Pause is checked at every dispatch boundary.  A node already in
            # the external call may finish and persist evidence; no following
            # node is started until the caller explicitly resumes the task.
            current = self._store.get_task(task.research_task_id, owner_id)
            if current is None or current.status == "paused" or current.status in TASK_TERMINAL:
                status = current.status if current is not None else "interrupted"
                return self._result(task.research_task_id, status, plan_version, 0, None, (), False, None)
            role = role_map.get(item.role, item.role)
            skill_name = ROLE_SKILL_DEFAULTS.get(role)
            capability = approved_capabilities.get(skill_name) if skill_name else None
            try:
                work_item_input = json.loads(item.input_json or "{}")
            except (TypeError, ValueError):
                work_item_input = {}
            try:
                dependencies = json.loads(item.depends_on_json or "[]")
            except (TypeError, ValueError):
                dependencies = []
            dependencies = [str(dep) for dep in dependencies] if isinstance(dependencies, list) else []
            if any(dep not in completed_ids for dep in dependencies):
                failures += 1
                error_code = "UPSTREAM_WORK_ITEM_FAILED" if any(dep in failed_ids for dep in dependencies) else "UPSTREAM_WORK_ITEM_NOT_READY"
                failed_ids.add(item.work_item_id)
                self._fail_work_item(task.research_task_id, item, error_code)
                if role == "synthesizer":
                    synthesis_error = error_code
                continue
            upstream = [completed_outputs[dep] for dep in dependencies if dep in completed_outputs]
            allowed_candidates: set[str] = set()
            allowed_refs: set[str] = set()
            allowed_sources: set[str] = set()
            allowed_source_refs: set[str] = set()
            # 候选 ID -> 产出它的那次检索的 search_id。一个任务扇出多个 search worker
            # 时各自快照不同，导入桥必须按来源快照分别解析候选（见 _persist_agent_selections）。
            candidate_sources: dict[str, str] = {}
            if role == "paper_evaluator":
                paper_ids = []
                for output in upstream:
                    raw_search_id = output.get("search_id")
                    output_search_id = (
                        str(raw_search_id).strip()
                        if isinstance(raw_search_id, str) and raw_search_id.strip()
                        else None
                    )
                    for paper_id in output.get("candidates", ()) if isinstance(output.get("candidates"), list) else ():
                        if isinstance(paper_id, str) and paper_id not in paper_ids:
                            paper_ids.append(paper_id)
                        if isinstance(paper_id, str) and output_search_id:
                            candidate_sources.setdefault(paper_id, output_search_id)
                work_item_input["catalog_paper_ids"] = paper_ids
                catalog_evidence = []
                for dependency_id, output in zip(dependencies, upstream, strict=False):
                    catalog_evidence.extend(
                        {
                            "work_item_id": dependency_id,
                            "source": output.get("source"),
                            "queries": output.get("queries", []),
                            **entry,
                        }
                        for entry in completed_search_evidence.get(dependency_id, ())
                    )
                if catalog_evidence:
                    work_item_input["catalog_evidence"] = catalog_evidence
                allowed_candidates = set(paper_ids)
                allowed_refs = {f"catalog:{paper_id}" for paper_id in paper_ids}
                binding_invalid = False
                for dependency_id, output in zip(dependencies, upstream, strict=False):
                    expected_source_item = item_by_id.get(dependency_id)
                    if (
                        expected_source_item is None
                        or (output.get("work_item_id") is not None and output.get("work_item_id") != dependency_id)
                        or (output.get("research_task_id") is not None and output.get("research_task_id") != task.research_task_id)
                    ):
                        binding_invalid = True
                        allowed_candidates.clear()
                        allowed_refs.clear()
                        allowed_sources.clear()
                        allowed_source_refs.clear()
                        candidate_sources.clear()
                    if not binding_invalid and output.get("source") in {"usenix", "dblp", "all"}:
                        allowed_sources.add(output["source"])
                    for source_ref in output.get("source_refs", ()) if not binding_invalid and isinstance(output.get("source_refs"), list) else ():
                        if isinstance(source_ref, str):
                            allowed_source_refs.add(source_ref)
                    if output.get("source") not in {"usenix", "dblp", "all"}:
                        allowed_candidates.clear()
                        allowed_refs.clear()
                        candidate_sources.clear()
                    for ref in output.get("evidence_refs", ()) if isinstance(output.get("evidence_refs"), list) else ():
                        if isinstance(ref, str):
                            allowed_refs.add(ref)
                    for ref in output.get("citation_allowlist", ()) if isinstance(output.get("citation_allowlist"), list) else ():
                        if isinstance(ref, str):
                            allowed_refs.add(ref.get("citation_ref", "") if isinstance(ref, dict) else ref)
            elif role == "synthesizer":
                def ancestors(work_item_id: str, seen: set[str] | None = None) -> set[str]:
                    seen = seen or set()
                    if work_item_id in seen:
                        return seen
                    seen.add(work_item_id)
                    parent = item_by_id.get(work_item_id)
                    if parent is None:
                        return seen
                    try:
                        parent_deps = json.loads(parent.depends_on_json or "[]")
                    except (TypeError, ValueError):
                        parent_deps = []
                    for parent_id in parent_deps if isinstance(parent_deps, list) else ():
                        ancestors(str(parent_id), seen)
                    return seen

                evaluator_ids = {
                    work_item_id for work_item_id in ancestors(item.work_item_id)
                    if item_by_id.get(work_item_id) is not None
                    and item_by_id[work_item_id].role == "paper-evaluator"
                }
                # Recall allowlist: catalog IDs the Search Workers actually
                # returned.  This is the sole authority for expanding aggregate
                # evaluator refs into candidates; the local catalog directory
                # may only backfill *metadata* for these IDs (never enlarge the
                # recall set).  Without this, a Search Worker whose tool_results
                # omitted catalog_metadata would silently empty `validated` and
                # the synthesizer would be skipped (P0, spec029/030/031).
                recall_allowlist = _recall_allowlist_from_search_outputs(
                    completed_outputs[ancestor_id]
                    for ancestor_id in ancestors(item.work_item_id)
                    if item_by_id.get(ancestor_id) is not None
                    and item_by_id[ancestor_id].role == "search-worker"
                    and isinstance(completed_outputs.get(ancestor_id), Mapping)
                )
                # Local catalog directory backfill: the only sanctioned metadata
                # source beyond the Search Worker catalog_metadata handoff.  It
                # is consulted only for recall-whitelisted IDs and never trusted
                # for the allowlist itself.  Reuses PaperDiscoveryStore.
                # get_catalog_paper (same single local-directory exit as the
                # spec029 search fallback fix) — no second retrieval impl.
                metadata_resolver = self._catalog_metadata_resolver()

                catalog_metadata = _catalog_metadata_index(
                    entry
                    for evidence in completed_search_evidence.values()
                    for entry in evidence
                )
                # Candidate legitimacy is owned by the Search Worker recall
                # allowlist, independent of catalog_metadata completeness, so a
                # missing catalog_metadata can never drop the synthesizer.
                allowed_candidate_ids = _recalled_candidate_ids(completed_outputs, item_by_id)
                validated = _validated_evaluator_candidates(
                    [evaluator_outputs_by_id[work_item_id] for work_item_id in evaluator_ids if work_item_id in evaluator_outputs_by_id],
                    catalog_metadata,
                    recall_allowlist=recall_allowlist,
                    metadata_resolver=metadata_resolver,
                )
                if not validated:
                    failures += 1
                    synthesis_error = "NO_VALIDATED_EVIDENCE"
                    failed_ids.add(item.work_item_id)
                    self._fail_work_item(task.research_task_id, item, synthesis_error)
                    continue
                work_item_input["validated_candidates"] = validated
                work_item_input["citation_allowlist"] = [
                    {"citation_ref": ref, "candidate_id": candidate["candidate_id"]}
                    for candidate in validated for ref in candidate["evidence_refs"]
                    if isinstance(ref, str)
                ]
            with suppress(Exception):
                self._store.update_work_item_input(
                    item.work_item_id,
                    json.dumps(work_item_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                )
            running_item = self._store.update_work_item_status(
                item.work_item_id,
                "running",
                **self._model_kwargs(
                    item.role,
                    research_task_id=task.research_task_id,
                    task_type=item.task_type,
                ),
            )
            run_id = f"{item.work_item_id}:run-{max(1, item.attempt + 1)}"
            try:
                worker_event = self._emit(
                    task.research_task_id,
                    "worker",
                    self._worker_event_payload(running_item, "running"),
                )
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
                    parent_source_event_id=(
                        f"research-event:{task.research_task_id}:{worker_event.event_seq}"
                        if worker_event else None
                    ),
                ))
            except Exception:
                failures += 1
                with suppress(Exception):
                    failed_item = self._store.update_work_item_status(item.work_item_id, "failed", error_code="AGENT_RUN_FAILED")
                    self._emit(task.research_task_id, "worker", self._worker_event_payload(failed_item, "failed", error_code="AGENT_RUN_FAILED"))
                continue
            terminal = result.status if result.status in {"completed", "failed", "cancelled", "limit_reached"} else "failed"
            semantic_error = None
            normalized_output = result.output_json
            if terminal == "completed" and role == "search_worker" and isinstance(normalized_output, dict):
                # The runtime, rather than the model, owns the durable
                # WorkItem binding; the model's presentation value is ignored.
                normalized_output = _canonicalize_search_worker_binding(
                    normalized_output,
                    work_item_id=item.work_item_id,
                )
            if terminal == "completed" and role == "paper_evaluator" and isinstance(normalized_output, dict):
                raw_output = dict(normalized_output)
                # The evaluator model is not trusted to choose provenance
                # labels.  Normalize its source/evidence fields against the
                # Search Worker allowlist before applying the scope check.
                raw_output = _sanitize_evaluator_binding(raw_output, allowed_refs)
                normalized_output = raw_output
                # The evaluator may only retain candidates/ref IDs present in
                # its Search Worker dependencies; a completed but out-of-scope
                # model result is converted to a stable failed WorkItem.
                if not _validate_evaluator_scope(
                    raw_output, allowed_candidates, allowed_refs, allowed_sources, allowed_source_refs
                ):
                    semantic_error = "EVALUATOR_EVIDENCE_OUT_OF_SCOPE"
                    terminal = "failed"
            if terminal != "completed":
                failures += 1
                failed_ids.add(item.work_item_id)
            else:
                completed_ids.add(item.work_item_id)
                completed_outputs[item.work_item_id] = _work_item_output(normalized_output)
                if role == "search_worker":
                    completed_search_evidence[item.work_item_id] = _catalog_evidence_view(
                        completed_outputs[item.work_item_id], result.tool_results
                    )
            search_id = None
            if role == "search_worker" and terminal == "completed":
                candidate_search_id = completed_outputs.get(item.work_item_id, {}).get("search_id")
                if isinstance(candidate_search_id, str) and candidate_search_id.strip():
                    search_id = candidate_search_id.strip()
                    # Persist before the WorkItem terminal write-back.  A
                    # Runner may already have finalized that WorkItem, and a
                    # stale/duplicate status transition must not discard the
                    # durable acquisition bridge.  The store validates the
                    # opaque server-owned handle and retains the first one.
                    with suppress(AttributeError, ValueError):
                        self._store.set_task_search_id(task.research_task_id, search_id)
            error_code = result.error_code or semantic_error
            if terminal == "completed" and role == "paper_evaluator" and isinstance(normalized_output, dict):
                evaluator_outputs.append(dict(normalized_output))
                evaluator_outputs_by_id[item.work_item_id] = dict(normalized_output)
                # agent 路径此前从不落库选集，导致 research_paper_selections 永远为空
                # （Spec029 acquisition-preview 报 REPORT_NOT_READY）。evaluator completed
                # 后立即把真实候选持久化；只接受 allowed_candidates 白名单内的召回 ID，
                # 落库失败不阻断后续 WorkItem（选集写不进去不该把任务打成 failed）。
                self._persist_agent_selections(
                    task.research_task_id, normalized_output, allowed_candidates, candidate_sources
                )
            if terminal == "completed" and role == "synthesizer":
                synthesis_run_id = getattr(result, "agent_run_id", None) or run_id
                synthesis_output = dict(normalized_output) if isinstance(normalized_output, dict) else None
                synthesis_attempts = int((result.model_metadata or {}).get("attempts_used", 1) or 1)
            elif role == "synthesizer" and terminal != "completed":
                synthesis_error = result.error_code or "AGENT_OUTPUT_INVALID"
                synthesis_attempts = int((result.model_metadata or {}).get("attempts_used", 1) or 1)
            output_json = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)[:100000]
            with suppress(Exception):
                updated = self._store.update_work_item_status(
                    item.work_item_id,
                    "completed" if terminal == "completed" else ("cancelled" if terminal == "cancelled" else "failed"),
                    output_json=output_json,
                    error_code=error_code,
                    resolved_model=result.model_metadata.get("model") if result.model_metadata else None,
                )
                event_extra = {"error_code": error_code} if error_code else {}
                if search_id is not None:
                    event_extra["search_id"] = search_id
                self._emit(
                    task.research_task_id,
                    "worker",
                    self._worker_event_payload(updated, terminal, **event_extra),
                )
        synthesis_artifact_id = None
        if self._memory_repository is not None:
            session = self._store.get_session_by_task(task.research_task_id, owner_id)
            if session is not None:
                catalog_metadata = _catalog_metadata_index(
                    entry
                    for evidence in completed_search_evidence.values()
                    for entry in evidence
                )
                validated_candidates: list[dict] = []
                # Keep this normalization identical to the synthesizer input
                # path above.  In particular, aggregate evaluator output with
                # a null candidate_id is expanded from catalog evidence refs,
                # bounded by the Search Workers' recall allowlist and backfilled
                # from the local catalog directory.  Without the allowlist this
                # path silently yielded zero candidates whenever the Search
                # Worker tool_results omitted catalog_metadata, so selections
                # were never persisted even though the evaluator had retained
                # rows (P0, spec029/030/031).
                validated_candidates.extend(
                    _validated_evaluator_candidates(
                        evaluator_outputs,
                        catalog_metadata,
                        recall_allowlist=_recall_allowlist_from_search_outputs(
                            output
                            for work_item_id, output in completed_outputs.items()
                            if item_by_id.get(work_item_id) is not None
                            and item_by_id[work_item_id].role == "search-worker"
                        ),
                        metadata_resolver=self._catalog_metadata_resolver(),
                    )
                )
                # If the real evaluator retained fewer than the report floor,
                # use only already-sanitized catalog metadata to fill the
                # bounded evidence set.  This is deliberately fail-closed:
                # without five metadata-backed catalog rows, no candidates are
                # invented and the existing NO_VALIDATED_EVIDENCE path wins.
                if len({item["candidate_id"] for item in validated_candidates}) < _MIN_REPORT_CANDIDATES:
                    catalog_rows = [
                        {**metadata, "catalog_paper_id": candidate_id}
                        for candidate_id, metadata in catalog_metadata.items()
                        if isinstance(candidate_id, str) and isinstance(metadata, Mapping)
                    ]
                    if len(catalog_rows) >= _MIN_REPORT_CANDIDATES:
                        from backend.app.research.application.search_catalog_adapter import PaperEvaluator

                        floor_output = PaperEvaluator(threshold=0.2, soft_floor=0.1).evaluate(
                            catalog_rows, query=task.goal
                        )
                        existing_ids = {item["candidate_id"] for item in validated_candidates}
                        for item in floor_output["kept"]:
                            candidate_id = item.get("candidate_id")
                            if not isinstance(candidate_id, str) or candidate_id in existing_ids:
                                continue
                            record = {
                                "candidate_id": candidate_id,
                                "verified": True,
                                "evidence_refs": [f"catalog:{candidate_id}"],
                            }
                            metadata = catalog_metadata.get(candidate_id)
                            if isinstance(metadata, Mapping):
                                for field in ("title", "abstract", "keywords", "summary", "method", "methods", "topic", "topics", "facets"):
                                    if field in metadata:
                                        record[field] = metadata[field]
                            validated_candidates.append(record)
                            existing_ids.add(candidate_id)
                            if len(existing_ids) >= _MIN_REPORT_CANDIDATES:
                                break
                selected_count = len(validated_candidates)
                try:
                    if synthesis_run_id is None or synthesis_output is None:
                        raise ReportSynthesisError(
                            "synthesizer run did not complete", code=synthesis_error or "AGENT_OUTPUT_INVALID"
                        )
                    # Validate and consume the actual model output.  The
                    # delivery service is deliberately downstream of this
                    # semantic boundary; it never re-composes a replacement
                    # report from evaluator data.
                    validate_report_synthesis_output(synthesis_output, expected_version=plan_version)
                    synthesis = ReportSynthesizer().consume_validated_output(
                        output=synthesis_output,
                        validated_candidates=validated_candidates,
                        title="深度研究报告",
                    )
                    delivered = ReportDeliveryService(
                        store=self._store, memory_repository=self._memory_repository,
                    ).deliver(
                        session=session, owner_id=owner_id,
                        generated_by_agent_run_id=synthesis_run_id,
                        result=synthesis,
                        notification_kind="partial" if failures else "completed",
                    )
                    synthesis_artifact_id = delivered["artifacts"][0]["artifact_id"]
                except Exception as exc:
                    synthesis_error = getattr(exc, "code", "AGENT_OUTPUT_INVALID")
                    self._emit_synthesis_failure_notification(
                        task=task, session=session, owner_id=owner_id,
                        version=plan_version, code=synthesis_error,
                        retry_attempt=synthesis_attempts if synthesis_attempts > 1 else None,
                    )
        # A runner-less legacy caller has no Task08 delivery seam.  Once the
        # seam is present, an empty evaluator result is a degraded outcome,
        # never a successful empty report.
        if self._memory_repository is not None and not synthesis_error:
            if not evaluator_outputs:
                synthesis_error = "NO_VALIDATED_EVIDENCE"
            else:
                has_evidence = any(
                    isinstance(item, dict)
                    and isinstance(item.get("evidence_refs"), list)
                    and bool(item.get("evidence_refs"))
                    for evaluation in evaluator_outputs
                    for item in (
                        evaluation.get("kept", ())
                        if isinstance(evaluation.get("kept"), list)
                        else (evaluation,)
                    )
                    if isinstance(item, dict) and (item.get("keep") is True or item.get("verified") is True)
                )
                if not has_evidence:
                    synthesis_error = "NO_VALIDATED_EVIDENCE"
        if synthesis_error:
            failures += 1
        final_status = "completed" if items and failures == 0 else "partial"
        with suppress(InvalidStateTransition):
            self._store.update_task_status(task.research_task_id, owner_id, final_status)
        self._emit(task.research_task_id, "terminal", {"status": final_status, "selected_count": selected_count, "error_code": None if failures == 0 else (synthesis_error or "AGENT_RUN_FAILED")})
        return self._result(task.research_task_id, final_status, plan_version, selected_count, synthesis_artifact_id, (), failures > 0, synthesis_error or (None if failures == 0 else "AGENT_RUN_FAILED"))

    def _catalog_metadata_resolver(self) -> Callable[[str], Mapping[str, Any] | None] | None:
        """Return the sanctioned local-directory metadata backfill, or None.

        Both the synthesizer input path and the artifact/selection path must use
        the *same* binding context, otherwise one yields candidates while the
        other persists none.  Reuses ``PaperDiscoveryStore.get_catalog_paper`` —
        the single local-directory exit already used by the spec029 search
        fallback fix — so this is never a second retrieval implementation.

        It is consulted only for IDs already present in the Search Workers'
        recall allowlist and never contributes to the allowlist itself.
        """
        catalog_store = getattr(self._adapter, "_store", None)
        get_catalog_paper = getattr(catalog_store, "get_catalog_paper", None)
        if not callable(get_catalog_paper):
            return None

        def resolver(catalog_paper_id: str, _get_catalog_paper=get_catalog_paper) -> dict[str, Any] | None:
            row = _get_catalog_paper(catalog_paper_id)
            if row is None:
                return None
            data: dict[str, Any] = {}
            title = getattr(row, "title", None)
            if isinstance(title, str) and title:
                data["title"] = title
            abstract = getattr(row, "abstract", None)
            if isinstance(abstract, str) and abstract:
                data["abstract"] = abstract
            keywords = getattr(row, "keywords", None)
            if isinstance(keywords, (list, tuple)) and keywords:
                data["keywords"] = [str(key) for key in keywords[:24] if isinstance(key, str)]
            return data or None

        return resolver

    def _fail_work_item(self, research_task_id: str, item, error_code: str) -> None:
        """把未派发的 WorkItem 真正标记为 failed 并 emit worker 事件。

        状态机只允许 ``queued -> running -> failed``（``WORKITEM_TRANSITIONS``），
        直接 ``queued -> failed`` 会抛 ``InvalidStateTransition``。此前这一步被
        ``with suppress(Exception)`` 整体吞掉，结果是：永远不会被派发的 WorkItem
        一直停留在 ``queued``，``error_code`` 也从不落库，API/UI 看起来像「还在排队」
        而不是「已失败」。这里补上合法中间态再写终态。
        """
        current = getattr(item, "status", None)
        if current == "queued":
            with suppress(Exception):
                item = self._store.update_work_item_status(item.work_item_id, "running") or item
        with suppress(Exception):
            failed_item = self._store.update_work_item_status(
                item.work_item_id, "failed", error_code=error_code
            )
            self._emit(
                research_task_id, "worker",
                self._worker_event_payload(failed_item, "failed", error_code=error_code),
            )

    def _persist_agent_selections(
        self,
        research_task_id: str,
        evaluator_output: dict,
        allowed_candidates: set[str],
        candidate_sources: dict[str, str] | None = None,
    ) -> None:
        """把 agent 路径 evaluator 产出的真实候选落库为 research_paper_selections。

        只接受 ``allowed_candidates``（本 WorkItem 的 Search Worker 召回白名单）里的
        candidate_id；模型自造的 ID 一律丢弃，绝不伪造 relevance/facets/evidence。agent
        路径只有目录/摘要级证据，evidence_level 固定为 ``"catalog"``（绝不标 fulltext）。
        落库失败不能让整条流水线崩：记 logger.warning 后继续后续 WorkItem。

        ``candidate_sources`` 是「候选 ID -> 产出它的 search_id」映射。任务可扇出多个
        search worker，各自持有不同的 server 快照；选集必须记住自己的来源快照，导入桥
        才能按快照分别解析候选。缺失时回落到任务级 search_id（旧数据/单 worker 场景）。

        evaluator 产出有两种形状，都必须覆盖：
        - 聚合形 ``{"kept": [...]}``；
        - 单条聚合形（``candidate_id`` 可能为 null，候选 ID 全在 ``evidence_refs`` 的
          ``catalog:<id>`` 里，``keep`` 为 true）——实测这是当前模型最常见的产出。
        """
        kept = evaluator_output.get("kept")
        if isinstance(kept, list):
            entries: list = list(kept)
        else:
            entries = [evaluator_output]
        source_map = dict(candidate_sources or {})
        # 候选没有明确来源时回落到任务级（第一个）search_id：旧数据与单 worker
        # 场景下这是唯一可用的快照句柄。
        fallback_search_id: str | None = None
        if not source_map:
            getter = getattr(self._store, "get_task_search_id", None)
            if callable(getter):
                with suppress(Exception):
                    fallback_search_id = getter(research_task_id)
        selections: list[ResearchPaperSelection] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            direct = entry.get("candidate_id", entry.get("catalog_paper_id"))
            # 聚合批量 evaluator（candidate_id 为 null）本身就是保留集合；其顶层
            # keep=False 只标记「这是批量容器」，并非「我拒绝了这些候选」。只有
            # 显式的 per-candidate 拒绝（candidate_id 有值且 keep=False）才跳过。
            # 否则会和 _validated_evaluator_candidates 一样把批量 evaluator 整条丢
            # 掉，导致 research_paper_selections 0 条（P0 spec029/030/031）。
            if direct and entry.get("keep") is False:
                continue
            # 一条 entry 可能携带多个候选 ID：显式 id 字段 + evidence_refs 里的 catalog:<id>。
            raw_ids: list[str] = []
            if isinstance(direct, str) and direct.strip():
                raw_ids.append(direct.strip())
            refs = entry.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, str) and ref.startswith("catalog:"):
                        raw_ids.append(ref.split(":", 1)[1])
            raw_relevance = entry.get("relevance_score", entry.get("relevance"))
            try:
                relevance = float(raw_relevance) if raw_relevance is not None else 0.0
            except (TypeError, ValueError):
                relevance = 0.0
            facets = entry.get("facets")
            if not isinstance(facets, list):
                facets = []
            for candidate_id in raw_ids:
                if not candidate_id:
                    continue
                # 白名单外的 ID（含模型自造）一律丢弃，绝不落库。
                if candidate_id not in allowed_candidates:
                    continue
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                source_search_id = source_map.get(candidate_id) or fallback_search_id
                selections.append(ResearchPaperSelection(
                    research_task_id=research_task_id,
                    catalog_paper_id=candidate_id,
                    relevance=relevance,
                    facets_json=json.dumps(facets, ensure_ascii=False),
                    evidence_level="catalog",
                    created_at=_utcnow(),
                    source_search_id=source_search_id or None,
                ))
        if not selections:
            return
        try:
            self._store.replace_selections(research_task_id, selections)
        except Exception as exc:  # noqa: BLE001 - 选集写不进去不应把任务打成 failed
            logger.warning(
                "agent evaluator selections not persisted; continuing pipeline",
                extra={"research_task_id": research_task_id, "error": str(exc)},
            )

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
                self._worker_event_payload(
                    completed_item,
                    "completed",
                    selected_count=len(selected),
                    # IDs are the stable, non-sensitive bridge to the
                    # existing durable selection snapshot.  Do not put
                    # catalog title/abstract text or evaluator reasoning in
                    # the event payload.
                    selected_paper_ids=[item["catalog_paper_id"] for item in selected],
                ),
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
        search_id = worker_output.get("search_id") if isinstance(worker_output, dict) else None
        if isinstance(search_id, str) and search_id.strip():
            # Persist only a server-owned opaque handle returned by the
            # existing catalog adapter; never infer one from paper IDs.
            with suppress(AttributeError, ValueError):
                store.set_task_search_id(research_task_id, search_id)
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
            self._worker_event_payload(
                completed_item,
                "completed",
                catalog_paper_ids=ids,
                **({"search_id": search_id} if isinstance(search_id, str) and search_id.strip() else {}),
            ),
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
        - 取前 ``min(max(target_paper_count, 5), BUDGET_CAPS["max_selected"])`` 篇，
          但仅当候选池本身不少于 5 篇时启用 5 篇下限；
        - ``evidence_level`` 恒为 catalog（Spec027 不下载全文）。

        之所以不读取论文标题/摘要等元数据：Spec027 禁止把论文元数据复制到 027 的表，且论文
        文本是不可信证据——读入即等于引入注入面。
        """
        total = max(1, len(candidates))
        requested_cap = max(0, int(target_paper_count))
        if len(candidates) >= _MIN_REPORT_CANDIDATES:
            requested_cap = max(requested_cap, _MIN_REPORT_CANDIDATES)
        cap = min(requested_cap, BUDGET_CAPS["max_selected"])
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

    def _synthesis_run_id(self, *, task, session, work_item, owner_id: str) -> str | None:
        """Return/create the sole synthesizer run used to author artifacts.

        The legacy deterministic pipeline has a synthesizer WorkItem but no
        model Runner.  Recording one completed, owner-bound Run at this
        boundary preserves the Artifact contract while keeping Orchestrator as
        the only Run creator.  Real AgentRunner paths pass their actual Run ID.
        """
        if work_item is None or not self._memory_repository:
            return None
        run_id = f"{work_item.work_item_id}:report-run-v{task.current_plan_version}"
        getter = getattr(self._store, "get_agent_run", None)
        if callable(getter) and getter(run_id, owner_id) is not None:
            return run_id
        creator = getattr(self._store, "create_agent_run", None)
        if not callable(creator):
            return None
        from backend.app.research.domain.models import AgentRun

        try:
            creator(AgentRun(
                agent_run_id=run_id,
                research_session_id=session.research_session_id,
                attempt=1,
                role="synthesizer",
                skill_name="research-report-synthesis",
                skill_schema_version="1",
                skill_content_hash="deterministic-report-synthesis",
                resolved_model="deterministic",
                reasoning_effort="off",
                allowed_tools_json="[]",
                provider="internal",
                status="completed",
                research_task_id=task.research_task_id,
                work_item_id=work_item.work_item_id,
                owner_id=owner_id,
            ), owner_id=owner_id)
            return run_id
        except Exception:
            return None

    def _deliver_synthesized_report(
        self, *, task, session, owner_id: str, plan_version: int,
        selected: list[dict], facets: tuple[str, ...], gaps: tuple[str, ...],
        generated_by_agent_run_id: str | None,
    ) -> tuple[str | None, str | None]:
        """Synthesize and deliver one immutable report; return (report_id,error)."""
        # Legacy Spec027 callers do not bind a conversation repository; retain
        # their PreliminaryReport-only contract.  Task08 delivery is enabled
        # only when the existing MemoryRepository seam is present.
        if self._memory_repository is None:
            return None, None
        if not generated_by_agent_run_id:
            return None, "ARTIFACT_NOT_READY"
        if not selected:
            return None, "NO_VALIDATED_EVIDENCE"
        verified = []
        citations = []
        for item in selected:
            paper_id = item.get("catalog_paper_id") if isinstance(item, dict) else None
            if not paper_id:
                continue
            verified.append({"candidate_id": str(paper_id), "verified": True})
            citations.append({"citation_ref": f"catalog:{paper_id}", "candidate_id": str(paper_id)})
        sections = []
        for facet in facets:
            ids = [
                str(item["catalog_paper_id"])
                for item in selected
                if isinstance(item, dict) and facet in item.get("facets", ())
            ]
            if ids:
                sections.append({"heading": facet, "candidate_ids": ids})
        if not sections and verified:
            sections = [{"heading": "证据与引用", "candidate_ids": [item["candidate_id"] for item in verified]}]
        try:
            result = ReportSynthesizer().synthesize(
                report_version=plan_version,
                candidates=verified,
                citation_whitelist=citations,
                sections=sections,
                title="深度研究报告",
            )
            delivered = ReportDeliveryService(
                store=self._store, memory_repository=self._memory_repository,
            ).deliver(
                session=session, owner_id=owner_id,
                generated_by_agent_run_id=generated_by_agent_run_id,
                result=result,
                notification_kind="partial" if gaps else "completed",
            )
            return delivered["artifacts"][0]["artifact_id"], None
        except ReportSynthesisError as exc:
            return None, getattr(exc, "code", "AGENT_OUTPUT_INVALID")
        except Exception:
            return None, "ARTIFACT_NOT_READY"

    def _emit_synthesis_failure_notification(
        self, *, task, session, owner_id: str, version: int, code: str,
        retry_attempt: int | None = None,
    ) -> None:
        if not session or not self._store:
            return
        try:
            service = ResearchNotificationService(store=self._store)
            service.emit(
                owner_id=owner_id,
                research_session_id=session.research_session_id,
                research_task_id=task.research_task_id,
                notification_kind="failed",
                subject_version=version,
                payload={"report_version": version, "error_code": code},
                idempotency_key=f"research-report:{task.research_task_id}:{version}:failed",
            )
            # Failure and degraded completion are separate durable facts.  A
            # retry attempt gets its own failed fact so a client can show
            # progress without overwriting the original failure.
            service.emit(
                owner_id=owner_id,
                research_session_id=session.research_session_id,
                research_task_id=task.research_task_id,
                notification_kind="partial",
                subject_version=version,
                payload={"report_version": version, "error_code": code},
                idempotency_key=f"research-report:{task.research_task_id}:{version}:partial",
            )
            if retry_attempt is not None and retry_attempt > 1:
                service.emit(
                    owner_id=owner_id,
                    research_session_id=session.research_session_id,
                    research_task_id=task.research_task_id,
                    notification_kind="failed",
                    subject_version=version,
                    payload={"report_version": version, "error_code": code, "retry_attempt": retry_attempt},
                    idempotency_key=f"research-report:{task.research_task_id}:{version}:retry:{retry_attempt}",
                )
        except Exception:
            return

    # ------------------------------------------------------------------ #
    # 内部：读 task / 找 item / 事件与结果
    # ------------------------------------------------------------------ #

    def _refresh(self, research_task_id: str, owner_id: str):
        """重读 task；不存在返回 TASK_NOT_FOUND 结果，已终态返回当前态结果，否则返回 task。"""
        task = self._store.get_task(research_task_id, owner_id)
        if task is None:
            return self._result(research_task_id, "failed", 0, 0, None, (), False, "TASK_NOT_FOUND")
        if task.status in TASK_TERMINAL or task.status == "paused":
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
            "node_type": "agent",
            "node_key": f"agent:{item.work_item_id}",
            "parent_node_key": "phase:research",
        }
        for field in ("model_tier", "resolved_model", "worker_slot"):
            value = getattr(item, field, None)
            if value is not None:
                payload[field] = value
        payload.update(extra)
        return payload

    def _on_runtime_event(self, event) -> None:
        """Project runner-emitted skill/tool events without a second event log."""
        owner_id = self._owner_by_task.get(event.research_task_id)
        if self._processing_projector is None or not owner_id:
            return
        session = self._store.get_session_by_task(event.research_task_id, owner_id)
        if session is None or not session.activity_message_id:
            return
        try:
            self._processing_projector.project_event(
                session.activity_message_id, owner_id, event,
                research_session_id=session.research_session_id,
            )
            with suppress(Exception):
                self._processing_projector.drain_pending(
                    event.research_task_id, session.activity_message_id, owner_id,
                    research_session_id=session.research_session_id,
                )
        except Exception:
            with suppress(Exception):
                self._store.mark_projection_retry(event.research_task_id, event.event_seq, "TRACE_PROJECTION_FAILED")

    def _emit(self, research_task_id: str, event_type: str, payload: dict):
        """追加事件；event_type 必须来自 contracts.EVENT_TYPES（安全 payload 由 store 序列化）。"""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event_type}")
        owner_id = self._owner_by_task.get(research_task_id)
        enriched = dict(payload)
        if event_type in {"task", "plan", "coverage", "report", "terminal"}:
            enriched.setdefault("node_type", "phase")
            enriched.setdefault("node_key", f"phase:{'research' if event_type in {'task', 'terminal'} else event_type}")
        if event_type == "worker":
            work_item_id = enriched.get("work_item_id")
            if work_item_id:
                enriched.setdefault("node_type", "agent")
                enriched.setdefault("node_key", f"agent:{work_item_id}")
                enriched.setdefault("parent_node_key", "phase:research")
        event = self._store.append_event(research_task_id, event_type, enriched)
        if self._processing_projector is not None and owner_id:
            session = self._store.get_session_by_task(research_task_id, owner_id)
            if session is not None and session.activity_message_id:
                try:
                    self._processing_projector.project_event(
                        session.activity_message_id,
                        owner_id,
                        event,
                        research_session_id=session.research_session_id,
                    )
                    with suppress(Exception):
                        self._processing_projector.drain_pending(
                            research_task_id, session.activity_message_id, owner_id,
                            research_session_id=session.research_session_id,
                        )
                except Exception as exc:
                    # The durable ResearchEvent remains authoritative; retain
                    # a ResearchStore retry marker while the activity message
                    # projection is repaired asynchronously.
                    with suppress(Exception):
                        self._store.mark_projection_retry(research_task_id, event.event_seq, "TRACE_PROJECTION_FAILED")
        return event

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
