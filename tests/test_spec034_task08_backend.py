"""Task08 report/artifact/notification backend contracts."""

import hashlib
import json
import uuid
from types import SimpleNamespace

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.orchestrator import Orchestrator, _validate_evaluator_scope
from backend.app.research.application.planner import Planner
from backend.app.research.application.processing_projector import ProcessingStepProjector
from backend.app.research.application.report_synthesis import (
    ReportDeliveryService,
    ReportSynthesisError,
    ReportSynthesizer,
    ResearchNotificationService,
    render_markdown_html,
    report_output_hash,
)
from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter, SearchOutcome
from backend.app.research.domain.models import ResearchArtifact, ResearchNotification
from backend.app.research.infrastructure.research_store import ResearchArtifactConflict, ResearchStore


def _id():
    return uuid.uuid4().hex


def test_synthesizer_rejects_unverified_candidate_and_non_allowlisted_citation():
    synth = ReportSynthesizer()
    with pytest.raises(ReportSynthesisError):
        synth.synthesize(report_version=1, candidates=[{"candidate_id": "c1"}], citation_whitelist=["catalog:c1"])
    with pytest.raises(ReportSynthesisError):
        synth.synthesize(report_version=1, candidates=[{"candidate_id": "c1", "verified": True}], citation_whitelist=["catalog:c2"])


@pytest.mark.parametrize("marker", ["false", 1, [], {"yes": True}])
def test_synthesizer_requires_literal_boolean_validation(marker):
    with pytest.raises(ReportSynthesisError):
        ReportSynthesizer().synthesize(
            report_version=1, candidates=[{"candidate_id": "c1", "verified": marker}],
            citation_whitelist=["catalog:c1"],
        )


def test_evaluator_output_is_bound_to_search_worker_candidates_and_refs():
    allowed_candidates = {"c1"}
    allowed_refs = {"catalog:c1"}
    assert _validate_evaluator_scope(
        {"kept": [{"candidate_id": "c1", "keep": True, "evidence_refs": ["catalog:c1"]}]},
        allowed_candidates, allowed_refs,
    )
    assert not _validate_evaluator_scope(
        {"kept": [{"candidate_id": "c2", "keep": True, "evidence_refs": ["catalog:c2"]}]},
        allowed_candidates, allowed_refs,
    )
    assert not _validate_evaluator_scope(
        {"source": "attacker", "source_refs": ["search:attacker"], "candidate_id": "c1", "keep": True, "evidence_refs": ["catalog:c1"]},
        allowed_candidates, allowed_refs, {"usenix"}, {"search:s1"},
    )
    assert not _validate_evaluator_scope(
        {"source": "usenix", "source_refs": ["search:attacker"], "candidate_id": "c1", "keep": True, "evidence_refs": ["catalog:c1"]},
        allowed_candidates, allowed_refs, {"usenix"}, {"search:s1"},
    )
    assert _validate_evaluator_scope(
        {"source": "usenix", "source_refs": ["search:s1"], "candidate_id": "c1", "keep": True, "evidence_refs": ["catalog:c1"]},
        allowed_candidates, allowed_refs, {"usenix"}, {"search:s1"},
    )


@pytest.mark.parametrize("unsafe", ["https://example.invalid/report", "/tmp/report.md", "prompt: hidden", "C:\\secrets\\report"])
def test_synthesizer_rejects_unsafe_title_and_heading_inputs(unsafe):
    with pytest.raises(ReportSynthesisError):
        ReportSynthesizer().synthesize(
            report_version=1, candidates=[{"candidate_id": "c1", "verified": True}],
            citation_whitelist=["catalog:c1"], title=unsafe,
        )
    with pytest.raises(ReportSynthesisError):
        ReportSynthesizer().synthesize(
            report_version=1, candidates=[{"candidate_id": "c1", "verified": True}],
            citation_whitelist=["catalog:c1"], sections=[{"heading": unsafe, "candidate_ids": ["c1"]}],
        )


