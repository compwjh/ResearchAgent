/* Task09 Fake-DOM/HTTP-style contract probes for the Session-first Research Tab. */
const assert = require('assert');
const {
  sessionTaskProjection,
  sessionDurationText,
  sessionProgressText,
  sessionApprovalText,
  sessionAgentToolText,
  reportPublicationText,
  reportQualityMetrics,
  reportProgressText,
  reportReasonCodes,
  reportDownloadAllowed,
  isQualityValidated,
} = require('../../frontend/research-tasks.js');

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
assert.equal(sessionTaskProjection({
  research_session_id: 'stale-session', status: 'queued',
  task: { research_task_id: 'terminal-task', status: 'partial' },
}).status, 'partial');

const publishedReport = {
  report_version: 4,
  status: 'completed',
  reason_codes: [],
  quality_validation: {
    schema_version: 'report-quality-v1', count_method: 'report-quality-v1', status: 'pass',
    cjk_count: 1604, paper_count: 5, comparison_count: 2, supported_finding_count: 3,
    revision_count: 1, failure_codes: [],
  },
  generation: { published: true, budget: { report_totals: { elapsed_seconds: 42.5 } } },
  limitations: { evidence_level: 'abstract' },
};
assert.equal(reportPublicationText(publishedReport), '正式发布');
assert.deepEqual(reportQualityMetrics(publishedReport), [
  { label: '正文 CJK', value: '1,604 / 1,500' },
  { label: '有效逐篇', value: '5 / 5' },
  { label: '有效比较', value: '2 / 1' },
  { label: '支持发现', value: '3 / 3' },
  { label: '定向改写', value: '1 / 2' },
  { label: '证据等级', value: '摘要证据' },
]);
assert.equal(reportProgressText(publishedReport, [{ stage: 'published', elapsed_seconds: 42.5 }]), '报告已发布 · 已用 42.5 秒');
assert.equal(reportReasonCodes({ reason_codes: ['CJK_COUNT_BELOW_MINIMUM', 'CJK_COUNT_BELOW_MINIMUM'] }).join(', '), 'CJK_COUNT_BELOW_MINIMUM');
assert.equal(reportPublicationText({ status: 'draft', quality_validation: { status: 'fail' }, generation: { published: false } }), '未发布草稿');
assert.equal(reportPublicationText({ status: 'completed' }), '旧版，未按本质量合同核验');
assert.equal(reportProgressText({ status: 'generating' }, [{ stage: 'targeted_revision', elapsed_seconds: 18 }]), '定向补写 · 已用 18 秒');
assert.equal(reportDownloadAllowed({ status: 'draft', generation: { published: false } }), false);
assert.equal(reportDownloadAllowed({ status: 'generating', published: false }), false);
assert.equal(reportDownloadAllowed({ ...publishedReport, status: 'generating' }), false);
assert.equal(reportDownloadAllowed({ ...publishedReport, quality_validation: { ...publishedReport.quality_validation, status: 'fail' } }), false);
assert.equal(reportDownloadAllowed(publishedReport), true);
assert.equal(reportDownloadAllowed({ status: 'completed' }), true, 'legacy published-version download behavior remains available');
assert.equal(reportDownloadAllowed({ status: 'completed', published: true }), true, 'published legacy versions remain downloadable');
assert.equal(isQualityValidated(publishedReport), true);
const malformedQualityReport = {
  ...publishedReport,
  quality_validation: { ...publishedReport.quality_validation, schema_version: 'report-quality-v0', count_method: 'legacy-counter' },
};
assert.equal(isQualityValidated(malformedQualityReport), false);
assert.equal(reportPublicationText(malformedQualityReport), '旧版，未按本质量合同核验');
assert.deepEqual(reportQualityMetrics(malformedQualityReport), []);
assert.equal(reportDownloadAllowed(malformedQualityReport), false);
const malformedUnpublishedMetadata = {
  ...malformedQualityReport,
  published: undefined,
  generation: { ...malformedQualityReport.generation, published: undefined },
};
assert.equal(reportDownloadAllowed(malformedUnpublishedMetadata), false, 'malformed quality cannot use the legacy download fallback');
const qualityWithoutPublication = {
  ...publishedReport,
  published: undefined,
  generation: { ...publishedReport.generation, published: undefined },
};
assert.equal(reportDownloadAllowed(qualityWithoutPublication), false, 'quality-v1 reports require an explicit published=true signal');
const missingQualityReport = { ...publishedReport, quality_validation: undefined };
assert.equal(reportPublicationText(missingQualityReport), '旧版，未按本质量合同核验');
assert.deepEqual(reportQualityMetrics(missingQualityReport), []);
assert.equal(reportDownloadAllowed(missingQualityReport), false, 'a present but missing quality field is not a pure legacy version');
console.log('Task09 frontend Session/Fake-DOM contract: PASS');
