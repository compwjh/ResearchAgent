// 契约测试：spec-036 task-06（前端）—— v2 重建失败态中文文案 + 显式「重试」入口
// 零依赖：Node 内置 vm + 轻量假 DOM，直接加载真实源码 app.js。
// 锁定不变量（前端不可回归）：
//   1) 失败态主文案不得出现后端原始错误码 INDEX_FINALIZE_REQUIRED（仅可保留在 title/日志调试）。
//   2) 失败态必须存在显式「重试」入口（复用既有 .kb-item-rebuild 按钮，失败态标签为「重试」）。
//   3) 失败态渲染中文可读的失败说明（.kb-item-error），引导用户重试。
//   4) 原始错误码仍需保留在 item.title（调试信息不丢）。
//   5) 非失败态不渲染 .kb-item-error，按钮仍标「重建索引」（不回归既有行为）。
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const FRONTEND = path.resolve(import.meta.dirname, '..');
const INDEX = fs.readFileSync(path.join(FRONTEND, 'index.html'), 'utf8');

// ---- 轻量假 DOM（与 context-meter-and-kb-count.test.mjs 同源，自包含）----
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
  'kb-list', 'kb-status', 'kb-empty', 'kb-count', 'kb-nav-count',
];

function loadApp(extra = {}) {
  const code = fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8');
  const els = {};
  for (const id of REGISTRY_IDS) els[id] = new FakeEl('span');
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
  const context = baseGlobals({ document: appDocument, ...extra });
  vm.createContext(context);
  vm.runInContext(code, context, { filename: 'app.js', timeout: 4000 });
  return { context, els };
}

// 递归收集节点（含子节点）的全部可见文本。
function collectText(node, acc = []) {
  if (!node) return acc;
  if (typeof node.textContent === 'string' && node.textContent) acc.push(node.textContent);
  for (const c of node.children || []) collectText(c, acc);
  return acc;
}

// 递归查找第一个带指定 class 的节点。
function findByClass(node, cls, acc = null) {
  if (!node || acc) return acc;
  if ((node.className || '').split(/\s+/).includes(cls)) return node;
  for (const c of node.children || []) {
    const r = findByClass(c, cls);
    if (r) return r;
  }
  return acc;
}

// 递归查找第一个 button（或指定文本）的节点。
function findButton(node, text = null, acc = null) {
  if (!node) return acc;
  if (node.tagName === 'BUTTON' && (text === null || node.textContent === text)) return node;
  for (const c of node.children || []) {
    const r = findButton(c, text);
    if (r) return r;
  }
  return acc;
}

function response(status, payload, { jsonError = false } = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async json() {
      if (jsonError) throw new Error('malformed JSON');
      return payload;
    },
  };
}

function canonicalPaper(overrides = {}) {
  return {
    document_id: 'd4dfd2a620384ad5bece27320661f8f0',
    file_name: 'How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf',
    page_count: 12,
    status: 'indexed',
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 107 },
      v2: { status: 'indexed', progress: 100, chunk_count: 308 },
    },
    ...overrides,
  };
}

function partialPaper(overrides = {}) {
  return canonicalPaper({
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 107 },
      v2: {
        status: 'indexed_partial',
        progress: 100,
        chunk_count: 297,
        error: '部分切片无法精确定位原文：SOURCE_RANGE_UNRESOLVED',
      },
    },
    ...overrides,
  });
}

// 故障期遗留的失败文档：paper.error 与 chunker.error 都带原始后端码。
function failedPaper(overrides = {}) {
  return {
    paper_id: 'doc-failed-1',
    file_name: '故障期遗留论文.pdf',
    page_count: 12,
    status: 'failed',
    error: '索引任务异常终止：INDEX_FINALIZE_REQUIRED',
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 8 },
      v2: { status: 'failed', progress: 0, chunk_count: 0, error: '索引任务异常终止：INDEX_FINALIZE_REQUIRED' },
    },
    ...overrides,
  };
}

