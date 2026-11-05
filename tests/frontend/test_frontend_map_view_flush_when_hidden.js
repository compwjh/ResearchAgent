'use strict';

/**
 * 离开视图时 flush 必须真的落库（缺陷 C，执行级 `node:vm`）。
 *
 * 真实缺陷（主会话真实浏览器 E2E 抓到，单测此前未覆盖）：
 *   `showView()` 先 `hideAllMainAreas()` 隐藏所有主区，**之后**才调
 *   `window.LiteratureMaps.setActive(false)`。`setActive(false)` →
 *   `flushPendingViewSave()` → `saveView({allowInactive:true})`，但此时
 *   `#literature-maps-view` 已 hidden，真实浏览器实测 `svg.getBoundingClientRect()`
 *   为 `{width:0, height:0}` → `mapViewportWorldSize()` 返回 `valid:false` →
 *   `saveView()` 早退，PATCH 从未发出。
 *   实测现象：地图 zoom-out（DOM transform scale(2.3333)）后立即切到知识库，2 秒后
 *   `GET /api/literature-maps/{id}` 的 viewport 仍是旧 `scale:2.8`、revision 不变。
 *
 * 因此本文件把 `svg.getBoundingClientRect()` 桩成**隐藏时的真实测量值**（0×0），
 * 断言：
 *   1. `valid:false` + `allowInactive:true`（离开视图的 flush）→ **仍发 PATCH**，
 *      body.viewport 等于用户刚操作过的 `state.view`，且落地后 dirty 清零；
 *   2. 普通 active 路径（`allowInactive` 不传）且 `valid:false` → **不发 PATCH**
 *      （零尺寸守卫未被削弱，防写入 bogus 视口）；
 *   3. flush 成功后不产生 409（expected_revision 沿用 state.map.revision，并收口）。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MODULE = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.js'), 'utf8');

// 函数体在 `  }` 之后可能是空行、另一个函数，或 IIFE 收尾的 `})();`，
// 这里统一收在「独立的 `  }` 行」为止（默认 `\n  }\n` 匹配不到文件末尾那一段）。
function slice(signature) {
  const match = MODULE.match(new RegExp('  (?:async )?function ' + signature + '[\\s\\S]*?\\n  }(?=\\n)'));
  assert.ok(match, 'literature-maps.js 必须定义 ' + signature);
  return match[0] + '\n';
}

const CREATE_ELEMENT = slice('createElement\\(tag, className, text\\)');
const SET_HIDDEN = slice('setHidden\\(node, hidden\\)');
const NORMALIZE_STYLE = slice('normalizeNodeStyle\\(nodeStyle\\)');
const NORMALIZE_MAP = slice('normalizeMapNodeCount\\(value\\)')
  + slice('normalizeMapViewInitialized\\(map\\)')
  + slice('normalizeMap\\(map\\)')
  + slice('resolveInitialFitPending\\(map, viewportInfo = \\{\\}\\)');
const MAP_VIEWPORT_WORLD_SIZE = slice('mapViewportWorldSize\\(\\)');
const SAVE_VIEW = slice('saveView\\(options = \\{\\}\\)');
const SCHEDULE = slice('scheduleViewSave\\(\\)');
const FLUSH = slice('flushPendingViewSave\\(options = \\{\\}\\)');
const SET_ACTIVE = slice('setActive\\(active\\)');
const LOAD_MAPS = slice('loadMaps\\(options = \\{\\}\\)');

function makeEl(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
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

/**
 * 关键桩：模拟「视图已被 hideAllMainAreas() 隐藏」的真实浏览器测量结果。
 * 真实 Chromium 实测隐藏后 svg.getBoundingClientRect() === {width:0, height:0}。
 */
