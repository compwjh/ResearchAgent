// 契约测试：spec-036 task-05 —— 侧边栏「本地工作区」三点菜单改真按钮
// 零依赖：Node 内置 vm + 轻量假 DOM，直接加载真实源码 app.js / index.html。
// 锁定不变量：
//   1) index.html 中该元素必须是 <button>，不再是死的 <span class="more">。
//   2) 按钮带 aria-haspopup="menu"、初始 aria-expanded="false"、aria-label="本地工作区选项"。
//   3) 行为：点击按钮后 aria-expanded 翻转为 "true"（菜单展开）。
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
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
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
  'model-label', 'profile-menu-button',
];

function loadApp() {
  const code = fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8');
  const els = {};
  for (const id of REGISTRY_IDS) els[id] = new FakeEl(id === 'profile-menu-button' ? 'button' : 'span');
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

// 从原始 HTML 中按 id 抽取某个开始标签，返回其属性片段（不含闭合）。
function extractTagById(html, id) {
  const re = new RegExp(`<([a-zA-Z0-9]+)\\b([^>]*?\\bid="${id}"[^>]*)>`, 'g');
  const m = re.exec(html);
  if (!m) return null;
  return { tag: m[1].toLowerCase(), attrs: m[2] };
}

function hasAttr(attrs, name, value) {
  const re = new RegExp(`\\b${name}="${value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`);
  return re.test(attrs);
}

const html = fs.readFileSync(INDEX_HTML, 'utf8');

describe('spec-036 task-05 侧边栏三点菜单 = 真按钮（DOM 契约）', () => {
  test('A：#profile-menu-button 必须是 <button>，且不再是死的 <span class="more">', () => {
    const dead = extractTagById(html, 'profile-menu-button');
    assert.ok(dead, 'index.html 应存在 id="profile-menu-button" 的元素');
    assert.equal(dead.tag, 'button', '该元素必须是 <button>，而不是 <span>');
    // 反向锁定：旧的装饰 span 必须消失。
    assert.ok(!/<span\b[^>]*\bclass="more"/.test(html), '旧的 <span class="more"> 应已被移除');
  });

  test('B：按钮带 aria-haspopup="menu"、初始 aria-expanded="false"、aria-label="本地工作区选项"、type="button"', () => {
    const btn = extractTagById(html, 'profile-menu-button');
    assert.ok(btn, '应存在 #profile-menu-button');
    assert.ok(hasAttr(btn.attrs, 'aria-haspopup', 'menu'), '必须带 aria-haspopup="menu"');
    assert.ok(hasAttr(btn.attrs, 'aria-expanded', 'false'), '初始必须带 aria-expanded="false"');
    assert.ok(hasAttr(btn.attrs, 'aria-label', '本地工作区选项'), '必须带 aria-label="本地工作区选项"');
    assert.ok(hasAttr(btn.attrs, 'type', 'button'), '必须是 type="button"');
    assert.ok(/\bclass="[^"]*\bmore\b/.test(btn.attrs) && /\bclass="[^"]*\bicon-button\b/.test(btn.attrs), '应保留 .more 与 .icon-button 样式契约');
  });
});

describe('spec-036 task-05 点击展开菜单（行为契约）', () => {
  test('C：点击 #profile-menu-button 后 aria-expanded 翻转为 "true"', () => {
    const { els } = loadApp();
    const btn = els['profile-menu-button'];
    // 假 DOM 不解析 index.html，这里播种 HTML 初始态 aria-expanded="false"（由测试 A/B 锁定）。
    btn.setAttribute('aria-expanded', 'false');
    const clickHandlers = btn.handlers.click || [];
    assert.ok(clickHandlers.length >= 1, '按钮应绑定 click 处理（展开菜单）');
    const event = { stopPropagation() {} };
    for (const h of clickHandlers) h(event);
    assert.equal(btn.getAttribute('aria-expanded'), 'true', '点击后 aria-expanded 应翻转为 true（菜单展开）');
  });
});
