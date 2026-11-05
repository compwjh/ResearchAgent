'use strict';

/**
 * 知识库版本「服务重启中断」失败态的可读提示契约（执行级，`node:vm`）。
 *
 * 真实缺陷（Spec012 收口后用户反馈）：索引任务只跑在内存线程池里，服务重启后
 * `papers.json` 里残留的 `status=indexing, progress=0` 不会被回滚，卡片永久显示
 * 「v2 索引中 0%」；即使后端启动收敛成 `failed`（error=「服务重启导致中断」），
 * 前端也只把 error 塞进 `item.title`（悬停才看得到），主文案固定为
 * 「索引重建未完成，请点击「重试」重建」，用户不知道「上次是被重启打断的，可以自助重试」。
 *
 * 本文件把 `frontend/app.js` 里真实实现摘进 `node:vm` 沙箱执行（不复制影子实现）：
 *   `KB_STATUS_TEXT` / `chunkerBadgeText()` / `renderKbPapers()` / `rebuildKbPaper()`
 *
 * 覆盖：
 *   1. 收敛后（status=failed + error=「服务重启导致中断」）卡片显示可操作提示（不是只放 title）；
 *   2. 该卡片同时显示「重试」按钮，点击走既有 `rebuildKbPaper()`（POST 体仍为 `{chunker:'all'}`）；
 *   3. 收敛后不再残留「索引中 0%」文案，也不再有 progressbar；
 *   4. 普通失败（非重启原因）保持既有主文案，不误报「被重启打断」；
 *   5. `indexing` 长时间 progress=0 时给出兜底提示（可点重试），但轮询间隔仍 2500ms、
 *      `hasRunning` 启停逻辑不变；
 *   6. 新增文案全部走 textContent / setAttribute，禁止 innerHTML；
 *      CSS class 必须在 styles.css 里有定义（新增 class 必须落样式）。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');
const CSS = fs.readFileSync(path.resolve(__dirname, '../../frontend/styles.css'), 'utf8');

const RESTART_REASON = '服务重启导致中断';
const RESTART_HINT = '上次索引被服务重启中断，可点击「重试」重新建立索引';
const DEFAULT_FAILED_TEXT = '索引重建未完成，请点击「重试」重建';
const IDLE_INDEXING_HINT = '索引进度长时间停在 0%，如长时间停留可点「重试」';
const STUCK_BADGE_TEXT = 'v2 索引中断';

// ---- 源码抽取（原样） ----
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
  // 从常量定义起、到 kbFailureNotice 结束（不吞前面的 KB_STATUS_TEXT，避免重复声明）。
  const match = APP_JS.match(/const KB_INTERRUPTED_ERROR_PREFIX[\s\S]*?\nfunction kbFailureNotice[\s\S]*?\n}\n/);
  assert.ok(
    match,
    'app.js 必须定义「服务重启中断」识别与提示函数（KB_INTERRUPTED_ERROR_PREFIX / kbFailureNotice）',
  );
  return match[0];
})();

const chunkerBadgeTextSrc = slice('chunkerBadgeText\\(name, state\\)');
const kbDocumentIdSrc = slice('kbDocumentId\\(paper\\)');
const rebuildSrc = slice('rebuildKbPaper\\(paper, button\\)');
const renderSrc = slice('renderKbPapers\\(papers\\)');
const kbReindexErrorSrc = slice('kbReindexError\\(response, data\\)');
const kbReindexFailureTextSrc = slice('kbReindexFailureText\\(error\\)');

// ---- 最小 DOM 桩 ----
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

function textOf(node) {
  let out = '';
  walk(node, (current) => {
    if (typeof current.textContent === 'string' && current.textContent) out += `${current.textContent}\n`;
  });
  return out;
}

function findButton(root, className) {
  let found = null;
  walk(root, (node) => {
    if (!found && node.tagName === 'BUTTON' && String(node.className).split(/\s+/).includes(className)) found = node;
  });
  return found;
}

function collect(root, predicate) {
  const hits = [];
  walk(root, (node) => {
    if (predicate(node)) hits.push(node);
  });
  return hits;
}

function makeHarness(options = {}) {
  const kbList = makeEl('ul');
  const kbStatus = makeEl('span');
  const kbEmpty = makeEl('p');
  const calls = { schedule: 0, stop: 0 };
  const requests = [];

  const sandbox = {
    console,
    kbList,
    kbStatus,
    kbEmpty,
    setKbCountBadge() {},
    scheduleKbPoll() { calls.schedule += 1; },
    stopKbPoll() { calls.stop += 1; },
    consumePendingKbJump() {},
    showKbCountError() {},
    kbReindexInFlight: new Set(),
    loadKbPapers: async () => true,
    fetch: async (url, init) => {
      requests.push({ url, init });
      return {
        ok: true,
        status: 202,
        json: async () => ({ task_id: 'task-abc' }),
      };
    },
    document: {
      createElement(tag) {
        return makeEl(tag);
      },
    },
    // 让 `new Set()` 等内建在沙箱内可用
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
      kbReindexErrorSrc,
      kbReindexFailureTextSrc,
      rebuildSrc,
      renderSrc,
      'this.__render = renderKbPapers;',
      'this.__rebuild = rebuildKbPaper;',
      'this.__badge = chunkerBadgeText;',
    ].join('\n'),
    sandbox,
  );
  sandbox.__render(options.papers || []);
  return { sandbox, kbList, kbStatus, calls, requests };
}

function itemOf(h, index = 0) {
  return h.kbList.children[index];
}

// ---- 0. 静态契约：新增 class 必须有样式，且不得用 innerHTML ----
const renderSection = APP_JS.slice(
  APP_JS.indexOf('function renderKbPapers(papers)'),
  APP_JS.indexOf('async function loadKbHealth()'),
);
assert.ok(renderSection.length > 0, '必须能定位到 renderKbPapers 实现段');
assert.ok(!renderSection.includes('innerHTML'), 'KB 卡片渲染段不得使用 innerHTML（只用 textContent / setAttribute）');

const interruptSection = APP_JS.slice(
  APP_JS.indexOf('KB_INTERRUPTED_ERROR_PREFIX'),
  APP_JS.indexOf('function chunkerBadgeText'),
);
assert.ok(!interruptSection.includes('innerHTML'), '「重启中断」识别段不得使用 innerHTML');

// ---- 1. 重启中断失败态：可读提示 + 「重试」按钮 ----
{
  const paper = {
    document_id: 'doc-restart',
    file_name: 'restarted.pdf',
    status: 'failed',
    page_count: 0,
    error: null,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'failed', progress: 0, chunk_count: 0, error: RESTART_REASON },
    },
  };
  const h = makeHarness({ papers: [paper] });
  const item = itemOf(h);
  const text = textOf(item);

  assert.ok(
    text.includes(RESTART_HINT),
    `收敛后的卡片必须直接显示可操作提示「${RESTART_HINT}」，实际卡片文本为：${JSON.stringify(text)}`,
  );
  assert.ok(
    !text.includes(DEFAULT_FAILED_TEXT),
    `「被重启打断」不应退化回通用失败文案「${DEFAULT_FAILED_TEXT}」`,
  );

  const retry = findButton(item, 'kb-item-rebuild');
  assert.ok(retry, '失败态卡片必须给出「重试」按钮');
  assert.equal(retry.textContent, '重试', '失败态按钮文案必须是「重试」');
  assert.equal(retry.disabled, false, '「重试」按钮初始必须可点');
  assert.equal(h.calls.schedule, 0, '收敛成 failed 后没有 running 版本 → 不得启动轮询');
}

// ---- 2. 收敛后不再残留「索引中 0%」 ----
{
  const paper = {
    document_id: 'doc-converged',
    file_name: 'converged.pdf',
    status: 'failed',
    page_count: 0,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'failed', progress: 0, chunk_count: 0, error: RESTART_REASON },
    },
  };
  const h = makeHarness({ papers: [paper] });
  const item = itemOf(h);
  const text = textOf(item);
  assert.ok(!/索引中\s*0%/.test(text), `收敛后不得残留「索引中 0%」，实际文本：${JSON.stringify(text)}`);
  assert.equal(
    collect(item, (node) => node.getAttribute && node.getAttribute('role') === 'progressbar').length,
    0,
    '收敛后不应再有 indexing 进度条（progressbar）',
  );
  assert.equal(h.calls.schedule, 0, '没有 running 版本时不得启动轮询');

  // 版本徽标改成一眼能看出「中断」而不是「索引中」
  assert.equal(
    h.sandbox.__badge('v2', { status: 'failed', progress: 0, chunk_count: 0, error: RESTART_REASON }),
    STUCK_BADGE_TEXT,
    '被重启打断的版本徽标应显示「v2 索引中断」而不是「v2 索引中 0%」',
  );
}

// ---- 2b. 顶层 failed（error 直接落在文档上）+ indexing 版本被收敛 ----
{
  const paper = {
    document_id: 'doc-top-failed',
    file_name: 'top-failed.pdf',
    status: 'failed',
    page_count: 0,
    error: RESTART_REASON,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'failed', progress: 0, chunk_count: 0, error: RESTART_REASON },
    },
  };
  const h = makeHarness({ papers: [paper] });
  const item = itemOf(h);
  assert.ok(textOf(item).includes(RESTART_HINT), 'error 落在文档顶层时同样必须显示可操作提示');
}

// ---- 3. 普通失败（非重启原因）保持既有文案，不误报 ----
{
  const paper = {
    document_id: 'doc-real-fail',
    file_name: 'real-fail.pdf',
    status: 'failed',
    page_count: 3,
    // 既有渲染契约：只有 `paper.error` 进 `item.title`（chunker 级 error 不进，也不进主文案）。
    // 这里显式给出 paper.error，守住「原始错误码只进 title」这条既有底线。
    error: 'EmbeddingServiceUnavailable',
    chunkers: {
      v1: { status: 'failed', progress: 0, chunk_count: 0, error: 'EmbeddingServiceUnavailable' },
      v2: { status: 'pending', progress: 0, chunk_count: 0, error: null },
    },
  };
  const h = makeHarness({ papers: [paper] });
  const item = itemOf(h);
  const text = textOf(item);
  assert.ok(text.includes(DEFAULT_FAILED_TEXT), `普通失败必须保留既有主文案「${DEFAULT_FAILED_TEXT}」`);
  assert.ok(!text.includes(RESTART_HINT), '普通失败不得误报「被服务重启中断」');
  const retry = findButton(item, 'kb-item-rebuild');
  assert.ok(retry, '普通失败态同样有「重试」按钮（既有行为）');
  assert.equal(retry.textContent, '重试');
  const failureNode = item.children.find(
    (child) => String(child.className).split(/\s+/).includes('kb-item-error'),
  );
  assert.ok(failureNode, '失败态必须渲染 .kb-item-error 提示节点');
  // 既有契约（app.js「原始后端错误码只保留在 item.title」）：原始错误码只进列表项 title 供调试，
  // 绝不作为用户可见主文案。本用例确认这条契约在新增「重启中断」文案后仍然成立。
  assert.equal(
    item.title,
    'EmbeddingServiceUnavailable',
    '原始错误码仍保留在列表项 title 供调试',
  );
  assert.ok(
    !String(failureNode.textContent).includes('EmbeddingServiceUnavailable'),
    '原始错误码绝不进入用户可见主文案',
  );
}

// ---- 4. indexing 长时间 0%：兜底提示，但轮询与 hasRunning 逻辑不变 ----
{
  const paper = {
    document_id: 'doc-indexing',
    file_name: 'indexing.pdf',
    status: 'indexed',
    page_count: 0,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'indexing', progress: 0, chunk_count: 0, error: null },
    },
  };
  const h = makeHarness({ papers: [paper] });
  const item = itemOf(h);
  const text = textOf(item);
  assert.ok(text.includes('索引中 0%'), 'indexing 态仍应显示真实进度（不得伪造完成）');
  assert.ok(
    text.includes(IDLE_INDEXING_HINT),
    `indexing 且 progress=0 时必须给出兜底提示「${IDLE_INDEXING_HINT}」`,
  );
  const retry = findButton(item, 'kb-item-rebuild');
  assert.ok(retry, '兜底提示必须配可点的按钮');
  assert.equal(retry.textContent, '重建索引', '仅 indexing 时按钮仍为「重建索引」（不是重试）');
  assert.equal(h.calls.schedule, 1, 'indexing 仍在跑 → 必须启动轮询（hasRunning 逻辑不变）');
  assert.equal(h.calls.stop, 0);

  // progress > 0 时不再打扰用户
  const h2 = makeHarness({
    papers: [{
      ...paper,
      document_id: 'doc-indexing-2',
      chunkers: {
        v1: paper.chunkers.v1,
        v2: { status: 'indexing', progress: 42, chunk_count: 0, error: null },
      },
    }],
  });
  assert.ok(
    !textOf(itemOf(h2)).includes(IDLE_INDEXING_HINT),
    'progress > 0 说明任务真在跑，不应显示「长时间停在 0%」提示',
  );
}

// ---- 5. 轮询间隔与 hasRunning 启停逻辑不变 ----
assert.ok(
  /kbPollTimer = window\.setInterval\(\(\) => \{\s*\n\s*loadKbPapers\(\);\s*\n\s*\}, 2500\);/.test(APP_JS),
  'KB 轮询间隔必须仍为 2500ms（scheduleKbPoll 内 setInterval 不得改动）',
);
assert.ok(
  /if \(hasRunning\) scheduleKbPoll\(\);\s*\n\s*else stopKbPoll\(\);/.test(APP_JS),
  'hasRunning → scheduleKbPoll / 否则 stopKbPoll 的启停逻辑不得改动',
);

// ---- 6. 新增 class 必须在 styles.css 有样式 ----
for (const className of ['kb-item-error-restart', 'kb-item-hint']) {
  assert.ok(
    CSS.includes(`.${className}`),
    `styles.css 必须定义 .${className}（新增 class 不能只是加个无样式的名字）`,
  );
}

async function main() {
  // ---- 7. 点「重试」仍走既有 rebuildKbPaper：POST /reindex，body 契约仍是 {chunker:'all'} ----
  const paper = {
    document_id: 'doc-restart',
    file_name: 'restarted.pdf',
    status: 'failed',
    page_count: 0,
    error: null,
    chunkers: {
      v1: { status: 'indexed', progress: 100, chunk_count: 55, error: null },
      v2: { status: 'failed', progress: 0, chunk_count: 0, error: RESTART_REASON },
    },
  };
  const h = makeHarness({ papers: [paper] });
  const retry = findButton(itemOf(h), 'kb-item-rebuild');
  assert.ok(retry, '重启中断卡片必须仍有「重试」按钮');
  await retry.click();
  const request = h.requests[0];
  assert.ok(request, '点击「重试」必须发出重建请求（沿既有 rebuildKbPaper）');
  assert.equal(
    request.url,
    '/api/kb/documents/doc-restart/reindex',
    '必须复用既有 POST /api/kb/documents/{id}/reindex 契约',
  );
  assert.equal(request.init.method, 'POST');
  assert.deepEqual(JSON.parse(request.init.body), { chunker: 'all' }, '请求体契约不得改动：{chunker:"all"}');
  assert.equal(retry.disabled, false, '请求收尾后「重试」按钮必须解锁，允许用户再次自助重试');
  assert.ok(
    /已提交重建/.test(h.kbStatus.textContent),
    `成功后 #kb-status 文案体系不变（应提示「已提交重建…」），实际为「${h.kbStatus.textContent}」`,
  );

  console.log(
    'ok - kb index interruption notice（重启中断可读提示 / 重试按钮 / 无「索引中 0%」残留 / 普通失败不误报 / 兜底提示 / 轮询不变）',
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
