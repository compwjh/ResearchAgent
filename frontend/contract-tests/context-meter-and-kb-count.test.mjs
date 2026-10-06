// 契约测试：spec-036 task-03 —— 上下文模块始终可见 + KB 计数加载态
// 零依赖：Node 内置 vm + 轻量假 DOM，直接加载真实源码 app.js。
// 锁定不变量：
//   1) 无会话（renderContextUsage(null)）时模块可见（绝不带 is-idle → visibility:hidden），且不显示 0% 占位。
//   2) 有数据时显示真实百分比（含空历史会话的恒定上下文基线，非 0%）。
//   3) 加载中三态：is-loading + 「加载中」文案 + spinner。
//   4) 失败三态：值「—」+ 重试按钮。
//   5) 首屏 #kb-count / #kb-nav-count 不得硬编码 0：初始进入加载态（spinner），数据到达后淡入真实数字，失败显示「!」+ 重试。
//   6) index.html 契约：#context-meter 无 is-idle、#kb-count / #kb-nav-count 初始非硬编码 0。
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const FRONTEND = path.resolve(import.meta.dirname, '..');
const INDEX_HTML = path.resolve(FRONTEND, 'index.html');

// ---- 轻量假 DOM：真实记录 children / className / dataset / textContent，供断言 ----
class FakeEl {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.dataset = {};
    this._text = '';
    this.className = '';
    this.type = '';
    this.disabled = false;
    this.hidden = false;
    this.style = {};
    this.handlers = {};
    this.attributes = {};
  }
  set textContent(v) { this._text = String(v); }
  get textContent() { return this._text; }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { for (const c of cs) this.children.push(c); }
  replaceChildren(...cs) { this.children = cs; }
  prepend(...cs) { this.children.unshift(...cs); }
  insertBefore(node) { this.children.push(node); return node; }
  addEventListener(evt, fn) { (this.handlers[evt] ||= []).push(fn); }
  removeEventListener() {}
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; }
  hasAttribute(k) { return k in this.attributes; }
  removeAttribute(k) { delete this.attributes[k]; }
  remove() {}
  querySelector(sel) {
    const m = String(sel).match(/^\.([\w-]+)$/);
    if (!m) return null;
    const cls = m[1];
    const find = (node) => {
      for (const c of node.children || []) {
        if ((c.className || '').split(/\s+/).includes(cls)) return c;
        const r = find(c);
        if (r) return r;
      }
      return null;
    };
    return find(this);
  }
  querySelectorAll() { return []; }
  get classList() {
    const self = this;
    return {
      add(...c) { for (const x of c) if (!self.className.split(/\s+/).includes(x)) self.className = (self.className + ' ' + x).trim(); },
      remove(...c) { self.className = self.className.split(/\s+/).filter(x => !c.includes(x)).join(' '); },
      toggle() {},
      contains(c) { return self.className.split(/\s+/).includes(c); },
    };
  }
}

