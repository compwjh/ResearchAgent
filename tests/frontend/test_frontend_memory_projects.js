'use strict';

/**
 * 任务 D：记忆治理「项目记忆列表」行为探针（执行级，node:vm）。
 *
 * 从 frontend/app.js 原样摘出 renderMemoryProjectDocuments() 放进沙箱执行，
 * 用最小 DOM 桩断言：
 *   1. 所有 active 项目一次性全部列出（不做逐个手选、不按 projectId 截断）。
 *   2. 每条渲染项目名/文档名/更新时间/内容简版/revision/字数。
 *   3. 内容简版用 .clamp-3 + withTooltip 悬浮全文（textContent 逐字，不 innerHTML）。
 *   4. 点击某条 → 调 switchMemoryDocument('project', projectId) 打开既有编辑器。
 *   5. 空列表 → 显示「暂无项目记忆」；错误 → 显示可诊断状态文本。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const FRONTEND = path.resolve(__dirname, '../../frontend');
const APP = fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8');

function sliceFunction(source, name) {
  const marker = new RegExp('function\\s+' + name + '\\s*\\(');
  const found = marker.exec(source);
  assert.ok(found, `app.js 必须定义函数 ${name}`);
  const brace = source.indexOf('{', found.index);
  let depth = 0;
  for (let i = brace; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(found.index, i + 1);
    }
  }
  throw new Error(`unbalanced braces while slicing ${name}`);
}

function makeEl(tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    title: '',
    type: '',
    hidden: false,
    dataset: {},
    attributes: new Map(),
    listeners: new Map(),
    append(...nodes) { this.children.push(...nodes); },
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; },
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    },
    focus() {},
  };
  return node;
}

// 递归收集某节点树里所有含指定 class 的节点。
function collectByClass(node, cls, out = []) {
  if (node && typeof node === 'object') {
    if (String(node.className || '').split(/\s+/).includes(cls)) out.push(node);
    (node.children || []).forEach((child) => collectByClass(child, cls, out));
  }
  return out;
}

function makeSandbox() {
  const list = makeEl('ul');
  const empty = makeEl('p');
  const status = makeEl('p');
  const calls = [];
  const sandbox = {
    memoryProjectDocumentsList: list,
    memoryProjectDocumentsEmpty: empty,
    memoryProjectDocumentsStatus: status,
    memoryProjectDocumentsState: { items: [], loading: false, loaded: true, error: '' },
    formatShortHash: (value, n = 8) => {
      const text = value == null ? '' : String(value);
      return text.length > n ? `${text.slice(0, n)}…` : text;
    },
    withTooltip: (el, fullText) => {
      if (!el) return el;
      el.title = String(fullText == null ? '' : fullText);
      if (typeof el.setAttribute === 'function') el.setAttribute('aria-label', el.title);
      return el;
    },
    switchMemoryDocument: (scope, projectId) => calls.push({ scope, projectId }),
    document: { createElement: (tag) => makeEl(tag) },
    String, Number, Array, Boolean, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      sliceFunction(APP, 'renderMemoryProjectDocuments'),
      'this.__render = renderMemoryProjectDocuments;',
    ].join('\n'),
    sandbox,
  );
  return { sandbox, list, empty, status, calls };
}

const ITEMS = [
  {
    project_id: 'p-alpha', project_name: '项目甲', document: 'projects/p-alpha.md',
    content_excerpt: '- 甲的一条记忆\n- 甲的第二条记忆', content_length: 24,
    revision: 'abcdef0123456789cafebabe', updated_at: '2026-11-09T03:00:00Z',
  },
  {
    project_id: 'p-beta', project_name: '项目乙', document: 'projects/p-beta.md',
    content_excerpt: '', content_length: 0,
    revision: '1234567890abcdef', updated_at: '2026-11-08T12:00:00Z',
  },
  {
    project_id: 'p-gamma', project_name: '项目丙（无 md）', document: 'projects/p-gamma.md',
    content_excerpt: '第三条记忆内容', content_length: 7,
    revision: 'deadbeefdeadbeef', updated_at: '2026-11-07T08:30:00Z',
  },
];

// ---- 1. 所有 active 项目一次性全部列出 ----
{
  const { sandbox, list, empty } = makeSandbox();
  sandbox.memoryProjectDocumentsState.items = ITEMS;
  sandbox.__render();
  const cards = list.children;
  assert.equal(cards.length, 3, '3 个 active 项目必须一次性全部渲染（不逐个手选、不截断）');
  assert.equal(empty.hidden, true, '有数据时隐藏空态');

  // 每条含项目名、文档名、更新时间、内容简版、revision、字数。
  const allText = cards.map((c) => collectByClass(c, 'memory-project-doc-name')[0]?.textContent || '');
  assert.deepEqual(allText, ['项目甲', '项目乙', '项目丙（无 md）'], '项目名逐条渲染');

  const docs = cards.map((c) => collectByClass(c, 'memory-project-doc-file')[0]?.textContent || '');
  assert.deepEqual(docs, ['projects/p-alpha.md', 'projects/p-beta.md', 'projects/p-gamma.md'], '文档名逐条渲染');

  const updated = cards.map((c) => collectByClass(c, 'memory-project-doc-updated')[0]?.textContent || '');
  assert.ok(updated.every((t) => t.includes('2026-11')), '更新时间逐条渲染');

  const excerpts = cards.map((c) => collectByClass(c, 'memory-project-doc-excerpt')[0]);
  assert.ok(excerpts.every(Boolean), '内容简版节点逐条存在');
  assert.ok(excerpts[0].textContent.includes('甲的一条记忆'), '内容简版用 textContent 逐字渲染');
  assert.equal(excerpts[1].textContent, '', '空文档简版为空字符串（不是 undefined/null 字面量）');

  const revisions = cards.map((c) => collectByClass(c, 'memory-project-doc-revision')[0]?.textContent || '');
  assert.ok(revisions[0].includes('…'), 'revision 用 formatShortHash 短码显示');

  const lengths = cards.map((c) => collectByClass(c, 'memory-project-doc-length')[0]?.textContent || '');
  assert.ok(lengths[0].includes('24'), '字数显示 content_length');
}

// ---- 2. 内容简版 .clamp-3 + title 全文（XSS 安全：textContent，不 innerHTML） ----
{
  const { sandbox, list } = makeSandbox();
  const evil = '<img src=x onerror=alert(1)>；安全正文';
  sandbox.memoryProjectDocumentsState.items = [{
    project_id: 'p-x', project_name: 'X', document: 'projects/p-x.md',
    content_excerpt: evil, content_length: evil.length,
    revision: 'ff'.repeat(20), updated_at: '2026-11-09T00:00:00Z',
  }];
  sandbox.__render();
  const excerpt = collectByClass(list, 'memory-project-doc-excerpt')[0];
  assert.ok(excerpt.className.includes('clamp-3'), '内容简版用 .clamp-3 折叠');
  assert.equal(excerpt.textContent, evil, 'content_excerpt 逐字进 textContent（不拼接 HTML）');
  assert.equal(excerpt.title, evil, 'withTooltip 悬浮保留全文');
  assert.ok(!('innerHTML' in excerpt), 'DOM 桩不含 innerHTML：渲染路径不得依赖 innerHTML');
}

// ---- 3. 点击某条 → switchMemoryDocument('project', projectId) ----
{
  const { sandbox, list, calls } = makeSandbox();
  sandbox.memoryProjectDocumentsState.items = ITEMS;
  sandbox.__render();
  const items = list.children;
  const buttons = items.map((li) => collectByClass(li, 'memory-project-doc-open')[0]);
  assert.ok(buttons.every(Boolean), '每条含可点击入口 .memory-project-doc-open');
  buttons[1].listeners.get('click')[0]();
  assert.deepEqual(calls, [{ scope: 'project', projectId: 'p-beta' }],
    '点击项目乙 → switchMemoryDocument(project, p-beta) 打开既有单文档编辑器');
  assert.equal(items[1].dataset.projectId, 'p-beta', '卡片承载 data-project-id');
}

// ---- 4. 空列表 → 「暂无项目记忆」 ----
{
  const { sandbox, list, empty } = makeSandbox();
  sandbox.memoryProjectDocumentsState.items = [];
  sandbox.__render();
  assert.equal(list.children.length, 0, '空列表不渲染卡片');
  assert.equal(empty.hidden, false, '空列表显示空态');
  assert.equal(empty.textContent, '暂无项目记忆', '空态文案');
}

// ---- 5. 请求失败 → 可诊断错误（不静默） ----
{
  const { sandbox, status, empty } = makeSandbox();
  sandbox.memoryProjectDocumentsState.items = [];
  sandbox.memoryProjectDocumentsState.error = '项目记忆加载失败：请求失败（503）';
  sandbox.__render();
  assert.ok(status.textContent.includes('失败'), '状态区显示可诊断失败文案');
  assert.ok(status.textContent.includes('503'), '失败文案含可诊断信息（状态码/错误体）');
  assert.equal(status.getAttribute('data-state'), 'error', '失败态 data-state=error');
  assert.equal(empty.hidden, true, '错误时空态不误导为「无数据」');
}

console.log('memory project documents: PASS (全量列出/字段/clamp-3 悬浮全文/点击接线/空态/可诊断错误)');
