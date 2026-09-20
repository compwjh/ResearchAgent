/* Spec034 Task12 TDD probe: after approve_plan, mergeSessionCommandResult must
 * auto-select the newly materialized Task, load its report, and connect the
 * event stream so the runtime timeline can render.
 *
 * Runs the REAL research-tasks.js mergeSessionCommandResult through a robust
 * fake-DOM / fake-fetch / fake-EventSource harness and asserts that the Task
 * GET /report and the SSE /events endpoints are actually requested.
 *
 * Coverage of the confirmed race (root cause 100%): a concurrent refreshWorkspace
 * that runs while selectTask is in flight must NOT clobber the in-flight
 * selection. We reproduce it faithfully by invoking the REAL refreshWorkspace()
 * during selectTask's session fetch (simulating the concurrent refresh). Two
 * sub-cases:
 *   2a) list still lacks the new Task  -> refreshWorkspace would reset selection to null
 *   2b) list already has the new Task  -> refreshWorkspace would re-select (duplicate SSE pipe)
 * In both, loadReport + connectStream must execute exactly once.
 */
const assert = require('assert');

// --- capture layer -------------------------------------------------------
const FETCH_URLS = [];
const EVENTSOURCE_URLS = [];

// Race configuration: when set, the session-detail fetch triggers a concurrent
// refreshWorkspace() exactly once, mirroring the real race where the workspace
// refresh runs while selectTask is awaiting its session fetch.
let RACE = { mode: null, fired: false };

function makeResponse(body) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  };
}

function sessionDetail() {
  return {
    research_session_id: 'session-1', status: 'queued', current_plan_version: 1,
    conversation_id: 'conv-1', project_id: 'proj-1',
    research_task_id: 'task-new',
  };
}

function taskDetail() {
  return {
    research_task_id: 'task-new', status: 'queued', research_session_id: 'session-1',
    current_plan_version: 1, goal_excerpt: '测试研究目标',
  };
}

function routeFetch(url) {
  FETCH_URLS.push(url);
  if (url.includes('/evidence-matrix')) return makeResponse({ evidence: [] });
  if (url.includes('/report')) return makeResponse({ report_version: 1, status: 'running', artifacts: [], evidence: [] });
  if (url.includes('/artifacts')) return makeResponse({ artifacts: [] });
  if (url.includes('/research-tasks/') && !url.includes('/events')) return makeResponse(taskDetail());
  // Session-detail fetch: optionally fire the concurrent refreshWorkspace race.
  if (url.includes('/research-sessions/session-1')) {
    if (RACE.mode && !RACE.fired) {
      RACE.fired = true;
      // The concurrent refresh runs while selectTask is still in flight.
      // eslint-disable-next-line no-use-before-define
      refreshWorkspace();
    }
    return makeResponse(sessionDetail());
  }
  if (url.includes('/research-sessions') && url.includes('limit=100')) {
    // List endpoint: empty (2a) or already containing the new Task (2b).
    if (RACE.mode === 'with-task') {
      return makeResponse({ research_sessions: [{ research_session_id: 'session-1', research_task_id: 'task-new', status: 'queued' }] });
    }
    return makeResponse({ research_sessions: [] });
  }
  return makeResponse({});
}

// --- robust fake DOM (no-op element that survives arbitrary access) --------
function makeEl() {
  const store = {
    textContent: '', hidden: false, value: '', innerHTML: '', id: '',
    dataset: {}, style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    selected: false, disabled: false, checked: false,
  };
  return new Proxy(store, {
    get(t, p) {
      if (p === 'querySelector') return () => makeEl();
      if (p === 'querySelectorAll') return () => [];
      if (['appendChild', 'append', 'replaceChildren', 'addEventListener', 'removeEventListener',
        'setAttribute', 'removeAttribute', 'remove', 'focus', 'blur', 'click', 'closest',
        'insertBefore', 'dispatchEvent', 'scrollIntoView', 'setSelectionRange'].includes(p)) return () => {};
      if (p === 'getAttribute') return () => '';
      if (p === 'getAttributeNS') return () => '';
      if (p === 'hasAttribute') return () => false;
      if (p in t) return t[p];
      return makeEl();
    },
    set(t, p, v) { t[p] = v; return true; },
  });
}

const fakeDocument = {
  getElementById: () => makeEl(),
  createElement: () => makeEl(),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  body: makeEl(),
};

globalThis.document = fakeDocument;
globalThis.fetch = async (url) => routeFetch(String(url));
globalThis.EventSource = class {
  constructor(url) { this.url = String(url); this.closed = false; EVENTSOURCE_URLS.push(this.url); }
  addEventListener() {}
  set onerror(_fn) {}
  close() { this.closed = true; }
};
globalThis.ResearchSessionUI = require('../frontend/research-session-ui.js');
globalThis.location = { hash: '', href: '' };
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.dispatchEvent = () => true;
globalThis.history = { pushState() {}, replaceState() {}, __researchTasksNavigationGuard: undefined };
globalThis.PopStateEvent = class {};
globalThis.setTimeout = globalThis.setTimeout || ((fn) => fn());
globalThis.clearTimeout = globalThis.clearTimeout || (() => {});

