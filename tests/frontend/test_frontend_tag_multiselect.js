'use strict';

/**
 * 任务 D：文献地图「标签筛选」下拉多选行为探针（执行级，node:vm）。
 *
 * 从 frontend/literature-maps.js 原样摘出真实函数放进沙箱执行（不复制影子实现），
 * DOM 只桩到被测函数真正用到的 API。覆盖三条用户裁决：
 *   1. 多选：state.listTagIds 是 Set，可同时选中多个标签（不再单选用标量覆盖）。
 *   2. OR 过滤：filteredMaps() 命中任一已选标签即返回（不是 AND）。
 *   3. 再点取消：对同一标签再 toggle 会移出 Set；切图清空用 .clear()。
 *   4. 选中优先：收起态只渲染前 3 个 chip，且已选标签优先展示；超出显示 +N 更多。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const FRONTEND = path.resolve(__dirname, '../../frontend');
const MODULE = fs.readFileSync(path.join(FRONTEND, 'literature-maps.js'), 'utf8');
const CSS = fs.readFileSync(path.join(FRONTEND, 'literature-maps.css'), 'utf8');

// ---- 源码抽取（按花括号配平，原样不改写） ----
function sliceFunction(source, name) {
  const marker = new RegExp('function\\s+' + name + '\\s*\\(');
  const found = marker.exec(source);
  assert.ok(found, `literature-maps.js 必须定义函数 ${name}`);
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
    style: { setProperty() {} },
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; },
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    },
    contains(target) { return target === this || this.children.includes(target); },
    querySelector() { return null; },
    focus() {},
  };
  return node;
}

// ---- 1. Set 多选 + 再点取消（setTagFilter / toggleTagFilter） ----
function makeFilterSandbox() {
  const sandbox = {
    state: { listTagIds: new Set() },
    refs: { tagFilterMenu: null },
    renderMapList() {},
    renderTagFilterBar() {},
    updateTagFilterMenuCount() {},
    createElement(tag, className, text) {
      const el = makeEl(tag);
      if (className) el.className = className;
      if (text !== undefined && text !== null) el.textContent = String(text);
      return el;
    },
    document: { createElement(tag) { return makeEl(tag); } },
  };
  sandbox.document.createElement = (tag) => makeEl(tag);
  vm.createContext(sandbox);
  vm.runInContext(
    [
      sliceFunction(MODULE, 'setTagFilter'),
      sliceFunction(MODULE, 'toggleTagFilter'),
      'this.__toggle = toggleTagFilter;',
      'this.__setTagFilter = setTagFilter;',
    ].join('\n'),
    sandbox,
  );
  return sandbox;
}

{
  const s = makeFilterSandbox();
  assert.ok(s.state.listTagIds instanceof Set, 'state.listTagIds 必须是 Set（多选）');
  s.__toggle('t1');
  s.__toggle('t2');
  assert.ok(s.state.listTagIds.has('t1') && s.state.listTagIds.has('t2'),
    '多选：选中 t2 后 t1 仍在集合中（不得回退为单选标量覆盖）');
  assert.equal(s.state.listTagIds.size, 2);
  s.__toggle('t1');
  assert.ok(!s.state.listTagIds.has('t1') && s.state.listTagIds.has('t2'),
    '再点取消：对已选 t1 再次 toggle 应移出 Set，且不影响 t2');
  // 下拉 checkbox 走 setTagFilter(on, false)，不重绘筛选条，避免边选边关浮层。
  s.__setTagFilter('t3', true, false);
  assert.ok(s.state.listTagIds.has('t2') && s.state.listTagIds.has('t3'),
    '下拉 checkbox：setTagFilter(on,false) 累加选中且不清除既有项');
  s.__setTagFilter('t3', false, false);
  assert.ok(!s.state.listTagIds.has('t3'), '下拉 checkbox 取消勾选应移出 Set');
  // 切图清空语义：.clear() 一次性清空全部选中。
  s.state.listTagIds.clear();
  assert.equal(s.state.listTagIds.size, 0, '.clear() 清空全部多选');
}

// ---- 2. OR 过滤（filteredMaps） ----
function makeFilteredSandbox(maps, selectedIds) {
  const sandbox = {
    state: {
      maps,
      listQuery: '',
      listStatus: 'all',
      listTagIds: new Set(selectedIds),
    },
    mapTitle: (map) => map.title || '',
    normalizeMapNodeCount: (value) => (Number(value) > 0 ? Number(value) : 0),
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      sliceFunction(MODULE, 'filteredMaps'),
      'this.__filteredMaps = filteredMaps;',
    ].join('\n'),
    sandbox,
  );
  return sandbox;
}

{
  const maps = [
    { map_id: 'm1', title: 'A', status: 'ready', tags: [{ tag_id: 't1' }] },
    { map_id: 'm2', title: 'B', status: 'ready', tags: [{ tag_id: 't2' }] },
    { map_id: 'm3', title: 'C', status: 'ready', tags: [{ tag_id: 't1' }, { tag_id: 't2' }] },
    { map_id: 'm4', title: 'D', status: 'ready', tags: [{ tag_id: 't3' }] },
    { map_id: 'm5', title: 'E', status: 'ready', tags: [] },
  ];
  const ids = (s) => s.__filteredMaps().map((m) => m.map_id);

  assert.deepEqual(ids(makeFilteredSandbox(maps, [])),
    ['m1', 'm2', 'm3', 'm4', 'm5'], '空 Set：不过滤，返回全部地图');

  assert.deepEqual(ids(makeFilteredSandbox(maps, ['t1'])),
    ['m1', 'm3'], '单选 t1：只返回带 t1 的地图');

  // 关键 OR 断言：同时选中 t1 + t2 时，命中任一即返回（并集，不是交集）。
  assert.deepEqual(ids(makeFilteredSandbox(maps, ['t1', 't2'])),
    ['m1', 'm2', 'm3'], '多选 OR：t1∪t2 命中任一即返回（不是 AND 只留 m3）');

  assert.deepEqual(ids(makeFilteredSandbox(maps, ['tX'])),
    [], '选中不存在的标签：返回空列表');
}

// ---- 3. 选中优先 + 前 3 chip + 更多按钮 + 已选计数（renderTagFilterBar） ----
function makeBarSandbox(tags, selectedIds) {
  const bar = makeEl('div');
  const sandbox = {
    state: { tags, listTagIds: new Set(selectedIds) },
    refs: { tagFilterBar: bar, tagFilterMenu: null },
    TAG_FILTER_CHIP_LIMIT: 3,
    closeTagFilterMenu() {},
    openTagFilterMenu() {},
    normalizeHexColor: (c) => c || '',
    toggleTagFilter() {},
    createElement(tag, className, text) {
      const el = makeEl(tag);
      if (className) el.className = className;
      if (text !== undefined && text !== null) el.textContent = String(text);
      return el;
    },
    document: { createElement(tag) { return makeEl(tag); } },
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      sliceFunction(MODULE, 'renderTagFilterBar'),
      'this.__renderTagFilterBar = renderTagFilterBar;',
    ].join('\n'),
    sandbox,
  );
  return sandbox;
}

{
  const tags = ['t1', 't2', 't3', 't4', 't5'].map((id) => ({ tag_id: id, name: `标签${id}`, color: '#8d80e6' }));
  // 选中靠后的 t4、t5：收起态应把它们优先排到前 3 个 chip。
  const s = makeBarSandbox(tags, ['t4', 't5']);
  s.__renderTagFilterBar();
  assert.equal(s.refs.tagFilterBar.hidden, false, '有标签时筛选条可见');
  const list = s.refs.tagFilterBar.children.find((c) => c.className === 'literature-map-tag-filter-list');
  assert.ok(list, '渲染 .literature-map-tag-filter-list');
  const chips = list.children;
  assert.equal(chips.length, 3, '收起态只渲染前 3 个 chip（选中优先）');
  assert.deepEqual(chips.map((c) => c.dataset.tagId), ['t4', 't5', 't1'],
    '已选标签 t4/t5 优先展示，再按原顺序补齐到 3 个');
  assert.ok(chips.every((c) => c.getAttribute('aria-pressed') !== null),
    '每个 chip 保留 aria-pressed');
  assert.equal(chips[0].getAttribute('aria-pressed'), 'true', '选中 chip aria-pressed=true');
  assert.equal(chips[2].getAttribute('aria-pressed'), 'false', '未选 chip aria-pressed=false');

  const more = s.refs.tagFilterBar.children.find((c) => c.className.includes('literature-map-tag-filter-more'));
  assert.ok(more, '超出 3 个时渲染「+N 更多」按钮');
  assert.ok(more.className.includes('btn-outline'), '「更多」按钮复用 .btn-outline');
  assert.match(more.textContent, /\+2/, '「+N」显示未收起数量（total 5 - 展示 3 = +2，沿用 renderMapCardTags 的 +N 范式）');
  assert.equal(more.getAttribute('aria-expanded'), 'false', '收起态 aria-expanded=false');

  const count = s.refs.tagFilterBar.children.find((c) => c.className.includes('literature-map-tag-filter-count'));
  assert.ok(count, '收起态显示已选计数');
  assert.match(count.textContent, /2/, '已选计数 = 2');
}

// ---- 4. CSS 契约：不再折行 + 下拉浮层类存在 ----
assert.ok(/literature-map-tag-filter-list\s*\{[^}]*flex-wrap:\s*nowrap/.test(CSS),
  'literature-map-tag-filter-list 必须 flex-wrap: nowrap（不再折行）');
assert.ok(CSS.includes('.literature-map-tag-filter-menu'),
  'literature-maps.css 必须定义下拉浮层 .literature-map-tag-filter-menu');
assert.ok(CSS.includes('.literature-map-tag-filter-more'),
  'literature-maps.css 必须定义 .literature-map-tag-filter-more');

console.log('tag multiselect: PASS (Set 多选/OR 过滤/再点取消/选中优先 3 chip/+N 更多/已选计数/CSS)');
