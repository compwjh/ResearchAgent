'use strict';

/**
 * 文献地图「多选模式」控件：多选**不再提供任何色板**（Spec043 节点分组化改造）。
 *
 * 历史背景：本文件原本守「点『应用到 N 篇』保存成功后多选色板自动收起、失败保持可见」。
 * 改造后节点颜色一律跟随所属分组，多选色板的整条链路（`selectionPaletteDismissed` /
 * `applyNodeColor` / `verifyNodeColorWrite` / `reloadAfterColorConflict` / `refs.selectionPalette`）
 * 已从实现中删除，因此本文件改写为**反向契约断言**，并保留 node:vm 真实执行方式：
 *   - 从 `frontend/literature-maps.js` 原样摘出**新的** `renderMultiSelectControls()` /
 *     `toggleMultiSelectMode()` / `toggleMultiSelectNode()` 放进 `node:vm` 沙箱真实执行；
 *   - 断言多选控件**只**维护「开关文案 / aria-pressed / 工具条显隐 / 已选计数」，
 *     不再创建、切换或引用任何色板（`refs.selectionPalette` 不存在也不被读取）；
 *   - 断言 `state` 不再声明与色板收起相关的字段；
 *   - 断言源码里已无节点/多选调色 API，并保留「分组色唯一」的正向实现入口。
 *
 * 不删除文件、不改成纯字符串 grep：真实函数仍在沙箱中被执行，只是断言改为「不再有色板」。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MODULE = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.js'), 'utf8');
const MAP_ID = 'map-fixture';
const NODE_IDS = ['node-a', 'node-b'];

// ---- 源码抽取：测的是真实实现 ----
function extract(name) {
  const match = MODULE.match(new RegExp(`  (?:async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}\\n`));
  assert.ok(match, `literature-maps.js 必须定义 ${name}()（多选控件渲染路径）`);
  return match[0];
}

const renderControlsSource = extract('renderMultiSelectControls');
const toggleModeSource = extract('toggleMultiSelectMode');
const toggleNodeSource = extract('toggleMultiSelectNode');

// ---- 1. 源码级反向契约：节点 / 多选调色 API 与「多选色板收起」状态必须已删除 ----
{
  for (const removed of [
    'applyNodeColor',
    'verifyNodeColorWrite',
    'reloadAfterColorConflict',
    'colorTargetNodeIds',
    'renderNodeColorControls',
    'updateGraphColorOverrides',
    'selectionPalette',
    'selectionPaletteDismissed',
  ]) {
    assert.equal(
      MODULE.includes(removed),
      false,
      `literature-maps.js 不得再出现 ${removed}（多选色板链路已随节点分组化删除）`,
    );
  }
  // 仍保留的能力入口必须继续存在，避免「删干净」把分组改色一起删掉。
  for (const kept of ('renderMultiSelectControls', 'createColorPalette', 'applyGroupColor', 'toggleGroupHighlight')) {
    assert.ok(MODULE.includes(kept), `literature-maps.js 必须保留 ${kept}`);
  }
}

// `state` 里不得再有与多选色板相关的字段。
const stateBlock = (() => {
  const match = MODULE.match(/  const state = \{[\s\S]*?\n  \};\n/);
  assert.ok(match, 'literature-maps.js 必须以 `const state = {...}` 声明前端状态');
  return match[0];
})();
for (const goneField of ['selectionPaletteDismissed', 'colorDraftMapIdBySelection']) {
  assert.equal(
    new RegExp(`\\b${goneField}\\s*:`).test(stateBlock),
    false,
    `state 不得再声明 ${goneField}（多选色板已删除）`,
  );
}
// 多选仍然需要的三个字段必须继续存在，否则下面的真实执行会失去意义。
for (const keptField of ['multiSelectActive', 'multiSelectedNodeIds', 'colorDraft']) {
  assert.ok(
    new RegExp(`\\b${keptField}\\s*:`).test(stateBlock),
    `state 必须继续声明 ${keptField}`,
  );
}

// ---- 最小 DOM 桩：只提供多选控件真实依赖的四个 refs ----
function makeNode(tag, className = '') {
  return {
    tagName: String(tag).toUpperCase(),
    className,
    children: [],
    hidden: false,
    disabled: false,
    textContent: '',
    dataset: {},
    attributes: {},
    append(...children) {
      this.children.push(...children);
      return undefined;
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    querySelector(selector) {
      const wanted = String(selector).replace(/^[.#]/, '');
      return this.children.find(
        (child) => child.className && String(child.className).split(/\s+/).includes(wanted),
      ) || null;
    },
  };
}

function makeRefs() {
  const toolbar = makeNode('section', 'literature-map-selection-toolbar');
  toolbar.hidden = true;
  const selectionCount = makeNode('strong', 'literature-map-selected-count');
  const toggle = makeNode('button', 'literature-map-multi-select-toggle');
  const refs = {
    multiSelectToggle: toggle,
    selectionToolbar: toolbar,
    selectionCount,
  };
  // 记录实现是否真的去碰了已删除的色板（若实现回退，这里会立刻报警）。
  const paletteTouches = [];
  Object.defineProperty(refs, 'selectionPalette', {
    configurable: true,
    get() {
      paletteTouches.push(new Error('refs.selectionPalette 被读取').stack);
      return undefined;
    },
    set() {
      paletteTouches.push(new Error('refs.selectionPalette 被写入').stack);
    },
  });
  return { refs, toggle, toolbar, selectionCount, paletteTouches };
}

/** 装配沙箱：只注入这些函数真正依赖的外部符号。 */
function makeHarness({ multiSelectActive = false, selected = [] } = {}) {
  const { refs, toggle, toolbar, selectionCount, paletteTouches } = makeRefs();
  const statuses = [];
  const state = {
    map: { map_id: MAP_ID, revision: 3 },
    active: true,
    multiSelectActive,
    multiSelectedNodeIds: new Set(selected),
    colorDraft: null,
    colorSaveInFlight: false,
    selectedNodeId: null,
    selectedNode: null,
    nodeRequest: 0,
    analysisRequest: 0,
    expansionHighlightNodeIds: new Set(),
  };
  const calls = { renderGraph: 0, renderNodeDetail: 0, selectNode: [] };
  const sandbox = {
    console,
    JSON,
    Number,
    Object,
    Array,
    Error,
    Set,
    Map,
    Boolean,
    String,
    state,
    refs,
    MAX_MAP_NODES: 500,
    activeNodes: () => NODE_IDS.map((nodeId) => ({ node_id: nodeId })),
    renderGraph: () => { calls.renderGraph += 1; },
    renderNodeDetail: () => { calls.renderNodeDetail += 1; },
    selectNode: (nodeId) => { calls.selectNode.push(nodeId); state.selectedNodeId = nodeId; },
    setStatus: (message, tone) => { statuses.push({ message, tone }); },
    setColorDraft: () => { throw new Error('多选控件不得调用 setColorDraft（色板只属于分组）'); },
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      renderControlsSource,
      toggleModeSource,
      toggleNodeSource,
      'this.__renderMultiSelectControls = renderMultiSelectControls;',
      'this.__toggleMultiSelectMode = toggleMultiSelectMode;',
      'this.__toggleMultiSelectNode = toggleMultiSelectNode;',
    ].join('\n'),
    sandbox,
  );
  return {
    sandbox,
    state,
    refs,
    toggle,
    toolbar,
    selectionCount,
    paletteTouches,
    statuses,
    calls,
    // 沙箱里的真实 renderMultiSelectControls()：断言直接来自实现，而不是手工赋值。
    renderControls: () => vm.runInContext('renderMultiSelectControls()', sandbox),
  };
}

