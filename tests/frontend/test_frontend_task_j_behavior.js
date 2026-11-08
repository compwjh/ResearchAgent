'use strict';

/**
 * 任务 J 行为探针（TDD / RED → GREEN）。
 *
 * 由 test_frontend_task_j_contract.py 经 subprocess 驱动；也可直接
 * `node tests/frontend/test_frontend_task_j_behavior.js` 单跑。
 *
 * 全部从**真实源码**执行，不用影子实现：
 *   A. renderMemoryProjectDocuments（node:vm 原样 slice app.js）：后端失败项
 *      available=false / error 显示「该项目记忆不可用」+ data-state=error，
 *      空串 content_excerpt/revision 不渲染「0 字 / 空版本」，其余项目照常全展示；
 *   B. selectTask（require 真模块 + deferred fetch）：A→B 快速切换时 A 的迟到
 *      finally 不得移除 B 的 is-loading 骨架（MEDIUM2）；
 *   C. refreshWorkspace（require 真模块）：外部删除选中任务后清理详情/报告/矩阵/
 *      流并给出空态（MEDIUM3）。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '../..');
const APP = fs.readFileSync(path.join(ROOT, 'frontend/app.js'), 'utf8');

const failures = [];
async function check(name, fn) {
  try {
    await fn();
    console.log(`  ok - ${name}`);
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
    console.log(`  FAIL - ${name}: ${error.message}`);
  }
}

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

// ---- 最小 DOM 桩（含 classList，供 setDetailLoading 观测 is-loading）--------
function makeEl(tag = 'div') {
  const kids = [];
  const classes = new Set();
  return {
    tagName: String(tag).toUpperCase(),
    children: kids,
    childNodes: kids,
    className: '', textContent: '', title: '', type: '', value: '', hidden: false,
    dataset: {}, attributes: new Map(), listeners: new Map(),
    classList: {
      add(c) { classes.add(c); },
      remove(c) { classes.delete(c); },
      contains(c) { return classes.has(c); },
      toggle(c, force) {
        const next = force === undefined ? !classes.has(c) : Boolean(force);
        if (next) classes.add(c); else classes.delete(c);
        return next;
      },
    },
    append(...nodes) { kids.push(...nodes); },
    appendChild(child) { kids.push(child); return child; },
    replaceChildren(...nodes) { kids.length = 0; kids.push(...nodes); },
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; },
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    },
    focus() {},
  };
}

function collectByClass(node, cls, out = []) {
  if (node && typeof node === 'object') {
    if (String(node.className || '').split(/\s+/).includes(cls)) out.push(node);
    (node.children || []).forEach((child) => collectByClass(child, cls, out));
  }
  return out;
}

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
    `${sliceFunction(APP, 'renderMemoryProjectDocuments')}\nthis.__render = renderMemoryProjectDocuments;`,
    sandbox,
  );
  return { sandbox, list, empty, status, calls };
}

const ITEMS = [
  {
    project_id: 'p-ok-a', project_name: '项目甲', document: 'projects/p-ok-a.md',
    content_excerpt: '- 甲的一条记忆\n- 甲的第二条记忆', content_length: 24,
    revision: 'abcdef0123456789cafebabe', updated_at: '2026-11-09T03:00:00Z',
  },
  {
    // 后端任务 G 的失败项：available=false + error，其余字段为空串/0。
    project_id: 'p-fail', project_name: '项目乙（失败）', document: 'projects/p-fail.md',
    available: false, error: 'MEMORY_DOCUMENT_UNAVAILABLE',
    content_excerpt: '', content_length: 0, revision: '', updated_at: '',
  },
  {
    project_id: 'p-ok-b', project_name: '项目丙', document: 'projects/p-ok-b.md',
    content_excerpt: '第三条记忆内容', content_length: 7,
    revision: 'deadbeefdeadbeef', updated_at: '2026-11-07T08:30:00Z',
  },
];

async function main() {
  // ---- A. 项目记忆列表：对接后端新字段 ----
  await check('失败项与正常项全部展示（用户裁决「都展示」）', () => {
    const { sandbox, list } = makeSandbox();
    sandbox.memoryProjectDocumentsState.items = ITEMS;
    sandbox.__render();
    assert.equal(list.children.length, 3, '3 项必须全部渲染，含失败项，不得过滤/截断');
    const names = list.children.map(
      (card) => collectByClass(card, 'memory-project-doc-name')[0]?.textContent || '',
    );
    assert.deepEqual(names, ['项目甲', '项目乙（失败）', '项目丙'], '项目名逐条渲染');
  });

  await check('失败项 data-state=error + 明确「该项目记忆不可用」文案', () => {
    const { sandbox, list } = makeSandbox();
    sandbox.memoryProjectDocumentsState.items = ITEMS;
    sandbox.__render();
    const fail = list.children[1];
    assert.equal(fail.getAttribute('data-state'), 'error', '失败项必须用 data-state=error 强调');
    assert.equal(list.children[0].getAttribute('data-state'), null, '正常项不得误标');
    assert.equal(list.children[2].getAttribute('data-state'), null, '正常项不得误标');
    const excerpt = collectByClass(fail, 'memory-project-doc-excerpt')[0];
    assert.ok(excerpt, '失败项仍渲染简版节点');
    assert.match(String(excerpt.textContent), /该项目记忆不可用/, '失败项显示明确不可用状态');
  });

  await check('空串 content_excerpt / revision 不渲染「0 字 / 空版本」', () => {
    const { sandbox, list } = makeSandbox();
    sandbox.memoryProjectDocumentsState.items = ITEMS;
    sandbox.__render();
    const fail = list.children[1];
    const length = collectByClass(fail, 'memory-project-doc-length')[0];
    assert.ok(length, '失败项仍渲染字数字段节点');
    assert.ok(!/0\s*字/.test(String(length.textContent)), `不得显示误导性的「0 字」：${length.textContent}`);
    const revision = collectByClass(fail, 'memory-project-doc-revision')[0];
    assert.ok(revision, '失败项仍渲染版本节点');
    assert.ok(String(revision.textContent).trim().length > 0, '空 revision 不得渲染成空白「空版本」');
  });

  await check('正常项照常渲染字段（回归任务 D 契约，不改已交付逻辑）', () => {
    const { sandbox, list } = makeSandbox();
    sandbox.memoryProjectDocumentsState.items = ITEMS;
    sandbox.__render();
    const okA = list.children[0];
    assert.ok(
      collectByClass(okA, 'memory-project-doc-excerpt')[0].textContent.includes('甲的一条记忆'),
      '正常项简版逐字 textContent',
    );
    assert.ok(
      collectByClass(okA, 'memory-project-doc-revision')[0].textContent.includes('…'),
      '正常项 revision 短码',
    );
    assert.ok(
      collectByClass(okA, 'memory-project-doc-length')[0].textContent.includes('24'),
      '正常项字数',
    );
    const okB = list.children[2];
    assert.ok(
      collectByClass(okB, 'memory-project-doc-length')[0].textContent.includes('7'),
      '正常项丙字数',
    );
  });

  await check('失败项文案走 textContent（XSS 恶意串逐字，DOM 桩不含 innerHTML）', () => {
    const { sandbox, list } = makeSandbox();
    const evil = '<img src=x onerror=alert(1)>';
    sandbox.memoryProjectDocumentsState.items = [{
      project_id: 'p-x', project_name: evil, document: 'projects/p-x.md',
      available: false, error: 'MEMORY_DOCUMENT_UNAVAILABLE',
      content_excerpt: '', content_length: 0, revision: '', updated_at: '',
    }];
    sandbox.__render();
    const name = collectByClass(list, 'memory-project-doc-name')[0];
    assert.equal(name.textContent, evil, '项目名逐字进 textContent');
    assert.ok(!('innerHTML' in name), 'DOM 桩不含 innerHTML：渲染路径不得依赖 innerHTML');
  });

  await check('正常项点击仍接线 switchMemoryDocument(project, id)', () => {
    const { sandbox, list, calls } = makeSandbox();
    sandbox.memoryProjectDocumentsState.items = ITEMS;
    sandbox.__render();
    const buttons = list.children.map((li) => collectByClass(li, 'memory-project-doc-open')[0]);
    assert.ok(buttons.every(Boolean), '每条含可点击入口');
    buttons[0].listeners.get('click')[0]();
    assert.deepEqual(calls, [{ scope: 'project', projectId: 'p-ok-a' }], '点击复用既有编辑器');
  });

  // ---- B/C. require 真模块 + fake DOM + deferred fetch ----
  const detailColumn = makeEl('div');
  const detailEmpty = makeEl('p');
  const idMap = new Map([['research-detail-empty', detailEmpty]]);
  const doc = {
    getElementById: (id) => idMap.get(id) || null,
    createElement: (tag) => makeEl(tag),
    querySelector: () => null,
    querySelectorAll: (sel) => (String(sel).includes('research-detail-column') ? [detailColumn] : []),
    addEventListener() {}, removeEventListener() {},
    body: makeEl('body'),
  };
  // boot() 会因 byId('research-view') === null 提前返回，避免网络副作用。
  globalThis.document = doc;
  globalThis.location = { pathname: '/', search: '', hash: '', href: '' };
  globalThis.history = { replaceState() {}, pushState() {} };
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.dispatchEvent = () => true;
  globalThis.setTimeout = () => 0;
  globalThis.clearTimeout = () => {};
  globalThis.EventSource = class { addEventListener() {} close() {} };
  let fetchImpl = async () => response({});
  globalThis.fetch = (url, options) => fetchImpl(url, options);

  const api = require('../../frontend/research-tasks.js');
  api.state.document = doc;

  // ---- B. MEDIUM2：A→B 快速切换，A 的迟到 finally 不得移除 B 的骨架 ----
  await check('MEDIUM2: A 的迟到 finally 不移除 B 的 is-loading 骨架', async () => {
    api.state.taskGeneration = 0;
    api.state.selectTaskInFlight = null;
    api.state.selectedTaskId = null;
    api.state.selectedSessionId = null;
    api.state.tasks = [];
    api.state.eventSource = null;
    api.state.reconnectTimer = null;
    detailColumn.classList.toggle('is-loading', false);
    const dA = deferred();
    const dB = deferred(); // B 的请求始终挂起：B 一直处于加载骨架态。
    fetchImpl = async (url) => {
      const u = String(url);
      if (u.includes('/research-tasks/task-a')) return dA.promise;
      if (u.includes('/research-tasks/task-b')) return dB.promise;
      return response({});
    };
    const pA = api.selectTask('task-a'); // generation=1
    const pB = api.selectTask('task-b'); // generation=2
    assert.equal(detailColumn.classList.contains('is-loading'), true, 'B 切换期间应显示 is-loading 骨架');
    // A 的迟到响应到达：try 内 generation 守卫提前 return，进入 finally。
    dA.resolve(response({ research_task_id: 'task-a', status: 'completed' }));
    await pA;
    assert.equal(
      detailColumn.classList.contains('is-loading'), true,
      'A 的迟到响应进入 finally 时不得移除 B 的 is-loading 骨架、不得提前算空态',
    );
  });

  // ---- C. MEDIUM3：外部删除选中任务后清理残留并给空态 ----
  await check('MEDIUM3: 外部删除后清理详情/报告/矩阵/流并给出空态', async () => {
    api.state.taskGeneration = 7;
    api.state.selectTaskInFlight = null;
    api.state.selectedTaskId = 'task-gone';
    api.state.selectedSessionId = 'session-gone';
    api.state.selectedTask = { research_task_id: 'task-gone', research_session_id: 'session-gone' };
    api.state.report = { report_version: 1, markdown: '旧报告正文' };
    api.state.matrix = { claims: [], dimensions: [], cells: [] };
    api.state.conversation = null;
    api.state.conversationId = null;
    api.state.tasks = [];
    api.state.reconnectTimer = null;
    let closed = false;
    api.state.eventSource = { close() { closed = true; } };
    detailEmpty.hidden = true;
    fetchImpl = async (url) => {
      const u = String(url);
      // 刷新拿到的列表已不含被外部删除的选中任务。
      if (u.includes('/api/research-sessions?limit=100')) return response({ research_sessions: [] });
      return response({});
    };
    await api.refreshWorkspace();
    assert.equal(api.state.selectedTaskId, null, '清空 selectedTaskId');
    assert.equal(api.state.selectedSessionId, null, '清空 selectedSessionId');
    assert.equal(api.state.report, null, '清理报告');
    assert.equal(api.state.matrix, null, '清理矩阵');
    assert.equal(api.state.eventSource, null, '关闭 SSE 流');
    assert.equal(closed, true, 'closeStream 调用了 eventSource.close()');
    assert.equal(detailEmpty.hidden, false, '给出可见空态（只切 hidden，不整块白屏）');
  });

  if (failures.length) {
    console.error(`\n${failures.length} task J behavior assertion(s) FAILED:\n - ${failures.join('\n - ')}`);
    process.exitCode = 1;
    return;
  }
  console.log('task J behavior: PASS (失败项渲染/都展示/空串不误导/点击接线 + A→B 竞态 + 外部删除清理)');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
