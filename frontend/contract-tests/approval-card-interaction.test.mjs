// 契约测试：spec-036 task-04 —— 审批卡片交互收口
// 零依赖：Node 内置 vm + 轻量假 DOM，直接加载真实源码 app.js / research-tasks.js。
// 锁定两条不变量：
//   1) 非 pending 状态下，DOM 中根本不存在批准/拒绝按钮节点。
//   2) 状态文案为中文（pending→待处理 / approved→已批准 / rejected|declined→已拒绝 / superseded→已被新版本替代）。
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const FRONTEND = path.resolve(import.meta.dirname, '..');
const CHINESE = /[一-龥]/;
const ENGLISH_AFTER_YI = /已[a-z]/; // 形如「已approved」

// ---- 轻量假 DOM：可真实记录 children / dataset / textContent，供断言 ----
class FakeEl {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.dataset = {};
    this._text = '';
    this.className = '';
    this.type = '';
    this.disabled = false;
    this.handlers = {};
    this.attributes = {};
  }
  set textContent(v) { this._text = String(v); }
  get textContent() { return this._text; }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { for (const c of cs) this.children.push(c); }
  replaceChildren(...cs) { this.children = cs; }
  prepend(...cs) { this.children.unshift(...cs); }
  addEventListener(evt, fn) { (this.handlers[evt] ||= []).push(fn); }
  removeEventListener() {}
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; }
  hasAttribute(k) { return k in this.attributes; }
  removeAttribute(k) { delete this.attributes[k]; }
  querySelector(sel) { return this._qs ? this._qs(sel) : null; }
  querySelectorAll() { return []; }
  remove() {}
  get classList() {
    const self = this;
    return {
      add(...c) { for (const x of c) if (!self.className.split(/\s+/).includes(x)) self.className = (self.className + ' ' + x).trim(); },
      remove(...c) { self.className = self.className.split(/\s+/).filter(x => !c.includes(x)).join(' '); },
      toggle() {}, contains(c) { return self.className.split(/\s+/).includes(c); },
    };
  }
}

// 通用兜底 Proxy：app.js 顶层会立即 document.querySelector(...) 并访问其属性，
// 用该 Proxy 让顶层执行不抛错；渲染调用本身用的是上面的真实 FakeEl。
function makeUniversal() {
  const target = function () {};
  // 这些遍历/终止属性必须返回 null，否则 `while (el = el.parentNode)` 之类
  // 的祖先遍历会在 Proxy 上死循环。
  const DEAD_ENDS = new Set([
    'parentNode', 'parentElement', 'ownerDocument', 'nextSibling', 'previousSibling',
    'nextElementSibling', 'previousElementSibling', 'firstChild', 'lastChild',
    'firstElementChild', 'lastElementChild', 'childNodes', 'shadowRoot', 'assignedSlot',
  ]);
  const handler = {
    get(_t, prop) {
      if (prop === Symbol.toPrimitive) return () => '';
      if (prop === Symbol.iterator) return function* () {};
      if (DEAD_ENDS.has(prop)) return null;
      if (prop === 'nodeType') return 1;
      if (prop === 'length') return 0;
      if (prop === 'dataset') return {};
      if (prop === 'classList') return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
      if (prop === 'children') return [];
      if (prop === 'style') return makeUniversal();
      if (prop === 'textContent' || prop === 'value' || prop === 'innerHTML') return '';
      if (prop === 'then') return undefined;
      return makeUniversal();
    },
    apply() { return makeUniversal(); },
    construct() { return makeUniversal(); },
    set() { return true; },
  };
  return new Proxy(target, handler);
}

function baseGlobals(extra = {}) {
  const g = {
    console,
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    CustomEvent: class { constructor(t, o) { this.type = t; this.detail = o && o.detail; } },
    Event: class { constructor(t) { this.type = t; } },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    navigator: { userAgent: 'node' },
    location: { pathname: '/', hash: '', href: 'http://localhost/' },
    history: { replaceState() {}, pushState() {} },
    marked: makeUniversal(),
    DOMPurify: makeUniversal(),
    HTMLElement: function () {}, Node: function () {},
    addEventListener: () => {}, dispatchEvent: () => {},
  };
  // 补齐 Node 的 Web/全局对象，避免 app.js 顶层无关的异步初始化在 vm 沙箱里抛 ReferenceError。
  const NODE_GLOBALS = [
    'URLSearchParams', 'URL', 'Headers', 'Request', 'Response', 'FormData', 'AbortController',
    'AbortSignal', 'TextEncoder', 'TextDecoder', 'EventTarget', 'queueMicrotask', 'crypto',
    'btoa', 'atob', 'WebSocket', 'Blob', 'structuredClone', 'ReadableStream', 'WritableStream',
    'MessageChannel', 'MessagePort', 'ReadableByteStreamController',
  ];
  for (const k of NODE_GLOBALS) if (globalThis[k] !== undefined) g[k] = globalThis[k];
  Object.assign(g, extra);
  g.window = g; g.globalThis = g; g.self = g;
  return g;
}

