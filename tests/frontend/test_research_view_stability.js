'use strict';

/**
 * 任务 B：深度研究页稳定性行为探针（TDD / RED → GREEN）。
 *
 * 真实 require research-tasks.js / research-session-ui.js，在 fake DOM 上验证：
 *   1. durationText / sessionDurationText：无有效耗时显示「—」，绝不显示「0.0 秒」，
 *      并兼容后端新字段 duration_ms / started_at / completed_at；
 *   2. 主 tab 切换只切 hidden / aria-selected / tabIndex，不重建 DOM（节点引用不变）；
 *   3. renderTaskList 按 taskId 复用卡片节点，绿色「已完成」徽章原地更新（不重建）；
 *   4. 列表为空时显示「暂无研究任务」空态，不留白。
 *
 * 本文件由 test_research_view_stability_contract.py 经 subprocess 调用。
 */
const assert = require('node:assert/strict');

// ---- 最小 fake DOM -------------------------------------------------------
// 真实浏览器把含焦点元素（或其祖先）从 DOM 中移走会立即失焦；fake DOM 必须
// 复现这一点，否则「全量刷新后焦点仍在卡片内」的契约无法被真正驱动。
function blurIfFocusMoved(node) {
  const doc = globalThis.document;
  if (!doc || !doc.activeElement) return;
  let current = doc.activeElement;
  while (current) {
    if (current === node) { doc.activeElement = doc.body; return; }
    current = current.parentNode;
  }
}

function matchesClass(el, selector) {
  if (!selector || selector[0] !== '.') return false;
  const cls = selector.slice(1);
  return String(el.className || '').split(/\s+/).includes(cls);
}
function querySelector(root, selector) {
  for (const child of root.children || []) {
    if (matchesClass(child, selector)) return child;
    const deep = querySelector(child, selector);
    if (deep) return deep;
  }
  return null;
}
function makeEl(tag = 'div') {
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '',
    hidden: false, tabIndex: 0, title: '', dataset: {}, attributes: {},
    children: [], parentNode: null,
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      contains(c) { return this._set.has(c); },
      toggle(c, force) {
        const next = force === undefined ? !this._set.has(c) : Boolean(force);
        if (next) this._set.add(c); else this._set.delete(c);
        return next;
      },
    },
    appendChild(child) {
      if (!child) return child;
      const previous = this.children.indexOf(child);
      if (previous >= 0) {
        blurIfFocusMoved(child);
        this.children.splice(previous, 1);
      }
      this.children.push(child);
      child.parentNode = this;
      return child;
    },
    append(...kids) { kids.forEach((k) => this.appendChild(k)); },
    replaceChildren(...kids) { this.children = []; kids.forEach((k) => this.appendChild(k)); },
    insertBefore(node, ref) {
      const at = ref ? this.children.indexOf(ref) : -1;
      const existing = this.children.indexOf(node);
      if (existing >= 0) {
        blurIfFocusMoved(node);
        this.children.splice(existing, 1);
      }
      if (at >= 0) this.children.splice(at, 0, node); else this.children.push(node);
      node.parentNode = this;
      return node;
    },
    remove() {
      if (this.parentNode) {
        this.parentNode.children = this.parentNode.children.filter((c) => c !== this);
        this.parentNode = null;
      }
    },
    setAttribute(key, value) { this.attributes[key] = String(value); },
    getAttribute(key) { return Object.prototype.hasOwnProperty.call(this.attributes, key) ? this.attributes[key] : null; },
    removeAttribute(key) { delete this.attributes[key]; },
    querySelector(sel) { return querySelector(this, sel); },
    querySelectorAll() { return []; },
    closest() { return null; },
    get nextSibling() {
      const parent = this.parentNode;
      if (!parent) return null;
      const index = parent.children.indexOf(this);
      return index >= 0 && index + 1 < parent.children.length ? parent.children[index + 1] : null;
    },
    addEventListener() {}, removeEventListener() {},
    focus() { globalThis.document.activeElement = this; },
  };
  return el;
}

