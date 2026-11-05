'use strict';

/**
 * 首开 fit 判定 + revision 收口 + 跨图 positions 守卫（执行级，`node:vm`）。
 *
 * 集中复审/回归发现的三处缺口，本文件逐条钉住：
 *
 *   1. 阻塞 1（frontend-tester 判 BLOCKED）：上一轮把旧启发式
 *      `savedScale <= MIN_MAP_SCALE + INITIAL_FIT_SCALE_EPSILON → fit`
 *      （提交 61096ed6 `fix(maps): fit unreadable opening views` 的既有 UX 契约）整段删掉了，
 *      于是「没有 view_initialized 标记 + 极小缩放（0.35）」被当成有效视图，
 *      首次打开时停在 0.35 倍、完全不可读。
 *      修法：以「是否有显式保存证据」分流——有证据（view_initialized===true 或本次会话
 *      viewSavedOnce）绝不 fit；无任何证据时才恢复旧启发式。
 *
 *   2. P1-2（frontend-reviewer）：`loadMapGraph` 只看 `state.positions[node_id]` 是否存在，
 *      不校验这些位置属于哪张地图；跨图时节点 id 相同时会沿用上一张图的坐标。
 *
 *   3. P1-1（frontend-reviewer）：`keepLocalView` 读路径跳过 `applySavedView` 后，
 *      `view_settings` 期间可能拿到旧快照；`state.map` 必须吸收服务端 revision，
 *      下一次 `saveView` 的 `expected_revision` 才不会落后触发 409。
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
  + slice('normalizeMap\\(map\\)');
const RESOLVE_FIT = slice('resolveInitialFitPending\\(map, viewportInfo = \\{\\}\\)');
const APPLY_SAVED_VIEW = slice('applySavedView\\(map\\)');
const RESET_MAP_STATE = slice('resetMapSelectionState\\(mapId, options = \\{\\}\\)');
const LOAD_MAP_GRAPH = slice('loadMapGraph\\(mapId, options = \\{\\}\\)');

function makeEl(tag) {
  const el = {
    tagName: String(tag || 'div').toUpperCase(),
    children: [],
    dataset: {},
    style: {},
    classList: {
      _set: new Set(),
      add(name) { this._set.add(name); },
      remove(name) { this._set.delete(name); },
      contains(name) { return this._set.has(name); },
      toggle(name, force) {
        const want = force === undefined ? !this._set.has(name) : Boolean(force);
        if (want) this._set.add(name); else this._set.delete(name);
        return want;
      },
    },
    setAttribute() {},
    removeAttribute() {},
    appendChild(child) { this.children.push(child); return child; },
    addEventListener() {},
    removeEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  el.textContent = '';
  return el;
}

function makeSandbox(overrides = {}) {
  const requested = [];
  const statuses = [];
  const sandbox = {
    console,
    MIN_MAP_SCALE: /const MIN_MAP_SCALE = ([0-9.]+);/.exec(MODULE)[1] * 1,
    INITIAL_FIT_SCALE_EPSILON: /const INITIAL_FIT_SCALE_EPSILON = ([0-9.]+);/.exec(MODULE)[1] * 1,
    DEFAULT_NODE_STYLE: { fill_mode: 'filled', fill_opacity: 0.3 },
    LABEL_MODES: ['all', 'neighbors', 'hidden'],
    DEFAULT_LABEL_MODE: 'all',
    LAYER_NAMES: ['citation', 'similarity'],
    MAP_WIDTH: 960,
    MAP_HEIGHT: 680,
    state: {
      active: true,
      mounted: true,
      map: null,
      graph: null,
      selectedMapId: null,
      selectedNodeId: null,
      positions: Object.create(null),
      positionsMapId: null,
      multiSelectActive: false,
      multiSelectedNodeIds: new Set(),
      expansionHighlightNodeIds: new Set(),
      colorDraft: null,
      analysisHistory: [],
      multiSelectActive: false,
      previewSelection: new Set(),
      previewConflict: false,
      positionsDirty: false,
      viewDirty: false,
      view: { x: 0, y: 0, scale: 1 },
      initialFitPending: false,
      viewSavedOnce: false,
      layers: { citation: true, similarity: true },
      labelMode: 'all',
      nodeStyle: { fill_mode: 'filled', fill_opacity: 0.3 },
      nodeStyleDraft: { fill_mode: 'filled', fill_opacity: 0.3 },
      layoutPendingIds: new Set(),
      graphRequest: 0,
      mapRequest: 0,
      layerStatus: {},
      spacingViolationCount: 0,
      saveTimer: null,
      ...(overrides.state || {}),
    },
    refs: {
      root: null,
      currentTitle: makeEl('strong'),
      currentMeta: makeEl('span'),
      labelModeSelect: makeEl('select'),
      svg: {
        getBoundingClientRect: () => ({ width: 800, height: 600 }),
        viewBox: { baseVal: { x: 0, y: 0, width: 960, height: 680 } },
      },
    },
    request: async (url) => {
      requested.push(url);
      if (overrides.graphPayload) return overrides.graphPayload;
      return {
        schema_version: 'literature-map-v1',
        map: { map_id: 'm1', revision: 5, view_settings: { viewport: { x: 0, y: 0, scale: 1 } } },
        nodes: [],
        edges: [],
        layers: {},
        latest_job: null,
      };
    },
    setStatus: (message, status) => statuses.push([message, status]),
    normalizeNodes: (graph) => (Array.isArray(graph?.nodes) ? graph.nodes.filter((n) => n && n.node_id) : []),
    normalizeEdges: () => [],
    activeNodes: (graph) => (Array.isArray(graph?.nodes) ? graph.nodes.filter((n) => !n.removed && !n.tombstone) : []),
    initialPosition: (index, total) => ({ x: 100 + index * 10, y: 100 + total }),
    layoutPendingNodes: (pending) => Object.fromEntries(pending.map((node, index) => [node.node_id, { x: 500 + index, y: 500 }])),
    countSpacingViolations: () => 0,
    fitView: () => true,
    renderCurrentMeta() {},
    renderGraph() {},
    renderJobActions() {},
    renderNodeStyleControls() {},
    scheduleViewSave() {},
    selectNode() {},
    closeExpansionPanel() {},
    renderMapList() {},
    renderGroups() {},
    renderNodeDetail() {},
    renderSpacingPreviewPanel() {},
    renderAnalysisQueue() {},
    stopPolling() {},
    stopAnalysisPolling() {},
    stopAnalysisQueuePolling() {},
    stopPreviewPolling() {},
        mapTitle: (map) => map?.name || '未命名地图',
    mapStatusLabel: () => '可用',
    errorAction: (error, fallback) => (error && error.message) || fallback,
    normalizeLabelMode: (value) => String(value || 'all'),
    TERMINAL_JOB_STATES: new Set(['ready', 'partial', 'failed', 'stopped']),
    window: { clearTimeout() {}, setTimeout: () => 1 },
    document: {
      createElement: makeEl,
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
    },
  };
  sandbox.globalThis = sandbox;

  const src = [
    CREATE_ELEMENT,
    SET_HIDDEN,
    NORMALIZE_STYLE,
    NORMALIZE_MAP,
    RESOLVE_FIT,
    APPLY_SAVED_VIEW,
    RESET_MAP_STATE,
    LOAD_MAP_GRAPH,
    'this.__fns = { applySavedView, loadMapGraph, resolveInitialFitPending, normalizeMap, resetMapSelectionState };',
  ].join('\n');
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { sandbox, requested, statuses, fns: sandbox.__fns };
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

// fixture `tests/frontend/fixtures/literature_map_component.html:189` 的真实数值：
// `?tiny-saved-view` 把 viewport 设成 {x:218.19, y:185.00, scale:0.35}，且**没有** view_initialized。
const TINY_VIEWPORT = { x: 218.19159296052774, y: 185.0037455589592, scale: 0.35 };

async function main() {
  // ---- 1. 阻塞 1：无显式证据 + 极小缩放 → 必须 fit（恢复 61096ed6 的 UX 契约） ----
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({ revision: 3, view_settings: { viewport: { ...TINY_VIEWPORT } } }));
    assert.equal(
      h.sandbox.state.initialFitPending,
      true,
      '无 view_initialized 标记、本次会话也没保存过时，0.35 的极小缩放不可读，首开必须 fit（fixture ?tiny-saved-view 的回归点）',
    );
  }
  // 1b. 旧后端无标记 + 缩放到 MIN_MAP_SCALE + EPSILON 边界内 → 仍 fit
  {
    const h = makeSandbox();
    const boundary = h.sandbox.MIN_MAP_SCALE + h.sandbox.INITIAL_FIT_SCALE_EPSILON;
    h.fns.applySavedView(makeMap({ view_settings: { viewport: { x: 12, y: 34, scale: boundary } } }));
    assert.equal(h.sandbox.state.initialFitPending, true, '缩放在极小阈值内仍视为不可读，必须 fit');
  }
  // 1c. 无标记但缩放明显可读 → 不 fit（不能反过来把正常视图也 fit 掉）
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({
      view_settings: { viewport: { x: 12, y: 34, scale: h.sandbox.MIN_MAP_SCALE + h.sandbox.INITIAL_FIT_SCALE_EPSILON + 0.01 } },
    }));
    assert.equal(h.sandbox.state.initialFitPending, false, '缩放已超出极小阈值时不得覆盖用户视图');
  }
  // ---- 2. 带 view_initialized=true 且 scale=0.35 → 绝不 fit（用户真的保存过） ----
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({
      view_settings: { viewport: { x: 218.19, y: 185.0, scale: 0.35 }, view_initialized: true },
    }));
    assert.equal(
      h.sandbox.state.initialFitPending,
      false,
      'view_initialized=true 表示用户显式保存过视图，即使缩放是 0.35 也不得自动 fit',
    );
  }
  // 2b. 本次会话保存过（viewSavedOnce）且 scale=0.35 → 绝不 fit
  {
    const h = makeSandbox({ state: { viewSavedOnce: true } });
    h.fns.applySavedView(makeMap({ view_settings: { viewport: { ...TINY_VIEWPORT } } }));
    assert.equal(h.sandbox.state.initialFitPending, false, '本次会话保存过视图时，0.35 也不得再自动 fit');
  }
  // 2c. explicit===false → fit
  {
    const h = makeSandbox();
    h.fns.applySavedView(makeMap({
      view_settings: { viewport: { x: 10, y: 10, scale: 1.5 }, view_initialized: false },
    }));
    assert.equal(h.sandbox.state.initialFitPending, true, 'view_initialized=false 是后端明确的未初始化，必须 fit');
  }

  // ---- 3. P1-2：跨图时不得沿用上一张图的坐标 ----
  {
    const h = makeSandbox({
      graphPayload: {
        map: { map_id: 'm1', revision: 4 },
        nodes: [{ node_id: 'shared-node', position: { x: 11, y: 22 } }],
        edges: [],
        layers: {},
        latest_job: null,
      },
    });
    // 上一张图（m0）留下的同名节点坐标，贴着图纸左上角，与 m1 服务端坐标明显不同。
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { 'shared-node': { x: -999, y: -999 } };
    h.sandbox.state.positionsMapId = 'm0';
    await h.fns.loadMapGraph('m1');
    assert.deepEqual(
      { ...h.sandbox.state.positions['shared-node'] },
      { x: 11, y: 22 },
      '跨图时 node_id 相同的旧图坐标必须被丢弃，改用本图服务端坐标',
    );
    assert.equal(h.sandbox.state.positionsMapId, 'm1', 'positions 归属必须更新为当前地图');
  }
  // 3b-0. 归属未知（positionsMapId 尚未记录）时按跨图处理：宁可重排，也不沿用不明坐标
  {
    const h = makeSandbox({
      graphPayload: {
        map: { map_id: 'm1', revision: 4 },
        nodes: [{ node_id: 'shared-node', position: { x: 11, y: 22 } }],
        edges: [],
        layers: {},
        latest_job: null,
      },
    });
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { 'shared-node': { x: -999, y: -999 } };
    h.sandbox.state.positionsMapId = null;
    await h.fns.loadMapGraph('m1', { keepLocalView: true });
    assert.deepEqual(
      { ...h.sandbox.state.positions['shared-node'] },
      { x: 11, y: 22 },
      '归属未知的坐标必须按跨图处理，不得被 keepLocalView 当作本地改动保留',
    );
  }
  // 3b. 同图 keepLocalView 时仍保留本地坐标（不得因新增守卫误伤）
  {
    const h = makeSandbox({
      graphPayload: {
        map: { map_id: 'm1', revision: 4 },
        nodes: [{ node_id: 'shared-node', position: { x: 11, y: 22 } }],
        edges: [],
        layers: {},
        latest_job: null,
      },
    });
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positions = { 'shared-node': { x: 700, y: 400 } };
    h.sandbox.state.positionsMapId = 'm1';
    await h.fns.loadMapGraph('m1', { keepLocalView: true });
    assert.deepEqual(
      { ...h.sandbox.state.positions['shared-node'] },
      { x: 700, y: 400 },
      '同一张地图上 keepLocalView 必须保留本地未落地的坐标',
    );
  }
  // 3c. resetMapSelectionState 的归属维护：keepLocalView 标当前图、清空时置 null
  {
    const h = makeSandbox();
    h.sandbox.state.active = true;
    h.sandbox.state.positions = { 'shared-node': { x: 700, y: 400 } };
    h.sandbox.state.positionsMapId = null;
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.positionsDirty = true;
    h.fns.resetMapSelectionState('m1', { keepLocalView: true });
    assert.equal(
      h.sandbox.state.positionsMapId,
      'm1',
      '同图保留本地坐标时必须把归属标成当前地图，否则 loadMapGraph 的跨图守卫会误清',
    );
    h.fns.resetMapSelectionState('m2');
    assert.equal(h.sandbox.state.positionsMapId, null, '清空坐标时归属必须一并置空');
  }

  // ---- 4. P1-1：loadMapGraph 必须吸收服务端 revision（saveView 的 expected_revision 来源） ----
  {
    const h = makeSandbox({
      graphPayload: {
        map: { map_id: 'm1', revision: 42, view_settings: { viewport: { x: 0, y: 0, scale: 1 } } },
        nodes: [],
        edges: [],
        layers: {},
        latest_job: null,
      },
    });
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.map = h.fns.normalizeMap(makeMap({ map_id: 'm1', revision: 7 }));
    await h.fns.loadMapGraph('m1', { keepLocalView: true });
    assert.equal(
      h.sandbox.state.map.revision,
      42,
      'keepLocalView 跳过 applySavedView 时，服务端 revision 仍必须吸收进 state.map',
    );
  }
  // 4b. 服务端没有 revision 时不得把它清成 undefined（保持上一次已知值）
  {
    const h = makeSandbox({
      graphPayload: {
        map: { map_id: 'm1' },
        nodes: [],
        edges: [],
        layers: {},
        latest_job: null,
      },
    });
    h.sandbox.state.selectedMapId = 'm1';
    h.sandbox.state.map = h.fns.normalizeMap(makeMap({ map_id: 'm1', revision: 7 }));
    await h.fns.loadMapGraph('m1', { keepLocalView: true });
    assert.equal(h.sandbox.state.map.revision, 7, '服务端未给 revision 时必须保留已知值，不能清空');
  }

  console.log('ok - map initial fit / cross-map positions guard / revision sync (node:vm, real functions)');
}

main().then(
  () => { process.exitCode = 0; },
  (error) => {
    console.error(error);
    process.exitCode = 1;
  },
);