describe('spec-036 task-06 KB 失败态：中文文案 + 重试入口', () => {
  test('A：失败态主文案不含原始错误码 INDEX_FINALIZE_REQUIRED', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper()]);
    const item = els['kb-list'].children[0];
    assert.ok(item, '应渲染出文档卡片');
    const texts = collectText(item);
    const joined = texts.join(' ');
    assert.ok(!joined.includes('INDEX_FINALIZE_REQUIRED'), `主文案不得含原始码，实际：${joined}`);
    assert.ok(!joined.includes('索引任务异常终止'), `主文案不得含原始错误描述，实际：${joined}`);
  });

  test('B：失败态存在显式「重试」入口（复用 .kb-item-rebuild 按钮）', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper()]);
    const item = els['kb-list'].children[0];
    const retry = findButton(item, '重试');
    assert.ok(retry, '失败卡片应存在文本为「重试」的按钮');
    assert.ok((retry.className || '').includes('kb-item-rebuild'), '重试按钮应复用既有 .kb-item-rebuild 类');
  });

  test('C：失败态渲染中文可读的失败说明（.kb-item-error）', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper()]);
    const item = els['kb-list'].children[0];
    const notice = findByClass(item, 'kb-item-error');
    assert.ok(notice, '失败卡片应渲染 .kb-item-error 失败说明');
    assert.ok(notice.textContent.includes('重试'), `失败说明应引导重试，实际：${notice.textContent}`);
    assert.ok(!notice.textContent.includes('INDEX_FINALIZE_REQUIRED'), '失败说明不得暴露原始码');
  });

  test('D：失败态加 status-failed 红框类（DOM 契约保留）', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper()]);
    const item = els['kb-list'].children[0];
    assert.ok((item.className || '').includes('status-failed'), '失败卡片应带 status-failed 类');
  });

  test('E：原始错误码保留在 item.title（调试信息不丢）', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper()]);
    const item = els['kb-list'].children[0];
    assert.equal(item.title, '索引任务异常终止：INDEX_FINALIZE_REQUIRED', '原始码应保留在 title 供调试');
  });

  test('F：非失败态不渲染 .kb-item-error，按钮仍标「重建索引」', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper({ status: 'indexed', error: null, chunkers: { v1: { status: 'indexed', progress: 100, chunk_count: 8 }, v2: { status: 'indexed', progress: 100, chunk_count: 9 } } })]);
    const item = els['kb-list'].children[0];
    assert.ok(!findByClass(item, 'kb-item-error'), '非失败态不得渲染失败说明');
    const rebuild = findButton(item, '重建索引');
    assert.ok(rebuild, '非失败态按钮应仍为「重建索引」');
  });

  test('G：文档级未 failed 但某版本 chunker failed 时仍判定失败（边界）', () => {
    const { context, els } = loadApp();
    context.renderKbPapers([failedPaper({ status: 'indexed', error: null, chunkers: { v1: { status: 'indexed', progress: 100, chunk_count: 8 }, v2: { status: 'failed', progress: 0, chunk_count: 0, error: '索引任务异常终止：INDEX_FINALIZE_REQUIRED' } } })]);
    const item = els['kb-list'].children[0];
    assert.ok((item.className || '').includes('status-failed'), '任一 chunker failed 仍应带 status-failed');
    assert.ok(findButton(item, '重试'), '任一 chunker failed 仍应提供「重试」入口');
    assert.ok(findByClass(item, 'kb-item-error'), '任一 chunker failed 仍应渲染失败说明');
  });
});

