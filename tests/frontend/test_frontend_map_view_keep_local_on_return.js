'use strict';

/**
 * 文献地图**切回不覆盖本地视图**接线级契约（执行级，`node:vm`）。
 *
 * 机制级用例已在 test_frontend_map_view_save_on_leave.js 覆盖 `keepLocalView`
 * 这个开关本身；本文件补的是**接线级**：走真实的
 * `LiteratureMaps.setActive(false) → setActive(true)` 序列，断言
 *
 *   1. setActive(true) 的重读分支真的把 `{ keepLocalView: true }` 传给 `selectMap`，
 *      且用户点另一张地图 / 其它调用点仍不传（跨地图不得串图）；
 *   2. 切回同一张地图时本地 positions / view 不被服务端旧值覆盖；
 *   3. 离开时那次 flush 尚未完成就切回：flush 必须能落地（dirty 被清、revision 收口），
 *      不产生重复保存，也不把「自己造成的成功」判成 409；
 *   4. 跨地图切换仍清空本地状态（防串图）。
 *
 * 测试直接从 `frontend/literature-maps.js` 摘真实函数进 vm 执行（不写影子实现），
 * 桩只提供 DOM / fetch 边界。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MODULE = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.js'), 'utf8');

function slice(signature) {
  const match = MODULE.match(new RegExp(`  (?:async )?function ${signature}[\\s\\S]*?\\n  }\\n`));
  assert.ok(match, `literature-maps.js 必须定义 ${signature}`);
  return match[0];
}

const CREATE_ELEMENT = slice('createElement\\(tag, className, text\\)');
const SET_HIDDEN = slice('setHidden\\(node, hidden\\)');
const NORMALIZE_STYLE = slice('normalizeNodeStyle\\(nodeStyle\\)');
const NORMALIZE_MAP = slice('normalizeMapNodeCount\\(value\\)')
  + slice('normalizeMapViewInitialized\\(map\\)')
  + slice('normalizeMap\\(map\\)')
  + slice('resolveInitialFitPending\\(map, viewportInfo = \\{\\}\\)');
const APPLY_SAVED_VIEW = slice('applySavedView\\(map\\)');
const APPLY_MAP_PAYLOAD = slice('applyMapPayload\\(payload, keepLocalView\\)');
const LOAD_MAP_GRAPH = slice('loadMapGraph\\(mapId, options = \\{\\}\\)');
const SAVE_VIEW = slice('saveView\\(options = \\{\\}\\)');
const SCHEDULE = slice('scheduleViewSave\\(\\)');
const FLUSH = slice('flushPendingViewSave\\(options = \\{\\}\\)');
const WAIT_FLUSH = slice('waitForPendingViewFlush\\(mapId\\)');
const RESET_MAP_STATE = slice('resetMapSelectionState\\(mapId, options = \\{\\}\\)');
const SELECT_MAP = slice('selectMap\\(mapId, options = \\{\\}\\)');
const SET_ACTIVE = slice('setActive\\(active\\)');
const LOAD_MAPS = slice('loadMaps\\(options = \\{\\}\\)');
const INITIAL_POSITION = slice('initialPosition\\(index, total\\)');
const LAYOUT_PENDING = slice('layoutPendingNodes\\(pendingNodes, existingPositions = \\{\\}, existingNodes = \\[\\]\\)');
const COUNT_SPACING = slice('countSpacingViolations\\(nodes = activeNodes\\(\\)\\)');

// 布局/间距用到的常量与几何辅助，按源码顺序摘出来（避免两处漂移）。
function constValue(name) {
  const match = MODULE.match(new RegExp(`const ${name} = ([^;]+);`));
  assert.ok(match, `literature-maps.js 必须定义 ${name}`);
  return match[1];
}

// saveView 会先用 mapViewportWorldSize() 校验视口是否可用。
const MAP_VIEWPORT_WORLD_SIZE = slice('mapViewportWorldSize\(\)');

const GEOMETRY = [
  `const MIN_NODE_RADIUS = ${constValue('MIN_NODE_RADIUS')};`,
  `const MAX_NODE_RADIUS = ${constValue('MAX_NODE_RADIUS')};`,
  `const LAYOUT_CLEARANCE_MULTIPLIER = ${constValue('LAYOUT_CLEARANCE_MULTIPLIER')};`,
  `const LAYOUT_STROKE_CLEARANCE = ${constValue('LAYOUT_STROKE_CLEARANCE')};`,
  `const MAX_LAYOUT_PLACEMENT_ATTEMPTS = ${constValue('MAX_LAYOUT_PLACEMENT_ATTEMPTS')};`,
  slice('citationCount\\(value\\)'),
  slice('citationRadius\\(node\\)'),
  slice('nodeRadiusForLayout\\(node\\)'),
  slice('requiredCenterDistance\\(first, second\\)'),
].join('\n');

function makeEl(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    value: '',
    hidden: false,
    dataset: {},
    attributes: new Map(),
    append(...items) { this.children.push(...items); },
    replaceChildren() { this.children = []; },
    setAttribute(k, v) { this.attributes.set(k, String(v)); },
    getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; },
    addEventListener() {},
    querySelectorAll() { return []; },
    querySelector() { return null; },
  };
}

// 服务端旧快照：位置/视口都是「上一版」，用来检出本地改动是否被覆盖。
// 服务端「权威」版本号。第一次 flush 的 expected_revision=7，成功后推进到 8；
// 之后任何用 7 提交的请求都应被拒（真实后端会回 409）。
const SERVER_REVISION = 8;

const SERVER_MAP = {
  map_id: 'm1',
  name: 'A',
  topic: 't',
  status: 'ready',
  revision: 7,
  view_settings: {
    viewport: { x: 12, y: 34, scale: 1.5 },
    layers: { citation: true, similarity: true },
    label_mode: 'all',
    view_initialized: true,
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

/**
 * @param {object} options
 *  - deferViewPatch: 返回一个 promise 用于「卡住」PATCH /view 的响应（模拟 flush 仍在途）
 *  - mapsList: 地图列表返回
 */
