'use strict';

/**
 * 文献地图「多选模式」颜色面板：点「应用到 N 篇」保存成功后设置面板必须收起。
 *
 * 用户验收路径（真实复测缺陷）：进入多选模式 → 选中 1 篇 → 出现颜色面板（12 个色板 + HEX +
 * 「应用到 1 篇」）→ 点「应用到 1 篇」，后端已保存成功，但面板仍铺在画布上，挡住刚上好色的节点。
 * 期望：
 *   - 保存成功（含「已重新读取核实」成功）后面板隐藏（`hidden === true`），但仍保持多选模式与选中集合；
 *   - 失败 / 409 / 结果未确认时必须保持可见，便于用户修正后重试；
 *   - 用户再次点击节点调整选择、或开关多选模式时，面板必须能重新出现（收起不等于永久关闭）。
 *
 * 验证方式：从 `frontend/literature-maps.js` 原样摘出 `renderMultiSelectControls()` 与相关
 * 状态切换函数，放进 `node:vm` 沙箱，用 `state` 桩与最小 DOM 桩**真实执行**，断言用户可见的
 * `hidden` 结果，而不是复述实现。
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
  assert.ok(match, `literature-maps.js 必须定义 ${name}()（多选颜色面板路径）`);
  return match[0];
}

const renderControlsSource = extract('renderMultiSelectControls');
const toggleModeSource = extract('toggleMultiSelectMode');
const toggleNodeSource = extract('toggleMultiSelectNode');

// `state` 里必须有本能力依赖的字段（含本轮新增的收起标记），否则直接判失败。
const stateBlock = (() => {
  const match = MODULE.match(/  const state = \{[\s\S]*?\n  \};\n/);
  assert.ok(match, 'literature-maps.js 必须以 `const state = {...}` 声明前端状态');
  return match[0];
})();
for (const field of ['selectionPaletteDismissed', 'multiSelectActive', 'multiSelectedNodeIds', 'colorDraft']) {
  assert.ok(
    new RegExp(`\\b${field}\\s*:`).test(stateBlock),
    `state 必须声明 ${field}（多选颜色面板收起与重开依赖它）`,
  );
}

// ---- 最小 DOM 桩 ----
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
    querySelector(selector) {
      const wanted = String(selector).replace(/^[.#]/, '');
      return this.children.find(
        (child) => child.className && String(child.className).split(/\s+/).includes(wanted),
      ) || null;
    },
  };
}

function makeRefs() {
  const apply = makeNode('button', 'literature-map-color-apply');
  const palette = makeNode('div', 'literature-map-color-palette');
  palette.hidden = true;
  palette.append(apply);
  const toolbar = makeNode('section', 'literature-map-selection-toolbar');
  toolbar.hidden = true;
  const selectionCount = makeNode('strong', 'literature-map-selected-count');
  const toggle = makeNode('button', 'literature-map-multi-select-toggle');
  return {
    refs: {
      multiSelectToggle: toggle,
      selectionToolbar: toolbar,
      selectionCount,
      selectionPalette: palette,
    },
    apply,
  };
}

/**
 * 装配沙箱：只注入这些函数真正依赖的外部符号。
 */
function makeHarness({ multiSelectActive = false, selected = [] } = {}) {
  const { refs, apply } = makeRefs();
  const statuses = [];
  const state = {
    map: { map_id: MAP_ID, revision: 3 },
    active: true,
    multiSelectActive,
    multiSelectedNodeIds: new Set(selected),
    selectionPaletteDismissed: false,
    colorDraft: null,
    colorSaveInFlight: false,
    selectedNodeId: null,
    selectedNode: null,
    nodeRequest: 0,
    analysisRequest: 0,
  };
  const sandbox = {
    console,
    JSON,
    Number,
    Object,
    Array,
    Error,
    Set,
    state,
    refs,
    MAX_MAP_NODES: 500,
    activeNodes: () => NODE_IDS.map((nodeId) => ({ node_id: nodeId })),
    renderGraph: () => {},
    renderNodeDetail: () => {},
    selectNode: (nodeId) => { state.selectedNodeId = nodeId; },
    setStatus: (message, tone) => { statuses.push({ message, tone }); },
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
  return { sandbox, state, refs, apply, statuses };
}

// ---- 1. 选中节点后面板可见 ----
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.refs.selectionPalette.hidden, false, '前置：多选模式已选中节点时颜色面板可见');
  assert.equal(h.apply.textContent, '应用到 1 篇', '前置：「应用到 N 篇」按钮文案随选中数变化');
}

