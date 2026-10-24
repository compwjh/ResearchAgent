"""agent 路径（_run_agent_work_items）evaluator 完成后必须把真实候选落库到 research_paper_selections。

覆盖 Spec029 修复点：
1. evaluator completed 后 research_paper_selections 有行，且 ID 全部来自 Search Worker 召回白名单。
2. evaluator 输出含白名单外（模型自造）的 ID 时这些 ID 被丢弃而不是落库。
3. replace_selections 抛异常时流水线不崩（记 warning 继续后续 WorkItem）。
"""

import json
import uuid
from types import SimpleNamespace

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.agent_runtime import AgentRunOutput
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.planner import Planner
from backend.app.research.application.report_synthesis import ReportSynthesizer
from backend.app.research.domain.contracts import BUDGET_CAPS
from backend.app.research.domain.models import ResearchSession, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _id():
    return uuid.uuid4().hex


def _make_repo_and_store(tmp_path, target_paper_count=3):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages(
        "owner", "research goal", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        _id(), "owner", conversation.conversation_id, "research goal", "en",
        "balanced", False, target_paper_count, 60, "draft", 1, "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    )
    store.create_task(task)
    session = ResearchSession(
        _id(), "owner", conversation.conversation_id, user.message_id,
        _id(), "running", research_task_id=task.research_task_id,
        activity_message_id=assistant.message_id,
    )
    store.create_session(session, memory_repository=memory)
    store.update_session_links(session.research_session_id, "owner", research_task_id=task.research_task_id)
    return memory, store, task


class _FakeProbe:
    def arbitrate(self, _task_id, requested):
        return max(1, requested), None

    def release(self, _task_id):
        return None


def _search_output():
    return {
        "schema_version": "runtime-v1",
        "work_item_id": "PLACEHOLDER",
        "source": "usenix",
        "queries": ["research goal"],
        "candidates": ["paper-1", "paper-2", "paper-3"],
        "evidence_refs": [],
        "source_refs": [],
    }


def _evaluator_output(kept):
    return {
        "schema_version": "paper-evaluation-v1",
        "work_item_id": "PLACEHOLDER",
        "kept": kept,
        "evidence_refs": [],
        "source_refs": [],
    }


def _runner_for(kept):
    class _Runner:
        event_sink = None

        def run(self, run_input):
            output = _search_output() if run_input.role == "search_worker" else _evaluator_output(kept)
            output["work_item_id"] = run_input.work_item_id
            return AgentRunOutput(
                "completed", output_json=output, output_hash="hash",
                agent_run_id=run_input.agent_run_id,
            )

    return _Runner()


def _planner_with_search_and_evaluator():
    return SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=(
            {
                "id": "s1", "task_type": "search_catalog", "role": "search-worker",
                "depends_on": [], "params": {"query": "research goal"},
            },
            {
                "id": "e1", "task_type": "evaluate_papers", "role": "paper-evaluator",
                "depends_on": ["s1"], "params": {},
            },
        ),
    ))


def test_agent_path_persists_evaluator_selections_from_whitelist(tmp_path):
    _memory, store, task = _make_repo_and_store(tmp_path)
    kept = [
        {"candidate_id": "paper-1", "relevance_score": 0.9, "keep": True, "reason": "r",
         "evidence_refs": ["catalog:paper-1"]},
        {"candidate_id": "paper-2", "relevance_score": 0.4, "keep": True, "reason": "r",
         "evidence_refs": ["catalog:paper-2"]},
    ]
    runner = _runner_for(kept)
    planner = _planner_with_search_and_evaluator()
    orchestrator = Orchestrator(
        store=store, planner=planner, agent_runner=runner, probe=_FakeProbe(),
        memory_repository=None,
    )
    result = orchestrator.run(task.research_task_id, "owner")

    selections = store.list_selections(task.research_task_id)
    ids = {s.catalog_paper_id for s in selections}
    # 落库的全部来自 Search Worker 召回白名单（paper-1/2/3），无白名单外 ID。
    assert ids == {"paper-1", "paper-2"}, ids
    assert ids <= {"paper-1", "paper-2", "paper-3"}
    for s in selections:
        assert s.evidence_level == "catalog"
        assert isinstance(s.relevance, float)
        assert json.loads(s.facets_json) == []
    assert store.get_selection_version(task.research_task_id) >= 1
    assert result is not None