function loadApp() {
  const code = fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8');
  const appDocument = {
    createElement: (tag) => new FakeEl(tag),
    querySelector: () => makeUniversal(),
    querySelectorAll: () => [],
    getElementById: () => makeUniversal(),
    addEventListener: () => {},
    body: makeUniversal(),
    documentElement: makeUniversal(),
  };
  const context = baseGlobals({ document: appDocument });
  vm.createContext(context);
  vm.runInContext(code, context, { filename: 'app.js', timeout: 4000 });
  return context;
}

function loadResearchTasks() {
  const code = fs.readFileSync(path.join(FRONTEND, 'research-tasks.js'), 'utf8');
  const container = new FakeEl('div');
  const fakeDocument = {
    createElement: (tag) => new FakeEl(tag),
    getElementById: (id) => (id === 'research-session-approvals' ? container : null),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    body: null,
  };
  const sandbox = baseGlobals();
  const moduleObj = { exports: {} };
  sandbox.module = moduleObj;
  sandbox.require = (name) => {
    if (name === './research-session-ui.js') return {};
    throw new Error('unexpected require: ' + name);
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'research-tasks.js', timeout: 4000 });
  const api = moduleObj.exports;
  // boot 用假 DOM 让 state.document 就绪；因 research-view 缺失会提前返回，安全。
  api.boot(fakeDocument);
  return { api, container };
}

const SAMPLE_APPROVALS = [
  { kind: 'plan', status: 'approved', subject_version: 2, approval_request_id: 'ar-1' },
  { kind: 'capability_override', status: 'rejected', subject_version: 1, approval_request_id: 'ar-2' },
  { kind: 'resource_extension', status: 'superseded', subject_version: 3, approval_request_id: 'ar-3' },
  { kind: 'plan', status: 'pending', subject_version: 4, approval_request_id: 'ar-4' },
];

function collectButtons(node, acc = []) {
  for (const c of node.children || []) {
    if (c && c.tagName === 'BUTTON') acc.push(c);
    if (c && c.children) collectButtons(c, acc);
  }
  return acc;
}

function assertCard(card, expectPending) {
  const statusEl = card.children.find((c) => /approval-status$/.test(c.className || ''));
  assert.ok(statusEl, 'status element must exist');
  assert.match(statusEl.textContent, CHINESE, `状态文案应为中文，实际：${statusEl.textContent}`);
  assert.ok(!ENGLISH_AFTER_YI.test(statusEl.textContent), `状态文案不得出现「已+英文」，实际：${statusEl.textContent}`);
  const buttons = collectButtons(card);
  if (expectPending) {
    assert.equal(buttons.length, 2, 'pending 卡片应有 2 个按钮（含嵌套在 actions 容器内）');
    assert.equal(statusEl.textContent, '待处理');
    assert.ok(buttons.every((b) => /command$/.test(b.className || '')), 'pending 按钮应为 command 类');
  } else {
    assert.equal(buttons.length, 0, `非 pending（${card.dataset.status}）卡片必须无任何按钮节点`);
    assert.equal(card.children.length, 3, '非 pending 卡片仅含 标题/状态/元信息');
  }
}

describe('spec-036 task-04 审批卡片交互', () => {
  test('A：会话内研究面板（renderConversationApprovals）非 pending 不渲染按钮，状态中文', () => {
    const context = loadApp();
    const render = context.renderConversationApprovals;
    assert.equal(typeof render, 'function', 'renderConversationApprovals 应为全局函数');
    const container = new FakeEl('div');
    const panel = {
      dataset: { researchSessionId: 'sess-1' },
      querySelector: (sel) => (sel === '.conversation-research-approvals' ? container : null),
    };
    render(panel, SAMPLE_APPROVALS, {});
    assert.equal(container.children.length, SAMPLE_APPROVALS.length, '应渲染全部 4 张卡片');
    for (const card of container.children) assertCard(card, card.dataset.status === 'pending');
  });

  test('B：研究工作台（renderSessionApprovals）非 pending 不渲染按钮，状态中文', () => {
    const { api, container } = loadResearchTasks();
    assert.equal(typeof api.renderSessionApprovals, 'function', 'renderSessionApprovals 应被导出供测试');
    api.renderSessionApprovals(SAMPLE_APPROVALS, 'sess-1', 4, {});
    assert.equal(container.children.length, SAMPLE_APPROVALS.length, '应渲染全部 4 张卡片');
    for (const card of container.children) assertCard(card, card.dataset.status === 'pending');
  });

  test('回归：approved 卡片 DOM 中绝无批准/拒绝按钮（两视图一致）', () => {
    const context = loadApp();
    const container = new FakeEl('div');
    const panel = { dataset: {}, querySelector: (sel) => (sel === '.conversation-research-approvals' ? container : null) };
    context.renderConversationApprovals(panel, [{ kind: 'plan', status: 'approved', subject_version: 1, approval_request_id: 'a' }], {});
    const approvedCard = container.children[0];
    assert.equal(collectButtons(approvedCard).length, 0);

    const { api, container: containerB } = loadResearchTasks();
    api.renderSessionApprovals([{ kind: 'plan', status: 'approved', subject_version: 1, approval_request_id: 'a' }], 's', 1, {});
    const approvedCardB = containerB.children[0];
    assert.equal(collectButtons(approvedCardB).length, 0);
  });
});