const ids = new Map();
function el(id) {
  if (!ids.has(id)) { const node = makeEl(); node.id = id; ids.set(id, node); }
  return ids.get(id);
}

const docRoot = makeEl();
const documentRef = {
  activeElement: null,
  getElementById: (id) => (ids.has(id) ? ids.get(id) : null),
  createElement: (tag) => makeEl(tag),
  querySelector: (sel) => querySelector(docRoot, sel),
  querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
  body: makeEl('body'),
};

// boot() 会因 byId('research-view') === null 提前 return，避免网络副作用，
// 但 state.document 已被设置，导出的纯/DOM 函数仍可直接使用。
globalThis.document = documentRef;
globalThis.location = { pathname: '/', search: '', hash: '', href: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.dispatchEvent = () => true;
globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({}), text: async () => '{}' });
globalThis.EventSource = class { addEventListener() {} close() {} };
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};
globalThis.console = console;

const sessionUI = require('../../frontend/research-session-ui.js');
const api = require('../../frontend/research-tasks.js');

// ---- 1. 耗时显示（两处实现都要修） ---------------------------------------
const sameInstant = '2026-01-01T00:00:00Z';
for (const [name, durationText] of [
  ['research-session-ui.durationText', sessionUI.durationText],
  ['research-tasks.sessionDurationText', api.sessionDurationText],
]) {
  assert.equal(durationText({}), '—', `${name}: 空对象应显示 —`);
  assert.equal(durationText({ duration_ms: 0 }), '—', `${name}: duration_ms=0 不应显示 0.0 秒`);
  assert.equal(durationText({ duration_ms: null }), '—', `${name}: duration_ms=null 不应显示 0.0 秒`);
  assert.equal(durationText({ created_at: sameInstant, completed_at: sameInstant, updated_at: sameInstant }), '—',
    `${name}: 演示数据（创建=完成时间）不应显示 0.0 秒`);
  assert.equal(durationText({ duration_ms: 1 }), '—', `${name}: 亚秒级耗时不应显示 0.0 秒`);
  assert.equal(durationText({ started_at: '2026-01-01T00:00:00Z', completed_at: '2026-01-01T00:00:03Z' }), '3.0 秒',
    `${name}: 兼容 started_at/completed_at 新字段`);
  assert.equal(durationText({ duration_ms: 12500 }), '13 秒', `${name}: 回归既有 13 秒契约`);
  assert.ok(!String(durationText({ duration_ms: 0 })).includes('0.0 秒'), `${name}: 不得出现 0.0 秒`);
}

// ---- 2. 主 tab：只切 hidden/aria-selected/tabIndex，不重建 DOM ------------
const tabTasks = el('research-tab-tasks');
const tabCreate = el('research-tab-create');
tabTasks.dataset.researchTab = 'tasks';
tabCreate.dataset.researchTab = 'create';
tabTasks.setAttribute('aria-controls', 'research-tabpanel-tasks');
tabCreate.setAttribute('aria-controls', 'research-tabpanel-create');
const panelTasks = el('research-tabpanel-tasks');
const panelCreate = el('research-tabpanel-create');
panelCreate.hidden = true;

assert.equal(typeof api.activateResearchTab, 'function', '必须导出 activateResearchTab 供切换复用');
const tabsBefore = [tabTasks, tabCreate];
api.activateResearchTab('create');
assert.equal(tabCreate.getAttribute('aria-selected'), 'true', '切到创建 tab 后 aria-selected=true');
assert.equal(tabTasks.getAttribute('aria-selected'), 'false', '原 tab 取消选中');
assert.equal(tabCreate.tabIndex, 0);
assert.equal(tabTasks.tabIndex, -1);
assert.equal(panelTasks.hidden, true, '研究任务面板应隐藏');
assert.equal(panelCreate.hidden, false, '创建面板应显示');
assert.equal(el('research-tab-tasks'), tabsBefore[0], '不得重建 tab DOM 节点');
assert.equal(el('research-tab-create'), tabsBefore[1], '不得重建 tab DOM 节点');
assert.equal(el('research-tabpanel-tasks'), panelTasks, '不得重建面板节点');
api.activateResearchTab('tasks');
assert.equal(panelCreate.hidden, true, '切回研究任务后创建面板隐藏');
assert.equal(panelTasks.hidden, false);
assert.equal(tabTasks.getAttribute('aria-selected'), 'true');