const { mergeSessionCommandResult, selectTask, refreshWorkspace, state } = require('../frontend/research-tasks.js');

function resetState() {
  state.selectedTaskId = null;
  state.selectedSessionId = null;
  state.selectedTask = null;
  state.eventSource = null;
  state.streamGeneration = 0;
  state.streamEnded = false;
  state.lastSeq = 0;
  state.selectTaskInFlight = null;
  state.report = null;
  state.matrix = null;
  state.terminal = null;
  state.events = new Map();
  state.selectedPapers = new Set();
  state.selectedPaperCount = null;
  state.selectionDetails = new Map();
  state.selectionSnapshotTaskId = null;
  state.reportSelections = [];
  state.reportViews = new Map();
  state.reportVersions = [];
  state.approvalInFlight = false;
  state.statusNotice = '';
  state.notificationEventSource = null;
  state.tasks = [];
  state.sessions = [];
  state.conversationId = null;
}

function resetCounters() {
  FETCH_URLS.length = 0;
  EVENTSOURCE_URLS.length = 0;
}

const taskEventSources = () => EVENTSOURCE_URLS.filter((u) => u.includes('/research-tasks/') && u.includes('/events'));
// The loadReport endpoint is the singular `/research-tasks/<id>/report`; exclude the
// plural `/research-tasks/<id>/reports/<version>` report-body fetch.
const reportFetches = () => FETCH_URLS.filter((u) => /\/research-tasks\/task-new\/report(\?|$)/.test(u));

const approveResult = {
  research_session_id: 'session-1',
  status: 'queued',
  subject_version: 1,
  approval: { kind: 'plan', status: 'approved' },
  research_task_id: 'task-new',
  task: { research_task_id: 'task-new', status: 'draft', current_plan_version: 1, research_session_id: 'session-1' },
};

(async () => {
  // === Scenario 1: happy path + idempotent replay (no concurrent refresh) ===
  resetState(); resetCounters(); RACE = { mode: null, fired: false };
  await mergeSessionCommandResult(approveResult, 'session-1');
  assert.strictEqual(reportFetches().length, 1, `report must be requested exactly once; got fetches: ${JSON.stringify(FETCH_URLS)}`);
  assert.strictEqual(taskEventSources().length, 1, `exactly one Task event stream expected; got ${JSON.stringify(taskEventSources())}`);

  resetCounters();
  await mergeSessionCommandResult(approveResult, 'session-1');
  // Replay must not open a new SSE pipe or re-fetch the report (counters were
  // cleared before the replay, so any positive count is a duplicate).
  assert.strictEqual(taskEventSources().length, 0, `replay must not open a new SSE pipe (got ${taskEventSources().length})`);
  assert.strictEqual(reportFetches().length, 0, `replay must not re-fetch report (got ${reportFetches().length})`);
  console.log('Task12 scenario1 happy-path + replay idempotency: PASS');

  // === Scenario 2a: concurrent refreshWorkspace RESETS selection (list lacks Task) ===
  resetState(); resetCounters(); RACE = { mode: 'empty', fired: false };
  await mergeSessionCommandResult(approveResult, 'session-1');
  assert.strictEqual(reportFetches().length, 1, `2a: report must be requested exactly once despite concurrent reset; got ${JSON.stringify(FETCH_URLS)}`);
  assert.strictEqual(taskEventSources().length, 1, `2a: exactly one Task event stream despite concurrent reset; got ${JSON.stringify(taskEventSources())}`);
  console.log('Task12 scenario2a race(reset) -> loadReport+connectStream once: PASS');

  // === Scenario 2b: concurrent refreshWorkspace RE-SELECTS (list has Task => dup SSE) ===
  resetState(); resetCounters(); RACE = { mode: 'with-task', fired: false };
  await mergeSessionCommandResult(approveResult, 'session-1');
  assert.strictEqual(reportFetches().length, 1, `2b: report must be requested exactly once despite re-select; got ${JSON.stringify(FETCH_URLS)}`);
  assert.strictEqual(taskEventSources().length, 1, `2b: exactly ONE Task event stream (no duplicate SSE pipe); got ${JSON.stringify(taskEventSources())}`);
  console.log('Task12 scenario2b race(re-select) -> unique SSE pipe: PASS');

  console.log('Task12 approval -> Task auto-select / report / events (race-safe): ALL PASS');
})().catch((err) => {
  console.error('Task12 approval probe FAILED:', err && err.message);
  console.error('  fetches:', JSON.stringify(FETCH_URLS));
  console.error('  eventsources:', JSON.stringify(EVENTSOURCE_URLS));
  process.exit(1);
});