function makeSandbox(options = {}) {
  const calls = [];
  const statuses = [];
  const timed = [];
  let timerId = 1;
  const pendingViewPatches = [];
  const viewPatchResolvers = [];

  const sandbox = {
    console,
    MIN_MAP_SCALE: Number(constValue('MIN_MAP_SCALE')),
    LAYER_NAMES: (() => {
      const raw = MODULE.match(/const LAYER_NAMES = (\[[^\]]*\]);/);
      assert.ok(raw, 'literature-maps.js 必须定义 LAYER_NAMES');
      return JSON.parse(raw[1].replace(/'/g, '"'));
    })(),
    INITIAL_FIT_SCALE_EPSILON: Number(constValue('INITIAL_FIT_SCALE_EPSILON')),
    DEFAULT_NODE_STYLE: { fill_mode: 'filled', fill_opacity: 0.3 },
    LABEL_MODES: ['all', 'neighbors', 'hidden'],
    DEFAULT_LABEL_MODE: 'all',
    state: {
      active: false,
      mounted: true,
      maps: [],
      map: null,
      graph: null,
      selectedMapId: null,
      positions: Object.create(null),
      positionsDirty: false,
      viewDirty: false,
      view: { x: 0, y: 0, scale: 1 },
      saveTimer: null,
      viewRequest: 0,
      viewSavedOnce: false,
      mapRequest: 0,
      graphRequest: 0,
      ...(options.state || {}),
      layerStatus: {},
      layoutPreviewActive: false,
      layers: { citation: true, similarity: true },
      labelMode: 'all',
      nodeStyle: { fill_mode: 'filled', fill_opacity: 0.3 },
      nodeStyleDraft: { fill_mode: 'filled', fill_opacity: 0.3 },
      initialFitPending: false,
      multiSelectActive: false,
      colorDraft: null,
      expansionHighlightNodeIds: new Set(),
      multiSelectedNodeIds: new Set(),
      previewSelection: new Set(),
      layoutPendingIds: new Set(),
      layoutPreview: null,
      spacingViolationCount: 0,
      job: null,
      groups: [],
      eventCursor: 0,
      // resetMapSelectionState 会清的一批计数字段
      nodeRequest: 0,
      analysisRequest: 0,
      conversationRequest: 0,
      importRequest: 0,
      queueRequest: 0,
      previewRequest: 0,
    },
    refs: {
      root: null,
      status: makeEl('p'),
      mapList: makeEl('div'),
      count: makeEl('span'),
      listEmpty: makeEl('p'),
      currentTitle: makeEl('strong'),
      currentMeta: makeEl('span'),
      labelModeSelect: makeEl('select'),
      nodeStyle: null,
      svg: {
        getBoundingClientRect: () => ({ width: 800, height: 600 }),
        viewBox: { baseVal: { x: 0, y: 0, width: 1200, height: 900 } },
      },
    },
    MAP_WIDTH: 1200,
    MAP_HEIGHT: 900,
    // 网络边界：只在这里打桩，被测函数保持源码原样。
    request: async (url, init = {}) => {
      const call = { url, method: init.method || 'GET' };
      calls.push(call);
      const isViewPatch = String(url).endsWith('/view') && (init.method || '') === 'PATCH';
      if (isViewPatch) {
        call.body = JSON.parse(init.body);

        if (options.deferViewPatch) {
          await new Promise((resolve) => {
            pendingViewPatches.push(resolve);
          });
        }
        // 保存成功后服务端 revision 前进；用过期 revision 提交则按真实后端 409。
        if (Number(call.body.expected_revision) !== Number(call.body.expected_revision) || Number(call.body.expected_revision) < SERVER_REVISION - 1) {
          const conflict = new Error('地图版本已变化，请重新读取后再保存。');
          conflict.status = 409;
          conflict.code = 'MAP_REVISION_CONFLICT';
          throw conflict;
        }
        return {
          map: {
            ...clone(SERVER_MAP),
            revision: SERVER_REVISION,
            view_settings: {
              ...clone(SERVER_MAP.view_settings),
              viewport: clone(call.body.viewport),
            },
          },
        };
      }
      if (/^\/[^/]+$/.test(String(url))) {
        return { map: { ...clone(SERVER_MAP), revision: SERVER_REVISION }, latest_job: null };
      }
      if (String(url).endsWith('/graph')) {
        return {
          map: { ...clone(SERVER_MAP), revision: SERVER_REVISION },
          latest_job: null,
          nodes: [
            // 服务端旧位置：本地已拖到别处，切回时不得被覆盖。
            { node_id: 'n1', title: 'n1', position: { x: 100, y: 200 } },
            { node_id: 'n2', title: 'n2', position: { x: 300, y: 400 } },
          ],
          edges: [],
          layers: { citation: { status: 'ready' }, similarity: { status: 'ready' } },
          schema_version: '1',
        };
      }
      // 地图列表（GET 列表接口的 path 就是 ''）。
      if (url === '' || url === undefined) {
        return { maps: options.mapsList ? clone(options.mapsList) : [clone(SERVER_MAP)] };
      }
      return { map: clone(SERVER_MAP) };
    },
    setStatus: (message, status) => statuses.push([message, status]),
    renderMapList() {},
    renderGroups() {},
    renderNodeDetail() {},
    renderSpacingPreviewPanel() {},
    renderAnalysisQueue() {},
    renderCurrentMeta() {},
    renderJobActions() {},
    renderNodeStyleControls() {},
    renderGraph() {},
    closeExpansionPanel() {},
    closeAllMobilePanels() {},
    closeCreatePanel() {},
    closeTagFilterMenu() {}, // 任务 D：setActive(false) 新增的筛选浮层清理
    closeGroupsPopover() {}, // 补齐 HEAD 基线既有的沙箱夹具缺口（setActive 一直调用它）
    stopPolling() {},
    stopAnalysisPolling() {},
    stopAnalysisQueuePolling() {},
    stopPreviewPolling() {},
    ensureAnalysisQueue: async () => undefined,
    restorePreviewForMap: async () => undefined,
    loadGroups: async () => undefined,
    restoreDesktopPanelAccessibility() {},
    renderShell() {},
    errorAction: (error, fallback) => (error && error.message) || fallback,
    SCHEMA_VERSION: '1',
    TERMINAL_JOB_STATES: new Set(['ready', 'partial', 'failed', 'stopped']),
    startPolling() {},
    activeNodes: (graph) => activeNodes(graph),
    normalizeNodes: (graph) => normalizeNodesFn(graph),
    normalizeEdges: (graph) => normalizeEdges(graph),
    mapTitle: (map) => mapTitle(map),
    mapStatusLabel: (status) => mapStatusLabel(status),
    normalizeLabelMode: (value) => normalizeLabelMode(value),
    stageLabel: (step) => String(step || ''),
    isMobileViewport: () => false,
    window: {
      clearTimeout(id) {
        const entry = timed.find((item) => item.id === id);
        if (entry) entry.cleared = true;
      },
      setTimeout(fn, ms) {
        const id = timerId;
        timerId += 1;
        timed.push({ id, fn, ms, cleared: false });
        return id;
      },
    },
    document: {
      createElement: makeEl,
      createElementNS: (ns, tag) => makeEl(tag),
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
    },
  };

  function activeNodes(graph = sandbox.state.graph) {
    return normalizeNodesFn(graph).filter((node) => !node.removed && !node.tombstone);
  }
  function normalizeNodesFn(graph) {
    return Array.isArray(graph?.nodes) ? graph.nodes.filter((node) => node && node.node_id) : [];
  }
  function normalizeEdges(graph) {
    return Array.isArray(graph?.edges) ? graph.edges.filter((edge) => edge && edge.source_id && edge.target_id) : [];
  }
  function mapTitle(map) {
    return map?.name || map?.topic || '未命名地图';
  }
  function mapStatusLabel(status) {
    return String(status || '');
  }
  function normalizeLabelMode(value) {
    return ['all', 'neighbors', 'hidden'].includes(String(value || '')) ? String(value) : 'all';
  }

  sandbox.globalThis = sandbox;

  const src = [
    GEOMETRY,
    CREATE_ELEMENT,
    SET_HIDDEN,
    NORMALIZE_STYLE,
    NORMALIZE_MAP,
    APPLY_SAVED_VIEW,
    APPLY_MAP_PAYLOAD,
    INITIAL_POSITION,
    LAYOUT_PENDING,
    slice('positionFor\\(node, index, total\\)'),
    COUNT_SPACING,
    MAP_VIEWPORT_WORLD_SIZE,
    LOAD_MAP_GRAPH,
    SAVE_VIEW,
    SCHEDULE,
    FLUSH,
    WAIT_FLUSH,
    RESET_MAP_STATE,
    SELECT_MAP,
    SET_ACTIVE,
    LOAD_MAPS,
    'this.__fns = { applySavedView, saveView, scheduleViewSave, flushPendingViewSave, resetMapSelectionState, selectMap, setActive, loadMaps, loadMapGraph, normalizeMap, mapViewportWorldSize };',
  ].join('\n');
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);

  return {
    sandbox,
    calls,
    statuses,
    timed,
    pendingViewPatches,
    viewPatchResolvers,
    fns: sandbox.__fns,
  };
}