def test_synthesizer_consumes_model_output_only_with_evaluator_allowlist():
    payload = {
        "schema_version": "report-synthesis-v1", "report_version": 1,
        "sections": [{"heading": "证据", "candidate_ids": ["c1"]}],
        "citation_manifest": [{"citation_ref": "catalog:c1", "candidate_id": "c1"}],
        "artifact_ids": [], "safe_summary": {"candidate_count": 1},
        "source_refs": ["catalog:c1"],
    }
    payload["output_hash"] = report_output_hash(payload)
    result = ReportSynthesizer().consume_validated_output(
        output=payload,
        validated_candidates=[{"candidate_id": "c1", "verified": True, "evidence_refs": ["catalog:c1"]}],
    )
    assert result.output.sections[0]["candidate_ids"] == ["c1"]
    bad = {**payload, "citation_manifest": [{"citation_ref": "catalog:c2", "candidate_id": "c1"}]}
    bad["output_hash"] = report_output_hash(bad)
    with pytest.raises(ReportSynthesisError):
        ReportSynthesizer().consume_validated_output(
            output=bad,
            validated_candidates=[{"candidate_id": "c1", "verified": True, "evidence_refs": ["catalog:c1"]}],
        )
    bad_source = {**payload, "source_refs": ["catalog:c2"]}
    bad_source["output_hash"] = report_output_hash(bad_source)
    with pytest.raises(ReportSynthesisError):
        ReportSynthesizer().consume_validated_output(
            output=bad_source,
            validated_candidates=[{"candidate_id": "c1", "verified": True, "evidence_refs": ["catalog:c1"]}],
        )


def test_consume_report_keeps_verified_candidates_omitted_by_model():
    payload = {
        "schema_version": "report-synthesis-v1", "report_version": 1,
        "sections": [{"heading": "主题综述", "candidate_ids": ["c1"], "summary": "目录级摘要对照"}],
        "citation_manifest": [{"citation_ref": "catalog:c1", "candidate_id": "c1"}],
        "artifact_ids": [], "safe_summary": {"candidate_count": 5},
        "source_refs": ["catalog:c1"],
    }
    payload["output_hash"] = report_output_hash(payload)
    candidates = [
        {"candidate_id": f"c{i}", "verified": True, "evidence_refs": [f"catalog:c{i}"],
         "title": f"Paper {i}", "abstract": f"Abstract {i}"}
        for i in range(1, 6)
    ]
    result = ReportSynthesizer().consume_validated_output(output=payload, validated_candidates=candidates)
    assert "目录证据补充" in result.markdown
    assert all(f"Paper {i}" in result.markdown for i in range(1, 6))
    assert len(result.output.citation_manifest) == 5


def test_synthesizer_output_is_hashed_and_html_escapes_xss():
    result = ReportSynthesizer().synthesize(
        report_version=1,
        candidates=[{"candidate_id": "c1", "verified": True}],
        citation_whitelist=["catalog:c1"],
        title="<script>alert(1)</script>",
    )
    assert result.output.report_version == 1
    assert len(result.output.output_hash) == 64
    assert "<script>" not in result.html and "&lt;script&gt;" in result.html
    assert "catalog:c1" in result.markdown


def test_synthesizer_renders_verified_catalog_metadata_and_rejects_unsafe_fields():
    candidate = {
        "candidate_id": "c1", "verified": True, "evidence_refs": ["catalog:c1"],
        "title": "Supply-chain defenses",
        "abstract": "A catalog abstract describing bounded defenses.",
        "keywords": ["supply chain", "defense"],
    }
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[candidate],
        citation_manifest=["catalog:c1"],
        sections=[{"heading": "方法与主题：防御", "candidate_ids": ["c1"]}],
    )
    assert "#### Supply-chain defenses" in result.markdown
    assert "- 摘要：A catalog abstract describing bounded defenses." in result.markdown
    assert "- 关键词：supply chain、defense" in result.markdown
    with pytest.raises(ReportSynthesisError):
        ReportSynthesizer().synthesize(
            report_version=1,
            validated_candidates=[{**candidate, "abstract": "https://untrusted.invalid/paper"}],
            citation_manifest=["catalog:c1"],
        )


