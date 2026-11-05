'use strict';

/**
 * 「在知识库中查看」跳转定位契约（执行级，`node:vm`）。
 *
 * 真实缺陷（用户验收反馈）：地图节点详情点「在知识库中查看」后只切到知识库视图，
 * 列表既不滚动也不高亮。原因是跨模块标识符契约不一致：
 *   - 地图 / 深度研究传的是 `document_id`；
 *   - KB 列表项在 `paper_id` 为 null 时**只写** `data-document-id`（app.js:6339-6340）；
 *   - 旧 `jumpToKnowledgeBase(paperId)` 只按 `[data-paper-id]` 精确匹配 → 必然落空。
 *
 * 本文件把 `frontend/app.js` 里真实实现摘进 `node:vm` 沙箱执行（不复制影子实现）：
 *   `kbDocumentId(paper)` / `selectKbJumpTarget(id)` / `applyKbJumpFocus(item, id)` /
 *   `consumePendingKbJump()` / `loadKbPapers()`
 *
 * 覆盖：
 *   1. 按 `data-document-id` 命中（paper_id 为 null 的真实场景）；
 *   2. 兼容 `data-paper-id`（旧链接 / 有 paper_id 的条目）；
 *   3. 命中后 scrollIntoView({block:'center'}) + focus + 可见高亮 class；
 *   4. 未命中时 kbStatus 明确提示并给出可操作下一步（不是静默切页）；
 *   5. `pendingKbPaperId` 被消费：loadKbPapers() 渲染完成后重试定位（含异步未就绪）；
 *   6. 只滚动 + 高亮，不自动展开 / 打开文档详情。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');
const CSS = fs.readFileSync(path.resolve(__dirname, '../../frontend/styles.css'), 'utf8');

const HIGHLIGHT_CLASS = 'kb-item-jump-target';
const NOT_FOUND_PREFIX = '未在当前知识库列表中找到该文档';
const NEED_ID_PREFIX = '无法定位该文档：缺少稳定 ID';

// ---- 源码抽取（原样） ----
function slice(signature) {
  const match = APP_JS.match(new RegExp(`(?:async )?function ${signature}[\\s\\S]*?\\n\\}\\n`));
  assert.ok(match, `app.js 必须定义 ${signature}`);
  return match[0];
}

const jumpConstsMatch = APP_JS.match(/const KB_JUMP_HIGHLIGHT_CLASS = .*?;\nconst KB_JUMP_NOT_FOUND_TEXT = .*?;\nconst KB_JUMP_NEED_ID_TEXT = .*?;\n/s);
assert.ok(jumpConstsMatch, 'app.js 必须定义 KB_JUMP_* 常量（高亮 class 与提示文案）');
const jumpConstsSrc = jumpConstsMatch[0];
const kbDocumentIdSrc = slice('kbDocumentId\\(paper\\)');
const selectTargetSrc = slice('selectKbJumpTarget\\(identifier\\)');
const focusSrc = slice('applyKbJumpFocus\\(item, identifier\\)');
const clearSrc = slice('clearKbJumpHighlight\\(\\)');
const consumePendingSrc = slice('consumePendingKbJump\\(\\)');
const jumpSrc = slice('jumpToKnowledgeBase\\(paperId\\)');
const loadKbPapersSrc = slice('loadKbPapers\\(\\)');
const renderKbPapersSrc = slice('renderKbPapers\\(papers\\)');

// ---- 最小 DOM 桩 ----
function makeEl(tag, extra = {}) {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    title: '',
    hidden: false,
    tabIndex: 0,
    dataset: {},
    classList: {
      added: [],
      removed: [],
      add(name) {
        this.added.push(name);
        node.className = `${node.className} ${name}`.trim();
      },
      remove(name) {
        this.removed.push(name);
        node.className = node.className
          .split(/\s+/)
          .filter((part) => part && part !== name)
          .join(' ');
      },
      contains(name) {
        return node.className.split(/\s+/).includes(name);
      },
    },
    focused: false,
    scrolled: null,
    focus() {
      node.focused = true;
    },
    scrollIntoView(options) {
      node.scrolled = options || {};
    },
    setAttribute() {},
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
    ...extra,
  };
  return node;
}

function makeHarness(options = {}) {
  const kbList = makeEl('ul');
  const kbStatus = makeEl('span');
  const kbEmpty = makeEl('p');

  const listItems = (options.items || []).map((entry) => {
    const item = makeEl('li');
    if (entry.documentId) item.dataset.documentId = entry.documentId;
    if (entry.paperId) item.dataset.paperId = entry.paperId;
    // 与真实 renderKbPapers 一致：条目可被动聚焦但不在 tab 顺序内。
    item.tabIndex = -1;
    return item;
  });

  const sandbox = {
    console,
    kbList,
    kbStatus,
    kbEmpty,
    showKbCountLoading() {},
    showKbCountError() {},
    setKbCountBadge() {},
    scheduleKbPoll() {},
    stopKbPoll() {},
    renderKbItem: (paper) => {
      const item = makeEl('li');
      const documentId = paper.document_id;
      if (documentId) item.dataset.documentId = documentId;
      if (paper.paper_id) item.dataset.paperId = paper.paper_id;
      // 与真实 renderKbPapers 一致：条目可被动聚焦但不在 tab 顺序内。
      item.tabIndex = -1;
      kbList.appendChild(item);
      return item;
    },
    KB_STATUS_TEXT: {},
    fetch: options.fetch || (async () => ({ ok: true, json: async () => ({ papers: options.papers || [] }) })),
    // 生产环境里 jumpToKnowledgeBase 通过 showView('kb') 真正切视图；这里只记账。
    showViewCalls: [],
    document: {
      querySelectorAll(selector) {
        // 与真实 DOM 一致：查询时**活取**当前列表内容（不缓存快照），
        // 否则异步渲染出来的新条目会被漏掉（这正是「跳转失败」的真实成因之一）。
        const highlightSelector = /^\.([a-z-]+)$/.exec(selector);
        if (highlightSelector) {
          const className = highlightSelector[1];
          return [...listItems, ...kbList.children].filter((item) => item.className.includes(className));
        }
        const match = /^\[data-([a-z-]+)\]$/.exec(selector);
        if (!match) return [];
        const key = match[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        return [...listItems, ...kbList.children].filter((item) => item.dataset[key] !== undefined);
      },
      querySelector() {
        return null;
      },
      createElement(tag) {
        return makeEl(tag);
      },
    },
    paperState: { pendingKbPaperId: null },
  };
  sandbox.showView = (view) => {
    sandbox.showViewCalls.push(view);
  };

  vm.createContext(sandbox);
  vm.runInContext(
    [
      jumpConstsSrc,
      kbDocumentIdSrc,
      clearSrc,
      selectTargetSrc,
      focusSrc,
      consumePendingSrc,
      jumpSrc,
      // renderKbPapers 在真实代码里很大，这里只保留它对 kbList 的收口语义：
      // 渲染即把列表项挂到 kbList（与真实实现等价的可观察结果）。
      'function renderKbPapers(papers) {',
      '  kbList.replaceChildren();',
      '  for (const paper of papers) { renderKbItem(paper); }',
      '  kbList.removeAttribute?.("aria-busy");',
      // 与生产实现同一条收口路径：渲染完成后消费 pending 并重试定位。
      '  consumePendingKbJump();',
      '  return false;',
      '}',
      'this.__picked_renderKbPapers = renderKbPapers;',
      loadKbPapersSrc,
      'this.__fns = { kbDocumentId, selectKbJumpTarget, applyKbJumpFocus, consumePendingKbJump, jumpToKnowledgeBase, loadKbPapers };',
    ].join('\n'),
    sandbox,
  );
  void renderKbPapersSrc;
  return { sandbox, kbList, kbStatus, listItems };
}

// ---- 0. CSS 契约：高亮 class 必须有样式（新增 class 必须落 styles.css） ----
assert.ok(
  CSS.includes(`.kb-item.${HIGHLIGHT_CLASS}`),
  `styles.css 必须定义 .kb-item.${HIGHLIGHT_CLASS}（高亮可见，不能只是加个无样式 class）`,
);
// app.js 里既有经 sanitize/markdown 的 innerHTML（不属本次范围）；这里只守
// 本次新增的跳转定位链路：不得用 innerHTML 拼提示或列表项内容。
const jumpSection = APP_JS.slice(
  APP_JS.indexOf('const KB_JUMP_HIGHLIGHT_CLASS'),
  APP_JS.indexOf('async function loadPaperConferences'),
);
assert.ok(jumpSection.length > 0, '必须能定位到跳转定位实现段');
assert.ok(!jumpSection.includes('innerHTML'), '跳转定位段不得使用 innerHTML（只用 textContent / classList）');

async function main() {
// ---- 1. 生产契约自检：KB 列表项在 paper_id 为 null 时只写 data-document-id ----
assert.ok(
  /if \(documentId\) item\.dataset\.documentId = documentId;\s*\n\s*if \(paper\.paper_id\) item\.dataset\.paperId = paper\.paper_id;/.test(APP_JS),
  'renderKbPapers 必须仍按 documentId / paper_id 分别写入 data 属性',
);

// ---- 2. 按 data-document-id 命中（paper_id 为 null 的真实场景） ----
{
  const h = makeHarness({
    items: [
      { documentId: 'other-doc' },
      { documentId: '1b967ed8638e46569d36e3f6565c51eb' },
    ],
  });
  await h.sandbox.__fns.jumpToKnowledgeBase('1b967ed8638e46569d36e3f6565c51eb');
  const target = h.listItems[1];
  assert.equal(target.scrolled?.block, 'center', '命中后必须滚动到视口中央（scrollIntoView({block:\'center\'})）');
  assert.equal(target.focused, true, '命中后必须 focus 列表项');
  assert.equal(target.tabIndex, -1, '可以被动聚焦（不进入 tab 顺序）');
  assert.ok(
    target.className.includes(HIGHLIGHT_CLASS),
    '命中后必须加可见高亮 class（用户要看到「跳到这篇了」）',
  );
  assert.equal(h.listItems[0].className.includes(HIGHLIGHT_CLASS), false, '未命中的兄弟项不得高亮');
  assert.deepEqual(h.sandbox.showViewCalls, ['kb'], '仍必须切到知识库视图');
}

// ---- 3. 兼容 data-paper-id ----
{
  const h = makeHarness({
    items: [{ documentId: 'doc-1', paperId: 'paper-1' }, { paperId: 'paper-2' }],
  });
  await h.sandbox.__fns.jumpToKnowledgeBase('paper-2');
  assert.equal(h.listItems[1].focused, true, '传入 paper_id 时必须仍能命中 data-paper-id（向后兼容）');
  assert.equal(h.listItems[1].scrolled?.block, 'center');
}

// ---- 4. 未命中 → 明确提示 + 可操作下一步 ----
{
  const h = makeHarness({ items: [{ documentId: 'doc-1' }] });
  await h.sandbox.__fns.jumpToKnowledgeBase('missing-doc');
  assert.ok(
    h.kbStatus.textContent.startsWith(NOT_FOUND_PREFIX),
    `未命中时 kbStatus 必须以「${NOT_FOUND_PREFIX}」开头，实际为「${h.kbStatus.textContent}」`,
  );
  assert.ok(
    /刷新|重试/.test(h.kbStatus.textContent),
    '未命中提示必须给出可操作下一步（刷新 / 重试）',
  );
  assert.equal(h.listItems[0].focused, false, '未命中不得乱选中别的条目');
}

// ---- 5. 缺少稳定 ID → 给专门提示 ----
{
  const h = makeHarness({ items: [{ documentId: 'doc-1' }] });
  await h.sandbox.__fns.jumpToKnowledgeBase(null);
  assert.ok(
    h.kbStatus.textContent.startsWith(NEED_ID_PREFIX),
    `传入空 id 时必须提示「${NEED_ID_PREFIX}」，实际为「${h.kbStatus.textContent}」`,
  );
}

// ---- 5b. 未命中提示不得覆盖「列表加载失败」文案（避免把后端故障误报成「文档不在库里」） ----
{
  const loadFailure = '列表加载失败：网络中断';
  const h = makeHarness({
    items: [{ documentId: 'doc-1' }],
    fetch: async () => { throw new Error('网络中断'); },
  });
  await h.sandbox.__fns.jumpToKnowledgeBase('missing-doc');
  assert.equal(
    h.kbStatus.textContent,
    loadFailure,
    `列表本身加载失败时必须保留真实故障文案「${loadFailure}」，不得覆盖成未命中提示，实际为「${h.kbStatus.textContent}」`,
  );
  assert.equal(h.listItems[0].focused, false, '列表加载失败时不得乱选中条目');
}

// ---- 5c. 切视图 / 重新定位时清除旧高亮（避免多个条目同时高亮） ----
{
  const h = makeHarness({ items: [{ documentId: 'doc-1' }, { documentId: 'doc-2' }] });
  await h.sandbox.__fns.jumpToKnowledgeBase('doc-1');
  assert.ok(h.listItems[0].className.includes(HIGHLIGHT_CLASS), '第一次定位必须高亮 doc-1');
  await h.sandbox.__fns.jumpToKnowledgeBase('doc-2');
  assert.equal(
    h.listItems[0].className.includes(HIGHLIGHT_CLASS),
    false,
    '再次定位到别的文档时，旧条目的高亮必须被清除（同一时刻只应有一处高亮）',
  );
  assert.ok(h.listItems[1].className.includes(HIGHLIGHT_CLASS), '新目标必须高亮');
}

// ---- 6. pendingKbPaperId 被消费：列表异步渲染完成后重试定位 ----
  // 首次 fetch 返回空列表（模拟列表还没就绪），第二次返回目标文档。
  let call = 0;
  const h = makeHarness({
    fetch: async () => {
      call += 1;
      const papers = call === 1 ? [] : [{ document_id: 'doc-late', paper_id: null }];
      return { ok: true, json: async () => ({ papers }) };
    },
  });
  await h.sandbox.__fns.jumpToKnowledgeBase('doc-late');
  assert.ok(
    h.kbStatus.textContent.startsWith(NOT_FOUND_PREFIX),
    '第一次列表里没有该文档时仍要给明确提示（不能静默）',
  );
  assert.equal(h.sandbox.paperState.pendingKbPaperId, 'doc-late', '未命中时必须记住待定位 ID，等列表就绪后重试');

  // 列表后续渲染完成（poll / 重新加载）→ 自动重试定位并命中。
  await h.sandbox.__fns.loadKbPapers();
  const item = h.kbList.children[0];
  assert.ok(item, '第二次加载必须渲染出目标条目');
  assert.equal(item.focused, true, 'loadKbPapers 渲染完成后必须消费 pendingKbPaperId 重试定位');
  assert.equal(item.scrolled?.block, 'center');
  assert.ok(item.className.includes(HIGHLIGHT_CLASS), '重试命中后同样要可见高亮');
  // 缺陷 A2 修复后语义变更：pendingKbPaperId 是「当前跳转目标」，命中后**不再立即清空**。
  // 原因：跳转路径上 showView('kb') 与 jump 自己各触发一次 loadKbPapers() →
  // 两次 renderKbPapers() 重建 DOM，首次命中的 class/focus 会被冲掉。保留 pending
  // 才能让每次渲染都对新 DOM 重新定位。生命周期改由离开 KB 视图（showView 的
  // nextView !== 'kb' 分支）或下一次跳转覆盖来结束，见
  // tests/frontend/test_frontend_kb_jump_rerender.js。
  assert.equal(
    h.sandbox.paperState.pendingKbPaperId,
    'doc-late',
    '命中后必须保留「当前跳转目标」，供后续每次 renderKbPapers() 重新对新 DOM 定位',
  );
  assert.ok(
    h.kbStatus.textContent.includes('已定位'),
    `命中后 kbStatus 应给出已定位提示，实际为「${h.kbStatus.textContent}」`,
  );

  // ---- 7. 不自动展开 / 打开文档详情 ----
  assert.equal(item.children.length, 0, '定位不得向列表项追加详情内容（不自动展开/打开详情）');
  assert.equal(item.hidden, false, '定位不得改动可见性以外的展示状态');
  assert.equal(item.dataset.documentId, 'doc-late', '条目 data-document-id 与跳转 ID 一致');
}

main().then(
  () => {
    console.log('ok - kb jump focus (document_id 命中 / paper_id 兼容 / 未命中提示 / pending 消费)');
  },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
