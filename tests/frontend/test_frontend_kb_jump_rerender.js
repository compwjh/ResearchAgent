'use strict';

/**
 * 「在知识库中查看」跳转定位的**重渲染时序**契约（缺陷 A2，执行级 `node:vm`）。
 *
 * 真实缺陷（主会话真实 Chromium E2E 抓到，既有 test_frontend_kb_jump_focus.js 未覆盖）：
 *   从地图节点点「在知识库中查看」后，`#kb-status` 明明显示
 *   「已定位到知识库中的该文档（1b967ed…）」，但目标
 *   `li[data-document-id="1b967ed…"]` 的 classList 里没有 `kb-item-jump-target`、
 *   `document.activeElement !== li`、`getBoundingClientRect().top = 10505`
 *   （viewport 高 720）——即**完全没定位**，状态文案是假阳性。
 *
 * 根因（时序）：
 *   `jumpToKnowledgeBase()` 在 `showView('kb')` 之后**立即** `focusNow()`，命中的是
 *   跳转前就已渲染的旧 DOM，随即写入「已定位」并清空 pending；紧接着 `showView('kb')`
 *   内部的 `loadKbPapers()` 与 jump 自己那次 `loadKbPapers()` 共**两次**异步
 *   `renderKbPapers()` 重建列表，class / focus / scroll 全部丢失。
 *
 * 因此本文件按真实时序断言：
 *   1. 跳转时列表已存在 → 立刻对旧 DOM 命中，但**不得**因此清空「当前跳转目标」；
 *   2. 两次 renderKbPapers 重建 DOM 后，高亮 / focus / scrollIntoView 最终落在
 *      **最后一次渲染的新节点**上，旧节点既不保留高亮也不保留 focus；
 *   3. 状态文案与真实定位一致（新节点确实被高亮+聚焦时才允许出现「已定位」）；
 *   4. 离开 KB 视图后 pending 被清除，且旧高亮不残留（回来不会莫名高亮一条）；
 *   5. 保持既有 C-4 行为：列表加载失败时不得把故障文案覆盖成「未找到该文档」。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');

const HIGHLIGHT_CLASS = 'kb-item-jump-target';
const NOT_FOUND_PREFIX = '未在当前知识库列表中找到该文档';
const NEED_ID_PREFIX = '无法定位该文档：缺少稳定 ID';

function slice(signature) {
  const match = APP_JS.match(new RegExp('(?:async )?function ' + signature + '[\\s\\S]*?\\n}\\n'));
  assert.ok(match, 'app.js 必须定义 ' + signature);
  return match[0];
}

const jumpConstsMatch = APP_JS.match(/const KB_JUMP_HIGHLIGHT_CLASS = .*?;\nconst KB_JUMP_NOT_FOUND_TEXT = .*?;\nconst KB_JUMP_NEED_ID_TEXT = .*?;\n/s);
assert.ok(jumpConstsMatch, 'app.js 必须定义 KB_JUMP_* 常量');
const jumpConstsSrc = jumpConstsMatch[0];
const kbDocumentIdSrc = slice('kbDocumentId\\(paper\\)');
const selectTargetSrc = slice('selectKbJumpTarget\\(identifier\\)');
const focusSrc = slice('applyKbJumpFocus\\(item, identifier\\)');
const clearSrc = slice('clearKbJumpHighlight\\(\\)');
const consumePendingSrc = slice('consumePendingKbJump\\(\\)');
const jumpSrc = slice('jumpToKnowledgeBase\\(paperId\\)');
const loadKbPapersSrc = slice('loadKbPapers\\(\\)');
const renderKbPapersSrc = slice('renderKbPapers\\(papers\\)');

// ---- 最小 DOM 桩（带 isConnected / ownerDocument 语义） ----
function makeDoc() {
  const doc = {
    items: [],
    createElement(tag) {
      return makeEl(tag, doc);
    },
  };
  return doc;
}

function makeEl(tag, doc) {
  const node = {
    tagName: String(tag).toUpperCase(),
    ownerDocument: doc,
    children: [],
    className: '',
    textContent: '',
    title: '',
    hidden: false,
    tabIndex: 0,
    dataset: {},
    removed: false,
    focused: false,
    scrolled: null,
    get isConnected() {
      return !node.removed && !node.__detached;
    },
    classList: {
      add(name) {
        const parts = node.className.split(/\s+/).filter(Boolean);
        if (!parts.includes(name)) parts.push(name);
        node.className = parts.join(' ');
      },
      remove(name) {
        node.className = node.className.split(/\s+/).filter((part) => part && part !== name).join(' ');
      },
      contains(name) {
        return node.className.split(/\s+/).includes(name);
      },
    },
    focus() {
      node.focused = true;
      if (doc) doc.activeElement = node;
    },
    scrollIntoView(options) {
      node.scrolled = options || {};
    },
    setAttribute() {},
    removeAttribute() {},
    remove() {
      node.removed = true;
      node.focused = false;
      if (doc && doc.activeElement === node) doc.activeElement = null;
    },
    appendChild(child) {
      node.children.push(child);
      return child;
    },
    append(...items) {
      node.children.push(...items);
    },
    replaceChildren() {
      // 真实 DOM：被替换掉的旧子节点脱离文档（isConnected=false），不能再被聚焦/高亮。
      for (const child of node.children) {
        child.removed = true;
        child.focused = false;
        if (doc && doc.activeElement === child) doc.activeElement = null;
      }
      node.children = [];
    },
  };
  return node;
}

function makeHarness(options = {}) {
  const doc = makeDoc();
  doc.activeElement = null;
  const kbList = makeEl('ul', doc);
  const kbStatus = makeEl('span', doc);
  const kbEmpty = makeEl('p', doc);

  // 跳转前列表可能已经渲染过一次（真实场景：用户之前看过知识库）。
  for (const paper of options.initialPapers || []) {
    kbList.appendChild(makeKbItem(doc, paper));
  }

  function makeKbItem(ownerDoc, paper) {
    const item = makeEl('li', ownerDoc);
    item.className = `kb-item status-${paper.status || 'indexed'}`;
    const documentId = paper.document_id || paper.paper_id || '';
    if (documentId) item.dataset.documentId = String(documentId);
    if (paper.paper_id) item.dataset.paperId = String(paper.paper_id);
    item.tabIndex = -1;
    return item;
  }

  const sandbox = {
    console,
    kbList,
    kbStatus,
    kbEmpty,
    kbListLoadFailed: false,
    showKbCountLoading() {},
    showKbCountError() {},
    setKbCountBadge() {},
    scheduleKbPoll() {},
    stopKbPoll() {},
    KB_STATUS_TEXT: {},
    fetch: options.fetch || (async () => ({ ok: true, json: async () => ({ papers: options.papers || [] }) })),
    showViewCalls: [],
    document: doc,
    paperState: { pendingKbPaperId: null },
  };
  doc.querySelectorAll = (selector) => {
    const all = kbList.children.filter((item) => !item.removed);
    const highlight = /^\.([a-z-]+)$/.exec(selector);
    if (highlight) return all.filter((item) => item.classList.contains(highlight[1]));
    const match = /^\[data-([a-z-]+)\]$/.exec(selector);
    if (!match) return [];
    const key = match[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    return all.filter((item) => item.dataset[key] !== undefined);
  };
  doc.querySelector = () => null;
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
      loadKbPapersSrc,
      // 真实 renderKbPapers 很大，这里保留它对 kbList 与 pending 的收口语义：
      // 清空并重建列表项，末尾消费 pending 重新定位（与生产同一路径）。
      'function renderKbPapers(papers) {',
      '  kbList.replaceChildren();',
      '  for (const paper of papers) {',
      '    const item = document.createElement("li");',
      '    item.className = "kb-item status-" + (paper.status || "indexed");',
      '    const documentId = kbDocumentId(paper);',
      '    if (documentId) item.dataset.documentId = documentId;',
      '    if (paper.paper_id) item.dataset.paperId = paper.paper_id;',
      '    item.tabIndex = -1;',
      '    kbList.appendChild(item);',
      '  }',
      '  consumePendingKbJump();',
      '  return false;',
      '}',
      'this.__fns = { kbDocumentId, selectKbJumpTarget, applyKbJumpFocus, clearKbJumpHighlight, consumePendingKbJump, jumpToKnowledgeBase, loadKbPapers, renderKbPapers };',
    ].join('\n'),
    sandbox,
  );
  void renderKbPapersSrc;
  return { sandbox, doc, kbList, kbStatus, makeKbItem };
}

function items(kbList) {
  return kbList.children.filter((item) => !item.removed);
}

function summary(kbList) {
  return JSON.stringify(items(kbList).map((item) => ({
    id: item.dataset.documentId,
    highlight: item.classList.contains(HIGHLIGHT_CLASS),
    focused: item.focused,
    scrolled: item.scrolled,
  })));
}

async function main() {
  // ---- 0. 静态契约 ----
  const jumpSection = APP_JS.slice(
    APP_JS.indexOf('const KB_JUMP_HIGHLIGHT_CLASS'),
    APP_JS.indexOf('async function loadPaperConferences'),
  );
  assert.ok(jumpSection.length > 0, '必须能定位到跳转定位实现段');
  assert.ok(!jumpSection.includes('innerHTML'), '跳转定位段不得使用 innerHTML');
  assert.ok(
    /item\.isConnected/.test(focusSrc),
    'applyKbJumpFocus 必须校验 item.isConnected：已脱离文档的旧节点不得写入「已定位」',
  );
  assert.ok(
    !/paperState\.pendingKbPaperId = null/.test(jumpSrc.replace(/[\s\S]*?clearKbJumpHighlight\(\);/, '')),
    'jumpToKnowledgeBase 不得在列表重建前就把 pendingKbPaperId 清空（否则后续 renderKbPapers 无法重新定位）',
  );

  // ---- 1. 核心时序：跳转时列表已存在 → 两次 renderKbPapers 重建 DOM ----
  {
    const staleId = '1b967ed8638e46569d36e3f6565c51eb';
    const h = makeHarness({
      // 跳转前列表里已有该文档（旧 DOM）。
      initialPapers: [{ document_id: staleId, status: 'indexed' }, { document_id: 'other-doc' }],
      // showView('kb') 的那次加载 + jump 自己那次加载，各返回一次同样的列表。
      fetch: async () => ({
        ok: true,
        json: async () => ({ papers: [{ document_id: staleId, status: 'indexed' }, { document_id: 'other-doc' }] }),
      }),
    });
    const staleItem = items(h.kbList).find((item) => item.dataset.documentId === staleId);
    assert.ok(staleItem, '前置条件：跳转前列表必须已渲染过该文档（复现旧 DOM 命中）');

    await h.sandbox.__fns.jumpToKnowledgeBase(staleId);

    assert.deepEqual(h.sandbox.showViewCalls, ['kb'], '必须切到知识库视图');

    // 两次加载把列表重建了两遍 → 现在列表里是全新节点。
    const fresh = items(h.kbList).find((item) => item.dataset.documentId === staleId);
    assert.ok(fresh, '重建后列表里仍应有目标文档');
    assert.notEqual(fresh, staleItem, '前置条件：重建后必须是**新** DOM 节点（旧节点已被替换脱离文档）');
    assert.equal(staleItem.isConnected, false, '旧节点必须已脱离文档');

    assert.equal(
      staleItem.classList.contains(HIGHLIGHT_CLASS),
      false,
      `旧节点不得保留高亮（否则用户看到的是已经不在页面上的节点），实际 ${summary(h.kbList)}`,
    );
    assert.equal(
      fresh.classList.contains(HIGHLIGHT_CLASS),
      true,
      `高亮必须落在最后一次渲染的新节点上，实际 ${summary(h.kbList)}`,
    );
    assert.equal(fresh.scrolled?.block, 'center', `新节点必须被滚动到视口中央，实际 ${summary(h.kbList)}`);
    assert.equal(fresh.focused, true, `新节点必须被聚焦，实际 ${summary(h.kbList)}`);
    assert.equal(h.doc.activeElement, fresh, 'document.activeElement 必须是新节点（不是已脱离文档的旧节点）');

    assert.ok(
      h.kbStatus.textContent.includes('已定位'),
      `定位成功时 kbStatus 应给出「已定位」，实际「${h.kbStatus.textContent}」`,
    );

    // 状态文案必须与真实定位一致：说「已定位」时新节点确实高亮 + 聚焦。
    assert.ok(
      fresh.classList.contains(HIGHLIGHT_CLASS) && h.doc.activeElement === fresh,
      '状态文案「已定位」必须与真实定位（高亮 + 聚焦）一致，不允许假阳性',
    );

    // 同一时刻只应有一处高亮（且只能是可见的当前节点）。
    const highlighted = items(h.kbList).filter((item) => item.classList.contains(HIGHLIGHT_CLASS));
    assert.equal(highlighted.length, 1, `同一时刻只应有一处高亮，实际 ${summary(h.kbList)}`);
    assert.equal(highlighted[0], fresh, '唯一的高亮必须落在新节点上');
  }

  // ---- 2. 每次渲染都重新定位：三次重建后仍落在最新节点 ----
  {
    const targetId = 'doc-repeat';
    const h = makeHarness({
      initialPapers: [{ document_id: targetId }],
      fetch: async () => ({ ok: true, json: async () => ({ papers: [{ document_id: targetId }] }) }),
    });
    await h.sandbox.__fns.jumpToKnowledgeBase(targetId);
    assert.equal(h.sandbox.paperState.pendingKbPaperId, targetId, 'pending 作为「当前跳转目标」必须保留，供后续每次渲染重新定位');

    const seen = [];
    for (let round = 0; round < 3; round += 1) {
      await h.sandbox.__fns.loadKbPapers();
      const current = items(h.kbList).find((item) => item.dataset.documentId === targetId);
      assert.ok(current, `第 ${round + 1} 次重建后目标文档仍应在列表里`);
      assert.ok(
        current.classList.contains(HIGHLIGHT_CLASS),
        `第 ${round + 1} 次重建后高亮必须重新落在当前节点上，实际 ${summary(h.kbList)}`,
      );
      assert.equal(h.doc.activeElement, current, `第 ${round + 1} 次重建后 focus 必须落在当前节点上`);
      seen.push(current);
    }
    assert.equal(new Set(seen).size, 3, '每次重建都必须是新节点（证明定位跟着 DOM 走，而不是停在第一次的旧节点）');
  }

  // ---- 3. 离开 KB 视图 → pending 清除、旧高亮不残留 ----
  {
    const targetId = 'doc-leave';
    const h = makeHarness({
      initialPapers: [{ document_id: targetId }],
      fetch: async () => ({ ok: true, json: async () => ({ papers: [{ document_id: targetId }] }) }),
    });
    await h.sandbox.__fns.jumpToKnowledgeBase(targetId);
    const current = items(h.kbList).find((item) => item.dataset.documentId === targetId);
    assert.ok(current.classList.contains(HIGHLIGHT_CLASS), '前置条件：跳转后目标必须高亮');

    // 生产语义：showView 里 nextView !== 'kb' 时清 pending + 旧高亮。
    h.sandbox.paperState.pendingKbPaperId = null;
    h.sandbox.__fns.clearKbJumpHighlight();
    const after = items(h.kbList).filter((item) => item.classList.contains(HIGHLIGHT_CLASS));
    assert.equal(after.length, 0, '离开 KB 视图后旧高亮不得残留（再回来不应莫名高亮一条）');

    // 残留的 pending 会让下一次渲染又跳一次：必须已清除。
    await h.sandbox.__fns.loadKbPapers();
    const again = items(h.kbList).filter((item) => item.classList.contains(HIGHLIGHT_CLASS));
    assert.equal(again.length, 0, '离开后重新渲染不得再自动跳转高亮（pending 已清除）');
  }

  // ---- 4. 未命中：保留 pending 并给出可操作提示（既有行为不回归） ----
  {
    const h = makeHarness({ fetch: async () => ({ ok: true, json: async () => ({ papers: [] }) }) });
    await h.sandbox.__fns.jumpToKnowledgeBase('missing-doc');
    assert.ok(
      h.kbStatus.textContent.startsWith(NOT_FOUND_PREFIX),
      `未命中时必须提示「${NOT_FOUND_PREFIX}」，实际「${h.kbStatus.textContent}」`,
    );
    assert.equal(h.sandbox.paperState.pendingKbPaperId, 'missing-doc', '未命中时必须记住待定位 ID，等列表就绪后重试');
    assert.equal(
      items(h.kbList).filter((item) => item.classList.contains(HIGHLIGHT_CLASS)).length,
      0,
      '未命中时不得高亮任何条目',
    );
  }

  // ---- 5. C-4 不回归：列表加载失败不得被覆盖成「未找到该文档」 ----
  {
    const h = makeHarness({
      fetch: async () => {
        throw new Error('网络中断');
      },
    });
    await h.sandbox.__fns.jumpToKnowledgeBase('missing-doc');
    assert.equal(
      h.kbStatus.textContent,
      '列表加载失败：网络中断',
      `列表本身加载失败时必须保留真实故障文案，实际「${h.kbStatus.textContent}」`,
    );
    assert.notEqual(
      h.sandbox.paperState.pendingKbPaperId,
      null,
      '加载失败时 pending 不得被当成「已处理」清掉（列表恢复后仍应能跳过去）',
    );
  }

  // ---- 6. 缺少稳定 ID：专门提示，且不留在 pending 里 ----
  {
    const h = makeHarness({});
    await h.sandbox.__fns.jumpToKnowledgeBase(null);
    assert.ok(
      h.kbStatus.textContent.startsWith(NEED_ID_PREFIX),
      `传入空 id 时必须提示「${NEED_ID_PREFIX}」，实际「${h.kbStatus.textContent}」`,
    );
    assert.equal(h.sandbox.paperState.pendingKbPaperId, null, '缺少 ID 时不得留下 pending');
  }

  // ---- 7. 不自动展开 / 打开文档详情 ----
  {
    const targetId = 'doc-noexpand';
    const h = makeHarness({
      initialPapers: [{ document_id: targetId }],
      fetch: async () => ({ ok: true, json: async () => ({ papers: [{ document_id: targetId }] }) }),
    });
    await h.sandbox.__fns.jumpToKnowledgeBase(targetId);
    const current = items(h.kbList).find((item) => item.dataset.documentId === targetId);
    assert.equal(current.children.length, 0, '定位不得向列表项追加详情内容（不自动展开/打开详情）');
  }

  // ---- 8. 旧 DOM 假阳性防线：目标已脱离文档时不得写「已定位」 ----
  {
    const h = makeHarness({});
    const detached = h.makeKbItem(h.doc, { document_id: 'detached-doc' });
    detached.__detached = true;
    const applied = h.sandbox.__fns.applyKbJumpFocus(detached, 'detached-doc');
    assert.equal(applied, false, '已脱离文档的节点不得被当作定位成功');
    assert.equal(detached.focused === true && detached.classList.contains(HIGHLIGHT_CLASS), false, '脱离节点不得被高亮/聚焦');
    assert.ok(
      !h.kbStatus.textContent.includes('已定位'),
      `对已脱离文档的节点不得写「已定位」假阳性文案，实际「${h.kbStatus.textContent}」`,
    );
  }

  console.log('ok - kb jump rerender (重建后定位落到新节点 / 离开清 pending / 加载失败不被覆盖)');
}

main().then(
  () => { process.exitCode = 0; },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