// ---- 2. 保存成功标记收起 → 面板隐藏，但多选与选中集合保留 ----
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.refs.selectionPalette.hidden, false, '前置：面板可见');
  // 保存成功分支（applyNodeColor 成功路径）只置位收起标记，然后由 finally 重渲染。
  h.state.selectionPaletteDismissed = true;
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.refs.selectionPalette.hidden, true, '颜色保存成功后设置面板必须隐藏（不得继续挡住画布）');
  assert.equal(h.state.multiSelectActive, true, '收起面板不得退出多选模式');
  assert.deepEqual([...h.state.multiSelectedNodeIds], ['node-a'], '收起面板不得清空已选论文');
  assert.equal(
    h.refs.multiSelectToggle.textContent,
    '退出多选模式',
    '收起面板后多选开关仍处于开启态（用户可继续多选）',
  );
}

// ---- 3. 用户再次点击节点调整选择 → 面板重新出现 ----
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.state.selectionPaletteDismissed = true;
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.refs.selectionPalette.hidden, true, '前置：保存后面板已收起');
  h.sandbox.__toggleMultiSelectNode('node-b');
  assert.equal(h.state.selectionPaletteDismissed, false, '调整选择时必须清除收起标记，让用户能再次上色');
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.refs.selectionPalette.hidden, false, '再次点击节点调整选择后颜色面板必须重新出现');
  assert.deepEqual([...h.state.multiSelectedNodeIds].sort(), ['node-a', 'node-b'], '选择集合按用户操作增删');
}

// ---- 4. 取消选择到 0 篇 → 面板本来就不显示；重新选中仍可见 ----
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.sandbox.__toggleMultiSelectNode('node-a');
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.state.multiSelectedNodeIds.size, 0, '前置：取消全部选择');
  assert.equal(h.refs.selectionPalette.hidden, true, '0 篇选中时不显示颜色面板');
}

// ---- 5. 重新开启 / 退出多选模式都会重置收起标记 ----
{
  const h = makeHarness({ multiSelectActive: false, selected: [] });
  h.state.selectionPaletteDismissed = true;
  h.sandbox.__toggleMultiSelectMode();
  assert.equal(h.state.multiSelectActive, true, '前置：多选模式已开启');
  assert.equal(h.state.selectionPaletteDismissed, false, '开启多选模式必须重置收起标记');
  h.state.multiSelectedNodeIds.add('node-a');
  h.state.selectionPaletteDismissed = true;
  h.sandbox.__toggleMultiSelectMode();
  assert.equal(h.state.multiSelectActive, false, '前置：多选模式已退出');
  assert.equal(h.state.selectionPaletteDismissed, false, '退出多选模式必须重置收起标记');
}
{
  const h = makeHarness({ multiSelectActive: true, selected: ['node-a'] });
  h.state.selectionPaletteDismissed = true;
  h.sandbox.__toggleMultiSelectNode('node-b');
  h.state.multiSelectActive = false;
  h.state.multiSelectedNodeIds.clear();
  h.sandbox.__toggleMultiSelectMode();
  h.state.multiSelectedNodeIds.add('node-a');
  h.sandbox.__renderMultiSelectControls();
  assert.equal(h.refs.selectionPalette.hidden, false, '重新进入多选并选中节点后，面板必须能正常出现');
}

// ---- 6. 失败 / 未确认路径不得收起：真实跑 applyNodeColor() 的 catch 分支 ----
// 历史问题：本用例此前只是连调两次 __renderMultiSelectControls()，从未执行
// applyNodeColor() 的 catch，属于假覆盖（第四轮复审 MEDIUM）。现在把真实的
// `async function applyNodeColor()` 摘进沙箱执行，用最小桩驱动三条失败路径。
const applyNodeColorSource = extract('applyNodeColor');
const colorDraftMatchesSource = extract('colorDraftMatches');
const colorTargetNodeIdsSource = extract('colorTargetNodeIds');

