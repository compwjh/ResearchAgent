'use strict';

/**
 * 文献地图**切回后不产生 409** 的接线级契约（执行级，`node:vm`）。
 *
 * frontend-reviewer P1-1：`keepLocalView` 读路径跳过 `applySavedView`，怀疑
 * 「服务端 revision 没被吸收 → 下次 saveView 用旧 expected_revision → 409」。
 *
 * 本文件走真实链路 `LiteratureMaps.setActive(false) → setActive(true)`，服务器桩
 * 严格按真实后端的 revision 乐观锁行事（expected_revision 落后就回 409），断言：
 *
 *   1. 切回前本地已积累新改动（flush 已落地、revision 已推进到 8），切回后
 *      `state.map.revision` 必须等于服务端最新 revision；
 *   2. 切回后用户再动一次 → 唯一那次 PATCH /view 的 `expected_revision`
 *      必须等于服务端最新 revision，且**不得产生 409**、不得报错状态；
 *   3. 服务端 graph 里没有 revision 时不得把它清成 undefined（否则下次保存必 409）。
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

function constValue(name) {
  const match = MODULE.match(new RegExp(`const ${name} = ([^;]+);`));
  assert.ok(match, `literature-maps.js 必须定义 ${name}`);
  return match[1];
}

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

const CREATE_ELEMENT = slice('createElement\\(tag, className, text\\)');
const SET_HIDDEN = slice('setHidden\\(node, hidden\\)');
const NORMALIZE_STYLE = slice('normalizeNodeStyle\\(nodeStyle\\)');
const NORMALIZE_MAP = slice('normalizeMapNodeCount\\(value\\)')
  + slice('normalizeMapViewInitialized\\(map\\)')
  + slice('normalizeMap\\(map\\)')
  + slice('resolveInitialFitPending\\(map, viewportInfo = \\{\\}\\)');
const APPLY_SAVED_VIEW = slice('applySavedView\\(map\\)');
const APPLY_MAP_PAYLOAD = slice('applyMapPayload\\(payload, keepLocalView\\)');
const INITIAL_POSITION = slice('initialPosition\\(index, total\\)');
const LAYOUT_PENDING = slice('layoutPendingNodes\\(pendingNodes, existingPositions = \\{\\}, existingNodes = \\[\\]\\)');
const COUNT_SPACING = slice('countSpacingViolations\\(nodes = activeNodes\\(\\)\\)');
const MAP_VIEWPORT_WORLD_SIZE = slice('mapViewportWorldSize\\(\\)');
const LOAD_MAP_GRAPH = slice('loadMapGraph\\(mapId, options = \\{\\}\\)');
const SAVE_VIEW = slice('saveView\\(options = \\{\\}\\)');
const SCHEDULE = slice('scheduleViewSave\\(\\)');
const FLUSH = slice('flushPendingViewSave\\(options = \\{\\}\\)');
const WAIT_FLUSH = slice('waitForPendingViewFlush\\(mapId\\)');
const RESET_MAP_STATE = slice('resetMapSelectionState\\(mapId, options = \\{\\}\\)');
const SELECT_MAP = slice('selectMap\\(mapId, options = \\{\\}\\)');
const SET_ACTIVE = slice('setActive\\(active\\)');
const LOAD_MAPS = slice('loadMaps\\(options = \\{\\}\\)');

// 服务端权威 revision：每次成功的 PATCH /view 都 +1；用旧值提交回 409。
let serverRevision = 7;

const SERVER_MAP = {
  map_id: 'm1',
  name: 'A',
  topic: 't',
  status: 'ready',
  revision: 7,
  requested_count: 20,
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

function makeSandbox(options = {}) {
  const calls = [];
  const statuses = [];
  const timed = [];
  let timerId = 1;

  const sandbox = {
    console,
    MIN_MAP_SCALE: Number(constValue('MIN_MAP_SCALE')),
    INITIAL_FIT_SCALE_EPSILON: Number(constValue('INITIAL_FIT_SCALE_EPSILON')),
    LAYER_NAMES: (() => {
      const raw = MODULE.match(/const LAYER_NAMES = (\[[^\]]*\]);/);
      assert.ok(raw, 'literature-maps.js 必须定义 LAYER_NAMES');
      return JSON.parse(raw[1].replace(/'/g, '"'));
    })(),
    DEFAULT_NODE_STYLE: { fill_mode: 'filled', fill_opacity: 0.3 },
    LABEL_MODES: ['all', 'neighbors', 'hidden'],
    DEFAULT_LABEL_MODE: 'all',
    MAP_WIDTH: 1200,
    MAP_HEIGHT: 900,
    state: {
      active: false,
      mounted: true,
      maps: [],
      map: null,
      graph: null,
      selectedMapId: null,
      selectedNodeId: null,
      positions: Object.create(null),
      positionsMapId: null,
      positionsDirty: false,
      viewDirty: false,
      view: { x: 0, y: 0, scale: 1 },
      saveTimer: null,
      viewRequest: 0,
      viewSavedOnce: false,
      mapRequest: 0,
      graphRequest: 0,
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
      nodeRequest: 0,
      analysisRequest: 0,
      conversationRequest: 0,
      importRequest: 0,
      queueRequest: 0,
      previewRequest: 0,
      ...(options.state || {}),
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
    request: async (url, init = {}) => {
      const call = { url, method: init.method || 'GET' };
      calls.push(call);
      const isViewPatch = String(url).endsWith('/view') && (init.method || '') === 'PATCH';
      if (isViewPatch) {
        call.body = JSON.parse(init.body);
        if (Number(call.body.expected_revision) !== serverRevision) {
          const conflict = new Error('地图版本已变化，请重新读取后再保存。');
          conflict.status = 409;
          conflict.code = 'MAP_REVISION_CONFLICT';
          throw conflict;
        }
        serverRevision += 1;
        return {
          map: {
            ...clone(SERVER_MAP),
            revision: serverRevision,
            view_settings: { ...clone(SERVER_MAP.view_settings), viewport: clone(call.body.viewport) },
          },
        };
      }
      if (/^\/[^/]+$/.test(String(url))) {
        return { map: { ...clone(SERVER_MAP), revision: serverRevision }, latest_job: null };
      }
      if (String(url).endsWith('/graph')) {
        if (options.graphWithoutRevision) return { map: { map_id: 'm1' }, nodes: [], edges: [], layers: {}, latest_job: null };
        return {
          map: { ...clone(SERVER_MAP), revision: serverRevision },
          latest_job: null,
          nodes: [
            { node_id: 'n1', title: 'n1', position: { x: 100, y: 200 } },
            { node_id: 'n2', title: 'n2', position: { x: 300, y: 400 } },
          ],
          edges: [],
          layers: { citation: { status: 'ready' }, similarity: { status: 'ready' } },
          schema_version: '1',
        };
      }
      if (url === '' || url === undefined) {
        return { maps: [{ ...clone(SERVER_MAP), revision: serverRevision }] };
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
    activeNodes: (graph = sandbox.state.graph) => normalizeNodesFn(graph).filter((node) => !node.removed && !node.tombstone),
    normalizeNodes: (graph) => normalizeNodesFn(graph),
    normalizeEdges: (graph) => (Array.isArray(graph?.edges) ? graph.edges.filter((edge) => edge && edge.source_id && edge.target_id) : []),
    mapTitle: (map) => map?.name || map?.topic || '未命名地图',
    mapStatusLabel: (status) => String(status || ''),
    normalizeLabelMode: (value) => (['all', 'neighbors', 'hidden'].includes(String(value || '')) ? String(value) : 'all'),
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

  function normalizeNodesFn(graph) {
    return Array.isArray(graph?.nodes) ? graph.nodes.filter((node) => node && node.node_id) : [];
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

  return { sandbox, calls, statuses, timed, fns: sandbox.__fns };
}

function viewPatches(calls) {
  return calls.filter((call) => call.method === 'PATCH' && String(call.url).endsWith('/view'));
}

function tick(times = 10) {
  let p = Promise.resolve();
  for (let i = 0; i < times; i += 1) p = p.then(() => new Promise((resolve) => setTimeout(resolve, 0)));
  return p;
}

function enterMap(h) {
  h.sandbox.state.active = true;
  h.sandbox.state.map = h.fns.normalizeMap({ ...clone(SERVER_MAP), revision: serverRevision });
  h.sandbox.state.selectedMapId = 'm1';
  h.sandbox.state.graph = {
    nodes: [
      { node_id: 'n1', title: 'n1', position: { x: 100, y: 200 } },
      { node_id: 'n2', title: 'n2', position: { x: 300, y: 400 } },
    ],
    edges: [],
  };
  h.sandbox.state.positions = Object.assign(Object.create(null), {
    n1: { x: 100, y: 200 },
    n2: { x: 300, y: 400 },
  });
  h.sandbox.state.positionsMapId = 'm1';
  h.sandbox.state.view = { x: 12, y: 34, scale: 1.5 };
  h.sandbox.state.positionsDirty = false;
  h.sandbox.state.viewDirty = false;
}

async function main() {
  // ---- 1. 切回后 revision 必须跟上服务端，且下一次保存不带旧 expected_revision ----
  {
    serverRevision = 7;
    const h = makeSandbox();
    enterMap(h);

    // 用户整理视图（未落库）→ 离开触发 flush → 服务端 revision 7 → 8。
    h.sandbox.state.positions.n1 = { x: 999, y: 888 };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.viewDirty = true;
    h.fns.setActive(false);
    await tick();
    assert.equal(serverRevision, 8, '离开时的 flush 必须真的落地（服务端 revision 7 → 8）');
    assert.equal(h.sandbox.state.map.revision, 8, 'flush 落地后本地 revision 必须收口到 8');

    // 切回：重读 map + graph，keepLocalView 跳过 applySavedView。
    h.fns.setActive(true);
    await tick(16);
    assert.equal(
      h.sandbox.state.map.revision,
      8,
      `切回后 state.map.revision 必须等于服务端最新 revision，实际 ${h.sandbox.state.map.revision}`,
    );
    assert.equal(h.sandbox.state.view.scale, 1.5, '切回时本地没有未落地改动，视口应与服务端一致（不被重读改写）');

    // 切回后用户再动一次：expected_revision 必须是 8，否则真实后端回 409。
    h.sandbox.state.view = { x: 20, y: 30, scale: 1.75 };
    h.sandbox.state.viewDirty = true;
    const before = viewPatches(h.calls).length;
    const saved = await h.fns.saveView();
    assert.equal(saved, true, '切回后的保存必须成功');
    const patches = viewPatches(h.calls);
    assert.equal(patches.length, before + 1, '切回后的保存应恰好产生一次 PATCH /view');
    assert.equal(
      Number(patches[patches.length - 1].body.expected_revision),
      8,
      '切回后保存的 expected_revision 必须等于服务端最新 revision（否则 409）',
    );
    const errors = h.statuses.filter(([, status]) => status === 'error');
    assert.deepEqual(errors, [], `切回后保存不得报错（409 也不该出现），实际 ${JSON.stringify(errors)}`);
    assert.equal(serverRevision, 9, '保存成功后服务端 revision 应推进到 9');
  }

  // ---- 2. 服务端 graph 不带 revision 时不得把它清成 undefined ----
  {
    serverRevision = 11;
    const h = makeSandbox({ graphWithoutRevision: true });
    enterMap(h);
    h.sandbox.state.map = h.fns.normalizeMap({ ...clone(SERVER_MAP), revision: 11 });
    await h.fns.loadMapGraph('m1', { keepLocalView: true });
    assert.equal(
      h.sandbox.state.map.revision,
      11,
      'graph 响应缺 revision 时必须保留已知值，清成 undefined 会让下次保存必 409',
    );
    h.sandbox.state.viewDirty = true;
    const saved = await h.fns.saveView();
    assert.equal(saved, true, '缺 revision 的 graph 响应不得影响后续保存');
    assert.equal(
      Number(viewPatches(h.calls).pop().body.expected_revision),
      11,
      '后续保存仍须使用已知 revision',
    );
    const errors = h.statuses.filter(([, status]) => status === 'error');
    assert.deepEqual(errors, [], `不得产生 409，实际 ${JSON.stringify(errors)}`);
  }

  console.log('ok - map view revision on reentry (keepLocalView 后 expected_revision 不落后 / 不产生 409)');
}

main().then(
  () => { process.exitCode = 0; },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
