"""未派发的 WorkItem 必须真正落到 failed，而不是永远停在 queued。

状态机只允许 ``queued -> running -> failed``。此前 agent 路径在跳过 WorkItem 时
直接从 queued 写 failed，抛 InvalidStateTransition 后被 ``suppress`` 吞掉，
结果是这些永远不会再被派发的 WorkItem 一直显示 ``queued``、``error_code`` 也丢失。
"""

import re
import uuid
from types import SimpleNamespace

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.agent_runtime import AgentRunOutput
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.domain.models import ResearchSession, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _id():
    return uuid.uuid4().hex


def _build(tmp_path, evaluator_output):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages(
        "owner", "research goal", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        _id(), "owner", conversation.conversation_id, "research goal", "en",
        "balanced", False, 3, 60, "draft", 1, "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    )
    store.create_task(task)
    session = ResearchSession(
        _id(), "owner", conversation.conversation_id, user.message_id,
        _id(), "running", research_task_id=task.research_task_id,
        activity_message_id=assistant.message_id,
    )
    store.create_session(session, memory_repository=memory)
    store.update_session_links(
        session.research_session_id, "owner", research_task_id=task.research_task_id
    )
    return store, task, evaluator_output


class _FakeProbe:
    def arbitrate(self, _task_id, requested):
        return max(1, requested), None

    def release(self, _task_id):
        return None


class _Runner:
    """Search Worker 正常召回；evaluator 返回调用方给定的形状。"""

    event_sink = None

    def __init__(self, evaluator_output):
        self._evaluator_output = evaluator_output

    def run(self, run_input):
        if run_input.role == "search_worker":
            output = {
                "schema_version": "runtime-v1",
                "work_item_id": run_input.work_item_id,
                "source": "usenix",
                "queries": ["research goal"],
                "candidates": ["paper-1"],
                "evidence_refs": [],
                "source_refs": [],
            }
        else:
            output = dict(self._evaluator_output)
            output["work_item_id"] = run_input.work_item_id
        return AgentRunOutput(
            "completed", output_json=output, output_hash="hash",
            agent_run_id=run_input.agent_run_id,
        )


def _plan():
    return SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=(
            {"id": "s1", "task_type": "search_catalog", "role": "search-worker",
             "depends_on": [], "params": {}},
            {"id": "e1", "task_type": "evaluate_papers", "role": "paper-evaluator",
             "depends_on": ["s1"], "params": {}},
            {"id": "syn", "task_type": "synthesize_preliminary_report", "role": "synthesizer",
             "depends_on": ["e1"], "params": {}},
        ),
    ))


def _find(items, suffix):
    # work_item_id 形如 "<task_id>:syn" 或 "<task_id>-syn"，两种分隔符都要兼容。
    for item in items:
        if re.split(r"[:-]", item.work_item_id)[-1] == suffix:
            return item
    raise AssertionError(f"work item {suffix} not found")


def test_skipped_synthesizer_is_marked_failed_not_queued(tmp_path):
    """被跳过的 WorkItem 必须真的落 failed，而不是停在 queued（状态机可见性）。

    本用例真正要验证的是「被跳过的 WorkItem 必须真正落到 failed，不能停在 queued」，
    而不是验证「缺元数据就要跳过 synthesizer」。

    新设计（P0 修复）下：被 Search Worker 召回过的 ID 即使缺本地元数据，也会在
    Search Worker 召回白名单内被展开为有效候选，synthesizer 会正常运行。因此
    「无法解析出有效候选」的正确构造是让 evaluator 引用一个**从未被召回**的 ID
    （`catalog:paper-not-recalled` 不在 Search Worker 召回的 `["paper-1"]` 内）。
    原写法 `catalog:paper-1` 依赖的其实是那个已被修掉的 bug（无元数据即丢弃候选）。
    """
    # 聚合形产出且 evidence_refs 指向「从未被 Search Worker 召回」的 ID（白名单外）。
    # 既不在召回白名单内、又无本地元数据 -> 无法展开为有效候选 -> 无 validated 候选。
    # 注意：若引用召回过的 paper-1，新设计会直接展开为候选，synthesizer 转为 completed。
    evaluator_output = {
        "schema_version": "paper-evaluation-v1",
        "candidate_id": None,
        "keep": True,
        "relevance_score": 0.5,
        "evidence_refs": ["catalog:paper-not-recalled"],
        "source_refs": [],
    }
    store, task, _ = _build(tmp_path, evaluator_output)
    orchestrator = Orchestrator(
        store=store, planner=_plan(), agent_runner=_Runner(evaluator_output),
        probe=_FakeProbe(), memory_repository=None,
    )
    result = orchestrator.run(task.research_task_id, "owner")

    synth = _find(store.list_work_items(task.research_task_id), "syn")
    # 关键：不能停在 queued（此前 suppress 掉了非法转移）。
    assert synth.status == "failed", synth.status
    assert synth.error_code == "NO_VALIDATED_EVIDENCE", synth.error_code
    assert result.status == "partial"


def test_completed_path_still_runs_synthesizer(tmp_path):
    """evaluator 给出明确 candidate_id 时，synthesizer 正常派发并 completed。"""
    evaluator_output = {
        "schema_version": "paper-evaluation-v1",
        "candidate_id": "paper-1",
        "keep": True,
        "relevance_score": 0.5,
        "evidence_refs": ["catalog:paper-1"],
        "source_refs": [],
    }
    store, task, _ = _build(tmp_path, evaluator_output)
    orchestrator = Orchestrator(
        store=store, planner=_plan(), agent_runner=_Runner(evaluator_output),
        probe=_FakeProbe(), memory_repository=None,
    )
    result = orchestrator.run(task.research_task_id, "owner")

    synth = _find(store.list_work_items(task.research_task_id), "syn")
    assert synth.status == "completed", (synth.status, synth.error_code)
    assert result.status == "completed", (result.status, result.error_code)