function makeUniversal() {
  const target = function () {};
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

const REGISTRY_IDS = [
  'context-meter', 'context-ring', 'context-ring-fill', 'context-meter-text',
  'context-meter-value', 'context-compact-button', 'context-status', 'context-breakdown',
  'kb-count', 'kb-nav-count', 'kb-list', 'kb-status', 'kb-empty',
];

function loadApp() {
  const code = fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8');
  const els = {};
  for (const id of REGISTRY_IDS) els[id] = new FakeEl(id === 'context-meter' ? 'div' : 'span');
  const appDocument = {
    createElement: (tag) => new FakeEl(tag),
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
    getElementById: (id) => els[id] || makeUniversal(),
    querySelector: (sel) => {
      const m = String(sel).match(/^#([\w-]+)$/);
      if (m && els[m[1]]) return els[m[1]];
      return makeUniversal();
    },
    querySelectorAll: () => [],
    addEventListener: () => {},
    body: makeUniversal(),
    documentElement: makeUniversal(),
  };
  const context = baseGlobals({ document: appDocument });
  vm.createContext(context);
  vm.runInContext(code, context, { filename: 'app.js', timeout: 4000 });
  return { context, els };
}

function findButton(node, acc = null) {
  for (const c of node.children || []) {
    if (c && c.tagName === 'BUTTON') return c;
    const r = findButton(c);
    if (r) return r;
  }
  return acc;
}

describe('spec-036 task-03 上下文模块始终可见 + KB 计数加载态', () => {
  test('C：无会话 renderContextUsage(null) 模块可见且非 0% 占位', () => {
    const { context, els } = loadApp();
    context.renderContextUsage(null);
    assert.ok(!els['context-meter'].classList.contains('is-idle'), '不得带 is-idle（否则 visibility:hidden）');
    assert.ok(!els['context-meter'].className.includes('is-idle'), 'className 不得含 is-idle');
    assert.notEqual(els['context-meter-value'].textContent, '0%', '无会话不得显示 0% 占位');
    assert.equal(els['context-meter-value'].textContent, '—', '无会话应显示「—」表达尚未取得占比');
  });

  test('D：有数据 renderContextUsage 显示真实百分比（基线非 0%）', () => {
    const { context, els } = loadApp();
    // 恒定上下文基线：used_tokens>0、ratio 由后端算出（此处模拟空历史会话的基线）。
    context.renderContextUsage({ ratio: 0.05, used_tokens: 5000, budget_tokens: 100000, breakdown: [] });
    assert.equal(els['context-meter-value'].textContent, '5%', '应显示真实百分比');
    assert.ok(!els['context-meter'].classList.contains('is-idle'), '有数据时不得隐藏');
  });

  test('E：加载中 showContextUsageLoading 为 is-loading + 「加载中」+ spinner', () => {
    const { context, els } = loadApp();
    context.showContextUsageLoading();
    assert.ok(els['context-meter'].classList.contains('is-loading'), '应进入 is-loading');
    assert.equal(els['context-meter-value'].textContent, '加载中', '文案应为「加载中」');
    assert.ok(els['context-meter'].querySelector('.async-slot-spinner'), '应插入 spinner');
  });

  test('F：失败 renderContextUsageError 显示「—」+ 重试按钮', () => {
    const { context, els } = loadApp();
    context.renderContextUsageError();
    assert.equal(els['context-meter-value'].textContent, '—', '失败值应为「—」');
    const retry = findButton(els['context-status']);
    assert.ok(retry, 'context-status 内应有重试按钮');
    assert.equal(retry.textContent, '重试');
  });

  test('G：KB 首屏加载态 showKbCountLoading 非硬编码 0 + spinner', () => {
    const { context, els } = loadApp();
    context.showKbCountLoading();
    for (const id of ['kb-count', 'kb-nav-count']) {
      assert.ok(els[id].classList.contains('is-loading'), `${id} 应进入加载态`);
      assert.ok(els[id].querySelector('.async-slot-spinner'), `${id} 应有 spinner`);
      assert.notEqual(els[id].textContent, '0', `${id} 不得硬编码 0`);
    }
  });

  test('H：KB 数据到达 setKbCountBadge 淡入真实数字', () => {
    const { context, els } = loadApp();
    context.setKbCountBadge(7);
    assert.equal(els['kb-count'].textContent, '7', 'kb-count 应为真实条数');
    assert.equal(els['kb-nav-count'].textContent, '7', 'kb-nav-count 应为真实条数');
    assert.ok(els['kb-count'].classList.contains('model-count-fade'), '应复用 model-count-fade 淡入');
  });

  test('I：KB 失败 showKbCountError 显示「!」+ 重试按钮', () => {
    const { context, els } = loadApp();
    context.showKbCountError(() => {});
    const bang = els['kb-count'].children.find((c) => c && c.nodeType === 3 && c.textContent === '!');
    assert.ok(bang, 'kb-count 应显示「!」');
    const retry = findButton(els['kb-count']);
    assert.ok(retry, 'kb-count 内应有重试按钮');
    assert.equal(retry.textContent, '重试');
  });

  test('K：index.html 契约 — 无 is-idle 隐藏、kb-count 初始非硬编码 0', () => {
    const html = fs.readFileSync(INDEX_HTML, 'utf8');
    assert.ok(!/class="composer-context is-idle"/.test(html), '#context-meter 不得再带 is-idle');
    assert.ok(!/<span id="kb-count">0<\/span>/.test(html), '#kb-count 初始不得硬编码 0');
    assert.ok(!/<span[^>]*id="kb-nav-count">0<\/span>/.test(html), '#kb-nav-count 初始不得硬编码 0');
  });
});