def test_persist_agent_selections_expands_aggregate_evidence_refs(tmp_path):
    """单条聚合产出：candidate_id 为 null，候选 ID 全在 evidence_refs 的 catalog:<id> 里。

    这是当前模型最常见的产出形状（实测 evaluate_papers 输出），必须全部展开落库，
    而不是只取第一个或整体漏掉。
    """
    _memory, store, task = _make_repo_and_store(tmp_path)
    orchestrator = Orchestrator(store=store, planner=Planner(), probe=_FakeProbe())
    aggregate_output = {
        "schema_version": "paper-evaluation-v1",
        "candidate_id": None,
        "keep": True,
        "relevance_score": 0.5,
        "evidence_refs": [
            "catalog:paper-1", "catalog:paper-2",
            # 白名单外的 ID（模型自造）必须被丢弃。
            "catalog:paper-9",
        ],
        "source_refs": [],
    }
    orchestrator._persist_agent_selections(
        task.research_task_id, aggregate_output, {"paper-1", "paper-2", "paper-3"}
    )
    selections = store.list_selections(task.research_task_id)
    ids = [s.catalog_paper_id for s in selections]
    assert set(ids) == {"paper-1", "paper-2"}, ids
    assert "paper-9" not in ids
    # 同一 ID 不重复落库。
    assert len(ids) == len(set(ids))
    for s in selections:
        assert s.evidence_level == "catalog"
        assert s.relevance == 0.5


def test_persist_agent_selections_skips_keep_false(tmp_path):
    _memory, store, task = _make_repo_and_store(tmp_path)
    orchestrator = Orchestrator(store=store, planner=Planner(), probe=_FakeProbe())
    orchestrator._persist_agent_selections(
        task.research_task_id,
        {"candidate_id": "paper-1", "keep": False, "relevance_score": 0.9,
         "evidence_refs": ["catalog:paper-1"]},
        {"paper-1", "paper-2", "paper-3"},
    )
    assert store.list_selections(task.research_task_id) == []


def test_persist_agent_selections_keeps_batch_aggregate_keep_false(tmp_path):
    """真实批量聚合产出：candidate_id 为 null、顶层 keep=False（task
    81241f3f01885e2c8f0490123f2215f3 实测形状）。这是批量容器而非显式拒绝，
    必须展开 evidence_refs 落库，不能被 keep=False 整体跳过（否则选集 0 条）。
    """
    _memory, store, task = _make_repo_and_store(tmp_path)
    orchestrator = Orchestrator(store=store, planner=Planner(), probe=_FakeProbe())
    batch_aggregate = {
        "schema_version": "paper-evaluation-v1",
        "candidate_id": None,
        "keep": False,
        "relevance_score": 0.0,
        "evidence_refs": [
            "catalog:paper-1", "catalog:paper-2",
            "catalog:paper-9",  # 白名单外（模型自造）必须被丢弃
        ],
        "source_refs": ["usenix_security"],
    }
    orchestrator._persist_agent_selections(
        task.research_task_id, batch_aggregate, {"paper-1", "paper-2", "paper-3"}
    )
    ids = [s.catalog_paper_id for s in store.list_selections(task.research_task_id)]
    assert set(ids) == {"paper-1", "paper-2"}, ids
    assert "paper-9" not in ids
    assert len(ids) == len(set(ids))


def _runner_for_batch_aggregate():
    class _Runner:
        event_sink = None

        def run(self, run_input):
            if run_input.role == "search_worker":
                output = {
                    "schema_version": "runtime-v1",
                    "work_item_id": run_input.work_item_id,
                    "source": "usenix",
                    "queries": ["goal"],
                    "candidates": ["paper-1", "paper-2", "paper-3"],
                    "evidence_refs": [],
                    "source_refs": [],
                }
            # planner 里的 "paper-evaluator" 会经 orchestrator.py:910-913 的 role_map
            # 规范化为下划线形式，传给 run() 的 run_input.role 是 paper_evaluator。
            elif run_input.role == "paper_evaluator":
                output = {
                    "schema_version": "paper-evaluation-v1",
                    "work_item_id": run_input.work_item_id,
                    # 真实批量聚合形状：candidate_id=null, keep=False。
                    "candidate_id": None,
                    "keep": False,
                    "relevance_score": 0.0,
                    "evidence_refs": [
                        "catalog:paper-1", "catalog:paper-2", "catalog:paper-3",
                    ],
                    "source_refs": ["usenix_security"],
                }
            else:  # synthesizer
                output = {
                    "schema_version": "synthesis-v1",
                    "work_item_id": run_input.work_item_id,
                    "report": "ok",
                }
            return AgentRunOutput(
                "completed", output_json=output, output_hash="hash",
                agent_run_id=run_input.agent_run_id,
            )

    return _Runner()