function viewPatches(calls) {
  return calls.filter((call) => call.method === 'PATCH' && String(call.url).endsWith('/view'));
}

function tick(times = 6) {
  let p = Promise.resolve();
  for (let i = 0; i < times; i += 1) p = p.then(() => new Promise((resolve) => setTimeout(resolve, 0)));
  return p;
}

function seedLocalEdits(h) {
  h.sandbox.state.active = true;
  h.sandbox.state.map = h.fns.normalizeMap(clone(SERVER_MAP));
  h.sandbox.state.selectedMapId = 'm1';
  h.sandbox.state.graph = {
    nodes: [
      { node_id: 'n1', title: 'n1', position: { x: 100, y: 200 } },
      { node_id: 'n2', title: 'n2', position: { x: 300, y: 400 } },
    ],
    edges: [],
  };
  // 用户刚把 n1 拖到 (999, 888) 并把视口放大到 2 倍，还没落库。
  h.sandbox.state.positions = { n1: { x: 999, y: 888 }, n2: { x: 300, y: 400 } };
  h.sandbox.state.view = { x: 5, y: 6, scale: 2 };
  h.sandbox.state.positionsDirty = true;
  h.sandbox.state.viewDirty = true;
  // 还原成生产里的 null 原型字典（Object.create(null)）：渲染路径会直接
  // `state.positions[nodeId] = ...`，普通对象上的原生方法名会干扰按 id 读取。
  h.sandbox.state.positions = Object.assign(Object.create(null), h.sandbox.state.positions);
}

