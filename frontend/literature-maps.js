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
  const MAX_LAYOUT_FRAMES = 8;
  const MAX_POLL_ATTEMPTS = 120;
  const MAX_PREVIEW_DISCOVERY_PAGES = 50;
  const MAX_MAP_NODES = 200;
  const MAX_PREVIEW_SELECTION = 20;
  const MAX_ANALYSIS_POLL_ATTEMPTS = 120;
  const TERMINAL_JOB_STATES = new Set(['completed', 'partial', 'failed', 'stopped']);
  const LAYER_NAMES = ['citation', 'similarity'];
  // Keep this allow-list aligned with catalog_adapter.py's canonical IDs.  In
  // particular, do not invent a Semantic Scholar spelling for map filters.
  const SUPPORTED_MAP_SOURCE_IDS = new Set(['usenix', 'dblp', 'ieee_sp', 'ccs', 'ndss', 'openalex', 'crossref']);
  const SUPPORTED_MAP_CONFERENCE_IDS = new Set(['usenix-security', 'ieee-sp', 'ccs', 'ndss']);
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const state = {
    active: false,
    mounted: false,
    maps: [],
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
    mapRequest: 0,
    viewRequest: 0,
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
    layoutFrames: 0,
    layoutScheduled: false,
    view: { x: 0, y: 0, scale: 1 },
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
    conversationRequest: 0,
  };

  const refs = {};

  function createElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
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

  function normalizeNodes(graph) {
    return Array.isArray(graph?.nodes) ? graph.nodes.filter((node) => node && node.node_id) : [];
  }

  function normalizeEdges(graph) {
    return Array.isArray(graph?.edges) ? graph.edges.filter((edge) => edge && edge.source_id && edge.target_id) : [];
  }

  function mapTitle(map) {
    return map?.name || map?.topic || '未命名地图';
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
    };
    return labels[status] || status || '未知状态';
  }

  function nodeLabel(node) {
    const authors = Array.isArray(node?.authors)
      ? node.authors.map((author) => String(author || '').trim()).filter(Boolean)
      : [];
    const author = authors[0] || (typeof node?.authors === 'string' ? node.authors.trim() : '');
    const year = node?.year === null || node?.year === undefined || String(node.year).trim() === '' ? '' : String(node.year);
    const shortLabel = [author, year].filter(Boolean).join(', ');
    return (shortLabel || node?.title || node?.node_id || '').slice(0, 38);
  }

  function renderStatusBadge(status) {
    const badge = createElement('span', 'literature-map-badge', mapStatusLabel(status));
    badge.dataset.status = status || '';
    return badge;
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
    [['literature-map-zoom-out', '−', '缩小'], ['literature-map-zoom-in', '+', '放大'], ['literature-map-fit', '适应', '适应画布'], ['literature-map-locate', '定位', '定位所选论文'], ['literature-map-reset', '重置', '重置视图']].forEach(([id, label, title]) => {
      const button = createElement('button', 'icon-button literature-map-tool', label);
      button.type = 'button';
      button.id = id;
      button.title = title;
      button.setAttribute('aria-label', title);
      tools.append(button);
    });
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
    canvasPanel.append(layerTools);
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
    canvasPanel.append(legend);
    const previewPanel = createElement('section', 'literature-map-preview-panel');
    previewPanel.id = 'literature-map-preview-panel';
    previewPanel.hidden = true;
    previewPanel.setAttribute('aria-live', 'polite');
    canvasPanel.append(previewPanel);

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
    mount.append(root);

    Object.assign(refs, { root, listSearch, listStatus, mapList, listEmpty, createPanel, form, topicInput, nameInput, yearStart: formGrid.children[0].querySelector('input'), yearEnd: formGrid.children[1].querySelector('input'), limitInput, sourceOptions, sourceNotice, conferenceOptions, conferenceNotice, projectInput, projectNotice, submitButton, cancelButton, currentTitle, currentMeta, svg, viewport, edgesGroup, nodesGroup, canvasEmpty: empty, detailPanel, detail, status: notice, count: listCount, continueButton, refreshPreviewButton, openSavedPreviewButton, stopJobButton, retryJobButton, previewPanel });
    bindEvents(newButton, refreshButton, closeDetail);
    state.mounted = true;
    renderMapList();
    renderGraph();
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
    refs.svg.addEventListener('pointercancel', handleCanvasPointerUp);
    refs.svg.addEventListener('click', (event) => {
      const nodeGroup = event.target.closest ? event.target.closest('[data-node-id]') : null;
      if (nodeGroup && nodeGroup.dataset.nodeId && !state.pointer?.dragged) selectNode(nodeGroup.dataset.nodeId);
    });
    refs.svg.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const nodeGroup = event.target.closest ? event.target.closest('[data-node-id]') : null;
      if (!nodeGroup?.dataset.nodeId) return;
      event.preventDefault();
      selectNode(nodeGroup.dataset.nodeId);
    });
    refs.root.querySelector('#literature-map-zoom-in').addEventListener('click', () => changeScale(1.2));
    refs.root.querySelector('#literature-map-zoom-out').addEventListener('click', () => changeScale(1 / 1.2));
    refs.root.querySelector('#literature-map-fit').addEventListener('click', () => fitView(true));
    refs.root.querySelector('#literature-map-locate').addEventListener('click', locateSelectedNode);
    refs.root.querySelector('#literature-map-reset').addEventListener('click', () => {
      state.view = { x: 0, y: 0, scale: 1 };
      renderGraph();
      scheduleViewSave();
    });
    refs.root.querySelectorAll('input[data-layer]').forEach((input) => {
      input.addEventListener('change', () => {
        state.layers[input.dataset.layer] = input.checked;
        renderGraph();
        scheduleViewSave();
      });
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
      renderGraph();
      renderNodeDetail(null);
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
      item.addEventListener('click', () => selectMap(map.map_id));
      refs.mapList.append(item);
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
      state.selectedNodeId = null;
      state.selectedNode = null;
      state.positions = Object.create(null);
      state.positionsDirty = false;
      closeCreatePanel();
      await loadMaps();
      if (requestId !== state.mapRequest || !state.active) return;
      if (state.selectedMapId) {
        await loadMapGraph(state.selectedMapId);
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
    const requestId = ++state.mapRequest;
    state.selectedMapId = mapId;
    state.selectedNodeId = null;
    state.selectedNode = null;
    state.map = null;
    state.graph = null;
    state.job = null;
    state.eventCursor = 0;
    state.positions = Object.create(null);
    state.positionsDirty = false;
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
    state.conversationRequest = 0;
    state.importRequest += 1;
    state.viewRequest += 1;
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
    renderMapList();
    renderNodeDetail(null);
    renderGraph();
    setStatus('正在读取已保存地图…');
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}`);
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      state.map = normalizeMap(payload.map);
      state.job = payload.latest_job || null;
      applySavedView(state.map);
      await loadMapGraph(mapId);
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      await restorePreviewForMap(mapId, requestId);
      renderMapList();
      if (state.job && !TERMINAL_JOB_STATES.has(state.job.status)) startPolling();
      const mapStatus = state.map?.status === 'partial' ? '地图部分完成；已保留可用节点并标注失败阶段。' : '地图已打开，图谱数据来自本地保存结果。';
      setStatus(state.previewDiscoveryNotice || mapStatus, state.previewDiscoveryNotice ? 'waiting' : (state.map?.status === 'partial' ? 'partial' : ''));
      renderJobActions();
    } catch (error) {
      if (requestId !== state.mapRequest || mapId !== state.selectedMapId || !state.active) return;
      setStatus(`打开地图失败：${errorAction(error, '请重新点击地图重试。')}`, 'error');
    }
  }

  function applySavedView(map) {
    const settings = map?.view_settings || {};
    const viewport = settings.viewport || {};
    state.view = {
      x: Number.isFinite(Number(viewport.x)) ? Number(viewport.x) : 0,
      y: Number.isFinite(Number(viewport.y)) ? Number(viewport.y) : 0,
      scale: Number.isFinite(Number(viewport.scale)) && Number(viewport.scale) > 0 ? Number(viewport.scale) : 1,
    };
    const layers = settings.layers || {};
    state.layers = { citation: layers.citation !== false, similarity: layers.similarity !== false };
    refs.root?.querySelectorAll('input[data-layer]').forEach((input) => { input.checked = state.layers[input.dataset.layer]; });
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
      const nodes = normalizeNodes(payload);
      nodes.forEach((node, index) => {
        if (node.position && Number.isFinite(Number(node.position.x)) && Number.isFinite(Number(node.position.y))) {
          state.positions[node.node_id] = { x: Number(node.position.x), y: Number(node.position.y) };
        } else if (!state.positions[node.node_id]) {
          state.positions[node.node_id] = initialPosition(index, nodes.length);
        }
      });
      refs.currentTitle.textContent = state.map ? mapTitle(state.map) : '文献地图';
      renderCurrentMeta();
      renderGraph();
      renderJobActions();
      if (nodes.length && nodes.some((node) => !node.position)) scheduleLayout();
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

  function scheduleLayout() {
    if (state.layoutScheduled || !state.graph || !normalizeNodes(state.graph).length) return;
    state.layoutScheduled = true;
    state.layoutFrames = 0;
    const frame = () => {
      state.layoutFrames += 1;
      const nodes = normalizeNodes(state.graph);
      nodes.forEach((node, index) => {
        if (node.position) return;
        const current = state.positions[node.node_id] || initialPosition(index, nodes.length);
        // A bounded, deterministic nudge keeps the first paint stable and avoids an unbounded force loop.
        const nudge = Math.min(12, state.layoutFrames * 1.5);
        state.positions[node.node_id] = { x: current.x + Math.cos(index) * nudge * 0.06, y: current.y + Math.sin(index) * nudge * 0.06 };
      });
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

  function positionFor(node, index, total) {
    return state.positions[node.node_id] || (node.position ? { x: Number(node.position.x), y: Number(node.position.y) } : initialPosition(index, total));
  }

  function renderGraph() {
    if (!refs.svg) return;
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
      const selected = node.node_id === state.selectedNodeId;
      const provenance = typeof node.provenance === 'string' ? node.provenance : node.provenance?.basis || '';
      setAttributes(group, { class: `literature-map-node${selected ? ' is-selected' : ''}`, 'data-node-id': node.node_id, 'data-provenance': provenance, tabindex: '0', role: 'button', 'aria-label': node.title || node.node_id });
      const circle = createSvgElement('circle');
      setAttributes(circle, { cx: point.x, cy: point.y, r: selected ? 11 : 8 });
      group.append(circle);
      if (selected || index % 25 === 0) {
        const label = createSvgElement('text');
        setAttributes(label, { x: point.x + 13, y: point.y + 4, class: 'literature-map-node-label' });
        label.textContent = nodeLabel(node);
        group.append(label);
      }
      refs.nodesGroup.append(group);
    });
    renderCurrentMeta();
  }

  function handleCanvasPointerDown(event) {
    const nodeGroup = event.target.closest ? event.target.closest('[data-node-id]') : null;
    state.pointer = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, nodeId: nodeGroup?.dataset.nodeId || null, dragged: false };
    refs.svg.setPointerCapture?.(event.pointerId);
  }

  function handleCanvasPointerMove(event) {
    const pointer = state.pointer;
    if (!pointer || pointer.pointerId !== event.pointerId) return;
    const dx = event.clientX - pointer.lastX;
    const dy = event.clientY - pointer.lastY;
    if (Math.abs(event.clientX - pointer.startX) + Math.abs(event.clientY - pointer.startY) > 3) pointer.dragged = true;
    pointer.lastX = event.clientX;
    pointer.lastY = event.clientY;
    if (pointer.nodeId) {
      const current = state.positions[pointer.nodeId];
      if (!current) return;
      state.positions[pointer.nodeId] = { x: current.x + dx / state.view.scale, y: current.y + dy / state.view.scale };
      state.positionsDirty = true;
    } else {
      state.view.x += dx;
      state.view.y += dy;
    }
    renderGraph();
  }

  function handleCanvasPointerUp(event) {
    if (!state.pointer || state.pointer.pointerId !== event.pointerId) return;
    const dragged = state.pointer.dragged;
    const nodeId = state.pointer.nodeId;
    state.pointer = null;
    refs.svg.releasePointerCapture?.(event.pointerId);
    if (dragged) scheduleViewSave();
    if (!dragged && nodeId) selectNode(nodeId);
  }

  function handleWheel(event) {
    if (!state.graph) return;
    event.preventDefault();
    changeScale(event.deltaY > 0 ? 1 / 1.1 : 1.1);
  }

  function changeScale(factor) {
    state.view.scale = Math.max(0.35, Math.min(2.8, state.view.scale * factor));
    renderGraph();
    scheduleViewSave();
  }

  function fitView(save) {
    const nodes = normalizeNodes(state.graph);
    if (!nodes.length) return;
    const points = nodes.map((node, index) => positionFor(node, index, nodes.length));
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y));
    const maxY = Math.max(...points.map((point) => point.y));
    const width = Math.max(180, maxX - minX + 100);
    const height = Math.max(150, maxY - minY + 100);
    state.view.scale = Math.max(0.35, Math.min(1.6, Math.min(MAP_WIDTH / width, MAP_HEIGHT / height)));
    state.view.x = (MAP_WIDTH - (minX + maxX) * state.view.scale) / 2;
    state.view.y = (MAP_HEIGHT - (minY + maxY) * state.view.scale) / 2;
    renderGraph();
    if (save) scheduleViewSave();
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
    renderGraph();
    scheduleViewSave();
  }

  function scheduleViewSave() {
    if (!state.map?.map_id || !state.active) return;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(saveView, 500);
  }

  async function saveView() {
    if (!state.map?.map_id || !state.active || (!state.positionsDirty && !state.graph)) return;
    const requestId = ++state.viewRequest;
    const mapId = state.map.map_id;
    const expectedRevision = state.map.revision;
    const positions = Object.entries(state.positions).map(([node_id, position]) => ({ node_id, x: Number(position.x), y: Number(position.y) })).filter((position) => Number.isFinite(position.x) && Number.isFinite(position.y));
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/view`, {
        method: 'PATCH',
        body: JSON.stringify({
          expected_revision: expectedRevision,
          positions,
          viewport: state.view,
          layers: state.layers,
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
      setStatus('视图已保存。');
      renderMapList();
      renderCurrentMeta();
    } catch (error) {
      if (requestId !== state.viewRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      state.positionsDirty = true;
      setStatus(`视图保存失败：${errorAction(error, '请重新打开地图后再保存。')}`, 'error');
    }
  }

  async function selectNode(nodeId) {
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
    stopAnalysisPolling();
    state.analysisRequest += 1;
    state.conversationRequest = 0;
    state.importRequest += 1;
    refs.detailPanel.hidden = false;
    refs.detailPanel.classList.add('is-open');
    renderGraph();
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

  function analysisStatusLabel(status) {
    const labels = { queued: '排队中', running: '生成中', completed: '已完成', failed: '失败', stopped: '已停止' };
    return labels[status] || status || '未生成';
  }

  function analysisEvidenceLabel(level) {
    return level === 'full' ? '全文索引片段依据' : '摘要级';
  }

  function analysisSourceVersion(status, level) {
    const versions = status?.source_versions && typeof status.source_versions === 'object' ? status.source_versions : {};
    return versions[level] || '';
  }

  function analysisAvailable(level) {
    const status = state.analysisSourceStatus || {};
    if (Array.isArray(status.available_evidence_levels)) return status.available_evidence_levels.includes(level);
    return level === 'full' ? Boolean(status.fulltext_ready) : Boolean(status.abstract_available);
  }

  function analysisUnavailableMessage(level) {
    if (level === 'abstract') return '缺少摘要，不能生成摘要级分析；请先获取摘要。';
    return state.analysisSourceStatus?.unavailable_reason || '全文索引尚未就绪；请先主动入库并等待索引完成。';
  }

  function analysisErrorMessage(error) {
    const code = String(error?.code || '').toUpperCase();
    if (code === 'MAP_ABSTRACT_UNAVAILABLE') return '缺少摘要，不能生成摘要级分析；请先获取摘要。';
    if (code === 'MAP_FULLTEXT_UNAVAILABLE') return '全文索引尚未就绪；请先主动入库并等待索引完成。';
    if (code === 'MAP_EVIDENCE_UNAVAILABLE') return '没有可引用的有效证据片段，暂不生成分析。';
    return error?.message || '分析失败，请稍后重试。';
  }

  function analysisRecords() {
    const records = Array.isArray(state.analysisHistory) ? state.analysisHistory.slice() : [];
    if (state.analysis?.analysis_id && !records.some((record) => record.analysis_id === state.analysis.analysis_id)) records.unshift(state.analysis);
    return records;
  }

  function analysisResultNode(record) {
    const result = record?.result;
    if (!result || typeof result !== 'object' || !String(result.summary || '').trim()) return null;
    const section = createElement('section', 'literature-map-analysis-result');
    const heading = createElement('h4', '', record.evidence_level === 'abstract' ? '摘要级分析结果（仅基于摘要）' : '全文分析结果（全文索引片段依据）');
    const meta = createElement('p', 'literature-map-analysis-result-meta', `依据：${analysisEvidenceLabel(record.evidence_level)} · 版本：${metadataText(record.source_version, '未提供')}`);
    const summary = createElement('p', 'literature-map-analysis-summary', String(result.summary));
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

  function renderAnalysisPanel() {
    const panel = createElement('section', 'literature-map-analysis');
    panel.setAttribute('aria-live', 'polite');
    panel.append(createElement('h4', 'literature-map-analysis-title', 'AI 分析与会话'));
    const sourceStatus = state.analysisSourceStatus || {};
    const available = Array.isArray(sourceStatus.available_evidence_levels) ? sourceStatus.available_evidence_levels : [];
    const sourceText = available.length ? `可用依据：${available.map(analysisEvidenceLabel).join('、')}` : '当前没有可用分析依据。';
    panel.append(createElement('p', 'literature-map-analysis-source', sourceText));
    if (sourceStatus.unavailable_reason) panel.append(createElement('p', 'literature-map-analysis-unavailable', String(sourceStatus.unavailable_reason)));
    const versions = sourceStatus.source_versions && typeof sourceStatus.source_versions === 'object' ? sourceStatus.source_versions : {};
    Object.entries(versions).forEach(([level, version]) => {
      panel.append(createElement('p', 'literature-map-analysis-version', `${analysisEvidenceLabel(level)}来源版本：${metadataText(version, '未提供')}`));
    });

    const actions = createElement('div', 'literature-map-analysis-actions');
    const abstractButton = createElement('button', 'send-button', '基于摘要分析');
    abstractButton.type = 'button';
    abstractButton.disabled = !analysisAvailable('abstract') || state.analysis?.status === 'queued' || state.analysis?.status === 'running';
    abstractButton.addEventListener('click', () => startAnalysis('abstract'));
    const fullButton = createElement('button', 'secondary-button', '基于全文分析');
    fullButton.type = 'button';
    fullButton.disabled = !analysisAvailable('full') || state.analysis?.status === 'queued' || state.analysis?.status === 'running';
    fullButton.addEventListener('click', () => startAnalysis('full'));
    actions.append(abstractButton, fullButton);

    const preferredLevel = state.analysis?.evidence_level || analysisRecords().find((record) => record?.status === 'completed')?.evidence_level || (analysisAvailable('abstract') ? 'abstract' : 'full');
    const conversationButton = createElement('button', 'secondary-button', '关于本篇提问');
    conversationButton.type = 'button';
    conversationButton.disabled = !analysisAvailable(preferredLevel) || state.conversationRequest > 0;
    conversationButton.addEventListener('click', () => createNodeConversation(preferredLevel, conversationButton));
    actions.append(conversationButton);
    panel.append(actions);

    const records = analysisRecords();
    if (records.length) {
      const history = createElement('ul', 'literature-map-analysis-history');
      records.forEach((record) => {
        const item = createElement('li', 'literature-map-analysis-history-item');
        const historyButton = createElement('button', 'literature-map-analysis-history-button', `v${metadataText(record.version, '—')} · ${analysisEvidenceLabel(record.evidence_level)} · ${analysisStatusLabel(record.status)} · ${metadataText(record.source_version, '无来源版本')}`);
        historyButton.type = 'button';
        historyButton.setAttribute('aria-pressed', state.analysisViewedId === record.analysis_id ? 'true' : 'false');
        historyButton.addEventListener('click', () => {
          state.analysisViewedId = record.analysis_id || null;
          renderNodeDetail(state.selectedNode);
        });
        item.append(historyButton);
        history.append(item);
      });
      panel.append(createElement('p', 'literature-map-analysis-history-title', '历史版本（可点击查看旧摘要）'), history);
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
        retry.addEventListener('click', () => startAnalysis(state.analysis.evidence_level || preferredLevel));
        panel.append(retry);
      }
    }
    const resultRecord = selectedAnalysisRecord(records);
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
    status.append(renderStatusBadge(node.download_status || 'not_imported'));
    refs.detail.append(status);
    const fields = createElement('dl', 'literature-map-detail-fields');
    [['作者', node.authors], ['年份', node.year], ['来源', node.venue], ['关键词', node.keywords], ['引用数', node.citation_count], ['依据', node.provenance?.basis || node.provenance]].forEach(([label, value]) => {
      const dt = createElement('dt', '', label);
      const dd = createElement('dd', '', metadataText(value));
      fields.append(dt, dd);
    });
    refs.detail.append(fields);
    const abstract = createElement('section', 'literature-map-detail-section');
    abstract.append(createElement('h4', '', '摘要'));
    abstract.append(createElement('p', '', metadataText(node.abstract)));
    refs.detail.append(abstract);
    const provenance = createElement('p', 'literature-map-provenance', `来源依据：${metadataText(node.provenance?.source || node.provenance)}`);
    refs.detail.append(provenance);
    const actions = createElement('div', 'literature-map-detail-actions');
    const url = safeHttpUrl(node.source_url);
    if (url) {
      const link = createElement('a', 'secondary-button', '打开原文');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      actions.append(link);
    }
    const documentId = node.document_id === null || node.document_id === undefined ? '' : String(node.document_id).trim();
    const indexed = String(node.download_status || '').toLowerCase() === 'indexed' || Boolean(node.document_id);
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
      const importButton = createElement('button', 'send-button', '加入知识库');
      importButton.type = 'button';
      importButton.id = 'literature-map-import-button';
      importButton.disabled = !state.map?.map_id || !node.node_id;
      importButton.addEventListener('click', () => importNode(node, importButton));
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

  async function startAnalysis(evidenceLevel) {
    if (!state.map?.map_id || !state.selectedNodeId || !analysisAvailable(evidenceLevel)) return;
    const mapId = state.map.map_id;
    const nodeId = state.selectedNodeId;
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
      state.analysisJob = payload.job || null;
      renderNodeDetail(state.selectedNode);
      const analysisId = payload.analysis_id || state.analysis?.analysis_id;
      if (analysisId && !['completed', 'failed', 'stopped'].includes(state.analysis?.status)) scheduleAnalysisPoll(0, mapId, nodeId, analysisId, requestId, generation);
    } catch (error) {
      if (requestId !== state.analysisRequest || generation !== state.analysisPollGeneration || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      state.analysis = { ...(state.analysis || {}), status: 'failed', error: { code: error.code || 'MAP_ANALYSIS_REQUEST_FAILED', message: analysisErrorMessage(error), retryable: Boolean(error.retryable || error.status >= 500) } };
      renderNodeDetail(state.selectedNode);
    }
  }

  function navigateToConversation(conversationId) {
    if (!conversationId) return;
    if (typeof window.openConversationFromWorkspace === 'function') {
      window.openConversationFromWorkspace(conversationId);
      return;
    }
    if (typeof window.openExistingConversation === 'function') {
      window.openExistingConversation(conversationId);
      return;
    }
    const path = `/c/${encodeURIComponent(conversationId)}`;
    if (window.location.pathname !== path) window.history.pushState({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  async function createNodeConversation(evidenceLevel, button) {
    if (!state.map?.map_id || !state.selectedNodeId || !analysisAvailable(evidenceLevel)) return;
    const mapId = state.map.map_id;
    const nodeId = state.selectedNodeId;
    const requestId = ++state.conversationRequest;
    if (button) button.disabled = true;
    try {
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(nodeId)}/conversation`, {
        method: 'POST',
        body: JSON.stringify({ evidence_level: evidenceLevel, idempotency_key: makeIdempotencyKey() }),
      });
      if (requestId !== state.conversationRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      navigateToConversation(payload.conversation_id);
    } catch (error) {
      if (requestId !== state.conversationRequest || mapId !== state.selectedMapId || state.selectedNodeId !== nodeId || state.map?.map_id !== mapId || !state.active) return;
      if (button) button.disabled = false;
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
    const mapId = state.map.map_id;
    const requestId = ++state.importRequest;
    button.disabled = true;
    const status = refs.detail.querySelector('#literature-map-import-status');
    if (status) status.textContent = '正在提交入库请求…';
    try {
      // The server-side node snapshot is authoritative.  Do not let a client
      // supplied URL replace the node's provenance during import.
      const payload = await request(`/${encodeURIComponent(mapId)}/nodes/${encodeURIComponent(node.node_id)}/imports`, { method: 'POST', body: JSON.stringify({}) });
      if (requestId !== state.importRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      const returnedStatus = payload?.status || payload?.import?.status || '已提交';
      if (status) status.textContent = `入库状态：${mapStatusLabel(returnedStatus)}。`;
      state.selectedNode = { ...node, download_status: returnedStatus };
      renderNodeDetail(state.selectedNode);
      const renderedStatus = refs.detail.querySelector('#literature-map-import-status');
      if (renderedStatus) renderedStatus.textContent = `入库状态：${mapStatusLabel(returnedStatus)}。`;
    } catch (error) {
      if (requestId !== state.importRequest || mapId !== state.selectedMapId || state.map?.map_id !== mapId || !state.active) return;
      if (status) status.textContent = `入库失败：${errorAction(error, '请检查登录或来源配置后重试。')}`;
      button.disabled = false;
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
      closeCreatePanel();
      stopPolling();
      stopPreviewPolling();
      window.clearTimeout(state.saveTimer);
      renderJobActions();
    }
  }

  window.LiteratureMaps = { setActive };
})();