def test_artifact_is_immutable_and_owner_scoped(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "goal", None, "m", "normal")
    store = ResearchStore(tmp_path / "research.sqlite3")
    from backend.app.research.domain.models import AgentRun, ResearchSession, ResearchTask, ResearchWorkItem
    task = ResearchTask(_id(), "owner-a", conversation.conversation_id, "goal", "zh", "balanced", False, 1, 60, "draft", 1, "now", "now")
    store.create_task(task)
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id)
    store.create_session(session, memory_repository=memory)
    item = ResearchWorkItem(_id(), task.research_task_id, 1, "synthesize_preliminary_report", "synthesizer", "[]", "{}", "queued", 0, "now", "now")
    store.create_work_items(task.research_task_id, [item])
    run = AgentRun(_id(), session.research_session_id, 1, "synthesizer", "research-report-synthesis", "1", "h", "m", "off", "[]", research_task_id=task.research_task_id, work_item_id=item.work_item_id, owner_id="owner-a")
    store.create_agent_run(run, owner_id="owner-a")
    content = "# report\n"
    artifact = ResearchArtifact(_id(), task.research_task_id, 1, "markdown", hashlib.sha256(content.encode()).hexdigest(), run.agent_run_id, content=content)
    saved = store.create_artifact(artifact)
    assert store.get_artifact(saved.artifact_id, "owner-a").artifact_id == saved.artifact_id
    assert store.get_artifact(saved.artifact_id, "owner-b") is None
    with pytest.raises(ResearchArtifactConflict):
        store.create_artifact(ResearchArtifact(_id(), task.research_task_id, 1, "markdown", artifact.content_hash, run.agent_run_id, content=content))


def test_delivery_reuses_final_message_and_notification_on_retry(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, activity = memory.create_conversation_messages("owner-a", "goal", None, "m", "normal")
    store = ResearchStore(tmp_path / "research.sqlite3")
    from backend.app.research.domain.models import AgentRun, ResearchSession, ResearchTask, ResearchWorkItem
    task = ResearchTask(_id(), "owner-a", conversation.conversation_id, "goal", "zh", "balanced", False, 1, 60, "draft", 1, "now", "now")
    store.create_task(task)
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id, activity_message_id=activity.message_id)
    store.create_session(session, memory_repository=memory)
    item = ResearchWorkItem(_id(), task.research_task_id, 1, "synthesize_preliminary_report", "synthesizer", "[]", "{}", "queued", 0, "now", "now")
    store.create_work_items(task.research_task_id, [item])
    run = AgentRun(_id(), session.research_session_id, 1, "synthesizer", "research-report-synthesis", "1", "h", "m", "off", "[]", research_task_id=task.research_task_id, work_item_id=item.work_item_id, owner_id="owner-a")
    store.create_agent_run(run, owner_id="owner-a")
    final_run = AgentRun(_id(), session.research_session_id, 2, "synthesizer", "research-report-synthesis", "1", "h", "m", "off", "[]", research_task_id=task.research_task_id, work_item_id=item.work_item_id, owner_id="owner-a")
    store.create_agent_run(final_run, owner_id="owner-a")
    result = ReportSynthesizer().synthesize(report_version=1, candidates=[{"candidate_id": "c1", "verified": True}], citation_whitelist=["catalog:c1"])
    delivery = ReportDeliveryService(store=store, memory_repository=memory)
    first = delivery.deliver(session=session, owner_id="owner-a", generated_by_agent_run_id=final_run.agent_run_id, result=result)
    second = delivery.deliver(session=session, owner_id="owner-a", generated_by_agent_run_id=final_run.agent_run_id, result=result)
    assert first["message_id"] == second["message_id"]
    assert first["notification_id"] == second["notification_id"]
    assert len(memory.list_messages(conversation.conversation_id, "owner-a")[0]) == 3
    assert len(store.list_notifications("owner-a")) == 1
    assert all(item.generated_by_agent_run_id == final_run.agent_run_id for item in store.list_artifacts_for_task(task.research_task_id, "owner-a"))


