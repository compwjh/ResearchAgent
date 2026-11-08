'use strict';

/**
 * 文献地图**视图保存**契约（执行级，`node:vm`）。
 *
 * 用户验收反馈：「地图我已经整理过间距，但跳转回去又变初始的展示模式，我希望对地图
 * 的操作是会保存的」。只读复现显示后端确实存下了 viewport 与 position，问题全在前端：
 *
 *   A. `setActive(false)` 只 `clearTimeout(state.saveTimer)`，把 500ms 防抖里的
 *      `positionsDirty / viewDirty` 直接**丢弃**；`saveView()` 又因 `!state.active`
 *      早退，即使请求发出也不落地 → 离开即丢改动。
 *   B. 切回时 `selectMap()` 清空 `positionsDirty / viewDirty` 并用服务端旧值覆盖，
 *      同一次会话里未落地的本地改动被抹掉。
 *   C. `initialFitPending` 用 `savedScale <= 0.36` 或 `(x=0,y=0,scale=1)` **猜**
 *      「视图未初始化」，于是用户显式保存过的重置视图（重置按钮正好写 (0,0,1)）
 *      再次打开时被自动 fit 掉 → 表现为「回到初始展示」。
 *
 * 本文件把 `frontend/literature-maps.js` 的真实函数摘进 `node:vm` 执行（不复制影子
 * 实现），断言：
 *   1. 离开（setActive(false)）时 dirty 立即 flush 一次，且这次 flush 能真正落地；
 *   2. 干净离开不产生多余请求；
 *   3. 切回同一地图且本地仍有 dirty 时，不清空本地状态、不被服务端旧值覆盖；
 *   4. `initialFitPending` 由显式标记决定：旧后端兼容、显式保存 (0,0,1) 不再 fit、
 *      最小缩放的正常保存也不再 fit、revision===0 的新图仍 fit；
 *   5. 不改 `PATCH /view` 请求体契约（字段集合不变）。
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
const SAVE_VIEW = slice('saveView\\(options = \\{\\}\\)');
const SCHEDULE = slice('scheduleViewSave\\(\\)');
const FLUSH = slice('flushPendingViewSave\\(options = \\{\\}\\)');
const RESET_MAP_STATE = slice('resetMapSelectionState\\(mapId, options = \\{\\}\\)');
const WAIT_FLUSH = slice('waitForPendingViewFlush\\(mapId\\)');
const SELECT_MAP = slice('selectMap\\(mapId, options = \\{\\}\\)');
const ON_MAP_READY = slice('onMapLoaded\\(payload, requestId, mapId\\)');
const SET_ACTIVE = slice('setActive\\(active\\)');
const LOAD_MAPS = slice('loadMaps\\(options = \\{\\}\\)');

// ---- 最小 DOM / 环境桩 ----
function makeEl(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    hidden: false,
    dataset: {},
    attributes: new Map(),
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren() {
      this.children = [];
    },
    setAttribute(k, v) {
      this.attributes.set(k, String(v));
    },
    getAttribute(k) {
      return this.attributes.has(k) ? this.attributes.get(k) : null;
    },
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
    querySelector() {
      return null;
    },
  };
}

function makeSandbox(overrides = {}) {
  const requests = [];
  const statuses = [];
  const timed = [];
  let timerId = 1;
  const sandbox = {
    console,
    // 与生产实现一致的常量（从源码抓取，避免两处漂移）
    MIN_MAP_SCALE: /const MIN_MAP_SCALE = ([0-9.]+);/.exec(MODULE)[1] * 1,
    INITIAL_FIT_SCALE_EPSILON: /const INITIAL_FIT_SCALE_EPSILON = ([0-9.]+);/.exec(MODULE)[1] * 1,
    DEFAULT_NODE_STYLE: { fill_mode: 'filled', fill_opacity: 0.3 },
    LABEL_MODES: ['all', 'neighbors', 'hidden'],
    DEFAULT_LABEL_MODE: 'all',
    state: {
      active: true,
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
      mapRequest: 0,
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
      ...(overrides.state || {}),
    },
    refs: {
      root: null,
      mapList: makeEl('div'),
      count: makeEl('span'),
      listEmpty: makeEl('p'),
      currentTitle: makeEl('strong'),
      currentMeta: makeEl('span'),
      labelModeSelect: makeEl('select'),
      nodeStyle: null,
      svg: { getBoundingClientRect: () => ({ width: 800, height: 600 }), viewBox: { baseVal: { x: 0, y: 0, width: 1200, height: 900 } } },
    },
    MAP_WIDTH: 1200,
    MAP_HEIGHT: 900,
    request: async (url, options) => {
      requests.push({ url, options });
      return {
        map: {
          map_id: 'm1',
          revision: 42,
          name: 'A',
          topic: 't',
          status: 'ready',
          view_settings: {
            viewport: { x: 12, y: 34, scale: 1.5 },
            view_initialized: true,
          },
        },
      };
    },
    setStatus: (message, status) => statuses.push([message, status]),
    renderMapList() {},
    renderGroups() {},
    renderNodeDetail() {},
    renderGraphStub() {},
    renderSpacingPreviewPanel() {},
    renderAnalysisQueue() {},
    renderCurrentMeta() {},
    renderJobActions() {},
    renderNodeStyleControls() {},
    renderGraph() {},
    renderMultiSelectControls() {},
    closeExpansionPanel() {},
    closeAllMobilePanels() {},
    closeCreatePanel() {},
    closeTagFilterMenu() {}, // 任务 D：setActive(false) 新增的筛选浮层清理
    closeGroupsPopover() {}, // 补齐 HEAD 基线既有的沙箱夹具缺口（setActive 一直调用它）
    stopPolling() {},
    stopAnalysisPolling() {},
    stopAnalysisQueuePolling() {},
    stopPreviewPolling() {},
    stopPreviewPolling() {},
    ensureAnalysisQueue: async () => undefined,
    restorePreviewForMap: async () => undefined,
    loadGroups: async () => undefined,
    loadMapGraph: async () => undefined,
    restoreDesktopPanelAccessibility() {},
    renderShell() {},
    errorAction: (error, fallback) => (error && error.message) || fallback,
    TERMINAL_JOB_STATES: new Set(['ready', 'partial', 'failed', 'stopped']),
    startPolling() {},
    normalizeLabelMode: (value) => String(value || 'all'),
    activeNodes: (graph = sandbox.state.graph) => (Array.isArray(graph?.nodes) ? graph.nodes : []),
    normalizeNodes: (graph) => (Array.isArray(graph?.nodes) ? graph.nodes.filter((n) => n && n.node_id) : []),
    mapTitle: (map) => map?.name || '未命名地图',
    mapStatusLabel: () => '可用',
    isMobileViewport: () => false,
    closeMobilePanel() {},
    selectMap: overrides.selectMap || function selectMapStub() {},
    filteredMaps: () => sandbox.state.maps,
    setHidden: null,
    mapViewportWorldSize: () => ({ x: 0, y: 0, width: 1200, height: 900, cssScale: 1, valid: true }),
    fitView: () => true,
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
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    loadMaps: overrides.loadMaps || (async () => undefined),
  };
  sandbox.globalThis = sandbox;

  const src = [
    CREATE_ELEMENT,
    SET_HIDDEN,
    NORMALIZE_STYLE,
    NORMALIZE_MAP,
    APPLY_SAVED_VIEW,
    SAVE_VIEW,
    SCHEDULE,
    FLUSH,
    RESET_MAP_STATE,
    SELECT_MAP,
    ON_MAP_READY,
    WAIT_FLUSH,
    SET_ACTIVE,
    LOAD_MAPS,
    'this.__fns = { applySavedView, saveView, scheduleViewSave, flushPendingViewSave, resetMapSelectionState, selectMap, setActive, normalizeMap };',
  ].join('\n');
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { sandbox, requests, statuses, timed, fns: sandbox.__fns };
}

function makeMap(overrides = {}) {
  return {
    map_id: 'm1',
    name: 'A',
    topic: 't',
    status: 'ready',
    revision: 7,
    requested_count: 20,
    view_settings: {
      viewport: { x: 100, y: 200, scale: 1.5 },
      layers: { citation: true, similarity: true },
      label_mode: 'all',
      view_initialized: true,
    },
    ...overrides,
  };
}

async function main() {
  // ---- 0. 契约自检：生产实现必须提供离开时 flush 的入口 ----
  assert.ok(
    /function flushPendingViewSave\(/.test(MODULE),
    '退出视图时必须有一个显式的 flush 入口（不能只 clearTimeout 丢改动）',
  );
  const setActiveSrc = MODULE.slice(
    MODULE.indexOf('function setActive(active)'),
    MODULE.indexOf('window.LiteratureMaps'),
  );
  const elseBranch = setActiveSrc.slice(setActiveSrc.indexOf('} else {'));
  assert.ok(
    /flushPendingViewSave\(/.test(elseBranch),
    'setActive(false) 分支必须调用 flushPendingViewSave()（不能只 clearTimeout 丢改动）',
  );
  assert.ok(
    !/window\.clearTimeout\(state\.saveTimer\)/.test(elseBranch),
    'setActive(false) 分支不得再直接 clearTimeout 丢弃待保存的视图',
  );

  // ---- 1. 离开时 flush dirty 且真的落地 ----
  {
    const h = makeSandbox();
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { n1: { x: 10, y: 20 } };
    h.sandbox.state.graph = { nodes: [{ node_id: 'n1', position: { x: 10, y: 20 } }] };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.viewDirty = true;
    h.sandbox.state.saveTimer = 99; // 模拟 500ms 防抖仍挂着

    h.fns.setActive(false);
    // flush 是异步落地：这里等一次微任务洪泛，让 PATCH 的 await 链走完。
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(h.sandbox.state.active, false, 'setActive(false) 必须真的离开视图');
    assert.equal(
      h.requests.length,
      1,
      `离开时 dirty 必须立即 flush 一次 PATCH /view，实际请求 ${h.requests.length} 次`,
    );
    const call = h.requests[0];
    assert.ok(call.url.includes('/view'), `flush 必须打 PATCH .../view，实际 ${call.url}`);
    assert.equal(call.options.method, 'PATCH');
    const body = JSON.parse(call.options.body);
    assert.deepEqual(
      Object.keys(body).sort(),
      ['expected_revision', 'label_mode', 'layers', 'positions', 'viewport'],
      'PATCH /view 请求体字段集合必须保持不变（不改契约）',
    );
    assert.equal(body.positions.length, 1, '必须把本地改动的位置一起提交');
    assert.equal(body.expected_revision, 7, '必须沿用现有 expected_revision（409 策略不变）');

    await Promise.resolve();
    await Promise.resolve();
    assert.equal(h.sandbox.state.positionsDirty, false, '离开时这一次 flush 必须真正落地（清除 dirty）');
    assert.equal(h.sandbox.state.viewDirty, false, '离开时这一次 flush 必须真正落地（清除 view dirty）');
  }

  // ---- 2. 干净离开不产生多余请求 ----
  {
    const h = makeSandbox();
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.positionsDirty = false;
    h.sandbox.state.viewDirty = false;
    h.fns.setActive(false);
    assert.equal(h.requests.length, 0, '没有 dirty 时离开不得发 PATCH（避免无意义写入与 409）');
  }

  // ---- 3. 切回同一地图：本地 dirty 不被清空、不被服务端旧值覆盖 ----
  {
    const h = makeSandbox({ selectMap: undefined });
    h.sandbox.state.active = true;
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { n1: { x: 999, y: 888 } };
    h.sandbox.state.view = { x: 5, y: 6, scale: 2 };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.viewDirty = true;

    // 显式 keepLocalView（切回同一地图的路径）→ 保留本地未落地改动。
    h.fns.resetMapSelectionState('m1', { keepLocalView: true });
    assert.deepEqual(
      { x: h.sandbox.state.positions.n1.x, y: h.sandbox.state.positions.n1.y },
      { x: 999, y: 888 },
      '切回同一地图且本地 dirty 时不得清空本地位置（否则又被旧值覆盖）',
    );
    assert.equal(h.sandbox.state.positionsDirty, true, '切回时本地 positionsDirty 必须保持');
    assert.equal(h.sandbox.state.viewDirty, true, '切回时本地 viewDirty 必须保持');
    assert.equal(h.sandbox.state.view.scale, 2, '切回时本地视口必须保持');

    // 未显式传 keepLocalView（例如用户点了另一张地图）→ 保持原有清空语义。
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { n1: { x: 999, y: 888 } };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.viewDirty = true;
    h.fns.resetMapSelectionState('m1');
    assert.equal(h.sandbox.state.positionsDirty, false, '未要求保留时必须维持原有清空语义');

    // 切到另一张地图则仍是老行为（清空），否则会串图。
    h.fns.resetMapSelectionState('m2');
    assert.equal(h.sandbox.state.positionsDirty, false, '切到另一张地图时必须清空 dirty（不串图）');
    assert.deepEqual(Object.keys(h.sandbox.state.positions), [], '切到另一张地图时必须清空本地位置');
  }

  // ---- 4. 切回同一地图时不消费待保存计时器、不从服务端覆盖 ----
  {
    const h = makeSandbox();
    h.sandbox.state.active = true;
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { n1: { x: 1, y: 1 } };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.layoutPreviewActive = false;
    h.sandbox.state.positions = { n1: { x: 1, y: 1 } };
    h.sandbox.state.view = { x: 3, y: 4, scale: 2 };
    h.sandbox.state.positionsDirty = true;
    h.sandbox.state.viewDirty = true;
    await h.fns.selectMap('m1', { keepLocalView: true });
    assert.equal(
      h.sandbox.state.positionsDirty,
      true,
      '切回同一地图后本地 dirty 必须仍然存在（未被 selectMap 链路清掉）',
    );
    assert.equal(h.sandbox.state.positions.n1.x, 1, '切回同一地图时不得用服务端旧位置覆盖本地');
    assert.equal(
      h.sandbox.state.view.scale,
      2,
      'keepLocalView 时不得用服务端旧 viewport（scale=1.5）覆盖本地视口（本地 scale=2）',
    );
  }

  // ---- 5. initialFitPending：显式标记优先，不再用 (0,0,1) / 最小缩放猜 ----
  // 5a. 旧后端（无标记）且已有非默认视口 → 不 fit
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({ view_settings: { viewport: { x: 100, y: 200, scale: 1.5 } } }));
    assert.equal(h.sandbox.state.initialFitPending, false, '已有非默认视口的旧地图不得自动 fit');
  }
  // 5b. 旧后端（既无标记也拿不到 revision）且是后端默认 (0,0,1) → 兼容旧行为，仍 fit 一次
  {
    const h = makeSandbox();
    const legacy = makeMap({ view_settings: { viewport: { x: 0, y: 0, scale: 1 } } });
    delete legacy.revision;
    h.fns.applySavedView(legacy);
    assert.equal(
      h.sandbox.state.initialFitPending,
      true,
      '旧后端默认 (0,0,1) 且无任何显式信息时必须兼容性地 fit 一次',
    );
  }
  // 5b-2. 旧后端无标记，但本次会话已成功保存过视图（用户点了重置并存下 (0,0,1)）
  //       → 不再自动 fit（修复「又变初始展示模式」的直接原因）
  {
    const h = makeSandbox();
    h.sandbox.state.viewSavedOnce = true;
    h.fns.applySavedView(makeMap({
      revision: 9,
      view_settings: { viewport: { x: 0, y: 0, scale: 1 } },
    }));
    assert.equal(
      h.sandbox.state.initialFitPending,
      false,
      '本次会话已保存过视图时，(0,0,1) 也不得再自动 fit（那可能是用户重置后保存的视图）',
    );
  }
  // 5b-3. 保存成功会置位 viewSavedOnce（写完立刻收口，避免后续重新进入又 fit）
  {
    const h = makeSandbox();
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.graph = { nodes: [{ node_id: 'n1', position: { x: 1, y: 2 } }] };
    h.sandbox.state.positions = { n1: { x: 1, y: 2 } };
    h.sandbox.state.viewDirty = true;
    h.sandbox.state.initialFitPending = true;
    await h.fns.saveView();
    assert.equal(h.sandbox.state.viewSavedOnce, true, '视图保存成功后必须置位 viewSavedOnce');
    assert.equal(h.sandbox.state.initialFitPending, false, '保存成功后必须清掉 initialFitPending');
  }
  // 5c. 显式保存过 (0,0,1)（如点了「重置视图」）→ 不得再自动 fit
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({
      view_settings: { viewport: { x: 0, y: 0, scale: 1 }, view_initialized: true },
    }));
    assert.equal(
      h.sandbox.state.initialFitPending,
      false,
      '用户显式保存过 (0,0,1) 时不得再自动 fit（这就是「又变初始展示模式」的直接原因）',
    );
  }
  // 5d. 最小缩放的正常保存 → 不得 fit
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({
      view_settings: { viewport: { x: 10, y: 10, scale: 0.35 }, view_initialized: true },
    }));
    assert.equal(h.sandbox.state.initialFitPending, false, '最小缩放也是有效保存，不得判为未初始化');
  }
  // 5e. 全新地图 revision===0 且无视口 → fit
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({ revision: 0, view_settings: {} }));
    assert.equal(h.sandbox.state.initialFitPending, true, '全新地图（revision=0、无视口）仍必须自动 fit 一次');
  }
  // 5f. 有显式标记 true 但没有视口字段 → 不 fit（用户已明确保存过视图）
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({ revision: 12, view_settings: { view_initialized: true } }));
    assert.equal(
      h.sandbox.state.initialFitPending,
      false,
      '显式标记为已初始化时，即便缺 viewport 也不得覆盖用户视图',
    );
  }

  // ---- 6. 显式标记为 false 时仍 fit（后端明确「未初始化」） ----
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({
      view_settings: { viewport: { x: 0, y: 0, scale: 1 }, view_initialized: false },
    }));
    assert.equal(h.sandbox.state.initialFitPending, true, 'view_initialized=false 必须 fit 一次');
  }

  console.log('ok - map view save on leave (flush dirty / 不覆盖本地 / 显式 initialFit 标记)');
}

main().then(
  () => { process.exitCode = 0; },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
