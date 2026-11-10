'use strict';

/**
 * 「选了项目记忆后 MEMORY.md 再也看不到」修复 —— 执行级行为探针（node:vm，真实源码 slice）。
 *
 * 由 test_memory_return_global_contract.py 经 subprocess 驱动；也可直接
 * `node tests/frontend/test_memory_return_global_behavior.js` 单跑。
 *
 * 全部从**真实 app.js 源码**按函数边界切片执行，不用影子实现：
 *   A. memoryDocumentLabelFor：project → 「项目记忆 · <项目名>」，global → 「全局记忆 · MEMORY.md」，
 *      取不到项目名才 fallback 短 ID；绝不出现 `projects/<32位id>.md` 长串。
 *   B. 点击项目记忆条目：补下拉 option、接线 switchMemoryDocument('project', id)，
 *      切换完成后 #memory-status 含「返回全局」且编辑器被 scrollIntoView 滚入视野。
 *   C. 「返回全局 MEMORY.md」：switchMemoryDocument('global', null)、scope='global'、
 *      清 memoryProjectSelect 残留、同步 scope select / project label / back 按钮。
 *   D. 列表默认展开 + 全部 active 项目一次性列出（守住用户裁决）；收起按钮只切换显隐、不减数量。
 *   E. renderMemoryDocument 同步「返回全局」按钮与当前文档标题的显示状态。
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

function sliceFunction(source, name) {
  const marker = new RegExp('(?:function|async function)\\s+' + name + '\\s*\\(');
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

function makeEl(tag = 'div') {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    title: '',
    type: '',
    value: '',
    hidden: false,
    disabled: false,
    dataset: {},
    attributes: new Map(),
    listeners: new Map(),
    scrollCalls: [],
    append(...nodes) { this.children.push(...nodes); },
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren(...nodes) { this.children.length = 0; this.options && (this.options.length = 0); nodes.forEach((n) => this.appendChild(n)); },
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; },
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    },
    scrollIntoView(options) { this.scrollCalls.push(options); },
    focus() {},
  };
  return node;
}

function makeSelect() {
  const el = makeEl('select');
  el.options = [];
  el.appendChild = (child) => {
    el.children.push(child);
    if (child.tagName === 'OPTION') el.options.push(child);
    return child;
  };
  return el;
}

function collectByClass(node, cls, out = []) {
  if (node && typeof node === 'object') {
    if (String(node.className || '').split(/\s+/).includes(cls)) out.push(node);
    (node.children || []).forEach((child) => collectByClass(child, cls, out));
  }
  return out;
}

const ITEMS = [
  {
    project_id: 'p-defi', project_name: 'DeFi', document: 'projects/p-defi.md',
    content_excerpt: '- 关注 AMM 滑点\n- 关注清算', content_length: 18,
    revision: 'abcdef0123456789cafebabe', updated_at: '2026-11-09T03:00:00Z',
  },
  {
    project_id: '001270c0e0a44594b61e58b9713d0063', project_name: '量化研究',
    document: 'projects/001270c0e0a44594b61e58b9713d0063.md',
    content_excerpt: '', content_length: 0,
    revision: '1234567890abcdef', updated_at: '2026-11-08T12:00:00Z',
  },
  {
    project_id: 'p-gamma', project_name: '项目丙（无 md）', document: 'projects/p-gamma.md',
    content_excerpt: '第三条记忆内容', content_length: 7,
    revision: 'deadbeefdeadbeef', updated_at: '2026-11-07T08:30:00Z',
  },
];

const FUNCTIONS = [
  'memoryDocumentLabelFor',
  'renderMemoryProjectDocuments',
  'renderMemoryDocument',
  'ensureMemoryProjectOption',
  'clearMemoryProjectSelection',
  'announceOpenedProjectMemory',
  'scrollMemoryDocumentIntoView',
  'backToGlobalMemoryDocument',
  'toggleMemoryProjectDocuments',
];

function makeSandbox() {
  const calls = [];
  const statusTexts = [];
  const sandbox = {
    // --- 状态 ---
    memoryState: {
      scope: 'global', projectId: null, revision: '', content: '', loaded: true,
      loading: false, saving: false, dirty: false, requestGeneration: 0, requestKey: '',
    },
    memoryProjectDocumentsState: { items: ITEMS.map((it) => ({ ...it })), loading: false, loaded: true, error: '', requestGeneration: 0 },
    projectState: {
      items: [
        { project_id: 'p-defi', name: 'DeFi' },
        { project_id: '001270c0e0a44594b61e58b9713d0063', name: '量化研究' },
        { project_id: 'p-gamma', name: '项目丙（无 md）' },
      ],
    },
    MEMORY_DOCUMENT_LIMIT: 65536,
    // --- DOM 桩 ---
    memoryProjectDocumentsList: makeEl('ul'),
    memoryProjectDocumentsEmpty: makeEl('p'),
    memoryProjectDocumentsStatus: makeEl('p'),
    memoryProjectDocumentsToggle: makeEl('button'),
    memoryDocumentPanel: makeEl('section'),
    memoryDocumentLabel: makeEl('h2'),
    memoryDocumentEditor: makeEl('textarea'),
    memoryDocumentEmpty: makeEl('p'),
    memoryDocumentSaveButton: makeEl('button'),
    memoryDocumentRevision: makeEl('code'),
    memoryDocumentCount: makeEl('span'),
    memoryDocumentConflict: makeEl('section'),
    memoryDocumentConflictCopy: makeEl('pre'),
    memoryScopeSelect: makeSelect(),
    memoryProjectSelect: makeSelect(),
    memoryProjectLabel: makeEl('label'),
    memoryBackToGlobal: makeEl('button'),
    memoryStatus: makeEl('p'),
    // --- 工具桩 ---
    calls,
    statusTexts,
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
    setMemoryStatus: (text, state = '') => {
      statusTexts.push(String(text || ''));
      if (state) sandbox.memoryStatus.dataset.state = state;
      else delete sandbox.memoryStatus.dataset.state;
    },
    setMemoryDocumentRevision: () => {},
    updateMemoryDocumentCount: () => {},
    memoryDocumentDraft: () => String(sandbox.memoryDocumentEditor?.value || ''),
    clearMemoryDocumentConflict: () => {},
    switchMemoryDocument: (scope, projectId) => {
      calls.push({ scope, projectId });
      sandbox.memoryState.scope = scope;
      sandbox.memoryState.projectId = projectId;
      return Promise.resolve();
    },
    requestAnimationFrame: (fn) => { fn(); return 1; },
    document: { createElement: (tag) => makeEl(tag), querySelector: () => null },
    console,
    Promise, String, Number, Array, Boolean, Date, Object,
  };
  vm.createContext(sandbox);
  const sources = FUNCTIONS.map((name) => sliceFunction(APP, name));
  vm.runInContext(
    `${sources.join('\n')}\nthis.__fn = { ${FUNCTIONS.join(', ')} };`,
    sandbox,
  );
  return { sandbox, calls, statusTexts };
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

(async () => {
  // ---- A. 可读标题：项目名而非 32 位 ID / 长路径 ----
  await check('project 标题用项目名「DeFi」，不含 32 位 ID 与 projects/ 长路径', () => {
    const { sandbox } = makeSandbox();
    const label = sandbox.__fn.memoryDocumentLabelFor('project', 'p-defi');
    assert.match(label, /项目记忆/, '标题标明「项目记忆」');
    assert.match(label, /DeFi/, '标题含人类可读项目名');
    assert.doesNotMatch(label, /projects\//, '不再显示 projects/<id>.md 长串');
    assert.doesNotMatch(label, /001270c0e0a44594b61e58b9713d0063/, '不出现 32 位 ID');
  });

  await check('project 长 ID 也能解析出项目名（从 memoryProjectDocumentsState / projectState）', () => {
    const { sandbox } = makeSandbox();
    const longId = '001270c0e0a44594b61e58b9713d0063';
    const label = sandbox.__fn.memoryDocumentLabelFor('project', longId);
    assert.match(label, /量化研究/, '长 ID 仍解析为项目名，不裸露 32 位 ID');
    assert.doesNotMatch(label, new RegExp(longId), '标题不得含完整 32 位 ID');
  });

  await check('取不到项目名才 fallback 短 ID，且绝不出现完整 32 位 ID', () => {
    const { sandbox } = makeSandbox();
    const unknown = 'ffeeddccbbaa99887766554433221100ab';
    const label = sandbox.__fn.memoryDocumentLabelFor('project', unknown);
    assert.doesNotMatch(label, new RegExp(unknown), 'fallback 必须是短码，不能是完整 ID');
    assert.doesNotMatch(label, /projects\//, 'fallback 也不能是 projects/<id>.md');
    assert.match(label, /项目记忆/, 'fallback 仍标明项目记忆');
  });

  await check('global 标题为「全局记忆 · MEMORY.md」', () => {
    const { sandbox } = makeSandbox();
    assert.equal(sandbox.__fn.memoryDocumentLabelFor('global', null), '全局记忆 · MEMORY.md');
  });

  // ---- B. 点击项目条目：接线 + option 补全 + 滚动 + 状态提示 ----
  await check('点击前 option 不存在时补一个 option 再设值（active 列表未加载也不失败）', () => {
    const { sandbox } = makeSandbox();
    sandbox.memoryProjectSelect.options.length = 0;
    sandbox.__fn.ensureMemoryProjectOption('p-defi', 'DeFi');
    assert.equal(sandbox.memoryProjectSelect.options.length, 1, '补了一个 option');
    assert.equal(sandbox.memoryProjectSelect.options[0].value, 'p-defi');
    assert.equal(sandbox.memoryProjectSelect.options[0].textContent, 'DeFi', '项目名进 option.textContent');
    assert.equal(sandbox.memoryProjectSelect.value, 'p-defi', '设值成功');
    sandbox.__fn.ensureMemoryProjectOption('p-defi', 'DeFi');
    assert.equal(sandbox.memoryProjectSelect.options.length, 1, 'option 已存在时不重复添加');
  });

  await check('点击条目 → switchMemoryDocument(project, id) + option 同步 + 标题含项目名', async () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.__fn.renderMemoryProjectDocuments();
    const buttons = sandbox.memoryProjectDocumentsList.children.map(
      (li) => collectByClass(li, 'memory-project-doc-open')[0],
    );
    assert.ok(buttons.every(Boolean), '每条含可点击入口');
    buttons[0].listeners.get('click')[0]();
    await flush();
    assert.deepEqual(calls[0], { scope: 'project', projectId: 'p-defi' }, '复用既有 switchMemoryDocument');
    assert.equal(sandbox.memoryScopeSelect.value, 'project', '作用域下拉同步到 project');
    assert.equal(sandbox.memoryProjectLabel.hidden, false, '项目下拉标签显示');
    assert.equal(sandbox.memoryProjectSelect.value, 'p-defi', '项目下拉值同步');
    assert.equal(sandbox.memoryProjectSelect.options[0].textContent, 'DeFi', '补的 option 用项目名 textContent（非 innerHTML）');
    const label = sandbox.__fn.memoryDocumentLabelFor(sandbox.memoryState.scope, sandbox.memoryState.projectId);
    assert.match(label, /DeFi/, '当前文档标题含项目名');
  });

  await check('切换完成后 #memory-status 明确提示含「返回全局」', async () => {
    const { sandbox, statusTexts } = makeSandbox();
    sandbox.__fn.renderMemoryProjectDocuments();
    const button = collectByClass(sandbox.memoryProjectDocumentsList, 'memory-project-doc-open')[0];
    button.listeners.get('click')[0]();
    await flush();
    const feedback = statusTexts.find((text) => text.includes('返回全局'));
    assert.ok(feedback, '状态提示必须含「返回全局」告知返回路径');
    assert.match(feedback, /DeFi/, '提示含项目名「DeFi」');
    assert.match(feedback, /MEMORY\.md/, '提示点明全局 MEMORY.md');
  });

  await check('切换完成后编辑器被 scrollIntoView({block:"start"}) 滚入视野', async () => {
    const { sandbox } = makeSandbox();
    sandbox.__fn.renderMemoryProjectDocuments();
    const button = collectByClass(sandbox.memoryProjectDocumentsList, 'memory-project-doc-open')[0];
    button.listeners.get('click')[0]();
    await flush();
    assert.ok(sandbox.memoryDocumentPanel.scrollCalls.length >= 1, '编辑器面板必须被滚入视野');
    assert.equal(sandbox.memoryDocumentPanel.scrollCalls[0].block, 'start', '滚动对齐到顶部');
  });

  // ---- C. 返回全局 ----
  await check('「返回全局 MEMORY.md」→ switchMemoryDocument(global,null) + scope/控件/残留全部同步', () => {
    const { sandbox, calls } = makeSandbox();
    // 先模拟处于 project 且下拉残留
    sandbox.memoryState.scope = 'project';
    sandbox.memoryState.projectId = 'p-defi';
    sandbox.memoryScopeSelect.value = 'project';
    sandbox.memoryProjectSelect.value = 'p-defi';
    sandbox.memoryProjectLabel.hidden = false;
    sandbox.memoryBackToGlobal.hidden = false;
    sandbox.__fn.backToGlobalMemoryDocument();
    assert.deepEqual(calls[0], { scope: 'global', projectId: null }, '走既有 switchMemoryDocument(global, null)');
    assert.equal(sandbox.memoryState.scope, 'global', 'memoryState.scope 回到 global');
    assert.equal(sandbox.memoryScopeSelect.value, 'global', '作用域下拉同步 global');
    assert.equal(sandbox.memoryProjectLabel.hidden, true, '项目下拉标签隐藏');
    assert.equal(sandbox.memoryProjectSelect.value, '', '清掉 memoryProjectSelect 残留');
    assert.equal(sandbox.memoryBackToGlobal.hidden, true, '返回按钮自身隐藏（global 无需返回）');
  });

  // ---- D. 用户裁决：默认展开 + 全部 active 项目列出 ----
  await check('列表默认展开、全部 active 项目一次性列出，收起不减少条目', () => {
    const { sandbox } = makeSandbox();
    const list = sandbox.memoryProjectDocumentsList;
    const toggle = sandbox.memoryProjectDocumentsToggle;
    assert.equal(list.hidden, false, '默认展开（list 不 hidden）');
    sandbox.__fn.renderMemoryProjectDocuments();
    assert.equal(list.children.length, 3, '3 个 active 项目一次性全部列出');
    sandbox.__fn.toggleMemoryProjectDocuments();
    assert.equal(list.hidden, true, '点击收起');
    assert.equal(toggle.getAttribute('aria-expanded'), 'false', 'aria-expanded 同步');
    assert.equal(toggle.textContent, '展开列表', '按钮文案切到「展开列表」');
    assert.equal(list.children.length, 3, '收起只是显隐，不删除/减少条目（守用户裁决）');
    sandbox.__fn.toggleMemoryProjectDocuments();
    assert.equal(list.hidden, false, '再点展开');
    assert.equal(toggle.getAttribute('aria-expanded'), 'true', 'aria-expanded 恢复');
    assert.equal(toggle.textContent, '收起列表', '按钮文案恢复');
  });

  // ---- E. renderMemoryDocument 同步返回按钮与标题显示状态 ----
  await check('renderMemoryDocument：project 显示返回按钮+项目名标题，global 隐藏按钮+全局标题', () => {
    const { sandbox } = makeSandbox();
    sandbox.memoryState.scope = 'project';
    sandbox.memoryState.projectId = 'p-defi';
    sandbox.__fn.renderMemoryDocument();
    assert.equal(sandbox.memoryBackToGlobal.hidden, false, 'project 时「返回全局」按钮可见');
    assert.match(sandbox.memoryDocumentLabel.textContent, /DeFi/, '标题显示项目名');
    assert.match(sandbox.memoryDocumentLabel.textContent, /项目记忆/, '标题标明项目记忆');
    sandbox.memoryState.scope = 'global';
    sandbox.memoryState.projectId = null;
    sandbox.__fn.renderMemoryDocument();
    assert.equal(sandbox.memoryBackToGlobal.hidden, true, 'global 时「返回全局」按钮隐藏');
    assert.match(sandbox.memoryDocumentLabel.textContent, /全局记忆/, '标题显示全局记忆');
  });

  if (failures.length) {
    console.error(`\nmemory return-global contract: FAIL (${failures.length})\n${failures.join('\n')}`);
    process.exit(1);
  }
  console.log('\nmemory return-global contract: PASS (可读标题/点击反馈/返回全局/默认展开全量/渲染同步)');
})();