def test_delivery_rechecks_hash_after_concurrent_insert(tmp_path, monkeypatch):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, activity = memory.create_conversation_messages("owner-a", "goal", None, "m", "normal")
    store = ResearchStore(tmp_path / "research.sqlite3")
    from backend.app.research.domain.models import AgentRun, ResearchSession, ResearchTask, ResearchWorkItem
    task = ResearchTask(_id(), "owner-a", conversation.conversation_id, "goal", "zh", "balanced", False, 1, 60, "draft", 1, "now", "now")
    store.create_task(task)
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id, activity_message_id=activity.message_id)
    store.create_session(session, memory_repository=memory)
    item = ResearchWorkItem(_id(), task.research_task_id, 1, "synthesize_preliminary_report", "synthesizer", "[]", "{}", "queued", 0, "now", "now")
    store.create_work_items(task.research_task_id, [item])
    run = AgentRun(_id(), session.research_session_id, 1, "synthesizer", "research-report-synthesis", "1", "h", "m", "off", "[]", research_task_id=task.research_task_id, work_item_id=item.work_item_id, owner_id="owner-a")
    store.create_agent_run(run, owner_id="owner-a")
    result = ReportSynthesizer().synthesize(report_version=1, candidates=[{"candidate_id": "c1", "verified": True}], citation_whitelist=["catalog:c1"])
    wrong_content = "# a different report\n"
    wrong = ResearchArtifact(_id(), task.research_task_id, 1, "markdown", hashlib.sha256(wrong_content.encode()).hexdigest(), run.agent_run_id, content=wrong_content)
    calls = {"count": 0}
    original_list = store.list_artifacts_for_task

    def raced_list(*args, **kwargs):
        calls["count"] += 1
        return [] if calls["count"] == 1 else [wrong]

    monkeypatch.setattr(store, "list_artifacts_for_task", raced_list)
    monkeypatch.setattr(store, "create_artifact", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("race")))
    with pytest.raises(ReportSynthesisError, match="artifact immutable conflict") as exc:
        ReportDeliveryService(store=store, memory_repository=memory).deliver(
            session=session, owner_id="owner-a", generated_by_agent_run_id=run.agent_run_id, result=result,
        )
    assert exc.value.code == "ARTIFACT_IMMUTABLE_CONFLICT"


def test_notification_dedup_read_cas_and_cursor(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    service = ResearchNotificationService(store=store)
    # A task/session target is required by the ResearchStore binding checks.
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "goal", None, "m", "normal")
    from backend.app.research.domain.models import ResearchSession, ResearchTask
    task = ResearchTask(_id(), "owner-a", conversation.conversation_id, "goal", "zh", "balanced", False, 1, 60, "draft", 1, "now", "now")
    store.create_task(task)
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id)
    store.create_session(session, memory_repository=memory)
    first = service.emit(owner_id="owner-a", notification_kind="completed", subject_version=1, payload={"task": task.research_task_id}, idempotency_key="done:1", research_session_id=session.research_session_id, research_task_id=task.research_task_id)
    replay = service.emit(owner_id="owner-a", notification_kind="completed", subject_version=1, payload={"task": task.research_task_id}, idempotency_key="done:1", research_session_id=session.research_session_id, research_task_id=task.research_task_id)
    assert first.notification_id == replay.notification_id and first.event_seq == 1
    assert store.list_notifications("owner-a", after_seq=0)[0].event_seq == 1
    assert store.mark_notification_read(first.notification_id, "owner-b") is None
    assert store.mark_notification_read(first.notification_id, "owner-a").status == "read"
    assert store.mark_notification_read(first.notification_id, "owner-a").status == "read"


def test_renderer_does_not_interpret_raw_html_or_javascript():
    rendered = render_markdown_html("# hi\n\n<img src=x onerror=alert(1)>\n\n[jump](javascript:alert(1))")
    assert "<img" not in rendered and "javascript:" not in rendered


def test_notification_sse_polls_cursor_and_replays_new_items(monkeypatch):
    from backend.app.api import routes_research

    item = SimpleNamespace(
        notification_id="n1", research_session_id="s1", research_task_id="t1",
        notification_kind="partial", status="unread", subject_version=1,
        event_seq=1, payload_json='{"error_code":"NO_VALIDATED_EVIDENCE"}',
        created_at="now", read_at=None,
    )
    batches = [[], [item]]

    class Store:
        def list_notifications(self, _owner, *, after_seq, limit):
            assert after_seq in (0, 1)
            return batches.pop(0) if batches else []

    monkeypatch.setattr(routes_research, "_store", lambda: Store())
    stream = routes_research._notification_event_stream(0, max_polls=2, poll_seconds=0)
    assert next(stream) == ": heartbeat\n\n"
    assert "id: 1" in next(stream)


