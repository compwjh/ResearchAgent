'use strict';

const assert = require('node:assert/strict');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  };
}

function fakeElement() {
  return {
    textContent: '', hidden: false, value: '', dataset: {}, childNodes: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    replaceChildren() { this.childNodes = []; },
    appendChild(child) { this.childNodes.push(child); },
    append(...children) { this.childNodes.push(...children); },
    addEventListener() {}, setAttribute() {}, removeAttribute() {},
  };
}

const fakeDocument = {
  getElementById: (id) => id === 'research-summary-list' ? fakeElement() : null,
  createElement: fakeElement,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
};

globalThis.document = fakeDocument;
globalThis.location = { pathname: '', search: '', hash: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.dispatchEvent = () => true;
globalThis.FormData = class {
  append() {}
};
const localStorageValues = new Map();
globalThis.localStorage = {
  getItem(key) { return localStorageValues.has(key) ? localStorageValues.get(key) : null; },
  setItem(key, value) { localStorageValues.set(key, String(value)); },
  removeItem(key) { localStorageValues.delete(key); },
};

let fetchImpl = async () => response({});
globalThis.fetch = (...args) => fetchImpl(...args);

const api = require('../../frontend/research-tasks.js');
const { state } = api;

function resetState() {
  localStorageValues.clear();
  state.document = fakeDocument;
  state.selectedTaskId = null;
  state.selectedSessionId = null;
  state.selectedTask = null;
  state.conversationId = null;
  state.conversation = null;
  state.tasks = [];
  state.sessions = [];
  state.taskListRequestGeneration = 0;
  state.booted = false;
  state.notifications = new Map();
  state.selectTaskInFlight = null;
  state.reportVersionSelections = new Map();
  state.pendingReportVersion = null;
  state.reportLoadRequest = 0;
  state.taskGeneration = 0;
  state.reportVersionRequest = 0;
  state.report = null;
  state.reportViews = new Map();
  state.reportVersions = [];
  state.reportFormat = 'markdown';
  if (state.reportPollTimer) clearTimeout(state.reportPollTimer);
  state.reportPollTimer = null;
  state.reportPoll = null;
  state.matrix = null;
  state.paperDisplays = new Map();
  state.paperDisplaysPending = new Set();
  state.acquisition.reportActionMessage = '';
  state.acquisition.reportActionTaskIds = [];
  state.acquisition.reportActionStatus = '';
  state.acquisition.reportActionVersion = null;
  state.acquisition.reportActionInFlight = false;
  state.acquisition.reportActionRequestKey = null;
  state.acquisition.reportActionRetryMode = null;
  state.acquisition.issueActions = new Set();
  fetchImpl = async () => response({});
}

function nextTurn() {
  return new Promise((resolve) => setImmediate(resolve));
}

async function testLateGenerationResponseCannotWriteTheNextTask() {
  resetState();
  state.selectedTaskId = 'task-a';
  state.selectedTask = { current_plan_version: 1 };
  state.taskGeneration = 1;
  state.acquisition.reportActionTaskIds = ['task-a'];
  state.acquisition.reportActionStatus = 'available';
  const canonical = deferred();
  fetchImpl = async (url) => {
    if (url.endsWith('/reports')) return response({ report_version: 2 });
    if (url.includes('/reports/2?format=json')) return canonical.promise;
    if (url.endsWith('/research-tasks/task-b')) return response({ research_task_id: 'task-b', status: 'completed', current_plan_version: 1 });
    if (url.includes('/research-tasks/task-b/evidence-matrix')) return response({ error: { code: 'MATRIX_NOT_READY', message: 'not ready' } }, 404);
    if (url.endsWith('/research-tasks/task-b/report')) return response({ report_version: 1, status: 'completed', artifacts: [], evidence: [] });
    if (url.includes('/research-tasks/task-b/reports/1?format=json')) return response({ report_version: 1, status: 'completed', citation_manifest: [] });
    if (url.includes('/research-tasks/task-b/acquisitions')) return response({ status: 'completed', links: [], items: [], events: [], issues: [] });
    throw new Error(`unexpected request: ${url}`);
  };

  const pending = api.generateReportVersion('task-a');
  await nextTurn();
  const switching = api.selectTask('task-b');
  await nextTurn();
  canonical.resolve(response({ report_version: 2, status: 'completed', citation_manifest: [] }));

  assert.equal(await pending, null);
  await switching;
  assert.equal(state.selectedTaskId, 'task-b');
  assert.notEqual(state.report?.report_version, 2);
  assert.equal(state.reportViews.has('2:json'), false);
  assert.equal(state.reportVersions.includes(2), false);
  assert.equal(state.acquisition.reportActionMessage, '');
}

async function testLateUploadResponseCannotCreateTheNextTaskButton() {
  resetState();
  state.selectedTaskId = 'task-a';
  state.taskGeneration = 3;
  const upload = deferred();
  fetchImpl = async (url) => {
    if (url.includes('/papers/issues/issue-a/upload')) return upload.promise;
    throw new Error(`unexpected request: ${url}`);
  };

  const pending = api.uploadIssue(
    { issue_id: 'issue-a' },
    { name: 'paper.pdf' },
    { checked: true },
    fakeElement(),
  );
  await nextTurn();
  state.selectedTaskId = 'task-b';
  state.taskGeneration = 4;
  state.acquisition.reportActionMessage = '';
  state.acquisition.reportActionTaskIds = [];
  upload.resolve(response({ report_action: 'generate_new_version', research_task_ids: ['task-a'] }));

  assert.equal(await pending, null);
  assert.equal(state.acquisition.reportActionMessage, '');
  assert.deepEqual(state.acquisition.reportActionTaskIds, []);
}

async function testVersionFailureRollsBackAndLateVersionCannotWin() {
  resetState();
  state.selectedTaskId = 'task-a';
  state.taskGeneration = 5;
  state.report = { report_version: 1, status: 'completed', markdown: '旧正文', citation_manifest: [] };
  state.reportViews = new Map([['1:markdown', '旧正文']]);
  state.reportVersions = [1, 2, 3];
  const failedVersion = deferred();
  const versionTwo = deferred();
  const versionThree = deferred();
  const versionThreeMarkdown = deferred();
  let versionTwoCalls = 0;
  fetchImpl = async (url) => {
    if (url.includes('/reports/2?format=json')) {
      versionTwoCalls += 1;
      return (versionTwoCalls === 1 ? failedVersion : versionTwo).promise;
    }
    if (url.includes('/reports/3?format=json')) return versionThree.promise;
    if (url.includes('/reports/3?format=markdown')) return versionThreeMarkdown.promise;
    throw new Error(`unexpected request: ${url}`);
  };

  const failed = api.selectReportVersion(2);
  await nextTurn();
  failedVersion.resolve(response({ error: { code: 'REPORT_NOT_READY', message: 'not ready' } }, 503));
  assert.equal(await failed, null);
  assert.equal(state.report.report_version, 1);
  assert.equal(state.report.markdown, '旧正文');
  assert.equal(state.reportViews.get('1:markdown'), '旧正文');

  const stale = api.selectReportVersion(2);
  await nextTurn();
  const latest = api.selectReportVersion(3);
  await nextTurn();
  versionTwo.resolve(response({ report_version: 2, status: 'completed', citation_manifest: [] }));
  versionThree.resolve(response({ report_version: 3, status: 'completed', citation_manifest: [] }));
  await nextTurn();
  versionThreeMarkdown.resolve(response('新正文'));
  await Promise.all([stale, latest]);

  assert.equal(state.report.report_version, 3);
  assert.equal(state.report.markdown, '新正文');
  assert.equal(state.reportViews.get('3:markdown'), '新正文');
  assert.equal(state.reportViews.has('2:json'), false);
}

function qualityReport(version, status, published, qualityStatus = 'pending') {
  return {
    report_version: version,
    plan_version: 1,
    status,
    reason_codes: qualityStatus === 'fail' ? ['CJK_COUNT_BELOW_MINIMUM'] : [],
    quality_validation: {
      schema_version: 'report-quality-v1', count_method: 'report-quality-v1',
      status: qualityStatus, cjk_count: 900, paper_count: 5, comparison_count: 1,
      supported_finding_count: 3, invalid_evidence_count: 0, revision_count: 0,
      failure_codes: qualityStatus === 'fail' ? ['CJK_COUNT_BELOW_MINIMUM'] : [],
    },
    generation: { report_version: version, published, path: 'agent_runner', budget: { report_totals: { elapsed_seconds: 12 } } },
  };
}

async function testReportSubmissionUsesIdempotencyKeyAndTreats202AsPending() {
  resetState();
  state.selectedTaskId = 'task-report';
  state.selectedTask = { current_plan_version: 1, research_session_id: 'session-report' };
  state.taskGeneration = 8;
  state.acquisition.reportActionTaskIds = ['task-report'];
  state.acquisition.reportActionStatus = 'available';
  const pendingRead = deferred();
  const submittedKeys = [];
  const readUrls = [];
  let postCount = 0;
  let reportThreeReads = 0;
  let markdownCalls = 0;
  const originalSetTimeout = globalThis.setTimeout;
  let scheduledPoll = null;
  globalThis.setTimeout = (callback) => { scheduledPoll = callback; return 9001; };
  fetchImpl = async (url, options = {}) => {
    if (url.endsWith('/reports') && options.method === 'POST') {
      postCount += 1;
      submittedKeys.push(options.headers?.['Idempotency-Key']);
      if (postCount === 1) throw new Error('connection reset after submit');
      if (postCount === 2) return response({
        ...qualityReport(3, 'completed', true, 'pass'),
        published: true,
        report_url: '/api/research-tasks/task-report/reports/3?format=json',
      }, 202);
      return response({
        report_version: 4, status: 'generating', quality_status: 'pending', published: false,
        reason_codes: [], report_url: '/api/research-tasks/task-report/reports/4?format=json',
      }, 202);
    }
    if (url.includes('/reports/3?format=json')) {
      readUrls.push(url);
      reportThreeReads += 1;
      return reportThreeReads === 1 ? pendingRead.promise : response(qualityReport(3, 'completed', true, 'pass'));
    }
    if (url.includes('/reports/3?format=markdown')) { markdownCalls += 1; return response('正式发布正文'); }
    if (url.includes('/reports/4?format=json')) { readUrls.push(url); return response(qualityReport(4, 'draft', false, 'fail')); }
    if (url.includes('/reports/4?format=markdown')) { markdownCalls += 1; return response('可读草稿正文'); }
    if (url.includes('/sessions/session-report/artifacts')) return response({ artifacts: [] });
    throw new Error(`unexpected request: ${url}`);
  };

  assert.equal(await api.generateReportVersion('task-report'), null);
  assert.equal(state.acquisition.reportActionRetryMode, 'post');
  const firstKey = state.acquisition.reportActionRequestKey;
  assert.match(firstKey, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);

  const acceptedPromise = api.generateReportVersion('task-report');
  await nextTurn();
  assert.equal(state.acquisition.reportActionStatus, 'generating');
  assert.match(state.acquisition.reportActionMessage, /已受理|正在生成/);
  assert.equal(state.report.status, 'generating', 'POST 202 body cannot publish its claimed completed status');
  assert.equal(state.report.published, false, 'POST 202 body cannot set published=true');
  assert.equal(state.report.generation.published, false, 'POST 202 body cannot publish through generation metadata');
  assert.equal(state.report.quality_validation, undefined, 'quality remains unknown until the canonical GET');
  assert.equal(api.reportDownloadAllowed(state.report), false);
  pendingRead.resolve(response(qualityReport(3, 'generating', false)));
  const accepted = await acceptedPromise;
  assert.equal(accepted.report_version, 3);
  assert.equal(state.report.status, 'generating');
  assert.notEqual(state.acquisition.reportActionStatus, 'completed');
  assert.deepEqual(submittedKeys.slice(0, 2), [firstKey, firstKey]);
  assert.ok(readUrls.includes('/api/research-tasks/task-report/reports/3?format=json'));
  assert.equal(markdownCalls, 0, '202 acceptance must not require a report body');
  assert.equal(typeof scheduledPoll, 'function', 'accepted generating report must keep polling its report_url');
  const pollResult = scheduledPoll();
  await nextTurn();
  assert.equal((await pollResult).status, 'completed');
  assert.equal(state.acquisition.reportActionStatus, 'completed');
  assert.equal(state.report.generation.published, true);
  assert.equal(markdownCalls, 1);
  globalThis.setTimeout = originalSetTimeout;
  state.reportPollTimer = null;

  state.report = qualityReport(3, 'draft', false, 'fail');
  state.acquisition.reportActionStatus = 'available';
  state.acquisition.reportActionRequestKey = null;
  const retried = await api.generateReportVersion('task-report');
  assert.equal(retried.report_version, 4);
  assert.notEqual(submittedKeys[2], firstKey, 'a new user retry must get a fresh UUID');
  assert.equal(state.report.status, 'draft');
  assert.equal(state.report.generation.published, false);
  if (state.reportPollTimer) clearTimeout(state.reportPollTimer);
  state.reportPollTimer = null;
}

async function testForged202CannotPublishWhenCanonicalReadFails() {
  resetState();
  state.selectedTaskId = 'task-accepted-only';
  state.selectedTask = { current_plan_version: 1, research_session_id: 'session-accepted-only' };
  state.taskGeneration = 9;
  state.acquisition.reportActionTaskIds = ['task-accepted-only'];
  state.acquisition.reportActionStatus = 'available';
  let scheduledPoll = null;
  let markdownCalls = 0;
  const originalSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (callback) => { scheduledPoll = callback; return 9003; };
  fetchImpl = async (url, options = {}) => {
    if (url.endsWith('/reports') && options.method === 'POST') {
      return response({
        ...qualityReport(6, 'completed', true, 'pass'),
        published: true,
        report_url: '/api/research-tasks/task-accepted-only/reports/6?format=json',
      }, 202);
    }
    if (url.includes('/reports/6?format=json')) return response({ error: 'temporary read failure' }, 500);
    if (url.includes('/reports/6?format=markdown')) { markdownCalls += 1; return response('不可见正文'); }
    if (url.includes('/sessions/session-accepted-only/artifacts')) return response({ artifacts: [] });
    throw new Error(`unexpected request: ${url}`);
  };

  await api.generateReportVersion('task-accepted-only');
  assert.equal(state.report.status, 'generating');
  assert.equal(state.report.published, false);
  assert.equal(state.report.generation.published, false);
  assert.equal(state.report.quality_validation, undefined);
  assert.equal(api.reportPublicationText(state.report), '生成中 · 尚未发布');
  assert.deepEqual(api.reportQualityMetrics(state.report), []);
  assert.equal(api.reportDownloadAllowed(state.report), false);
  assert.equal(state.acquisition.reportActionStatus, 'retryable');
  assert.equal(markdownCalls, 0);
  assert.equal(typeof scheduledPoll, 'function', 'failed canonical read should continue tracking the accepted version');
  globalThis.setTimeout = originalSetTimeout;
  state.reportPollTimer = null;
}

async function testAsyncPollCannotPublishMalformedQualitySchema() {
  resetState();
  state.selectedTaskId = 'task-malformed';
  state.selectedTask = { current_plan_version: 1, research_session_id: 'session-malformed' };
  state.taskGeneration = 11;
  state.acquisition.reportActionTaskIds = ['task-malformed'];
  state.acquisition.reportActionStatus = 'available';
  let reportReads = 0;
  let scheduledPoll = null;
  const originalSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (callback) => { scheduledPoll = callback; return 9002; };
  fetchImpl = async (url, options = {}) => {
    if (url.endsWith('/reports') && options.method === 'POST') return response({
      report_version: 5, status: 'generating', quality_status: 'pending', published: false,
      reason_codes: [], report_url: '/api/research-tasks/task-malformed/reports/5?format=json',
    }, 202);
    if (url.includes('/reports/5?format=json')) {
      reportReads += 1;
      if (reportReads === 1) return response(qualityReport(5, 'generating', false));
      const malformed = qualityReport(5, 'completed', true, 'pass');
      malformed.quality_validation.schema_version = 'report-quality-v0';
      malformed.quality_validation.count_method = 'legacy-counter';
      return response(malformed);
    }
    if (url.includes('/reports/5?format=markdown')) return response('未核验版本正文');
    if (url.includes('/sessions/session-malformed/artifacts')) return response({ artifacts: [] });
    throw new Error(`unexpected request: ${url}`);
  };

  await api.generateReportVersion('task-malformed');
  assert.equal(state.acquisition.reportActionStatus, 'generating');
  assert.equal(typeof scheduledPoll, 'function');
  const pollPromise = scheduledPoll();
  await nextTurn();
  await pollPromise;
  assert.equal(state.report.status, 'completed');
  assert.equal(state.report.generation.published, true);
  assert.equal(api.reportPublicationText(state.report), '旧版，未按本质量合同核验');
  assert.deepEqual(api.reportQualityMetrics(state.report), []);
  assert.equal(state.acquisition.reportActionStatus, 'available');
  assert.notEqual(state.acquisition.reportActionStatus, 'completed');
  globalThis.setTimeout = originalSetTimeout;
  state.reportPollTimer = null;
}

async function testSelectingLegacyVersionDoesNotInheritCurrentQualityFields() {
  resetState();
  state.selectedTaskId = 'task-versions';
  state.taskGeneration = 12;
  state.report = { ...qualityReport(2, 'completed', true, 'pass'), markdown: 'v2正文', artifacts: [] };
  state.reportVersions = [2, 1];
  state.reportViews = new Map([['2:json', state.report], ['2:markdown', 'v2正文']]);
  fetchImpl = async (url) => {
    if (url.includes('/reports/1?format=json')) return response({ report_version: 1, status: 'completed', citation_manifest: [] });
    if (url.includes('/reports/1?format=markdown')) return response('旧版正文');
    throw new Error(`unexpected request: ${url}`);
  };

  const legacy = await api.selectReportVersion(1);
  assert.equal(legacy.report_version, 1);
  assert.equal(state.report.report_version, 1);
  assert.equal(state.report.status, 'completed');
  assert.equal(state.report.quality_validation, undefined);
  assert.equal(state.report.generation, undefined);
  assert.equal(state.report.published, undefined);
  assert.equal(api.reportPublicationText(state.report), '旧版，未按本质量合同核验');
  assert.deepEqual(api.reportQualityMetrics(state.report), []);
}

function reportSelectionFetch(oldSessionIds = []) {
  const canonical = qualityReport(2, 'completed', true, 'pass');
  return async (url, options = {}) => {
    if (url === '/api/conversations/conversation-target') {
      return response({ conversation_id: 'conversation-target', title: '当前对话' });
    }
    if (url === '/api/research-sessions?limit=100') {
      return response({ research_sessions: oldSessionIds.map((research_session_id) => ({
        research_session_id, status: 'completed', conversation_id: 'old-conversation',
        conversation: { conversation_id: 'old-conversation', title: '旧对话' },
      })) });
    }
    if (oldSessionIds.some((id) => url === `/api/research-sessions/${id}`)) {
      const research_session_id = oldSessionIds.find((id) => url === `/api/research-sessions/${id}`);
      return response({ research_session_id, status: 'completed', conversation_id: 'old-conversation', conversation: { conversation_id: 'old-conversation', title: '旧对话' } });
    }
    if (url === '/api/research-sessions/session-target') {
      return response({
        research_session_id: 'session-target', conversation_id: 'conversation-target', status: 'completed',
        current_plan_version: 2,
        task: { research_task_id: 'task-target', research_session_id: 'session-target', status: 'completed', current_plan_version: 2 },
      });
    }
    if (url === '/api/research-tasks/task-target') {
      return response({ research_task_id: 'task-target', research_session_id: 'session-target', status: 'completed', current_plan_version: 2 });
    }
    if (url === '/api/research-tasks/task-target/evidence-matrix') return response({ error: { code: 'MATRIX_NOT_READY' } }, 404);
    if (url === '/api/research-tasks/task-target/report') return response({ ...canonical, markdown: '当前对话中的已发布报告正文', artifacts: [], selections: [], evidence: [] });
    if (url === '/api/research-tasks/task-target/reports/2?format=json') return response(canonical);
    if (url === '/api/research-sessions/session-target/artifacts') return response({ artifacts: [] });
    if (url === '/api/research-tasks/task-target/acquisitions') return response({ status: 'completed', items: [], events: [], issues: [] });
    if (url === '/api/research-notifications/n-target/read' && options.method === 'POST') {
      return response({ notification_id: 'n-target', event_seq: 221, research_session_id: 'session-target', notification_kind: 'completed', status: 'read', payload: { conversation_id: 'conversation-target' } });
    }
    throw new Error(`unexpected request: ${url}`);
  };
}

function canonicalReportV5() {
  return {
    report_id: 'report-v5',
    report_version: 5,
    status: 'completed',
    published: true,
    report_content: {
      schema_version: 'research-report-content-v1',
      research_question: { text: 'report quality review' },
      evidence_scope: { paper_ids: [], text: 'abstract evidence' },
      paper_analyses: [{ findings: [], limitations: [], method: '', paper_id: 'paper-1' }],
      cross_paper_comparisons: [{ dimension_id: 'facet-1', evidence_ids: [], paper_ids: [], statement: '' }],
      synthesis_findings: [{ evidence_ids: [], finding_id: 'finding-1', paper_ids: [], statement: '' }],
      research_gaps: [{ evidence_ids: [], statement: '' }],
    },
    quality_validation: {
      schema_version: 'report-quality-v1', count_method: 'report-quality-v1', status: 'pass',
      cjk_count: 2912, paper_count: 5, comparison_count: 5,
      supported_finding_count: 6, revision_count: 0,
    },
    generation: { published: true, path: 'agent_runner', report_version: 5 },
    reason_codes: [],
  };
}

async function testCurrentConversationLoadsSessionOutsideFirstHundred() {
  resetState();
  const oldSessionIds = Array.from({ length: 100 }, (_, index) => `old-session-${index}`);
  globalThis.location.pathname = '/c/conversation-target';
  globalThis.location.hash = '#research-view';
  const originalQuerySelectorAll = fakeDocument.querySelectorAll;
  fakeDocument.querySelectorAll = (selector) => selector.includes('.conversation-research-plan')
    ? [{ dataset: { researchSessionId: 'session-target' } }] : [];
  const requested = [];
  const fetch = reportSelectionFetch(oldSessionIds);
  fetchImpl = async (url, options) => { requested.push(url); return fetch(url, options); };

  await api.refreshWorkspace();

  assert.ok(requested.includes('/api/research-sessions/session-target'), 'current conversation session must be read by owner-scoped detail ID');
  assert.equal(state.tasks.length, 101, 'the selected session outside the page is surfaced in the existing task list');
  assert.equal(state.selectedTaskId, 'task-target');
  assert.equal(state.selectedSessionId, 'session-target');
  assert.equal(state.report.report_version, 2);
  assert.equal(state.report.markdown, '当前对话中的已发布报告正文');
  fakeDocument.querySelectorAll = originalQuerySelectorAll;
}

async function testCompletedSessionNotificationLoadsItsReportWithoutTaskId() {
  resetState();
  const notification = {
    notification_id: 'n-target', event_seq: 221, research_session_id: 'session-target', research_task_id: '',
    notification_kind: 'completed', status: 'unread', payload: { conversation_id: 'conversation-target', report_version: 2 },
  };
  state.notifications.set(notification.notification_id, notification);
  globalThis.location.pathname = '/c/old-conversation';
  globalThis.location.hash = '';
  const originalReplaceState = globalThis.history.replaceState;
  const originalSetTimeout = globalThis.setTimeout;
  const scheduled = [];
  globalThis.history.replaceState = (_state, _title, url) => {
    const next = new URL(url, 'http://localhost');
    globalThis.location.pathname = next.pathname;
    globalThis.location.hash = next.hash;
  };
  globalThis.setTimeout = (callback) => { scheduled.push(callback); return 9901; };
  fetchImpl = reportSelectionFetch(Array.from({ length: 100 }, (_, index) => `old-session-${index}`));

  await api.openNotification(notification);
  assert.equal(scheduled.length, 1, 'session notification schedules direct workspace selection');
  await scheduled[0]();

  assert.equal(state.notifications.get('n-target').status, 'read');
  assert.ok(state.tasks.some((task) => task.research_session_id === 'session-target'), 'notification target remains visible when the paged list omits it');
  assert.equal(state.selectedTaskId, 'task-target');
  assert.equal(state.selectedSessionId, 'session-target');
  assert.equal(state.report.report_version, 2);
  assert.equal(state.report.markdown, '当前对话中的已发布报告正文');
  globalThis.history.replaceState = originalReplaceState;
  globalThis.setTimeout = originalSetTimeout;
}

async function testReportNotificationUsesTaskEmbeddedInOwnerScopedSessionDetail() {
  resetState();
  const notification = {
    notification_id: 'notification-target', event_seq: 222,
    research_session_id: 'session-target', research_task_id: 'task-target',
    notification_kind: 'completed', status: 'unread', subject_version: 5,
    payload: { report_version: 5, message_id: 'message-target', artifact_ids: ['artifact-a', 'artifact-b'] },
  };
  state.notifications.set(notification.notification_id, notification);
  const originalReplaceState = globalThis.history.replaceState;
  const originalSetTimeout = globalThis.setTimeout;
  const originalLocation = globalThis.location;
  const scheduled = [];
  const requested = [];
  const oldList = deferred();
  const oldListStarted = deferred();
  globalThis.location = { pathname: '/c/old-conversation', search: '', hash: '' };
  globalThis.history.replaceState = (_state, _title, url) => {
    const next = new URL(url, 'http://localhost');
    globalThis.location.pathname = next.pathname;
    globalThis.location.hash = next.hash;
  };
  globalThis.setTimeout = (callback) => { scheduled.push(callback); return 9922; };
  const oldSessionIds = Array.from({ length: 100 }, (_, index) => `old-session-${index}`);
  const fallback = reportSelectionFetch(oldSessionIds);
  const report = canonicalReportV5();
  const legacyReport = { report_version: 1, plan_version: 1, status: 'completed', published: true, markdown: '旧计划报告正文' };
  const markdownArtifact = {
    artifact_id: 'artifact-v5-markdown', artifact_type: 'markdown', report_version: 5,
    download_url: '/api/research-sessions/session-target/artifacts/artifact-v5-markdown/download',
  };
  const sessionDetail = {
    research_session_id: 'session-target', conversation_id: 'conversation-target',
    status: 'completed', current_plan_version: 1,
    task: {
      research_task_id: 'task-target', research_session_id: 'session-target',
      status: 'failed', current_plan_version: 1,
    },
    plan: { research_session_id: 'session-target', version: 1, status: 'completed' },
    approvals: [], artifacts: [],
  };
  fetchImpl = async (url, options = {}) => {
    requested.push(url);
    if (url === '/api/research-notifications/notification-target/read' && options.method === 'POST') {
      return response({ ...notification, status: 'read' });
    }
    if (url === '/api/research-sessions/session-target') return response(sessionDetail);
    if (url === '/api/conversations/conversation-target') {
      return response({ conversation_id: 'conversation-target', title: '当前对话', status: 'active' });
    }
    if (url === '/api/research-sessions?limit=100') {
      oldListStarted.resolve();
      return oldList.promise;
    }
    if (url === '/api/research-tasks/task-target') {
      throw new Error('notification must be recoverable from the owner-scoped session detail');
    }
    if (url === '/api/research-tasks/task-target/evidence-matrix') return response({ error: { code: 'MATRIX_NOT_READY' } }, 404);
    if (url === '/api/research-tasks/task-target/report') return response({ ...legacyReport, artifacts: [], selections: [], evidence: [] });
    if (url === '/api/research-tasks/task-target/reports/5?format=json') return response(report);
    if (url === '/api/research-tasks/task-target/reports/5?format=markdown') return response('已发布版本五');
    if (url === '/api/research-sessions/session-target/artifacts') return response({ artifacts: [markdownArtifact] });
    if (url === '/api/research-sessions/session-target/artifacts?report_version=5') return response({ artifacts: [markdownArtifact] });
    if (url === '/api/research-tasks/task-target/acquisitions') return response({ status: 'completed', items: [], events: [], issues: [] });
    return fallback(url, options);
  };

  try {
    await api.openNotification(notification);
    assert.equal(scheduled.length, 1, 'the session notification schedules selection after opening its conversation');
    await oldListStarted.promise;
    await scheduled[0]();
    oldList.resolve(response({ research_sessions: oldSessionIds.map((research_session_id) => ({
      research_session_id, status: 'completed', conversation_id: 'old-conversation',
    })) }));
    await nextTurn();
    await nextTurn();

    assert.ok(requested.includes('/api/research-sessions/session-target'), 'the notification target is loaded directly by session ID');
    assert.ok(!requested.includes('/api/research-tasks/task-target'), 'the matching session detail supplies its nested task projection');
    assert.equal(state.notifications.get('notification-target').status, 'read');
    assert.equal(state.selectedTaskId, 'task-target');
    assert.equal(state.selectedSessionId, 'session-target');
    assert.equal(state.report.report_version, 5);
    assert.equal(state.report.markdown, '已发布版本五');
    assert.equal(state.report.quality_validation.cjk_count, 2912);
    assert.equal(state.report.published, true, 'the v5 canonical version, not the plan-v1 response, owns publication state');
    assert.ok(requested.includes('/api/research-tasks/task-target/reports/5?format=markdown'), 'report body is loaded from the selected canonical report version');
    assert.equal(state.reportVersionSelections.get('task-target'), 5, 'notification version is independent of current plan v1');
    assert.ok(state.tasks.some((task) => task.research_session_id === 'session-target'), 'the session outside the 100-row list stays visible');
  } finally {
    globalThis.history.replaceState = originalReplaceState;
    globalThis.setTimeout = originalSetTimeout;
    globalThis.location = originalLocation;
  }
}

async function testManualReportVersionSurvivesLateRefreshAndKeepsPickerValue() {
  resetState();
  const nodes = new Map();
  const originalGetElementById = fakeDocument.getElementById;
  fakeDocument.getElementById = (id) => {
    if (!nodes.has(id)) nodes.set(id, fakeElement());
    return nodes.get(id);
  };
  state.document = fakeDocument;
  state.selectedTaskId = 'task-version-race';
  state.selectedTask = { research_task_id: 'task-version-race', research_session_id: 'session-version-race', current_plan_version: 1 };
  state.taskGeneration = 12;
  state.reportVersions = [5, 2, 1];
  state.report = { report_version: 1, status: 'completed', published: true, markdown: '旧版正文', citation_manifest: [] };

  const delayedDefaultReport = deferred();
  const delayedV5Markdown = deferred();
  const requested = [];
  const v5 = canonicalReportV5();
  const v5Artifact = {
    artifact_id: 'artifact-v5-markdown', artifact_type: 'markdown', report_version: 5,
    download_url: '/api/research-sessions/session-version-race/artifacts/artifact-v5-markdown/download',
  };
  fetchImpl = async (url) => {
    requested.push(url);
    if (url.endsWith('/research-tasks/task-version-race/report')) return delayedDefaultReport.promise;
    if (url.endsWith('/research-tasks/task-version-race/reports/5?format=json')) return response(v5);
    if (url.endsWith('/research-tasks/task-version-race/reports/5?format=markdown')) return delayedV5Markdown.promise;
    if (url.endsWith('/research-sessions/session-version-race/artifacts')) return response({ artifacts: [v5Artifact] });
    if (url.endsWith('/research-sessions/session-version-race/artifacts?report_version=5')) return response({ artifacts: [v5Artifact] });
    if (url.endsWith('/research-tasks/task-version-race/acquisitions')) return response({ status: 'completed', items: [], events: [], issues: [] });
    throw new Error(`unexpected request: ${url}`);
  };

  try {
    const lateRefresh = api.loadReport('task-version-race');
    await nextTurn();
    const selection = api.selectReportVersion(5);
    assert.equal(nodes.get('research-report-version-select')?.value, '5', 'the picker keeps the user-selected version while its request is pending');
    await nextTurn();

    delayedDefaultReport.resolve(response({
      report_version: 1, plan_version: 1, status: 'completed', markdown: '旧版正文',
      selections: [], artifacts: [], evidence: [],
    }));
    await lateRefresh;
    assert.equal(state.report?.report_version, 1, 'the in-flight previous report stays visible until the manual version resolves');

    delayedV5Markdown.resolve(response('v5 正文来自 canonical Markdown API'));
    await selection;
    assert.equal(state.report?.report_version, 5);
    assert.equal(state.report?.markdown, 'v5 正文来自 canonical Markdown API');
    assert.equal(state.report?.quality_validation?.cjk_count, 2912);
    assert.equal(state.reportVersionSelections.get('task-version-race'), 5);

    fetchImpl = async (url) => {
      requested.push(url);
      if (url.endsWith('/research-tasks/task-version-race/report')) return response({
        report_version: 1, plan_version: 1, status: 'completed', markdown: '旧版正文',
        selections: [], artifacts: [], evidence: [],
      });
      if (url.endsWith('/research-sessions/session-version-race/artifacts')) return response({ artifacts: [v5Artifact] });
      if (url.endsWith('/research-tasks/task-version-race/reports/5?format=json')) return response(v5);
      if (url.endsWith('/research-tasks/task-version-race/reports/5?format=markdown')) return response('v5 正文恢复');
      if (url.endsWith('/research-sessions/session-version-race/artifacts?report_version=5')) return response({ artifacts: [v5Artifact] });
      if (url.endsWith('/research-tasks/task-version-race/acquisitions')) return response({ status: 'completed', items: [], events: [], issues: [] });
      throw new Error(`unexpected request: ${url}`);
    };
    await api.loadReport('task-version-race');
    assert.equal(state.report?.report_version, 5, 'terminal/SSE refresh restores the selected report version instead of default plan v1');
    assert.equal(state.report?.markdown, 'v5 正文恢复');
    assert.equal(state.report?.status, 'completed');
    assert.equal(api.isQualityValidated(state.report), true);
    assert.equal(state.report?.quality_validation?.cjk_count, 2912);
    assert.ok(requested.includes('/api/research-tasks/task-version-race/reports/5?format=json'));
  } finally {
    fakeDocument.getElementById = originalGetElementById;
  }
}

async function runBootListRace(oldListOutcome) {
  resetState();
  const oldSessionIds = Array.from({ length: 100 }, (_, index) => `old-session-${index}`);
  const oldList = deferred();
  const originalGetElementById = fakeDocument.getElementById;
  const originalQuerySelectorAll = fakeDocument.querySelectorAll;
  const originalLocation = globalThis.location;
  const originalHistory = globalThis.history;
  const originalEventSource = globalThis.EventSource;
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const timeouts = [];
  const requested = [];
  const bootNodes = new Map();
  let listReads = 0;
  fakeDocument.getElementById = (id) => {
    if (!bootNodes.has(id)) bootNodes.set(id, fakeElement());
    return bootNodes.get(id);
  };
  fakeDocument.querySelectorAll = () => [];
  globalThis.location = { pathname: '/c/conversation-target', hash: '#research-view' };
  globalThis.history = { pushState() {}, replaceState() {} };
  globalThis.EventSource = class { addEventListener() {} close() {} };
  globalThis.setTimeout = (callback, delay = 0) => { timeouts.push({ callback, delay }); return 9900 + timeouts.length; };
  globalThis.clearTimeout = () => {};
  const pagedFetch = reportSelectionFetch(oldSessionIds);
  fetchImpl = async (url, options = {}) => {
    requested.push(url);
    if (url.startsWith('/api/research-notifications?')) return response({ notifications: [] });
    if (url === '/api/conversations/conversation-target') {
      return response({ conversation_id: 'conversation-target', title: '当前对话', research_session_id: 'session-target' });
    }
    if (url === '/api/research-sessions?limit=100') {
      listReads += 1;
      return listReads === 1 ? oldList.promise : pagedFetch(url, options);
    }
    return pagedFetch(url, options);
  };

  try {
    api.boot(fakeDocument);
    assert.equal(listReads, 1, 'boot starts its independent paged-list request');
    const refreshBoot = timeouts.find((item) => item.delay === 0);
    assert.ok(refreshBoot, 'boot schedules the normal current-workspace refresh');
    await refreshBoot.callback();
    assert.equal(state.selectedTaskId, 'task-target');
    assert.equal(state.selectedSessionId, 'session-target');
    assert.equal(state.report?.report_version, 2, `boot refresh should load the current report; status=${bootNodes.get('research-report-state')?.textContent}; requests=${JSON.stringify(requested)}`);
    assert.ok(state.tasks.some((task) => task.research_session_id === 'session-target'));

    if (oldListOutcome === 'reject') oldList.reject(new Error('late boot list failure'));
    else oldList.resolve(response({ research_sessions: [] }));
    await nextTurn();
    await nextTurn();

    assert.equal(state.selectedTaskId, 'task-target');
    assert.equal(state.selectedSessionId, 'session-target');
    assert.equal(state.report.report_version, 2);
    assert.ok(state.tasks.some((task) => task.research_session_id === 'session-target'), 'late boot result cannot erase the page-out current session');
  } finally {
    state.notificationEventSource?.close?.();
    state.eventSource?.close?.();
    [state.reportPollTimer, state.reconnectTimer, state.notificationReconnectTimer, state.acquisition?.pollTimer]
      .filter(Boolean).forEach((timer) => originalClearTimeout(timer));
    fakeDocument.getElementById = originalGetElementById;
    fakeDocument.querySelectorAll = originalQuerySelectorAll;
    globalThis.location = originalLocation;
    globalThis.history = originalHistory;
    globalThis.EventSource = originalEventSource;
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
    state.booted = false;
    state.notificationLoading = false;
    state.notificationEventSource = null;
    state.eventSource = null;
  }
}

async function testLateBootListFailureCannotClearSelectedCurrentSession() {
  await runBootListRace('reject');
}

async function testLateBootListSuccessCannotDropSelectedCurrentSession() {
  await runBootListRace('resolve');
}

(async () => {
  await testLateGenerationResponseCannotWriteTheNextTask();
  await testLateUploadResponseCannotCreateTheNextTaskButton();
  await testVersionFailureRollsBackAndLateVersionCannotWin();
  await testReportSubmissionUsesIdempotencyKeyAndTreats202AsPending();
  await testForged202CannotPublishWhenCanonicalReadFails();
  await testAsyncPollCannotPublishMalformedQualitySchema();
  await testSelectingLegacyVersionDoesNotInheritCurrentQualityFields();
  await testCurrentConversationLoadsSessionOutsideFirstHundred();
  await testCompletedSessionNotificationLoadsItsReportWithoutTaskId();
  await testReportNotificationUsesTaskEmbeddedInOwnerScopedSessionDetail();
  await testManualReportVersionSurvivesLateRefreshAndKeepsPickerValue();
  await testLateBootListFailureCannotClearSelectedCurrentSession();
  await testLateBootListSuccessCannotDropSelectedCurrentSession();
  console.log('Report action race contract: PASS (task isolation, rollback, delayed response ordering)');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
