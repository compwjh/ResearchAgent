"""Restart recovery for durable AgentRun WorkItem output envelopes."""

import json
import uuid
from types import SimpleNamespace

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.agent_runtime import AgentRunOutput, _hash
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.planner import ResearchPlanDraft
from backend.app.research.domain.models import (
    AgentCheckpoint,
    AgentRun,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _id():
    return uuid.uuid4().hex


class _Probe:
    def arbitrate(self, _task_id, requested):
        return max(1, requested), None

    def release(self, _task_id):
        return None


class _CountingRunner:
    event_sink = None

    def __init__(self):
        self.calls = []

    def run(self, run_input):
        self.calls.append(run_input)
        output = {
            "schema_version": "runtime-v1",
            "work_item_id": run_input.work_item_id,
        }
        if run_input.role == "research_critic":
            output["coverage_gaps"] = []
        elif run_input.role == "synthesizer":
            output.update({"schema_version": "synthesis-v1", "report": "ok"})
        return AgentRunOutput(
            "completed",
            output_json=output,
            output_hash="hash",
            agent_run_id=run_input.agent_run_id,
        )


def _planner():
    return SimpleNamespace(
        build_plan=lambda **_: ResearchPlanDraft(
            facets=("systems",),
            planner_model="fake",
            rationale_summary="fake",
            work_items=(
                {"id": "search", "task_type": "search_catalog", "role": "search-worker", "depends_on": [], "params": {"query": "goal"}},
                {"id": "evaluate", "task_type": "evaluate_papers", "role": "paper-evaluator", "depends_on": ["search"], "params": {}},
                {"id": "critic", "task_type": "check_coverage", "role": "research-critic", "depends_on": ["evaluate"], "params": {"goal": "goal"}},
                {"id": "synth", "task_type": "synthesize_preliminary_report", "role": "synthesizer", "depends_on": ["critic"], "params": {"goal": "goal"}},
            ),
            target_paper_count=1,
        )
    )


def _outer(
    output,
    *,
    status="completed",
    tool_results=None,
    agent_run_id="persisted-run",
    output_hash_override=None,
):
    inner_hash = ""
    if isinstance(output, dict):
        output["output_hash"] = _hash({key: value for key, value in output.items() if key != "output_hash"})
        inner_hash = output["output_hash"]
    safe_tool_results = list(tool_results or [])
    checkpoint = {
        "schema_version": output.get("schema_version", "runtime-v1") if isinstance(output, dict) else "runtime-v1",
        "output": output,
        "tool_results": safe_tool_results,
    }
    checkpoint_hash = _hash(checkpoint)
    checkpoint_ref = f"checkpoint:{agent_run_id}:{checkpoint_hash[:16]}"
    return json.dumps(
        {
            "status": status,
            "schema_version": "runtime-v1",
            "output_json": output,
            "output_hash": output_hash_override if output_hash_override is not None else inner_hash,
            "tool_results": safe_tool_results,
            "agent_run_id": agent_run_id,
            "checkpoint_ref": checkpoint_ref,
            "checkpoint_hash": checkpoint_hash,
        },
        ensure_ascii=False,
    )


def _create_completed_run(store, *, session, task, work_item_id, role, envelope):
    skill_by_role = {
        "search_worker": "usenix-catalog-orchestration",
        "paper_evaluator": "research-paper-evaluation",
        "research_critic": "research-coverage-review",
        "synthesizer": "research-report-synthesis",
    }
    agent_run_id = envelope["agent_run_id"]
    output = envelope["output_json"]
    tool_results = envelope.get("tool_results", [])
    checkpoint = {
        "schema_version": output.get("schema_version", "runtime-v1"),
        "output": output,
        "tool_results": tool_results,
    }
    checkpoint_hash = _hash(checkpoint)
    assert envelope["checkpoint_hash"] == checkpoint_hash
    store.create_agent_run(AgentRun(
        agent_run_id,
        session.research_session_id,
        1,
        role,
        skill_by_role[role],
        "1",
        "test-skill-hash",
        "fake",
        "off",
        "[]",
        provider="test",
        status="running",
        research_task_id=task.research_task_id,
        work_item_id=work_item_id,
        output_hash="",
        owner_id="owner",
    ), owner_id="owner")
    run = store.get_agent_run(agent_run_id, "owner")
    assert run is not None
    store.create_agent_checkpoint(AgentCheckpoint(
        checkpoint_ref=envelope["checkpoint_ref"],
        owner_id="owner",
        research_session_id=session.research_session_id,
        research_task_id=task.research_task_id,
        work_item_id=work_item_id,
        agent_run_id=agent_run_id,
        schema_version=checkpoint["schema_version"],
        content=json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        content_hash=checkpoint_hash,
    ), expected_generation=run.generation)
    store.update_agent_run_counters(
        agent_run_id,
        "owner",
        checkpoint_ref=envelope["checkpoint_ref"],
        checkpoint_hash=checkpoint_hash,
        output_hash=envelope["output_hash"],
        expected_generation=run.generation,
    )
    store.update_agent_run_status(agent_run_id, "owner", "completed")


def _build_store(
    tmp_path,
    *,
    search_output_json=None,
    evaluator_output_json=None,
    search_candidates=None,
    tool_catalog_ids=None,
    tool_search_id="search-1",
    output_search_id="search-1",
    evaluator_candidate="paper-1",
    seed_agent_runs=True,
    completed_role_outputs=None,
    search_output_hash_override=None,
):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages(
        "owner", "goal", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        _id(), "owner", conversation.conversation_id, "goal", "en",
        "balanced", False, 1, 60, "draft", 1,
        "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
    )
    store.create_task(task)
    session = ResearchSession(
        _id(), "owner", conversation.conversation_id, user.message_id,
        _id(), "running", research_task_id=task.research_task_id,
        activity_message_id=assistant.message_id,
    )
    store.create_session(session, memory_repository=memory)
    store.update_session_links(session.research_session_id, "owner", research_task_id=task.research_task_id)
    store.create_plan(ResearchPlan(
        research_task_id=task.research_task_id,
        version=1,
        rationale_summary="fake",
        facets_json='["systems"]',
        status="active",
        created_at="2026-01-01T00:00:00Z",
        planner_model="fake",
    ))

    search_id = f"{task.research_task_id}-search"
    evaluate_id = f"{task.research_task_id}-evaluate"
    critic_id = f"{task.research_task_id}-critic"
    synth_id = f"{task.research_task_id}-synth"
    search_candidates = list(search_candidates or ["paper-1"])
    tool_catalog_ids = list(tool_catalog_ids or search_candidates)
    search_output = {
        "schema_version": "runtime-v1",
        "work_item_id": search_id,
        "research_task_id": task.research_task_id,
        "safe_summary": {
            "decision": "catalog result",
            "search_id": output_search_id,
            "source_refs": [f"search:{output_search_id}"],
        },
        "source": "usenix",
        "search_id": output_search_id,
        "queries": ["goal"],
        "candidates": search_candidates,
        "refresh_diagnostics": {"degraded": False},
        "evidence_refs": [],
        "source_refs": [f"search:{output_search_id}"],
    }
    evaluator_output = {
        "schema_version": "paper-evaluation-v1",
        "work_item_id": evaluate_id,
        "safe_summary": {"decision": "kept catalog candidate"},
        "candidate_id": evaluator_candidate,
        "relevance_score": 0.9,
        "keep": True,
        "reason": "matches the goal",
        "kept": [{
            "candidate_id": evaluator_candidate,
            "keep": True,
            "relevance_score": 0.9,
            "evidence_refs": [f"catalog:{evaluator_candidate}"],
        }],
        "evidence_refs": [f"catalog:{evaluator_candidate}"],
        "source_refs": [],
    }
    search_run_id = f"{search_id}:run-1"
    evaluate_run_id = f"{evaluate_id}:run-1"
    completed_role_outputs = dict(completed_role_outputs or {})
    now = "2026-01-01T00:00:00Z"
    search_envelope = (
        search_output_json
        if search_output_json is not None
        else _outer(
            search_output,
            tool_results=[{
                "name": "search_paper_catalog",
                "status": "ok",
                "search_id": tool_search_id,
                "catalog_paper_ids": tool_catalog_ids,
                "summary": "bounded catalog result",
                "source_refs": [f"search:{tool_search_id}"],
            }],
            agent_run_id=search_run_id,
            output_hash_override=search_output_hash_override,
        )
    )
    evaluator_envelope = (
        evaluator_output_json
        if evaluator_output_json is not None
        else _outer(evaluator_output, agent_run_id=evaluate_run_id)
    )

    def role_output(role, work_item_id):
        if role == "research_critic":
            output = {
                "schema_version": "critic-v1",
                "work_item_id": work_item_id,
                "research_task_id": task.research_task_id,
                "safe_summary": {"decision": "persisted critic"},
                "source_refs": [],
                "coverage": {},
                "gaps": [],
                "recommendations": [],
                "bounded_replan": False,
            }
        else:
            output = {
                "schema_version": "synthesis-v1",
                "work_item_id": work_item_id,
                "research_task_id": task.research_task_id,
                "safe_summary": {"decision": "persisted synthesis"},
                "source_refs": [],
                "report_version": 1,
                "sections": [{"heading": "summary"}],
                "citation_manifest": [],
                "artifact_ids": [],
            }
        if completed_role_outputs.get(role) == "malformed":
            output.pop("coverage", None)
            output.pop("report_version", None)
        return output

    critic_envelope = (
        _outer(role_output("research_critic", critic_id), agent_run_id=f"{critic_id}:run-1")
        if "research_critic" in completed_role_outputs
        else None
    )
    synth_envelope = (
        _outer(role_output("synthesizer", synth_id), agent_run_id=f"{synth_id}:run-1")
        if "synthesizer" in completed_role_outputs
        else None
    )
    items = [
        ResearchWorkItem(
            search_id, task.research_task_id, 1, "search_catalog", "search-worker", "[]",
            '{"query":"goal"}', "completed", 1, now, now,
            output_json=search_envelope,
        ),
        ResearchWorkItem(
            evaluate_id, task.research_task_id, 1, "evaluate_papers", "paper-evaluator",
            json.dumps([search_id]), "{}", "completed", 1, now, now,
            output_json=evaluator_envelope,
        ),
        ResearchWorkItem(
            critic_id, task.research_task_id, 1, "check_coverage", "research-critic",
            json.dumps([evaluate_id]), '{"goal":"goal"}',
            "completed" if critic_envelope is not None else "queued",
            1 if critic_envelope is not None else 0,
            now if critic_envelope is not None else now,
            now if critic_envelope is not None else now,
            output_json=critic_envelope,
        ),
        ResearchWorkItem(
            synth_id, task.research_task_id, 1, "synthesize_preliminary_report", "synthesizer",
            json.dumps([critic_id]), '{"goal":"goal"}',
            "completed" if synth_envelope is not None else "queued",
            1 if synth_envelope is not None else 0,
            now if synth_envelope is not None else now,
            now if synth_envelope is not None else now,
            output_json=synth_envelope,
        ),
    ]
    store.create_work_items(task.research_task_id, items)
    if seed_agent_runs:
        for work_item_id, role, envelope_json in (
            (search_id, "search_worker", search_envelope),
            (evaluate_id, "paper_evaluator", evaluator_envelope),
            (critic_id, "research_critic", critic_envelope),
            (synth_id, "synthesizer", synth_envelope),
        ):
            if not envelope_json:
                continue
            try:
                envelope = json.loads(envelope_json)
            except (TypeError, ValueError):
                continue
            if envelope.get("status") == "completed" and isinstance(envelope.get("output_json"), dict):
                _create_completed_run(
                    store,
                    session=session,
                    task=task,
                    work_item_id=work_item_id,
                    role=role,
                    envelope=envelope,
                )
    return store, task, {"search": search_id, "evaluate": evaluate_id, "critic": critic_id, "synth": synth_id}


def test_restart_hydrates_completed_outputs_for_downstream_workers(tmp_path):
    store, task, ids = _build_store(tmp_path)
    runner = _CountingRunner()
    orchestrator = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    )

    result = orchestrator.run(task.research_task_id, "owner")

    assert [call.role for call in runner.calls] == ["research_critic", "synthesizer"]
    assert result.status == "completed", (result.status, result.error_code)
    assert store.get_work_item(ids["search"]).status == "completed"
    assert store.get_work_item(ids["evaluate"]).status == "completed"
    assert store.get_work_item(ids["critic"]).status == "completed"
    assert store.get_work_item(ids["synth"]).status == "completed"


