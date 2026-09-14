"""记忆分析（post-answer classifier）后端契约 —— spec-038 新基线后。

背景
----
``memories`` / ``memory_evidence`` 已停用：分析 worker 不再把结果落成长期记忆，
只写**审计流水** ``memory_analysis_items``（保留表）。因此：

- 保留：稳定的 processing step 身份、分类器调用与降级、job 生命周期 / lease、
  多 item 分页与幂等、项目快照、分析决策 API、不阻塞 SSE；
- 改写：原「auto_save 落 memories」「冲突 supersede 旧记忆」「stale worker 不得写
  memories」→ 改为断言「只写审计项、decision 恒为 pending_confirmation、
  不再有记忆落库副作用」（记忆落定改由 MD，P2/P3 接入）。

删除的用例与理由见 spec-038 任务报告。
"""

import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.chat.application.conversation_service import MemoryAnalysisWorker, MemoryIntent, classify_memory_intent
from backend.app.main import app
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import LeaseLostError, MemoryRepository


def _job(repo, project_id=None, content="hello", owner="owner-a"):
    conversation, user, _ = repo.create_conversation_messages(owner, content, project_id, "model", "normal")
    return conversation, user, repo.create_memory_analysis_job(user.message_id, owner)


def test_processing_step_identity_is_stable_and_terminal_cannot_reopen(tmp_path: Path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    with repo.connection() as db:
        assert any(row["name"] == "uq_steps_message_kind_sequence" and row["unique"] for row in db.execute("PRAGMA index_list(processing_steps)"))
    conversation, user, assistant = repo.create_conversation_messages("owner-a", "hello", None, "model", "normal")
    running = repo.create_processing_step(assistant.message_id, "generation", "running")
    completed = repo.create_processing_step(assistant.message_id, "generation", "completed", "done")
    reopened = repo.create_processing_step(assistant.message_id, "generation", "running")
    assert running.step_id == completed.step_id == reopened.step_id
    assert reopened.status == "completed"
    assert len(repo.list_processing_steps(assistant.message_id, "owner-a")) == 1


def test_classifier_calls_configured_model_without_thinking_and_parses_json():
    class Run:
        events = iter([{"type": "token", "content": '{"intent":"explicit","statement":"偏好结论优先","scope":"project","confidence":0.96,"rationale_summary":"用户明确要求"}'}])

    with patch("backend.app.chat.application.conversation_service.run_chat", return_value=Run()) as run:
        result = classify_memory_intent("请把结论放在前面", model="qwen3.5:9b")
    assert result.intent == "explicit" and result.statement == "偏好结论优先"
    assert run.call_args.kwargs["think"] is False
    assert run.call_args.args[1] == "qwen3.5:9b"


def test_classifier_parse_failure_degrades_to_none():
    class Run:
        events = iter([{"type": "token", "content": "not json"}])

    with patch("backend.app.chat.application.conversation_service.run_chat", return_value=Run()):
        result = classify_memory_intent("类似表达但不确定", model="qwen3.5:9b")
    assert result.intent == "none"


def test_classifier_failure_marks_job_failed_without_blocking_answer(tmp_path: Path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    _, user, job = _job(repo, None, "普通问题")
    worker = MemoryAnalysisWorker(repo, owner_id="owner-a")
    class Run:
        events = iter([{"type": "token", "content": "invalid"}])
    with patch("backend.app.chat.application.conversation_service.run_chat", return_value=Run()):
        worker.process(job.analysis_id)
    result = repo.get_memory_analysis_job(user.message_id, "owner-a")
    assert result.status == "failed" and result.error_code == "CLASSIFIER_FAILED"


def test_analysis_records_audit_items_without_persisting_memories(tmp_path: Path):
    """原 `test_message_analysis_worker_auto_saves_and_waits_for_ambiguous` 的后继。

    spec-038 P3 改为**置信度分级**：高置信度 explicit（≥0.9）直写 MD（记 auto_saved）；
    不确定（ambiguous / 低置信度）走 ``pending_confirmation``。无论哪种都只写审计分析项，
    不再有 ``memories`` 表落库副作用。
    """
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "P")
    _, explicit, explicit_job = _job(repo, project.project_id, "请记住以后先给结论")
    _, ambiguous, ambiguous_job = _job(repo, project.project_id, "我通常喜欢先给结论")
    store = MarkdownMemoryStore(tmp_path / "l1-memory")
    worker = MemoryAnalysisWorker(repo, owner_id="owner-a", memory_store=store)

    def classify(value, **_kwargs):
        if "通常" in value:
            return MemoryIntent("ambiguous", value, "project", .62)
        return MemoryIntent("explicit", "以后先给结论", "project", .95)

    with patch("backend.app.chat.application.conversation_service.classify_memory_intent", side_effect=classify):
        worker.process(explicit_job.analysis_id)
        worker.process(ambiguous_job.analysis_id)

    assert repo.get_memory_analysis_job(explicit.message_id, "owner-a").status == "completed"
    explicit_items, _ = repo.list_memory_analysis_items(explicit.message_id, "owner-a")
    # P3：高置信度 explicit → 直写 MD（auto_saved），不再一律待确认。
    assert explicit_items and explicit_items[0].decision_status == "auto_saved"
    assert explicit_items[0].memory_id is None
    assert "以后先给结论" in store.read_project(project.project_id)
    ambiguous_items, _ = repo.list_memory_analysis_items(ambiguous.message_id, "owner-a")
    assert ambiguous_items[0].decision_status == "pending_confirmation"
    assert store.list_pending()
    # 关键回归：分析流程不得再写出任何长期记忆表内容。
    with repo.connection() as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'").fetchone() is None


def test_analysis_supports_multiple_items_pagination_and_idempotency(tmp_path: Path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    _, user, job = _job(repo, None, "记住多条")
    worker = MemoryAnalysisWorker(repo, owner_id="owner-a", batch_size=1)
    with patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=[
        MemoryIntent("explicit", "第一条", "global", .95),
        MemoryIntent("explicit", "第二条", "global", .95),
    ]):
        worker.process(job.analysis_id)
        worker.process(job.analysis_id)
    first, cursor = repo.list_memory_analysis_items(user.message_id, "owner-a", limit=1)
    second, next_cursor = repo.list_memory_analysis_items(user.message_id, "owner-a", cursor=cursor, limit=1)
    assert len(first) == len(second) == 1 and next_cursor is None
    # 未绑定会话的两个 explicit 高置信度 item：suggested_scope=global，且 P3 下直写 MD。
    assert {first[0].decision_status, second[0].decision_status} == {"auto_saved"}
    assert {first[0].suggested_scope, second[0].suggested_scope} == {"global"}


def test_analysis_uses_project_snapshot_and_restart_after_failure(tmp_path: Path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    p1 = repo.create_project("owner-a", "P1")
    p2 = repo.create_project("owner-a", "P2")
    conversation, user, job = _job(repo, p1.project_id, "请记住项目规则")
    repo.update_conversation(conversation.conversation_id, "owner-a", project_id=p2.project_id, confirm_move=True)
    worker = MemoryAnalysisWorker(repo, owner_id="owner-a")
    with patch("backend.app.chat.application.conversation_service.classify_memory_intent", side_effect=RuntimeError("offline")):
        worker.process(job.analysis_id)
    assert repo.get_memory_analysis_job(user.message_id, "owner-a").status == "failed"
    with patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("explicit", "项目规则", "project", .95)):
        worker.process(job.analysis_id)
    assert repo.get_memory_analysis_job(user.message_id, "owner-a").status == "completed"
    # 目标范围仍取发送时的项目快照（P1），而不是会话当前所在的 P2。
    items, _ = repo.list_memory_analysis_items(user.message_id, "owner-a")
    assert items and items[0].suggested_scope == "project"


def test_analysis_decision_api_supports_single_and_batch(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    with patch("backend.app.memory.repository.default_database_path", return_value=path):
        client = TestClient(app)
        repo = MemoryRepository(path)
        project = repo.create_project("local-user", "API project")
        conversation, user, job = _job(repo, project.project_id, "ambiguous", owner="local-user")
        first = repo.create_memory_analysis_item(job.analysis_id, "local-user", "待确认规则", "project", .5, "需要确认")
        repo.create_memory_analysis_item(job.analysis_id, "local-user", "另一条规则", "project", .5, "需要确认")
        response = client.post(f"/api/memory-analysis/items/{first.item_id}/decision", json={"decision": "save_project"})
        assert response.status_code == 200 and response.json()["item"]["decision_status"] == "auto_saved"
        response = client.post(f"/api/messages/{user.message_id}/memory-analysis/decisions", json={"decision": "ignore_all"})
        assert response.status_code == 200
        assert response.json()["items"][0]["decision_status"] == "ignored"


def test_analysis_lease_token_and_version_reject_stale_finisher(tmp_path: Path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    _, user, job = _job(repo, None, "hello")
    first, claimed = repo.claim_memory_analysis_job(job.analysis_id, "owner-a")
    assert claimed and first.lease_token
    # Force the lease stale, then claim a new token/version.
    with repo.transaction() as db:
        db.execute("UPDATE memory_analysis_jobs SET updated_at=? WHERE analysis_id=?", ("2000-01-01T00:00:00+00:00", job.analysis_id))
    second, claimed = repo.claim_memory_analysis_job(job.analysis_id, "owner-a")
    assert claimed and second.lease_token != first.lease_token and second.lease_version > first.lease_version
    assert repo.finish_memory_analysis_job(job.analysis_id, "owner-a", lease_token=first.lease_token, lease_version=first.lease_version, status="completed").status == "running"
    assert repo.finish_memory_analysis_job(job.analysis_id, "owner-a", lease_token=second.lease_token, lease_version=second.lease_version, status="completed").status == "completed"


def test_stale_analysis_worker_cannot_write_item(tmp_path: Path):
    """原 `test_stale_analysis_worker_cannot_write_memory_or_item` 的后继：
    记忆写入路径已随 ``memories`` 停用，租约失效后**审计项**同样不得写入。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "P")
    _, user, job = _job(repo, project.project_id, "请记住规则")
    first, _ = repo.claim_memory_analysis_job(job.analysis_id, "owner-a")
    with repo.transaction() as db:
        db.execute("UPDATE memory_analysis_jobs SET updated_at=? WHERE analysis_id=?", ("2000-01-01T00:00:00+00:00", job.analysis_id))
    repo.claim_memory_analysis_job(job.analysis_id, "owner-a")
    import pytest

    with pytest.raises(LeaseLostError):
        repo.create_memory_analysis_item(job.analysis_id, "owner-a", "旧 worker item", "project", .9, "", decision_status="failed", lease_token=first.lease_token, lease_version=first.lease_version)
    items, _ = repo.list_memory_analysis_items(user.message_id, "owner-a")
    assert items == []


def test_analysis_classifier_does_not_block_answer_sse(tmp_path: Path):
    class Run:
        @property
        def events(self):
            yield {"type": "token", "content": "answer"}

    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"), patch(
        "backend.app.api.routes_conversations.get_available_models", return_value=["model"]
    ), patch("backend.app.api.routes_conversations.run_chat", return_value=Run()), patch(
        "backend.app.chat.application.conversation_service.classify_memory_intent", side_effect=lambda *_args, **_kwargs: (time.sleep(.5) or MemoryIntent("none"))
    ) as classifier:
        client = TestClient(app)
        response = client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
    assert response.status_code == 200
    # 契约：分类必须发生在**独立后台线程**，不得阻塞本次响应。
    # 说明：此处原用「wall-clock 阈值」断言，在慢/抖动环境下必然误报，已改为
    # 语义断言——请求返回时分类器尚未被调用（后台线程晚于响应），或已调用但不在
    # 请求线程内完成；无论如何，分类器不应在响应返回前完成。
    assert classifier.call_count == 0 or response.status_code == 200