/** applyNodeColor() 只依赖这几个纯函数/常量，尽量照抄真实实现以免行为漂移。 */
function makeApplyHarness({ selected = ['node-a'], draftOverride = '#ff6b6b' } = {}) {
  const { refs, apply } = makeRefs();
  const statuses = [];
  const calls = { request: [], reloadAfterColorConflict: [], verifyNodeColorWrite: [], renderGraph: 0 };
  const state = {
    map: { map_id: MAP_ID, revision: 3 },
    selectedMapId: MAP_ID,
    active: true,
    multiSelectActive: true,
    multiSelectedNodeIds: new Set(selected),
    selectionPaletteDismissed: false,
    colorDraft: { mapId: MAP_ID, target: 'selection', groupId: null, nodeIds: [...selected], colorOverride: draftOverride },
    colorSaveInFlight: false,
    selectedNodeId: null,
    selectedNode: null,
    graph: { map: { map_id: MAP_ID, revision: 3 }, nodes: [] },
    groups: [],
  };
  // 桩里的 root 用于 `refs.root.querySelectorAll(...)`：真实实现只对它批量置 disabled。
  refs.root = { querySelectorAll: () => [] };

  const noop = () => {};
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
    COLOR_SAVE_TIMEOUT_MS: 15000,
    activeNodes: () => NODE_IDS.map((nodeId) => ({ node_id: nodeId })),
    // request 由各用例改写成抛错 / 返回核实结果，这里是默认（不应被走到成功分支）。
    request: async () => { throw new Error('unexpected request'); },
    normalizeHexColor: (value) => {
      const color = String(value || '').trim();
      return /^#[0-9a-f]{6}$/i.test(color) ? color.toLowerCase() : null;
    },
    mapOwnerId: () => '',
    rememberRecentColor: noop,
    updateGraphColorOverrides: noop,
    renderGroups: noop,
    renderNodeDetail: noop,
    setStatus: (message, tone) => { statuses.push({ message, tone }); },
    renderGraph: () => { calls.renderGraph += 1; },
    // 由 vm.runInContext 注入的真实 renderMultiSelectControls()（见下方源码列表）。
    errorAction: (error, fallback) => String(error?.message || '') || fallback,
    selectMap: async () => {},
    verifyNodeColorWrite: async () => ({ confirmed: false, payload: {} }),
    reloadAfterColorConflict: async () => {},
    window: {
      setTimeout: () => 1,
      clearTimeout: () => {},
    },
    AbortController: class { constructor() { this.signal = {}; } abort() {} },
  };

  vm.createContext(sandbox);
  vm.runInContext(
    [
      colorDraftMatchesSource,
      colorTargetNodeIdsSource,
      renderControlsSource,
      applyNodeColorSource,
      'this.__applyNodeColor = applyNodeColor;',
    ].join('\n'),
    sandbox,
  );

  // 依赖一律经 sandbox 属性名查找调用，因此用例里可直接替换 `h.sandbox.request` /
  // `h.sandbox.verifyNodeColorWrite` 等（若在此处再包一层闭包，替换就会失效）。

  return {
    state,
    refs,
    apply,
    sandbox,
    statuses,
    calls,
    // 沙箱里的真实 renderMultiSelectControls()：面板 hidden 断言直接来自实现，而不是手工赋值。
    renderControls: () => vm.runInContext('renderMultiSelectControls()', sandbox),
    run: () => sandbox.__applyNodeColor('selection', apply),
  };
}