@pytest.mark.parametrize(
    "persisted_search_output",
    [
        pytest.param(_outer({"candidates": ["paper-1"]}, status="failed"), id="failed-envelope"),
        pytest.param(_outer(None), id="null-output"),
        pytest.param("{not-json", id="malformed-envelope"),
    ],
)
def test_invalid_completed_output_cannot_unblock_downstream_workers(tmp_path, persisted_search_output):
    store, task, ids = _build_store(tmp_path, search_output_json=persisted_search_output)
    runner = _CountingRunner()
    orchestrator = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    )

    result = orchestrator.run(task.research_task_id, "owner")

    assert result.status == "partial"
    assert result.error_code == "UPSTREAM_WORK_ITEM_FAILED"
    assert runner.calls == []
    # A bad persisted payload is rejected in memory; the already-terminal row
    # is never reopened or rewritten just to make the recovery pass through.
    assert store.get_work_item(ids["search"]).status == "completed"
    assert store.get_work_item(ids["evaluate"]).status == "completed"
    assert store.get_work_item(ids["critic"]).status == "failed"
    assert store.get_work_item(ids["synth"]).status == "failed"


def test_persisted_evaluator_scope_is_rechecked_before_downstream_dispatch(tmp_path):
    forged_evaluator = {
        "schema_version": "paper-evaluation-v1",
        "work_item_id": "placeholder",
        "safe_summary": {"decision": "forged"},
        "candidate_id": "paper-not-recalled",
        "relevance_score": 1.0,
        "keep": True,
        "reason": "forged provenance",
        "evidence_refs": ["catalog:paper-not-recalled"],
        "source_refs": [],
    }
    # The fixture binds the real WorkItem ID into a persisted model envelope;
    # only the candidate/reference pair is forged.
    store, task, ids = _build_store(tmp_path)
    forged_evaluator["work_item_id"] = ids["evaluate"]
    store.update_work_item_status(
        ids["evaluate"], "completed", output_json=_outer(forged_evaluator)
    )
    runner = _CountingRunner()
    orchestrator = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    )

    result = orchestrator.run(task.research_task_id, "owner")

    assert result.status == "partial"
    assert result.error_code == "UPSTREAM_WORK_ITEM_FAILED"
    assert runner.calls == []
    assert store.get_work_item(ids["evaluate"]).status == "completed"
    assert store.get_work_item(ids["critic"]).status == "failed"
    assert store.get_work_item(ids["synth"]).status == "failed"


