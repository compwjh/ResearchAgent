"""Static contracts for the Spec034 Task09 Session-first Research workspace."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")


def test_session_is_the_only_tab_create_and_list_entrypoint():
    assert "requestJson('/api/research-sessions?limit=100')" in RESEARCH
    assert "requestJson('/api/research-sessions'" in RESEARCH
    assert "method: 'POST'" in RESEARCH
    assert "requestJson('/api/research-tasks'" not in RESEARCH
    assert "research-conversation-action" not in RESEARCH


def test_chat_and_tab_use_shared_session_projection():
    assert '/assets/research-session-ui.js?v=1' in INDEX
    assert 'ResearchSessionUI' in RESEARCH
    assert 'ResearchSessionUI' in APP
    assert 'projectSession' in RESEARCH
    assert 'projectSession' in APP


def test_session_card_has_required_observability_and_navigation():
    for marker in (
        "research_session_id",
        "current_phase",
        "sessionProgressText",
        "sessionApprovalText",
        "sessionDurationText",
        "sessionAgentToolText",
        "research-open-session",
        "openConversationFromResearch",
        "hydrateSession",
    ):
        assert marker in RESEARCH


def test_form_payload_is_intake_summary_and_inherits_project():
    assert "intake:" in RESEARCH
    assert "topic: goal" in RESEARCH
    assert "objective: goal" in RESEARCH
    assert "currentProjectId()" in RESEARCH
    assert "project_id: currentProjectId()" in RESEARCH
    assert "深度研究：${goal}" in RESEARCH
    assert "idempotency_key: state.createIdempotencyKey" in RESEARCH
    assert "trigger_message_id: state.triggerMessageId" in RESEARCH


def test_old_button_removed_and_new_resources_versioned():
    assert "research-conversation-action" not in INDEX
    # spec-036 已递增资源版本号，冻结断言同步为当前实际值（v3 / v51 / v53）。
    assert '/assets/research-tasks.js?v=3' in INDEX
    assert '/assets/styles.css?v=53' in INDEX
    assert '/assets/app.js?v=53' in INDEX
    assert '#research-view .research-open-session' in STYLES
    assert '#research-view .research-task-card-details' in STYLES


def test_dynamic_session_values_use_textcontent_and_no_innerhtml():
    assert "title.textContent = text(task.goal_excerpt" in RESEARCH
    assert "details.textContent = [" in RESEARCH
    assert ".innerHTML" not in RESEARCH


def test_real_session_detail_projection_uses_conversation_title_and_nested_plan_summary():
    SESSION_UI = (ROOT / "frontend/research-session-ui.js").read_text(encoding="utf-8")
    assert "const conversationTitle = scalar(conversation.title);" in SESSION_UI
    assert "goal_excerpt: conversationTitle || value.goal_excerpt || title" in SESSION_UI
    assert "plan.work_items || plan.work_items_json" in SESSION_UI
    assert "plan.capabilities || plan.capabilities_json" in SESSION_UI
    assert "uniqueNamedValues" in SESSION_UI
    assert "value.agent_tool_summary || value.execution_summary || task.agent_tool_summary" in SESSION_UI


def test_approval_materializes_task_and_reuses_existing_stream_report_pipeline():
    assert "mergeSessionCommandResult" in RESEARCH
    assert "await selectTask(taskId, sessionId)" in RESEARCH
    assert "await loadReport(taskId); connectStream();" in RESEARCH
    assert "research-session-command-success" in RESEARCH
    assert "research-session-command-success" in APP
