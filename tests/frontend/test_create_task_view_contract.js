'use strict';

/**
 * 任务 P：创建研究会话成功后必须「留在深度研究视图」（TDD / RED → GREEN）。
 *
 * 真实 require research-tasks.js，在 fake DOM 上驱动 createTask() 成功路径，
 * 复现真实浏览器的因果链：
 *   - app.js 的 openConversation() 会 showView('chat') → hideAllMainAreas()
 *     把整个 #research-view 隐藏；
 *   - research-tasks.js 的 guardedHistoryMethod 也会在 pushState 到不带
 *     #research-view hash 的 /c/<id> 时 closeResearchView() 隐藏视图。
 * 契约断言：创建成功后 #research-view 仍可见、新任务被选中、会话在后台关联。
 *
 * 本文件由 test_create_task_view_contract.py 经 subprocess 调用。
 */
const assert = require('node:assert/strict');

// ---- 最小 fake DOM -------------------------------------------------------
function makeEl(id) {
  return {
    id, hidden: false, textContent: '', value: '', checked: false, disabled: false,
    tabIndex: 0, title: '', dataset: {}, attributes: {}, childNodes: [], children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    setAttribute(key, value) { this.attributes[key] = String(value); },
    removeAttribute(key) { delete this.attributes[key]; },
    getAttribute(key) { return Object.prototype.hasOwnProperty.call(this.attributes, key) ? this.attributes[key] : null; },
    appendChild(child) { this.childNodes.push(child); this.children.push(child); return child; },
    append(...kids) { kids.forEach((k) => this.appendChild(k)); },
    replaceChildren(...kids) { this.childNodes = []; this.children = []; kids.forEach((k) => this.appendChild(k)); },
    insertBefore(node, ref) {
      const at = ref ? this.children.indexOf(ref) : -1;
      if (at >= 0) { this.children.splice(at, 0, node); this.childNodes.splice(at, 0, node); }
      else { this.children.push(node); this.childNodes.push(node); }
      return node;
    },
    remove() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    closest() { return null; },
    focus() {},
    addEventListener() {}, removeEventListener() {},
  };
}

const ids = new Map();
function el(id) {
  if (!ids.has(id)) ids.set(id, makeEl(id));
  return ids.get(id);
}

// require 时先给一个「无 research-view」的 document，让 boot() 提前 return，
// 避免它安装 history guard / 发通知请求污染本契约的受控场景。
const bootDocument = {
  getElementById: () => null, createElement: () => makeEl(''),
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
};

const researchView = el('research-view');
const chatView = el('chat');
const mainAreas = [researchView, chatView];
const fullDocument = {
  getElementById: (id) => el(id),
  createElement: () => makeEl(''),
  querySelector: () => null,
  querySelectorAll: (selector) => (String(selector) === '.main-area' ? mainAreas : []),
  addEventListener() {}, removeEventListener() {},
};

const historyCalls = [];
const openConversationCalls = [];
const requests = [];

// 复现 bindNavigation 的 guardedHistoryMethod：任何 push/replaceState 只要目标
// URL 不带 #research-view hash，就会 closeResearchView() 隐藏研究视图。
function applyHistory(url) {
  const value = String(url);
  historyCalls.push(value);
  const hashAt = value.indexOf('#');
  globalThis.location.pathname = hashAt < 0 ? value : value.slice(0, hashAt);
  globalThis.location.hash = hashAt < 0 ? '' : value.slice(hashAt);
  if (globalThis.location.hash !== '#research-view') {
    mainAreas.forEach((section) => { section.hidden = true; });
  }
}

globalThis.document = bootDocument;
globalThis.location = { pathname: '/', search: '', hash: '#research-view' };
globalThis.history = {
  pushState(_state, _title, url) { applyHistory(url); },
  replaceState(_state, _title, url) { applyHistory(url); },
};
// app.js 的 openConversation() → showView('chat') → hideAllMainAreas()
globalThis.openConversation = (conversationId) => {
  openConversationCalls.push(conversationId);
  mainAreas.forEach((section) => { section.hidden = true; });
};
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.dispatchEvent = () => true;
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};
globalThis.EventSource = class { addEventListener() {} close() {} };
globalThis.FormData = class { append() {} };
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };

const createdSession = {
  research_session_id: 'session-new', research_task_id: 'task-new',
  status: 'intake_pending', conversation_id: 'conv-new',
  created_at: '2026-01-01T00:00:00Z',
};
globalThis.fetch = async (url, options = {}) => {
  const path = String(url);
  requests.push(path);
  const ok = (body) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });
  if (path === '/api/research-sessions' && options.method === 'POST') {
    return ok({
      session: createdSession,
      conversation: { conversation_id: 'conv-new', title: '新建深度研究会话' },
    });
  }
  if (path === '/api/research-tasks/task-new') {
    return ok({ ...createdSession, current_plan_version: 1 });
  }
  if (path === '/api/research-sessions/session-new') {
    return ok({ ...createdSession, task: createdSession });
  }
  if (path.startsWith('/api/conversations/')) {
    return ok({ conversation_id: 'conv-new', title: '新建深度研究会话' });
  }
  return ok({});
};

const api = require('../../frontend/research-tasks.js');

async function run() {
  assert.equal(typeof api.createTask, 'function', '须导出 createTask 供契约 harness 驱动成功路径');
  api.state.document = fullDocument;
  api.state.booted = true;

  // 表单：任务 P 之前的 create tab 已经有这些输入；填满合法值让 createTask 走到成功分支
  el('research-goal').value = '创建后留在研究视图的契约验证';
  el('research-quality').value = 'balanced';
  el('research-target-count').value = '12';
  el('research-language').value = 'zh';
  el('research-review-plan').checked = false;
  el('research-year-from').value = '2020';
  el('research-year-to').value = '2024';

  const event = { preventDefault() {}, stopPropagation() {}, target: null };
  await api.createTask(event);

  // 1. 创建成功后绝不能切到 app.js 的聊天视图（它会隐藏整个研究视图）
  assert.equal(openConversationCalls.length, 0,
    '创建成功后不得调用 app.js 的 openConversation（会 showView(chat) 并隐藏 #research-view）');
  // 2. 核心契约：#research-view 仍可见
  assert.equal(researchView.hidden, false,
    '创建成功后 #research-view 必须仍可见，用户应留在深度研究视图');
  // 3. 切回「研究任务」tab，任务列表/详情可见
  assert.equal(api.state.activeResearchTab, 'tasks', '创建成功后必须切回「研究任务」tab');
  assert.equal(el('research-tabpanel-tasks').hidden, false, '「研究任务」面板必须可见');
  // 4. 新任务被选中、出现在列表
  assert.equal(api.state.selectedTaskId, 'task-new', '创建成功后新任务必须被选中');
  assert.equal(api.state.selectedSessionId, 'session-new', '创建成功后新会话必须被选中');
  assert.ok(api.state.tasks.some((task) => task.research_task_id === 'task-new'),
    '新任务卡片必须进入「研究任务」列表');
  // 5. 会话关联语义保留（后台，不隐藏视图）
  assert.equal(api.state.conversationId, 'conv-new', '会话关联须保留在 state.conversationId');
  assert.ok(historyCalls.some((url) => url.includes('/c/conv-new') && url.includes('#research-view')),
    '后台关联须用带 #research-view hash 的 /c/<id> URL，避免 history guard 隐藏研究视图');
  assert.ok(requests.includes('/api/research-sessions'), '创建请求须发出');

  // 6. 任务 V / M1：创建后「当前会话」指示须反映新会话（真实行为探针）。
  const currentConversationLabel = String(el('research-current-conversation').textContent);
  assert.ok(
    currentConversationLabel.includes('conv-new'),
    `创建成功后 #research-current-conversation 必须反映新会话 conv-new，实际：${currentConversationLabel}`,
  );

  console.log('ok - create task stays in research view contract');
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
