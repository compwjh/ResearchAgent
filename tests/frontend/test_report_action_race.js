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
  getElementById: () => null,
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

let fetchImpl = async () => response({});
globalThis.fetch = (...args) => fetchImpl(...args);

const api = require('../../frontend/research-tasks.js');
const { state } = api;

function resetState() {
  state.document = fakeDocument;
  state.selectedTaskId = null;
  state.selectedTask = null;
  state.taskGeneration = 0;
  state.reportVersionRequest = 0;
  state.report = null;
  state.reportViews = new Map();
  state.reportVersions = [];
  state.reportFormat = 'markdown';
  state.matrix = null;
  state.paperDisplays = new Map();
  state.paperDisplaysPending = new Set();
  state.acquisition.reportActionMessage = '';
  state.acquisition.reportActionTaskIds = [];
  state.acquisition.reportActionStatus = '';
  state.acquisition.reportActionVersion = null;
  state.acquisition.reportActionInFlight = false;
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

(async () => {
  await testLateGenerationResponseCannotWriteTheNextTask();
  await testLateUploadResponseCannotCreateTheNextTaskButton();
  await testVersionFailureRollsBackAndLateVersionCannotWin();
  console.log('Report action race contract: PASS (task isolation, rollback, delayed response ordering)');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