function makeSandbox(options = {}) {
  const requests = [];
  const statuses = [];
  const timed = [];
  let timerId = 1;
  let serverRevision = options.serverRevision ?? 7;
  const sandbox = {
    console,
    MIN_MAP_SCALE: Number(/const MIN_MAP_SCALE = ([0-9.]+);/.exec(MODULE)[1]),
    INITIAL_FIT_SCALE_EPSILON: Number(/const INITIAL_FIT_SCALE_EPSILON = ([0-9.]+);/.exec(MODULE)[1]),
    DEFAULT_NODE_STYLE: { fill_mode: 'filled', fill_opacity: 0.3 },
    LABEL_MODES: ['all', 'neighbors', 'hidden'],
    DEFAULT_LABEL_MODE: 'all',
    MAP_WIDTH: 1200,
    MAP_HEIGHT: 900,
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
      viewSavedOnce: false,
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
      ...(options.state || {}),
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
      // 隐藏后的真实测量值：宽高为 0 → mapViewportWorldSize() 判 valid:false。
      svg: options.svg || {
        getBoundingClientRect: () => ({ width: 0, height: 0 }),
        viewBox: { baseVal: { x: 0, y: 0, width: 1200, height: 900 } },
      },
    },
    request: async (url, init = {}) => {
      const method = init.method || 'GET';
      const call = { url: String(url), method, body: init.body ? JSON.parse(init.body) : null };
      requests.push(call);
      if (method === 'PATCH' && call.url.endsWith('/view')) {
        // 与真实后端同语义：expected_revision 过期就回 409。
        if (Number(call.body.expected_revision) !== serverRevision) {
          const conflict = new Error('地图版本已变化，请重新读取后再保存。');
          conflict.status = 409;
          conflict.code = 'MAP_REVISION_CONFLICT';
          throw conflict;
        }
        serverRevision += 1;
        return {
          map: {
            map_id: 'm1',
            name: 'A',
            topic: 't',
            status: 'ready',
            revision: serverRevision,
            view_settings: {
              viewport: { ...call.body.viewport },
              layers: { citation: true, similarity: true },
              label_mode: 'all',
              view_initialized: true,
            },
          },
        };
      }
      return { maps: [] };
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
    restoreDesktopPanelAccessibility() {},
    renderShell() {},
    errorAction: (error, fallback) => (error && error.message) || fallback,
    TERMINAL_JOB_STATES: new Set(['ready', 'partial', 'failed', 'stopped']),
    startPolling() {},
    normalizeLabelMode: (value) => String(value || 'all'),
    activeNodes: (graph = sandbox.state.graph) => (Array.isArray(graph?.nodes) ? graph.nodes.filter((n) => n && !n.removed && !n.tombstone) : []),
    normalizeNodes: (graph) => (Array.isArray(graph?.nodes) ? graph.nodes.filter((n) => n && n.node_id) : []),
    mapTitle: (map) => map?.name || '未命名地图',
    mapStatusLabel: () => '可用',
    isMobileViewport: () => false,
    closeMobilePanel() {},
    selectMap: async () => {},
    filteredMaps: () => sandbox.state.maps,
    setHidden: null,
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
    loadMaps: async () => undefined,
  };
  sandbox.globalThis = sandbox;

  const src = [
    CREATE_ELEMENT,
    SET_HIDDEN,
    NORMALIZE_STYLE,
    NORMALIZE_MAP,
    MAP_VIEWPORT_WORLD_SIZE,
    SAVE_VIEW,
    SCHEDULE,
    FLUSH,
    SET_ACTIVE,
    LOAD_MAPS,
    'this.__fns = { saveView, scheduleViewSave, flushPendingViewSave, setActive, normalizeMap, mapViewportWorldSize };',
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
      viewport: { x: 100, y: 200, scale: 2.8 },
      layers: { citation: true, similarity: true },
      label_mode: 'all',
      view_initialized: true,
    },
    ...overrides,
  };
}

function viewPatches(requests) {
  return requests.filter((call) => call.method === 'PATCH' && call.url.endsWith('/view'));
}

async function tick(times = 8) {
  let p = Promise.resolve();
  for (let i = 0; i < times; i += 1) p = p.then(() => new Promise((resolve) => setTimeout(resolve, 0)));
  return p;
}

