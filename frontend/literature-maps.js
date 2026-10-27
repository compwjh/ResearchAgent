/* Spec043 Task03：文献地图桌面 MVP。
 * 该模块刻意保持为无框架组件：后端返回的节点/边是唯一数据来源，
 * 性能样例只用于边界验证，不在生产组件中注入示例数据。
 */
(function literatureMapsModule() {
  'use strict';

  const API_ROOT = '/api/literature-maps';
  const SCHEMA_VERSION = 'literature-map-v1';
  const MAP_WIDTH = 960;
  const MAP_HEIGHT = 680;
  const MIN_MAP_SCALE = 0.35;
  const MAX_MAP_SCALE = 2.8;
  const FIT_MAX_SCALE = 2.4;
  const INITIAL_FIT_SCALE_EPSILON = 0.01;
  const FIT_PADDING_CSS_PX = 48;
  const MAX_LAYOUT_FRAMES = 8;
  // A spacing preview treats a node's edge clearance as two copies of the
  // larger node's diameter, plus a small world-unit allowance for SVG strokes.
  // The placement algorithm is deliberately bounded and deterministic so a
  // dense map expands outward instead of spinning a force simulation forever.
  const LAYOUT_CLEARANCE_MULTIPLIER = 4;
  const LAYOUT_STROKE_CLEARANCE = 4;
  const MAX_LAYOUT_PLACEMENT_ATTEMPTS = 10000;
  const MAX_POLL_ATTEMPTS = 120;
  const MAX_PREVIEW_DISCOVERY_PAGES = 50;
  const MAX_MAP_NODES = 200;
  const MAX_PREVIEW_SELECTION = 20;
  const MAX_ANALYSIS_POLL_ATTEMPTS = 120;
  const MAX_QUEUE_POLL_ATTEMPTS = 120;
  const QUEUE_POLL_DELAY = 1600;
  const QUEUE_POLL_BACKOFF = 3200;
  const MAX_GROUPS = 200;
  const GROUP_NAME_MAX_LENGTH = 80;
  const GROUP_COLOR_PATTERN = /^#[0-9a-f]{6}$/i;
  const COLOR_PRESETS = ['#ff6b6b', '#f06595', '#cc5de8', '#845ef7', '#5c7cfa', '#339af0', '#22b8cf', '#20c997', '#00c2a8', '#51cf66', '#a9e34b', '#ffd43b'];
  const RECENT_COLOR_LIMIT = 8;
  const COLOR_SAVE_TIMEOUT_MS = 15000;
  const DEFAULT_NODE_COLOR = '#8d80e6';
  const DEFAULT_NODE_STYLE = { fill_mode: 'filled', fill_opacity: 0.3 };
  const EXPORT_SCHEMA_VERSION = 'literature-map-export-v2';
  const TERMINAL_JOB_STATES = new Set(['completed', 'partial', 'failed', 'stopped']);
  const LAYER_NAMES = ['citation', 'similarity'];
  const LABEL_MODES = ['all', 'neighbors', 'hidden'];
  const DEFAULT_LABEL_MODE = 'all';
  const MIN_NODE_RADIUS = 8;
  const MAX_NODE_RADIUS = 28;
  const LABEL_MAX_LENGTH = 38;
  const LABEL_BASE_FONT_SIZE = 9;
  const LABEL_MIN_CSS_PX = 9;
  const LABEL_CHAR_WIDTH_FACTOR = 0.61;
  const LABEL_LINE_HEIGHT_FACTOR = 1.25;
  // Keep this allow-list aligned with catalog_adapter.py's canonical IDs.  In
  // particular, do not invent a Semantic Scholar spelling for map filters.
  const SUPPORTED_MAP_SOURCE_IDS = new Set(['usenix', 'dblp', 'ieee_sp', 'ccs', 'ndss', 'openalex', 'crossref']);
  const SUPPORTED_MAP_CONFERENCE_IDS = new Set(['usenix-security', 'ieee-sp', 'ccs', 'ndss']);
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const state = {
    active: false,
    mounted: false,
    maps: [],
    groups: [],
    multiSelectActive: false,
    multiSelectedNodeIds: new Set(),
    colorDraft: null,
    colorSaveInFlight: false,
    recentColorBuckets: new Map(),
    nodeStyle: { ...DEFAULT_NODE_STYLE },
    nodeStyleDraft: { ...DEFAULT_NODE_STYLE },
    nodeStyleSaveInFlight: false,
    selectedMapId: null,
    map: null,
    graph: null,
    selectedNodeId: null,
    selectedNode: null,
    listQuery: '',
    listStatus: 'all',
    job: null,
    eventCursor: 0,
    pollTimer: null,
    pollInFlight: false,
    pollAttempts: 0,
    graphRequest: 0,
    nodeRequest: 0,
    importRequest: 0,
    importInFlightNodeId: null,
    mapRequest: 0,
    viewRequest: 0,
    initialFitPending: false,
    pollGeneration: 0,
    preview: null,
    previewJob: null,
    previewId: null,
    previewKind: null,
    previewNodeId: null,
    savedPreview: null,
    previewDiscoveryNotice: '',
    previewRequest: 0,
    previewPollTimer: null,
    previewPollGeneration: 0,
    previewSelection: new Set(),
    previewConflict: false,
    positions: Object.create(null),
    positionsDirty: false,
    spacingViolationCount: 0,
    viewDirty: false,
    layoutPendingIds: new Set(),
    layoutPreview: null,
    layoutPreviewActive: false,
    layoutFrames: 0,
    layoutScheduled: false,
    view: { x: 0, y: 0, scale: 1 },
    labelMode: DEFAULT_LABEL_MODE,
    layers: { citation: true, similarity: true },
    layerStatus: { citation: 'waiting', similarity: 'waiting' },
    saveTimer: null,
    pointer: null,
    createPanelOpen: false,
    createOptionsLoaded: false,
    createOptionsRequest: 0,
    createOptionsLoading: false,
    jobActionRequest: 0,
    nodeActionRequest: 0,
    analysisRequest: 0,
    analysisPollTimer: null,
    analysisPollGeneration: 0,
    analysisPollInFlight: false,
    analysisPollAttempts: 0,
    analysis: null,
    analysisJob: null,
    analysisHistory: [],
    analysisSourceStatus: null,
    analysisNodeId: null,
    analysisViewedId: null,
    analysisPollExhausted: false,
    analysisTab: 'abstract',
    analysisSubmitInFlight: false,
    analysisManualRequest: false,
    analysisQueue: null,
    queueRequest: 0,
    queuePollTimer: null,
    queuePollGeneration: 0,
    queuePollInFlight: false,
    queuePollAttempts: 0,
    queueEnsureMapId: null,
    queueEnsureKey: null,
    queueMutationRequest: 0,
    queueSignature: '',
    queueError: '',
    conversationRequest: 0,
    groupRequest: 0,
    exportRequest: 0,
    pointers: new Map(),
    pinch: null,
    suppressTap: false,
    mobile: { listOpen: false, detailOpen: false, listRestoreFocus: null, detailRestoreFocus: null },
    mobileViewport: null,
    resizeObserver: null,
    resizeRaf: null,
  };

  const refs = {};

  function createElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function renderAnalysisMarkdown(source) {
    const text = String(source || '');
    const content = createElement('div', 'literature-map-analysis-summary md-body');
    if (typeof window.renderMarkdown !== 'function') {
      content.textContent = text;
      return content;
    }
    try {
      const rendered = window.renderMarkdown(text);
      if (typeof rendered !== 'string') throw new Error('Markdown renderer returned a non-string result');
      const parsed = new DOMParser().parseFromString(rendered, 'text/html');
      while (parsed.body.firstChild) content.append(parsed.body.firstChild);
    } catch (_) {
      content.textContent = text;
    }
    return content;
  }

  function createSvgElement(tag) {
    return document.createElementNS(SVG_NS, tag);
  }

  function setAttributes(node, attributes) {
    Object.entries(attributes || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null) node.setAttribute(key, String(value));
    });
    return node;
  }

  function setHidden(node, hidden) {
    if (node) node.hidden = Boolean(hidden);
  }

  function setStatus(message, status) {
    if (!refs.status) return;
    refs.status.textContent = message || '';
    refs.status.dataset.state = status || '';
  }

  function makeIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    return `literature-map-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function errorAction(error, fallback) {
    const code = String(error?.code || '').toLowerCase();
    if (error?.status === 429 || code.includes('rate') || code.includes('429')) {
      return '来源暂时限流，请稍后点击刷新状态；已完成的地图结果会保留。';
    }
    if (error?.status === 409 || code.includes('revision') || code.includes('conflict')) {
      return '地图版本已变化，请重新打开地图后再保存视图。';
    }
    if (code.includes('partial') || error?.partial) {
      return '部分来源失败，已保留可用节点；可重新打开地图查看已完成阶段。';
    }
    return error?.message || fallback || '请求失败，请稍后重试。';
  }

  class LiteratureMapError extends Error {
    constructor(message, details) {
      super(message);
      this.name = 'LiteratureMapError';
      this.status = details?.status || 0;
      this.code = details?.code || '';
      this.retryable = Boolean(details?.retryable);
      this.partial = Boolean(details?.partial);
    }
  }

  async function request(path, init) {
    let response;
    try {
      response = await fetch(`${API_ROOT}${path}`, {
        credentials: 'same-origin',
        ...init,
        headers: {
          Accept: 'application/json',
          ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
          ...(init?.headers || {}),
        },
      });
    } catch (error) {
      if (error?.name === 'AbortError') throw error;
      throw new LiteratureMapError('无法连接本地服务，请确认后端已启动。', { retryable: true });
    }

    let payload = {};
    try {
      payload = await response.json();
    } catch (_) {
      payload = {};
    }
    if (!response.ok) {
      const detail = payload?.detail && typeof payload.detail === 'object' ? payload.detail : payload;
      const code = detail?.code || payload?.error_code || '';
      const message = detail?.message || payload?.message || '地图请求失败。';
      throw new LiteratureMapError(message, {
        status: response.status,
        code,
        retryable: detail?.retryable,
        partial: response.status === 206 || code === 'partial',
      });
    }
    if (payload?.schema_version && payload.schema_version !== SCHEMA_VERSION) {
      throw new LiteratureMapError('地图接口版本不匹配，请刷新页面后重试。', { retryable: false });
    }
    return payload;
  }

  async function requestCatalog(path) {
    let response;
    try {
      response = await fetch(path, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
    } catch (error) {
      throw new LiteratureMapError('筛选项服务暂时不可用。', { retryable: true, cause: error });
    }
    let payload = {};
    try {
      payload = await response.json();
    } catch (_) {
      payload = {};
    }
    if (!response.ok) {
      const detail = payload?.detail && typeof payload.detail === 'object' ? payload.detail : payload;
      throw new LiteratureMapError(detail?.message || payload?.message || '筛选项读取失败。', {
        status: response.status,
        code: detail?.code || payload?.error_code || '',
        retryable: detail?.retryable,
      });
    }
    return payload;
  }

  async function requestExport(path) {
    let response;
    try {
      response = await fetch(`${API_ROOT}${path}`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
    } catch (error) {
      throw new LiteratureMapError('无法连接本地服务，请确认后端已启动。', { retryable: true });
    }
    if (!response.ok) {
      let payload = {};
      try { payload = await response.json(); } catch (_) { payload = {}; }
      const detail = payload?.detail && typeof payload.detail === 'object' ? payload.detail : payload;
      throw new LiteratureMapError(detail?.message || payload?.message || '导出失败，请稍后重试。', {
        status: response.status,
        code: detail?.code || payload?.error_code || '',
        retryable: detail?.retryable,
      });
    }
    const blob = await response.blob();
    if (!blob || !blob.size) throw new LiteratureMapError('导出结果为空，未生成文件。');
    return { blob, disposition: response.headers.get('Content-Disposition') || '' };
  }

  function parseCsv(value) {
    return String(value || '')
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
      .slice(0, 50);
  }

  function parseYear(value) {
    const text = String(value || '').trim();
    if (!text) return null;
    const year = Number(text);
    return Number.isInteger(year) && year >= 1900 && year <= 2100 ? year : NaN;
  }

  function normalizeMap(map) {
    return map && typeof map === 'object' ? map : null;
  }

  function normalizeNodeStyle(nodeStyle) {
    const fillMode = nodeStyle?.fill_mode === 'outline' ? 'outline' : 'filled';
    const candidate = nodeStyle?.fill_opacity;
    const opacity = typeof candidate === 'number' && Number.isFinite(candidate) && candidate >= 0 && candidate <= 1
      ? candidate
      : DEFAULT_NODE_STYLE.fill_opacity;
    return { fill_mode: fillMode, fill_opacity: opacity };
  }

  function normalizeNodes(graph) {
    return Array.isArray(graph?.nodes) ? graph.nodes.filter((node) => node && node.node_id) : [];
  }

  function activeNodes(graph = state.graph) {
    return normalizeNodes(graph).filter((node) => !node.removed && !node.tombstone);
  }

  function normalizeEdges(graph) {
    return Array.isArray(graph?.edges) ? graph.edges.filter((edge) => edge && edge.source_id && edge.target_id) : [];
  }

  function mapTitle(map) {
    return map?.name || map?.topic || '未命名地图';
  }

  function normalizeLabelMode(value) {
    const mode = String(value || '').trim().toLowerCase();
    return LABEL_MODES.includes(mode) ? mode : DEFAULT_LABEL_MODE;
  }

  function mapStatusLabel(status) {
    const labels = {
      generating: '生成中',
      ready: '可用',
      partial: '部分完成',
      failed: '失败',
      stopped: '已停止',
      queued: '排队中',
      running: '运行中',
      completed: '已完成',
      not_imported: '未入库',
      submitted: '已提交',
      importing: '入库处理中',
      downloading: '下载中',
      validating: '文件校验中',
      indexing: '索引中',
      waiting_login: '等待登录',
      pending: '处理中',
      processing: '处理中',
      indexed: '已入库',
    };
    return labels[String(status || '').toLowerCase()] || '状态待确认';
  }

  function nodeLabel(node) {
    const authors = Array.isArray(node?.authors)
      ? node.authors.map((author) => String(author || '').trim()).filter(Boolean)
      : [];
    const rawAuthor = authors[0] || (typeof node?.authors === 'string' ? node.authors.trim() : '');
    const etAlMatch = rawAuthor.match(/(?:^|\s)et\s*al(?:\.|…)?\s*$/i);
    const author = etAlMatch
      ? rawAuthor.slice(0, etAlMatch.index).replace(/[,\s]+$/, '').trim()
      : rawAuthor;
    const authorSuffix = author && (authors.length > 1 || Boolean(etAlMatch)) ? ' et al.' : '';
    const year = node?.year === null || node?.year === undefined || String(node.year).trim() === '' ? '年份未知' : String(node.year).trim();
    const fallback = String(node?.title || node?.node_id || '未命名论文').trim() || String(node?.node_id || '未命名论文');
    const suffix = `, ${year}`;
    const body = author || fallback;
    const bodyLimit = Math.max(1, LABEL_MAX_LENGTH - authorSuffix.length - suffix.length);
    const boundedBody = body.length > bodyLimit
      ? `${body.slice(0, Math.max(1, bodyLimit - 1)).trimEnd()}…`
      : body;
    return `${boundedBody}${authorSuffix}${suffix}`;
  }

  function citationCount(value) {
    if (value === null || value === undefined || (typeof value !== 'number' && typeof value !== 'string')) return null;
    if (typeof value === 'string' && !value.trim()) return null;
    const count = Number(value);
    return Number.isFinite(count) && count >= 0 ? count : null;
  }

  function citationRadius(node) {
    const count = citationCount(node?.citation_count);
    if (count === null) return MIN_NODE_RADIUS;
    return Math.min(MAX_NODE_RADIUS, MIN_NODE_RADIUS + 2 * Math.log1p(count));
  }

  function citationCountLabel(node) {
    const count = citationCount(node?.citation_count);
    return count === null ? '未知' : String(count);
  }

  function nodeDisplayLabel(node) {
    const label = nodeLabel(node);
    return citationCount(node?.citation_count) === null ? `${label} · 引用数未知` : label;
  }

  function nodeAccessibleLabel(node) {
    const title = String(node?.title || node?.node_id || '未命名论文');
    return `${title} · ${nodeDisplayLabel(node)} · 引用数${citationCountLabel(node)}`;
  }

  function labelIdsForGraph(nodes, edges) {
    if (state.labelMode === 'hidden') return new Set();
    if (state.labelMode === 'all') return new Set(nodes.map((node) => node.node_id));
    if (!state.selectedNodeId) return new Set();
    const ids = new Set([state.selectedNodeId]);
    edges.forEach((edge) => {
      if (edge.source_id === state.selectedNodeId) ids.add(edge.target_id);
      if (edge.target_id === state.selectedNodeId) ids.add(edge.source_id);
    });
    return ids;
  }

  function svgMatrixScale(matrix) {
    if (!matrix) return 0;
    const scale = Math.hypot(Number(matrix.a) || 0, Number(matrix.b) || 0);
    return Number.isFinite(scale) && scale > 0 ? scale : 0;
  }

  function labelScreenScale() {
    const rootScale = svgMatrixScale(refs.svg?.getScreenCTM?.());
    const viewportScale = Number(state.view?.scale);
    if (rootScale > 0 && Number.isFinite(viewportScale) && viewportScale > 0) return rootScale * viewportScale;
    const rect = refs.svg?.getBoundingClientRect?.();
    const fallbackScale = rect ? Math.min(Number(rect.width) / MAP_WIDTH, Number(rect.height) / MAP_HEIGHT) : 1;
    return Number.isFinite(fallbackScale) && fallbackScale > 0 ? fallbackScale : 1;
  }

  function labelFontSizeSvgUnits() {
    const screenScale = labelScreenScale();
    return Math.max(LABEL_BASE_FONT_SIZE, LABEL_MIN_CSS_PX / screenScale);
  }

  function labelPosition(point, radius, text, occupied, fontSize = LABEL_BASE_FONT_SIZE) {
    const x = point.x + radius + 5;
    const actualFontSize = Number.isFinite(Number(fontSize)) && Number(fontSize) > 0 ? Number(fontSize) : LABEL_BASE_FONT_SIZE;
    const width = Math.max(40, String(text || '').length * actualFontSize * LABEL_CHAR_WIDTH_FACTOR);
    const height = Math.max(12, actualFontSize * LABEL_LINE_HEIGHT_FACTOR);
    let y = point.y + 4;
    let attempts = 0;
    while (attempts < 6 && occupied.some((box) => x < box.right && x + width > box.left && y - height < box.bottom && y + 2 > box.top)) {
      y += height + 2;
      attempts += 1;
    }
    occupied.push({ left: x, right: x + width, top: y - height, bottom: y + 2 });
    return { x, y };
  }

  function normalizeGroups(payload) {
    const groups = Array.isArray(payload?.groups) ? payload.groups : [];
    return groups.filter((group) => group && String(group.group_id || '').trim())
      .slice(0, MAX_GROUPS)
      .map((group) => ({
        group_id: String(group.group_id).trim(),
        name: String(group.name || '').trim().slice(0, GROUP_NAME_MAX_LENGTH),
        color: GROUP_COLOR_PATTERN.test(String(group.color || '')) ? String(group.color).toLowerCase() : '#8d80e6',
      }));
  }

  function groupById(groupId) {
    return state.groups.find((group) => group.group_id === groupId) || null;
  }

  function normalizeHexColor(value) {
    const color = String(value || '').trim();
    return GROUP_COLOR_PATTERN.test(color) ? color.toLowerCase() : null;
  }

  function mapOwnerId() {
    return String(state.map?.owner_id || state.graph?.map?.owner_id || '').trim();
  }

  function recentColorScope() {
    const ownerId = mapOwnerId();
    if (ownerId) return { scope: `owner:${ownerId}`, ownerId };
    const mapId = String(state.map?.map_id || state.selectedMapId || '').trim();
    return mapId ? { scope: `map:${mapId}`, ownerId: '' } : { scope: '', ownerId: '' };
  }

  function getRecentColors() {
    const { scope, ownerId } = recentColorScope();
    if (!scope) return [];
    if (state.recentColorBuckets.has(scope)) return [...state.recentColorBuckets.get(scope)];
    let colors = [];
    if (ownerId) {
      try {
        const saved = JSON.parse(window.localStorage.getItem(`literature-map-recent-colors:${ownerId}`) || '[]');
        if (Array.isArray(saved)) colors = saved.map(normalizeHexColor).filter(Boolean).slice(0, RECENT_COLOR_LIMIT);
      } catch (_) {
        colors = [];
      }
    }
    state.recentColorBuckets.set(scope, colors);
    return [...colors];
  }

  function rememberRecentColor(colorValue, scopeOverride = null) {
    const color = normalizeHexColor(colorValue);
    const current = recentColorScope();
    const ownerId = String(scopeOverride?.ownerId ?? current.ownerId).trim();
    const mapId = String(scopeOverride?.mapId ?? state.map?.map_id ?? state.selectedMapId ?? '').trim();
    const scope = ownerId ? `owner:${ownerId}` : (mapId ? `map:${mapId}` : '');
    if (!color || !scope) return;
    let previous = state.recentColorBuckets.get(scope);
    if (!Array.isArray(previous)) {
      previous = [];
      if (ownerId) {
        try {
          const saved = JSON.parse(window.localStorage.getItem(`literature-map-recent-colors:${ownerId}`) || '[]');
          if (Array.isArray(saved)) previous = saved.map(normalizeHexColor).filter(Boolean).slice(0, RECENT_COLOR_LIMIT);
        } catch (_) {
          previous = [];
        }
      }
    }
    const colors = [color, ...previous.filter((recent) => recent !== color)].slice(0, RECENT_COLOR_LIMIT);
    state.recentColorBuckets.set(scope, colors);
    if (!ownerId) return;
    try {
      window.localStorage.setItem(`literature-map-recent-colors:${ownerId}`, JSON.stringify(colors));
    } catch (_) {
      // An unavailable browser store only removes cross-session persistence.
    }
  }

  function currentGroupColor(groupId) {
    const group = groupById(groupId);
    if (state.colorDraft?.target === 'group'
      && state.colorDraft.groupId === groupId
      && normalizeHexColor(state.colorDraft.colorOverride)) {
      return state.colorDraft.colorOverride;
    }
    return group?.color || DEFAULT_NODE_COLOR;
  }

  function nodeDisplayColor(node) {
    const draft = state.colorDraft;
    if (draft?.mapId === state.map?.map_id && ['node', 'selection'].includes(draft.target)
      && draft.nodeIds.includes(node?.node_id)) {
      if (draft.colorOverride === null) return currentGroupColor(node.group_id);
      const draftColor = normalizeHexColor(draft.colorOverride);
      if (draftColor) return draftColor;
    }
    const override = normalizeHexColor(node?.color_override);
    if (override) return override;
    return currentGroupColor(node?.group_id);
  }

  function colorDraftMatches(target, groupId = null) {
    if (!state.colorDraft || state.colorDraft.mapId !== state.map?.map_id || state.colorDraft.target !== target) return false;
    if (target === 'group') return state.colorDraft.groupId === groupId;
    const currentIds = target === 'selection' ? [...state.multiSelectedNodeIds] : [state.selectedNodeId].filter(Boolean);
    return state.colorDraft.nodeIds.length === currentIds.length
      && state.colorDraft.nodeIds.every((nodeId) => currentIds.includes(nodeId));
  }

  function initialPaletteColor(target, groupId = null) {
    if (colorDraftMatches(target, groupId)) {
      const draft = state.colorDraft.colorOverride;
      if (normalizeHexColor(draft)) return draft;
    }
    if (target === 'group') return currentGroupColor(groupId);
    const ids = target === 'selection'
      ? [...state.multiSelectedNodeIds]
      : [state.selectedNodeId].filter(Boolean);
    const node = normalizeNodes(state.graph).find((item) => item.node_id === ids[0]);
    return node ? nodeDisplayColor(node) : DEFAULT_NODE_COLOR;
  }

  function colorTargetNodeIds(target) {
    const ids = target === 'selection' ? [...state.multiSelectedNodeIds] : [state.selectedNodeId].filter(Boolean);
    return [...new Set(ids)].filter((nodeId) => activeNodes().some((node) => node.node_id === nodeId)).slice(0, MAX_MAP_NODES);
  }

  function setColorDraft(target, colorOverride, groupId = null) {
    if (!state.map?.map_id) return;
    const nodeIds = target === 'group' ? [] : colorTargetNodeIds(target);
    if (target !== 'group' && !nodeIds.length) return;
    state.colorDraft = { mapId: state.map.map_id, target, groupId, nodeIds, colorOverride };
    renderGraph();
  }

  function cancelColorDraft(target, groupId = null) {
    if (state.colorDraft && state.colorDraft.target === target
      && (target !== 'group' || state.colorDraft.groupId === groupId)) state.colorDraft = null;
    renderGraph();
    if (target === 'group') renderGroups();
    else if (target === 'node' && state.selectedNode) renderNodeDetail(state.selectedNode);
  }

  function createColorPalette(target, groupId = null) {
    const palette = createElement('section', `literature-map-color-palette literature-map-color-palette-${target}`);
    palette.dataset.target = target;
    if (groupId) palette.dataset.groupId = groupId;
    const colors = createElement('div', 'literature-map-color-swatches');
    COLOR_PRESETS.forEach((color) => {
      const swatch = createElement('button', 'literature-map-color-swatch');
      swatch.type = 'button';
      swatch.dataset.color = color;
      swatch.style.backgroundColor = color;
      swatch.setAttribute('aria-label', `选择颜色 ${color}`);
      swatch.title = color;
      swatch.addEventListener('click', () => {
        setColorDraft(target, color, groupId);
        hexInput.value = color;
        error.textContent = '';
        hexInput.removeAttribute('aria-invalid');
        applyButton.disabled = false;
      });
      colors.append(swatch);
    });
    const recentColors = createElement('div', 'literature-map-color-recents');
    recentColors.setAttribute('aria-label', '最近使用的颜色');
    getRecentColors().forEach((color) => {
      const swatch = createElement('button', 'literature-map-color-swatch literature-map-color-recent');
      swatch.type = 'button';
      swatch.dataset.color = color;
      swatch.style.backgroundColor = color;
      swatch.setAttribute('aria-label', `最近使用的颜色 ${color}`);
      swatch.title = color;
      swatch.addEventListener('click', () => {
        setColorDraft(target, color, groupId);
        hexInput.value = color;
        error.textContent = '';
        hexInput.removeAttribute('aria-invalid');
        applyButton.disabled = false;
      });
      recentColors.append(swatch);
    });
    const hexLabel = createElement('label', 'literature-map-color-hex-label', '自定义 HEX');
    const hexInput = createElement('input', 'literature-map-color-hex');
    hexInput.type = 'text';
    hexInput.inputMode = 'text';
    hexInput.autocomplete = 'off';
    hexInput.maxLength = '7';
    hexInput.value = initialPaletteColor(target, groupId);
    hexInput.setAttribute('aria-label', '自定义 HEX 颜色');
    const error = createElement('span', 'literature-map-color-error');
    error.setAttribute('role', 'alert');
    hexLabel.append(hexInput);
    const actions = createElement('div', 'literature-map-color-actions');
    const applyButton = createElement('button', 'send-button literature-map-color-apply', target === 'group' ? '应用分组颜色' : '应用到 1 篇');
    applyButton.type = 'button';
    applyButton.disabled = !state.map?.map_id || (target === 'selection' && !state.multiSelectedNodeIds.size);
    applyButton.addEventListener('click', () => {
      if (target === 'group') applyGroupColor(groupId, applyButton);
      else applyNodeColor(target, applyButton);
    });
    const cancelButton = createElement('button', 'secondary-button literature-map-color-cancel', '取消预览');
    cancelButton.type = 'button';
    cancelButton.addEventListener('click', () => cancelColorDraft(target, groupId));
    actions.append(applyButton, cancelButton);
    palette.append(colors, recentColors, hexLabel, error, actions);
    if (target === 'node') {
      const followGroup = createElement('button', 'secondary-button literature-map-node-color-follow-group', '恢复跟随分组');
      followGroup.type = 'button';
      followGroup.addEventListener('click', () => {
        setColorDraft(target, null);
        hexInput.value = initialPaletteColor(target);
        error.textContent = '';
        hexInput.removeAttribute('aria-invalid');
        applyButton.disabled = false;
      });
      palette.append(followGroup);
    }
    hexInput.addEventListener('input', () => {
      const normalized = normalizeHexColor(hexInput.value);
      if (!normalized) {
        error.textContent = '颜色格式应为 #RRGGBB。';
        hexInput.setAttribute('aria-invalid', 'true');
        applyButton.disabled = true;
        return;
      }
      hexInput.value = normalized;
      error.textContent = '';
      hexInput.removeAttribute('aria-invalid');
      applyButton.disabled = false;
      setColorDraft(target, normalized, groupId);
    });
    return palette;
  }

  function validateGroupForm(name, color) {
    const normalizedName = String(name || '').trim();
    const normalizedColor = String(color || '').trim().toLowerCase();
    if (!normalizedName || normalizedName.length > GROUP_NAME_MAX_LENGTH) {
      throw new LiteratureMapError(`分组名称不能为空且最多 ${GROUP_NAME_MAX_LENGTH} 个字符。`);
    }
    if (!GROUP_COLOR_PATTERN.test(normalizedColor)) {
      throw new LiteratureMapError('分组颜色必须是 #RRGGBB 格式。');
    }
    return { name: normalizedName, color: normalizedColor };
  }

  function exportFilenameFromDisposition(disposition, fallback) {
    const match = String(disposition || '').match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
    if (match) {
      try { return decodeURIComponent(match[1] || match[2]); } catch (_) { return match[1] || match[2]; }
    }
    return fallback;
  }

  function safeDownload(blob, filename) {
    if (!blob || !blob.size) throw new LiteratureMapError('导出结果为空，未生成文件。');
    const url = URL.createObjectURL(blob);
    const anchor = createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.hidden = true;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function renderStatusBadge(status) {
    const badge = createElement('span', 'literature-map-badge', mapStatusLabel(status));
    badge.dataset.status = status || '';
    return badge;
  }

  const IMPORT_DIAGNOSTIC_LABELS = Object.freeze({
    ARXIV_UNAVAILABLE: 'arXiv 服务暂不可用',
    ARXIV_RATE_LIMITED: 'arXiv 服务暂时限流',
    ARXIV_HTTP_ERROR: 'arXiv 服务响应异常',
    ARXIV_INVALID_RESPONSE: 'arXiv 服务返回无效结果',
    ARXIV_MATCH_UNCERTAIN: 'arXiv 身份匹配不确定',
    ARXIV_IDENTITY_CONFLICT: 'arXiv 身份冲突',
    SEMANTIC_SCHOLAR_IDENTIFIER_REQUIRED: 'Semantic Scholar 身份信息不足',
    SEMANTIC_SCHOLAR_UNAVAILABLE: 'Semantic Scholar 服务暂不可用',
    SEMANTIC_SCHOLAR_RATE_LIMITED: 'Semantic Scholar 提供方暂时限流',
    SEMANTIC_SCHOLAR_HTTP_ERROR: 'Semantic Scholar 服务响应异常',
    SEMANTIC_SCHOLAR_INVALID_RESPONSE: 'Semantic Scholar 服务返回无效结果',
    SEMANTIC_SCHOLAR_AUTH_FAILED: 'Semantic Scholar 提供方授权失败',
    SEMANTIC_SCHOLAR_NOT_FOUND: 'Semantic Scholar 未找到匹配',
    SEMANTIC_SCHOLAR_NO_OPEN_PDF: '未找到可验证的开放 PDF',
    SEMANTIC_SCHOLAR_MATCH_UNCERTAIN: 'Semantic Scholar 身份匹配不确定',
    SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST: 'PDF 来源主机不受支持',
    OA_IDENTITY_CONFLICT: '开放来源身份冲突',
    PDF_NOT_FOUND: '未找到可验证的 PDF',
    IMPORT_IDENTITY_CONFLICT: '导入身份不一致',
    DOWNLOAD_BLOCKED: '下载被来源策略阻止',
    DOWNLOAD_TIMEOUT: '来源下载超时',
    PDF_TOO_LARGE: 'PDF 文件超过大小限制',
    INVALID_PDF: '来源文件不是可验证的 PDF',
    LOGIN_REQUIRED: '需要登录后才能处理来源',
    BROWSER_SESSION_REQUIRED: '需要浏览器会话处理来源',
    BROWSER_SESSION_EXPIRED: '浏览器会话已过期',
    KB_IMPORT_FAILED: '知识库导入失败',
    KB_INDEX_FAILED: '知识库索引失败',
    KB_STORAGE_LOCKED: '知识库存储暂时被占用',
    DUPLICATE_IMPORT: '知识库中已有相同导入',
    PAPER_ALREADY_EXISTS: '知识库中已有该论文',
  });
  const IMPORT_PENDING_STATES = new Set(['queued', 'running', 'pending', 'submitted', 'processing', 'importing', 'downloading', 'validating', 'indexing', 'waiting_login']);

  function normalizeImportDiagnostics(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const codes = [];
    const addCode = (candidate) => {
      const code = String(candidate || '').trim().toUpperCase();
      if (code && Object.prototype.hasOwnProperty.call(IMPORT_DIAGNOSTIC_LABELS, code) && !codes.includes(code)) codes.push(code);
    };
    addCode(value.error_code);
    if (Array.isArray(value.resolver_codes)) value.resolver_codes.slice(0, 20).forEach(addCode);
    addCode(value.resolver_code);
    return {
      error_code: codes[0] || '',
      resolver_codes: codes,
      retryable: value.retryable === true,
      reasons: codes.map((code) => IMPORT_DIAGNOSTIC_LABELS[code]).filter(Boolean),
    };
  }

  function nodeImportDiagnostics(node) {
    const provenance = node?.provenance;
    return normalizeImportDiagnostics(provenance && typeof provenance === 'object' && !Array.isArray(provenance)
      ? provenance.import_diagnostics
      : null);
  }

  function importPayloadEnvelope(payload) {
    const nested = payload?.import && typeof payload.import === 'object' && !Array.isArray(payload.import) ? payload.import : null;
    return nested ? { ...(payload || {}), ...nested } : (payload && typeof payload === 'object' ? payload : {});
  }

  function mergeImportResponse(node, payload) {
    const envelope = importPayloadEnvelope(payload);
    const returnedStatus = String(envelope.download_status || envelope.status || 'submitted').trim() || 'submitted';
    const normalizedStatus = returnedStatus.toLowerCase();
    const next = { ...node, download_status: returnedStatus };
    if (Object.prototype.hasOwnProperty.call(envelope, 'document_id')) next.document_id = envelope.document_id;
    const existingProvenance = node?.provenance && typeof node.provenance === 'object' && !Array.isArray(node.provenance)
      ? { ...node.provenance }
      : (node?.provenance ? { source: String(node.provenance) } : {});
    const diagnostics = normalizeImportDiagnostics(envelope.import_diagnostics || envelope.provenance?.import_diagnostics || envelope);
    if (normalizedStatus === 'indexed' || normalizedStatus === 'completed' || Boolean(next.document_id) || normalizedStatus !== 'failed') {
      delete existingProvenance.import_diagnostics;
    } else if (diagnostics && (diagnostics.resolver_codes.length || diagnostics.error_code || diagnostics.retryable)) {
      existingProvenance.import_diagnostics = {
        error_code: diagnostics.error_code,
        resolver_codes: diagnostics.resolver_codes,
        resolver_code: diagnostics.resolver_codes.at(-1) || '',
        retryable: diagnostics.retryable,
      };
    }
    if (Object.keys(existingProvenance).length) next.provenance = existingProvenance;
    return next;
  }

  function importStatusMessage(node) {
    const status = String(node?.download_status || '').toLowerCase();
    const documentId = String(node?.document_id ?? '').trim();
    if (status === 'waiting_login') return '入库状态：等待登录处理。请在论文检索的既有导入处理区完成现有等待登录项，再返回刷新全文状态；不会自动重试。';
    if (status === 'not_imported') return documentId ? '入库状态：已加入知识库；全文依据是否可用以服务器状态为准。' : '入库状态：未入库。';
    if (!status) return documentId ? '入库状态：已加入知识库；全文依据是否可用以服务器状态为准。' : '入库状态：未入库。';
    if (status === 'indexed' || documentId) return '入库状态：已加入知识库；全文依据是否可用以服务器状态为准。';
    return `入库状态：${mapStatusLabel(status)}。`;
  }

  function renderImportDiagnostics(node) {
    const status = String(node?.download_status || '').toLowerCase();
    if (!['failed', 'waiting_login'].includes(status)) return null;
    const section = createElement('section', 'literature-map-detail-section literature-map-import-diagnostics');
    section.append(createElement('h4', '', '入库诊断'));
    const diagnostics = nodeImportDiagnostics(node);
    if (status === 'waiting_login') {
      section.append(createElement('p', '', diagnostics?.reasons?.length
        ? `当前状态：等待登录处理。${diagnostics.reasons.join('；')}。请到既有导入处理区完成登录；不会自动重试或新建批次。`
        : '当前状态：等待登录处理。此地图没有登录会话资料，请到既有导入处理区完成现有任务；不会自动重试或新建批次。'));
      return section;
    }
    if (!diagnostics || !diagnostics.reasons.length) {
      section.append(createElement('p', '', '失败原因未记录。可人工重新提交以获取新的诊断；不会自动重试。'));
      return section;
    }
    section.append(createElement('p', '', `失败原因：${diagnostics.reasons.join('；')}。`));
    section.append(createElement('p', '', diagnostics.retryable
      ? '当前可人工重试；不会自动重试。'
      : '当前未标记为可重试；请使用人工处理入口。'));
    return section;
  }

  function renderShell() {
    const mount = document.querySelector('#literature-maps-mount');
    if (!mount || state.mounted) return;

    const root = createElement('div', 'literature-map-app');
    const header = createElement('header', 'literature-map-header');
    const heading = createElement('div', 'literature-map-heading');
    heading.append(createElement('p', 'literature-map-eyebrow', 'LITERATURE MAPS'));
    heading.append(createElement('h1', '', '自动主题探索'));
    heading.append(createElement('p', 'literature-map-subtitle', '输入主题，保存一张可继续探索的论文关系图。'));
    const headerActions = createElement('div', 'literature-map-header-actions literature-map-job-actions');
    const refreshButton = createElement('button', 'secondary-button', '刷新状态');
    refreshButton.type = 'button';
    refreshButton.id = 'literature-map-refresh-button';
    refreshButton.title = '重新读取地图和作业状态';
    headerActions.append(refreshButton);
    const newButton = createElement('button', 'secondary-button', '新建地图');
    newButton.type = 'button';
    newButton.id = 'literature-map-new-button';
    headerActions.append(newButton);
    const continueButton = createElement('button', 'secondary-button', '继续搜索');
    continueButton.type = 'button';
    continueButton.id = 'literature-map-continue-search';
    continueButton.hidden = true;
    headerActions.append(continueButton);
    const refreshPreviewButton = createElement('button', 'secondary-button', '刷新预览');
    refreshPreviewButton.type = 'button';
    refreshPreviewButton.id = 'literature-map-refresh-preview';
    refreshPreviewButton.hidden = true;
    headerActions.append(refreshPreviewButton);
    const openSavedPreviewButton = createElement('button', 'secondary-button', '打开上次预览');
    openSavedPreviewButton.type = 'button';
    openSavedPreviewButton.id = 'literature-map-open-saved-preview';
    openSavedPreviewButton.hidden = true;
    headerActions.append(openSavedPreviewButton);
    const stopJobButton = createElement('button', 'secondary-button', '停止任务');
    stopJobButton.type = 'button';
    stopJobButton.id = 'literature-map-stop-job';
    stopJobButton.hidden = true;
    headerActions.append(stopJobButton);
    const retryJobButton = createElement('button', 'secondary-button', '重试失败单元');
    retryJobButton.type = 'button';
    retryJobButton.id = 'literature-map-retry-job';
    retryJobButton.hidden = true;
    headerActions.append(retryJobButton);
    header.append(heading, headerActions);
    root.append(header);

    const notice = createElement('div', 'literature-map-notice');
    notice.id = 'literature-map-status';
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    root.append(notice);

    const grid = createElement('div', 'literature-map-grid');
    const listPanel = createElement('aside', 'literature-map-panel literature-map-list-panel');
    const listHead = createElement('header', 'literature-map-panel-head');
    listHead.append(createElement('h2', '', '我的地图'));
    const listCount = createElement('span', 'literature-map-count');
    listCount.id = 'literature-map-count';
    listHead.append(listCount);
    const listClose = createElement('button', 'icon-button literature-map-mobile-close', '×');
    listClose.type = 'button';
    listClose.id = 'literature-map-list-close';
    listClose.title = '关闭地图列表';
    listClose.setAttribute('aria-label', '关闭地图列表');
    listHead.append(listClose);
    listPanel.append(listHead);
    const listFilters = createElement('div', 'literature-map-list-filters');
    const listSearch = createElement('input');
    listSearch.id = 'literature-map-list-search';
    listSearch.type = 'search';
    listSearch.placeholder = '筛选主题或名称';
    listSearch.setAttribute('aria-label', '筛选地图');
    const listStatus = createElement('select');
    listStatus.id = 'literature-map-list-status';
    listStatus.setAttribute('aria-label', '按地图状态筛选');
    [['all', '全部状态'], ['generating', '生成中'], ['ready', '可用'], ['partial', '部分完成'], ['failed', '失败'], ['stopped', '已停止']].forEach(([value, label]) => {
      const option = createElement('option', '', label);
      option.value = value;
      listStatus.append(option);
    });
    listFilters.append(listSearch, listStatus);
    listPanel.append(listFilters);
    const mapList = createElement('div', 'literature-map-list');
    mapList.id = 'literature-map-list';
    mapList.setAttribute('role', 'list');
    listPanel.append(mapList);
    const listEmpty = createElement('p', 'literature-map-empty', '还没有地图，请从右上角新建。');
    listEmpty.id = 'literature-map-list-empty';
    listPanel.append(listEmpty);

    const groupsPanel = createElement('section', 'literature-map-groups');
    groupsPanel.id = 'literature-map-groups';
    groupsPanel.hidden = true;
    const groupsHeading = createElement('div', 'literature-map-groups-heading');
    groupsHeading.append(createElement('h3', '', '人工分组'));
    const groupForm = createElement('form', 'literature-map-group-form');
    groupForm.id = 'literature-map-group-form';
    const groupNameInput = createElement('input');
    groupNameInput.id = 'literature-map-group-name';
    groupNameInput.name = 'name';
    groupNameInput.maxLength = String(GROUP_NAME_MAX_LENGTH);
    groupNameInput.placeholder = '新分组名称';
    groupNameInput.setAttribute('aria-label', '分组名称');
    const groupColorInput = createElement('input');
    groupColorInput.id = 'literature-map-group-color';
    groupColorInput.name = 'color';
    groupColorInput.type = 'color';
    groupColorInput.value = '#8d80e6';
    groupColorInput.setAttribute('aria-label', '分组颜色');
    const groupCreateButton = createElement('button', 'secondary-button', '创建分组');
    groupCreateButton.type = 'submit';
    groupCreateButton.id = 'literature-map-group-create';
    groupForm.append(groupNameInput, groupColorInput, groupCreateButton);
    const groupList = createElement('div', 'literature-map-group-list');
    groupList.id = 'literature-map-group-list';
    const groupEmpty = createElement('p', 'literature-map-group-empty', '还没有人工分组。');
    groupEmpty.id = 'literature-map-group-empty';
    groupsPanel.append(groupsHeading, groupForm, groupList, groupEmpty);
    listPanel.append(groupsPanel);

    const createPanel = createElement('section', 'literature-map-create-panel');
    createPanel.id = 'literature-map-create-panel';
    createPanel.hidden = true;
    const createTitle = createElement('h3', '', '新建主题地图');
    const form = createElement('form', 'literature-map-create-form');
    form.id = 'literature-map-create-form';
    const topicLabel = createElement('label', '', '主题（必填）');
    const topicInput = createElement('textarea');
    topicInput.id = 'literature-map-topic';
    topicInput.name = 'topic';
    topicInput.required = true;
    topicInput.maxLength = 500;
    topicInput.rows = 3;
    topicInput.placeholder = '例如：面向边缘设备的联邦学习隐私保护';
    topicLabel.append(topicInput);
    const nameLabel = createElement('label', '', '地图名称（可选）');
    const nameInput = createElement('input');
    nameInput.id = 'literature-map-name';
    nameInput.name = 'name';
    nameInput.maxLength = 160;
    nameLabel.append(nameInput);
    const formGrid = createElement('div', 'literature-map-form-grid');
    [['literature-map-year-start', '起始年份'], ['literature-map-year-end', '结束年份']].forEach(([id, label]) => {
      const field = createElement('label', '', label);
      const input = createElement('input');
      input.id = id;
      input.type = 'number';
      input.min = '1900';
      input.max = '2100';
      input.step = '1';
      field.append(input);
      formGrid.append(field);
    });
    const limitLabel = createElement('label', '', '首批数量');
    const limitInput = createElement('select');
    limitInput.id = 'literature-map-limit';
    [20, 30, 50].forEach((value) => {
      const option = createElement('option', '', String(value));
      option.value = String(value);
      option.selected = value === 30;
      limitInput.append(option);
    });
    limitLabel.append(limitInput);
    formGrid.append(limitLabel);
    const filterGrid = createElement('div', 'literature-map-filter-grid');
    const sourceField = createElement('fieldset', 'literature-map-selection-field');
    sourceField.append(createElement('legend', '', '来源（可选）'));
    const sourceOptions = createElement('div', 'literature-map-option-list');
    sourceOptions.id = 'literature-map-source-options';
    const sourceNotice = createElement('p', 'literature-map-selection-notice');
    sourceNotice.id = 'literature-map-source-notice';
    sourceField.append(sourceOptions, sourceNotice);
    const conferenceField = createElement('fieldset', 'literature-map-selection-field');
    conferenceField.append(createElement('legend', '', '会议（可选）'));
    const conferenceOptions = createElement('div', 'literature-map-option-list');
    conferenceOptions.id = 'literature-map-conference-options';
    const conferenceNotice = createElement('p', 'literature-map-selection-notice');
    conferenceNotice.id = 'literature-map-conference-notice';
    conferenceField.append(conferenceOptions, conferenceNotice);
    const projectField = createElement('label', 'literature-map-project-field', '项目（可选）');
    const projectInput = createElement('select');
    projectInput.id = 'literature-map-project';
    const unboundProject = createElement('option', '', '不绑定项目');
    unboundProject.value = '';
    projectInput.append(unboundProject);
    const projectNotice = createElement('p', 'literature-map-selection-notice');
    projectNotice.id = 'literature-map-project-notice';
    projectField.append(projectInput, projectNotice);
    filterGrid.append(sourceField, conferenceField, projectField);
    const formActions = createElement('div', 'literature-map-form-actions');
    const cancelButton = createElement('button', 'secondary-button', '取消');
    cancelButton.type = 'button';
    cancelButton.id = 'literature-map-create-cancel';
    const submitButton = createElement('button', 'send-button', '开始建图');
    submitButton.type = 'submit';
    submitButton.id = 'literature-map-create-submit';
    formActions.append(cancelButton, submitButton);
    form.append(topicLabel, nameLabel, formGrid, filterGrid, formActions);
    createPanel.append(createTitle, form);
    listPanel.append(createPanel);

    const canvasPanel = createElement('main', 'literature-map-panel literature-map-canvas-panel');
    const canvasHead = createElement('header', 'literature-map-panel-head literature-map-canvas-head');
    const canvasTitle = createElement('div', 'literature-map-canvas-title');
    const currentTitle = createElement('h2', '', '选择一张地图');
    currentTitle.id = 'literature-map-current-title';
    const currentMeta = createElement('p', 'literature-map-canvas-meta', '图谱会在后台分阶段生成。');
    currentMeta.id = 'literature-map-current-meta';
    canvasTitle.append(currentTitle, currentMeta);
    const tools = createElement('div', 'literature-map-tools');
    const mobileListButton = createElement('button', 'secondary-button literature-map-mobile-list-open', '地图列表');
    mobileListButton.type = 'button';
    mobileListButton.id = 'literature-map-mobile-list-open';
    mobileListButton.title = '打开地图列表和筛选';
    mobileListButton.setAttribute('aria-label', '打开地图列表和筛选');
    tools.append(mobileListButton);
    [['literature-map-zoom-out', '−', '缩小'], ['literature-map-zoom-in', '+', '放大'], ['literature-map-fit', '适应', '适应画布'], ['literature-map-locate', '定位', '定位所选论文'], ['literature-map-reset', '重置', '重置视图'], ['literature-map-spacing', '整理间距', '预览整理间距']].forEach(([id, label, title]) => {
      const button = createElement('button', 'icon-button literature-map-tool', label);
      button.type = 'button';
      button.id = id;
      button.title = title;
      button.setAttribute('aria-label', title);
      tools.append(button);
    });
    const exportJsonButton = createElement('button', 'secondary-button literature-map-export-button', 'JSON');
    exportJsonButton.type = 'button';
    exportJsonButton.id = 'literature-map-export-json';
    exportJsonButton.title = '导出当前地图 JSON';
    exportJsonButton.setAttribute('aria-label', '导出 JSON');
    const exportPngButton = createElement('button', 'secondary-button literature-map-export-button', 'PNG');
    exportPngButton.type = 'button';
    exportPngButton.id = 'literature-map-export-png';
    exportPngButton.title = '导出当前图谱 PNG';
    exportPngButton.setAttribute('aria-label', '导出 PNG');
    tools.append(exportJsonButton, exportPngButton);
    canvasHead.append(canvasTitle, tools);
    canvasPanel.append(canvasHead);
    const layerTools = createElement('div', 'literature-map-layer-tools');
    LAYER_NAMES.forEach((kind) => {
      const label = createElement('label', 'literature-map-layer-toggle');
      const checkbox = createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = true;
      checkbox.dataset.layer = kind;
      const text = kind === 'citation' ? '引用关系' : '主题相似';
      label.append(checkbox, createElement('span', '', text));
      layerTools.append(label);
    });
    const labelModeLabel = createElement('label', 'literature-map-label-mode', '标签');
    const labelModeSelect = createElement('select');
    labelModeSelect.id = 'literature-map-label-mode';
    labelModeSelect.setAttribute('aria-label', '标签显示模式');
    [['all', '全部'], ['neighbors', '选中及相邻'], ['hidden', '隐藏']].forEach(([value, text]) => {
      const option = createElement('option', '', text);
      option.value = value;
      labelModeSelect.append(option);
    });
    labelModeSelect.value = state.labelMode;
    labelModeLabel.append(labelModeSelect);
    layerTools.append(labelModeLabel);
    const multiSelectToggle = createElement('button', 'secondary-button literature-map-multi-select-toggle', '多选模式');
    multiSelectToggle.type = 'button';
    multiSelectToggle.id = 'literature-map-multi-select-toggle';
    multiSelectToggle.disabled = true;
    multiSelectToggle.addEventListener('click', () => toggleMultiSelectMode());
    layerTools.append(multiSelectToggle);
    const nodeStyle = createElement('fieldset', 'literature-map-node-style');
    nodeStyle.id = 'literature-map-node-style';
    nodeStyle.append(createElement('legend', '', '节点填充'));
    [['filled', '填充'], ['outline', '仅描边']].forEach(([value, labelText]) => {
      const label = createElement('label', 'literature-map-node-style-mode');
      const input = createElement('input');
      input.type = 'radio';
      input.name = 'fill_mode';
      input.value = value;
      input.checked = state.nodeStyleDraft.fill_mode === value;
      input.addEventListener('change', () => updateNodeStyleDraft());
      label.append(input, createElement('span', '', labelText));
      nodeStyle.append(label);
    });
    const opacityLabel = createElement('label', 'literature-map-node-style-opacity-label', '填充透明度');
    const opacityInput = createElement('input');
    opacityInput.type = 'range';
    opacityInput.name = 'fill_opacity';
    opacityInput.min = '0';
    opacityInput.max = '1';
    opacityInput.step = '0.05';
    opacityInput.value = String(state.nodeStyleDraft.fill_opacity);
    opacityInput.addEventListener('input', () => updateNodeStyleDraft());
    const opacityValue = createElement('output', 'literature-map-node-style-opacity-value', `${Math.round(state.nodeStyleDraft.fill_opacity * 100)}%`);
    nodeStyle.append(opacityLabel, opacityInput, opacityValue);
    const applyNodeStyleButton = createElement('button', 'send-button literature-map-node-style-apply', '应用外观');
    applyNodeStyleButton.type = 'button';
    applyNodeStyleButton.disabled = true;
    applyNodeStyleButton.addEventListener('click', () => saveNodeStyle(applyNodeStyleButton));
    const cancelNodeStyleButton = createElement('button', 'secondary-button literature-map-node-style-cancel', '取消预览');
    cancelNodeStyleButton.type = 'button';
    cancelNodeStyleButton.disabled = true;
    cancelNodeStyleButton.addEventListener('click', () => cancelNodeStyleDraft());
    nodeStyle.append(applyNodeStyleButton, cancelNodeStyleButton);
    const nodeStyleDisclosure = createElement('details', 'literature-map-node-style-disclosure');
    nodeStyleDisclosure.open = !isMobileViewport();
    nodeStyleDisclosure.append(createElement('summary', '', '节点样式'), nodeStyle);
    layerTools.append(nodeStyleDisclosure);
    canvasPanel.append(layerTools);
    const selectionToolbar = createElement('section', 'literature-map-selection-toolbar');
    selectionToolbar.id = 'literature-map-node-selection-toolbar';
    selectionToolbar.hidden = true;
    const selectionCount = createElement('strong', 'literature-map-selected-count', '已选 0 篇');
    selectionCount.id = 'literature-map-selected-count';
    selectionToolbar.append(selectionCount);
    const selectionPalette = createColorPalette('selection');
    selectionPalette.hidden = true;
    selectionToolbar.append(selectionPalette);
    canvasPanel.append(selectionToolbar);
    const canvas = createElement('div', 'literature-map-canvas');
    const svg = createSvgElement('svg');
    setAttributes(svg, { id: 'literature-map-svg', viewBox: `0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`, role: 'img', tabindex: '0', 'aria-label': '文献关系图谱' });
    const defs = createSvgElement('defs');
    const marker = createSvgElement('marker');
    setAttributes(marker, { id: 'literature-map-arrow', viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '5', markerHeight: '5', orient: 'auto-start-reverse' });
    const arrow = createSvgElement('path');
    setAttributes(arrow, { d: 'M 0 0 L 10 5 L 0 10 z' });
    marker.append(arrow);
    defs.append(marker);
    const viewport = createSvgElement('g');
    viewport.id = 'literature-map-viewport';
    const edgesGroup = createSvgElement('g');
    edgesGroup.id = 'literature-map-edges';
    const nodesGroup = createSvgElement('g');
    nodesGroup.id = 'literature-map-nodes';
    viewport.append(edgesGroup, nodesGroup);
    svg.append(defs, viewport);
    canvas.append(svg);
    const empty = createElement('div', 'literature-map-canvas-empty', '选择左侧地图后查看图谱。');
    empty.id = 'literature-map-canvas-empty';
    canvas.append(empty);
    canvasPanel.append(canvas);
    const legend = createElement('div', 'literature-map-legend');
    legend.append(createElement('span', 'literature-map-legend-line citation', '实线箭头：引用者 → 被引用者'));
    legend.append(createElement('span', 'literature-map-legend-line similarity', '虚线：主题相似（无向）'));
    legend.append(createElement('span', 'literature-map-legend-note', '来源字段由接口返回；title_only 表示仅标题依据。'));
    const groupLegend = createElement('span', 'literature-map-group-legend');
    groupLegend.id = 'literature-map-group-legend';
    legend.append(groupLegend);
    canvasPanel.append(legend);
    const queuePanel = createElement('section', 'literature-map-analysis-queue');
    queuePanel.id = 'literature-map-analysis-queue';
    queuePanel.hidden = true;
    queuePanel.setAttribute('aria-live', 'polite');
    canvasPanel.append(queuePanel);
    const previewPanel = createElement('section', 'literature-map-preview-panel');
    previewPanel.id = 'literature-map-preview-panel';
    previewPanel.hidden = true;
    previewPanel.setAttribute('aria-live', 'polite');
    canvasPanel.append(previewPanel);
    const spacingPreviewPanel = createElement('section', 'literature-map-spacing-preview-panel');
    spacingPreviewPanel.id = 'literature-map-spacing-preview-panel';
    spacingPreviewPanel.hidden = true;
    spacingPreviewPanel.setAttribute('aria-live', 'polite');
    canvasPanel.append(spacingPreviewPanel);

    const detailPanel = createElement('aside', 'literature-map-panel literature-map-detail-panel');
    const detailHead = createElement('header', 'literature-map-panel-head');
    detailHead.append(createElement('h2', '', '论文详情'));
    const closeDetail = createElement('button', 'icon-button', '×');
    closeDetail.type = 'button';
    closeDetail.id = 'literature-map-detail-close';
    closeDetail.title = '关闭详情';
    closeDetail.setAttribute('aria-label', '关闭论文详情');
    detailHead.append(closeDetail);
    detailPanel.append(detailHead);
    const detail = createElement('div', 'literature-map-detail');
    detail.id = 'literature-map-detail';
    detail.append(createElement('p', 'literature-map-detail-empty', '点击图中的论文查看真实元数据。'));
    detailPanel.append(detail);

    grid.append(listPanel, canvasPanel, detailPanel);
    root.append(grid);
    const mobileBackdrop = createElement('button', 'literature-map-mobile-backdrop');
    mobileBackdrop.type = 'button';
    mobileBackdrop.id = 'literature-map-mobile-backdrop';
    mobileBackdrop.hidden = true;
    mobileBackdrop.setAttribute('aria-label', '关闭地图面板');
    mobileBackdrop.tabIndex = -1;
    root.append(mobileBackdrop);
    mount.append(root);

    Object.assign(refs, { root, listPanel, listClose, listSearch, listStatus, mapList, listEmpty, groupsPanel, groupForm, groupNameInput, groupColorInput, groupCreateButton, groupList, groupEmpty, createPanel, form, topicInput, nameInput, yearStart: formGrid.children[0].querySelector('input'), yearEnd: formGrid.children[1].querySelector('input'), limitInput, sourceOptions, sourceNotice, conferenceOptions, conferenceNotice, projectInput, projectNotice, submitButton, cancelButton, currentTitle, currentMeta, svg, viewport, edgesGroup, nodesGroup, canvasEmpty: empty, groupLegend, exportJsonButton, exportPngButton, labelModeSelect, multiSelectToggle, selectionToolbar, selectionCount: selectionToolbar.querySelector('.literature-map-selected-count'), selectionPalette, nodeStyleDisclosure, nodeStyle, detailPanel, detail, mobileListButton, mobileBackdrop, status: notice, count: listCount, continueButton, refreshPreviewButton, openSavedPreviewButton, stopJobButton, retryJobButton, queuePanel, previewPanel, spacingPreviewPanel });
    if (isMobileViewport()) {
      refs.listPanel.setAttribute('aria-hidden', 'true');
      refs.detailPanel.setAttribute('aria-hidden', 'true');
    }
    state.mobileViewport = isMobileViewport();
    bindEvents(newButton, refreshButton, closeDetail);
    state.mounted = true;
    renderMapList();
    renderGraph();
  }

  function isMobileViewport() {
    return Boolean(window.matchMedia?.('(max-width: 760px)').matches);
  }

  function restoreMobileFocus(target) {
    if (!isMobileViewport()) return;
    let focusTarget = target;
    if (!focusTarget?.isConnected && focusTarget?.dataset?.nodeId) {
      focusTarget = [...(refs.nodesGroup?.querySelectorAll('[data-node-id]') || [])]
        .find((node) => node.dataset.nodeId === focusTarget.dataset.nodeId);
    }
    if (!focusTarget?.isConnected) return;
    try { focusTarget.focus({ preventScroll: true }); } catch (_) { focusTarget.focus(); }
  }

  function setMobileDrawerBodyState(open) {
    document.body?.classList.toggle('literature-map-drawer-open', Boolean(open));
  }

  function closeMobilePanel(panel, restoreFocus = true, preserveDesktopDetail = false) {
    const isList = panel === 'list';
    const target = isList ? refs.listPanel : refs.detailPanel;
    const shouldRestoreFocus = restoreFocus && isMobileViewport();
    if (target) {
      target.classList.remove('is-open');
      if (preserveDesktopDetail) {
        target.removeAttribute('aria-hidden');
      } else {
        target.setAttribute('aria-hidden', 'true');
        if (!isList) target.hidden = true;
      }
    }
    if (isList) {
      state.mobile.listOpen = false;
      if (shouldRestoreFocus) {
        const focusTarget = state.mobile.listRestoreFocus || refs.mobileListButton;
        window.setTimeout(() => restoreMobileFocus(focusTarget), 0);
      }
      state.mobile.listRestoreFocus = null;
    } else {
      state.mobile.detailOpen = false;
      if (shouldRestoreFocus) {
        const focusTarget = state.mobile.detailRestoreFocus || refs.svg;
        window.setTimeout(() => restoreMobileFocus(focusTarget), 0);
      }
      state.mobile.detailRestoreFocus = null;
    }
    if (!state.mobile.listOpen && !state.mobile.detailOpen) {
      setHidden(refs.mobileBackdrop, true);
      setMobileDrawerBodyState(false);
    }
  }

  function openMobilePanel(panel, trigger) {
    if (!isMobileViewport()) return;
    const isList = panel === 'list';
    const target = isList ? refs.listPanel : refs.detailPanel;
    if (!target) return;
    const other = isList ? 'detail' : 'list';
    if (isList && state.mobile.detailOpen) closeMobilePanel(other, false);
    if (!isList && state.mobile.listOpen) closeMobilePanel(other, false);
    target.classList.add('is-open');
    target.setAttribute('aria-hidden', 'false');
    // The list drawer is modal, but the detail sheet leaves the map usable so
    // users can keep inspecting nearby nodes without closing their selection.
    setHidden(refs.mobileBackdrop, !isList);
    setMobileDrawerBodyState(true);
    if (isList) {
      state.mobile.listOpen = true;
      state.mobile.listRestoreFocus = trigger || document.activeElement;
    } else {
      state.mobile.detailOpen = true;
      state.mobile.detailRestoreFocus = trigger || document.activeElement;
    }
  }

  function closeAllMobilePanels(restoreFocus = false, preserveDesktopDetail = false) {
    closeMobilePanel('list', restoreFocus, preserveDesktopDetail);
    closeMobilePanel('detail', restoreFocus, preserveDesktopDetail);
    setHidden(refs.mobileBackdrop, true);
    setMobileDrawerBodyState(false);
  }

  function handleMobileViewportResize() {
    const currentMobileViewport = isMobileViewport();
    const previousMobileViewport = state.mobileViewport;
    state.mobileViewport = currentMobileViewport;
    if (previousMobileViewport === currentMobileViewport) return;
    if (refs.nodeStyleDisclosure) refs.nodeStyleDisclosure.open = !currentMobileViewport;
    const preserveDesktopDetail = state.active && previousMobileViewport === true && !currentMobileViewport;
    closeAllMobilePanels(false, preserveDesktopDetail);
    scheduleViewportStabilization();
  }

  function scheduleViewportStabilization() {
    if (state.resizeRaf) return;
    state.resizeRaf = window.requestAnimationFrame(() => {
      state.resizeRaf = null;
      if (!state.active || !refs.svg) return;
      const viewport = mapViewportWorldSize();
      if (!viewport.valid) return;
      if (state.initialFitPending && state.graph && fitView(false)) {
        state.initialFitPending = false;
      } else if (state.viewDirty || state.positionsDirty) {
        // A zero-sized/collapsed map must never write a bogus viewport. Once
        // the browser reports a real size, retry the already-dirty state.
        scheduleViewSave();
      }
      if (state.selectedNodeId && refs.detailPanel?.classList.contains('is-open')) ensureSelectedNodeVisible();
    });
  }

  function restoreDesktopPanelAccessibility() {
    if (isMobileViewport()) return;
    refs.listPanel?.removeAttribute('aria-hidden');
    refs.detailPanel?.removeAttribute('aria-hidden');
  }

  function bindEvents(newButton, refreshButton, closeDetail) {
    refreshButton.addEventListener('click', () => {
      if (state.selectedMapId) selectMap(state.selectedMapId);
      else loadMaps();
    });
    refs.continueButton.addEventListener('click', () => openPreview('topic'));
    refs.refreshPreviewButton.addEventListener('click', () => openPreview('refresh'));
    refs.openSavedPreviewButton.addEventListener('click', () => openSavedPreview());
    refs.stopJobButton.addEventListener('click', () => stopCurrentJob());
    refs.retryJobButton.addEventListener('click', () => retryCurrentJob());
    newButton.addEventListener('click', () => {
      if (isMobileViewport() && !state.mobile.listOpen) openMobilePanel('list', newButton);
      if (!refs.createPanel.hidden) {
        closeCreatePanel();
      } else {
        refs.createPanel.hidden = false;
        state.createPanelOpen = true;
        refs.topicInput.focus();
        loadCreateOptions();
      }
    });
    refs.cancelButton.addEventListener('click', () => {
      closeCreatePanel();
    });
    refs.form.addEventListener('submit', (event) => {
      event.preventDefault();
      createMap();
    });
    refs.groupForm.addEventListener('submit', (event) => {
      event.preventDefault();
      createGroup();
    });
    refs.exportJsonButton.addEventListener('click', () => exportJson());
    refs.exportPngButton.addEventListener('click', () => exportPng());
    refs.listSearch.addEventListener('input', () => {
      state.listQuery = refs.listSearch.value.trim().toLowerCase();
      renderMapList();
    });
    refs.listStatus.addEventListener('change', () => {
      state.listStatus = refs.listStatus.value;
      renderMapList();
    });
    refs.svg.addEventListener('wheel', handleWheel, { passive: false });
    refs.svg.addEventListener('pointerdown', handleCanvasPointerDown);
    refs.svg.addEventListener('pointermove', handleCanvasPointerMove);
    refs.svg.addEventListener('pointerup', handleCanvasPointerUp);
    refs.svg.addEventListener('pointercancel', handleCanvasPointerCancel);
    refs.svg.addEventListener('click', (event) => {
      if (state.suppressTap) {
        state.suppressTap = false;
        return;
      }
      const nodeGroup = event.target.closest ? event.target.closest('[data-node-id]') : null;
      if (nodeGroup && nodeGroup.dataset.nodeId && !state.pointer?.dragged) {
        try { nodeGroup.focus({ preventScroll: true }); } catch (_) { nodeGroup.focus(); }
        if (state.multiSelectActive) toggleMultiSelectNode(nodeGroup.dataset.nodeId);
        else selectNode(nodeGroup.dataset.nodeId, nodeGroup);
      }
    });
    refs.svg.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const nodeGroup = event.target.closest ? event.target.closest('[data-node-id]') : null;
      if (!nodeGroup?.dataset.nodeId) return;
      event.preventDefault();
      if (state.multiSelectActive) toggleMultiSelectNode(nodeGroup.dataset.nodeId);
      else selectNode(nodeGroup.dataset.nodeId, nodeGroup);
    });
    refs.root.querySelector('#literature-map-zoom-in').addEventListener('click', () => changeScale(1.2));
    refs.root.querySelector('#literature-map-zoom-out').addEventListener('click', () => changeScale(1 / 1.2));
    refs.root.querySelector('#literature-map-fit').addEventListener('click', () => fitView(true));
    refs.root.querySelector('#literature-map-locate').addEventListener('click', locateSelectedNode);
    refs.root.querySelector('#literature-map-spacing').addEventListener('click', beginSpacingPreview);
    refs.root.querySelector('#literature-map-reset').addEventListener('click', () => {
      state.view = { x: 0, y: 0, scale: 1 };
      state.viewDirty = true;
      renderGraph();
      scheduleViewSave();
    });
    refs.root.querySelectorAll('input[data-layer]').forEach((input) => {
      input.addEventListener('change', () => {
        state.layers[input.dataset.layer] = input.checked;
        state.viewDirty = true;
        renderGraph();
        scheduleViewSave();
      });
    });
    refs.labelModeSelect.addEventListener('change', () => {
      state.labelMode = normalizeLabelMode(refs.labelModeSelect.value);
      refs.labelModeSelect.value = state.labelMode;
      state.viewDirty = true;
      renderGraph();
      scheduleViewSave();
    });
    closeDetail.addEventListener('click', () => {
      state.selectedNodeId = null;
      state.selectedNode = null;
      state.nodeRequest += 1;
      state.analysisRequest += 1;
      state.analysisNodeId = null;
      stopAnalysisPolling();
      state.analysis = null;
      state.analysisJob = null;
      state.analysisHistory = [];
      state.analysisSourceStatus = null;
      state.analysisViewedId = null;
      state.analysisPollExhausted = false;
      state.conversationRequest += 1;
      state.importRequest += 1;
      refs.detailPanel.classList.remove('is-open');
      refs.detailPanel.hidden = true;
      closeMobilePanel('detail');
      renderGraph();
      renderNodeDetail(null);
    });
    refs.detailPanel.addEventListener('transitionend', (event) => {
      if (event.target !== refs.detailPanel || event.propertyName !== 'transform') return;
      if (!isMobileViewport() || !state.selectedNodeId || !refs.detailPanel.classList.contains('is-open')) return;
      ensureSelectedNodeVisible();
    });
    refs.listClose.addEventListener('click', () => closeMobilePanel('list'));
    refs.mobileListButton.addEventListener('click', () => {
      if (state.mobile.listOpen) closeMobilePanel('list');
      else openMobilePanel('list', refs.mobileListButton);
    });
    refs.mobileBackdrop.addEventListener('click', () => closeAllMobilePanels(true));
    window.addEventListener('pointerup', handleCanvasPointerUp);
    window.addEventListener('pointercancel', handleCanvasPointerCancel);
    window.addEventListener('blur', () => resetCanvasGesture(true));
    window.addEventListener('resize', handleMobileViewportResize);
    if (typeof ResizeObserver === 'function' && refs.svg) {
      state.resizeObserver?.disconnect();
      state.resizeObserver = new ResizeObserver(() => scheduleViewportStabilization());
      state.resizeObserver.observe(refs.svg);
    }
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') resetCanvasGesture(true);
    });
  }

  function closeCreatePanel() {
    if (!refs.createPanel) return;
    refs.createPanel.hidden = true;
    state.createPanelOpen = false;
    state.createOptionsRequest += 1;
    state.createOptionsLoading = false;
    refs.form.reset();
    refs.limitInput.value = '30';
    refs.projectInput.value = '';
  }

  function filteredMaps() {
    return state.maps.filter((map) => {
      const haystack = `${mapTitle(map)} ${map?.topic || ''}`.toLowerCase();
      const matchesQuery = !state.listQuery || haystack.includes(state.listQuery);
      const matchesStatus = state.listStatus === 'all' || map?.status === state.listStatus;
      return matchesQuery && matchesStatus;
    });
  }

  function optionId(value) {
    const id = String(value || '').trim();
    return id || null;
  }

  function selectedOptionIds(container) {
    return Array.from(container?.querySelectorAll('input[type="checkbox"][data-option-id]:checked') || [])
      .map((input) => optionId(input.dataset.optionId))
      .filter(Boolean);
  }

  function renderSelectionNotice(node, message, status = '') {
    if (!node) return;
    node.textContent = message || '';
    node.dataset.state = status;
  }

  function renderCheckboxOptions(container, items, selectedIds, emptyMessage) {
    if (!container) return;
    container.replaceChildren();
    if (!items.length) {
      container.append(createElement('span', 'literature-map-option-empty', emptyMessage));
      return;
    }
    items.forEach((item, index) => {
      const label = createElement('label', 'literature-map-option');
      const input = createElement('input');
      input.type = 'checkbox';
      input.name = item.name;
      input.dataset.optionId = item.id;
      input.id = `${item.name}-${index}`;
      input.value = item.id;
      input.disabled = item.enabled === false;
      input.checked = !input.disabled && selectedIds.has(item.id);
      label.append(input, createElement('span', '', item.label));
      container.append(label);
    });
  }

  function normalizeSourceOptions(payload) {
    const entries = Array.isArray(payload?.sources) ? payload.sources : [];
    return entries.map((entry) => {
      const id = optionId(entry?.source_id);
      if (!id || !SUPPORTED_MAP_SOURCE_IDS.has(id)) return null;
      return {
        id,
        name: 'source_ids',
        label: String(entry.source_kind || entry.source_id),
        enabled: entry.enabled !== false,
      };
    }).filter(Boolean);
  }

  function normalizeConferenceOptions(payload) {
    const entries = Array.isArray(payload?.conferences) ? payload.conferences : [];
    return entries.map((entry) => {
      const id = optionId(entry?.conference_id);
      if (!id || !SUPPORTED_MAP_CONFERENCE_IDS.has(id)) return null;
      return {
        id,
        name: 'conference_ids',
        label: String(entry.name || entry.short_name || entry.conference_id),
        enabled: entry.enabled !== false,
      };
    }).filter(Boolean);
  }

  function normalizeProjectOptions(payload) {
    const entries = Array.isArray(payload?.projects) ? payload.projects : [];
    return entries.map((entry) => {
      const id = optionId(entry?.project_id);
      const name = String(entry?.name || '').trim();
      if (!id || !name) return null;
      return { id, label: name };
    }).filter(Boolean);
  }

  function renderProjectOptions(items) {
    if (!refs.projectInput) return;
    const current = refs.projectInput.value;
    refs.projectInput.replaceChildren();
    const unbound = createElement('option', '', '不绑定项目');
    unbound.value = '';
    refs.projectInput.append(unbound);
    items.forEach((item) => {
      const option = createElement('option', '', item.label);
      option.value = item.id;
      refs.projectInput.append(option);
    });
    if (items.some((item) => item.id === current)) refs.projectInput.value = current;
  }

  async function loadProjectsForMapForm() {
    const projects = [];
    let cursor = null;
    let pageCount = 0;
    do {
      const params = new URLSearchParams({ limit: '100' });
      if (cursor) params.set('cursor', cursor);
      const payload = await requestCatalog(`/api/projects?${params.toString()}`);
      projects.push(...normalizeProjectOptions(payload));
      cursor = optionId(payload?.next_cursor);
      pageCount += 1;
    } while (cursor && pageCount < 10);
    return { items: projects, truncated: Boolean(cursor) };
  }

  async function loadCreateOptions() {
    if (state.createOptionsLoaded || !state.createPanelOpen || state.createOptionsLoading) return;
    const requestId = ++state.createOptionsRequest;
    state.createOptionsLoading = true;
    renderSelectionNotice(refs.sourceNotice, '正在读取可用来源…');
    renderSelectionNotice(refs.conferenceNotice, '正在读取可用会议…');
    renderSelectionNotice(refs.projectNotice, '正在读取项目列表…');
    const [sources, conferences, projects] = await Promise.allSettled([
      requestCatalog('/api/papers/sources'),
      requestCatalog('/api/papers/conferences'),
      loadProjectsForMapForm(),
    ]);
    if (requestId !== state.createOptionsRequest || !state.createPanelOpen) return;
    state.createOptionsLoading = false;
    state.createOptionsRequest = 0;
    state.createOptionsLoaded = true;

    if (sources.status === 'fulfilled') {
      const selected = new Set(selectedOptionIds(refs.sourceOptions));
      const items = normalizeSourceOptions(sources.value);
      renderCheckboxOptions(refs.sourceOptions, items, selected, '通用来源（不限）');
      renderSelectionNotice(refs.sourceNotice, items.length ? '可多选；不选择表示不限来源。' : '暂无可用来源，仍可按通用来源建图。', items.length ? '' : 'warning');
    } else {
      renderCheckboxOptions(refs.sourceOptions, [], new Set(), '通用来源（不限）');
      renderSelectionNotice(refs.sourceNotice, '来源筛选暂不可用，仍可直接建图（不限来源）。', 'warning');
    }
    if (conferences.status === 'fulfilled') {
      const selected = new Set(selectedOptionIds(refs.conferenceOptions));
      const items = normalizeConferenceOptions(conferences.value);
      renderCheckboxOptions(refs.conferenceOptions, items, selected, '通用会议范围（不限）');
      renderSelectionNotice(refs.conferenceNotice, items.length ? '可多选；不选择表示不限会议。' : '暂无可用会议，仍可按通用会议范围建图。', items.length ? '' : 'warning');
    } else {
      renderCheckboxOptions(refs.conferenceOptions, [], new Set(), '通用会议范围（不限）');
      renderSelectionNotice(refs.conferenceNotice, '会议筛选暂不可用，仍可直接建图（不限会议）。', 'warning');
    }
    if (projects.status === 'fulfilled') {
      const result = projects.value && typeof projects.value === 'object' ? projects.value : {};
      const items = Array.isArray(result.items) ? result.items : [];
      renderProjectOptions(items);
      const projectMessage = result.truncated
        ? '项目列表未加载完（已显示前 1000 项）；可关闭后重新打开重试，或先不绑定项目。'
        : (items.length ? '只显示当前账户可用项目。' : '暂无项目，默认不绑定。');
      renderSelectionNotice(refs.projectNotice, projectMessage, result.truncated || !items.length ? 'warning' : '');
    } else {
      renderProjectOptions([]);
      renderSelectionNotice(refs.projectNotice, '项目列表暂不可用，仍可不绑定项目建图。', 'warning');
    }
  }

  function renderMapList() {
    if (!refs.mapList) return;
    refs.mapList.replaceChildren();
    const visibleMaps = filteredMaps();
    refs.count.textContent = `${visibleMaps.length}/${state.maps.length}`;
    setHidden(refs.listEmpty, visibleMaps.length > 0);
    visibleMaps.forEach((map) => {
      const item = createElement('button', 'literature-map-list-item');
      item.type = 'button';
      item.dataset.mapId = map.map_id || '';
      item.setAttribute('role', 'listitem');
      item.setAttribute('aria-pressed', String(map.map_id === state.selectedMapId));
      const title = createElement('strong', 'literature-map-list-title', mapTitle(map));
      const topic = createElement('span', 'literature-map-list-topic', map.topic || '主题未提供');
      const meta = createElement('span', 'literature-map-list-meta');
      meta.append(renderStatusBadge(map.status));
      if (map.requested_count) meta.append(createElement('span', '', `${map.requested_count} 篇`));
      item.append(title, topic, meta);
      item.addEventListener('click', () => {
        selectMap(map.map_id);
        if (isMobileViewport()) closeMobilePanel('list');
      });
      refs.mapList.append(item);
    });
  }

  function renderMultiSelectControls() {
    if (!refs.multiSelectToggle || !refs.selectionToolbar) return;
    refs.multiSelectToggle.disabled = !state.map?.map_id;
    refs.multiSelectToggle.textContent = state.multiSelectActive ? '退出多选模式' : '多选模式';
    refs.multiSelectToggle.setAttribute('aria-pressed', String(state.multiSelectActive));
    refs.selectionToolbar.hidden = !state.multiSelectActive;
    const count = state.multiSelectedNodeIds.size;
    if (refs.selectionCount) refs.selectionCount.textContent = `已选 ${count} 篇`;
    if (refs.selectionPalette) {
      refs.selectionPalette.hidden = !state.multiSelectActive || count === 0;
      const apply = refs.selectionPalette.querySelector('.literature-map-color-apply');
      if (apply) {
        apply.textContent = `应用到 ${count} 篇`;
        apply.disabled = !state.map?.map_id || count === 0 || Boolean(state.colorSaveInFlight);
      }
    }
  }

  function toggleMultiSelectMode() {
    if (!state.map?.map_id) return;
    if (!state.multiSelectActive) {
      state.multiSelectActive = true;
      state.multiSelectedNodeIds.clear();
      state.selectedNodeId = null;
      state.selectedNode = null;
      state.nodeRequest += 1;
      state.analysisRequest += 1;
      renderNodeDetail(null);
      setStatus('多选模式已开启；点击可见节点添加或移除选择。', 'waiting');
      renderGraph();
      return;
    }
    const selectedNodeId = [...state.multiSelectedNodeIds].find((nodeId) => activeNodes().some((node) => node.node_id === nodeId)) || null;
    state.multiSelectActive = false;
    state.multiSelectedNodeIds.clear();
    state.colorDraft = null;
    renderGraph();
    if (selectedNodeId) selectNode(selectedNodeId);
    else {
      state.selectedNodeId = null;
      state.selectedNode = null;
      renderNodeDetail(null);
      setStatus('已退出多选模式。');
    }
  }

  function toggleMultiSelectNode(nodeId) {
    if (!state.multiSelectActive || !activeNodes().some((node) => node.node_id === nodeId)) return;
    if (state.multiSelectedNodeIds.has(nodeId)) {
      state.multiSelectedNodeIds.delete(nodeId);
    } else if (state.multiSelectedNodeIds.size >= MAX_MAP_NODES) {
      setStatus(`一次最多可选择 ${MAX_MAP_NODES} 篇论文。`, 'error');
      return;
    } else {
      state.multiSelectedNodeIds.add(nodeId);
    }
    if (state.colorDraft?.target === 'selection') state.colorDraft.nodeIds = [...state.multiSelectedNodeIds];
    renderGraph();
  }

  function renderGroupLegend() {
    if (!refs.groupLegend) return;
    refs.groupLegend.replaceChildren();
    if (!state.groups.length) {
      refs.groupLegend.hidden = true;
      return;
    }
    refs.groupLegend.hidden = false;
    state.groups.forEach((group) => {
      const item = createElement('span', 'literature-map-group-legend-item');
      const swatch = createElement('span', 'literature-map-group-swatch');
      swatch.style.backgroundColor = currentGroupColor(group.group_id);
      swatch.setAttribute('aria-hidden', 'true');
      item.append(swatch, createElement('span', '', group.name));
      refs.groupLegend.append(item);
    });
    const ungrouped = createElement('span', 'literature-map-group-legend-item');
    const ungroupedSwatch = createElement('span', 'literature-map-group-swatch is-ungrouped');
    ungroupedSwatch.setAttribute('aria-hidden', 'true');
    ungrouped.append(ungroupedSwatch, createElement('span', '', '未分组'));
    refs.groupLegend.append(ungrouped);
  }

  function renderGroups() {
    if (!refs.groupsPanel) return;
    refs.groupsPanel.hidden = !state.map?.map_id;
    refs.groupList.replaceChildren();
    setHidden(refs.groupEmpty, state.groups.length > 0);
    state.groups.forEach((group) => {
      const row = createElement('div', 'literature-map-group-row');
      row.dataset.groupId = group.group_id;
      const swatch = createElement('button', 'literature-map-group-swatch literature-map-group-color-trigger');
      swatch.type = 'button';
      swatch.style.backgroundColor = currentGroupColor(group.group_id);
      swatch.setAttribute('aria-label', `修改分组颜色：${group.name}`);
      swatch.addEventListener('click', () => {
        const palette = row.querySelector('.literature-map-color-palette[data-target="group"]');
        const opening = palette?.hidden !== false;
        if (state.colorDraft && (state.colorDraft.target !== 'group' || state.colorDraft.groupId !== group.group_id)) state.colorDraft = null;
        if (palette) palette.hidden = !opening;
        renderGraph();
      });
      const name = createElement('span', 'literature-map-group-name', group.name);
      name.title = group.name;
      const rename = createElement('button', 'secondary-button literature-map-group-rename', '重命名');
      rename.type = 'button';
      rename.dataset.groupId = group.group_id;
      rename.addEventListener('click', () => renameGroup(group, rename));
      const palette = createColorPalette('group', group.group_id);
      palette.hidden = !colorDraftMatches('group', group.group_id);
      const remove = createElement('button', 'secondary-button literature-map-group-delete', '删除');
      remove.type = 'button';
      remove.dataset.groupId = group.group_id;
      remove.addEventListener('click', () => deleteGroup(group, remove));
      row.append(swatch, name, rename, remove, palette);
      refs.groupList.append(row);
    });
    renderGroupLegend();
  }

  function updateGroupState(payload) {
    const revision = Number(payload?.revision);
    if (Number.isInteger(revision) && state.map) state.map = { ...state.map, revision };
    state.groups = normalizeGroups(payload);
    renderGroups();
    renderGraph();
    if (state.selectedNode) renderNodeDetail(state.selectedNode);
    renderMapList();
  }

  async function loadGroups(mapId, requestId = state.mapRequest) {
    if (!mapId) return;
    const groupRequestId = ++state.groupRequest;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/groups`);
      if (groupRequestId !== state.groupRequest || requestId !== state.mapRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      updateGroupState(payload);
    } catch (error) {
      if (groupRequestId !== state.groupRequest || requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      state.groups = [];
      renderGroups();
      renderSpacingPreviewPanel();
      setStatus(`分组读取失败：${errorAction(error, '请重新打开地图后重试。')}`, 'error');
    }
  }

  async function runGroupMutation(path, method, body, button, onSuccess, onConfirmed, verification = null) {
    if (!state.map?.map_id || !state.active) return;
    const mapId = state.map.map_id;
    const requestId = ++state.groupRequest;
    const isCurrentMap = () => mapId === state.selectedMapId && state.map?.map_id === mapId && state.active;
    const isCurrentRequest = () => isCurrentMap() && requestId === state.groupRequest;
    if (button) button.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}${path}`, { method, body: JSON.stringify({ expected_revision: state.map.revision, ...body }) });
      if (typeof onConfirmed === 'function') onConfirmed(payload);
      if (!isCurrentRequest()) return;
      updateGroupState(payload);
      if (typeof onSuccess === 'function') onSuccess(payload);
      setStatus('分组已保存。', 'waiting');
    } catch (error) {
      if (error.status === 409 || String(error.code || '').toUpperCase() === 'MAP_REVISION_CONFLICT' || String(error.code || '').toLowerCase().includes('revision')) {
        if (!isCurrentRequest()) return;
        if (button) button.disabled = false;
        setStatus('地图版本已变化，正在重新读取；未覆盖其他操作。', 'error');
        await selectMap(mapId);
        return;
      }
      const outcomeUnknown = error.name === 'AbortError' || !error.status || error.retryable || Number(error.status) >= 500;
      if (verification && outcomeUnknown) {
        let payload;
        try {
          payload = await request(`/${encodeURIComponent(mapId)}${verification.path}`);
        } catch (_) {
          if (!isCurrentRequest()) return;
          if (button) button.disabled = false;
          setStatus(verification.readFailedMessage, 'error');
          return;
        }
        const confirmed = verification.matches(payload);
        if (confirmed && isCurrentMap() && typeof onConfirmed === 'function') onConfirmed(payload);
        if (!isCurrentRequest()) return;
        updateGroupState(payload);
        if (confirmed) {
          if (typeof onSuccess === 'function') onSuccess(payload);
          setStatus(verification.successMessage, 'waiting');
        } else {
          if (button) button.disabled = false;
          setStatus(verification.uncertainMessage, 'error');
        }
        return;
      }
      if (!isCurrentRequest()) return;
      if (button) button.disabled = false;
      setStatus(`分组保存失败：${errorAction(error, '请检查分组名称和颜色后重试。')}`, 'error');
    }
  }

  function createGroup() {
    let group;
    try { group = validateGroupForm(refs.groupNameInput.value, refs.groupColorInput.value); } catch (error) {
      setStatus(errorAction(error), 'error');
      return;
    }
    runGroupMutation('/groups', 'POST', group, refs.groupCreateButton, () => {
      refs.groupNameInput.value = '';
      refs.groupColorInput.value = '#8d80e6';
    });
  }

  function renameGroup(group, button) {
    if (!group) return;
    const nextName = window.prompt('请输入新的分组名称', group.name);
    if (nextName === null) return;
    let values;
    try { values = validateGroupForm(nextName, group.color); } catch (error) {
      setStatus(errorAction(error), 'error');
      return;
    }
    runGroupMutation(`/groups/${encodeURIComponent(group.group_id)}`, 'PATCH', { name: values.name }, button);
  }

  function updateGroup(group, values, input) {
    if (!group) return;
    let normalized;
    try { normalized = validateGroupForm(group.name, values.color || group.color); } catch (error) {
      if (input) input.value = group.color;
      setStatus(errorAction(error), 'error');
      return;
    }
    runGroupMutation(`/groups/${encodeURIComponent(group.group_id)}`, 'PATCH', { color: normalized.color }, input);
  }

  function deleteGroup(group, button) {
    if (!group) return;
    runGroupMutation(`/groups/${encodeURIComponent(group.group_id)}`, 'DELETE', {}, button);
  }

  function updateGraphColorOverrides(nodeIds, colorOverride, returnedNodes = []) {
    const returned = new Map(returnedNodes.map((node) => [node.node_id, node]));
    normalizeNodes(state.graph).forEach((node) => {
      if (!nodeIds.includes(node.node_id)) return;
      const saved = returned.get(node.node_id);
      node.color_override = saved && Object.prototype.hasOwnProperty.call(saved, 'color_override')
        ? normalizeHexColor(saved.color_override)
        : colorOverride;
      if (saved && Object.prototype.hasOwnProperty.call(saved, 'group_id')) node.group_id = saved.group_id || null;
    });
    if (state.selectedNode && nodeIds.includes(state.selectedNode.node_id)) {
      state.selectedNode.color_override = colorOverride;
    }
  }

  function nodeColorWriteMatches(graph, nodeIds, colorOverride) {
    const byId = new Map(normalizeNodes(graph).map((node) => [node.node_id, node]));
    return nodeIds.every((nodeId) => {
      const node = byId.get(nodeId);
      if (!node) return false;
      return (normalizeHexColor(node.color_override) || null) === colorOverride;
    });
  }

  async function verifyNodeColorWrite(mapId, nodeIds, colorOverride) {
    const payload = await request(`/${encodeURIComponent(mapId)}/graph`);
    if (mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return { confirmed: false, payload, stale: true };
    state.graph = payload;
    state.map = normalizeMap(payload.map) || state.map;
    const confirmed = nodeColorWriteMatches(payload, nodeIds, colorOverride);
    renderGraph();
    if (state.selectedNode && nodeIds.includes(state.selectedNode.node_id)) {
      const updated = normalizeNodes(payload).find((node) => node.node_id === state.selectedNode.node_id);
      if (updated) state.selectedNode = { ...state.selectedNode, ...updated };
      renderNodeDetail(state.selectedNode);
    }
    return { confirmed, payload };
  }

  async function reloadAfterColorConflict(mapId, nodeIds, target) {
    const preservedDraft = state.colorDraft ? { ...state.colorDraft, nodeIds: [...state.colorDraft.nodeIds] } : null;
    const wasMultiSelect = state.multiSelectActive;
    const selectedNodeId = state.selectedNodeId;
    await selectMap(mapId);
    if (mapId !== state.selectedMapId || !state.active) return;
    state.colorDraft = preservedDraft;
    if (wasMultiSelect) {
      state.multiSelectActive = true;
      state.multiSelectedNodeIds = new Set(nodeIds.filter((nodeId) => activeNodes().some((node) => node.node_id === nodeId)));
      renderGraph();
    } else if (target === 'node' && selectedNodeId && activeNodes().some((node) => node.node_id === selectedNodeId)) {
      await selectNode(selectedNodeId);
    } else {
      renderGraph();
    }
    if (state.colorDraft) state.colorDraft.nodeIds = target === 'selection' ? [...state.multiSelectedNodeIds] : [state.selectedNodeId].filter(Boolean);
    renderNodeDetail(state.selectedNode);
    setStatus('地图版本已变化，已重新读取。颜色草稿仍保留；核对后请再次点击“应用到 N 篇”。', 'error');
  }

  async function applyNodeColor(target, button) {
    if (!state.map?.map_id || !state.active || state.colorSaveInFlight) return;
    const draft = colorDraftMatches(target) ? state.colorDraft : null;
    if (!draft || (draft.colorOverride !== null && !normalizeHexColor(draft.colorOverride))) {
      setStatus('请先选择有效的颜色。', 'error');
      return;
    }
    const nodeIds = colorTargetNodeIds(target);
    if (!nodeIds.length || nodeIds.length > MAX_MAP_NODES) {
      setStatus(`请选择 1 到 ${MAX_MAP_NODES} 篇可见论文后再应用颜色。`, 'error');
      return;
    }
    const mapId = state.map.map_id;
    const ownerId = mapOwnerId();
    const expectedRevision = Number(state.map.revision);
    const colorOverride = draft.colorOverride === null ? null : normalizeHexColor(draft.colorOverride);
    state.colorSaveInFlight = true;
    refs.root.querySelectorAll('.literature-map-color-apply').forEach((item) => { item.disabled = true; });
    if (button) button.disabled = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), COLOR_SAVE_TIMEOUT_MS);
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/node-styles`, {
        method: 'PATCH',
        body: JSON.stringify({ expected_revision: expectedRevision, node_ids: nodeIds, color_override: colorOverride }),
        signal: controller.signal,
      });
      if (mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) {
        if (colorOverride) rememberRecentColor(colorOverride, { ownerId, mapId });
        return;
      }
      const revision = Number(payload?.revision);
      if (Number.isInteger(revision)) state.map = { ...state.map, revision };
      updateGraphColorOverrides(nodeIds, colorOverride, Array.isArray(payload.nodes) ? payload.nodes : []);
      if (colorOverride) rememberRecentColor(colorOverride, { ownerId, mapId });
      state.colorDraft = null;
      renderGraph();
      renderGroups();
      if (!state.multiSelectActive && state.selectedNode) renderNodeDetail(state.selectedNode);
      setStatus('颜色已保存。', 'waiting');
    } catch (error) {
      if (mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      if (error.status === 409) {
        await reloadAfterColorConflict(mapId, nodeIds, target);
        return;
      }
      if (error.name === 'AbortError' || !error.status || error.retryable) {
        try {
          const verification = await verifyNodeColorWrite(mapId, nodeIds, colorOverride);
          if (verification.stale || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
          if (verification.confirmed) {
            const revision = Number(verification.payload?.map?.revision);
            if (Number.isInteger(revision)) state.map = { ...state.map, revision };
            if (colorOverride) rememberRecentColor(colorOverride, { ownerId, mapId });
            state.colorDraft = null;
            renderGraph();
            if (!state.multiSelectActive && state.selectedNode) renderNodeDetail(state.selectedNode);
            setStatus('颜色已保存（已重新读取核实）。', 'waiting');
            return;
          }
          setStatus('保存结果未能确认；已重新读取地图，颜色草稿仍保留。请核对后重试。', 'error');
        } catch (_) {
          if (mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
          setStatus('保存结果暂无法确认；颜色草稿仍保留，请稍后核对地图后重试。', 'error');
        }
        return;
      }
      setStatus(`颜色保存失败：${errorAction(error, '颜色草稿仍保留，可修正后重试。')}`, 'error');
    } finally {
      window.clearTimeout(timeoutId);
      state.colorSaveInFlight = false;
      if (button?.isConnected) button.disabled = false;
      renderMultiSelectControls();
      refs.root.querySelectorAll('.literature-map-color-apply').forEach((item) => { item.disabled = item.closest('.literature-map-color-palette[data-target="selection"]') ? !state.multiSelectedNodeIds.size : false; });
    }
  }

  function applyGroupColor(groupId, button) {
    const group = groupById(groupId);
    if (!group || !state.map?.map_id || !state.active || state.colorSaveInFlight) return;
    const draft = colorDraftMatches('group', groupId) ? state.colorDraft : null;
    const color = normalizeHexColor(draft?.colorOverride);
    if (!color) {
      setStatus('请先选择有效的分组颜色。', 'error');
      return;
    }
    const mapId = state.map.map_id;
    const ownerId = mapOwnerId();
    state.colorSaveInFlight = true;
    if (button) button.disabled = true;
    runGroupMutation(`/groups/${encodeURIComponent(groupId)}`, 'PATCH', { color }, button, () => {
      state.colorDraft = null;
      renderGroups();
      renderGraph();
    }, () => {
      rememberRecentColor(color, { ownerId, mapId });
    }, {
      path: '/groups',
      matches: (payload) => normalizeGroups(payload).some((item) => item.group_id === groupId && item.color === color),
      successMessage: '分组颜色已保存（已重新读取核实）。',
      uncertainMessage: '分组颜色保存结果未能确认；已重新读取分组，颜色草稿仍保留，请核对后重试。',
      readFailedMessage: '分组颜色保存结果暂无法确认；颜色草稿仍保留，请稍后核对分组并重试。',
    }).finally(() => {
      state.colorSaveInFlight = false;
    });
  }

  async function loadMaps() {
    try {
      const payload = await request('');
      state.maps = Array.isArray(payload.maps) ? payload.maps.map(normalizeMap).filter(Boolean) : [];
      renderMapList();
      if (state.selectedMapId) {
        const existing = state.maps.find((map) => map.map_id === state.selectedMapId);
        if (existing && !state.map) await selectMap(existing.map_id);
      }
      if (!state.maps.length) {
        setStatus('还没有地图。点击“新建地图”输入主题即可开始。');
      } else if (!state.map) {
        setStatus('选择一张地图查看已保存的图谱。');
      }
    } catch (error) {
      setStatus(`地图列表加载失败：${errorAction(error, '请确认服务已启动后重试。')}`, 'error');
    }
  }

  function buildCreatePayload() {
    const topic = refs.topicInput.value.trim();
    const name = refs.nameInput.value.trim();
    const yearStart = parseYear(refs.yearStart.value);
    const yearEnd = parseYear(refs.yearEnd.value);
    if (!topic || topic.length > 500) throw new LiteratureMapError('主题不能为空且最多 500 个字符。');
    if (Number.isNaN(yearStart) || Number.isNaN(yearEnd)) throw new LiteratureMapError('年份必须是四位数字。');
    if (yearStart !== null && yearEnd !== null && yearStart > yearEnd) throw new LiteratureMapError('起始年份不能晚于结束年份。');
    const limit = Number(refs.limitInput.value);
    if (![20, 30, 50].includes(limit)) throw new LiteratureMapError('首批数量只能选择 20、30 或 50。');
    const payload = { topic, limit, idempotency_key: makeIdempotencyKey() };
    if (name) payload.name = name;
    if (yearStart !== null) payload.year_start = yearStart;
    if (yearEnd !== null) payload.year_end = yearEnd;
    const sourceIds = selectedOptionIds(refs.sourceOptions);
    const conferenceIds = selectedOptionIds(refs.conferenceOptions);
    if (sourceIds.length) payload.source_ids = sourceIds;
    if (conferenceIds.length) payload.conference_ids = conferenceIds;
    const projectId = optionId(refs.projectInput.value);
    if (projectId) payload.project_id = projectId;
    return payload;
  }

  async function createMap() {
    refs.submitButton.disabled = true;
    setStatus('正在提交主题地图任务…');
    let payload;
    try {
      payload = buildCreatePayload();
    } catch (error) {
      refs.submitButton.disabled = false;
      setStatus(errorAction(error), 'error');
      return;
    }
    const requestId = ++state.mapRequest;
    try {
      const response = await request('', { method: 'POST', body: JSON.stringify(payload) });
      if (requestId !== state.mapRequest || !state.active) return;
      if (response?.status && response.status !== 'generating') {
        // The server is authoritative; this branch only preserves its status text.
        setStatus(`地图任务已提交：${mapStatusLabel(response.status)}。`);
      } else {
        setStatus('地图任务已提交，正在后台分阶段生成。');
      }
      const map = normalizeMap(response.map);
      state.map = map;
      state.selectedMapId = map?.map_id || response.map_id || null;
      state.job = response.job || null;
      state.eventCursor = 0;
      state.graph = null;
      state.groups = [];
      renderGroups();
      state.selectedNodeId = null;
      state.selectedNode = null;
      state.positions = Object.create(null);
      state.positionsDirty = false;
      state.viewDirty = false;
      state.layoutPendingIds.clear();
      state.layoutPreview = null;
      state.layoutPreviewActive = false;
      closeCreatePanel();
      await loadMaps();
      if (requestId !== state.mapRequest || !state.active) return;
      if (state.selectedMapId) {
        await loadMapGraph(state.selectedMapId);
        await loadGroups(state.selectedMapId, requestId);
        renderJobActions();
        startPolling();
      }
    } catch (error) {
      if (requestId !== state.mapRequest || !state.active) return;
      setStatus(`创建失败：${errorAction(error, '请检查主题和筛选条件后重试。')}`, 'error');
    } finally {
      refs.submitButton.disabled = false;
    }
  }

  async function selectMap(mapId) {
    if (!mapId) return;
    const previousMapId = state.selectedMapId;
    if (previousMapId !== mapId) {
      state.multiSelectActive = false;
      state.multiSelectedNodeIds.clear();
      state.colorDraft = null;
    }
    const requestId = ++state.mapRequest;
    state.selectedMapId = mapId;
    state.selectedNodeId = null;
    state.selectedNode = null;
    state.groups = [];
    state.map = null;
    state.graph = null;
    state.job = null;
    state.eventCursor = 0;
    state.positions = Object.create(null);
    state.positionsDirty = false;
    state.spacingViolationCount = 0;
    state.viewDirty = false;
    state.layoutPendingIds.clear();
    state.layoutPreview = null;
    state.layoutPreviewActive = false;
    state.nodeRequest += 1;
    state.analysisRequest += 1;
    state.analysisNodeId = null;
    stopAnalysisPolling();
    state.analysis = null;
    state.analysisJob = null;
    state.analysisHistory = [];
    state.analysisSourceStatus = null;
    state.analysisViewedId = null;
    state.analysisPollExhausted = false;
    state.analysisTab = 'abstract';
    state.analysisSubmitInFlight = false;
    state.analysisManualRequest = false;
    state.conversationRequest = 0;
    state.importRequest += 1;
    state.viewRequest += 1;
    state.initialFitPending = false;
    if (previousMapId !== mapId) {
      stopPreviewPolling();
      state.preview = null;
      state.previewJob = null;
      state.previewId = null;
      state.previewKind = null;
      state.previewNodeId = null;
      state.savedPreview = null;
      state.previewDiscoveryNotice = '';
      state.previewSelection.clear();
      state.previewConflict = false;
    }
    state.previewRequest += 1;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = null;
    stopPolling();
    stopAnalysisQueuePolling();
    state.queueRequest += 1;
    state.queueEnsureMapId = null;
    state.queueEnsureKey = null;
    state.analysisQueue = null;
    state.queueSignature = '';
    state.queueError = '';
    renderMapList();
    renderGroups();
    renderNodeDetail(null);
    renderGraph();
    renderSpacingPreviewPanel();
    renderAnalysisQueue();
    setStatus('正在读取已保存地图…');
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}`);
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      state.map = normalizeMap(payload.map);
      state.job = payload.latest_job || null;
      applySavedView(state.map);
      await loadMapGraph(mapId);
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      await loadGroups(mapId, requestId);
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      await ensureAnalysisQueue(mapId, requestId);
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      await restorePreviewForMap(mapId, requestId);
      renderMapList();
      if (state.job && !TERMINAL_JOB_STATES.has(state.job.status)) startPolling();
      const mapStatus = state.map?.status === 'partial' ? '地图部分完成；已保留可用节点并标注失败阶段。' : '地图已打开，图谱数据来自本地保存结果。';
      const spacingNotice = state.spacingViolationCount
        ? `检测到${state.spacingViolationCount}对节点间距不足，原有位置未修改；可点击“整理间距”预览。`
        : '';
      setStatus([state.previewDiscoveryNotice, mapStatus, spacingNotice].filter(Boolean).join(' '),
        state.previewDiscoveryNotice ? 'waiting' : (state.map?.status === 'partial' ? 'partial' : ''));
      renderJobActions();
    } catch (error) {
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      setStatus(`打开地图失败：${errorAction(error, '请重新点击地图重试。')}`, 'error');
    }
  }

  function applySavedView(map) {
    const settings = map?.view_settings || {};
    const viewport = settings.viewport || {};
    const savedX = Number(viewport.x);
    const savedY = Number(viewport.y);
    const savedScale = Number(viewport.scale);
    state.view = {
      x: Number.isFinite(savedX) ? savedX : 0,
      y: Number.isFinite(savedY) ? savedY : 0,
      scale: Number.isFinite(savedScale) && savedScale > 0 ? savedScale : 1,
    };
    // A viewport persisted at the minimum zoom is not useful as an opening
    // view for a graph. The exact backend default is also an uninitialized
    // view for a newly created map. Fit it once after the graph arrives,
    // but leave ordinary saved views (including intentional zoom/pan) alone.
    state.initialFitPending = !Number.isFinite(savedScale)
      || savedScale <= MIN_MAP_SCALE + INITIAL_FIT_SCALE_EPSILON
      || (savedX === 0 && savedY === 0 && savedScale === 1);
    const layers = settings.layers || {};
    state.layers = { citation: layers.citation !== false, similarity: layers.similarity !== false };
    state.labelMode = normalizeLabelMode(settings.label_mode);
    state.nodeStyle = normalizeNodeStyle(settings.node_style);
    state.nodeStyleDraft = { ...state.nodeStyle };
    refs.root?.querySelectorAll('input[data-layer]').forEach((input) => { input.checked = state.layers[input.dataset.layer]; });
    if (refs.labelModeSelect) refs.labelModeSelect.value = state.labelMode;
    renderNodeStyleControls();
  }

  async function loadMapGraph(mapId) {
    const requestId = ++state.graphRequest;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/graph`);
      if (requestId !== state.graphRequest || mapId !== state.selectedMapId || !state.active) return;
      state.graph = payload;
      state.map = normalizeMap(payload.map) || state.map;
      state.job = payload.latest_job || state.job;
      state.layerStatus = {};
      LAYER_NAMES.forEach((kind) => {
        state.layerStatus[kind] = payload.layers?.[kind]?.status || 'waiting';
      });
      const nodes = activeNodes(payload);
      state.layoutPendingIds.clear();
      nodes.forEach((node, index) => {
        if (node.position && Number.isFinite(Number(node.position.x)) && Number.isFinite(Number(node.position.y))) {
          state.positions[node.node_id] = { x: Number(node.position.x), y: Number(node.position.y) };
        } else {
          state.layoutPendingIds.add(node.node_id);
          if (!state.positions[node.node_id]) state.positions[node.node_id] = initialPosition(index, nodes.length);
        }
      });
      if (state.layoutPendingIds.size) {
        const pending = nodes.filter((node) => state.layoutPendingIds.has(node.node_id) && !node.removed && !node.tombstone);
        const generated = layoutPendingNodes(pending, state.positions, nodes.filter((node) => !state.layoutPendingIds.has(node.node_id) && !node.removed && !node.tombstone));
        Object.assign(state.positions, generated);
        state.layoutPendingIds.clear();
        state.positionsDirty = true;
      }
      state.spacingViolationCount = countSpacingViolations(nodes);
      if (state.initialFitPending && fitView(false)) state.initialFitPending = false;
      refs.currentTitle.textContent = state.map ? mapTitle(state.map) : '文献地图';
      renderCurrentMeta();
      renderGraph();
      renderJobActions();
      if (state.positionsDirty) scheduleViewSave();
      if (state.selectedNodeId) selectNode(state.selectedNodeId);
    } catch (error) {
      if (requestId !== state.graphRequest || mapId !== state.selectedMapId || !state.active) return;
      setStatus(`图谱读取失败：${errorAction(error, '请重新打开地图重试。')}`, 'error');
      refs.currentMeta.textContent = '图谱读取失败；原有地图数据未被修改。';
    }
  }

  function renderCurrentMeta() {
    if (!refs.currentMeta) return;
    const nodes = normalizeNodes(state.graph).length;
    const edges = normalizeEdges(state.graph).length;
    const status = state.job?.status || state.map?.status || '';
    const stage = state.job?.step ? ` · 阶段：${stageLabel(state.job.step)}` : '';
    refs.currentMeta.textContent = state.map ? `${nodes} 个节点 · ${edges} 条关系 · ${mapStatusLabel(status)}${stage}` : '图谱会在后台分阶段生成。';
  }

  function activeJob() {
    if (state.previewJob && (!TERMINAL_JOB_STATES.has(state.previewJob.status) || hasRetryableUnits(state.previewJob))) return state.previewJob;
    return state.job;
  }

  function hasRetryableUnits(job) {
    if (!job) return false;
    if (Number(job.retryable_count) > 0) return true;
    return Array.isArray(job.failed_units) && job.failed_units.some((unit) => unit && unit.retryable !== false);
  }

  function renderJobActions() {
    if (!refs.stopJobButton || !refs.retryJobButton || !refs.openSavedPreviewButton) return;
    const job = activeJob();
    const canStop = Boolean(job?.job_id && !TERMINAL_JOB_STATES.has(job.status));
    const canRetry = Boolean(job?.job_id && TERMINAL_JOB_STATES.has(job.status) && hasRetryableUnits(job));
    refs.stopJobButton.hidden = !canStop;
    refs.stopJobButton.disabled = false;
    refs.retryJobButton.hidden = !canRetry;
    refs.retryJobButton.disabled = false;
    refs.continueButton.hidden = !state.map?.map_id;
    refs.refreshPreviewButton.hidden = !state.map?.map_id;
    refs.openSavedPreviewButton.hidden = !state.savedPreview || Boolean(state.preview || state.previewId);
  }

  function previewStorageKey(mapId) {
    return `literature-map-preview:${mapId}`;
  }

  function persistPreviewSession() {
    if (!state.map?.map_id || !state.previewId) return;
    try {
      window.sessionStorage.setItem(previewStorageKey(state.map.map_id), JSON.stringify({
        preview_id: state.previewId,
        kind: state.previewKind,
        node_id: state.previewNodeId,
      }));
    } catch (_) {
      // Session storage is an optional convenience; server state remains authoritative.
    }
  }

  function clearPreviewSession(mapId = state.map?.map_id) {
    if (!mapId) return;
    try { window.sessionStorage.removeItem(previewStorageKey(mapId)); } catch (_) {}
  }

  function stopPreviewPolling() {
    if (state.previewPollTimer) window.clearTimeout(state.previewPollTimer);
    state.previewPollTimer = null;
    state.previewPollGeneration += 1;
  }

  function schedulePreviewPoll(delay) {
    if (!state.active || !state.map?.map_id || !state.previewId) return;
    state.previewPollTimer = window.setTimeout(pollPreview, delay);
  }

  function previewReady(preview) {
    return ['completed', 'partial', 'ready'].includes(String(preview?.status || '').toLowerCase());
  }

  function previewTerminal(preview) {
    return previewReady(preview) || ['failed', 'stopped', 'expired', 'applied'].includes(String(preview?.status || '').toLowerCase());
  }

  function previewKindLabel(kind) {
    return { topic: '继续搜索', references: '参考文献', citations: '引用它的论文', refresh: '刷新预览' }[kind] || '扩展预览';
  }

  function previewCandidates() {
    return Array.isArray(state.preview?.candidates) ? state.preview.candidates.filter((candidate) => candidate && candidate.candidate_id) : [];
  }

  function selectedPreviewIds() {
    return Array.from(state.previewSelection).filter((candidateId) => previewCandidates().some((candidate) => candidate.candidate_id === candidateId && !candidate.already_present && !candidate.existing && !candidate.removed));
  }

  function previewHasDiff(preview = state.preview) {
    if (!preview?.diff) return false;
    return Array.isArray(preview.diff) ? preview.diff.length > 0 : Object.keys(preview.diff).length > 0;
  }

  function renderPreviewLoading(label) {
    if (!refs.previewPanel) return;
    refs.previewPanel.hidden = false;
    const actions = createElement('div', 'literature-map-preview-actions');
    const close = createElement('button', 'secondary-button', '关闭预览');
    close.type = 'button';
    close.addEventListener('click', () => closePreviewPanel());
    actions.append(close);
    refs.previewPanel.replaceChildren(
      createElement('h3', '', `${label}预览`),
      createElement('p', 'literature-map-preview-state', '正在读取候选与作业进度…'),
      actions,
    );
    renderJobActions();
  }

  function renderPreviewPanel() {
    if (!refs.previewPanel) return;
    if (!state.preview) {
      refs.previewPanel.hidden = true;
      refs.previewPanel.replaceChildren();
      return;
    }
    refs.previewPanel.hidden = false;
    refs.previewPanel.replaceChildren();
    const preview = state.preview;
    const panelTitle = createElement('h3', '', `${previewKindLabel(state.previewKind)}预览`);
    refs.previewPanel.append(panelTitle);
    const statusText = previewTerminal(preview)
      ? (preview.status === 'applied' ? '已提交确认，地图正在保存新增结果。' : `预览状态：${mapStatusLabel(preview.status)}`)
      : `预览状态：${mapStatusLabel(preview.status || state.previewJob?.status || 'running')}，候选仍在读取。`;
    refs.previewPanel.append(createElement('p', 'literature-map-preview-state', statusText));
    if (state.previewConflict) {
      const conflict = createElement('p', 'literature-map-preview-error', '地图版本已变化；未自动覆盖你的操作，请重新读取后再次预览。');
      conflict.setAttribute('role', 'alert');
      refs.previewPanel.append(conflict);
      const reread = createElement('button', 'secondary-button', '重新读取并预览');
      reread.type = 'button';
      reread.addEventListener('click', repreviewAfterConflict);
      refs.previewPanel.append(reread);
    }
    const warnings = Array.isArray(preview.warnings) ? preview.warnings : [];
    warnings.forEach((warning) => refs.previewPanel.append(createElement('p', 'literature-map-preview-warning', metadataText(warning))));
    if (previewHasDiff(preview)) {
      const diffTitle = createElement('p', 'literature-map-preview-diff-title', '字段变更');
      refs.previewPanel.append(diffTitle);
      const diffList = createElement('ul', 'literature-map-preview-diff');
      const entries = Array.isArray(preview.diff) ? preview.diff : Object.entries(preview.diff).map(([key, value]) => ({ field: key, value }));
      entries.slice(0, 50).forEach((entry) => diffList.append(createElement('li', '', formatPreviewDiffEntry(entry))));
      refs.previewPanel.append(diffList);
    } else if (state.previewKind === 'refresh' && previewReady(preview)) {
      refs.previewPanel.append(createElement('p', 'literature-map-preview-empty', '没有字段或关系差异；地图无需更新。'));
    }
    const candidates = previewCandidates();
    const nodeCount = normalizeNodes(state.graph).length;
    const available = Math.max(0, MAX_MAP_NODES - nodeCount);
    const selected = selectedPreviewIds();
    const capacity = createElement('p', 'literature-map-preview-capacity', `已选择 ${selected.length}/${MAX_PREVIEW_SELECTION}；地图容量 ${nodeCount}/${MAX_MAP_NODES}（还可加入 ${available}）`);
    refs.previewPanel.append(capacity);
    const list = createElement('div', 'literature-map-preview-candidates');
    list.setAttribute('role', 'list');
    candidates.forEach((candidate) => {
      const row = createElement('div', 'literature-map-preview-candidate');
      row.dataset.candidateId = candidate.candidate_id;
      const title = createElement('strong', 'literature-map-preview-candidate-title', metadataText(candidate.title, '标题未提供'));
      const meta = createElement('span', 'literature-map-preview-candidate-meta', `${metadataText(candidate.authors)} · ${metadataText(candidate.year)}`);
      row.append(title, meta);
      const alreadyPresent = Boolean(candidate.already_present || candidate.existing);
      const removed = Boolean(candidate.removed);
      if (alreadyPresent) {
        const checkbox = createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = candidate.candidate_id;
        checkbox.disabled = true;
        row.append(checkbox);
        row.append(createElement('span', 'literature-map-preview-candidate-state', '已在当前地图'));
      } else if (removed) {
        const checkbox = createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = candidate.candidate_id;
        checkbox.disabled = true;
        row.append(checkbox);
        row.append(createElement('span', 'literature-map-preview-candidate-state', '已移除墓碑 · 需显式恢复'));
        const restoreId = candidate.node_id || candidate.existing_node_id;
        if (restoreId) {
          const restore = createElement('button', 'secondary-button', '显式恢复');
          restore.type = 'button';
          restore.addEventListener('click', () => restoreNode(restoreId, restore));
          row.append(restore);
        }
      } else {
        const label = createElement('label', 'literature-map-preview-candidate-select');
        const checkbox = createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = candidate.candidate_id;
        checkbox.checked = state.previewSelection.has(candidate.candidate_id);
        checkbox.addEventListener('change', () => updatePreviewSelection(candidate.candidate_id, checkbox.checked));
        label.append(checkbox, createElement('span', '', '加入预览结果'));
        row.append(label);
      }
      list.append(row);
    });
    if (!candidates.length) list.append(createElement('p', 'literature-map-preview-empty', previewReady(preview) ? '没有新的可加入候选；已有节点和移除墓碑未混入新增。' : '等待服务端返回候选…'));
    refs.previewPanel.append(list);
    const actions = createElement('div', 'literature-map-preview-actions');
    const canApplyRefresh = state.previewKind === 'refresh' && previewHasDiff(preview);
    if (previewReady(preview) && preview.status !== 'applied' && (selected.length > 0 || canApplyRefresh)) {
      const apply = createElement('button', 'send-button', state.previewKind === 'refresh' ? '确认刷新' : '确认加入');
      apply.type = 'button';
      apply.id = 'literature-map-preview-apply';
      apply.disabled = (!canApplyRefresh && selected.length === 0) || selected.length > MAX_PREVIEW_SELECTION || selected.length > available;
      apply.addEventListener('click', () => applyPreview(apply));
      actions.append(apply);
    }
    const close = createElement('button', 'secondary-button', '关闭预览');
    close.type = 'button';
    close.addEventListener('click', () => closePreviewPanel());
    actions.append(close);
    refs.previewPanel.append(actions);
    renderJobActions();
  }

  function closePreviewPanel() {
    state.previewRequest += 1;
    state.preview = null;
    state.previewJob = null;
    state.previewId = null;
    state.previewKind = null;
    state.previewNodeId = null;
    state.previewSelection.clear();
    state.previewConflict = false;
    stopPreviewPolling();
    renderPreviewPanel();
    renderJobActions();
  }

  function updatePreviewSelection(candidateId, checked) {
    if (checked) {
      const available = Math.max(0, MAX_MAP_NODES - normalizeNodes(state.graph).length);
      if (state.previewSelection.size >= MAX_PREVIEW_SELECTION || state.previewSelection.size >= available) {
        setStatus(`本次最多加入 ${Math.min(MAX_PREVIEW_SELECTION, available)} 篇；请先取消其他选择。`, 'waiting');
        renderPreviewPanel();
        return;
      }
      state.previewSelection.add(candidateId);
    } else {
      state.previewSelection.delete(candidateId);
    }
    renderPreviewPanel();
  }

  async function openPreview(kind, nodeId = state.selectedNodeId) {
    if (!state.map?.map_id || !state.active) return;
    if (['references', 'citations'].includes(kind) && !nodeId) {
      setStatus(`请先选择论文，再打开“${previewKindLabel(kind)}”。`, 'waiting');
      return;
    }
    const mapId = state.map.map_id;
    const requestId = ++state.previewRequest;
    state.previewKind = kind;
    state.previewNodeId = nodeId || null;
    state.previewId = null;
    state.preview = null;
    state.previewJob = null;
    state.savedPreview = null;
    state.previewSelection.clear();
    state.previewConflict = false;
    stopPreviewPolling();
    renderPreviewLoading(previewKindLabel(kind));
    setStatus(`正在生成${previewKindLabel(kind)}…`, 'waiting');
    const body = { kind, idempotency_key: makeIdempotencyKey() };
    if (nodeId) body.node_id = nodeId;
    if (kind === 'topic') body.query = state.map.topic || '';
    try {
      const response = await request(`/${encodeURIComponent(mapId)}/previews`, { method: 'POST', body: JSON.stringify(body) });
      if (requestId !== state.previewRequest || mapId !== state.selectedMapId || !state.active) return;
      state.previewId = response.preview_id;
      state.previewJob = response.job || null;
      state.preview = { preview_id: response.preview_id, map_id: mapId, status: response.status || response.job?.status || 'queued', base_revision: response.base_revision ?? state.map.revision, candidates: [] };
      state.savedPreview = { preview_id: response.preview_id, map_id: mapId, kind, node_id: nodeId || null, job_id: response.job_id || response.job?.job_id || null };
      persistPreviewSession();
      renderPreviewPanel();
      await loadPreview(state.previewId, requestId);
      if (state.previewJob && !TERMINAL_JOB_STATES.has(state.previewJob.status)) schedulePreviewPoll(700);
    } catch (error) {
      if (requestId !== state.previewRequest || mapId !== state.selectedMapId || !state.active) return;
      state.preview = null;
      renderPreviewPanel();
      setStatus(`预览失败：${errorAction(error, '请稍后重试。')}`, 'error');
    }
  }

  async function loadPreview(previewId = state.previewId, requestId = state.previewRequest) {
    if (!previewId || !state.map?.map_id || !state.active) return;
    const mapId = state.map.map_id;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/previews/${encodeURIComponent(previewId)}`);
      if (requestId !== state.previewRequest || previewId !== state.previewId || mapId !== state.selectedMapId || !state.active) return;
      state.preview = payload.preview || state.preview;
      state.previewJob = payload.job || state.previewJob;
      state.previewKind = state.preview?.kind || state.previewKind || 'topic';
      state.savedPreview = {
        ...(state.savedPreview || {}),
        preview_id: previewId,
        map_id: mapId,
        kind: state.previewKind,
        job_id: state.previewJob?.job_id || state.savedPreview?.job_id || null,
        job: state.previewJob,
      };
      renderPreviewPanel();
      if (state.preview?.status === 'expired') clearPreviewSession(mapId);
    } catch (error) {
      if (requestId !== state.previewRequest || previewId !== state.previewId || mapId !== state.selectedMapId || !state.active) return;
      if (error.status === 410 || error.code === 'MAP_PREVIEW_EXPIRED') clearPreviewSession(mapId);
      setStatus(`预览读取失败：${errorAction(error, '请重新生成预览。')}`, 'error');
    }
  }

  async function pollPreview() {
    if (!state.active || !state.previewId || !state.map?.map_id) return;
    const generation = state.previewPollGeneration;
    const previewId = state.previewId;
    const requestId = state.previewRequest;
    await loadPreview(previewId, requestId);
    if (generation !== state.previewPollGeneration || requestId !== state.previewRequest || previewId !== state.previewId || !state.active) return;
    if (state.previewJob && !TERMINAL_JOB_STATES.has(state.previewJob.status) && !previewTerminal(state.preview)) schedulePreviewPoll(1600);
  }

  async function repreviewAfterConflict() {
    const mapId = state.selectedMapId;
    const kind = state.previewKind;
    const nodeId = state.previewNodeId;
    if (!mapId || !kind) return;
    clearPreviewSession(mapId);
    state.previewConflict = false;
    await selectMap(mapId);
    if (state.active && state.selectedMapId === mapId) await openPreview(kind, nodeId);
  }

  function isCurrentMapRequest(mapId, mapRequestId) {
    return Boolean(mapId && state.active && state.selectedMapId === mapId && state.map?.map_id === mapId && mapRequestId === state.mapRequest);
  }

  async function discoverPersistedPreview(mapId, mapRequestId) {
    if (!isCurrentMapRequest(mapId, mapRequestId)) return null;
    state.previewDiscoveryNotice = '';
    let cursor = 0;
    let pageCount = 0;
    let reachedEmptyPage = false;
    const previewEvents = [];
    try {
      while (pageCount < MAX_PREVIEW_DISCOVERY_PAGES) {
        const eventsPayload = await request(`/${encodeURIComponent(mapId)}/events?after_seq=${encodeURIComponent(cursor)}`);
        if (!isCurrentMapRequest(mapId, mapRequestId)) return null;
        pageCount += 1;
        const events = Array.isArray(eventsPayload.events) ? eventsPayload.events : [];
        if (!events.length) {
          reachedEmptyPage = true;
          break;
        }
        previewEvents.push(...events.filter((event) => String(event?.type || '').startsWith('preview_') && event?.job_id));
        const nextCursor = Number(eventsPayload.next_cursor);
        if (!Number.isSafeInteger(nextCursor) || nextCursor <= cursor) {
          state.previewDiscoveryNotice = '上次预览事件读取中断：服务端游标未前进，请重新打开地图重试。';
          break;
        }
        state.eventCursor = Math.max(state.eventCursor, nextCursor);
        cursor = nextCursor;
      }
      if (!reachedEmptyPage && pageCount >= MAX_PREVIEW_DISCOVERY_PAGES && state.previewDiscoveryNotice === '') {
        state.previewDiscoveryNotice = '上次预览事件较多，尚未读完；请重新打开地图继续读取。';
      }
      for (const event of previewEvents.reverse()) {
        try {
          const jobPayload = await request(`/${encodeURIComponent(mapId)}/jobs/${encodeURIComponent(event.job_id)}`);
          if (!isCurrentMapRequest(mapId, mapRequestId)) return null;
          const job = jobPayload?.job;
          const previewId = job?.cursor?.preview_id;
          if (!previewId) continue;
          return {
            preview_id: String(previewId),
            map_id: mapId,
            job_id: job.job_id || event.job_id,
            kind: null,
            node_id: null,
            job,
            event_type: event.type,
          };
        } catch (_) {
          // A stale preview job must not hide an older persisted preview.
        }
      }
    } catch (_) {
      if (isCurrentMapRequest(mapId, mapRequestId)) state.previewDiscoveryNotice = '上次预览记录暂时无法读取，请重新打开地图重试。';
    }
    return null;
  }

  async function restorePreviewForMap(mapId, mapRequestId = state.mapRequest) {
    if (!mapId || !state.active || state.preview || !isCurrentMapRequest(mapId, mapRequestId)) return;
    if (!state.previewId) {
      let saved = null;
      try { saved = JSON.parse(window.sessionStorage.getItem(previewStorageKey(mapId)) || 'null'); } catch (_) { saved = null; }
      if (saved?.preview_id) {
        state.previewId = saved.preview_id;
        state.previewKind = saved.kind || 'topic';
        state.previewNodeId = saved.node_id || null;
        state.savedPreview = { ...saved, map_id: mapId };
      }
    }
    if (!state.previewId) {
      state.savedPreview = await discoverPersistedPreview(mapId, mapRequestId);
      renderJobActions();
      return;
    }
    const previewRequest = ++state.previewRequest;
    state.previewSelection.clear();
    state.previewConflict = false;
    await loadPreview(state.previewId, previewRequest);
    if (!isCurrentMapRequest(mapId, mapRequestId)) return;
    if (!state.preview) {
      state.previewId = null;
      state.previewKind = null;
      state.previewNodeId = null;
      state.savedPreview = await discoverPersistedPreview(mapId, mapRequestId);
      renderJobActions();
      return;
    }
    if (state.previewJob && !TERMINAL_JOB_STATES.has(state.previewJob.status) && !previewTerminal(state.preview)) schedulePreviewPoll(700);
  }

  async function openSavedPreview() {
    const saved = state.savedPreview;
    const mapId = state.map?.map_id;
    if (!saved?.preview_id || !mapId || saved.map_id !== mapId || !state.active) return;
    const requestId = ++state.previewRequest;
    state.previewId = saved.preview_id;
    state.previewKind = saved.kind || 'topic';
    state.previewNodeId = saved.node_id || null;
    state.preview = null;
    state.previewJob = saved.job || null;
    state.previewSelection.clear();
    state.previewConflict = false;
    stopPreviewPolling();
    renderPreviewLoading('上次');
    setStatus('正在读取上次预览…', 'waiting');
    await loadPreview(saved.preview_id, requestId);
    if (requestId !== state.previewRequest || !state.active || state.selectedMapId !== mapId || state.map?.map_id !== mapId) return;
    if (state.previewJob && !TERMINAL_JOB_STATES.has(state.previewJob.status) && !previewTerminal(state.preview)) schedulePreviewPoll(700);
  }

  async function applyPreview(button) {
    const selected = selectedPreviewIds();
    const canApplyRefresh = state.previewKind === 'refresh' && previewHasDiff(state.preview);
    if (!state.map?.map_id || !state.previewId || (!selected.length && !canApplyRefresh)) return;
    const mapId = state.map.map_id;
    const previewId = state.previewId;
    const requestId = ++state.previewRequest;
    button.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/previews/${encodeURIComponent(previewId)}/apply`, {
        method: 'POST',
        body: JSON.stringify({ expected_revision: state.map.revision, selected_candidate_ids: selected, idempotency_key: makeIdempotencyKey() }),
      });
      if (requestId !== state.previewRequest || mapId !== state.selectedMapId || !state.active) return;
      state.map = normalizeMap(payload.map) || state.map;
      state.job = payload.job || state.job;
      state.previewJob = payload.job || state.previewJob;
      state.preview = { ...state.preview, status: 'applied', selected_candidate_ids: selected };
      state.previewSelection.clear();
      setStatus('已确认加入，新增节点正在保存；原有布局不会被重排。', 'waiting');
      renderPreviewPanel();
      await loadMaps();
      await loadMapGraph(mapId);
      if (state.job && !TERMINAL_JOB_STATES.has(state.job.status)) startPolling();
    } catch (error) {
      if (requestId !== state.previewRequest || mapId !== state.selectedMapId || !state.active) return;
      button.disabled = false;
      if (error.status === 409) {
        state.previewConflict = true;
        renderPreviewPanel();
        setStatus('地图版本已变化；未自动覆盖你的操作，请重新读取后再次预览。', 'error');
      } else {
        setStatus(`确认加入失败：${errorAction(error, '请重新读取预览后重试。')}`, 'error');
      }
    }
  }

  async function runJobAction(action) {
    const job = activeJob();
    if (!state.map?.map_id || !job?.job_id) return;
    const mapId = state.map.map_id;
    const requestId = ++state.jobActionRequest;
    const button = action === 'stop' ? refs.stopJobButton : refs.retryJobButton;
    if (button) button.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/jobs/${encodeURIComponent(job.job_id)}/${action}`, { method: 'POST', body: JSON.stringify({ idempotency_key: makeIdempotencyKey() }) });
      if (requestId !== state.jobActionRequest || mapId !== state.selectedMapId || !state.active) return;
      if (state.previewJob?.job_id === job.job_id) state.previewJob = payload.job || state.previewJob;
      state.job = payload.job || state.job;
      if (action === 'stop') {
        stopPolling();
        stopPreviewPolling();
        setStatus('任务已停止；已保留停止前的成果，未完成单元不会自动复活。', 'waiting');
      } else {
        setStatus('已提交可重试失败单元；成功单元不会重复抓取。', 'waiting');
        startPolling();
      }
      renderCurrentMeta();
      renderJobActions();
    } catch (error) {
      if (requestId !== state.jobActionRequest || mapId !== state.selectedMapId || !state.active) return;
      if (button) button.disabled = false;
      setStatus(`${action === 'stop' ? '停止' : '重试'}任务失败：${errorAction(error, '请刷新地图状态后重试。')}`, 'error');
    }
  }

  function stopCurrentJob() { return runJobAction('stop'); }

  function retryCurrentJob() {
    if (!hasRetryableUnits(activeJob())) {
      setStatus('当前任务没有可重试失败单元；已完成结果不会重复抓取。', 'waiting');
      return Promise.resolve();
    }
    return runJobAction('retry');
  }

  function stageLabel(step) {
    const labels = { discover: '寻找论文', metadata: '补充元数据与引用', references: '补充引用', similarity: '计算主题相似关系', finished: '地图可用' };
    return labels[step] || step;
  }

  function initialPosition(index, total) {
    const ring = Math.max(1, Math.ceil(Math.sqrt(total / 2)));
    const layer = Math.floor(index / (ring * 2));
    const slot = index % (ring * 2);
    const radius = Math.min(285, 70 + layer * 58);
    const angle = (slot / Math.max(1, ring * 2)) * Math.PI * 2 + (layer % 2 ? 0.25 : 0);
    return { x: MAP_WIDTH / 2 + Math.cos(angle) * radius, y: MAP_HEIGHT / 2 + Math.sin(angle) * radius * 0.78 };
  }

  function nodeRadiusForLayout(node) {
    const radius = citationRadius(node);
    return Number.isFinite(radius) ? radius : MIN_NODE_RADIUS;
  }

  function requiredCenterDistance(first, second) {
    const firstRadius = nodeRadiusForLayout(first);
    const secondRadius = nodeRadiusForLayout(second);
    return firstRadius + secondRadius
      + LAYOUT_CLEARANCE_MULTIPLIER * Math.max(firstRadius, secondRadius)
      + LAYOUT_STROKE_CLEARANCE;
  }

  function countSpacingViolations(nodes = activeNodes()) {
    const positioned = nodes
      .map((node, index) => ({ node, point: positionFor(node, index, nodes.length) }))
      .filter(({ point }) => point && Number.isFinite(point.x) && Number.isFinite(point.y));
    let violations = 0;
    for (let firstIndex = 0; firstIndex < positioned.length; firstIndex += 1) {
      for (let secondIndex = firstIndex + 1; secondIndex < positioned.length; secondIndex += 1) {
        const first = positioned[firstIndex];
        const second = positioned[secondIndex];
        const distance = Math.hypot(first.point.x - second.point.x, first.point.y - second.point.y);
        if (distance < requiredCenterDistance(first.node, second.node) - 0.001) violations += 1;
      }
    }
    return violations;
  }

  function layoutCandidate(index, columns, step, origin) {
    const row = Math.floor(index / columns);
    const column = index % columns;
    return {
      x: origin.x + (column - (columns - 1) / 2) * step,
      y: origin.y + (row - (Math.ceil(columns / 2) - 1) / 2) * step,
    };
  }

  function layoutPendingNodes(pendingNodes, existingPositions = {}, existingNodes = []) {
    const ordered = [...pendingNodes].sort((first, second) => String(first.node_id).localeCompare(String(second.node_id)));
    const placed = existingNodes
      .map((node) => ({ node, point: existingPositions[node.node_id] }))
      .filter((entry) => entry.point && Number.isFinite(entry.point.x) && Number.isFinite(entry.point.y));
    const result = Object.create(null);
    if (!ordered.length) return result;
    const largestRadius = Math.max(...ordered.map(nodeRadiusForLayout), ...placed.map((entry) => nodeRadiusForLayout(entry.node)), MAX_NODE_RADIUS);
    const step = 2 * largestRadius + LAYOUT_CLEARANCE_MULTIPLIER * largestRadius + LAYOUT_STROKE_CLEARANCE;
    const origin = placed.length
      ? {
        x: placed.reduce((sum, entry) => sum + entry.point.x, 0) / placed.length,
        y: placed.reduce((sum, entry) => sum + entry.point.y, 0) / placed.length,
      }
      : { x: MAP_WIDTH / 2, y: MAP_HEIGHT / 2 };
    const columns = Math.max(1, Math.ceil(Math.sqrt(ordered.length)));
    const occupied = [...placed];
    ordered.forEach((node, nodeIndex) => {
      let point = null;
      for (let attempt = 0; attempt < MAX_LAYOUT_PLACEMENT_ATTEMPTS; attempt += 1) {
        // Expanding square rings keep the search finite and deterministic while
        // still placing new nodes near the existing map when possible.
        const ring = Math.floor(Math.sqrt(attempt));
        const offset = attempt - ring * ring;
        const side = Math.max(1, ring * 2 + 1);
        const sideIndex = offset % Math.max(1, side * 4);
        let dx = 0;
        let dy = 0;
        if (ring > 0) {
          if (sideIndex < side) { dx = sideIndex - ring; dy = -ring; }
          else if (sideIndex < side * 2) { dx = ring; dy = sideIndex - ring - side; }
          else if (sideIndex < side * 3) { dx = ring - (sideIndex - side * 2); dy = ring; }
          else { dx = -ring; dy = ring - (sideIndex - side * 3); }
        }
        const candidate = {
          x: origin.x + dx * step + (nodeIndex % 2 ? step * 0.25 : 0),
          y: origin.y + dy * step + (nodeIndex % 3 ? step * 0.12 : 0),
        };
        const clear = occupied.every((entry) => {
          const other = entry.node;
          const required = requiredCenterDistance(node, other);
          return Math.hypot(candidate.x - entry.point.x, candidate.y - entry.point.y) + 1e-6 >= required;
        });
        if (clear) { point = candidate; break; }
      }
      // The deterministic grid is an explicit finite fallback. It is far
      // outside the initial canvas when necessary, so dense maps remain
      // navigable through the existing pan/zoom controls.
      if (!point) point = layoutCandidate(nodeIndex + occupied.length, columns, step, origin);
      result[node.node_id] = point;
      occupied.push({ node, point });
    });
    return result;
  }

  function scheduleLayout() {
    if (state.layoutScheduled || !state.graph || !normalizeNodes(state.graph).length || !state.layoutPendingIds.size) return;
    state.layoutScheduled = true;
    state.layoutFrames = 0;
    const frame = () => {
      state.layoutFrames += 1;
      const nodes = normalizeNodes(state.graph);
      const pending = nodes.filter((node) => state.layoutPendingIds.has(node.node_id) && !node.removed && !node.tombstone);
      const generated = layoutPendingNodes(pending, state.positions, nodes.filter((node) => !state.layoutPendingIds.has(node.node_id) && !node.removed && !node.tombstone));
      Object.assign(state.positions, generated);
      state.layoutPendingIds.clear();
      renderGraph();
      if (state.active && state.layoutFrames < MAX_LAYOUT_FRAMES) {
        window.requestAnimationFrame(frame);
      } else {
        state.layoutScheduled = false;
        state.positionsDirty = true;
        scheduleViewSave();
      }
    };
    window.requestAnimationFrame(frame);
  }

  function clonePositions(positions) {
    return Object.fromEntries(Object.entries(positions || {}).map(([nodeId, point]) => [nodeId, { x: Number(point.x), y: Number(point.y) }]));
  }

  function renderSpacingPreviewPanel(message = '') {
    if (!refs.spacingPreviewPanel) return;
    refs.spacingPreviewPanel.replaceChildren();
    refs.spacingPreviewPanel.hidden = !state.layoutPreviewActive;
    if (!state.layoutPreviewActive) return;
    refs.spacingPreviewPanel.append(createElement('h3', '', '整理间距预览'));
    const stateText = createElement('p', 'literature-map-spacing-preview-state', message || '仅在本地预览，尚未保存地图。筛选隐藏的论文也会保留位置。');
    stateText.id = 'literature-map-spacing-preview-state';
    refs.spacingPreviewPanel.append(stateText);
    const actions = createElement('div', 'literature-map-spacing-preview-actions');
    const confirm = createElement('button', 'send-button', '确认保存');
    confirm.type = 'button';
    confirm.id = 'literature-map-spacing-preview-confirm';
    confirm.addEventListener('click', () => confirmSpacingPreview(confirm));
    const cancel = createElement('button', 'secondary-button', '取消');
    cancel.type = 'button';
    cancel.id = 'literature-map-spacing-preview-cancel';
    cancel.addEventListener('click', cancelSpacingPreview);
    actions.append(confirm, cancel);
    refs.spacingPreviewPanel.append(actions);
  }

  function beginSpacingPreview() {
    if (!state.graph || !state.map?.map_id || state.layoutPreviewActive) return;
    const nodes = activeNodes();
    if (!nodes.length) {
      setStatus('当前地图没有可整理的活动节点。', 'waiting');
      return;
    }
    window.clearTimeout(state.saveTimer);
    state.saveTimer = null;
    state.layoutPreview = {
      positions: clonePositions(state.positions),
      view: { ...state.view },
      positionsDirty: state.positionsDirty,
      viewDirty: state.viewDirty,
    };
    state.positions = Object.assign(Object.create(null), state.positions, layoutPendingNodes(nodes, state.positions, []));
    state.positionsDirty = false;
    state.viewDirty = false;
    state.layoutPreviewActive = true;
    renderGraph();
    renderSpacingPreviewPanel();
    setStatus('已生成整理间距预览；确认前不会写入地图。', 'waiting');
  }

  function cancelSpacingPreview() {
    if (!state.layoutPreviewActive || !state.layoutPreview) return;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = null;
    const snapshot = state.layoutPreview;
    state.positions = Object.assign(Object.create(null), snapshot.positions);
    state.view = { ...snapshot.view };
    state.positionsDirty = snapshot.positionsDirty;
    state.viewDirty = snapshot.viewDirty;
    state.layoutPreview = null;
    state.layoutPreviewActive = false;
    renderSpacingPreviewPanel();
    renderGraph();
    setStatus('已取消整理间距，位置和视图已还原。');
  }

  async function confirmSpacingPreview(button) {
    if (!state.layoutPreviewActive || !state.layoutPreview || button?.disabled) return;
    const mapId = state.map?.map_id;
    const snapshot = state.layoutPreview;
    if (!mapId || !state.active) return;
    if (button) button.disabled = true;
    state.layoutPreviewActive = false;
    state.positionsDirty = true;
    state.viewDirty = false;
    const saved = await saveView({ allowLayoutPreview: true });
    if (saved) {
      state.layoutPreview = null;
      renderSpacingPreviewPanel();
      setStatus('整理间距已保存。');
      return;
    }
    if (mapId !== state.selectedMapId || !state.active) return;
    // Preserve the uncommitted preview after a transport or 409 failure. The
    // retry remains explicit; no autosave may turn a failed confirmation into
    // an unreported write.
    state.layoutPreview = snapshot;
    state.layoutPreviewActive = true;
    state.positionsDirty = false;
    state.viewDirty = false;
    renderSpacingPreviewPanel('保存失败；预览仍保留，可重试确认或取消还原。');
    if (button) button.disabled = false;
  }

  function positionFor(node, index, total) {
    return state.positions[node.node_id] || (node.position ? { x: Number(node.position.x), y: Number(node.position.y) } : initialPosition(index, total));
  }

  function renderGraph() {
    if (!refs.svg) return;
    renderMultiSelectControls();
    const nodes = normalizeNodes(state.graph);
    const edges = normalizeEdges(state.graph);
    refs.viewport.setAttribute('transform', `translate(${state.view.x} ${state.view.y}) scale(${state.view.scale})`);
    refs.edgesGroup.replaceChildren();
    refs.nodesGroup.replaceChildren();
    setHidden(refs.canvasEmpty, Boolean(state.graph && nodes.length));
    if (!state.graph) {
      refs.canvasEmpty.textContent = '选择左侧地图后查看图谱。';
      refs.currentTitle.textContent = '选择一张地图';
      refs.currentMeta.textContent = '图谱会在后台分阶段生成。';
      return;
    }
    if (!nodes.length) {
      refs.canvasEmpty.textContent = state.job && !TERMINAL_JOB_STATES.has(state.job.status) ? '正在等待首批论文；此处会显示真实节点。' : '当前地图暂无节点。';
      return;
    }
    const positions = Object.create(null);
    nodes.forEach((node, index) => { positions[node.node_id] = positionFor(node, index, nodes.length); });
    const labelIds = labelIdsForGraph(nodes, edges);
    const occupiedLabels = [];
    edges.forEach((edge) => {
      if (!state.layers[edge.kind] || !positions[edge.source_id] || !positions[edge.target_id]) return;
      const line = createSvgElement('line');
      const source = positions[edge.source_id];
      const target = positions[edge.target_id];
      setAttributes(line, { x1: source.x, y1: source.y, x2: target.x, y2: target.y, 'data-edge-id': edge.edge_id || '', 'data-edge-kind': edge.kind || '', class: `literature-map-edge ${edge.kind || ''}` });
      if (edge.kind === 'citation') line.setAttribute('marker-end', 'url(#literature-map-arrow)');
      refs.edgesGroup.append(line);
    });
    nodes.forEach((node, index) => {
      const point = positions[node.node_id];
      const group = createSvgElement('g');
      const selected = node.node_id === state.selectedNodeId || state.multiSelectedNodeIds.has(node.node_id);
      const mapGroup = groupById(node.group_id);
      const provenance = typeof node.provenance === 'string' ? node.provenance : node.provenance?.basis || '';
      const fullTitle = String(node.title || node.node_id || '未命名论文');
      setAttributes(group, { class: `literature-map-node${selected ? ' is-selected' : ''}${mapGroup ? ' is-grouped' : ''}`, 'data-node-id': node.node_id, 'data-group-id': mapGroup?.group_id || '', 'data-group-color': mapGroup?.color || '', 'data-provenance': provenance, 'data-citation-known': citationCount(node.citation_count) === null ? 'false' : 'true', tabindex: '0', role: 'button', 'aria-label': nodeAccessibleLabel(node), title: fullTitle });
      const svgTitle = createSvgElement('title');
      svgTitle.textContent = `${fullTitle} · 引用数${citationCountLabel(node)}`;
      group.append(svgTitle);
      const circle = createSvgElement('circle');
      const radius = citationRadius(node);
      const color = nodeDisplayColor(node);
      const outlineOnly = state.nodeStyleDraft.fill_mode === 'outline';
      setAttributes(circle, { cx: point.x, cy: point.y, r: radius, fill: outlineOnly ? 'none' : color, 'fill-opacity': outlineOnly ? 0 : state.nodeStyleDraft.fill_opacity, stroke: color, 'stroke-opacity': 1, 'stroke-width': selected ? 3 : (mapGroup ? 2.5 : 2), 'data-node-color': color, 'data-color-override': node.color_override || '', 'data-citation-count': citationCountLabel(node), 'data-group-color': mapGroup?.color || '' });
      circle.style.fill = outlineOnly ? 'none' : color;
      circle.style.fillOpacity = String(outlineOnly ? 0 : state.nodeStyleDraft.fill_opacity);
      circle.style.stroke = color;
      circle.style.strokeOpacity = '1';
      group.append(circle);
      if (labelIds.has(node.node_id)) {
        const label = createSvgElement('text');
        const labelText = nodeDisplayLabel(node);
        const labelFontSize = labelFontSizeSvgUnits();
        const labelPoint = labelPosition(point, radius, labelText, occupiedLabels, labelFontSize);
        setAttributes(label, { x: labelPoint.x, y: labelPoint.y, class: 'literature-map-node-label' });
        label.style.fontSize = `${labelFontSize}px`;
        label.textContent = labelText;
        group.append(label);
      }
      refs.nodesGroup.append(group);
    });
    renderCurrentMeta();
  }

  function ensureSelectedNodeVisible() {
    if (!state.selectedNodeId || !refs.svg || !refs.detailPanel?.classList.contains('is-open')) return false;
    const svgRect = refs.svg.getBoundingClientRect();
    if (!svgRect.width || !svgRect.height) return false;
    const selected = refs.nodesGroup.querySelector(`[data-node-id="${CSS.escape(state.selectedNodeId)}"] circle`);
    if (!selected) return false;
    const nodeRect = selected.getBoundingClientRect();
    const canvasRect = refs.svg.closest('.literature-map-canvas')?.getBoundingClientRect() || svgRect;
    const visible = {
      left: Math.max(svgRect.left, canvasRect.left, 0),
      right: Math.min(svgRect.right, canvasRect.right, window.innerWidth),
      top: Math.max(svgRect.top, canvasRect.top, 0),
      bottom: Math.min(svgRect.bottom, canvasRect.bottom, window.innerHeight),
    };
    const detailRect = refs.detailPanel.getBoundingClientRect();
    const detailOverlaysCanvas = isMobileViewport()
      && window.getComputedStyle(refs.detailPanel).position === 'fixed'
      && detailRect.width > 0
      && detailRect.height > 0
      && detailRect.left < visible.right
      && detailRect.right > visible.left
      && detailRect.top < visible.bottom
      && detailRect.bottom > visible.top;
    if (detailOverlaysCanvas) {
      const candidates = [
        { left: visible.left, right: visible.right, top: visible.top, bottom: Math.min(visible.bottom, detailRect.top) },
        { left: visible.left, right: visible.right, top: Math.max(visible.top, detailRect.bottom), bottom: visible.bottom },
        { left: visible.left, right: Math.min(visible.right, detailRect.left), top: visible.top, bottom: visible.bottom },
        { left: Math.max(visible.left, detailRect.right), right: visible.right, top: visible.top, bottom: visible.bottom },
      ].filter((area) => area.right > area.left && area.bottom > area.top);
      const largest = candidates.sort((first, second) =>
        ((second.right - second.left) * (second.bottom - second.top))
          - ((first.right - first.left) * (first.bottom - first.top)))[0];
      if (!largest) return false;
      Object.assign(visible, largest);
    }
    const availableWidth = visible.right - visible.left;
    const availableHeight = visible.bottom - visible.top;
    if (availableWidth <= 0 || availableHeight <= 0) return false;
    const horizontalInset = Math.min(16, Math.max(0, (availableWidth - nodeRect.width) / 2));
    const verticalInset = Math.min(16, Math.max(0, (availableHeight - nodeRect.height) / 2));
    visible.left += horizontalInset;
    visible.right -= horizontalInset;
    visible.top += verticalInset;
    visible.bottom -= verticalInset;
    const minimumPan = (start, end, targetStart, targetEnd) => {
      const range = end - start;
      const targetSize = targetEnd - targetStart;
      if (targetSize > range) return ((start + end) - (targetStart + targetEnd)) / 2;
      if (targetStart < start) return start - targetStart;
      if (targetEnd > end) return end - targetEnd;
      return 0;
    };
    const dx = minimumPan(visible.left, visible.right, nodeRect.left, nodeRect.right);
    const dy = minimumPan(visible.top, visible.bottom, nodeRect.top, nodeRect.bottom);
    if (!Number.isFinite(dx) || !Number.isFinite(dy) || (!dx && !dy)) return false;
    const viewport = mapViewportWorldSize();
    if (!viewport.valid) return false;
    state.view.x += dx / viewport.cssScale;
    state.view.y += dy / viewport.cssScale;
    state.viewDirty = true;
    renderGraph();
    scheduleViewSave();
    return true;
  }

  function eventPoint(event) {
    return { pointerId: event.pointerId, pointerType: event.pointerType, x: event.clientX, y: event.clientY };
  }

  function safeCapturePointer(pointerId) {
    try { refs.svg.setPointerCapture?.(pointerId); } catch (_) { /* cancelled pointers may not be capturable */ }
  }

  function safeReleasePointer(pointerId) {
    try {
      if (refs.svg.hasPointerCapture?.(pointerId)) refs.svg.releasePointerCapture(pointerId);
    } catch (_) { /* pointer capture may already be gone after a cancel */ }
  }

  function svgPointFromClient(point) {
    if (refs.svg?.createSVGPoint && typeof refs.svg.getScreenCTM === 'function') {
      try {
        const matrix = refs.svg.getScreenCTM();
        if (matrix && typeof matrix.inverse === 'function') {
          const screenPoint = refs.svg.createSVGPoint();
          screenPoint.x = Number(point?.x) || 0;
          screenPoint.y = Number(point?.y) || 0;
          const local = screenPoint.matrixTransform(matrix.inverse());
          if (Number.isFinite(local.x) && Number.isFinite(local.y)) return { x: local.x, y: local.y };
        }
      } catch (_) {
        // Hidden SVGs and cancelled gestures can briefly lack a screen matrix.
      }
    }
    const rect = refs.svg.getBoundingClientRect();
    const scale = Math.min(rect.width / MAP_WIDTH, rect.height / MAP_HEIGHT);
    if (!Number.isFinite(scale) || scale <= 0) return { x: MAP_WIDTH / 2, y: MAP_HEIGHT / 2 };
    const offsetX = (rect.width - MAP_WIDTH * scale) / 2;
    const offsetY = (rect.height - MAP_HEIGHT * scale) / 2;
    return { x: (point.x - rect.left - offsetX) / scale, y: (point.y - rect.top - offsetY) / scale };
  }

  function canvasCenterClient() {
    const rect = refs.svg?.getBoundingClientRect?.();
    if (!rect) return { x: 0, y: 0 };
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  }

  function pinchSnapshot() {
    const points = [...state.pointers.values()];
    if (points.length < 2) return null;
    const [first, second] = points;
    const dx = second.x - first.x;
    const dy = second.y - first.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    return {
      center: { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 },
      distance,
    };
  }

  function startPinch() {
    const snapshot = pinchSnapshot();
    if (!snapshot) return;
    const center = svgPointFromClient(snapshot.center);
    state.pinch = {
      initialDistance: snapshot.distance,
      initialScale: state.view.scale,
      initialView: { ...state.view },
      worldCenter: {
        x: (center.x - state.view.x) / state.view.scale,
        y: (center.y - state.view.y) / state.view.scale,
      },
    };
    state.pointer = null;
    state.suppressTap = true;
  }

  function updatePinch() {
    const pinch = state.pinch;
    const snapshot = pinchSnapshot();
    if (!pinch || !snapshot) return;
    const center = svgPointFromClient(snapshot.center);
    const scale = Math.max(MIN_MAP_SCALE, Math.min(MAX_MAP_SCALE, pinch.initialScale * snapshot.distance / pinch.initialDistance));
    state.view.scale = scale;
    state.view.x = center.x - pinch.worldCenter.x * scale;
    state.view.y = center.y - pinch.worldCenter.y * scale;
    state.viewDirty = true;
    renderGraph();
  }

  function resetCanvasGesture(suppressTap = false) {
    state.pointers.forEach((point) => safeReleasePointer(point.pointerId));
    state.pointers.clear();
    state.pointer = null;
    state.pinch = null;
    if (suppressTap) state.suppressTap = true;
  }

  function handleCanvasPointerDown(event) {
    if (event.pointerType === 'touch' && !state.graph) return;
    if (!state.pointers.size && !state.pinch) state.suppressTap = false;
    const nodeGroup = event.target.closest ? event.target.closest('[data-node-id]') : null;
    state.pointers.set(event.pointerId, eventPoint(event));
    safeCapturePointer(event.pointerId);
    if (event.pointerType === 'touch' && state.pointers.size >= 2) {
      startPinch();
      return;
    }
    state.pointer = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, nodeId: nodeGroup?.dataset.nodeId || null, dragged: false };
  }

  function handleCanvasPointerMove(event) {
    const point = state.pointers.get(event.pointerId);
    if (point) {
      point.x = event.clientX;
      point.y = event.clientY;
    }
    if (state.pinch) {
      updatePinch();
      return;
    }
    const pointer = state.pointer;
    if (!pointer || pointer.pointerId !== event.pointerId) return;
    const dx = event.clientX - pointer.lastX;
    const dy = event.clientY - pointer.lastY;
    if (Math.abs(event.clientX - pointer.startX) + Math.abs(event.clientY - pointer.startY) > 3) pointer.dragged = true;
    pointer.lastX = event.clientX;
    pointer.lastY = event.clientY;
    const dragNode = pointer.nodeId && !(isMobileViewport() && event.pointerType === 'touch');
    if (dragNode) {
      const nodes = normalizeNodes(state.graph);
      const nodeIndex = nodes.findIndex((node) => node.node_id === pointer.nodeId);
      const current = state.positions[pointer.nodeId] || (nodeIndex >= 0 ? positionFor(nodes[nodeIndex], nodeIndex, nodes.length) : null);
      if (!current) return;
      state.positions[pointer.nodeId] = { x: current.x + dx / state.view.scale, y: current.y + dy / state.view.scale };
      state.positionsDirty = true;
    } else {
      state.view.x += dx;
      state.view.y += dy;
      state.viewDirty = true;
    }
    renderGraph();
  }

  function handleCanvasPointerUp(event) {
    if (state.pointers.has(event.pointerId)) state.pointers.delete(event.pointerId);
    safeReleasePointer(event.pointerId);
    if (state.pinch) {
      // The first pointerup ends a pinch even when its partner is still down.
      // Save the latest transform exactly once; leave no single-pointer drag
      // baseline behind, so a two-to-one transition cannot jump the viewport.
      const pinchEnded = state.pointers.size < 2;
      if (pinchEnded) {
        state.pinch = null;
        state.pointer = null;
        state.suppressTap = true;
        scheduleViewSave();
      }
      state.pointer = null;
      return;
    }
    if (!state.pointer || state.pointer.pointerId !== event.pointerId) return;
    const dragged = state.pointer.dragged;
    const nodeId = state.pointer.nodeId;
    state.pointer = null;
    if (dragged) {
      state.suppressTap = true;
      scheduleViewSave();
    }
    if (!dragged && nodeId && state.multiSelectActive) {
      toggleMultiSelectNode(nodeId);
      state.suppressTap = true;
    } else if (!dragged && nodeId && event.pointerType !== 'touch') {
      const nodeGroup = refs.nodesGroup.querySelector(`[data-node-id="${CSS.escape(nodeId)}"]`);
      try { nodeGroup?.focus({ preventScroll: true }); } catch (_) { nodeGroup?.focus(); }
      selectNode(nodeId, nodeGroup);
    }
  }

  function handleCanvasPointerCancel(event) {
    if (state.pointers.has(event.pointerId)) state.pointers.delete(event.pointerId);
    safeReleasePointer(event.pointerId);
    resetCanvasGesture(true);
  }

  function handleWheel(event) {
    if (!state.graph) return;
    event.preventDefault();
    changeScale(event.deltaY > 0 ? 1 / 1.1 : 1.1, { x: event.clientX, y: event.clientY });
  }

  function changeScale(factor, clientPoint = null) {
    const nextScale = Math.max(MIN_MAP_SCALE, Math.min(MAX_MAP_SCALE, state.view.scale * factor));
    if (!Number.isFinite(nextScale) || nextScale === state.view.scale) return;
    const anchorClient = clientPoint && Number.isFinite(Number(clientPoint.x)) && Number.isFinite(Number(clientPoint.y))
      ? clientPoint
      : canvasCenterClient();
    const anchorSvg = svgPointFromClient(anchorClient);
    const world = {
      x: (anchorSvg.x - state.view.x) / state.view.scale,
      y: (anchorSvg.y - state.view.y) / state.view.scale,
    };
    state.view.scale = nextScale;
    state.view.x = anchorSvg.x - world.x * nextScale;
    state.view.y = anchorSvg.y - world.y * nextScale;
    state.viewDirty = true;
    renderGraph();
    scheduleViewSave();
  }

  function mapViewportWorldSize() {
    const rect = refs.svg?.getBoundingClientRect?.();
    const viewBox = refs.svg?.viewBox?.baseVal;
    const viewBoxX = Number(viewBox?.x) || 0;
    const viewBoxY = Number(viewBox?.y) || 0;
    const viewBoxWidth = Number(viewBox?.width) || MAP_WIDTH;
    const viewBoxHeight = Number(viewBox?.height) || MAP_HEIGHT;
    if (!rect || !Number.isFinite(rect.width) || !Number.isFinite(rect.height) || rect.width <= 0 || rect.height <= 0) {
      return { x: viewBoxX, y: viewBoxY, width: viewBoxWidth, height: viewBoxHeight, cssScale: 1, valid: false };
    }
    const cssScale = Math.min(rect.width / viewBoxWidth, rect.height / viewBoxHeight);
    if (!Number.isFinite(cssScale) || cssScale <= 0) {
      return { x: viewBoxX, y: viewBoxY, width: viewBoxWidth, height: viewBoxHeight, cssScale: 1, valid: false };
    }
    return { x: viewBoxX, y: viewBoxY, width: viewBoxWidth, height: viewBoxHeight, cssScale, valid: true };
  }

  function elementBounds(element) {
    if (!element || typeof element.getBBox !== 'function') return null;
    try {
      const box = element.getBBox();
      if (![box.x, box.y, box.width, box.height].every(Number.isFinite) || box.width < 0 || box.height < 0) return null;
      return { left: box.x, right: box.x + box.width, top: box.y, bottom: box.y + box.height };
    } catch (_) {
      return null;
    }
  }

  function unionBounds(...bounds) {
    const available = bounds.filter(Boolean);
    if (!available.length) return null;
    return {
      left: Math.min(...available.map((bound) => bound.left)),
      right: Math.max(...available.map((bound) => bound.right)),
      top: Math.min(...available.map((bound) => bound.top)),
      bottom: Math.max(...available.map((bound) => bound.bottom)),
    };
  }

  function renderedFitBounds(fallback) {
    return unionBounds(elementBounds(refs.nodesGroup), elementBounds(refs.edgesGroup)) || fallback;
  }

  function fitView(save) {
    const nodes = normalizeNodes(state.graph);
    if (!nodes.length) return false;
    const points = nodes.map((node, index) => positionFor(node, index, nodes.length));
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y));
    const maxY = Math.max(...points.map((point) => point.y));
    const viewport = mapViewportWorldSize();
    if (!viewport.valid) return false;
    const padding = FIT_PADDING_CSS_PX / viewport.cssScale;
    const availableWidth = Math.max(1, viewport.width - padding * 2);
    const availableHeight = Math.max(1, viewport.height - padding * 2);
    let bounds = { left: minX - MAX_NODE_RADIUS, right: maxX + MAX_NODE_RADIUS, top: minY - MAX_NODE_RADIUS, bottom: maxY + MAX_NODE_RADIUS };
    let scale = Math.max(MIN_MAP_SCALE, Math.min(FIT_MAX_SCALE, availableWidth / Math.max(1, bounds.right - bounds.left), availableHeight / Math.max(1, bounds.bottom - bounds.top)));
    const applyTransform = () => {
      state.view.scale = scale;
      state.view.x = viewport.x + viewport.width / 2 - ((bounds.left + bounds.right) / 2) * scale;
      state.view.y = viewport.y + viewport.height / 2 - ((bounds.top + bounds.bottom) / 2) * scale;
      renderGraph();
    };
    // Label font sizes are recomputed from the candidate transform, so use a
    // bounded render/measure loop to fit actual circles and text, not centers.
    for (let iteration = 0; iteration < 6; iteration += 1) {
      applyTransform();
      bounds = renderedFitBounds(bounds);
      const nextScale = Math.max(MIN_MAP_SCALE, Math.min(FIT_MAX_SCALE, availableWidth / Math.max(1, bounds.right - bounds.left), availableHeight / Math.max(1, bounds.bottom - bounds.top)));
      if (Math.abs(nextScale - scale) < 0.002) {
        scale = nextScale;
        break;
      }
      scale = nextScale;
    }
    applyTransform();
    if (save) {
      state.viewDirty = true;
      scheduleViewSave();
    }
    return true;
  }

  function locateSelectedNode() {
    if (!state.selectedNodeId || !state.graph) {
      setStatus('请先点击图中的论文，再使用“定位”。', 'waiting');
      return;
    }
    const nodes = normalizeNodes(state.graph);
    const index = nodes.findIndex((node) => node.node_id === state.selectedNodeId);
    if (index < 0) return;
    const point = positionFor(nodes[index], index, nodes.length);
    state.view.x = MAP_WIDTH / 2 - point.x * state.view.scale;
    state.view.y = MAP_HEIGHT / 2 - point.y * state.view.scale;
    state.viewDirty = true;
    renderGraph();
    scheduleViewSave();
  }

  function scheduleViewSave() {
    if (!state.map?.map_id || !state.active || state.layoutPreviewActive || (!state.positionsDirty && !state.viewDirty)) return;
    const viewport = mapViewportWorldSize();
    if (!viewport.valid) return;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(saveView, 500);
  }

  async function saveView(options = {}) {
    if (!state.map?.map_id || !state.active || (!state.positionsDirty && !state.viewDirty)) return false;
    if (state.layoutPreviewActive && !options.allowLayoutPreview) return false;
    const viewport = mapViewportWorldSize();
    if (!viewport.valid) return false;
    const requestId = ++state.viewRequest;
    const mapId = state.map.map_id;
    const expectedRevision = state.map.revision;
    const activeIds = new Set(activeNodes().map((node) => node.node_id));
    const positions = Object.entries(state.positions)
      .filter(([node_id]) => activeIds.has(node_id))
      .map(([node_id, position]) => ({ node_id, x: Number(position.x), y: Number(position.y) }))
      .filter((position) => Number.isFinite(position.x) && Number.isFinite(position.y));
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/view`, {
        method: 'PATCH',
        body: JSON.stringify({
          expected_revision: expectedRevision,
          positions,
          viewport: state.view,
          layers: state.layers,
          label_mode: state.labelMode,
        }),
      });
      if (requestId !== state.viewRequest) {
        if (mapId === state.selectedMapId && state.map?.map_id === mapId && state.active) {
          const responseMap = normalizeMap(payload.map);
          if (responseMap && Number.isInteger(Number(responseMap.revision))) {
            state.map = { ...state.map, revision: Number(responseMap.revision) };
          }
          scheduleViewSave();
        }
        return;
      }
      if (requestId !== state.viewRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      state.map = normalizeMap(payload.map) || state.map;
      state.positionsDirty = false;
      state.viewDirty = false;
      setStatus('视图已保存。');
      renderMapList();
      renderCurrentMeta();
      return true;
    } catch (error) {
      if (requestId !== state.viewRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      state.positionsDirty = true;
      setStatus(`视图保存失败：${errorAction(error, '请重新打开地图后再保存。')}`, 'error');
      return false;
    }
  }

  function nodeStyleIsDirty() {
    return state.nodeStyleDraft.fill_mode !== state.nodeStyle.fill_mode
      || state.nodeStyleDraft.fill_opacity !== state.nodeStyle.fill_opacity;
  }

  function renderNodeStyleControls() {
    if (!refs.nodeStyle) return;
    refs.nodeStyle.querySelectorAll('input[name="fill_mode"]').forEach((input) => {
      input.checked = input.value === state.nodeStyleDraft.fill_mode;
    });
    const opacity = refs.nodeStyle.querySelector('input[name="fill_opacity"]');
    if (opacity) opacity.value = String(state.nodeStyleDraft.fill_opacity);
    const output = refs.nodeStyle.querySelector('.literature-map-node-style-opacity-value');
    if (output) output.textContent = `${Math.round(state.nodeStyleDraft.fill_opacity * 100)}%`;
    const dirty = nodeStyleIsDirty();
    const apply = refs.nodeStyle.querySelector('.literature-map-node-style-apply');
    const cancel = refs.nodeStyle.querySelector('.literature-map-node-style-cancel');
    if (apply) apply.disabled = !state.map?.map_id || !dirty || state.nodeStyleSaveInFlight;
    if (cancel) cancel.disabled = !dirty || state.nodeStyleSaveInFlight;
  }

  function updateNodeStyleDraft() {
    if (!refs.nodeStyle) return;
    const fillMode = refs.nodeStyle.querySelector('input[name="fill_mode"]:checked')?.value;
    const opacity = Number(refs.nodeStyle.querySelector('input[name="fill_opacity"]')?.value);
    state.nodeStyleDraft = normalizeNodeStyle({ fill_mode: fillMode, fill_opacity: opacity });
    renderNodeStyleControls();
    renderGraph();
  }

  function cancelNodeStyleDraft() {
    state.nodeStyleDraft = { ...state.nodeStyle };
    renderNodeStyleControls();
    renderGraph();
  }

  function updateSavedNodeStyle(mapId, nodeStyle, revision) {
    if (mapId !== state.selectedMapId || !state.map || state.map.map_id !== mapId) return;
    const nextStyle = normalizeNodeStyle(nodeStyle);
    const nextRevision = Number(revision);
    state.map = {
      ...state.map,
      ...(Number.isInteger(nextRevision) ? { revision: nextRevision } : {}),
      view_settings: { ...(state.map.view_settings || {}), node_style: nextStyle },
    };
    state.nodeStyle = nextStyle;
    state.nodeStyleDraft = { ...nextStyle };
    renderNodeStyleControls();
    renderGraph();
  }

  async function rereadNodeStyleAfterConflict(mapId, draft) {
    const payload = await request(`/${encodeURIComponent(mapId)}`);
    if (mapId !== state.selectedMapId || !state.active) return false;
    state.map = normalizeMap(payload.map) || state.map;
    state.nodeStyle = normalizeNodeStyle(state.map?.view_settings?.node_style);
    state.nodeStyleDraft = { ...draft };
    renderNodeStyleControls();
    renderGraph();
    setStatus('地图版本已变化，已重新读取。外观草稿仍保留；核对后请再次点击“应用外观”。', 'error');
    return true;
  }

  async function saveNodeStyle(button) {
    if (!state.map?.map_id || !state.active || state.nodeStyleSaveInFlight || !nodeStyleIsDirty()) return;
    const mapId = state.map.map_id;
    const draft = { ...state.nodeStyleDraft };
    const expectedRevision = Number(state.map.revision);
    state.nodeStyleSaveInFlight = true;
    renderNodeStyleControls();
    if (button) button.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/view`, {
        method: 'PATCH',
        body: JSON.stringify({ expected_revision: expectedRevision, node_style: draft }),
      });
      if (mapId !== state.selectedMapId || !state.active) return;
      updateSavedNodeStyle(mapId, payload.map?.view_settings?.node_style || draft, payload.map?.revision);
      setStatus('节点外观已保存。', 'waiting');
    } catch (error) {
      if (mapId !== state.selectedMapId || !state.active) return;
      if (error.status === 409) {
        try { await rereadNodeStyleAfterConflict(mapId, draft); } catch (_) {
          setStatus('地图版本已变化，外观草稿仍保留；当前无法重新读取，请稍后重试。', 'error');
        }
        return;
      }
      if (!error.status || error.retryable || error.name === 'AbortError') {
        try {
          const payload = await request(`/${encodeURIComponent(mapId)}`);
          if (mapId !== state.selectedMapId || !state.active) return;
          const saved = normalizeNodeStyle(payload.map?.view_settings?.node_style);
          state.map = normalizeMap(payload.map) || state.map;
          if (saved.fill_mode === draft.fill_mode && saved.fill_opacity === draft.fill_opacity) {
            updateSavedNodeStyle(mapId, saved, payload.map?.revision);
            setStatus('节点外观已保存（已重新读取核实）。', 'waiting');
          } else {
            state.nodeStyle = saved;
            state.nodeStyleDraft = draft;
            renderNodeStyleControls();
            renderGraph();
            setStatus('外观保存结果未能确认；已重新读取地图，外观草稿仍保留。', 'error');
          }
        } catch (_) {
          setStatus('外观保存结果暂无法确认；草稿仍保留，请稍后核对地图后重试。', 'error');
        }
        return;
      }
      setStatus(`外观保存失败：${errorAction(error, '外观草稿仍保留，可重试应用。')}`, 'error');
    } finally {
      state.nodeStyleSaveInFlight = false;
      if (button?.isConnected) button.disabled = false;
      renderNodeStyleControls();
    }
  }

  function exportFileStem() {
    const raw = mapTitle(state.map).replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 60);
    return raw || 'literature-map';
  }

  function cleanExportValue(value) {
    if (Array.isArray(value)) return value.map(cleanExportValue);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(Object.entries(value)
      .filter(([key]) => !/^owner_id$/i.test(key) && !/recent.?colors|preview/i.test(key))
      .map(([key, nested]) => [key, cleanExportValue(nested)]));
  }

  function exportFields(source, fields) {
    const result = {};
    fields.forEach((field) => {
      if (Object.prototype.hasOwnProperty.call(source || {}, field)) result[field] = cleanExportValue(source[field]);
    });
    return result;
  }

  async function sanitizeJsonExportBlob(blob) {
    let payload;
    try { payload = JSON.parse(await blob.text()); } catch (_) {
      throw new LiteratureMapError('JSON 导出内容无法解析，未下载文件。');
    }
    if (payload?.schema_version !== EXPORT_SCHEMA_VERSION || !payload.map || !Array.isArray(payload.groups)
      || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
      throw new LiteratureMapError('JSON 导出版本或数据结构不符合当前地图契约。');
    }
    const viewSettings = payload.map.view_settings || {};
    const nodeStyle = viewSettings.node_style;
    if (!nodeStyle || !['filled', 'outline'].includes(nodeStyle.fill_mode)
      || typeof nodeStyle.fill_opacity !== 'number' || !Number.isFinite(nodeStyle.fill_opacity)
      || nodeStyle.fill_opacity < 0 || nodeStyle.fill_opacity > 1) {
      throw new LiteratureMapError('JSON 导出的节点外观缺失或无效，未下载文件。');
    }
    const nodes = payload.nodes.map((node) => {
      if (!Object.prototype.hasOwnProperty.call(node || {}, 'color_override')
        || (node.color_override !== null && !normalizeHexColor(node.color_override))) {
        throw new LiteratureMapError('JSON 导出包含无效的节点颜色，未下载文件。');
      }
      const safeNode = exportFields(node, ['node_id', 'identity_key', 'external_ids', 'title', 'authors', 'year', 'venue', 'abstract', 'keywords', 'citation_count', 'source_url', 'provenance', 'catalog_paper_id', 'document_id', 'download_status', 'position', 'group_id', 'color_override']);
      safeNode.color_override = node.color_override === null ? null : normalizeHexColor(node.color_override);
      return safeNode;
    });
    const map = exportFields(payload.map, ['map_id', 'name', 'topic', 'project_id', 'filters', 'requested_count', 'revision']);
    map.view_settings = exportFields(viewSettings, ['filters', 'viewport', 'layers', 'label_mode']);
    map.view_settings.node_style = { fill_mode: nodeStyle.fill_mode, fill_opacity: nodeStyle.fill_opacity };
    const safePayload = {
      schema_version: EXPORT_SCHEMA_VERSION,
      exported_at: cleanExportValue(payload.exported_at),
      map,
      groups: payload.groups.map((group) => exportFields(group, ['group_id', 'name', 'color'])),
      nodes,
      edges: payload.edges.map((edge) => exportFields(edge, ['edge_id', 'kind', 'source_id', 'target_id', 'provenance', 'score', 'basis', 'model_version', 'content_hash'])),
    };
    return new Blob([JSON.stringify(safePayload, null, 2)], { type: 'application/json' });
  }

  function hasUnappliedVisualDraft() {
    return Boolean(state.colorDraft || nodeStyleIsDirty());
  }

  function blockExportWithUnappliedDraft(formatLabel) {
    if (!hasUnappliedVisualDraft()) return false;
    setStatus(`存在未应用的颜色或外观预览；请先应用或取消预览，再导出${formatLabel}。`, 'waiting');
    return true;
  }

  async function exportJson() {
    if (!state.map?.map_id || !state.active) return;
    if (blockExportWithUnappliedDraft(' JSON')) return;
    const requestId = ++state.exportRequest;
    refs.exportJsonButton.disabled = true;
    setStatus('正在准备 JSON 导出…', 'waiting');
    try {
      const result = await requestExport(`/${encodeURIComponent(state.map.map_id)}/export?format=json`);
      if (requestId !== state.exportRequest || !state.active) return;
      const safeBlob = await sanitizeJsonExportBlob(result.blob);
      if (requestId !== state.exportRequest || !state.active) return;
      safeDownload(safeBlob, exportFilenameFromDisposition(result.disposition, `${exportFileStem()}.json`));
      setStatus('JSON 已下载；导出只包含服务端授权的公开地图字段。');
    } catch (error) {
      if (requestId !== state.exportRequest || !state.active) return;
      setStatus(`JSON 导出失败：${errorAction(error, '请稍后重试。')}`, 'error');
    } finally {
      if (requestId === state.exportRequest) refs.exportJsonButton.disabled = false;
    }
  }

  function addExportSvgText(svg, text, x, y, attributes = {}) {
    const label = createSvgElement('text');
    setAttributes(label, { x, y, ...attributes });
    label.textContent = String(text || '');
    svg.append(label);
    return label;
  }

  function buildExportSvg() {
    if (!refs.svg || !state.graph || !normalizeNodes(state.graph).length) {
      throw new LiteratureMapError('当前图谱没有可导出的节点。');
    }
    const sourceRect = refs.svg.getBoundingClientRect();
    if (!Number.isFinite(sourceRect.width) || !Number.isFinite(sourceRect.height) || sourceRect.width <= 0 || sourceRect.height <= 0) {
      throw new LiteratureMapError('图谱当前没有有效尺寸，请先点击“适应”后重试。');
    }
    const exportHeight = MAP_HEIGHT + 92;
    const svg = refs.svg.cloneNode(true);
    setAttributes(svg, {
      xmlns: SVG_NS,
      width: MAP_WIDTH,
      height: exportHeight,
      viewBox: `0 0 ${MAP_WIDTH} ${exportHeight}`,
    });
    const background = createSvgElement('rect');
    setAttributes(background, { x: 0, y: 0, width: MAP_WIDTH, height: exportHeight, fill: '#ffffff' });
    svg.insertBefore(background, svg.firstChild);
    const style = createSvgElement('style');
    style.textContent = [
      'svg{background:#fff}',
      '.literature-map-edge{fill:none;stroke-width:1.15;opacity:.56}',
      '.literature-map-edge.citation{stroke:#8478d8}',
      '.literature-map-edge.similarity{stroke:#b7a9db;stroke-dasharray:5 4}',
      'marker path{fill:#8478d8}',
      '.literature-map-node circle{stroke:#8d80e6;stroke-width:2;fill:#fff}',
      '.literature-map-node.is-selected circle{stroke:#fff;stroke-width:2.5}',
      '.literature-map-node-label{fill:#5a5d66;font:9px monospace}',
      '.literature-map-export-title{fill:#25272b;font:700 18px Arial,sans-serif}',
      '.literature-map-export-meta{fill:#5a5d66;font:10px monospace}',
      '.literature-map-export-legend{fill:#5a5d66;font:10px monospace}',
    ].join('');
    svg.insertBefore(style, svg.firstChild);
    const viewport = svg.querySelector('#literature-map-viewport');
    const currentTransform = viewport?.getAttribute('transform') || 'translate(0 0) scale(1)';
    if (viewport) viewport.setAttribute('transform', `translate(0 36) ${currentTransform}`);
    addExportSvgText(svg, mapTitle(state.map), 16, 23, { class: 'literature-map-export-title' });
    addExportSvgText(svg, `${normalizeNodes(state.graph).length} 个节点 · ${normalizeEdges(state.graph).length} 条关系`, 16, 38, { class: 'literature-map-export-meta' });
    addExportSvgText(svg, '实线箭头：引用者 → 被引用者    虚线：主题相似（无向）', 16, MAP_HEIGHT + 57, { class: 'literature-map-export-legend' });
    let legendX = 16;
    state.groups.forEach((group) => {
      const swatch = createSvgElement('rect');
      setAttributes(swatch, { x: legendX, y: MAP_HEIGHT + 69, width: 10, height: 10, rx: 2, fill: group.color });
      svg.append(swatch);
      addExportSvgText(svg, group.name, legendX + 14, MAP_HEIGHT + 78, { class: 'literature-map-export-legend' });
      legendX += 22 + Math.max(30, group.name.length * 10);
    });
    const ungrouped = createSvgElement('rect');
    setAttributes(ungrouped, { x: legendX, y: MAP_HEIGHT + 69, width: 10, height: 10, rx: 2, fill: '#ffffff', stroke: '#8d80e6' });
    svg.append(ungrouped);
    addExportSvgText(svg, '未分组', legendX + 14, MAP_HEIGHT + 78, { class: 'literature-map-export-legend' });
    return svg;
  }

  function svgToPngBlob(svg) {
    return new Promise((resolve, reject) => {
      const xml = new XMLSerializer().serializeToString(svg);
      if (!xml || !xml.includes('<svg')) {
        reject(new LiteratureMapError('图谱快照为空，未生成 PNG。'));
        return;
      }
      const svgBlob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' });
      const imageUrl = URL.createObjectURL(svgBlob);
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(imageUrl);
        const width = Number(svg.getAttribute('width'));
        const height = Number(svg.getAttribute('height'));
        if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
          reject(new LiteratureMapError('图谱尺寸无效，未生成 PNG。'));
          return;
        }
        const ratio = Math.min(3, Math.max(1, Number(window.devicePixelRatio) || 1));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(width * ratio));
        canvas.height = Math.max(1, Math.round(height * ratio));
        const context = canvas.getContext('2d');
        if (!context) {
          reject(new LiteratureMapError('浏览器无法创建图像画布，请先适应画布后重试。'));
          return;
        }
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => {
          if (!blob || !blob.size) reject(new LiteratureMapError('PNG 为空，未生成文件。'));
          else resolve(blob);
        }, 'image/png');
      };
      image.onerror = () => {
        URL.revokeObjectURL(imageUrl);
        reject(new LiteratureMapError('图谱快照无法转换为 PNG，请先适应画布后重试。'));
      };
      image.src = imageUrl;
    });
  }

  async function exportPng() {
    if (!state.map?.map_id || !state.active) return;
    if (blockExportWithUnappliedDraft(' PNG')) return;
    const requestId = ++state.exportRequest;
    refs.exportPngButton.disabled = true;
    setStatus('正在准备 PNG 图谱快照…', 'waiting');
    try {
      const svg = buildExportSvg();
      const blob = await svgToPngBlob(svg);
      if (requestId !== state.exportRequest || !state.active) return;
      safeDownload(blob, `${exportFileStem()}.png`);
      setStatus('PNG 已下载；快照只包含当前图谱、标题和图例。');
    } catch (error) {
      if (requestId !== state.exportRequest || !state.active) return;
      setStatus(`PNG 导出失败：${errorAction(error, '请先点击“适应”后重试。')}`, 'error');
    } finally {
      if (requestId === state.exportRequest) refs.exportPngButton.disabled = false;
    }
  }

  async function selectNode(nodeId, trigger = null) {
    if (!state.map?.map_id || !nodeId) return;
    const mapId = state.map.map_id;
    state.selectedNodeId = nodeId;
    state.selectedNode = null;
    state.analysisNodeId = nodeId;
    state.analysis = null;
    state.analysisJob = null;
    state.analysisHistory = [];
    state.analysisSourceStatus = null;
    state.analysisViewedId = null;
    state.analysisPollExhausted = false;
    state.analysisTab = 'abstract';
    state.analysisSubmitInFlight = false;
    state.analysisManualRequest = false;
    stopAnalysisPolling();
    state.analysisRequest += 1;
    state.conversationRequest = 0;
    state.importRequest += 1;
    if (isMobileViewport()) openMobilePanel('detail', trigger || document.activeElement);
    else refs.detailPanel.removeAttribute('aria-hidden');
    refs.detailPanel.hidden = false;
    refs.detailPanel.classList.add('is-open');
    renderGraph();
    window.requestAnimationFrame(() => {
      if (requestId === state.nodeRequest && state.selectedNodeId === nodeId) ensureSelectedNodeVisible();
    });
    renderNodeDetail({ loading: true });
    const requestId = ++state.nodeRequest;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(nodeId)}`);
      if (requestId !== state.nodeRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      state.selectedNode = payload.node || null;
      renderNodeDetail(state.selectedNode);
      await loadNodeAnalyses(mapId, nodeId, requestId);
    } catch (error) {
      if (requestId !== state.nodeRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      renderNodeDetail({ error: errorAction(error, '论文详情读取失败，请稍后重试。') });
    }
  }

  function metadataText(value, fallback) {
    if (Array.isArray(value)) return value.length ? value.join('、') : (fallback || '未提供');
    if (value && typeof value === 'object') {
      const candidate = value.label || value.name || value.source || value.basis;
      return candidate ? metadataText(candidate, fallback) : (fallback || '未提供');
    }
    if (value === null || value === undefined || String(value).trim() === '') return fallback || '未提供';
    return String(value);
  }

  const DIFF_FIELD_LABELS = {
    title: '标题',
    authors: '作者',
    year: '年份',
    venue: '来源',
    abstract: '摘要',
    keywords: '关键词',
    citation_count: '引用数',
    source_url: '来源链接',
    relations: '关系',
    citation_relations: '引用关系',
    similarity_relations: '主题相似关系',
  };

  function diffValueText(value) {
    if (value === null) return 'null';
    if (value === undefined) return '字段缺失';
    if (typeof value === 'string') return value === '' ? '空字符串' : value;
    if (Array.isArray(value)) return value.length ? value.map((item) => diffValueText(item)).join('、') : '空列表';
    if (value && typeof value === 'object') {
      try { return JSON.stringify(value); } catch (_) { return '对象'; }
    }
    return String(value);
  }

  function diffFieldLabel(field) {
    return DIFF_FIELD_LABELS[field] || String(field || '未命名字段');
  }

  function formatRelationDiff(change) {
    if (!change || typeof change !== 'object' || Array.isArray(change)) return diffValueText(change);
    return [
      `新增关系：${diffValueText(change.added)}`,
      `移除关系：${diffValueText(change.removed)}`,
    ].join('；');
  }

  function formatPreviewDiffEntry(entry) {
    if (typeof entry === 'string') return entry;
    if (!entry || typeof entry !== 'object') return diffValueText(entry);
    const nodeId = entry.node_id || entry.nodeId;
    const node = nodeId ? normalizeNodes(state.graph).find((item) => item.node_id === nodeId) : null;
    const title = node?.title ? metadataText(node.title, '') : '';
    const subject = title ? `论文《${title}》${nodeId ? `（${nodeId}）` : ''}` : (nodeId ? `节点 ${nodeId}` : '地图');
    const changes = entry.changes && typeof entry.changes === 'object' ? entry.changes : null;
    if (!changes) {
      if (entry.field) return `${subject}：${diffFieldLabel(entry.field)}：${diffValueText(entry.value)}`;
      return `${subject}：${diffValueText(entry)}`;
    }
    const parts = Object.entries(changes).map(([field, change]) => {
      if (field === 'relations' || field.endsWith('_relations')) return formatRelationDiff(change);
      if (change && typeof change === 'object' && !Array.isArray(change) && ('from' in change || 'to' in change)) {
        return `${diffFieldLabel(field)}：${diffValueText(change.from)} → ${diffValueText(change.to)}`;
      }
      return `${diffFieldLabel(field)}：${diffValueText(change)}`;
    });
    return parts.length ? `${subject}：${parts.join('；')}` : `${subject}：无可显示字段`;
  }

  function safeHttpUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(String(value), window.location.origin);
      return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function stopAnalysisPolling() {
    if (state.analysisPollTimer) window.clearTimeout(state.analysisPollTimer);
    state.analysisPollTimer = null;
    state.analysisPollInFlight = false;
    state.analysisPollAttempts = 0;
    state.analysisPollGeneration += 1;
  }

  function stopAnalysisQueuePolling() {
    if (state.queuePollTimer) window.clearTimeout(state.queuePollTimer);
    state.queuePollTimer = null;
    state.queuePollInFlight = false;
    state.queuePollAttempts = 0;
    state.queuePollGeneration += 1;
  }

  function normalizeAnalysisQueue(payload) {
    const candidate = payload?.queue && typeof payload.queue === 'object' ? payload.queue : payload;
    if (!candidate || typeof candidate !== 'object') return null;
    const counts = candidate.counts && typeof candidate.counts === 'object' ? candidate.counts : {};
    const count = (value) => {
      const number = Number(value);
      return Number.isFinite(number) && number >= 0 ? Math.floor(number) : 0;
    };
    const failedItems = Array.isArray(candidate.failed_items) ? candidate.failed_items.slice(0, 50) : [];
    return {
      map_id: candidate.map_id || state.selectedMapId,
      queue_job_id: candidate.queue_job_id || null,
      state: ['active', 'paused', 'completed', 'partial'].includes(candidate.state) ? candidate.state : 'active',
      pause_reason: candidate.pause_reason || null,
      counts: {
        total: count(counts.total),
        completed: count(counts.completed),
        queued: count(counts.queued),
        running: count(counts.running),
        failed: count(counts.failed),
        skipped: count(counts.skipped),
      },
      current: candidate.current && typeof candidate.current === 'object' ? candidate.current : null,
      failed_items: failedItems,
    };
  }

  function queueStateLabel(value) {
    return ({ active: '运行中', paused: '已暂停', completed: '已完成', partial: '部分完成' })[value] || '处理中';
  }

  function queuePauseReasonLabel(value) {
    if (!value) return '';
    const reason = String(value);
    const normalized = reason.toUpperCase();
    if (normalized === 'USER' || normalized === 'USER_PAUSED') return '用户已暂停。';
    if (normalized.includes('AUTH') || normalized.includes('LOGIN')) return '需要模型授权；完成授权后可继续。';
    if (normalized.includes('CONFIG') || normalized.includes('MODEL_UNAVAILABLE')) return '模型配置暂不可用；修复配置后可继续。';
    if (/^[A-Z][A-Z0-9_:-]{2,}$/.test(reason)) return '队列已暂停；修复配置后可继续。';
    return reason;
  }

  function analysisQueueIsCurrent(mapId, requestId, generation) {
    return Boolean(state.active && state.selectedMapId === mapId && state.map?.map_id === mapId && state.mapRequest === requestId && state.queuePollGeneration === generation);
  }

  function analysisQueueNeedsPolling(queue) {
    if (!queue || queue.state !== 'active') return false;
    const counts = queue.counts || {};
    return Number(counts.queued) > 0 || Number(counts.running) > 0;
  }

  function analysisQueueSignature(queue) {
    if (!queue) return '';
    try {
      return JSON.stringify({
        state: queue.state,
        pause_reason: queue.pause_reason,
        counts: queue.counts,
        current: queue.current,
        failed_items: queue.failed_items,
      });
    } catch (_) {
      return `${queue.state}:${queue.counts?.completed || 0}:${queue.counts?.failed || 0}`;
    }
  }

  function scheduleAnalysisQueuePoll(delay, mapId, requestId, generation) {
    if (!analysisQueueIsCurrent(mapId, requestId, generation) || !analysisQueueNeedsPolling(state.analysisQueue)) return;
    if (state.queuePollTimer) window.clearTimeout(state.queuePollTimer);
    state.queuePollTimer = window.setTimeout(() => pollAnalysisQueue(mapId, requestId, generation), Math.max(0, Number(delay) || 0));
  }

  function queueItemLabel(item) {
    if (item && typeof item === 'object') {
      const candidate = item.title || item.node_title || item.node_id || item.analysis_id || item.message;
      return safeAnalysisReason(metadataText(candidate, '某个分析项'), '某个分析项');
    }
    return safeAnalysisReason(metadataText(item, '某个分析项'), '某个分析项');
  }

  function renderAnalysisQueue() {
    if (!refs.queuePanel) return;
    refs.queuePanel.replaceChildren();
    const queue = state.analysisQueue;
    if (!queue && !state.queueError) {
      refs.queuePanel.hidden = true;
      return;
    }
    if (queue && !state.queueError && queue.state === 'completed' && Number(queue.counts?.total || 0) === 0 && !queue.failed_items?.length) {
      refs.queuePanel.hidden = true;
      return;
    }
    refs.queuePanel.hidden = false;
    refs.queuePanel.append(createElement('h3', 'literature-map-analysis-queue-title', '摘要分析队列'));
    if (state.queueError) {
      const error = createElement('p', 'literature-map-analysis-queue-error', state.queueError);
      error.setAttribute('role', 'alert');
      refs.queuePanel.append(error);
    }
    if (!queue) return;
    const stateLine = createElement('p', 'literature-map-analysis-queue-state', `状态：${queueStateLabel(queue.state)}`);
    refs.queuePanel.append(stateLine);
    const counts = queue.counts || {};
    refs.queuePanel.append(createElement('p', 'literature-map-analysis-queue-counts', `完成 ${counts.completed || 0}/${counts.total || 0} · 排队 ${counts.queued || 0} · 运行 ${counts.running || 0} · 失败 ${counts.failed || 0} · 跳过 ${counts.skipped || 0}`));
    const pauseReason = queuePauseReasonLabel(queue.pause_reason);
    if (pauseReason) refs.queuePanel.append(createElement('p', 'literature-map-analysis-queue-pause', pauseReason));
    if (queue.current) {
      const currentName = queueItemLabel(queue.current);
      const currentStatus = queue.current.status ? safeAnalysisReason(analysisStatusLabel(queue.current.status), '处理中') : '处理中';
      refs.queuePanel.append(createElement('p', 'literature-map-analysis-queue-current', `当前：${currentName}（${currentStatus}）`));
    }
    const actions = createElement('div', 'literature-map-analysis-queue-actions');
    if (queue.state === 'active') {
      const pause = createElement('button', 'secondary-button', '暂停队列');
      pause.type = 'button';
      pause.addEventListener('click', () => mutateAnalysisQueue('pause', pause));
      actions.append(pause);
    } else if (queue.state === 'paused') {
      const resume = createElement('button', 'send-button', '继续队列');
      resume.type = 'button';
      resume.addEventListener('click', () => mutateAnalysisQueue('resume', resume));
      actions.append(resume);
    }
    const retryable = (queue.failed_items || []).some((item) => item?.retryable !== false);
    if (Number(counts.failed) > 0 && retryable) {
      const retry = createElement('button', 'secondary-button', '重试失败项');
      retry.type = 'button';
      retry.addEventListener('click', () => mutateAnalysisQueue('retry', retry));
      actions.append(retry);
    }
    if (actions.childNodes.length) refs.queuePanel.append(actions);
    if (queue.failed_items?.length) {
      const failed = createElement('p', 'literature-map-analysis-queue-failed', `失败项 ${queue.failed_items.length} 个：${queue.failed_items.slice(0, 5).map(queueItemLabel).join('、')}`);
      refs.queuePanel.append(failed);
    }
  }

  async function mutateAnalysisQueue(action, button) {
    if (!state.map?.map_id || !state.active || !['pause', 'resume', 'retry'].includes(action)) return;
    const mapId = state.map.map_id;
    const requestId = state.mapRequest;
    const mutationRequest = ++state.queueMutationRequest;
    stopAnalysisQueuePolling();
    const generation = state.queuePollGeneration;
    if (button) button.disabled = true;
    state.queueError = '';
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/analysis-queue/${action}`, {
        method: 'POST',
        body: JSON.stringify({ idempotency_key: makeIdempotencyKey() }),
      });
      if (mutationRequest !== state.queueMutationRequest || !analysisQueueIsCurrent(mapId, requestId, generation)) return;
      state.analysisQueue = normalizeAnalysisQueue(payload);
      state.queueSignature = analysisQueueSignature(state.analysisQueue);
      renderAnalysisQueue();
      if (analysisQueueNeedsPolling(state.analysisQueue)) scheduleAnalysisQueuePoll(0, mapId, requestId, generation);
    } catch (_) {
      if (mutationRequest !== state.queueMutationRequest || !analysisQueueIsCurrent(mapId, requestId, generation)) return;
      state.queueError = '队列操作失败；请检查配置后重试，已保留当前结果。';
      renderAnalysisQueue();
    } finally {
      if (mutationRequest === state.queueMutationRequest && button) button.disabled = false;
    }
  }

  async function pollAnalysisQueue(mapId, requestId, generation) {
    if (!analysisQueueIsCurrent(mapId, requestId, generation) || state.queuePollInFlight) return;
    state.queuePollTimer = null;
    if (state.queuePollAttempts >= MAX_QUEUE_POLL_ATTEMPTS) {
      state.queueError = '摘要队列仍在后台运行；已暂停自动查询，重新打开地图可继续查看。';
      renderAnalysisQueue();
      return;
    }
    state.queuePollInFlight = true;
    state.queuePollAttempts += 1;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/analysis-queue`);
      if (!analysisQueueIsCurrent(mapId, requestId, generation)) return;
      const queue = normalizeAnalysisQueue(payload);
      if (!queue) throw new LiteratureMapError('队列响应无效。');
      state.analysisQueue = queue;
      state.queueSignature = analysisQueueSignature(queue);
      state.queueError = '';
      renderAnalysisQueue();
      if (state.selectedNodeId) await loadNodeAnalyses(mapId, state.selectedNodeId, state.nodeRequest);
      if (analysisQueueNeedsPolling(queue)) scheduleAnalysisQueuePoll(QUEUE_POLL_DELAY, mapId, requestId, generation);
    } catch (_) {
      if (!analysisQueueIsCurrent(mapId, requestId, generation)) return;
      state.queueError = '摘要队列读取失败；已保留当前结果，稍后会自动重试。';
      renderAnalysisQueue();
      if (analysisQueueNeedsPolling(state.analysisQueue)) scheduleAnalysisQueuePoll(QUEUE_POLL_BACKOFF, mapId, requestId, generation);
    } finally {
      state.queuePollInFlight = false;
    }
  }

  async function ensureAnalysisQueue(mapId, requestId) {
    if (!mapId || state.queueEnsureMapId === mapId || !analysisQueueIsCurrent(mapId, requestId, state.queuePollGeneration)) return;
    state.queueEnsureMapId = mapId;
    state.queueEnsureKey = makeIdempotencyKey();
    state.queueError = '';
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/analysis-queue/ensure`, {
        method: 'POST',
        body: JSON.stringify({ idempotency_key: state.queueEnsureKey }),
      });
      if (!analysisQueueIsCurrent(mapId, requestId, state.queuePollGeneration)) return;
      state.analysisQueue = normalizeAnalysisQueue(payload);
      state.queueSignature = analysisQueueSignature(state.analysisQueue);
      renderAnalysisQueue();
      if (analysisQueueNeedsPolling(state.analysisQueue)) scheduleAnalysisQueuePoll(0, mapId, requestId, state.queuePollGeneration);
    } catch (_) {
      if (!analysisQueueIsCurrent(mapId, requestId, state.queuePollGeneration)) return;
      state.queueError = '摘要队列读取失败；可重新打开地图重试，已保留当前图谱。';
      renderAnalysisQueue();
    }
  }

  function analysisStatusLabel(status) {
    const labels = { queued: '排队中', running: '生成中', completed: '已完成', failed: '失败', stopped: '已停止' };
    return labels[String(status || '').toLowerCase()] || '状态待确认';
  }

  function analysisEvidenceLabel(level) {
    if (level === 'full') return '全文索引片段依据';
    if (level === 'abstract') return '摘要级';
    return '状态待确认';
  }

  function analysisSourceVersion(status, level) {
    const versions = status?.source_versions && typeof status.source_versions === 'object' ? status.source_versions : {};
    return versions[level] || '';
  }

  function analysisAvailable(level) {
    const status = state.analysisSourceStatus || {};
    if (level === 'full') return status.fulltext_ready === true;
    if (level === 'abstract') return status.abstract_available === true;
    return false;
  }

  function availableAnalysisEvidenceLevels(status) {
    const sourceStatus = status && typeof status === 'object' ? status : {};
    const available = [];
    if (sourceStatus.abstract_available === true) available.push('abstract');
    if (sourceStatus.fulltext_ready === true) available.push('full');
    return available;
  }

  function fulltextUnavailableInfo() {
    const status = state.analysisSourceStatus;
    const node = state.selectedNode || {};
    const downloadStatus = String(node.download_status || '').trim().toLowerCase();
    const documentId = String(node.document_id || '').trim();
    const reason = String(status?.unavailable_reason || '').trim();
    const normalizedReason = reason.toUpperCase();
    const diagnostics = nodeImportDiagnostics(node);
    const diagnosticCode = String(diagnostics?.error_code || '').toUpperCase();
    const diagnosticText = diagnostics?.reasons?.join('；') || '';
    const machineCode = /^[A-Z][A-Z0-9_:-]{2,}$/.test(reason);
    const pendingStatuses = new Set(['queued', 'running', 'pending', 'submitted', 'processing', 'importing', 'downloading', 'validating', 'indexing']);
    const loginCodes = new Set(['LOGIN_REQUIRED', 'KB_AUTH_REQUIRED', 'AUTH_REQUIRED', 'BROWSER_SESSION_REQUIRED', 'BROWSER_SESSION_EXPIRED']);
    const permissionCodes = new Set(['KB_PERMISSION_DENIED', 'PERMISSION_DENIED', 'SOURCE_PERMISSION_DENIED', 'FULLTEXT_PERMISSION_DENIED']);
    const mismatchCodes = new Set(['SOURCE_VERSION_MISMATCH', 'KB_SOURCE_VERSION_MISMATCH', 'FULLTEXT_SOURCE_VERSION_MISMATCH', 'SOURCE_MISMATCH', 'KB_SOURCE_MISMATCH']);
    const indexFailureCodes = new Set(['KB_INDEX_FAILED', 'INDEX_FAILED', 'FULLTEXT_INDEX_FAILED', 'MAP_INDEX_FAILED']);
    const indexPendingCodes = new Set(['KB_INDEX_PENDING', 'INDEX_PENDING', 'FULLTEXT_INDEX_PENDING']);

    if (status?.fulltext_ready === true) return { kind: 'ready', label: '全文依据已就绪', message: '全文索引片段可用于 AI 分析。这里展示分析结果，不是 PDF 阅读器；原文请使用“打开原文”。' };
    if (loginCodes.has(normalizedReason) || loginCodes.has(diagnosticCode) || downloadStatus === 'waiting_login') {
      return {
        kind: 'login',
        label: '需要登录处理',
        message: '当前来源需要登录或受控浏览器处理。请在“论文检索”的既有导入处理区完成现有等待登录批次中的登录；完成后返回地图刷新全文状态。不会自动登录、重新检索或创建新导入批次。',
      };
    }
    if (indexFailureCodes.has(normalizedReason) || indexFailureCodes.has(diagnosticCode)) {
      return { kind: 'index-failed', label: '索引失败', message: `${diagnosticText || '服务器报告全文索引失败。'}请前往知识库检查并修复索引后，再刷新全文状态。` };
    }
    if (permissionCodes.has(normalizedReason)) {
      return { kind: 'permission', label: '权限不足', message: '服务器报告当前账号没有读取这份全文的权限。请前往知识库检查文档权限；权限恢复后再刷新状态。' };
    }
    if (mismatchCodes.has(normalizedReason)) {
      return { kind: 'source-mismatch', label: '来源版本不匹配', message: '服务器报告知识库来源版本与当前地图记录不一致。请前往知识库核对来源并修复索引；不会自动重新下载或分析。' };
    }
    if (indexPendingCodes.has(normalizedReason)) {
      return { kind: 'processing', label: '全文索引处理中', message: '服务器报告全文索引仍在处理中。可稍后刷新全文状态；不会自动重复入库或生成分析。' };
    }
    if (pendingStatuses.has(downloadStatus)) {
      return { kind: 'processing', label: '入库或索引处理中', message: `全文正在入库或建立索引（当前入库状态：${mapStatusLabel(downloadStatus)}）。请等待现有任务完成后刷新全文状态。` };
    }
    if (downloadStatus === 'failed') {
      const reasonText = diagnosticText || '入库失败原因未记录。';
      return { kind: 'failed', label: '入库失败', message: `${reasonText} 请使用下方现有人工重试入口；若未标记可重试，请按诊断前往知识库处理。` };
    }
    if (downloadStatus === 'not_imported' && !documentId) {
      return { kind: 'not-imported', label: '未入库', message: '这篇论文尚未加入知识库。点击下方按钮可按现有流程提交入库；全文分析不会自动触发。' };
    }
    if (!downloadStatus && !documentId) {
      if (!status) return { kind: 'loading', label: '状态待确认', message: '正在读取全文来源状态；如果状态仍未更新，可刷新后重试。' };
      return { kind: 'not-imported', label: '未入库', message: '这篇论文尚未加入知识库。点击下方按钮可按现有流程提交入库；全文分析不会自动触发。' };
    }
    if (reason && !machineCode && normalizedReason !== 'MAP_FULLTEXT_UNAVAILABLE' && normalizedReason !== 'MAP_EVIDENCE_UNAVAILABLE') {
      return { kind: 'unknown', label: '原因待核实', message: `服务器返回原因：${safeAnalysisReason(reason, '状态待确认').slice(0, 300)}。请前往知识库核实全文状态后刷新。` };
    }
    if (downloadStatus === 'indexed' || documentId) {
      return { kind: 'unknown', label: '原因未确定', message: '全文依据暂不可用：论文已加入知识库，但服务器未确认全文索引可用，具体原因未确定。请前往知识库检查文档并修复索引，再刷新全文状态；不会把“已入库”当作“全文已就绪”。' };
    }
    if (!status) {
      return { kind: 'loading', label: '状态待确认', message: '正在读取全文来源状态；如果状态仍未更新，可刷新后重试。' };
    }
    return { kind: 'unknown', label: '状态待确认', message: '全文依据暂不可用，具体原因未确定。请查看现有导入处理记录或在知识库核实来源与索引状态。' };
  }

  function safeAnalysisReason(value, fallback) {
    const text = String(value || '').trim();
    if (!text) return fallback;
    const normalized = text.toUpperCase();
    const messages = {
      MAP_ABSTRACT_UNAVAILABLE: '缺少摘要，不能生成摘要级分析；请先获取摘要。',
      MAP_FULLTEXT_UNAVAILABLE: '全文依据暂不可用，具体原因未确定。',
      MAP_EVIDENCE_UNAVAILABLE: '没有可引用的有效证据片段，暂不生成分析。',
      KB_IMPORT_REQUIRED: '全文尚未加入知识库；可先获取并加入知识库。',
      KB_AUTH_REQUIRED: '需要登录或授权后才能读取全文；请先完成授权。',
      KB_INDEX_PENDING: '全文正在等待索引；完成后可重新读取状态。',
    };
    if (messages[normalized]) return messages[normalized];
    if (/^[A-Z][A-Z0-9_:-]{2,}$/.test(text)) {
      if (normalized.includes('AUTH') || normalized.includes('LOGIN')) return '需要登录或授权后才能读取全文；请先完成授权。';
      return fallback;
    }
    return text;
  }

  function analysisUnavailableMessage(level) {
    const sourceStatus = state.analysisSourceStatus || {};
    if (String(sourceStatus.unavailable_reason || '').toUpperCase() === 'MAP_EVIDENCE_UNAVAILABLE') {
      return '没有可引用的有效证据片段，暂不生成分析。';
    }
    if (level === 'abstract') {
      const explicitlyUnavailable = sourceStatus.abstract_available === false;
      if (explicitlyUnavailable && sourceStatus.unavailable_reason) {
        return safeAnalysisReason(sourceStatus.unavailable_reason, '缺少摘要，不能生成摘要级分析；请先获取摘要。');
      }
      return '缺少摘要，不能生成摘要级分析；请先获取摘要。';
    }
    return fulltextUnavailableInfo().message;
  }

  function analysisUnavailableActionMessage(level, action) {
    const reason = analysisUnavailableMessage(level);
    if (action === 'conversation') return `${reason} 下一步：先准备摘要或全文索引依据，再点击“关于本篇提问”。`;
    if (level === 'full') {
      const nextStep = fulltextUnavailableInfo().kind === 'not-imported'
        ? '切换到“全文分析”页签并使用“获取并加入知识库”'
        : fulltextUnavailableInfo().kind === 'login'
          ? '查看“导入处理/登录处理”并完成现有等待登录项'
          : fulltextUnavailableInfo().kind === 'processing'
            ? '等待现有入库或索引任务后刷新全文状态'
            : '前往知识库检查或修复索引';
      if (action === 'analysis' && state.analysisTab !== 'full') return `${reason} 下一步：请先切换到“全文分析”页签查看状态与操作卡，再${nextStep}。`;
      return `${reason} 下一步：${nextStep}。`;
    }
    return `${reason} 下一步：先刷新论文详情或获取摘要，摘要可用后再试。`;
  }

  function analysisBusyMessage() {
    const level = state.analysis?.evidence_level === 'full' ? 'full' : 'abstract';
    const status = state.analysis?.status || (state.analysisSubmitInFlight ? 'queued' : 'running');
    return `${analysisEvidenceLabel(level)}分析${analysisStatusLabel(status)}；请等待当前请求完成后再操作。`;
  }

  function analysisErrorMessage(error) {
    const code = String(error?.code || '').toUpperCase();
    if (code) return safeAnalysisReason(code, safeAnalysisReason(error?.message, '分析失败，请稍后重试。'));
    return safeAnalysisReason(error?.message, '分析失败，请稍后重试。');
  }

  function analysisRecords() {
    const records = Array.isArray(state.analysisHistory) ? state.analysisHistory.slice() : [];
    if (state.analysis?.analysis_id && !records.some((record) => record.analysis_id === state.analysis.analysis_id)) records.unshift(state.analysis);
    return records;
  }

  function rememberCompletedAnalysis() {
    const current = state.analysis;
    if (!current?.analysis_id || current.status !== 'completed') return;
    const history = Array.isArray(state.analysisHistory) ? state.analysisHistory.slice() : [];
    if (history.some((record) => record?.analysis_id === current.analysis_id)) return;
    state.analysisHistory = [current, ...history];
  }

  function analysisResultNode(record) {
    const result = record?.result;
    if (!result || typeof result !== 'object' || !String(result.summary || '').trim()) return null;
    const section = createElement('section', 'literature-map-analysis-result');
    const heading = createElement('h4', '', record.evidence_level === 'abstract' ? '摘要级分析结果（仅基于摘要）' : '全文分析结果（全文索引片段依据）');
    const meta = createElement('p', 'literature-map-analysis-result-meta', `依据：${analysisEvidenceLabel(record.evidence_level)} · 版本：${metadataText(record.source_version, '未提供')}`);
    const summary = renderAnalysisMarkdown(result.summary);
    section.append(heading, meta, summary);
    const citations = Array.isArray(result.citations) ? result.citations : [];
    const refs = Array.isArray(result.source_refs) ? result.source_refs : [];
    if (citations.length || refs.length) {
      const evidence = createElement('p', 'literature-map-analysis-evidence', `受控来源引用：${citations.length + refs.length} 条`);
      section.append(evidence);
      const evidenceList = createElement('ul', 'literature-map-analysis-citations');
      [...citations, ...refs].forEach((citation) => {
        const value = citation && typeof citation === 'object'
          ? (citation.text || citation.quote || citation.chunk_id || citation.document_id || citation.locator || citation.source)
          : citation;
        evidenceList.append(createElement('li', '', metadataText(value, '受控来源引用')));
      });
      section.append(evidenceList);
    }
    return section;
  }

  function selectedAnalysisRecord(records) {
    if (state.analysisViewedId) {
      const selected = records.find((record) => record?.analysis_id === state.analysisViewedId);
      if (selected) return selected;
    }
    return state.analysis?.status === 'completed' ? state.analysis : records.find((record) => record?.status === 'completed');
  }

  function fulltextRecoveryActions(info, showActionFeedback) {
    const actions = createElement('div', 'literature-map-analysis-source-actions');
    const addButton = (label, handler) => {
      const button = createElement('button', 'secondary-button', label);
      button.type = 'button';
      button.addEventListener('click', handler);
      actions.append(button);
      return button;
    };
    const detailImportButton = refs.detail?.querySelector('#literature-map-import-button');
    const node = state.selectedNode || {};
    const documentId = String(node.document_id || '').trim();
    const openKnowledgeLabel = info.kind === 'permission' ? '检查知识库权限'
      : info.kind === 'index-failed' ? '前往知识库修复索引'
        : '前往知识库检查或修复索引';
    const openKnowledge = () => openKnowledgeBaseDocument(documentId);
    const refresh = () => {
      const mapId = state.selectedMapId;
      const nodeId = state.selectedNodeId;
      if (mapId && nodeId) loadNodeAnalyses(mapId, nodeId, state.nodeRequest);
    };

    if (info.kind === 'not-imported') {
      addButton('获取并加入知识库', () => {
        if (!detailImportButton) {
          showActionFeedback('当前无法提交入库。请重新打开论文详情后查看入库状态。');
        } else if (detailImportButton.disabled) {
          showActionFeedback('现有入库操作暂不可用；请查看论文详情中的中文诊断与下一步。');
        } else {
          detailImportButton.click();
        }
      });
    } else if (info.kind === 'login') {
      addButton('查看导入处理/登录处理', () => {
        openExistingImportRecovery();
        showActionFeedback('已打开论文检索的既有导入处理区。请完成现有等待登录项；若没有该项，请勿重新检索或新建批次。完成后返回地图刷新全文状态。');
      });
    } else if (info.kind === 'processing' || info.kind === 'loading') {
      addButton('刷新全文状态', refresh);
    } else if (info.kind === 'failed') {
      if (detailImportButton && !detailImportButton.disabled) {
        addButton(detailImportButton.textContent.trim() || '人工重试入库', () => detailImportButton.click());
      } else {
        addButton('查看入库诊断', () => {
          revealImportDiagnostics();
          showActionFeedback('请按入库诊断中的人工处理说明继续；当前没有可安全执行的自动重试。');
        });
        addButton('前往知识库处理', openKnowledge);
      }
    } else if (info.kind === 'permission' || info.kind === 'index-failed' || info.kind === 'source-mismatch') {
      addButton(openKnowledgeLabel, openKnowledge);
      addButton('刷新全文状态', refresh);
    } else if (info.kind === 'unknown') {
      if (String(node.download_status || '').toLowerCase() === 'indexed' || documentId) {
        addButton(openKnowledgeLabel, openKnowledge);
      } else {
        addButton('查看导入处理/登录处理', () => {
          openExistingImportRecovery();
          showActionFeedback('请查看既有导入处理记录；若没有等待登录任务，请勿重新检索。核实后返回地图刷新状态。');
        });
      }
      addButton('刷新全文状态', refresh);
    }
    return actions.childNodes.length ? actions : null;
  }

  function renderAnalysisPanel() {
    const panel = createElement('section', 'literature-map-analysis');
    panel.setAttribute('aria-live', 'polite');
    panel.append(createElement('h4', 'literature-map-analysis-title', 'AI 分析与会话'));
    const sourceStatus = state.analysisSourceStatus || {};
    const available = availableAnalysisEvidenceLevels(sourceStatus);
    const sourceText = available.length ? `可用依据：${available.map(analysisEvidenceLabel).join('、')}` : '当前没有可用分析依据。';
    panel.append(createElement('p', 'literature-map-analysis-source', sourceText));
    const activeLevel = ['abstract', 'full'].includes(state.analysisTab) ? state.analysisTab : 'abstract';
    const versions = sourceStatus.source_versions && typeof sourceStatus.source_versions === 'object' ? sourceStatus.source_versions : {};
    Object.entries(versions).forEach(([level, version]) => {
      if (!['abstract', 'full'].includes(level)) return;
      panel.append(createElement('p', 'literature-map-analysis-version', `${analysisEvidenceLabel(level)}来源版本：${metadataText(version, '未提供')}`));
    });

    const tabs = createElement('div', 'literature-map-analysis-tabs');
    tabs.setAttribute('role', 'tablist');
    [['abstract', '摘要分析'], ['full', '全文分析']].forEach(([level, label]) => {
      const tab = createElement('button', 'secondary-button literature-map-analysis-tab', label);
      tab.type = 'button';
      tab.dataset.evidenceLevel = level;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', activeLevel === level ? 'true' : 'false');
      tab.addEventListener('click', () => {
        state.analysisTab = level;
        state.analysisViewedId = null;
        renderNodeDetail(state.selectedNode);
      });
      tabs.append(tab);
    });
    panel.append(tabs);

    const actions = createElement('div', 'literature-map-analysis-actions');
    const actionFeedback = createElement('p', 'literature-map-analysis-unavailable');
    actionFeedback.classList.add('literature-map-analysis-action-feedback');
    actionFeedback.id = 'literature-map-analysis-action-feedback';
    actionFeedback.dataset.analysisActionFeedback = 'true';
    actionFeedback.setAttribute('role', 'status');
    actionFeedback.hidden = true;
    const showActionFeedback = (message) => {
      actionFeedback.textContent = message;
      actionFeedback.hidden = false;
    };
    const analysisBusy = state.analysisSubmitInFlight || ['queued', 'running'].includes(state.analysis?.status);
    const busyLevel = state.analysis?.evidence_level === 'full' ? 'full' : 'abstract';
    if (analysisBusy) showActionFeedback(analysisBusyMessage());

    const records = analysisRecords();
    const activeRecords = records.filter((record) => record?.evidence_level === activeLevel);
    const preferredLevel = activeLevel && analysisAvailable(activeLevel)
      ? activeLevel
      : state.analysis?.evidence_level || records.find((record) => record?.status === 'completed')?.evidence_level || (analysisAvailable('abstract') ? 'abstract' : 'full');
    const completedActive = activeRecords.some((record) => record?.status === 'completed');

    const abstractLabel = analysisBusy
      ? (busyLevel === 'abstract' ? '摘要分析进行中…' : '摘要分析等待中…')
      : '基于摘要分析';
    const abstractButton = createElement('button', 'send-button', abstractLabel);
    abstractButton.type = 'button';
    abstractButton.disabled = analysisBusy;
    abstractButton.setAttribute('aria-describedby', actionFeedback.id);
    abstractButton.addEventListener('click', () => {
      if (!analysisAvailable('abstract')) {
        showActionFeedback(analysisUnavailableActionMessage('abstract', 'analysis'));
        return;
      }
      startAnalysis('abstract');
    });
    const fullLabel = analysisBusy
      ? (busyLevel === 'full' ? '全文分析进行中…' : '全文分析等待中…')
      : '基于全文分析';
    const fullButton = createElement('button', 'secondary-button', fullLabel);
    fullButton.type = 'button';
    fullButton.disabled = analysisBusy && analysisAvailable('full');
    fullButton.setAttribute('aria-describedby', actionFeedback.id);
    fullButton.addEventListener('click', () => {
      if (!analysisAvailable('full')) {
        showActionFeedback(analysisUnavailableActionMessage('full', 'analysis'));
        return;
      }
      startAnalysis('full');
    });
    actions.append(abstractButton);
    if (activeLevel !== 'full') actions.append(fullButton);
    if (completedActive && analysisAvailable(activeLevel)) {
      const manualLabel = `重新生成${activeLevel === 'full' ? '全文' : '摘要'}（会调用模型）`;
      const manual = createElement('button', 'secondary-button', analysisBusy ? `${manualLabel}（分析进行中…）` : manualLabel);
      manual.type = 'button';
      manual.disabled = analysisBusy;
      manual.setAttribute('aria-describedby', actionFeedback.id);
      if (analysisBusy) manual.title = '当前分析仍在进行；请等待完成后再重新生成。';
      manual.addEventListener('click', () => {
        if (analysisBusy) {
          showActionFeedback(analysisBusyMessage());
          return;
        }
        setStatus(`将调用模型重新生成${activeLevel === 'full' ? '全文' : '摘要'}；旧结果仍保留。`, 'waiting');
        startAnalysis(activeLevel, { manual: true });
      });
      actions.append(manual);
    }
    const conversationBusy = state.conversationRequest > 0;
    const conversationButton = createElement('button', 'secondary-button', conversationBusy ? '关于本篇提问（打开中…）' : '关于本篇提问');
    conversationButton.type = 'button';
    conversationButton.disabled = conversationBusy;
    conversationButton.setAttribute('aria-describedby', actionFeedback.id);
    conversationButton.addEventListener('click', () => {
      if (!analysisAvailable(preferredLevel)) {
        showActionFeedback(analysisUnavailableActionMessage(preferredLevel, 'conversation'));
        return;
      }
      createNodeConversation(preferredLevel, conversationButton);
    });
    actions.append(conversationButton);

    if (activeLevel === 'full') {
      const rawFulltextInfo = fulltextUnavailableInfo();
      const fullAnalysisBusy = analysisBusy && busyLevel === 'full';
      const fullFailure = state.analysis?.evidence_level === 'full' && state.analysis.status === 'failed';
      const fullCardInfo = rawFulltextInfo.kind !== 'ready'
        ? rawFulltextInfo
        : fullAnalysisBusy
          ? { kind: 'running', label: state.analysisSubmitInFlight ? '全文分析正在提交' : (state.analysis?.status === 'queued' ? '全文分析正在排队' : '全文分析正在生成'), message: '全文索引片段可用；正在按你的请求生成 AI 分析，结果会通过现有进度查询更新。' }
          : completedActive
            ? { kind: 'completed', label: '全文分析已完成', message: '当前展示基于全文索引片段生成的 AI 分析结果；可在下方查看结果与历史版本。' }
            : fullFailure
              ? { kind: 'failed', label: '全文分析失败', message: '全文依据仍可用。请查看下方失败原因，之后可由你主动重试或重新生成。' }
              : { kind: 'ready', label: '全文依据已就绪', message: '尚无全文分析结果。点击下方“基于全文分析”后才会开始生成；这里展示 AI 结果，不是 PDF 阅读器。原文请使用“打开原文”。' };
      const card = createElement('section', 'literature-map-fulltext-feedback');
      card.dataset.state = fullCardInfo.kind;
      card.setAttribute('aria-live', 'polite');
      card.append(createElement('h4', 'literature-map-fulltext-title', '全文依据与分析状态'));
      card.append(createElement('span', 'literature-map-fulltext-badge', fullCardInfo.label));
      card.append(createElement('p', 'literature-map-fulltext-message', fullCardInfo.message));
      const recoveryActions = fulltextRecoveryActions(rawFulltextInfo, showActionFeedback);
      if (recoveryActions) card.append(recoveryActions);
      if (rawFulltextInfo.kind !== 'ready') {
        card.append(fullButton);
      } else if (fullAnalysisBusy) {
        fullButton.disabled = true;
        card.append(fullButton);
      } else {
        fullButton.disabled = false;
        card.append(fullButton);
      }
      card.append(actionFeedback);
      panel.append(card);
    }
    panel.append(actions);
    if (activeLevel !== 'full') panel.append(actionFeedback);

    if (activeRecords.length) {
      const history = createElement('ul', 'literature-map-analysis-history');
      activeRecords.forEach((record) => {
        const item = createElement('li', 'literature-map-analysis-history-item');
        const historyButton = createElement('button', 'literature-map-analysis-history-button', `v${metadataText(record.version, '—')} · ${analysisEvidenceLabel(record.evidence_level)} · ${analysisStatusLabel(record.status)} · ${metadataText(record.source_version, '无来源版本')}`);
        historyButton.type = 'button';
        historyButton.setAttribute('aria-pressed', state.analysisViewedId === record.analysis_id ? 'true' : 'false');
        historyButton.addEventListener('click', () => {
          state.analysisTab = record.evidence_level === 'full' ? 'full' : 'abstract';
          state.analysisViewedId = record.analysis_id || null;
          renderNodeDetail(state.selectedNode);
        });
        item.append(historyButton);
        history.append(item);
      });
      panel.append(createElement('p', 'literature-map-analysis-history-title', '历史版本（可点击查看旧结果）'), history);
    }

    if (state.analysis?.status === 'queued' || state.analysis?.status === 'running') {
      if (state.analysisPollExhausted) {
        panel.append(createElement('p', 'literature-map-analysis-state', '后台分析仍在运行；已暂停自动查询，任务不会被标记失败。'));
        const refresh = createElement('button', 'secondary-button', '重新查询');
        refresh.type = 'button';
        refresh.addEventListener('click', () => resumeAnalysisPolling());
        panel.append(refresh);
      } else {
        panel.append(createElement('p', 'literature-map-analysis-state', `分析${analysisStatusLabel(state.analysis.status)}…`));
      }
    }
    if (state.analysis?.status === 'failed') {
      const error = createElement('p', 'literature-map-analysis-error', analysisErrorMessage(state.analysis.error));
      error.setAttribute('role', 'alert');
      panel.append(error);
      if (state.analysis.error?.retryable) {
        const retry = createElement('button', 'secondary-button', '重新分析');
        retry.type = 'button';
        retry.addEventListener('click', () => startAnalysis(state.analysis.evidence_level || preferredLevel, { manual: true }));
        panel.append(retry);
      }
    }
    const resultRecord = selectedAnalysisRecord(activeRecords);
    const result = analysisResultNode(resultRecord);
    if (result) panel.append(result);
    return panel;
  }

  async function loadNodeAnalyses(mapId, nodeId, nodeRequestId) {
    const analysisRequestId = state.analysisRequest;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(nodeId)}/analyses`);
      if (nodeRequestId !== state.nodeRequest || analysisRequestId !== state.analysisRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysisHistory = Array.isArray(payload.analyses) ? payload.analyses : [];
      state.analysisSourceStatus = payload.source_status && typeof payload.source_status === 'object' ? payload.source_status : {};
      state.analysisNodeId = nodeId;
      renderNodeDetail(state.selectedNode);
    } catch (error) {
      if (nodeRequestId !== state.nodeRequest || analysisRequestId !== state.analysisRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysisSourceStatus = { available_evidence_levels: [], unavailable_reason: analysisErrorMessage(error) };
      state.analysisHistory = [];
      renderNodeDetail(state.selectedNode);
    }
  }

  function renderNodeGroupSelector(node) {
    const section = createElement('section', 'literature-map-node-group-section');
    section.append(createElement('h4', '', '人工分组'));
    const label = createElement('label', 'literature-map-node-group-label', '将此论文归入');
    const select = createElement('select');
    select.id = 'literature-map-node-group';
    select.setAttribute('aria-label', '论文人工分组');
    const none = createElement('option', '', '未分组');
    none.value = '';
    select.append(none);
    state.groups.forEach((group) => {
      const option = createElement('option', '', group.name);
      option.value = group.group_id;
      option.selected = group.group_id === node.group_id;
      option.dataset.color = group.color;
      select.append(option);
    });
    select.value = node.group_id || '';
    select.addEventListener('change', () => assignNodeGroup(node, select.value || null, select));
    label.append(select);
    section.append(label);
    return section;
  }

  function renderNodeColorControls() {
    const section = createElement('section', 'literature-map-node-color-section');
    section.append(createElement('h4', '', '节点外观'));
    section.append(createColorPalette('node'));
    return section;
  }

  async function assignNodeGroup(node, groupId, select) {
    if (!state.map?.map_id || !node?.node_id || !state.active) return;
    if (groupId && !groupById(groupId)) {
      setStatus('该分组不属于当前地图；请重新读取分组列表。', 'error');
      if (select) select.value = node.group_id || '';
      return;
    }
    const mapId = state.map.map_id;
    const requestId = ++state.groupRequest;
    const previousGroupId = node.group_id || null;
    if (select) select.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(node.node_id)}/group`, {
        method: 'PUT',
        body: JSON.stringify({ expected_revision: state.map.revision, group_id: groupId }),
      });
      if (requestId !== state.groupRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || state.selectedNodeId !== node.node_id || !state.active) return;
      const revision = Number(payload?.revision);
      if (Number.isInteger(revision)) state.map = { ...state.map, revision };
      const returnedNode = payload?.node && typeof payload.node === 'object' ? payload.node : null;
      state.selectedNode = returnedNode ? { ...state.selectedNode, ...returnedNode } : { ...state.selectedNode, group_id: groupId };
      const graphNode = normalizeNodes(state.graph).find((item) => item.node_id === node.node_id);
      if (graphNode) graphNode.group_id = groupId;
      renderGraph();
      renderNodeDetail(state.selectedNode);
      setStatus('论文分组已保存。', 'waiting');
    } catch (error) {
      if (requestId !== state.groupRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || state.selectedNodeId !== node.node_id || !state.active) return;
      if (select) select.disabled = false;
      if (error.status === 409 || String(error.code || '').toUpperCase() === 'MAP_REVISION_CONFLICT' || String(error.code || '').toLowerCase().includes('revision')) {
        if (select) select.value = previousGroupId || '';
        setStatus('地图版本已变化，正在重新读取；未覆盖其他操作。', 'error');
        await selectMap(mapId);
        return;
      }
      if (select) select.value = previousGroupId || '';
      setStatus(`论文分组保存失败：${errorAction(error, '请重新打开地图后重试。')}`, 'error');
    }
  }

  function renderNodeDetail(node) {
    if (!refs.detail) return;
    refs.detail.replaceChildren();
    if (!node) {
      refs.detail.append(createElement('p', 'literature-map-detail-empty', '点击图中的论文查看真实元数据。'));
      return;
    }
    if (node.loading) {
      refs.detail.append(createElement('p', 'literature-map-detail-state', '正在读取论文真实元数据…'));
      return;
    }
    if (node.error) {
      const error = createElement('p', 'literature-map-detail-error', node.error);
      error.setAttribute('role', 'alert');
      refs.detail.append(error);
      return;
    }
    const title = createElement('h3', 'literature-map-detail-title', metadataText(node.title, '标题未提供'));
    refs.detail.append(title);
    const status = createElement('div', 'literature-map-detail-status');
    const detailDownloadStatus = String(node.download_status || '').trim();
    const detailDocumentId = String(node.document_id ?? '').trim();
    const badgeStatus = detailDocumentId && (!detailDownloadStatus || detailDownloadStatus.toLowerCase() === 'not_imported')
      ? 'indexed'
      : (detailDownloadStatus || 'not_imported');
    status.append(renderStatusBadge(badgeStatus));
    refs.detail.append(status);
    const fields = createElement('dl', 'literature-map-detail-fields');
    [['作者', node.authors], ['年份', node.year], ['来源', node.venue], ['关键词', node.keywords], ['引用数', citationCountLabel(node)], ['依据', node.provenance?.basis || node.provenance]].forEach(([label, value]) => {
      const dt = createElement('dt', '', label);
      const dd = createElement('dd', '', metadataText(value));
      fields.append(dt, dd);
    });
    refs.detail.append(fields);
    const abstract = createElement('section', 'literature-map-detail-section');
    abstract.append(createElement('h4', '', '摘要'));
    abstract.append(createElement('p', '', metadataText(node.abstract)));
    refs.detail.append(abstract);
    refs.detail.append(renderNodeColorControls());
    refs.detail.append(renderNodeGroupSelector(node));
    const provenance = createElement('p', 'literature-map-provenance', `来源依据：${metadataText(node.provenance?.source || node.provenance)}`);
    refs.detail.append(provenance);
    const importDiagnostics = renderImportDiagnostics(node);
    if (importDiagnostics) {
      importDiagnostics.id = 'literature-map-import-diagnostics';
      refs.detail.append(importDiagnostics);
    }
    const actions = createElement('div', 'literature-map-detail-actions');
    const url = safeHttpUrl(node.source_url);
    if (url) {
      const link = createElement('a', 'secondary-button', '打开原文');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      actions.append(link);
    }
    const documentId = String(node.document_id ?? '').trim();
    const indexed = String(node.download_status || '').toLowerCase() === 'indexed' || Boolean(documentId);
    const removed = Boolean(node.removed || node.tombstone);
    if (indexed) {
      const linked = createElement('p', 'literature-map-document-link', documentId ? `已加入知识库 · 文档 ID：${documentId}` : '已加入知识库');
      refs.detail.append(linked);
      const knowledgeButton = createElement('button', 'secondary-button', '在知识库中查看');
      knowledgeButton.type = 'button';
      knowledgeButton.addEventListener('click', () => openKnowledgeBaseDocument(documentId));
      actions.append(knowledgeButton);
    }
    if (removed) {
      const restoreButton = createElement('button', 'secondary-button', '显式恢复');
      restoreButton.type = 'button';
      restoreButton.addEventListener('click', () => restoreNode(node.node_id, restoreButton));
      actions.append(restoreButton);
    } else if (!indexed) {
      const downloadStatus = String(node.download_status || '').toLowerCase();
      const diagnostics = nodeImportDiagnostics(node);
      const loginRecovery = downloadStatus === 'waiting_login';
      const knownImportStatuses = new Set(['not_imported', 'failed', ...IMPORT_PENDING_STATES]);
      const unknownImportRecovery = Boolean(downloadStatus) && !knownImportStatuses.has(downloadStatus) && !node.document_id;
      const importPending = IMPORT_PENDING_STATES.has(downloadStatus) && !loginRecovery;
      const blockedRetry = downloadStatus === 'failed' && diagnostics && !diagnostics.retryable;
      const importButton = createElement('button', 'send-button', loginRecovery || unknownImportRecovery
        ? '查看导入处理/登录处理'
        : (importPending ? '入库处理中' : (downloadStatus === 'failed' ? (diagnostics?.retryable ? '人工重试入库' : '人工重新提交入库') : '获取并加入知识库')));
      importButton.type = 'button';
      importButton.id = 'literature-map-import-button';
      importButton.disabled = !state.map?.map_id || !node.node_id || importPending || blockedRetry;
      if (blockedRetry) {
        importButton.setAttribute('aria-describedby', 'literature-map-import-diagnostics');
        importButton.title = '当前失败未标记为可重试；请使用入库诊断中的人工处理入口。';
      }
      importButton.addEventListener('click', () => {
        if (loginRecovery || unknownImportRecovery) openExistingImportRecovery();
        else importNode(node, importButton);
      });
      actions.append(importButton);
      const removeButton = createElement('button', 'secondary-button', '移出地图');
      removeButton.type = 'button';
      removeButton.addEventListener('click', () => removeNode(node.node_id, removeButton));
      actions.append(removeButton);
    }
    if (!removed) {
      const referencesButton = createElement('button', 'secondary-button', '参考文献');
      referencesButton.type = 'button';
      referencesButton.addEventListener('click', () => openPreview('references', node.node_id));
      const citationsButton = createElement('button', 'secondary-button', '引用它的论文');
      citationsButton.type = 'button';
      citationsButton.addEventListener('click', () => openPreview('citations', node.node_id));
      actions.append(referencesButton, citationsButton);
    }
    refs.detail.append(actions);
    const importStatus = createElement('p', 'literature-map-import-status');
    importStatus.id = 'literature-map-import-status';
    importStatus.setAttribute('role', 'status');
    const currentImportStatus = importStatusMessage(node);
    if (currentImportStatus) importStatus.textContent = currentImportStatus;
    refs.detail.append(importStatus);
    if (state.analysisNodeId === node.node_id) refs.detail.append(renderAnalysisPanel());
  }

  function scheduleAnalysisPoll(delay, mapId, nodeId, analysisId, requestId, generation) {
    if (!state.active || state.analysisPollGeneration !== generation) return;
    state.analysisPollTimer = window.setTimeout(() => pollAnalysis(mapId, nodeId, analysisId, requestId, generation), delay);
  }

  function resumeAnalysisPolling() {
    if (!state.active || !state.map?.map_id || !state.selectedNodeId || !state.analysis?.analysis_id || !['queued', 'running'].includes(state.analysis.status)) return;
    const mapId = state.map.map_id;
    const nodeId = state.selectedNodeId;
    const analysisId = state.analysis.analysis_id;
    stopAnalysisPolling();
    state.analysisPollExhausted = false;
    const generation = state.analysisPollGeneration;
    renderNodeDetail(state.selectedNode);
    scheduleAnalysisPoll(0, mapId, nodeId, analysisId, state.analysisRequest, generation);
  }

  async function pollAnalysis(mapId, nodeId, analysisId, requestId, generation) {
    if (!state.active || state.analysisPollInFlight || state.analysisPollGeneration !== generation) return;
    if (state.analysisPollAttempts >= MAX_ANALYSIS_POLL_ATTEMPTS) {
      if (requestId !== state.analysisRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId) return;
      state.analysisPollTimer = null;
      state.analysisPollExhausted = true;
      renderNodeDetail(state.selectedNode);
      return;
    }
    state.analysisPollInFlight = true;
    state.analysisPollAttempts += 1;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/analyses/${encodeURIComponent(analysisId)}`);
      if (requestId !== state.analysisRequest || generation !== state.analysisPollGeneration || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysis = payload.analysis || (payload.error ? { ...(state.analysis || {}), status: 'failed', error: payload.error } : state.analysis);
      state.analysisJob = payload.job || state.analysisJob;
      if (state.analysis?.status === 'completed' || state.analysis?.status === 'failed' || state.analysis?.status === 'stopped') {
        if (state.analysis?.status === 'completed') rememberCompletedAnalysis();
        if (state.analysis?.status === 'completed' && state.analysis?.evidence_level) state.analysisTab = state.analysis.evidence_level === 'full' ? 'full' : 'abstract';
        stopAnalysisPolling();
      } else {
        scheduleAnalysisPoll(1000, mapId, nodeId, analysisId, requestId, generation);
      }
      renderNodeDetail(state.selectedNode);
    } catch (error) {
      if (requestId !== state.analysisRequest || generation !== state.analysisPollGeneration || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysis = { ...(state.analysis || {}), status: 'failed', error: { code: error.code || 'MAP_ANALYSIS_READ_FAILED', message: analysisErrorMessage(error), retryable: true } };
      stopAnalysisPolling();
      renderNodeDetail(state.selectedNode);
    } finally {
      state.analysisPollInFlight = false;
    }
  }

  async function startAnalysis(evidenceLevel, options = {}) {
    if (!state.map?.map_id || !state.selectedNodeId || !analysisAvailable(evidenceLevel) || state.analysisSubmitInFlight || ['queued', 'running'].includes(state.analysis?.status)) return;
    const mapId = state.map.map_id;
    const nodeId = state.selectedNodeId;
    state.analysisSubmitInFlight = true;
    state.analysisManualRequest = Boolean(options.manual);
    rememberCompletedAnalysis();
    const requestId = ++state.analysisRequest;
    const generation = state.analysisPollGeneration + 1;
    stopAnalysisPolling();
    state.analysisPollGeneration = generation;
    state.analysisNodeId = nodeId;
    state.analysisViewedId = null;
    state.analysisPollExhausted = false;
    state.analysis = { analysis_id: null, map_id: mapId, node_id: nodeId, version: null, status: 'queued', evidence_level: evidenceLevel, source_version: analysisSourceVersion(state.analysisSourceStatus, evidenceLevel), result: null, error: null };
    state.analysisJob = null;
    renderNodeDetail(state.selectedNode);
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(nodeId)}/analyses`, {
        method: 'POST',
        body: JSON.stringify({ evidence_level: evidenceLevel, idempotency_key: makeIdempotencyKey() }),
      });
      if (requestId !== state.analysisRequest || generation !== state.analysisPollGeneration || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysis = payload.analysis || { ...(state.analysis || {}), analysis_id: payload.analysis_id, status: payload.status || 'queued', evidence_level: evidenceLevel, job_id: payload.job_id };
      if (state.analysis?.status === 'completed') state.analysisTab = evidenceLevel === 'full' ? 'full' : 'abstract';
      state.analysisJob = payload.job || null;
      renderNodeDetail(state.selectedNode);
      const analysisId = payload.analysis_id || state.analysis?.analysis_id;
      if (analysisId && !['completed', 'failed', 'stopped'].includes(state.analysis?.status)) scheduleAnalysisPoll(0, mapId, nodeId, analysisId, requestId, generation);
    } catch (error) {
      if (requestId !== state.analysisRequest || generation !== state.analysisPollGeneration || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysis = { ...(state.analysis || {}), status: 'failed', error: { code: error.code || 'MAP_ANALYSIS_REQUEST_FAILED', message: analysisErrorMessage(error), retryable: Boolean(error.retryable || error.status >= 500) } };
      renderNodeDetail(state.selectedNode);
    } finally {
      if (requestId === state.analysisRequest) {
        state.analysisSubmitInFlight = false;
        state.analysisManualRequest = false;
        renderNodeDetail(state.selectedNode);
      }
    }
  }

  function conversationDraft(node, evidenceLevel) {
    const title = String(node?.title || node?.node_id || '未命名论文');
    const authors = Array.isArray(node?.authors)
      ? node.authors.map((author) => String(author || '').trim()).filter(Boolean).join('、')
      : String(node?.authors || '').trim();
    const year = node?.year === null || node?.year === undefined || String(node.year).trim() === '' ? '年份未知' : String(node.year).trim();
    return [
      '请帮我解读这篇论文。',
      `标题：${title}`,
      `作者：${authors || '作者未知'}`,
      `年份：${year}`,
      '请重点回答：研究问题、方法、主要结论和局限。',
      `证据等级：${analysisEvidenceLabel(evidenceLevel)}`,
    ].join('\n');
  }

  function navigateToConversation(conversationId, options = {}) {
    if (!conversationId) return;
    if (typeof window.openConversationFromWorkspace === 'function') {
      window.openConversationFromWorkspace(conversationId, options);
      return;
    }
    if (typeof window.openExistingConversation === 'function') {
      window.openExistingConversation(conversationId, options);
      return;
    }
    const path = `/c/${encodeURIComponent(conversationId)}`;
    if (window.location.pathname !== path) window.history.pushState({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  async function createNodeConversation(evidenceLevel, button) {
    if (!state.map?.map_id || !state.selectedNodeId || !analysisAvailable(evidenceLevel)) return;
    if (state.conversationRequest > 0) {
      if (button) {
        button.disabled = true;
        button.textContent = '关于本篇提问（打开中…）';
        button.title = '正在打开论文会话；请等待当前请求完成。';
      }
      return;
    }
    const mapId = state.map.map_id;
    const nodeId = state.selectedNodeId;
    const requestId = ++state.conversationRequest;
    if (button) {
      button.disabled = true;
      button.textContent = '关于本篇提问（打开中…）';
      button.title = '正在打开论文会话；请等待当前请求完成。';
    }
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(nodeId)}/conversation`, {
        method: 'POST',
        body: JSON.stringify({ evidence_level: evidenceLevel, idempotency_key: makeIdempotencyKey() }),
      });
      if (requestId !== state.conversationRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      navigateToConversation(payload.conversation_id, { draft: conversationDraft(state.selectedNode, evidenceLevel), evidence_level: evidenceLevel });
    } catch (error) {
      if (requestId !== state.conversationRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      if (button) button.disabled = false;
      state.conversationRequest = 0;
      if (button) {
        button.textContent = '关于本篇提问';
        button.removeAttribute('title');
      }
      setStatus(`打开论文会话失败：${analysisErrorMessage(error)}`, 'error');
    }
  }

  function openKnowledgeBaseDocument(documentId) {
    if (typeof window.jumpToKnowledgeBase === 'function' && documentId) {
      window.jumpToKnowledgeBase(documentId);
      return;
    }
    const nav = document.querySelector('[data-view="kb"]');
    if (nav) nav.click();
  }

  function openExistingImportRecovery() {
    const nav = document.querySelector('[data-view="papers"]');
    if (nav) nav.click();
    window.requestAnimationFrame(() => {
      const progress = document.querySelector('#paper-import-panel');
      if (!progress || progress.hidden) return;
      progress.scrollIntoView({ block: 'center' });
      progress.querySelector('button:not([disabled])')?.focus();
    });
  }

  function revealImportDiagnostics() {
    const diagnostics = refs.detail?.querySelector('#literature-map-import-diagnostics');
    if (!diagnostics) return;
    diagnostics.scrollIntoView({ block: 'center' });
    diagnostics.setAttribute('tabindex', '-1');
    diagnostics.focus();
  }

  async function runNodeAction(action, nodeId, button) {
    if (!state.map?.map_id || !nodeId) return;
    const mapId = state.map.map_id;
    const requestId = ++state.nodeActionRequest;
    if (button) button.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(nodeId)}/${action}`, {
        method: 'POST',
        body: JSON.stringify({ expected_revision: state.map.revision, idempotency_key: makeIdempotencyKey() }),
      });
      if (requestId !== state.nodeActionRequest || mapId !== state.selectedMapId || !state.active) return;
      state.map = normalizeMap(payload.map) || state.map;
      setStatus(action === 'remove' ? '论文已移出当前地图；墓碑仍保留，只有显式恢复才会加入。' : '论文已显式恢复，正在补充当前地图关系。', 'waiting');
      await loadMapGraph(mapId);
      renderMapList();
    } catch (error) {
      if (requestId !== state.nodeActionRequest || mapId !== state.selectedMapId || !state.active) return;
      if (button) button.disabled = false;
      setStatus(`${action === 'remove' ? '移出地图' : '显式恢复'}失败：${errorAction(error, '请重新打开地图后重试。')}`, 'error');
    }
  }

  function removeNode(nodeId, button) { return runNodeAction('remove', nodeId, button); }

  function restoreNode(nodeId, button) { return runNodeAction('restore', nodeId, button); }

  async function importNode(node, button) {
    if (!state.map?.map_id || !node?.node_id) return;
    const currentStatus = String(node.download_status || '').toLowerCase();
    const diagnostics = nodeImportDiagnostics(node);
    if (state.importInFlightNodeId === node.node_id
      || IMPORT_PENDING_STATES.has(currentStatus)
      || (currentStatus === 'failed' && diagnostics && !diagnostics.retryable)) return;
    const mapId = state.map.map_id;
    const requestId = ++state.importRequest;
    state.importInFlightNodeId = node.node_id;
    if (button) button.disabled = true;
    const status = refs.detail.querySelector('#literature-map-import-status');
    if (status) status.textContent = '正在提交入库请求…';
    try {
      // The server-side node snapshot is authoritative.  Do not let a client
      // supplied URL replace the node's provenance during import.
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(node.node_id)}/imports`, { method: 'POST', body: JSON.stringify({}) });
      if (requestId !== state.importRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      state.selectedNode = mergeImportResponse(node, payload);
      renderNodeDetail(state.selectedNode);
      const renderedStatus = refs.detail.querySelector('#literature-map-import-status');
      if (renderedStatus) renderedStatus.textContent = importStatusMessage(state.selectedNode) || '入库请求已提交。';
    } catch (error) {
      if (requestId !== state.importRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      const transportMessage = error?.status
        ? `HTTP ${error.status}：${errorAction(error, '服务未接受入库请求。')}`
        : `请求未送达：${errorAction(error, '请确认服务已启动后重试。')}`;
      if (status) status.textContent = `入库请求失败（传输错误）：${transportMessage}`;
      if (button) button.disabled = false;
    } finally {
      if (state.importInFlightNodeId === node.node_id) state.importInFlightNodeId = null;
    }
  }

  function startPolling() {
    stopPolling();
    if (!state.active || !state.map?.map_id || !state.job?.job_id || TERMINAL_JOB_STATES.has(state.job.status)) return;
    state.pollAttempts = 0;
    schedulePoll(0);
  }

  function stopPolling() {
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
    state.pollInFlight = false;
    state.pollGeneration += 1;
  }

  function schedulePoll(delay) {
    if (!state.active || !state.map?.map_id || !state.job?.job_id) return;
    state.pollTimer = window.setTimeout(pollJob, delay);
  }

  async function pollJob() {
    if (!state.active || state.pollInFlight || !state.map?.map_id || !state.job?.job_id) return;
    if (state.pollAttempts >= MAX_POLL_ATTEMPTS) {
      setStatus('任务仍在后台运行；页面已停止自动轮询，重新打开此地图可继续查看。', 'waiting');
      return;
    }
    const generation = state.pollGeneration;
    const mapId = state.map.map_id;
    const jobId = state.job.job_id;
    const isCurrent = () => generation === state.pollGeneration
      && state.active
      && state.selectedMapId === mapId
      && state.map?.map_id === mapId
      && state.job?.job_id === jobId;
    state.pollInFlight = true;
    state.pollAttempts += 1;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/jobs/${encodeURIComponent(jobId)}`);
      if (!isCurrent()) return;
      await readEvents(mapId, jobId, generation);
      if (!isCurrent()) return;
      const previousStep = state.job.step;
      const previousStatus = state.job.status;
      state.job = payload.job || state.job;
      renderCurrentMeta();
      renderJobActions();
      const changed = previousStep !== state.job.step || previousStatus !== state.job.status;
      if (changed || state.pollAttempts === 1) await loadMapGraph(mapId);
      if (!isCurrent()) return;
      if (state.job.status === 'partial') setStatus('地图部分完成：已保留可用论文，失败阶段可稍后重试。', 'partial');
      else if (state.job.status === 'failed') setStatus('地图任务失败：已保留此前完成的节点，请检查来源配置后重试。', 'error');
      else if (state.job.status === 'stopped') setStatus('地图任务已停止；已保留停止前的成果。', 'waiting');
      else if (TERMINAL_JOB_STATES.has(state.job.status)) setStatus('地图已生成并保存，可点选节点查看详情。');
      else setStatus(`地图生成中：${stageLabel(state.job.step)}。已完成节点会逐步显示。`);
      if (!TERMINAL_JOB_STATES.has(state.job.status)) schedulePoll(1600);
    } catch (error) {
      if (!isCurrent()) return;
      setStatus(`状态读取失败：${errorAction(error, '请重新打开地图恢复状态查看。')}`, 'error');
      schedulePoll(3200);
    } finally {
      if (generation === state.pollGeneration) state.pollInFlight = false;
    }
  }

  async function readEvents(mapId = state.map?.map_id, jobId = state.job?.job_id, generation = state.pollGeneration) {
    if (!mapId || !jobId || generation !== state.pollGeneration || !state.active || state.selectedMapId !== mapId) return;
    const cursor = state.eventCursor;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/events?after_seq=${encodeURIComponent(cursor)}`);
      if (generation !== state.pollGeneration || !state.active || state.selectedMapId !== mapId || state.map?.map_id !== mapId || state.job?.job_id !== jobId) return;
      const events = Array.isArray(payload.events) ? payload.events : [];
      if (events.length) {
        const latest = events[events.length - 1];
        state.eventCursor = Number(payload.next_cursor || latest.event_seq || state.eventCursor) || state.eventCursor;
        const actionable = [...events].reverse().find((event) => event.error_code);
        if (actionable?.error_code === 'rate_limited' || actionable?.error_code === 'source_rate_limited') {
          setStatus('来源暂时限流，已保留当前成果；稍后可重新打开地图查看。', 'waiting');
        }
      }
    } catch (_) {
      // Job status remains authoritative; an unavailable optional event page
      // must not turn a usable map into a false failure.
    }
  }

  function setActive(active) {
    renderShell();
    const wasActive = state.active;
    const hadMap = Boolean(state.map);
    state.active = Boolean(active);
    if (state.active) {
      restoreDesktopPanelAccessibility();
      loadMaps().then(() => {
        // Re-entering the view re-reads the selected map/graph so a job that
        // finished while the user was elsewhere is immediately visible.
        if (!wasActive && hadMap && state.selectedMapId && state.map) {
          selectMap(state.selectedMapId);
        } else if (state.job && !TERMINAL_JOB_STATES.has(state.job.status)) {
          startPolling();
        }
        renderJobActions();
      });
    } else {
      closeAllMobilePanels(false);
      closeCreatePanel();
      stopPolling();
      stopAnalysisQueuePolling();
      stopPreviewPolling();
      window.clearTimeout(state.saveTimer);
      renderJobActions();
    }
  }

  window.LiteratureMaps = { setActive };
})();