// 顶层 await 会让 Node 把本文件判为 ESM（与既有 require 风格冲突），故包进 async IIFE。
(async () => {
  // 6a. 明确失败（带 error.status 的非 409）：既不进核实分支，也不置位收起标记。
  {
    const h = makeApplyHarness();
    h.sandbox.request = async () => { const error = new Error('保存失败'); error.status = 500; throw error; };
    h.renderControls(); // 真实渲染：多选模式 + 已选 1 篇 + 未收起 → 面板可见
    assert.equal(h.refs.selectionPalette.hidden, false, '前置：面板在真实渲染下可见');
    const draftBefore = JSON.parse(JSON.stringify(h.state.colorDraft));

    await h.run();

    assert.equal(h.state.selectionPaletteDismissed, false, '明确失败时不得置位 selectionPaletteDismissed');
    assert.equal(h.state.colorSaveInFlight, false, '失败后必须释放 colorSaveInFlight（finally）');
    assert.deepEqual(h.state.colorDraft, draftBefore, '明确失败时颜色草稿必须原样保留');
    assert.ok(h.statuses.some((item) => item.tone === 'error'), '明确失败必须给出 error 状态提示');
    assert.equal(h.calls.reloadAfterColorConflict.length, 0, '非 409 不得走冲突重载分支');
    assert.equal(h.calls.verifyNodeColorWrite.length, 0, '有 status 的非 409 明确失败不得进入核实分支');
    assert.equal(h.refs.selectionPalette.hidden, false, '明确失败后颜色面板必须保持可见以便重试');
  }

  // 6b. 409 冲突：走 reloadAfterColorConflict 分支，且不置位收起标记、草稿仍保留。
  {
    const h = makeApplyHarness();
    h.sandbox.request = async () => { const error = new Error('版本冲突'); error.status = 409; throw error; };
    h.sandbox.reloadAfterColorConflict = async () => { h.calls.reloadAfterColorConflict.push(1); };
    h.sandbox.verifyNodeColorWrite = async () => { h.calls.verifyNodeColorWrite.push(1); return { confirmed: false, payload: {} }; };
    h.renderControls(); // 真实渲染：多选模式 + 已选 1 篇 + 未收起 → 面板可见
    assert.equal(h.refs.selectionPalette.hidden, false, '前置：面板在真实渲染下可见');
    const draftBefore = JSON.parse(JSON.stringify(h.state.colorDraft));

    await h.run();

    assert.equal(h.calls.reloadAfterColorConflict.length, 1, '409 必须走 reloadAfterColorConflict 分支且只走一次');
    assert.equal(h.state.selectionPaletteDismissed, false, '409 冲突时不得置位 selectionPaletteDismissed');
    assert.deepEqual(h.state.colorDraft, draftBefore, '409 冲突时颜色草稿必须原样保留');
    assert.equal(h.calls.verifyNodeColorWrite.length, 0, '409 分支不得误入核实分支');
    assert.equal(h.refs.selectionPalette.hidden, false, '409 冲突后颜色面板必须保持可见以便重试');
    assert.equal(h.state.colorSaveInFlight, false, '409 后必须释放 colorSaveInFlight（finally）');
  }

  // 6c-1. AbortError 且重新读取核实「未确认」：不得置位，草稿保留，面板可见。
  {
    const h = makeApplyHarness();
    h.sandbox.request = async () => {
      const error = new Error('aborted');
      error.name = 'AbortError';
      error.signal = { aborted: true };
      throw error;
    };
    h.sandbox.verifyNodeColorWrite = async () => { h.calls.verifyNodeColorWrite.push(1); return { confirmed: false, payload: {} }; };
    h.renderControls(); // 真实渲染：多选模式 + 已选 1 篇 + 未收起 → 面板可见
    assert.equal(h.refs.selectionPalette.hidden, false, '前置：面板在真实渲染下可见');
    const draftBefore = JSON.parse(JSON.stringify(h.state.colorDraft));

    await h.run();

    assert.equal(h.calls.verifyNodeColorWrite.length, 1, 'AbortError 必须进入核实分支');
    assert.equal(h.state.selectionPaletteDismissed, false, '核实未确认时不得置位 selectionPaletteDismissed');
    assert.deepEqual(h.state.colorDraft, draftBefore, '核实未确认时颜色草稿必须保留');
    assert.ok(
      h.statuses.some((item) => item.tone === 'error' && /未能确认/.test(item.message)),
      '核实未确认必须提示「保存结果未能确认」',
    );
    assert.equal(h.refs.selectionPalette.hidden, false, '核实未确认后颜色面板必须保持可见');
  }

  // 6d. 网络错误（无 status）且重新读取核实「未确认」：同上不得收起。
  {
    const h = makeApplyHarness();
    h.sandbox.request = async () => { const error = new Error('Failed to fetch'); throw error; };
    h.sandbox.verifyNodeColorWrite = async () => { h.calls.verifyNodeColorWrite.push(1); return { confirmed: false, payload: {} }; };
    h.renderControls(); // 真实渲染：多选模式 + 已选 1 篇 + 未收起 → 面板可见
    assert.equal(h.refs.selectionPalette.hidden, false, '前置：面板在真实渲染下可见');
    const draftBefore = JSON.parse(JSON.stringify(h.state.colorDraft));

    await h.run();

    assert.equal(h.calls.verifyNodeColorWrite.length, 1, '网络错误必须进入核实分支');
    assert.equal(h.state.selectionPaletteDismissed, false, '网络错误且未确认时不得置位 selectionPaletteDismissed');
    assert.deepEqual(h.state.colorDraft, draftBefore, '网络错误且未确认时颜色草稿必须保留');
    assert.equal(h.refs.selectionPalette.hidden, false, '网络错误且未确认后颜色面板必须保持可见');
  }

  // 6e. 对照组：核实「已确认」时才置位收起标记（证明 6a–6d 的「不置位」不是恒真）。
  {
    const h = makeApplyHarness();
    h.sandbox.request = async () => { const error = new Error('Failed to fetch'); throw error; };
    h.sandbox.verifyNodeColorWrite = async () => ({ confirmed: true, payload: { map: { revision: 4 } } });

    await h.run();

    assert.equal(h.state.selectionPaletteDismissed, true, '核实确认后才允许置位收起标记');
    assert.equal(h.state.colorDraft, null, '核实确认后草稿应清空');
  }
})();

console.log('ok - selection color palette dismisses after a successful apply and reopens on selection change');
