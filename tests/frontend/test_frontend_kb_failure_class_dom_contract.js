'use strict';

/**
 * 知识库失败/兜底提示的 **CSS class ↔ 真实 DOM** 双向契约（执行级，`node:vm`）。
 *
 * 为什么要有这条用例（Spec012 架构评审 A-9）：
 *   既有 `test_frontend_kb_index_interruption_notice.js` 只断言「JS 逻辑产出了正确文案」，
 *   即 `textOf(item)` 里包含提示字符串。但用户看得见的是**样式**：`app.js:6551` 用
 *   `failure.className = notice.interrupted ? 'kb-item-error kb-item-error-restart' : 'kb-item-error'`
 *   赋值，`app.js:6564` 用 `hint.className = 'kb-item-hint'`。如果哪天有人把这两处 className
 *   改成别名（或误写成 `kb-item-error-restart` 却忘了加 `kb-item-error` 基类、
 *   把 `kb-item-hint` 写成 `kb-item-warning`），**文案断言依然全绿，样式却悄悄失效**。
 *
 *   所以本文件从**渲染出来的 DOM 节点**反向断言 class 存在，并反向核对
 *   `frontend/styles.css` 里确实有对应选择器，压住「CSS 与 DOM 契约单方面漂移」。
 *
 * 复用 `test_frontend_kb_index_interruption_notice.js` 的 node:vm 夹具做法：
 * 从 `frontend/app.js` 原样摘取真实实现到沙箱执行（不复制影子实现），
 * 用最小 DOM 桩（`className` / `textContent` / `appendChild` …）收集渲染结果。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');
const CSS = fs.readFileSync(path.resolve(__dirname, '../../frontend/styles.css'), 'utf8');

const RESTART_REASON = '服务重启导致中断';

// 契约常量：class 名与文案一律写成期望字面量（不从被测算出来再自比）。
const BASE_ERROR_CLASS = 'kb-item-error';
const RESTART_CLASS = 'kb-item-error-restart';
const HINT_CLASS = 'kb-item-hint';
const IDLE_HINT_TEXT = '索引进度长时间停在 0%，如长时间停留可点「重试」';
const RESTART_HINT_TEXT = '上次索引被服务重启中断，可点击「重试」重新建立索引';

// ---- 源码抽取（原样，不复制实现） ----
function slice(signature) {
  const match = APP_JS.match(new RegExp(`(?:async )?function ${signature}[\\s\\S]*?\\n}\\n`));
  assert.ok(match, `app.js 必须定义 ${signature}`);
  return match[0];
}

const kbStatusTextSrc = (() => {
  const match = APP_JS.match(/const KB_STATUS_TEXT = \{[\s\S]*?\n\};\n/);
  assert.ok(match, 'app.js 必须定义 KB_STATUS_TEXT');
  return match[0];
})();

const kbInterruptedSrc = (() => {
  const match = APP_JS.match(/const KB_INTERRUPTED_ERROR_PREFIX[\s\S]*?\nfunction kbFailureNotice[\s\S]*?\n}\n/);
  assert.ok(
    match,
    'app.js 必须定义「服务重启中断」识别与提示函数（KB_INTERRUPTED_ERROR_PREFIX / kbFailureNotice）',
  );
  return match[0];
})();

const chunkerBadgeTextSrc = slice('chunkerBadgeText\\(name, state\\)');
const kbDocumentIdSrc = slice('kbDocumentId\\(paper\\)');
const renderSrc = slice('renderKbPapers\\(papers\\)');

// ---- 最小 DOM 桩（与既有 node:vm 夹具一致，只保留渲染需要的部分） ----
function makeEl(tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    title: '',
    hidden: false,
    tabIndex: 0,
    disabled: false,
    style: {},
    dataset: {},
    attributes: {},
    listeners: {},
    type: '',
    classList: {
      add(name) {
        if (!node.className.split(/\s+/).includes(name)) node.className = `${node.className} ${name}`.trim();
      },
      remove(name) {
        node.className = node.className
          .split(/\s+/)
          .filter((part) => part && part !== name)
          .join(' ');
      },
      contains(name) {
        return node.className.split(/\s+/).includes(name);
      },
    },
    setAttribute(name, value) {
      node.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete node.attributes[name];
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(node.attributes, name) ? node.attributes[name] : null;
    },
    addEventListener(type, handler) {
      node.listeners[type] = handler;
    },
    appendChild(child) {
      node.children.push(child);
      return child;
    },
    append(...items) {
      node.children.push(...items);
    },
    replaceChildren() {
      node.children = [];
    },
    click() {
      return node.listeners.click ? node.listeners.click() : undefined;
    },
  };
  return node;
}

function walk(node, visit) {
  visit(node);
  for (const child of node.children) walk(child, visit);
}

function classesOf(node) {
  return String(node.className || '').split(/\s+/).filter(Boolean);
}

function hasClass(node, className) {
  return classesOf(node).includes(className);
}

/** 返回所有 class 交集包含全部给定 class 的节点（等价于 CSS 复合选择器 `.a.b` 的匹配）。 */
function findAll(root, classNames) {
  const hits = [];
  walk(root, (node) => {
    if (classNames.every((name) => hasClass(node, name))) hits.push(node);
  });
  return hits;
}

