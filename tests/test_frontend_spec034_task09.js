/* Task09 Fake-DOM/HTTP-style contract probes for the Session-first Research Tab. */
const assert = require('assert');
const {
  sessionTaskProjection,
  sessionDurationText,
  sessionProgressText,
  sessionApprovalText,
  sessionAgentToolText,
} = require('../frontend/research-tasks.js');

const session = sessionTaskProjection({
  research_session_id: 'session-1', conversation_id: 'conversation-1', project_id: 'project-1',
  title: '深度研究：软件供应链攻击', status: 'running', current_phase: 'search',
  progress_percent: 42, approval_status: 'approved', duration_ms: 12500,
  agent_tool_summary: { agents: 2, tools: 4 },
  task: { research_task_id: 'task-1', current_plan_version: 2 },
});
assert.equal(session.research_session_id, 'session-1');
assert.equal(session.research_task_id, 'task-1');
assert.equal(session.conversation_id, 'conversation-1');
assert.equal(session.status, 'running');
assert.equal(sessionProgressText(session), '进度：42%');
assert.equal(sessionApprovalText(session), '审批：approved');
assert.equal(sessionDurationText(session), '13 秒');
assert.equal(sessionAgentToolText(session), 'Agent 2 · Tool 4');
assert.equal(sessionApprovalText({ approval_status: { kind: 'plan', status: 'pending' } }), '审批：待处理');

// This mirrors the real Session detail response: hydrate starts from a
// generic list projection, then attaches conversation and the nested plan
// whose JSON fields are still strings.
const hydratedRealShape = sessionTaskProjection({
  research_session_id: 'session-real', title: '深度研究', status: 'running',
  conversation: { conversation_id: 'conversation-real', title: '深度研究：真实会话标题' },
  plan: {
    work_items_json: JSON.stringify([
      { id: 'w1', role: 'planner' }, { id: 'w2', role: 'search-worker' }, { id: 'w3', role: 'search-worker' },
    ]),
    capabilities_json: JSON.stringify([
      { skill: { name: 'catalog' }, tools: [{ name: 'search' }, { name: 'detail' }] },
      { skill: { name: 'catalog' }, tools: [{ name: 'search' }] },
    ]),
  },
});
assert.equal(hydratedRealShape.title, '深度研究：真实会话标题');
assert.equal(hydratedRealShape.goal_excerpt, '深度研究：真实会话标题');
assert.equal(sessionAgentToolText(hydratedRealShape), 'Agent 2 · Tool 2');

const explicitSummary = sessionTaskProjection({
  research_session_id: 'session-explicit', agent_tool_summary: '后端摘要优先',
  plan: { work_items_json: '[{"role":"planner"}]', capabilities_json: '[{"tools":[{"name":"search"}]}]' },
});
assert.equal(sessionAgentToolText(explicitSummary), '后端摘要优先');

const intakeOnly = sessionTaskProjection({ research_session_id: 'session-2', topic: '<img src=x onerror=alert(1)>', status: 'intake_pending' });
assert.equal(intakeOnly.research_task_id, null);
assert.equal(intakeOnly.goal_excerpt, '<img src=x onerror=alert(1)>');
assert.equal(intakeOnly.status, 'intake_pending');
assert.equal(sessionProgressText({ progress: 0.5 }), '进度：50%');
assert.equal(sessionApprovalText({}), '审批：—');
assert.equal(sessionAgentToolText({}), 'Agent/Tool：—');
assert.equal(sessionTaskProjection({ title: 'invalid' }), null);
console.log('Task09 frontend Session/Fake-DOM contract: PASS');