// ---- 3. renderTaskList key 化 diff：复用节点 + 徽章原地更新 --------------
assert.equal(typeof api.renderTaskList, 'function', '必须导出 renderTaskList 供 diff 探针');
api.state.document = documentRef;
const list = el('research-task-list');
const listEmpty = el('research-list-empty');
const taskBase = {
  research_task_id: 'task-1', research_session_id: 'session-1',
  goal_excerpt: '软件供应链攻击综述', status: 'running',
  current_plan_version: 1, created_at: '2026-01-02T00:00:00Z',
};
api.state.selectedTaskId = 'task-1';
api.state.selectedSessionId = 'session-1';
api.state.tasks = [taskBase];
api.renderTaskList();
const firstItem = list.children[0];
assert.ok(firstItem, '首次渲染应生成一张任务卡片');
const firstBadge = firstItem.querySelector('.research-badge');
assert.ok(firstBadge, '卡片应带状态徽章');
assert.equal(firstBadge.dataset.status, 'running');

// 状态推进为 completed：同一 taskId 必须复用节点，绿色徽章原地更新（不重建）
api.state.tasks = [{ ...taskBase, status: 'completed' }];
api.renderTaskList();
assert.equal(list.children[0], firstItem, '同一 taskId 必须复用卡片节点（不重建）');
assert.equal(firstItem.querySelector('.research-badge'), firstBadge, '绿色「已完成」徽章节点不得重建');
assert.equal(firstBadge.dataset.status, 'completed', '徽章 data-status 应原地更新');
assert.equal(firstBadge.textContent, '已完成', '徽章文案应原地更新');
assert.equal(list.children.length, 1, '复用后卡片数量不应翻倍');

// 新增任务：已有节点仍复用
api.state.tasks = [
  { ...taskBase, status: 'completed' },
  { ...taskBase, research_task_id: 'task-2', research_session_id: 'session-2', goal_excerpt: '第二个任务', created_at: '2026-01-03T00:00:00Z' },
];
api.renderTaskList();
assert.equal(list.children.length, 2);
assert.ok(list.children.includes(firstItem), '新增任务时旧卡片仍应复用');

// ---- 3b. 点击卡片后全量刷新不得把焦点移出卡片（D6） ----------------------
api.state.tasks = [
  { ...taskBase, status: 'completed' },
  { ...taskBase, research_task_id: 'task-2', research_session_id: 'session-2', goal_excerpt: '第二个任务', created_at: '2026-01-03T00:00:00Z' },
];
api.renderTaskList();
const focusedCard = list.children[0].querySelector('.research-task-card');
assert.ok(focusedCard, '列表首项应有可聚焦的 .research-task-card 按钮');
focusedCard.focus(); // 模拟用户点击卡片后焦点落在该按钮上
assert.ok(documentRef.activeElement === focusedCard, 'focus() 应把卡片按钮设为 activeElement');
api.renderTaskList(); // 无 onlyTaskId 的全量刷新：顺序不变，已就位节点不得被移动
assert.ok(documentRef.activeElement === focusedCard, '全量 renderTaskList 后焦点必须仍在卡片按钮上');
assert.equal(list.children.length, 2, '全量刷新不得增删卡片');
assert.ok(documentRef.activeElement.parentNode === list.children[0], '焦点元素仍须属于首张卡片');

// ---- 4. 空态：列表为空显示「暂无研究任务」 ------------------------------
api.state.tasks = [];
api.renderTaskList();
assert.equal(listEmpty.hidden, false, '列表为空时空态必须可见');
assert.match(String(listEmpty.textContent), /暂无研究任务/, '空态文案应为「暂无研究任务」');

console.log('ok - research view stability behavior contract');