def test_historical_conversation_message_includes_safe_report_projection(tmp_path, monkeypatch):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, activity = memory.create_conversation_messages("owner-a", "goal", None, "m", "normal")
    store = ResearchStore(tmp_path / "research.sqlite3")
    from backend.app.research.domain.models import AgentRun, ResearchSession, ResearchTask, ResearchWorkItem
    task = ResearchTask(_id(), "owner-a", conversation.conversation_id, "goal", "zh", "balanced", False, 1, 60, "draft", 1, "now", "now")
    store.create_task(task)
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id, activity_message_id=activity.message_id)
    store.create_session(session, memory_repository=memory)
    item = ResearchWorkItem(_id(), task.research_task_id, 1, "synthesize_preliminary_report", "synthesizer", "[]", "{}", "queued", 0, "now", "now")
    store.create_work_items(task.research_task_id, [item])
    run = AgentRun(_id(), session.research_session_id, 1, "synthesizer", "research-report-synthesis", "1", "h", "m", "off", "[]", research_task_id=task.research_task_id, work_item_id=item.work_item_id, owner_id="owner-a")
    store.create_agent_run(run, owner_id="owner-a")
    result = ReportSynthesizer().synthesize(report_version=1, candidates=[{"candidate_id": "c1", "verified": True}], citation_whitelist=["catalog:c1"])
    ReportDeliveryService(store=store, memory_repository=memory).deliver(
        session=session, owner_id="owner-a", generated_by_agent_run_id=run.agent_run_id, result=result,
    )
    from backend.app.api import routes_conversations
    monkeypatch.setattr(routes_conversations, "get_provider", lambda name: store if name == "research_store" else memory)
    final = memory.get_activity_message(conversation.conversation_id, "owner-a", f"research-report:{task.research_task_id}:1")
    payload = routes_conversations._message_payload(final, memory, "owner-a")
    assert payload["report"]["report_version"] == 1
    assert payload["report"]["download_url"].endswith("/download")
    assert "storage_ref" not in json.dumps(payload) and "prompt" not in json.dumps(payload).casefold()


def test_html_artifact_supports_inline_read_but_other_types_stay_attachment(monkeypatch):
    from backend.app.api import routes_research
    artifact = SimpleNamespace(
        artifact_id="a1", research_task_id="t1", report_version=1, artifact_type="html",
        content_hash="h", generated_by_agent_run_id="r1", content="<!doctype html><p>safe</p>", storage_ref=None,
    )
    session = SimpleNamespace(research_task_id="t1")
    class Store:
        def get_session(self, _sid, _owner): return session
        def get_artifact(self, _aid, _owner): return artifact
    monkeypatch.setattr(routes_research, "_store", lambda: Store())
    inline = routes_research.download_research_artifact("s1", "a1", mode="inline")
    assert inline.headers["content-disposition"].startswith("inline;")
    assert inline.headers["content-type"].startswith("text/html")
    attachment = routes_research.download_research_artifact("s1", "a1", mode="attachment")
    assert attachment.headers["content-disposition"].startswith("attachment;")
    artifact.artifact_type = "markdown"
    rejected = routes_research.download_research_artifact("s1", "a1", mode="inline")
    assert rejected.status_code == 400


def test_orchestrator_completion_delivers_artifacts_message_and_notification(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages("owner-a", "联邦学习和隐私", None, "m", "normal")
    store = ResearchStore(tmp_path / "research.sqlite3")
    from backend.app.research.domain.models import ResearchSession, ResearchTask
    task = ResearchTask(_id(), "owner-a", conversation.conversation_id, "联邦学习和隐私", "zh", "balanced", False, 2, 60, "draft", 1, "now", "now")
    store.create_task(task)
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id, activity_message_id=assistant.message_id)
    store.create_session(session, memory_repository=memory)

    class Probe:
        def arbitrate(self, _task_id, requested):
            return max(1, requested), None

        def release(self, _task_id):
            return None

    def search(_request):
        return SearchOutcome(("paper-1", "paper-2"), 2, False, None)

    projector = ProcessingStepProjector(store, memory)
    orchestrator = Orchestrator(
        store=store, search_adapter=CatalogSearchAdapter(searcher=search), planner=Planner(),
        probe=Probe(), processing_projector=projector, memory_repository=memory,
    )
    result = orchestrator.run(task.research_task_id, "owner-a")
    assert result.status == "completed"
    artifacts = store.list_artifacts_for_task(task.research_task_id, "owner-a", report_version=1)
    assert {item.artifact_type for item in artifacts} == {"markdown", "html", "citation_manifest"}
    final = memory.get_activity_message(conversation.conversation_id, "owner-a", f"research-report:{task.research_task_id}:1")
    assert final is not None and final.status == "completed"
    notifications = store.list_notifications("owner-a")
    assert len(notifications) == 1 and notifications[0].notification_kind == "completed"
