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
  state.selectedTask = null;
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
        report_version: 3, status: 'generating', quality_status: 'pending', published: false,
        reason_codes: [], report_url: '/api/research-tasks/task-report/reports/3?format=json',
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

(async () => {
  await testLateGenerationResponseCannotWriteTheNextTask();
  await testLateUploadResponseCannotCreateTheNextTaskButton();
  await testVersionFailureRollsBackAndLateVersionCannotWin();
  await testReportSubmissionUsesIdempotencyKeyAndTreats202AsPending();
  await testAsyncPollCannotPublishMalformedQualitySchema();
  await testSelectingLegacyVersionDoesNotInheritCurrentQualityFields();
  console.log('Report action race contract: PASS (task isolation, rollback, delayed response ordering)');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