// ---- 2. 真实执行：多选模式下选中 1 篇 → 只有工具条与计数，没有任何色板 ----
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.renderControls();
  assert.equal(h.toolbar.hidden, false, '多选工具条必须可见');
  assert.equal(h.selectionCount.textContent, '已选 1 篇', '已选计数必须随选中集合变化');
  assert.equal(h.toggle.textContent, '退出多选模式', '多选开关必须显示当前态');
  assert.equal(h.toggle.getAttribute('aria-pressed'), 'true');
  assert.deepEqual(h.paletteTouches, [], '真实渲染路径不得读取或写入 refs.selectionPalette');
}
{
  // 选中 2 篇 → 计数与文案继续正确，仍然不产生色板。
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a', 'node-b'] });
  h.renderControls();
  assert.equal(h.selectionCount.textContent, '已选 2 篇');
  assert.deepEqual(h.paletteTouches, []);
}

// ---- 3. 真实执行：没有地图 / 未开多选时不显示工具条 ----
{
  const h = makeHarness({ multiSelectActive: false, selected: [] });
  h.renderControls();
  assert.equal(h.toolbar.hidden, true, '未开启多选时工具条必须隐藏');
  assert.equal(h.toggle.textContent, '多选模式');
  assert.equal(h.toggle.getAttribute('aria-pressed'), 'false');
  assert.deepEqual(h.paletteTouches, []);
}
{
  const h = makeHarness({ multiSelectActive: true, selected: [] });
  h.state.map = null;
  h.renderControls();
  assert.equal(h.toggle.disabled, true, '没有地图时多选开关必须禁用');
  assert.deepEqual(h.paletteTouches, []);
}