describe('KB canonical 重建入口', () => {
  test('production KB markup loads the current app bundle and exposes the status/list targets', () => {
    assert.match(INDEX, /id="kb-status"/);
    assert.match(INDEX, /id="kb-list"/);
    assert.match(INDEX, /src="\/assets\/app\.js\?v=62"/);
  });

  test('canonical-only DTO submits one all-chunker request to the document endpoint', async () => {
    const requests = [];
    const paper = canonicalPaper();
    const { context, els } = loadApp({
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        if (options.method === 'POST') {
          return response(202, { task_id: 'task-kb-1', document_id: paper.document_id, chunker: 'all', status: 'queued', progress: 0 });
        }
        return response(200, { papers: [paper] });
      },
    });
    context.renderKbPapers([paper]);
    const button = findButton(els['kb-list'].children[0], '重建索引');
    await button.handlers.click[0]();

    const submitted = requests.filter(({ options }) => options.method === 'POST');
    assert.equal(submitted.length, 1);
    assert.equal(submitted[0].url, `/api/kb/documents/${paper.document_id}/reindex`);
    assert.deepEqual(JSON.parse(submitted[0].options.body), { chunker: 'all' });
    assert.ok(els['kb-status'].textContent.includes('已提交重建'), '202 应显示排队成功提示');
  });

  test('only 202 with a non-empty task_id is a successful queued response', async () => {
    const scenarios = [
      ['202 missing task_id', response(202, { document_id: 'd4dfd2a620384ad5bece27320661f8f0', chunker: 'all', status: 'queued' })],
      ['200 with task_id', response(200, { task_id: 'task-wrong-status', document_id: 'd4dfd2a620384ad5bece27320661f8f0', chunker: 'all', status: 'queued' })],
      ['204 empty body', response(204, null)],
      ['202 malformed JSON', response(202, null, { jsonError: true })],
    ];
    for (const [label, postResponse] of scenarios) {
      const paper = canonicalPaper();
      const { context, els } = loadApp({
        queueMicrotask: () => {},
        fetch: async (_url, options = {}) => options.method === 'POST'
          ? postResponse
          : response(200, { papers: [paper] }),
      });
      context.renderKbPapers([paper]);
      await findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();

      assert.ok(!els['kb-status'].textContent.includes('已提交重建'), `${label} 不得显示成功排队`);
      assert.ok(els['kb-status'].textContent.startsWith('重建失败：'), `${label} 应显示失败提示`);
    }
  });

  test('legacy paper_id DTO falls back to the canonical document endpoint', async () => {
    const requests = [];
    const paper = canonicalPaper({ document_id: undefined, paper_id: 'legacy-document-id' });
    const { context, els } = loadApp({
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        return options.method === 'POST'
          ? response(202, { task_id: 'task-legacy', document_id: paper.paper_id, chunker: 'all', status: 'queued' })
          : response(200, { papers: [paper] });
      },
    });
    context.renderKbPapers([paper]);
    await findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();

    const submitted = requests.filter(({ options }) => options.method === 'POST');
    assert.equal(submitted.length, 1);
    assert.equal(submitted[0].url, '/api/kb/documents/legacy-document-id/reindex');
  });

  test('missing document identity does not submit a request', async () => {
    const requests = [];
    const paper = canonicalPaper({ document_id: '', paper_id: '' });
    const { context, els } = loadApp({
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        return response(200, { papers: [paper] });
      },
    });
    context.renderKbPapers([paper]);
    await findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();

    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 0, '缺少稳定 ID 时不得发出 POST');
    assert.ok(els['kb-status'].textContent.includes('未提交请求'));
  });

  test('structured already-running 409 is shown as actionable busy state, not success', async () => {
    const requests = [];
    const paper = canonicalPaper();
    const { context, els } = loadApp({
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        return options.method === 'POST'
          ? response(409, { error_code: 'INDEX_ALREADY_RUNNING', message: '文档已有索引任务运行中', status: 'running', progress: 0 })
          : response(200, { papers: [paper] });
      },
    });
    context.renderKbPapers([paper]);
    await findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();

    assert.equal(els['kb-status'].textContent, '重建进行中：已有索引任务正在运行，请稍后查看进度');
    assert.ok(!els['kb-status'].textContent.includes('已提交重建'));
    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 1);
  });

  test('structured service error uses canonical message and never renders undefined', async () => {
    const paper = canonicalPaper();
    const { context, els } = loadApp({
      fetch: async (_url, options = {}) => options.method === 'POST'
        ? response(503, { error_code: 'QDRANT_UNAVAILABLE', message: '索引任务暂时无法启动', retryable: true })
        : response(200, { papers: [paper] }),
    });
    context.renderKbPapers([paper]);
    await findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();

    assert.equal(els['kb-status'].textContent, '重建失败：索引任务暂时无法启动');
    assert.ok(!els['kb-status'].textContent.includes('undefined'));
    assert.ok(!els['kb-status'].textContent.includes('已提交重建'));
  });

  test('concurrent clicks on one rebuild button produce one POST', async () => {
    const requests = [];
    const paper = canonicalPaper();
    let releasePost;
    const postResponse = new Promise((resolve) => { releasePost = resolve; });
    const { context, els } = loadApp({
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        return options.method === 'POST' ? postResponse : response(200, { papers: [paper] });
      },
    });
    context.renderKbPapers([paper]);
    const handler = findButton(els['kb-list'].children[0], '重建索引').handlers.click[0];
    const first = handler();
    const second = handler();
    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 1);
    releasePost(response(202, { task_id: 'task-concurrent', document_id: paper.document_id, chunker: 'all', status: 'queued' }));
    await Promise.all([first, second]);
  });

  test('document lock survives list re-render and blocks a new button for the same ID', async () => {
    const requests = [];
    const paper = canonicalPaper();
    let releasePost;
    const postResponse = new Promise((resolve) => { releasePost = resolve; });
    const { context, els } = loadApp({
      queueMicrotask: () => {},
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        return options.method === 'POST' ? postResponse : response(200, { papers: [paper] });
      },
    });
    context.renderKbPapers([paper]);
    const firstButton = findButton(els['kb-list'].children[0], '重建索引');
    const first = firstButton.handlers.click[0]();
    context.renderKbPapers([paper]);
    const replacementButton = findButton(els['kb-list'].children[0], '重建索引');
    const second = replacementButton.handlers.click[0]();

    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 1, '重绘后的新按钮仍应被同文档锁阻止');
    releasePost(response(202, { task_id: 'task-rerender', document_id: paper.document_id, chunker: 'all', status: 'queued' }));
    await Promise.all([first, second]);
  });

  test('document lock releases after failure so a later retry can submit', async () => {
    const requests = [];
    const paper = canonicalPaper();
    let releaseFirst;
    const firstResponse = new Promise((resolve) => { releaseFirst = resolve; });
    let postCount = 0;
    const { context, els } = loadApp({
      queueMicrotask: () => {},
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        if (options.method !== 'POST') return response(200, { papers: [paper] });
        postCount += 1;
        return postCount === 1
          ? firstResponse
          : response(202, { task_id: 'task-retry', document_id: paper.document_id, chunker: 'all', status: 'queued' });
      },
    });
    context.renderKbPapers([paper]);
    const first = findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();
    context.renderKbPapers([paper]);
    const blocked = findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();
    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 1);

    releaseFirst(response(503, { error_code: 'QDRANT_UNAVAILABLE', message: '索引任务暂时无法启动', retryable: true }));
    await Promise.all([first, blocked]);
    const retry = findButton(els['kb-list'].children[0], '重建索引');
    await retry.handlers.click[0]();

    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 2, '失败释放锁后，后续重试应可提交');
    assert.ok(els['kb-status'].textContent.includes('已提交重建'));
  });

  test('different document IDs do not share the in-flight lock', async () => {
    const requests = [];
    const firstPaper = canonicalPaper();
    const secondPaper = canonicalPaper({ document_id: 'other-document-id', file_name: 'other.pdf' });
    let releaseFirst;
    let releaseSecond;
    const firstResponse = new Promise((resolve) => { releaseFirst = resolve; });
    const secondResponse = new Promise((resolve) => { releaseSecond = resolve; });
    let postCount = 0;
    const { context, els } = loadApp({
      queueMicrotask: () => {},
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        if (options.method !== 'POST') return response(200, { papers: [firstPaper, secondPaper] });
        postCount += 1;
        return postCount === 1 ? firstResponse : secondResponse;
      },
    });
    context.renderKbPapers([firstPaper, secondPaper]);
    const first = findButton(els['kb-list'].children[0], '重建索引').handlers.click[0]();
    const second = findButton(els['kb-list'].children[1], '重建索引').handlers.click[0]();
    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 2);
    releaseFirst(response(202, { task_id: 'task-first', document_id: firstPaper.document_id, chunker: 'all', status: 'queued' }));
    releaseSecond(response(202, { task_id: 'task-second', document_id: secondPaper.document_id, chunker: 'all', status: 'queued' }));
    await Promise.all([first, second]);
  });
});