def _planner_with_search_evaluator_synth():
    return SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=(
            {
                "id": "s1", "task_type": "search_catalog", "role": "search-worker",
                "depends_on": [], "params": {"query": "goal"},
            },
            {
                "id": "e1", "task_type": "evaluate_papers", "role": "paper-evaluator",
                "depends_on": ["s1"], "params": {},
            },
            {
                "id": "syn", "task_type": "synthesize_preliminary_report", "role": "synthesizer",
                "depends_on": ["e1"], "params": {},
            },
        ),
    ))


def test_batch_aggregate_evaluator_runs_synthesizer(tmp_path):
    """端到端：真实批量聚合 evaluator（candidate_id=null, keep=False）完成且
    recall 白名单 populated 时，synthesizer 不得因 NO_VALIDATED_EVIDENCE 被跳过，
    且 research_paper_selections 应落库。直接复现 task 81241f3f01885e2c8f0490123f2215f3。
    """
    _memory, store, task = _make_repo_and_store(tmp_path)
    runner = _runner_for_batch_aggregate()
    planner = _planner_with_search_evaluator_synth()
    orchestrator = Orchestrator(
        store=store, planner=planner, agent_runner=runner, probe=_FakeProbe(),
        memory_repository=None,
    )
    result = orchestrator.run(task.research_task_id, "owner")

    syn_items = [i for i in store.list_work_items(task.research_task_id, plan_version=1)
                 if i.role == "synthesizer"]
    assert syn_items, "synthesizer WorkItem was created"
    assert syn_items[0].status == "completed", syn_items[0].status
    assert result.status != "failed", (result.status, result.error_code)

    # 选集落库（candidate_id=null, keep=False 不再是跳过理由）。
    ids = {s.catalog_paper_id for s in store.list_selections(task.research_task_id)}
    assert ids == {"paper-1", "paper-2", "paper-3"}, ids


def test_persist_agent_selections_drops_out_of_whitelist_ids(tmp_path):
    _memory, store, task = _make_repo_and_store(tmp_path)
    orchestrator = Orchestrator(store=store, planner=Planner(), probe=_FakeProbe())
    evaluator_output = _evaluator_output([
        {"candidate_id": "paper-1", "relevance_score": 0.9, "evidence_refs": ["catalog:paper-1"]},
        {"candidate_id": "paper-2", "relevance_score": 0.5, "evidence_refs": ["catalog:paper-2"]},
        # 模型自造的 ID，不在白名单内，必须被丢弃。
        {"candidate_id": "paper-9", "relevance_score": 0.99, "evidence_refs": ["catalog:paper-9"]},
    ])
    orchestrator._persist_agent_selections(
        task.research_task_id, evaluator_output, {"paper-1", "paper-2", "paper-3"}
    )
    ids = {s.catalog_paper_id for s in store.list_selections(task.research_task_id)}
    assert ids == {"paper-1", "paper-2"}
    assert "paper-9" not in ids


def test_persist_agent_selections_survives_store_failure(tmp_path, caplog):
    _memory, store, task = _make_repo_and_store(tmp_path)
    orchestrator = Orchestrator(store=store, planner=Planner(), probe=_FakeProbe())

    def boom(*_args, **_kwargs):
        raise ValueError("disk full")

    original = store.replace_selections
    store.replace_selections = boom
    try:
        # 不应抛异常；选集写不进去不应让流水线崩。
        orchestrator._persist_agent_selections(
            task.research_task_id,
            _evaluator_output([
                {"candidate_id": "paper-1", "relevance_score": 0.9, "evidence_refs": ["catalog:paper-1"]},
            ]),
            {"paper-1", "paper-2", "paper-3"},
        )
    finally:
        store.replace_selections = original
    assert "agent evaluator selections not persisted" in caplog.text
    assert store.list_selections(task.research_task_id) == []


def test_agent_path_run_survives_replace_selections_failure(tmp_path):
    _memory, store, task = _make_repo_and_store(tmp_path)
    kept = [
        {"candidate_id": "paper-1", "relevance_score": 0.9, "keep": True, "reason": "r",
         "evidence_refs": ["catalog:paper-1"]},
    ]
    runner = _runner_for(kept)
    planner = _planner_with_search_and_evaluator()

    def boom(*_args, **_kwargs):
        raise ValueError("disk full")

    original = store.replace_selections
    store.replace_selections = boom
    try:
        orchestrator = Orchestrator(
            store=store, planner=planner, agent_runner=runner, probe=_FakeProbe(),
            memory_repository=None,
        )
        # 整条流水线不得因选集落库失败而冒泡异常或把任务打成 failed。
        result = orchestrator.run(task.research_task_id, "owner")
    finally:
        store.replace_selections = original
    assert result is not None
    assert result.status != "failed"
    # 选集确实没写进去（落库被故意搞挂），但不影响流水线收尾。
    assert store.list_selections(task.research_task_id) == []