// ---- 4. 真实执行：开关多选模式只改状态，不创建/收起任何色板 ----
{
  const h = makeHarness({ multiSelectActive: false, selected: [] });
  h.sandbox.__toggleMultiSelectMode();
  assert.equal(h.state.multiSelectActive, true, '开启多选模式');
  assert.equal(h.calls.renderGraph, 1, '开关多选必须重绘图谱（节点选中态）');
  assert.deepEqual(h.paletteTouches, [], '开启多选不得触碰色板');
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.selectionCount.textContent, '已选 0 篇');
  assert.deepEqual(h.paletteTouches, []);
}
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.sandbox.__toggleMultiSelectMode();
  assert.equal(h.state.multiSelectActive, false, '退出多选模式');
  assert.deepEqual([...h.state.multiSelectedNodeIds], [], '退出多选必须清空选中集合');
  assert.deepEqual(h.calls.selectNode, ['node-a'], '退出多选后回落到唯一选中节点');
  assert.deepEqual(h.paletteTouches, []);
}

// ---- 5. 真实执行：点击节点只增删选择集合，绝不触发调色 ----
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.sandbox.__toggleMultiSelectNode('node-b');
  assert.deepEqual([...h.state.multiSelectedNodeIds].sort(), ['node-a', 'node-b'], '选择集合按用户操作增删');
  assert.deepEqual(h.paletteTouches, [], '点击节点不得触碰色板');
  assert.deepEqual(h.statuses.filter((item) => item.tone === 'error'), [], '正常选择不得报错');
}
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.sandbox.__toggleMultiSelectNode('node-a');
  assert.equal(h.state.multiSelectedNodeIds.size, 0, '再次点击同一节点取消选择');
  assert.deepEqual(h.paletteTouches, []);
}
{
  // 超过上限时只给错误提示，不得顺手进入任何调色路径。
  const h = makeHarness({ multiSelectActive: true, selected: NODE_IDS.concat(['node-c']) });
  h.sandbox.MAX_MAP_NODES = 2;
  h.sandbox.__toggleMultiSelectNode('node-a');
  assert.deepEqual(h.paletteTouches, []);
}

console.log('ok - multi-select controls keep selection state only and never create or reference a color palette');