function textOf(node) {
  let out = '';
  walk(node, (current) => {
    if (typeof current.textContent === 'string' && current.textContent) out += `${current.textContent}\n`;
  });
  return out;
}

function makeHarness(papers) {
  const kbList = makeEl('ul');
  const calls = { schedule: 0, stop: 0 };

  const sandbox = {
    console,
    kbList,
    kbStatus: makeEl('span'),
    kbEmpty: makeEl('p'),
    setKbCountBadge() {},
    scheduleKbPoll() { calls.schedule += 1; },
    stopKbPoll() { calls.stop += 1; },
    consumePendingKbJump() {},
    showKbCountError() {},
    kbReindexInFlight: new Set(),
    loadKbPapers: async () => true,
    fetch: async () => ({ ok: true, status: 202, json: async () => ({ task_id: 'task-abc' }) }),
    document: {
      createElement(tag) {
        return makeEl(tag);
      },
    },
    Set,
    Number,
    Math,
    String,
    Object,
    Array,
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      kbStatusTextSrc,
      kbInterruptedSrc,
      chunkerBadgeTextSrc,
      kbDocumentIdSrc,
      renderSrc,
      'this.__render = renderKbPapers;',
    ].join('\n'),
    sandbox,
  );
  sandbox.__render(papers);
  return { kbList, calls };
}

function itemAt(harness, index = 0) {
  return harness.kbList.children[index];
}

// ---------------------------------------------------------------------------
// 1. 失败态（重启中断）→ DOM 里必须出现 `.kb-item-error.kb-item-error-restart`
// ---------------------------------------------------------------------------
{
  const paper = {
    document_id: 'doc-restart-dom',
    file_name: 'restarted.pdf',
    status: 'failed',
    page_count: 0,
    error: null,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'failed', progress: 0, chunk_count: 0, error: RESTART_REASON },
    },
  };
  const h = makeHarness([paper]);
  const item = itemAt(h);

  // 1a. 复合选择器 `#kb-view .kb-item-error.kb-item-error-restart` 的 DOM 侧：两 class 必须同一节点。
  const restartNodes = findAll(item, [BASE_ERROR_CLASS, RESTART_CLASS]);
  assert.equal(
    restartNodes.length,
    1,
    `failed 且 error 含「${RESTART_REASON}」时必须渲染恰好 1 个同时带 `
      + `"${BASE_ERROR_CLASS}" 与 "${RESTART_CLASS}" 的节点；实际 item.className 树为：`
      + JSON.stringify(collectClassNames(item)),
  );
  // 1b. 该节点是提示文案载体（style 不会挂到空节点上）。
  assert.equal(
    restartNodes[0].textContent,
    RESTART_HINT_TEXT,
    `.${RESTART_CLASS} 节点必须承载「重启中断」提示文案`,
  );
  // 1c. 反向：这个节点只能有一个，且不属于 hint 分支。
  assert.equal(
    findAll(item, [HINT_CLASS]).length,
    0,
    'failed 卡片不应同时渲染 .kb-item-hint（兜底提示只服务 indexing 未失败态）',
  );
  // 1d. 静态漂移守卫：app.js 里赋值 className 的那一行确实同时给出两个 class。
  assert.ok(
    APP_JS.includes(`failure.className = notice.interrupted ? '${BASE_ERROR_CLASS} ${RESTART_CLASS}' : '${BASE_ERROR_CLASS}'`),
    `app.js 必须以 "${BASE_ERROR_CLASS} ${RESTART_CLASS}" 同时赋两个 class（缺基类会让 `
      + `#kb-view .kb-item-error 的既有样式整体失效）`,
  );
}

// ---------------------------------------------------------------------------
// 2. 普通失败（非重启原因）→ 不得误加 `.kb-item-error-restart`
// ---------------------------------------------------------------------------
{
  const paper = {
    document_id: 'doc-plain-fail-dom',
    file_name: 'plain-fail.pdf',
    status: 'failed',
    page_count: 3,
    error: 'EmbeddingServiceUnavailable',
    chunkers: {
      v1: { status: 'failed', progress: 0, chunk_count: 0, error: 'EmbeddingServiceUnavailable' },
      v2: { status: 'pending', progress: 0, chunk_count: 0, error: null },
    },
  };
  const h = makeHarness([paper]);
  const item = itemAt(h);

  assert.equal(
    findAll(item, [BASE_ERROR_CLASS]).length,
    1,
    '普通失败态必须仍渲染 1 个 .kb-item-error 提示节点',
  );
  assert.equal(
    findAll(item, [RESTART_CLASS]).length,
    0,
    '普通失败（非重启原因）绝不能带 .kb-item-error-restart，否则会给用户误报「被重启打断」的红色色条',
  );
}