describe('KB indexed_partial reindex feedback', () => {
  test('real partial DTO keeps v1 ready, v2 partial reason, and does not look failed or fully successful', () => {
    const requests = [];
    const paper = partialPaper();
    const { context, els } = loadApp({
      fetch: async (url, options = {}) => {
        requests.push({ url, options });
        return response(200, { papers: [paper] });
      },
    });

    context.renderKbPapers([paper]);

    const item = els['kb-list'].children[0];
    assert.ok(item, '应渲染出部分索引文档卡片');
    assert.ok((item.className || '').includes('status-indexed_partial'), '部分索引卡片应带 scoped partial 警示类');
    assert.ok(!(item.className || '').includes('status-failed'), '合法 partial 不得被误判为失败');
    assert.equal(findByClass(item, 'kb-item-meta').textContent, '已索引 · 12 页', '顶层 indexed metadata 不得被版本 partial 覆盖');
    const texts = collectText(item);
    const joined = texts.join(' ');
    assert.ok(joined.includes('v1 已索引 · 107 片段'), `v1 ready 状态必须保留，实际：${joined}`);
    assert.ok(joined.includes('v2 部分索引 · 297 片段'), `v2 partial 状态必须保留，实际：${joined}`);
    const warning = findByClass(item, 'kb-item-warning');
    assert.ok(warning, 'partial 文档应有可见中文说明');
    assert.ok(warning.textContent.includes('部分切片无法精确定位原文'), `应解释合法 partial 原因，实际：${warning.textContent}`);
    assert.ok(warning.textContent.includes('已保留可用索引'), `应说明可用索引已保留，实际：${warning.textContent}`);
    assert.ok(warning.textContent.includes('可进入切片检查'), `应提供切片检查入口提示，实际：${warning.textContent}`);
    assert.ok(!warning.textContent.includes('索引失败'), 'partial 说明不得称为失败');
    assert.ok(!warning.textContent.includes('全部成功'), 'partial 说明不得宣称全量成功');
    assert.ok(!joined.includes('SOURCE_RANGE_UNRESOLVED'), 'partial 原始原因码不得作为主文案呈现');
    assert.equal(item.title, paper.chunkers.v2.error, 'partial 原因应保留在卡片 title 供诊断');
    assert.equal(requests.filter(({ options }) => options.method === 'POST').length, 0, '仅渲染真实 DTO 不得额外发起 reindex POST');
  });
});
