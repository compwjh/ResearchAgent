"""spec-038 P1 后半段：能力方法卡与技能改进建议的仓储契约（MD 化后的等价覆盖）。

背景
----
原文件（Task07）覆盖 `memories.category='capability_method'` 的方法卡与只读建议。
spec-038 已停用 ``memories`` / ``memory_evidence`` 表：能力方法的**语义**并入
Markdown 笔记（``MEMORY.md`` / ``projects/<id>.md``，由 ``MarkdownMemoryStore``
承载），因此：

- 「方法卡落库 + 证据门控 + 重复计数」的用例，改写为覆盖 **MD 等价路径**
  （``MarkdownMemoryStore.append_memory`` + ``load_snapshot`` 的 scope 隔离与
  预算截断），并新增 ``record_capability_failure`` 语义被移除的显式断言；
- ``skill_improvement_proposals`` 表**保留**，其状态机 / CAS / 保护区 hash 门控
  用例原样保留（仅把「来源记忆」从 memories 行改为 MD 条目 id）。

删除的用例与理由见 spec-038 任务报告。
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import MemoryRepository


def _repo(tmp_path):
    return MemoryRepository(tmp_path / "memory.sqlite3")


# ---------------------------------------------------------------- MD 等价路径


def test_capability_notes_are_scope_isolated_and_budgeted(tmp_path):
    """原 `test_capability_method_requires_evidence_and_is_scope_recalled` 的 MD 等价物。

    能力方法卡的语义（按 scope 隔离、按预算/关键词召回）现在由 MD 承载：
    ``append_memory(scope=...)`` 写入，``load_snapshot`` 按 scope 与预算装配。
    """
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.append_memory(scope="project", project_id="proj-a", content="先验证来源，再生成回答")
    store.append_memory(scope="global", project_id=None, content="跨项目通用方法")

    project_snapshot = store.load_snapshot(project_id="proj-a", max_chars=6000)
    other_snapshot = store.load_snapshot(project_id="proj-b", max_chars=6000)
    global_snapshot = store.load_snapshot(project_id=None, max_chars=6000)

    assert "先验证来源，再生成回答" in project_snapshot
    assert "跨项目通用方法" in project_snapshot
    # scope 隔离：项目记忆不泄漏到别的项目。
    assert "先验证来源，再生成回答" not in other_snapshot
    assert "跨项目通用方法" in other_snapshot
    assert "先验证来源，再生成回答" not in global_snapshot

    # 预算截断只作用于 MEMORY.md + 项目记忆，USER.md 画像优先全量注入。
    store.write_user("画像UNIQUE")
    tight = store.load_snapshot(project_id="proj-a", max_chars=40)
    assert "画像UNIQUE" in tight


def test_capability_note_requires_non_empty_content(tmp_path):
    """原 `test_capability_method_source_and_failure_gate` 的 MD 等价物（空内容拒绝）。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    with pytest.raises(ValueError):
        store.append_memory(scope="project", project_id="proj-a", content="   ")
    with pytest.raises(ValueError):
        store.append_memory(scope="project", project_id=None, content="缺少 project_id")
    with pytest.raises(ValueError):
        store.append_memory(scope="unknown", project_id=None, content="非法 scope")


def test_memories_table_is_retired_from_baseline(tmp_path):
    """回归保护：新基线不得再建出已停用表，也不得残留其读写方法。"""
    repo = _repo(tmp_path)
    with repo.connection() as db:
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "memories" not in tables
    assert "memory_evidence" not in tables
    assert "system_rules" not in tables
    for name in ("create_capability_method", "list_capability_methods", "record_capability_failure", "create_memory", "list_memories"):
        assert not hasattr(repo, name), name


# ------------------------------------------------------- 技能改进建议（表保留）