def test_recovery_rejects_candidate_not_present_in_successful_catalog_snapshot(tmp_path):
    store, task, ids = _build_store(
        tmp_path,
        search_candidates=["paper-forged"],
        tool_catalog_ids=["paper-1"],
        evaluator_candidate="paper-forged",
    )
    runner = _CountingRunner()

    result = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    ).run(task.research_task_id, "owner")

    assert result.status == "partial"
    assert result.error_code == "UPSTREAM_WORK_ITEM_FAILED"
    assert runner.calls == []
    assert store.get_work_item(ids["search"]).status == "completed"
    assert store.get_work_item(ids["evaluate"]).status == "completed"


def test_recovery_rejects_tool_candidate_tamper_even_when_output_is_unchanged(tmp_path):
    store, task, ids = _build_store(tmp_path)
    persisted = store.get_work_item(ids["search"])
    envelope = json.loads(persisted.output_json)
    original_output = json.dumps(envelope["output_json"], sort_keys=True)
    envelope["tool_results"][0]["catalog_paper_ids"] = ["paper-1", "paper-forged"]
    store.update_work_item_status(
        ids["search"], "completed", output_json=json.dumps(envelope, ensure_ascii=False)
    )
    assert json.dumps(envelope["output_json"], sort_keys=True) == original_output
    runner = _CountingRunner()

    result = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    ).run(task.research_task_id, "owner")

    assert result.status == "partial"
    assert result.error_code == "UPSTREAM_WORK_ITEM_FAILED"
    assert runner.calls == []
    assert store.get_work_item(ids["search"]).status == "completed"