// ---------------------------------------------------------------------------
// 3. indexing + progress=0 → DOM 里必须出现 `.kb-item-hint`
// ---------------------------------------------------------------------------
{
  const paper = {
    document_id: 'doc-indexing-dom',
    file_name: 'indexing.pdf',
    status: 'indexed',
    page_count: 0,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'indexing', progress: 0, chunk_count: 0, error: null },
    },
  };
  const h = makeHarness([paper]);
  const item = itemAt(h);

  const hintNodes = findAll(item, [HINT_CLASS]);
  assert.equal(
    hintNodes.length,
    1,
    `indexing 且 progress=0 时必须渲染恰好 1 个 .${HINT_CLASS} 节点；实际 class 名集合为：`
      + JSON.stringify(collectClassNames(item)),
  );
  assert.equal(hintNodes[0].textContent, IDLE_HINT_TEXT, `.${HINT_CLASS} 节点必须承载兜底提示文案`);
  // 兜底提示不是失败态：不得借用失败色条的 class。
  assert.equal(findAll(item, [RESTART_CLASS]).length, 0, 'indexing 兜底提示不是失败态，不得带 .kb-item-error-restart');
  assert.equal(findAll(item, [BASE_ERROR_CLASS]).length, 0, 'indexing 兜底提示不是失败态，不得带 .kb-item-error');
  // 轮询启停逻辑未被本特性改动（indexing 仍在跑）。
  assert.equal(h.calls.schedule, 1, 'indexing 仍在跑 → 必须启动轮询');
}

// ---------------------------------------------------------------------------
// 4. progress>0 的 indexing → 不得渲染 `.kb-item-hint`（不打扰用户）
// ---------------------------------------------------------------------------
{
  const paper = {
    document_id: 'doc-indexing-progress-dom',
    file_name: 'indexing-progress.pdf',
    status: 'indexed',
    page_count: 0,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'indexing', progress: 42, chunk_count: 0, error: null },
    },
  };
  const h = makeHarness([paper]);
  assert.equal(
    findAll(itemAt(h), [HINT_CLASS]).length,
    0,
    'progress>0 说明任务真在跑，不应渲染 .kb-item-hint 兜底提示',
  );
}

// ---------------------------------------------------------------------------
// 5. CSS 侧反向核对：两个选择器在 styles.css 里确有定义（含 #kb-view 作用域前缀）
// ---------------------------------------------------------------------------
for (const selector of [
  `#kb-view .${BASE_ERROR_CLASS}.${RESTART_CLASS}`,
  `#kb-view .${HINT_CLASS}`,
]) {
  assert.ok(
    CSS.includes(`${selector} {`),
    `styles.css 必须定义选择器「${selector}」；缺了它，app.js 赋的 class 就是个无样式的死名字`,
  );
}

// 作用域守卫：新样式不得写成全局裸 class（避免污染其它视图的 .kb-item-hint 同名元素）。
for (const className of [RESTART_CLASS, HINT_CLASS]) {
  const bareSelector = new RegExp(`(^|\\})\\s*\\.${className}\\s*\\{`, 'm');
  assert.ok(
    !bareSelector.test(CSS),
    `styles.css 不得出现无作用域的裸选择器 .${className} { ... }（必须限定 #kb-view 前缀）`,
  );
}

// ---------------------------------------------------------------------------
// 6. 禁用 innerHTML（XSS 回归点）
// ---------------------------------------------------------------------------
{
  const renderSection = APP_JS.slice(
    APP_JS.indexOf('function renderKbPapers(papers)'),
    APP_JS.indexOf('async function loadKbHealth()'),
  );
  assert.ok(renderSection.length > 0, '必须能定位到 renderKbPapers 实现段');
  assert.ok(!renderSection.includes('innerHTML'), 'KB 卡片渲染段不得使用 innerHTML');
}

/**
 * 收集子树里所有非空 className（失败信息用，帮助定位「class 被改成什么了」）。
 * 注意：只在断言失败路径调用，不参与正常判定。
 */
function collectClassNames(root) {
  const names = [];
  walk(root, (node) => {
    const classNames = classesOf(node);
    if (classNames.length) names.push(classNames.join(' '));
  });
  return names;
}

console.log(
  'ok - kb failure class dom contract（'
    + `.${BASE_ERROR_CLASS}.${RESTART_CLASS} 反向 DOM 断言 / `
    + `.${HINT_CLASS} 反向 DOM 断言 / `
    + '普通失败不误加重启色条 / progress=0 才出兜底提示 / CSS 选择器与作用域双向核对）',
);