def test_skill_proposal_state_machine_and_applied_hash_gate(tmp_path):
    repo = _repo(tmp_path)
    project = repo.create_project("owner-a", "Project A")
    protected = {".agents/skills/example/SKILL.md": hashlib.sha256(b"stable").hexdigest()}
    proposal = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id,
        target_file=".agents/skills/example/SKILL.md", problem_evidence="失败后缺少验证步骤",
        diff_summary="补充验证步骤", verification_plan="运行 pytest", risk_summary="仅文档建议",
        source_memory_id="md-entry-1", protected_hash_before=protected,
    )
    with pytest.raises(ValueError):
        repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="applied", external_confirmation=True, protected_hash_after=protected)
    accepted = repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="accepted")
    assert accepted.status == "accepted"
    with pytest.raises(ValueError):
        repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="applied", external_confirmation=True, protected_hash_after={"changed": "hash"})
    applied = repo.update_skill_improvement_proposal(
        proposal.proposal_id, "owner-a", status="applied", external_confirmation=True,
        protected_hash_after=protected,
    )
    assert applied.status == "applied"
    assert repo.list_skill_improvement_proposals("owner-b") == []


def test_proposal_requires_non_empty_source_id_when_given(tmp_path):
    """原「来源必须是 capability method」校验改为「非空弱引用」后的契约。"""
    repo = _repo(tmp_path)
    project = repo.create_project("owner-a", "Project A")
    with pytest.raises(ValueError):
        repo.create_skill_improvement_proposal(
            "owner-a", scope="project", project_id=project.project_id, target_file="AGENTS.md",
            problem_evidence="e", diff_summary="d", verification_plan="v", risk_summary="r",
            source_memory_id="   ",
        )
    created = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id, target_file="AGENTS.md",
        problem_evidence="e", diff_summary="d", verification_plan="v", risk_summary="r",
        source_memory_id="md-entry-9",
    )
    assert created.source_memory_id == "md-entry-9"


def test_rejected_proposal_cannot_be_applied(tmp_path):
    repo = _repo(tmp_path)
    project = repo.create_project("owner-a", "Project A")
    hashes = {"AGENTS.md": "stable"}
    proposal = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id, target_file="AGENTS.md",
        problem_evidence="e", diff_summary="d", verification_plan="v", risk_summary="r",
        source_memory_id="md-entry-1", protected_hash_before=hashes,
    )
    repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="rejected")
    with pytest.raises(ValueError):
        repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="applied", external_confirmation=True, protected_hash_after=hashes)


def test_proposal_decision_is_compare_and_set_under_concurrency(tmp_path):
    repo = _repo(tmp_path)
    project = repo.create_project("owner-a", "Project A")
    hashes = {"AGENTS.md": "stable"}
    proposal = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id, target_file="AGENTS.md",
        problem_evidence="e", diff_summary="d", verification_plan="v", risk_summary="r",
        source_memory_id="md-entry-1", protected_hash_before=hashes,
    )
    repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="accepted")

    def reject(_):
        try:
            return ("ok", repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="rejected").status)
        except ValueError as error:
            return ("error", str(error))

    def apply(_):
        try:
            return ("ok", repo.update_skill_improvement_proposal(
                proposal.proposal_id, "owner-a", status="applied", external_confirmation=True,
                protected_hash_after=hashes,
            ).status)
        except ValueError as error:
            return ("error", str(error))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda fn: fn(None), (reject, apply)))
    assert sorted(result[0] for result in results) == ["error", "ok"]
    assert {result[1] for result in results if result[0] == "ok"} <= {"applied", "rejected"}
    assert repo.get_skill_improvement_proposal(proposal.proposal_id, "owner-a").status in {"applied", "rejected"}


def test_proposal_generation_does_not_write_protected_file(tmp_path):
    repo = _repo(tmp_path)
    project = repo.create_project("owner-a", "Project A")
    protected_path = tmp_path / "AGENTS.md"
    protected_path.write_text("protected", encoding="utf-8")
    before = hashlib.sha256(protected_path.read_bytes()).hexdigest()
    repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id,
        target_file=str(protected_path), problem_evidence="边界缺少说明", diff_summary="增加说明",
        verification_plan="人工审查", risk_summary="不自动应用", source_memory_id="md-entry-1",
        protected_hash_before={str(protected_path): before},
    )
    assert hashlib.sha256(protected_path.read_bytes()).hexdigest() == before