def test_persist_agent_selections_enforces_global_selection_cap(tmp_path):
    _memory, store, task = _make_repo_and_store(tmp_path, target_paper_count=20)
    orchestrator = Orchestrator(store=store, planner=Planner(), probe=_FakeProbe())
    candidate_ids = [f"paper-{index}" for index in range(25)]
    kept = [
        {
            "candidate_id": candidate_id,
            "relevance_score": 0.9,
            "keep": True,
            "evidence_refs": [f"catalog:{candidate_id}"],
        }
        for candidate_id in candidate_ids
    ]
    kept.append(dict(kept[0]))

    orchestrator._persist_agent_selections(
        task.research_task_id,
        _evaluator_output(kept),
        set(candidate_ids),
        target_paper_count=task.target_paper_count,
    )

    ids = [item.catalog_paper_id for item in store.list_selections(task.research_task_id)]
    assert len(ids) == BUDGET_CAPS["max_selected"]
    assert set(ids) == set(candidate_ids[: BUDGET_CAPS["max_selected"]])
    assert len(ids) == len(set(ids))


def test_agent_selection_budget_is_shared_by_persistence_report_matrix_and_terminal(tmp_path, monkeypatch):
    memory, store, task = _make_repo_and_store(tmp_path, target_paper_count=5)
    candidate_ids = [f"paper-{index}" for index in range(25)]
    kept = [
        {
            "candidate_id": candidate_id,
            "relevance_score": 0.9,
            "keep": True,
            "evidence_refs": [f"catalog:{candidate_id}"],
        }
        for candidate_id in candidate_ids
    ]
    kept.append(dict(kept[0]))
    candidates = [
        {"candidate_id": candidate_id, "verified": True, "evidence_refs": [f"catalog:{candidate_id}"]}
        for candidate_id in candidate_ids[:5]
    ]
    synthesis = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=candidates,
        citation_manifest=[
            {"citation_ref": f"catalog:{candidate_id}", "candidate_id": candidate_id}
            for candidate_id in candidate_ids[:5]
        ],
    ).output.model_dump(mode="json")

    class Runner:
        event_sink = None

        def run(self, run_input):
            if run_input.role == "search_worker":
                output = {
                    "schema_version": "runtime-v1",
                    "work_item_id": run_input.work_item_id,
                    "source": "usenix",
                    "queries": ["research goal"],
                    "candidates": candidate_ids + [candidate_ids[0]],
                    "evidence_refs": [],
                    "source_refs": [],
                }
            elif run_input.role == "paper_evaluator":
                output = _evaluator_output(kept)
            else:
                output = synthesis
            if run_input.role != "synthesizer":
                output["work_item_id"] = run_input.work_item_id
            return AgentRunOutput(
                "completed", output_json=output, output_hash="hash", agent_run_id=run_input.agent_run_id,
            )

    seen_matrix = {}

    def capture_matrix_context(_self, *, validated_candidates, **_kwargs):
        bounded_ids = [item["candidate_id"] for item in validated_candidates]
        seen_matrix["ids"] = bounded_ids
        return {"allowed_paper_ids": bounded_ids}

    monkeypatch.setattr(Orchestrator, "_build_synthesis_matrix_context", capture_matrix_context)
    orchestrator = Orchestrator(
        store=store,
        planner=_planner_with_search_evaluator_synth(),
        agent_runner=Runner(),
        probe=_FakeProbe(),
        memory_repository=memory,
    )

    result = orchestrator.run(task.research_task_id, "owner")

    selections = store.list_selections(task.research_task_id)
    assert len(selections) == task.target_paper_count
    assert len({item.catalog_paper_id for item in selections}) == task.target_paper_count
    synthesizer = next(
        item for item in store.list_work_items(task.research_task_id, plan_version=1)
        if item.role == "synthesizer"
    )
    synthesizer_input = json.loads(synthesizer.input_json)
    assert len(synthesizer_input["validated_candidates"]) == task.target_paper_count
    assert len(synthesizer_input["citation_allowlist"]) == task.target_paper_count
    assert len(seen_matrix["ids"]) == task.target_paper_count
    selection_ids = {item.catalog_paper_id for item in selections}
    synthesizer_ids = {item["candidate_id"] for item in synthesizer_input["validated_candidates"]}
    assert selection_ids == synthesizer_ids == set(seen_matrix["ids"])
    terminal = [item for item in store.list_events(task.research_task_id) if item.event_type == "terminal"]
    assert terminal
    assert json.loads(terminal[-1].safe_payload_json)["selected_count"] == task.target_paper_count
    assert result.selected_count == task.target_paper_count
    assert result.selected_count <= BUDGET_CAPS["max_selected"]
