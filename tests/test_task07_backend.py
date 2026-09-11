"""Task07 backend contracts for capability methods and read-only proposals."""

import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.chat.application.conversation_service import MemoryEvolutionService
from backend.app.memory.repository import MemoryRepository


def _fixture(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Project A")
    conversation = repo.create_conversation("owner-a", project.project_id)
    message = repo.create_message(conversation.conversation_id, "owner-a", "user", "记住这个方法", status="completed")
    return repo, project, conversation, message


def test_capability_method_requires_evidence_and_is_scope_recalled(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    method = repo.create_capability_method(
        "owner-a",
        scope="project",
        project_id=project.project_id,
        statement="先验证来源，再生成回答",
        source_kind="explicit",
        confidence=0.92,
        evidence=(conversation.conversation_id, message.message_id, "user_statement", "先验证来源"),
    )
    assert method.category == "capability_method"
    assert repo.list_capability_methods("owner-a", project.project_id, query="验证来源")[0].memory_id == method.memory_id
    assert repo.list_capability_methods("owner-b", project.project_id) == []


def test_capability_method_source_and_failure_gate(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    with pytest.raises(ValueError):
        repo.create_capability_method("owner-a", scope="project", project_id=project.project_id, statement="无证据", source_kind="explicit", confidence=0.9)
    with pytest.raises(ValueError):
        repo.create_capability_method("owner-a", scope="project", project_id=project.project_id, statement="手工无证据", source_kind="manual", confidence=0.9)
    method = repo.create_capability_method(
        "owner-a", scope="project", project_id=project.project_id,
        statement="使用结构化检查清单", source_kind="repeated", confidence=0.9,
        evidence=(conversation.conversation_id, message.message_id, "repeated_sessions", "跨会话重复"),
    )
    repo.record_capability_failure("owner-a", method.memory_id, conversation.conversation_id, message.message_id, "失败信号")
    lowered = repo.get_memory(method.memory_id, "owner-a")
    assert lowered.status == "candidate"
    assert lowered.confidence < method.confidence
    assert len(repo.list_memory_evidence(method.memory_id, "owner-a")) == 2


def test_verified_tool_failure_can_create_candidate_method(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    service = MemoryEvolutionService(repo)
    service.record_trigger(
        "owner-a", conversation.conversation_id, "tool_failure",
        {"category": "capability_method", "statement": "失败后先重试并验证结果", "verified": True, "verification": "结果已通过校验"},
        message_id=message.message_id,
    )
    service.process_session(conversation.conversation_id, "owner-a", trigger="tool_failure")
    methods = repo.list_capability_methods("owner-a", project.project_id, include_candidates=True)
    assert len(methods) == 1
    assert methods[0].status == "candidate"
    assert methods[0].source_kind == "verified_failure"


def test_method_explicit_rejects_assistant_message(tmp_path):
    repo, project, conversation, _ = _fixture(tmp_path)
    assistant = repo.create_message(conversation.conversation_id, "owner-a", "assistant", "伪造的方法", status="completed")
    service = MemoryEvolutionService(repo)
    with pytest.raises(ValueError, match="user message"):
        service.record_trigger(
            "owner-a", conversation.conversation_id, "method_explicit",
            {"category": "capability_method", "method_statement": "伪造的方法"}, message_id=assistant.message_id,
        )
    repo.append_raw_event(
        "owner-a", conversation.conversation_id, "method_explicit",
        {"category": "capability_method", "method_statement": "伪造的方法"}, message_id=assistant.message_id,
    )
    service.process_session(conversation.conversation_id, "owner-a", trigger="method_explicit")
    assert repo.list_capability_methods("owner-a", project.project_id, include_candidates=True) == []


def test_method_repeated_ignores_forged_count_and_requires_two_conversations(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    service = MemoryEvolutionService(repo)
    payload = {
        "category": "capability_method", "method_statement": "跨会话复用的方法", "repeated_sessions": 99,
    }
    service.record_trigger("owner-a", conversation.conversation_id, "method_repeated", payload, message_id=message.message_id)
    service.process_session(conversation.conversation_id, "owner-a", trigger="method_repeated")
    assert repo.list_capability_methods("owner-a", project.project_id, include_candidates=True) == []

    conversation2 = repo.create_conversation("owner-a", project.project_id)
    message2 = repo.create_message(conversation2.conversation_id, "owner-a", "user", "再次复用", status="completed")
    service.record_trigger("owner-a", conversation2.conversation_id, "method_repeated", payload, message_id=message2.message_id)
    service.process_session(conversation2.conversation_id, "owner-a", trigger="method_repeated")
    methods = repo.list_capability_methods("owner-a", project.project_id, include_candidates=True)
    assert len(methods) == 1
    assert methods[0].source_kind == "repeated"


def test_verified_failure_can_enqueue_review_only_proposal(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    service = MemoryEvolutionService(repo)
    service.record_trigger(
        "owner-a", conversation.conversation_id, "tool_failure",
        {
            "category": "capability_method", "statement": "失败后先重试并验证结果",
            "verified": True, "verification": "结果已通过校验", "target_file": ".agents/skills/example/SKILL.md",
            "diff_summary": "补充重试后的验证步骤",
        },
        message_id=message.message_id,
    )
    service.process_session(conversation.conversation_id, "owner-a", trigger="tool_failure")
    proposals = repo.list_skill_improvement_proposals("owner-a", project_id=project.project_id)
    assert len(proposals) == 1
    assert proposals[0].status == "proposed"


def test_skill_proposal_state_machine_and_applied_hash_gate(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    method = repo.create_capability_method(
        "owner-a", scope="project", project_id=project.project_id,
        statement="先做最小验证", source_kind="explicit", confidence=0.95,
        evidence=(conversation.conversation_id, message.message_id, "user_statement", "最小验证"),
    )
    protected = {".agents/skills/example/SKILL.md": hashlib.sha256(b"stable").hexdigest()}
    proposal = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id,
        target_file=".agents/skills/example/SKILL.md", problem_evidence="失败后缺少验证步骤",
        diff_summary="补充验证步骤", verification_plan="运行 Task07 pytest", risk_summary="仅文档建议",
        source_memory_id=method.memory_id, protected_hash_before=protected,
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


def test_rejected_proposal_cannot_be_applied(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    method = repo.create_capability_method(
        "owner-a", scope="project", project_id=project.project_id, statement="拒绝后不可应用",
        source_kind="explicit", confidence=0.9,
        evidence=(conversation.conversation_id, message.message_id, "user_statement", "拒绝后不可应用"),
    )
    hashes = {"AGENTS.md": "stable"}
    proposal = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id, target_file="AGENTS.md",
        problem_evidence="e", diff_summary="d", verification_plan="v", risk_summary="r",
        source_memory_id=method.memory_id, protected_hash_before=hashes,
    )
    repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="rejected")
    with pytest.raises(ValueError):
        repo.update_skill_improvement_proposal(proposal.proposal_id, "owner-a", status="applied", external_confirmation=True, protected_hash_after=hashes)


def test_proposal_decision_is_compare_and_set_under_concurrency(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    method = repo.create_capability_method(
        "owner-a", scope="project", project_id=project.project_id, statement="并发决策方法",
        source_kind="explicit", confidence=0.9,
        evidence=(conversation.conversation_id, message.message_id, "user_statement", "并发决策方法"),
    )
    hashes = {"AGENTS.md": "stable"}
    proposal = repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id, target_file="AGENTS.md",
        problem_evidence="e", diff_summary="d", verification_plan="v", risk_summary="r",
        source_memory_id=method.memory_id, protected_hash_before=hashes,
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


def test_task07_schema_validation_checks_column_shape_and_indexes(tmp_path):
    path = tmp_path / "corrupt-task07.sqlite3"
    repo = MemoryRepository(path)
    with repo.connection() as db:
        db.execute("DROP TABLE skill_improvement_proposals")
        db.execute("""CREATE TABLE skill_improvement_proposals(
            proposal_id INTEGER PRIMARY KEY,
            owner_id TEXT NOT NULL, scope TEXT NOT NULL, project_id TEXT,
            target_file TEXT NOT NULL, problem_evidence TEXT NOT NULL,
            diff_summary TEXT NOT NULL, verification_plan TEXT NOT NULL,
            risk_summary TEXT NOT NULL, status TEXT NOT NULL,
            protected_hash_before TEXT NOT NULL, protected_hash_after TEXT NOT NULL,
            source_memory_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            decided_at TEXT
        )""")
        db.execute("CREATE INDEX idx_skill_proposals_scope ON skill_improvement_proposals(status, owner_id)")
        db.execute("CREATE INDEX idx_skill_proposals_source ON skill_improvement_proposals(owner_id)")
    with pytest.raises(RuntimeError, match="fail-closed"):
        MemoryRepository(path)


def test_capability_method_creation_is_idempotent_under_concurrency(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)

    def create_one(_):
        return repo.create_capability_method(
            "owner-a", scope="project", project_id=project.project_id,
            statement="并发请求只保留一张方法卡", source_kind="explicit", confidence=0.9,
            evidence=(conversation.conversation_id, message.message_id, "user_statement", "并发请求"),
        ).memory_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(create_one, range(8)))
    assert len(set(ids)) == 1
    with repo.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM memories WHERE owner_id=? AND category='capability_method'", ("owner-a",)).fetchone()[0] == 1


def test_proposal_generation_does_not_write_protected_file(tmp_path):
    repo, project, conversation, message = _fixture(tmp_path)
    method = repo.create_capability_method(
        "owner-a", scope="project", project_id=project.project_id,
        statement="先检查输入边界", source_kind="explicit", confidence=0.9,
        evidence=(conversation.conversation_id, message.message_id, "user_statement", "检查边界"),
    )
    protected_path = tmp_path / "AGENTS.md"
    protected_path.write_text("protected", encoding="utf-8")
    before = hashlib.sha256(protected_path.read_bytes()).hexdigest()
    repo.create_skill_improvement_proposal(
        "owner-a", scope="project", project_id=project.project_id,
        target_file=str(protected_path), problem_evidence="边界缺少说明", diff_summary="增加说明",
        verification_plan="人工审查", risk_summary="不自动应用", source_memory_id=method.memory_id,
        protected_hash_before={str(protected_path): before},
    )
    assert hashlib.sha256(protected_path.read_bytes()).hexdigest() == before