async function main() {
  // ---- 0. 静态契约：allowInactive 必须能绕过 valid 守卫，普通路径必须仍守着 ----
  assert.ok(
    /if \(!viewport\.valid && !allowInactive\) return false;/.test(SAVE_VIEW),
    'saveView 的视口守卫必须写成 `if (!viewport.valid && !allowInactive) return false;`：'
      + '离开视图的 flush（allowInactive:true）必须放行，普通 active 路径仍必须拦截零尺寸视口',
  );
  assert.ok(
    !/if \(!viewport\.valid\) return false;/.test(SAVE_VIEW),
    'saveView 不得保留无条件的 `if (!viewport.valid) return false;`（那会让离开视图的 flush 永远发不出 PATCH）',
  );

  // ---- 1. 缺陷 C 复现：视图已隐藏（svg 0×0）时离开 → flush 仍必须落库 ----
  {
    const h = makeSandbox();
    // 先确认桩真的模拟了「隐藏」：此时视口测量无效。
    assert.equal(
      h.fns.mapViewportWorldSize().valid,
      false,
      '测试前置条件：隐藏视图下 mapViewportWorldSize() 必须返回 valid:false（否则本用例检测不到缺陷 C）',
    );

    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.graph = { nodes: [{ node_id: 'n1', position: { x: 10, y: 20 } }], edges: [] };
    h.sandbox.state.positions = Object.assign(Object.create(null), { n1: { x: 10, y: 20 } });
    // 用户刚 zoom-out 到 scale 2.3333（DOM transform 实测值），还没落库。
    h.sandbox.state.view = { x: -120.5, y: -80.25, scale: 2.3333 };
    h.sandbox.state.viewDirty = true;
    h.sandbox.state.saveTimer = 4242; // 500ms 防抖还挂着

    // 生产时序：showView() 先隐藏主区，再 setActive(false)。
    h.fns.setActive(false);
    await tick();

    const patches = viewPatches(h.requests);
    assert.equal(
      patches.length,
      1,
      `视图已隐藏（svg 0×0）时离开必须仍发出 1 次 PATCH /view，实际 ${patches.length} 次`
        + '（0 次即缺陷 C：位置/视口没落库，下次查看又是原位置）',
    );
    assert.equal(patches[0].body.expected_revision, 7, '必须沿用 state.map.revision 作为 expected_revision');
    assert.deepEqual(
      patches[0].body.viewport,
      { x: -120.5, y: -80.25, scale: 2.3333 },
      'PATCH body.viewport 必须等于用户刚操作过的 state.view（逻辑值有效，不依赖零尺寸的测量结果）',
    );
    assert.equal(
      patches[0].body.viewport.scale,
      2.3333,
      '落库的 scale 必须是 DOM 实际的 2.3333，而不是服务端旧值 2.8',
    );
    assert.equal(patches[0].body.positions.length, 1, '同一批 dirty 的位置也要一起提交');

    // ---- 3. flush 成功后 dirty 清零、revision 收口（下次保存不会 409） ----
    assert.equal(h.sandbox.state.viewDirty, false, 'flush 落地后 viewDirty 必须清零（否则每次离开都重复写库）');
    assert.equal(h.sandbox.state.positionsDirty, false, 'flush 落地后 positionsDirty 必须清零');
    assert.equal(h.sandbox.state.map.revision, 8, 'flush 成功后本地 revision 必须收口（7 → 8），避免下次保存 409');
    assert.equal(h.sandbox.state.viewSavedOnce, true, 'flush 落地后必须置位 viewSavedOnce（后续不应再自动 fit）');
    assert.equal(h.sandbox.state.saveTimer, null, 'flush 必须取消仍挂着的 500ms 防抖计时器');
    const conflict = h.statuses.find(([, status]) => status === 'error');
    assert.equal(conflict, undefined, `flush 不得产生 409/错误状态，实际 ${JSON.stringify(h.statuses)}`);

    // 再刷一次（模拟再次离开）不得重复发请求：dirty 已清零。
    h.fns.setActive(false);
    await tick(4);
    assert.equal(viewPatches(h.requests).length, 1, 'dirty 已清零后再次离开不得重复发 PATCH');
  }

  // ---- 2. 守卫未被削弱：普通 active 调用 + valid:false → 不发 PATCH ----
  {
    const h = makeSandbox();
    h.sandbox.state.active = true;
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.graph = { nodes: [{ node_id: 'n1', position: { x: 10, y: 20 } }], edges: [] };
    h.sandbox.state.positions = Object.assign(Object.create(null), { n1: { x: 10, y: 20 } });
    h.sandbox.state.view = { x: 0, y: 0, scale: 9 };
    h.sandbox.state.viewDirty = true;

    const saved = await h.fns.saveView();
    assert.equal(saved, false, '普通 active 路径在 valid:false 时必须返回 false');
    assert.equal(
      viewPatches(h.requests).length,
      0,
      '普通 active 路径且视口零尺寸时不得发 PATCH（零尺寸守卫必须保留，防写入 bogus 视口）',
    );
    assert.equal(h.sandbox.state.viewDirty, true, '被守卫拦下时不得清 dirty（等下一次有效视口再保存）');
  }

  // ---- 2b. 普通 active 的防抖调度同样不得在 valid:false 时排期 ----
  {
    const h = makeSandbox();
    h.sandbox.state.active = true;
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.viewDirty = true;
    h.fns.scheduleViewSave();
    assert.equal(h.timed.filter((entry) => !entry.cleared).length, 0, 'valid:false 时 scheduleViewSave 不得排期保存');
  }

  // ---- 2c. active 且视口有效时仍照常保存（守卫只是有条件放行，不是绕过） ----
  {
    const h = makeSandbox({
      svg: {
        getBoundingClientRect: () => ({ width: 800, height: 600 }),
        viewBox: { baseVal: { x: 0, y: 0, width: 1200, height: 900 } },
      },
    });
    h.sandbox.state.active = true;
    h.sandbox.state.map = h.fns.normalizeMap(makeMap());
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.graph = { nodes: [{ node_id: 'n1', position: { x: 10, y: 20 } }], edges: [] };
    h.sandbox.state.positions = Object.assign(Object.create(null), { n1: { x: 10, y: 20 } });
    h.sandbox.state.view = { x: 3, y: 4, scale: 1.25 };
    h.sandbox.state.viewDirty = true;
    const saved = await h.fns.saveView();
    assert.equal(saved, true, 'active 且视口有效时必须正常保存');
    assert.equal(viewPatches(h.requests).length, 1, 'active 且视口有效时必须发出 PATCH');
    assert.deepEqual(viewPatches(h.requests)[0].body.viewport, { x: 3, y: 4, scale: 1.25 });
  }

  console.log('ok - map view flush while hidden (allowInactive 放行 / 普通路径仍守零尺寸 / 落地清 dirty 不 409)');
}

main().then(
  () => { process.exitCode = 0; },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