def test_recovery_rejects_search_handle_or_source_ref_drift(tmp_path):
    store, task, ids = _build_store(
        tmp_path,
        tool_search_id="catalog-handle",
        output_search_id="model-handle",
    )
    runner = _CountingRunner()

    result = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    ).run(task.research_task_id, "owner")

    assert result.status == "partial"
    assert result.error_code == "UPSTREAM_WORK_ITEM_FAILED"
    assert runner.calls == []
    assert store.get_work_item(ids["search"]).status == "completed"


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"search_output_hash_override": "0" * 64}, id="changed-output-hash"),
        pytest.param({"seed_agent_runs": False}, id="missing-agent-run"),
    ],
)
def test_recovery_requires_hash_and_real_agent_run_binding(tmp_path, kwargs):
    store, task, ids = _build_store(tmp_path, **kwargs)
    runner = _CountingRunner()

    result = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    ).run(task.research_task_id, "owner")

    assert result.status == "partial"
    assert result.error_code == "UPSTREAM_WORK_ITEM_FAILED"
    assert runner.calls == []
    assert store.get_work_item(ids["search"]).status == "completed"


@pytest.mark.parametrize("role", ["research_critic", "synthesizer"])
def test_recovery_rejects_completed_role_output_missing_role_contract(tmp_path, role):
    store, task, ids = _build_store(
        tmp_path,
        completed_role_outputs={role: "malformed"},
    )
    runner = _CountingRunner()

    result = Orchestrator(
        store=store,
        planner=_planner(),
        agent_runner=runner,
        probe=_Probe(),
        memory_repository=None,
    ).run(task.research_task_id, "owner")

    assert result.status == "partial"
    expected_error = "AGENT_OUTPUT_INVALID" if role == "synthesizer" else "UPSTREAM_WORK_ITEM_FAILED"
    assert result.error_code == expected_error
    assert all(call.role != role for call in runner.calls)
    work_item_key = "critic" if role == "research_critic" else "synth"
    assert store.get_work_item(ids[work_item_key]).status == "completed"