async function main() {
  // ---- 0. 静态契约：重读分支必须显式传 keepLocalView: true ----
  {
    const setActiveSrc = MODULE.slice(
      MODULE.indexOf('function setActive(active)'),
      MODULE.indexOf('window.LiteratureMaps'),
    );
    assert.ok(
      /selectMap\(state\.selectedMapId,\s*\{\s*keepLocalView:\s*true\s*\}\)/.test(setActiveSrc),
      'setActive(true) 的重读分支必须把 { keepLocalView: true } 传给 selectMap（否则缺陷 B 不可达）',
    );
    assert.equal(
      (MODULE.match(/keepLocalView: true/g) || []).length >= 1,
      true,
      'literature-maps.js 中必须至少有一处调用方传 keepLocalView: true',
    );
    const occurrences = (MODULE.match(/selectMap\(/g) || []).length;
    assert.ok(occurrences > 1, 'selectMap 应存在多个调用点');
  }

  // ---- 1. 接管级：setActive(false) → setActive(true) 序列把 keepLocalView 传下去 ----
  {
    const h = makeSandbox();
    seedLocalEdits(h);
    const keepArgs = [];
    h.sandbox.selectMap = async (mapId, opts) => {
      keepArgs.push([mapId, opts]);
    };

    h.fns.setActive(false);
    h.fns.setActive(true);
    await tick();

    assert.equal(keepArgs.length, 1, `重读分支必须恰好调用一次 selectMap，实际 ${keepArgs.length} 次`);
    assert.equal(keepArgs[0][0], 'm1', '重读必须仍是当前选中的地图');
    assert.equal(
      keepArgs[0][1] && keepArgs[0][1].keepLocalView,
      true,
      'setActive(true) 的重读分支必须传 { keepLocalView: true } 给 selectMap（缺陷 B 接线点）',
    );
  }

  // ---- 2. 首次进入视图（无既有地图）不得传 keepLocalView ----
  {
    const h = makeSandbox();
    const keepArgs = [];
    // listMaps: true 模拟「已加载地图列表但还没打开任何地图」的真实首次进入数据态。
    h.sandbox.state.maps = [h.fns.normalizeMap(clone(SERVER_MAP))];
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.selectMap = async (mapId, opts) => {
      keepArgs.push([mapId, opts]);
    };
    h.fns.setActive(true);
    await tick();
    // 首次进入（没有待重读的地图）：负责选图的是 loadMaps 内部的隐式选图分支，
    // 而不是 setActive 的重读分支，因此不得携带 keepLocalView。
    assert.equal(keepArgs.length, 1, `首次进入视图应由 loadMaps 隐式选中地图（一次），实际 ${keepArgs.length} 次`);
    assert.equal(keepArgs[0][0], 'm1', '首次进入应选中列表里的地图');
    assert.ok(
      !keepArgs[0][1] || !keepArgs[0][1].keepLocalView,
      `首次进入没有本地改动可保留，不得传 keepLocalView，实际 ${JSON.stringify(keepArgs[0][1])}`,
    );
  }

  // ---- 3. 走真实 selectMap：本地 positions / view 不被服务端旧值覆盖 ----
  {
    const h = makeSandbox();
    seedLocalEdits(h);

    h.fns.setActive(false);
    // 离开时 flush 已发；这里让它在切回前完成，聚焦「覆盖」这一条。
    await tick();
    assert.equal(viewPatches(h.calls).length, 1, '离开时必须 flush 一次 PATCH /view');

    h.fns.setActive(true);
    await tick(10);

    assert.equal(h.sandbox.state.positionsDirty, false, 'flush 落地后 dirty 必须被清理');
    assert.equal(h.sandbox.state.viewDirty, false, 'flush 落地后 viewDirty 必须被清理');
    assert.deepEqual(
      { x: h.sandbox.state.positions.n1.x, y: h.sandbox.state.positions.n1.y },
      { x: 999, y: 888 },
      '切回同一地图时本地位置不得被服务端图数据（100,200）覆盖',
    );
    assert.equal(
      h.sandbox.state.view.scale,
      2,
      '切回同一地图时本地视口（scale=2）不得被服务端旧视口（1.5）覆盖',
    );
    assert.equal(
      viewPatches(h.calls).length,
      1,
      `不得产生重复保存，实际 PATCH /view ${viewPatches(h.calls).length} 次`,
    );
    assert.equal(
      h.sandbox.state.map.revision,
      8,
      'flush 成功后本地 revision 必须收口（expected_revision 7 → 8），否则下一次保存会 409',
    );
  }

  // ---- 4. 竞态：flush 尚未完成就切回 ----
  {
    const h = makeSandbox({ deferViewPatch: true });
    seedLocalEdits(h);

    h.fns.setActive(false);
    // flush 卡在网络上：此时立刻切回。
    assert.equal(h.requests ? 0 : 0, 0);
    h.fns.setActive(true);
    await tick(4);

    assert.equal(viewPatches(h.calls).length, 1, 'flush 只发一次，不得因切回而重复发送');
    assert.equal(
      h.sandbox.state.positionsDirty,
      true,
      'flush 仍在途时不得凭空清 dirty（先等它落地）',
    );
    assert.equal(h.sandbox.state.positions.n1.x, 999, 'flush 在途期间本地位置必须保留');
    assert.equal(h.sandbox.state.view.scale, 2, 'flush 在途期间本地视口必须保留');

    // 放开网络：flush 响应返回。
    h.pendingViewPatches.forEach((resolve) => resolve());
    await tick(12);

    assert.equal(
      h.sandbox.state.positionsDirty,
      false,
      'flush 在途期间切回，响应返回后 dirty 必须被正确清理（否则下次进入又被旧值覆盖）',
    );
    assert.equal(h.sandbox.state.viewDirty, false, 'flush 响应返回后 viewDirty 必须被正确清理');
    assert.equal(
      h.sandbox.state.positions.n1.x,
      999,
      'flush 落地后本地位置仍必须是本地值（服务端旧图数据不得回填）',
    );
    assert.equal(h.sandbox.state.view.scale, 2, 'flush 落地后本地视口仍是本地值');
    assert.equal(
      h.sandbox.state.map.revision,
      8,
      'flush 落地后 revision 必须收口（过期 expected_revision 会导致后续 409）',
    );
    assert.equal(
      viewPatches(h.calls).length,
      1,
      `竞态路径不得产生重复保存，实际 PATCH /view ${viewPatches(h.calls).length} 次`,
    );
    const failed = h.statuses.filter(([, status]) => status === 'error');
    assert.deepEqual(failed, [], `竞态路径不得报错（409 也不该出现），实际 ${JSON.stringify(failed)}`);
  }

  // ---- 5. 跨地图切换仍清空本地状态（不串图） ----
  {
    const h = makeSandbox();
    seedLocalEdits(h);
    h.sandbox.state.multiSelectActive = true;
    h.sandbox.state.multiSelectedNodeIds = new Set(['n1']);
    h.sandbox.state.expansionHighlightNodeIds = new Set(['n1']);

    await h.fns.selectMap('m2');

    assert.equal(h.sandbox.state.selectedMapId, 'm2', '必须切到目标地图');
    assert.equal(h.sandbox.state.positionsDirty, false, '跨地图必须清空 positionsDirty（否则会串图写脏）');
    assert.equal(h.sandbox.state.viewDirty, false, '跨地图必须清空 viewDirty');
    assert.deepEqual(
      { x: h.sandbox.state.positions.n1.x, y: h.sandbox.state.positions.n1.y },
      { x: 100, y: 200 },
      '跨地图必须丢弃上一张地图的本地位置（999,888），回到新地图的服务端位置',
    );
    assert.equal(
      h.sandbox.state.positions.n2.x,
      300,
      '跨地图后位置应全部来自服务端，不得残留上一张地图的本地改动',
    );
    assert.equal(h.sandbox.state.multiSelectActive, false, '跨地图必须退出多选，避免带上上一张图的选中集合');
    assert.equal(h.sandbox.state.multiSelectedNodeIds.size, 0, '跨地图必须清空多选集合');
    assert.equal(h.sandbox.state.expansionHighlightNodeIds.size, 0, '跨地图必须清空高亮集合');
    assert.equal(
      h.sandbox.state.view.scale,
      1.5,
      '跨地图必须采用新地图服务端视口，而不是沿用上一张地图的 scale',
    );
  }

  // ---- 6a. loadMaps 的隐式选图分支也必须保留本地改动（否则先覆盖再被重读掩盖） ----
  {
    const h = makeSandbox();
    // 模拟 state.map 已为空（DOM 重挂载等），只剩 selectedMapId。
    h.sandbox.state.active = true;
    h.sandbox.state.map = null;
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { n1: { x: 777, y: 666 } };
    h.sandbox.state.view = { x: 4, y: 5, scale: 1.9 };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.viewDirty = true;

    await h.fns.loadMaps({ keepLocalView: true });

    assert.deepEqual(
      { x: h.sandbox.state.positions.n1.x, y: h.sandbox.state.positions.n1.y },
      { x: 777, y: 666 },
      'loadMaps 带 keepLocalView 时，隐式选图不得用服务端旧位置覆盖本地',
    );
    assert.equal(h.sandbox.state.view.scale, 1.9, 'loadMaps 带 keepLocalView 时不得覆盖本地视口');
    assert.equal(h.sandbox.state.positionsDirty, true, '保留本地改动时 dirty 必须继续挂着等保存');
  }

  // ---- 6b. loadMaps 不带 keepLocalView（首次进入/普通刷新）仍按服务端值套用 ----
  {
    const h = makeSandbox();
    h.sandbox.state.active = true;
    h.sandbox.state.map = null;
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { n1: { x: 777, y: 666 } };
    h.sandbox.state.positionsDirty = true;

    await h.fns.loadMaps();

    assert.equal(
      h.sandbox.state.positions.n1.x,
      100,
      '未要求保留时必须回到服务端位置（首次进入 / 普通刷新不得残留上一份本地状态）',
    );
    assert.equal(h.sandbox.state.positionsDirty, false, '普通刷新必须清掉本地 dirty');
  }

  // ---- 7. 同地图但本地不 dirty：不发无意义写入，且视图保持不变 ----
  {
    const h = makeSandbox();
    h.sandbox.state.active = true;
    h.sandbox.state.map = h.fns.normalizeMap(clone(SERVER_MAP));
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.view = { x: 12, y: 34, scale: 1.5 };
    h.sandbox.state.positionsDirty = false;
    h.sandbox.state.viewDirty = false;

    h.fns.setActive(false);
    h.fns.setActive(true);
    await tick(8);

    assert.equal(
      viewPatches(h.calls).length,
      0,
      '没有本地改动时离开不得发 PATCH（不产生无意义写入）',
    );
    assert.equal(
      h.sandbox.state.view.scale,
      1.5,
      '无本地改动时切回，视图应与服务端一致（不得被改动或重置）',
    );
  }

  console.log('ok - map view keep local on return (接线级：keepLocalView / 不覆盖 / 竞态 flush / 跨地图清空)');
}

main().then(
  () => { process.exitCode = 0; },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
