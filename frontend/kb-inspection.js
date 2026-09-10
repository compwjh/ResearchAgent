/*
 * Spec018 Task05-C: SourceBlock -> safe Markdown block.
 *
 * This module deliberately has no transport or interaction responsibilities.
 * The interaction layer owns those concerns and may mount the returned
 * block into the DOM after the caller has selected a document/version.
 */
(function attachKbInspectionRenderer(root) {
  'use strict';

  const REQUIRED_SOURCE_BLOCK_FIELDS = [
    'block_id',
    'ordinal',
    'text',
    'locator',
    'heading_path',
    'block_type',
  ];

  const SANITIZE_OPTIONS = {
    FORBID_TAGS: [
      'script', 'style', 'iframe', 'form', 'input', 'textarea', 'button',
      'object', 'embed', 'audio', 'video', 'source', 'link', 'meta',
    ],
    FORBID_ATTR: [
      'style', 'onerror', 'onload', 'onclick', 'onmouseover', 'onfocus',
      'onmouseenter', 'onkeydown', 'srcdoc',
    ],
  };

  const PDFJS_VERSION = '4.10.38';
  const PDFJS_MODULE_URL = '/assets/vendor/pdfjs/pdf.min.mjs?v=4.10.38';
  const PDFJS_WORKER_SRC = '/assets/vendor/pdfjs/pdf.worker.min.mjs?v=4.10.38';
  const PDFJS_MAIN_SHA256 = '27fc2a057a00f92a4334ad06e17dbd7259912954e9fb7f76400bcca5fd190a9c';
  const PDFJS_WORKER_SHA256 = '1baa1844c89c80a5b2797c916e75ab29254be46d8e9cb53cb6364d7aad84be36';
  const PDF_GET_DOCUMENT_OPTIONS = Object.freeze({
    isEvalSupported: false,
    enableXfa: false,
    useWorkerFetch: false,
    stopAtErrors: true,
    disableAutoFetch: true,
  });

  function pdfBaseUri(documentRef, rootScope) {
    const base = documentRef?.baseURI || rootScope?.location?.href;
    return typeof base === 'string' && base.trim() ? base : 'http://researchagent.invalid/';
  }

  function parsePdfWorkerUrl(value, documentRef, rootScope) {
    if (typeof value !== 'string' || !value.trim()) return null;
    try {
      return new URL(value, pdfBaseUri(documentRef, rootScope));
    } catch (_) {
      return null;
    }
  }

  // PDF.js may expose workerSrc as an absolute URL after receiving a relative
  // path. Compare URL semantics, not string spelling, while keeping the local
  // path, exact PDF.js version query and same-origin boundary fixed.
  function isAllowedPdfWorkerSource(value, documentRef, rootScope) {
    const expected = parsePdfWorkerUrl(PDFJS_WORKER_SRC, documentRef, rootScope);
    const candidate = parsePdfWorkerUrl(value, documentRef, rootScope);
    if (!expected || !candidate || candidate.hash) return false;
    return candidate.origin === expected.origin
      && candidate.pathname === expected.pathname
      && candidate.search === expected.search;
  }

  function resolvePdfWorkerSource(documentRef, rootScope) {
    const resolved = parsePdfWorkerUrl(PDFJS_WORKER_SRC, documentRef, rootScope);
    return resolved ? resolved.href : PDFJS_WORKER_SRC;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (character) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[character]));
  }

  function getDomDocument(options) {
    return options.document || root.document;
  }

  function getMarked(options) {
    return options.marked || root.marked;
  }

  function getPurify(options) {
    return options.DOMPurify || root.DOMPurify;
  }

  function validateSourceBlock(dto) {
    if (!dto || typeof dto !== 'object' || Array.isArray(dto)) {
      throw new TypeError('SourceBlock must be an object');
    }
    const missing = REQUIRED_SOURCE_BLOCK_FIELDS.filter((field) => !(field in dto));
    if (missing.length) {
      throw new TypeError(`SourceBlock missing: ${missing.join(', ')}`);
    }
    if (typeof dto.block_id !== 'string' || !dto.block_id.trim()) {
      throw new TypeError('SourceBlock.block_id must be a non-empty string');
    }
    if (!Number.isInteger(dto.ordinal) || dto.ordinal < 0) {
      throw new TypeError('SourceBlock.ordinal must be a non-negative integer');
    }
    if (typeof dto.text !== 'string') {
      throw new TypeError('SourceBlock.text must be a string');
    }
    if (!dto.locator || typeof dto.locator !== 'object' || Array.isArray(dto.locator)) {
      throw new TypeError('SourceBlock.locator must be an object');
    }
    return dto;
  }

  function notifyError(options, errorCode, detail) {
    if (typeof options.onError === 'function') {
      options.onError({ error_code: errorCode, detail: detail || null });
    }
  }

  function setAttribute(node, name, value) {
    node.setAttribute(name, String(value));
  }

  function metadataLabel(dto) {
    const heading = Array.isArray(dto.heading_path)
      ? dto.heading_path.join(' / ')
      : String(dto.heading_path ?? '');
    const type = String(dto.block_type ?? 'text');
    return heading ? `${type} · ${heading}` : type;
  }

  function createBlockContainer(dto, documentRef) {
    const block = documentRef.createElement('article');
    block.className = 'kb-source-block';
    setAttribute(block, 'data-block-id', dto.block_id);
    setAttribute(block, 'data-ordinal', dto.ordinal);
    setAttribute(block, 'role', 'article');
    setAttribute(block, 'aria-label', `原文块 ${dto.ordinal + 1}`);
    block.tabIndex = 0;

    const metadata = documentRef.createElement('p');
    metadata.className = 'kb-source-block-meta';
    metadata.textContent = metadataLabel(dto);
    block.appendChild(metadata);

    const body = documentRef.createElement('div');
    body.className = 'kb-source-block-body';
    block.appendChild(body);
    return { block, body };
  }

  function readImageAddress(image) {
    const src = image.getAttribute && image.getAttribute('src');
    const srcset = image.getAttribute && image.getAttribute('srcset');
    const alt = image.getAttribute && image.getAttribute('alt');
    return String(src || srcset || alt || '（无地址）').slice(0, 2048);
  }

  function replaceImages(node, documentRef) {
    if (!node) return;
    if (node.nodeType === 1 && String(node.tagName).toLowerCase() === 'img') {
      const placeholder = documentRef.createElement('span');
      placeholder.className = 'kb-image-placeholder';
      setAttribute(placeholder, 'role', 'img');
      setAttribute(placeholder, 'aria-label', '图片已阻止');
      placeholder.textContent = `图片已阻止：${readImageAddress(node)}`;
      if (typeof node.replaceWith === 'function') node.replaceWith(placeholder);
      else if (node.parentNode) node.parentNode.replaceChild(placeholder, node);
      return placeholder;
    }
    Array.from(node.childNodes || []).forEach((child) => replaceImages(child, documentRef));
    return node;
  }

  function appendSanitizedHtml(container, sanitizedHtml, documentRef, options) {
    let fragment;
    if (typeof options.parseSanitizedHtml === 'function') {
      fragment = options.parseSanitizedHtml(sanitizedHtml, documentRef);
    } else {
      const template = documentRef.createElement('template');
      // The only value assigned here is already returned by DOMPurify.
      template.innerHTML = sanitizedHtml;
      fragment = template.content;
    }
    if (!fragment) return;
    Array.from(fragment.childNodes || []).forEach((child) => {
      const mountedNode = replaceImages(child, documentRef);
      container.appendChild(mountedNode || child);
    });
  }

  function renderFallback(body, dto, options) {
    body.textContent = dto.text;
    setAttribute(body, 'data-renderer-status', 'fallback');
    setAttribute(body, 'data-error-code', 'RENDERER_UNAVAILABLE');
    notifyError(options, 'RENDERER_UNAVAILABLE', 'Marked or DOMPurify is unavailable');
  }

  function renderMarkdownBlock(sourceBlock, options = {}) {
    const dto = validateSourceBlock(sourceBlock);
    const documentRef = getDomDocument(options);
    if (!documentRef || typeof documentRef.createElement !== 'function') {
      throw new Error('A DOM document is required to render a SourceBlock');
    }

    const { block, body } = createBlockContainer(dto, documentRef);
    const marked = getMarked(options);
    const purify = getPurify(options);
    if (!marked || typeof marked.parse !== 'function' || !purify || typeof purify.sanitize !== 'function') {
      renderFallback(body, dto, options);
      return block;
    }

    const markedHtml = marked.parse(dto.text, { gfm: true, breaks: true });
    const sanitizedHtml = purify.sanitize(markedHtml, SANITIZE_OPTIONS);
    appendSanitizedHtml(body, sanitizedHtml, documentRef, options);
    setAttribute(body, 'data-renderer-status', 'ready');
    return block;
  }

  function elementById(documentRef, id) {
    return documentRef && typeof documentRef.getElementById === 'function'
      ? documentRef.getElementById(id)
      : null;
  }

  function childrenWithRole(element, role) {
    if (!element) return [];
    if (typeof element.querySelectorAll === 'function') {
      return Array.from(element.querySelectorAll(`[role="${role}"]`));
    }
    return Array.from(element.children || []).filter((child) => child.getAttribute?.('role') === role);
  }

  function setHidden(element, hidden) {
    if (element) element.hidden = Boolean(hidden);
  }

  function clearChildren(element) {
    if (!element) return;
    if (typeof element.replaceChildren === 'function') element.replaceChildren();
    else while (element.firstChild) element.removeChild(element.firstChild);
  }

  function retryAfterSeconds(response, payload) {
    const header = response && response.headers && response.headers.get
      ? Number(response.headers.get('Retry-After'))
      : NaN;
    const details = payload && payload.details ? Number(payload.details.retry_after_seconds) : NaN;
    const seconds = Number.isFinite(header) && header > 0 ? header : details;
    return Math.min(60, Math.max(1, Number.isFinite(seconds) && seconds > 0 ? seconds : 2));
  }

  function responseError(response, payload) {
    const body = payload && typeof payload === 'object' ? payload : {};
    const code = body.error_code || body.error?.error_code || `HTTP_${response?.status || 0}`;
    const message = body.message || body.error?.message || '请求暂时不可用';
    return { code: String(code), message: String(message), payload, status: response?.status || 0 };
  }

  function responseHeader(response, name) {
    return response?.headers?.get ? String(response.headers.get(name) || '') : '';
  }

  function createKbInspectionController(rootScope, options = {}) {
    const documentRef = options.document || rootScope.document;
    const fetchImpl = options.fetch || (rootScope.fetch && rootScope.fetch.bind(rootScope));
    const AbortControllerImpl = options.AbortController || rootScope.AbortController;
    const markedImpl = options.marked || rootScope.marked;
    const purifyImpl = options.DOMPurify || rootScope.DOMPurify;
    const renderer = options.renderer || { renderMarkdownBlock };
    const pdfjsLoader = options.pdfjsLoader || (() => import(PDFJS_MODULE_URL));
    const IntersectionObserverImpl = options.IntersectionObserver || rootScope.IntersectionObserver;
    const tablist = elementById(documentRef, 'kb-tabs');
    const inspectionTab = elementById(documentRef, 'kb-tab-inspection');
    const qaTab = elementById(documentRef, 'kb-tab-qa');
    const inspectionPanel = elementById(documentRef, 'kb-panel-inspection');
    const qaPanel = elementById(documentRef, 'kb-panel-qa');
    const documentSelect = elementById(documentRef, 'kb-inspection-document');
    const versionGroup = elementById(documentRef, 'kb-inspection-version-group');
    const maintenance = elementById(documentRef, 'kb-inspection-maintenance');
    const finalize = elementById(documentRef, 'kb-inspection-finalize');
    const loading = elementById(documentRef, 'kb-inspection-loading');
    const error = elementById(documentRef, 'kb-inspection-error');
    const sourceEmpty = elementById(documentRef, 'kb-source-empty');
    const sourceDocument = elementById(documentRef, 'kb-source-document');
    const sourceContent = elementById(documentRef, 'kb-source-content');
    const sourcePdf = elementById(documentRef, 'kb-source-pdf');
    const sourceMarkdown = elementById(documentRef, 'kb-source-markdown');
    const sourceMeta = elementById(documentRef, 'kb-source-meta');
    const sourceKind = elementById(documentRef, 'kb-source-kind');
    const chunkContent = elementById(documentRef, 'kb-chunk-content');
    const chunkEmpty = elementById(documentRef, 'kb-chunk-empty');
    const chunkLoadMore = elementById(documentRef, 'kb-chunk-load-more');
    const chunkMeta = elementById(documentRef, 'kb-chunk-meta');
    const chunkStatus = elementById(documentRef, 'kb-chunk-status');
    const layout = elementById(documentRef, 'kb-inspection-layout');
    const paneSwitcher = elementById(documentRef, 'kb-inspection-view-switcher');
    const state = {
      documentsLoaded: false,
      documentsPromise: null,
      documents: [],
      documentsCache: null,
      selectedDocument: null,
      selectedVersion: 'v1',
      inspectionCache: new Map(),
      inspectionManifest: null,
      sequence: 0,
      controller: null,
      pollTimer: null,
      pollResolve: null,
      pdfSession: null,
      chunkRows: [],
      chunkVisibleCount: 0,
      activeSelection: null,
      selectionToken: 0,
      paneScroll: { source: 0, chunks: 0 },
    };

    const CHUNK_BATCH_SIZE = 100;
    const INSPECTION_INITIAL_PAGE_SIZE = 500;

    function isActive(sequence) { return state.sequence === sequence; }

    function pdfFailure(code, message, cause) {
      const failure = new Error(message);
      failure.code = code;
      failure.cause = cause || null;
      return failure;
    }

    function mapPdfError(caught) {
      if (caught?.code) return caught.code;
      if (caught?.name === 'AbortException' || caught?.name === 'AbortError') return 'PDF_CANCELLED';
      const name = String(caught?.name || '').toLowerCase();
      const message = String(caught?.message || caught || '').toLowerCase();
      if (name.includes('invalidpdf') || name.includes('format') || name.includes('missingpdf')
        || message.includes('corrupt') || message.includes('invalid pdf')) return 'PDF_SOURCE_CORRUPT';
      if (name.includes('unexpectedresponse') || name.includes('responseexception')
        || message.includes('range') || message.includes('206') || message.includes('partial')) {
        return 'PDF_SOURCE_RANGE_ERROR';
      }
      if (message.includes('worker')) return 'PDFJS_WORKER_FAILED';
      return 'PDF_RENDER_FAILED';
    }

    function pdfErrorMessage(code) {
      return ({
        PDFJS_IMPORT_FAILED: 'PDF.js 本地模块加载失败。',
        PDFJS_VERSION_MISMATCH: 'PDF.js 版本不匹配。',
        PDFJS_WORKER_MISMATCH: 'PDF.js worker 来源不匹配。',
        PDFJS_WORKER_FAILED: 'PDF.js worker 启动失败。',
        PDF_SOURCE_RANGE_ERROR: 'PDF 分段读取失败。',
        PDF_SOURCE_CORRUPT: 'PDF 文件损坏或格式不可读。',
        PDF_CANCELLED: 'PDF 原文加载已取消。',
        PDF_RENDER_FAILED: 'PDF 原文渲染失败。',
      }[code] || 'PDF 原文暂时不可用。');
    }

    function cancelPdfSession() {
      const session = state.pdfSession;
      if (!session) return;
      session.cancelled = true;
      if (session.observer && typeof session.observer.disconnect === 'function') session.observer.disconnect();
      session.renderTasks.forEach((task) => {
        if (typeof task?.cancel === 'function') {
          try { task.cancel(); } catch (_) { /* cancellation is best effort */ }
        }
      });
      if (session.loadingTask) {
        const cancel = session.loadingTask.cancel || session.loadingTask.destroy;
        if (typeof cancel === 'function') {
          try { cancel.call(session.loadingTask); } catch (_) { /* cancellation is best effort */ }
        }
      }
      if (session.pdf && typeof session.pdf.destroy === 'function') {
        try { session.pdf.destroy(); } catch (_) { /* cancellation is best effort */ }
      }
      if (state.pdfSession === session) state.pdfSession = null;
    }

    function cancelPending() {
      state.sequence += 1;
      state.selectionToken += 1;
      cancelPdfSession();
      state.documentsPromise = null;
      if (state.pollTimer !== null) {
        (rootScope.clearTimeout || clearTimeout)(state.pollTimer);
        state.pollTimer = null;
      }
      if (state.pollResolve) {
        state.pollResolve();
        state.pollResolve = null;
      }
      if (state.controller && typeof state.controller.abort === 'function') state.controller.abort();
      state.controller = null;
    }

    function beginRequest() {
      cancelPending();
      state.controller = typeof AbortControllerImpl === 'function' ? new AbortControllerImpl() : null;
      return { sequence: state.sequence, signal: state.controller?.signal };
    }

    function resetStates() {
      setHidden(maintenance, true);
      setHidden(finalize, true);
      setHidden(loading, true);
      setHidden(error, true);
      if (inspectionPanel) inspectionPanel.setAttribute('aria-busy', 'false');
    }

    function showLoading(message = '正在加载检查清单…') {
      resetStates();
      if (loading) loading.textContent = message;
      setHidden(loading, false);
      if (inspectionPanel) inspectionPanel.setAttribute('aria-busy', 'true');
    }

    function showError(errorValue) {
      resetStates();
      if (error) {
        error.textContent = `${errorValue.code}：${errorValue.message}`;
        error.setAttribute('data-error-code', errorValue.code);
      }
      setHidden(error, false);
    }

    function showMaintenance(code) {
      resetStates();
      const target = code === 'INDEX_FINALIZE_REQUIRED' ? finalize : maintenance;
      if (target) {
        target.textContent = code === 'INDEX_FINALIZE_REQUIRED'
          ? '索引正在完成切换，检查器暂时只读。'
          : '索引正在维护，管理员完成全库重建后才能检查文档。';
        target.setAttribute('data-error-code', code);
      }
      setHidden(target, false);
    }

    function clearInspectionView() {
      setHidden(sourceEmpty, false);
      setHidden(sourceDocument, true);
      setHidden(chunkEmpty, false);
      clearChildren(sourcePdf);
      clearChildren(sourceMarkdown);
      clearChildren(chunkContent);
      if (chunkEmpty) chunkContent?.appendChild(chunkEmpty);
      state.chunkRows = [];
      state.chunkVisibleCount = 0;
      state.activeSelection = null;
      state.selectionToken += 1;
      state.inspectionManifest = null;
      setHidden(chunkLoadMore, true);
      if (sourceMeta) sourceMeta.textContent = '尚未选择文档';
      if (sourceKind) sourceKind.textContent = 'PDF / Markdown';
      if (chunkMeta) chunkMeta.textContent = '未选择 v1 / v2';
      if (chunkStatus) chunkStatus.textContent = '等待检查';
    }

    function activateTab(target, focus = false) {
      const tabs = childrenWithRole(tablist, 'tab');
      if (!tabs.includes(target)) return;
      tabs.forEach((tab) => {
        const selected = tab === target;
        tab.setAttribute('aria-selected', selected ? 'true' : 'false');
        tab.tabIndex = selected ? 0 : -1;
        const panel = elementById(documentRef, tab.getAttribute('aria-controls'));
        setHidden(panel, !selected);
      });
      if (focus && typeof target.focus === 'function') target.focus();
      if (target === inspectionTab) {
        loadDocuments();
      } else {
        cancelPending();
      }
    }

    function moveTab(event, tabs, current) {
      const index = tabs.indexOf(current);
      if (index < 0) return;
      let nextIndex = index;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') nextIndex = 0;
      if (event.key === 'End') nextIndex = tabs.length - 1;
      if (nextIndex === index) return;
      event.preventDefault();
      activateTab(tabs[nextIndex], true);
    }

    function bindPrimaryTabs() {
      if (!tablist) return;
      childrenWithRole(tablist, 'tab').forEach((tab) => {
        tab.addEventListener('click', () => activateTab(tab));
        tab.addEventListener('keydown', (event) => {
          const tabs = childrenWithRole(tablist, 'tab');
          if (['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            moveTab(event, tabs, tab);
          } else if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activateTab(tab);
          }
        });
      });
    }

    function activatePane(target, focus = false) {
      if (!layout || !target) return;
      const pane = target.dataset?.paneTarget || target.getAttribute('data-pane-target');
      if (pane !== 'source' && pane !== 'chunks') return;
      ['source', 'chunks'].forEach((paneName) => {
        const paneElement = elementById(documentRef, paneName === 'source' ? 'kb-source-content' : 'kb-chunk-content');
        if (paneElement) state.paneScroll[paneName] = paneElement.scrollTop || 0;
      });
      layout.setAttribute('data-active-pane', pane);
      const tabs = childrenWithRole(paneSwitcher, 'tab');
      tabs.forEach((tab) => {
        const selected = tab === target;
        tab.setAttribute('aria-selected', selected ? 'true' : 'false');
        tab.tabIndex = selected ? 0 : -1;
      });
      const nextPane = elementById(documentRef, pane === 'source' ? 'kb-source-content' : 'kb-chunk-content');
      if (nextPane) nextPane.scrollTop = state.paneScroll[pane] || 0;
      if (focus && typeof target.focus === 'function') target.focus();
    }

    function bindPaneTabs() {
      if (!paneSwitcher) return;
      childrenWithRole(paneSwitcher, 'tab').forEach((tab) => {
        tab.addEventListener('click', () => activatePane(tab));
        tab.addEventListener('keydown', (event) => {
          const tabs = childrenWithRole(paneSwitcher, 'tab');
          if (['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            const index = tabs.indexOf(tab);
            let next = index;
            if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % tabs.length;
            if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length;
            if (event.key === 'Home') next = 0;
            if (event.key === 'End') next = tabs.length - 1;
            event.preventDefault();
            activatePane(tabs[next], true);
          } else if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activatePane(tab);
          }
        });
      });
    }

    function setActiveState(node, active) {
      if (!node) return;
      node.setAttribute('data-active', active ? 'true' : 'false');
      node.setAttribute('aria-current', active ? 'true' : 'false');
    }

    function sourceNodes() {
      const nodes = [];
      [sourceMarkdown, sourcePdf].forEach((container) => {
        if (!container || typeof container.querySelectorAll !== 'function') return;
        nodes.push(...Array.from(container.querySelectorAll('[data-block-id]')));
      });
      return nodes;
    }

    function chunkNodes() {
      return chunkContent && typeof chunkContent.querySelectorAll === 'function'
        ? Array.from(chunkContent.querySelectorAll('[data-chunk-id]'))
        : [];
    }

    function chunkRowForNode(node) {
      const chunkId = String(node?.getAttribute?.('data-chunk-id') || '');
      return state.chunkRows.find((row) => row.chunkId === chunkId) || null;
    }

    function sourcePriority(node, relationByBlock) {
      const relation = relationByBlock.get(String(node.getAttribute('data-block-id') || ''));
      return relation ? [relation.is_primary ? 0 : 1, -relation.coverage] : [2, 0];
    }

    function clearHighlights() {
      sourceNodes().forEach((node) => setActiveState(node, false));
      chunkNodes().forEach((node) => setActiveState(node, false));
    }

    function scrollAndFocus(node, pane) {
      if (!node) return;
      const paneTab = pane === 'chunks'
        ? elementById(documentRef, 'kb-inspection-chunk-tab')
        : elementById(documentRef, 'kb-inspection-source-tab');
      if (paneTab) activatePane(paneTab);
      if (typeof node.scrollIntoView === 'function') node.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      if (typeof node.focus === 'function') node.focus({ preventScroll: true });
    }

    function bindActivatable(node, callback) {
      if (!node || node.__kbInspectionInteractionBound) return;
      node.__kbInspectionInteractionBound = true;
      node.addEventListener('click', () => callback());
      node.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        callback();
      });
    }

    function selectFromBlock(blockId) {
      const normalizedId = String(blockId || '');
      if (!normalizedId) return;
      const token = state.selectionToken + 1;
      state.selectionToken = token;
      clearHighlights();
      const matchingSource = sourceNodes().filter((node) => node.getAttribute('data-block-id') === normalizedId);
      matchingSource.forEach((node) => setActiveState(node, true));
      state.activeSelection = { type: 'block', ids: [normalizedId] };
      (async () => {
        const totalMatches = state.chunkRows.filter((row) => row.blockIds.includes(normalizedId)).length;
        while (state.chunkVisibleCount < state.chunkRows.length
          && chunkNodes().filter((node) => String(node.getAttribute('data-block-ids') || '').split(/\s+/).includes(normalizedId)).length < totalMatches) {
          renderChunkBatch();
        }
        if (token !== state.selectionToken) return;
        const matchingChunks = chunkNodes().filter((node) => String(node.getAttribute('data-block-ids') || '').split(/\s+/).includes(normalizedId));
        matchingChunks.sort((left, right) => {
          const leftRow = chunkRowForNode(left);
          const rightRow = chunkRowForNode(right);
          const leftRelation = leftRow?.anchorRelations.find((anchor) => anchor.block_id === normalizedId);
          const rightRelation = rightRow?.anchorRelations.find((anchor) => anchor.block_id === normalizedId);
          const leftScore = leftRelation ? [leftRelation.is_primary ? 0 : 1, -leftRelation.coverage] : [2, 0];
          const rightScore = rightRelation ? [rightRelation.is_primary ? 0 : 1, -rightRelation.coverage] : [2, 0];
          return leftScore[0] - rightScore[0] || leftScore[1] - rightScore[1];
        });
        matchingChunks.forEach((node) => setActiveState(node, true));
        scrollAndFocus(matchingChunks[0], 'chunks');
      })();
    }

    function selectFromChunk(chunkNode) {
      if (!chunkNode) return;
      const token = state.selectionToken + 1;
      state.selectionToken = token;
      const ids = String(chunkNode.getAttribute('data-block-ids') || '').split(/\s+/).filter(Boolean);
      clearHighlights();
      setActiveState(chunkNode, true);
      state.activeSelection = { type: 'chunk', ids };
      (async () => {
        try {
          const session = state.pdfSession;
          const pages = session && ids.length
            ? [...new Set(ids.map((id) => session.blockPages.get(id)).filter((pageNumber) => Number.isInteger(pageNumber)))]
            : [];
          if (session && pages.length) {
            await Promise.all(pages.map((pageNumber) => renderPdfPage(session, pageNumber, session.pageShells.get(pageNumber))));
          }
          if (token !== state.selectionToken) return;
          const row = chunkRowForNode(chunkNode);
          const relationByBlock = new Map((row?.anchorRelations || []).map((anchor) => [anchor.block_id, anchor]));
          const matchingSource = sourceNodes().filter((node) => ids.includes(String(node.getAttribute('data-block-id') || '')));
          matchingSource.sort((left, right) => {
            const leftScore = sourcePriority(left, relationByBlock);
            const rightScore = sourcePriority(right, relationByBlock);
            return leftScore[0] - rightScore[0] || leftScore[1] - rightScore[1];
          });
          matchingSource.forEach((node) => setActiveState(node, true));
          scrollAndFocus(matchingSource[0], 'source');
        } catch (caught) {
          if (token !== state.selectionToken) return;
          const code = mapPdfError(caught);
          showError({ code, message: pdfErrorMessage(code) });
        }
      })();
    }

    function bindSourceInteraction(node) {
      bindActivatable(node, () => selectFromBlock(node.getAttribute('data-block-id')));
      setActiveState(node, false);
    }

    function bindChunkInteraction(node) {
      bindActivatable(node, () => selectFromChunk(node));
      setActiveState(node, false);
    }

    function renderDocumentOptions(documents) {
      if (!documentSelect) return;
      clearChildren(documentSelect);
      const placeholder = documentRef.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '选择知识文档';
      documentSelect.appendChild(placeholder);
      documents.forEach((documentValue) => {
        const option = documentRef.createElement('option');
        const documentId = String(documentValue.document_id || '');
        option.value = documentId;
        option.textContent = `${String(documentValue.file_name || '未命名文档')} · ${String(documentValue.media_type || '未知格式')}`;
        documentSelect.appendChild(option);
      });
      documentSelect.value = state.selectedDocument?.document_id || '';
    }

    async function readJson(response) {
      try { return await response.json(); } catch (_) { return {}; }
    }

    async function loadDocuments(force = false) {
      if (state.documentsLoaded && !force) return state.documents;
      if (state.documentsPromise) return state.documentsPromise;
      if (typeof fetchImpl !== 'function') {
        showError({ code: 'NETWORK_UNAVAILABLE', message: '文档列表服务不可用' });
        return [];
      }
      const request = beginRequest();
      showLoading('正在加载知识文档…');
      state.documentsPromise = (async () => {
        try {
          const documents = [];
          let cursor = null;
          let pageCount = 0;
          let lastEtag = state.documentsCache?.etag || null;
          do {
            if (!isActive(request.sequence)) return [];
            const params = new URLSearchParams({ limit: '100' });
            if (cursor) params.set('cursor', cursor);
            const url = `/api/kb/documents?${params.toString()}`;
            const headers = !cursor && state.documentsCache?.etag
              ? { 'If-None-Match': state.documentsCache.etag }
              : undefined;
            const response = await fetchImpl(url, { signal: request.signal, ...(headers ? { headers } : {}) });
            const payload = await readJson(response);
            if (!isActive(request.sequence)) return [];
            if (response.status === 304) {
              if (!state.documentsCache) {
                showError({ code: 'DOCUMENT_CACHE_MISS_304', message: '文档列表缓存不可用，无法处理 304。' });
                return [];
              }
              documents.push(...state.documentsCache.documents);
              cursor = null;
              break;
            }
            if (response.status !== 200) {
              const failure = responseError(response, payload);
              if (failure.code === 'INDEX_FINALIZE_REQUIRED') showMaintenance(failure.code);
              else if (failure.code === 'INDEX_REBUILD_REQUIRED') showMaintenance(failure.code);
              else showError(failure);
              return [];
            }
            if (Array.isArray(payload.documents)) documents.push(...payload.documents);
            lastEtag = responseHeader(response, 'ETag') || lastEtag;
            cursor = payload.next_cursor || null;
            pageCount += 1;
            if (pageCount > 1000) {
              showError({ code: 'PAGINATION_LIMIT', message: '文档列表分页超过安全上限' });
              return [];
            }
            if (cursor) showLoading(`正在加载文档列表第 ${pageCount + 1} 页…`);
          } while (cursor);
          state.documents = documents;
          state.documentsCache = {
            documents: documents.slice(),
            etag: lastEtag,
          };
          state.documentsLoaded = true;
          renderDocumentOptions(state.documents);
          resetStates();
          return state.documents;
        } catch (caught) {
          if (caught?.name === 'AbortError' || !isActive(request.sequence)) return [];
          showError({ code: 'NETWORK_ERROR', message: '文档列表加载失败' });
          return [];
        } finally {
          state.documentsPromise = null;
        }
      })();
      return state.documentsPromise;
    }

    function selectedVersion() {
      const selected = versionGroup?.querySelector('input[name="kb-inspection-chunker"]:checked');
      return selected?.value || state.selectedVersion || 'v1';
    }

    function anchorKey(anchor, version) {
      return `${anchor?.chunker || version}:${anchor?.chunk_index}`;
    }

    function clampUnit(value) {
      return Math.min(1, Math.max(0, Number.isFinite(Number(value)) ? Number(value) : 0));
    }

    function appendPdfTextLayer(textLayer, textContent) {
      const items = Array.isArray(textContent?.items) ? textContent.items : [];
      items.forEach((item) => {
        const span = documentRef.createElement('span');
        span.className = 'kb-pdf-text';
        span.textContent = String(item?.str || '');
        textLayer.appendChild(span);
      });
    }

    function appendPdfBlockOverlays(overlay, pageNumber, viewport, blocks) {
      blocks.forEach((block) => {
        const locator = block?.locator;
        if (!locator || locator.kind !== 'pdf_bbox' || Number(locator.page) !== pageNumber) return;
        const bbox = Array.isArray(locator.bbox) && locator.bbox.length === 4
          ? locator.bbox.map(clampUnit)
          : null;
        if (!bbox) return;
        const left = Math.min(bbox[0], bbox[2]);
        const right = Math.max(bbox[0], bbox[2]);
        const top = Math.min(bbox[1], bbox[3]);
        const bottom = Math.max(bbox[1], bbox[3]);
        const blockOverlay = documentRef.createElement('div');
        blockOverlay.className = 'kb-pdf-source-block';
        blockOverlay.tabIndex = 0;
        blockOverlay.setAttribute('role', 'article');
        blockOverlay.setAttribute('data-block-id', String(block.block_id || ''));
        blockOverlay.setAttribute('aria-current', 'false');
        blockOverlay.setAttribute('aria-label', `原文块 ${Number(block.ordinal || 0) + 1}`);
        blockOverlay.style.left = `${left * 100}%`;
        blockOverlay.style.top = `${top * 100}%`;
        blockOverlay.style.width = `${(right - left) * 100}%`;
        blockOverlay.style.height = `${(bottom - top) * 100}%`;
        overlay.appendChild(blockOverlay);
        bindSourceInteraction(blockOverlay);
      });
      overlay.setAttribute('data-viewport-size', `${viewport.width}x${viewport.height}`);
    }

    function renderPdfPage(session, pageNumber, pageShell) {
      if (session.cancelled || !isActive(session.sequence) || !pageShell) return Promise.resolve();
      if (session.renderedPages.has(pageNumber)) return Promise.resolve();
      const pending = session.pageRenderPromises.get(pageNumber);
      if (pending) return pending;
      session.renderedPages.add(pageNumber);
      const renderPromise = (async () => {
        try {
          const page = await session.pdf.getPage(pageNumber);
          if (session.cancelled || !isActive(session.sequence)) return;
          const viewport = page.getViewport({ scale: 1 });
          const canvas = pageShell.querySelector('.kb-pdf-canvas');
          const textLayer = pageShell.querySelector('.kb-pdf-text-layer');
          const overlay = pageShell.querySelector('.kb-pdf-overlay');
          if (!canvas || !textLayer || !overlay || typeof canvas.getContext !== 'function') {
            throw pdfFailure('PDF_RENDER_FAILED', 'PDF 页面容器不可用');
          }
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          pageShell.style.width = `${viewport.width}px`;
          pageShell.style.height = `${viewport.height}px`;
          const canvasContext = canvas.getContext('2d');
          if (!canvasContext) throw pdfFailure('PDF_RENDER_FAILED', 'PDF canvas 不可用');
          const textContent = await page.getTextContent();
          if (session.cancelled || !isActive(session.sequence)) return;
          appendPdfTextLayer(textLayer, textContent);
          appendPdfBlockOverlays(overlay, pageNumber, viewport, session.blocks);
          const renderTask = page.render({ canvasContext, viewport });
          session.renderTasks.add(renderTask);
          await renderTask.promise;
          session.renderTasks.delete(renderTask);
        } catch (caught) {
          session.renderedPages.delete(pageNumber);
          if (!session.cancelled && isActive(session.sequence)) throw caught;
        }
      })();
      session.pageRenderPromises.set(pageNumber, renderPromise);
      return renderPromise.finally(() => {
        if (session.pageRenderPromises.get(pageNumber) === renderPromise) session.pageRenderPromises.delete(pageNumber);
      });
    }

    async function loadPdfJsModule() {
      let moduleValue;
      try {
        moduleValue = await pdfjsLoader();
      } catch (caught) {
        throw pdfFailure('PDFJS_IMPORT_FAILED', 'PDF.js 本地模块加载失败', caught);
      }
      const pdfjs = moduleValue?.default || moduleValue;
      if (!pdfjs || typeof pdfjs.getDocument !== 'function') {
        throw pdfFailure('PDFJS_IMPORT_FAILED', 'PDF.js display API 不可用');
      }
      if (String(pdfjs.version || '') !== PDFJS_VERSION) {
        throw pdfFailure('PDFJS_VERSION_MISMATCH', 'PDF.js 版本不匹配');
      }
      if (pdfjs.mainSha256 && String(pdfjs.mainSha256) !== PDFJS_MAIN_SHA256) {
        throw pdfFailure('PDFJS_VERSION_MISMATCH', 'PDF.js 主库摘要不匹配');
      }
      if (!pdfjs.GlobalWorkerOptions
        || !['object', 'function'].includes(typeof pdfjs.GlobalWorkerOptions)) {
        throw pdfFailure('PDFJS_WORKER_MISMATCH', 'PDF.js worker 配置不可用');
      }
      if ((pdfjs.workerVersion && String(pdfjs.workerVersion) !== PDFJS_VERSION)
        || (pdfjs.workerSha256 && String(pdfjs.workerSha256) !== PDFJS_WORKER_SHA256)) {
        throw pdfFailure('PDFJS_WORKER_MISMATCH', 'PDF.js worker 版本或摘要不匹配');
      }
      const workerSrc = resolvePdfWorkerSource(documentRef, rootScope);
      if (!isAllowedPdfWorkerSource(workerSrc, documentRef, rootScope)) {
        throw pdfFailure('PDFJS_WORKER_MISMATCH', 'PDF.js worker 必须同源且版本正确');
      }
      pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
      if (!isAllowedPdfWorkerSource(pdfjs.GlobalWorkerOptions.workerSrc, documentRef, rootScope)) {
        throw pdfFailure('PDFJS_WORKER_MISMATCH', 'PDF.js worker 来源不匹配');
      }
      return pdfjs;
    }

    function createPdfPageShell(pageNumber) {
      const pageShell = documentRef.createElement('section');
      pageShell.className = 'kb-pdf-page';
      pageShell.setAttribute('data-page', pageNumber);
      pageShell.setAttribute('aria-label', `PDF 第 ${pageNumber} 页`);
      const canvas = documentRef.createElement('canvas');
      canvas.className = 'kb-pdf-canvas';
      canvas.setAttribute('aria-hidden', 'true');
      const textLayer = documentRef.createElement('div');
      textLayer.className = 'kb-pdf-text-layer';
      textLayer.setAttribute('aria-label', `PDF 第 ${pageNumber} 页文本`);
      const overlay = documentRef.createElement('div');
      overlay.className = 'kb-pdf-overlay';
      overlay.setAttribute('aria-label', `PDF 第 ${pageNumber} 页原文块`);
      pageShell.append(canvas, textLayer, overlay);
      return pageShell;
    }

    async function renderPdfSource(documentValue, blocks, sequence) {
      const session = {
        sequence,
        blocks,
        cancelled: false,
        loadingTask: null,
        pdf: null,
        observer: null,
        renderTasks: new Set(),
        renderedPages: new Set(),
        pageRenderPromises: new Map(),
        pageShells: new Map(),
        blockPages: new Map(),
      };
      cancelPdfSession();
      state.pdfSession = session;
      const documentId = String(documentValue?.document_id || '');
      const sourceUrl = `/api/kb/documents/${encodeURIComponent(documentId)}/source`;
      try {
        const pdfjs = await loadPdfJsModule();
        if (session.cancelled || !isActive(sequence)) return;
        session.loadingTask = pdfjs.getDocument({ url: sourceUrl, ...PDF_GET_DOCUMENT_OPTIONS });
        if (!session.loadingTask || !session.loadingTask.promise) {
          throw pdfFailure('PDF_RENDER_FAILED', 'PDF.js 加载任务不可用');
        }
        session.pdf = await session.loadingTask.promise;
        if (session.cancelled || !isActive(sequence)) return;
        const numPages = Number(session.pdf?.numPages || 0);
        if (!Number.isInteger(numPages) || numPages < 1) {
          throw pdfFailure('PDF_SOURCE_CORRUPT', 'PDF 没有可显示页面');
        }
        const pageShells = [];
        for (let pageNumber = 1; pageNumber <= numPages; pageNumber += 1) {
          const pageShell = createPdfPageShell(pageNumber);
          pageShells.push({ pageNumber, pageShell });
          session.pageShells.set(pageNumber, pageShell);
          sourcePdf.appendChild(pageShell);
        }
        blocks.forEach((block) => {
          const blockId = String(block?.block_id || '');
          const pageNumber = Number(block?.locator?.page);
          if (blockId && Number.isInteger(pageNumber) && pageNumber >= 1 && pageNumber <= numPages) {
            session.blockPages.set(blockId, pageNumber);
          }
        });
        if (typeof IntersectionObserverImpl === 'function') {
          session.observer = new IntersectionObserverImpl((entries) => {
            entries.forEach((entry) => {
              if (!entry?.isIntersecting || session.cancelled) return;
              const pageNumber = Number(entry.target?.getAttribute('data-page'));
              const pageShell = entry.target;
              renderPdfPage(session, pageNumber, pageShell).catch((caught) => {
                if (!session.cancelled && isActive(sequence)) {
                  showError({ code: mapPdfError(caught), message: pdfErrorMessage(mapPdfError(caught)) });
                }
              });
            });
          }, { root: sourceContent || sourcePdf, rootMargin: '320px 0px' });
          pageShells.forEach(({ pageShell }) => session.observer.observe(pageShell));
        } else {
          for (const { pageNumber, pageShell } of pageShells) {
            await renderPdfPage(session, pageNumber, pageShell);
          }
        }
      } catch (caught) {
        if (session.cancelled || !isActive(sequence) || mapPdfError(caught) === 'PDF_CANCELLED') return;
        const code = mapPdfError(caught);
        showError({ code, message: pdfErrorMessage(code) });
        const placeholder = documentRef.createElement('p');
        placeholder.className = 'kb-inspection-empty';
        placeholder.textContent = `${code}：${pdfErrorMessage(code)}`;
        sourcePdf.appendChild(placeholder);
      }
    }

    async function renderSource(documentValue, blocks, sequence) {
      clearChildren(sourcePdf);
      clearChildren(sourceMarkdown);
      setHidden(sourceEmpty, blocks.length > 0);
      setHidden(sourceDocument, false);
      if (sourceMeta) sourceMeta.textContent = `${String(documentValue.file_name || '未命名文档')} · ${blocks.length} 个原文块`;
      if (sourceKind) sourceKind.textContent = documentValue.media_type === 'text/markdown' ? 'Markdown' : 'PDF';
      if (documentValue.media_type !== 'text/markdown') {
        setHidden(sourcePdf, false);
        setHidden(sourceMarkdown, true);
        await renderPdfSource(documentValue, blocks, sequence);
        return;
      }
      setHidden(sourcePdf, true);
      setHidden(sourceMarkdown, false);
      blocks.forEach((blockDto) => {
        try {
        const block = renderer.renderMarkdownBlock(blockDto, {
            document: documentRef,
            marked: markedImpl,
            DOMPurify: purifyImpl,
          });
          block.setAttribute('aria-current', 'false');
          bindSourceInteraction(block);
          sourceMarkdown.appendChild(block);
        } catch (caught) {
          const fallback = documentRef.createElement('p');
          fallback.textContent = '原文块无法渲染。';
          sourceMarkdown.appendChild(fallback);
        }
      });
    }

    function createChunkItem(row) {
      const { chunk, version, blockIds, anchorRelations, unmappedReason } = row;
      const chunkIndex = Number.isInteger(chunk.chunk_index) ? chunk.chunk_index : 0;
      const chunker = String(chunk.chunker || version);
      const chunkId = String(chunk.chunk_id || `${chunker}:${chunkIndex}`);
      const item = documentRef.createElement('article');
      item.className = 'kb-chunk-item';
      item.tabIndex = 0;
      item.setAttribute('role', 'listitem');
      item.setAttribute('data-chunk-id', chunkId);
      item.setAttribute('data-chunk-index', chunkIndex);
      item.setAttribute('data-block-ids', blockIds.join(' '));
      item.setAttribute('data-anchor-count', anchorRelations.length);
      if (unmappedReason) item.setAttribute('data-unmapped-reason', unmappedReason);
      const primary = anchorRelations.find((anchor) => anchor.is_primary && anchor.block_id);
      if (primary) item.setAttribute('data-primary-block-id', primary.block_id);
      item.setAttribute('aria-current', 'false');
      item.setAttribute('aria-label', `切片 ${chunkIndex + 1}`);
      const meta = documentRef.createElement('p');
      meta.className = 'kb-chunk-meta';
      meta.textContent = `${chunker} · #${chunkIndex}${chunk.section ? ` · ${String(chunk.section)}` : ''}`;
      const text = documentRef.createElement('p');
      text.className = 'kb-chunk-text';
      text.textContent = String(chunk.text || '');
      const mapping = documentRef.createElement('p');
      mapping.className = unmappedReason ? 'kb-chunk-warning' : 'kb-chunk-mapping';
      mapping.setAttribute('role', 'status');
      mapping.textContent = unmappedReason
        ? `未映射：${unmappedReason}`
        : anchorRelations.map((anchor) => `${anchor.block_id} · coverage ${anchor.coverage} · ${anchor.is_primary ? '主定位' : '关联'}`).join('；');
      item.append(meta, text, mapping);
      bindChunkInteraction(item);
      return item;
    }

    function renderChunkBatch() {
      if (!chunkContent) return;
      const start = state.chunkVisibleCount;
      const end = Math.min(state.chunkRows.length, start + CHUNK_BATCH_SIZE);
      for (let index = start; index < end; index += 1) {
        chunkContent.appendChild(createChunkItem(state.chunkRows[index]));
      }
      state.chunkVisibleCount = end;
      setHidden(chunkEmpty, state.chunkRows.length > 0);
      if (chunkLoadMore) {
        chunkLoadMore.textContent = state.chunkVisibleCount < state.chunkRows.length ? '加载更多切片' : '已加载全部切片';
        setHidden(chunkLoadMore, state.chunkVisibleCount >= state.chunkRows.length);
      }
    }

    function renderChunks(version, chunks, anchors, manifest = {}) {
      clearChildren(chunkContent);
      if (chunkEmpty) chunkContent?.appendChild(chunkEmpty);
      if (chunkMeta) chunkMeta.textContent = `${version} · ${chunks.length} 个切片`;
      state.inspectionManifest = manifest || null;
      const mappedCount = Number.isInteger(manifest?.mapped_count) ? manifest.mapped_count : null;
      const unmappedCount = Number.isInteger(manifest?.unmapped_count) ? manifest.unmapped_count : 0;
      const status = String(manifest?.status || 'ready');
      if (chunkStatus) {
        if (status === 'partial' || unmappedCount > 0) {
          const mappedLabel = mappedCount === null ? '部分' : `${mappedCount}/${chunks.length}`;
          const reasons = Object.keys(manifest?.unmapped_reasons || {}).join('、') || 'UNMAPPED';
          chunkStatus.textContent = `partial · 已映射 ${mappedLabel} · 未映射 ${unmappedCount} · 原因 ${reasons}`;
          chunkStatus.setAttribute('data-status', 'partial');
        } else {
          chunkStatus.textContent = `${status} · 已加载`;
          chunkStatus.setAttribute('data-status', status);
        }
      }
      const byChunk = new Map();
      anchors.forEach((anchor) => {
        const key = anchorKey(anchor, version);
        if (!byChunk.has(key)) byChunk.set(key, []);
        byChunk.get(key).push({
          block_id: String(anchor.block_id || ''),
          coverage: Number.isFinite(Number(anchor.coverage)) ? Number(anchor.coverage) : 0,
          is_primary: anchor.is_primary === true,
          unmapped_reason: anchor.unmapped_reason ? String(anchor.unmapped_reason) : null,
        });
      });
      state.chunkRows = chunks.map((chunk) => {
        const chunkIndex = Number.isInteger(chunk.chunk_index) ? chunk.chunk_index : 0;
        const chunker = String(chunk.chunker || version);
        const anchorRelations = byChunk.get(`${chunker}:${chunkIndex}`) || byChunk.get(`${version}:${chunkIndex}`) || [];
        const reasons = Object.keys(manifest?.unmapped_reasons || {});
        const unmappedReason = String(chunk.unmapped_reason || '')
          || anchorRelations.find((anchor) => anchor.unmapped_reason)?.unmapped_reason
          || (anchorRelations.length === 0 && unmappedCount > 0 ? (reasons[0] || 'UNMAPPED') : null);
        return {
          chunk,
          version,
          chunkId: String(chunk.chunk_id || `${chunker}:${chunkIndex}`),
          anchorRelations,
          unmappedReason,
          blockIds: anchorRelations.map((anchor) => anchor.block_id).filter(Boolean),
        };
      });
      state.chunkVisibleCount = 0;
      renderChunkBatch();
    }

    async function loadInspection() {
      const documentId = documentSelect?.value || '';
      const documentValue = state.documents.find((candidate) => String(candidate.document_id) === documentId);
      const version = selectedVersion();
      state.selectedVersion = version;
      state.selectedDocument = documentValue || null;
      cancelPending();
      clearInspectionView();
      if (!documentId || !documentValue) return;
      if (typeof fetchImpl !== 'function') {
        showError({ code: 'NETWORK_UNAVAILABLE', message: '检查清单服务不可用' });
        return;
      }
      const request = beginRequest();
      showLoading('正在加载定位关系：已获取 0');
      const blocks = [];
      const chunks = [];
      const anchors = [];
      let manifest = {};
      let cursor = null;
      let pageCount = 0;
      let lastEtag = null;
      const cacheKey = `${documentId}|${version}`;
      const cachedInspection = state.inspectionCache.get(cacheKey);
      try {
        do {
          if (!isActive(request.sequence)) return;
          const params = new URLSearchParams({
            chunker: version,
            page_size: String(INSPECTION_INITIAL_PAGE_SIZE),
          });
          if (cursor) params.set('cursor', cursor);
          const url = `/api/kb/documents/${encodeURIComponent(documentId)}/inspection?${params.toString()}`;
          const headers = !cursor && cachedInspection?.complete === true && cachedInspection?.etag
            ? { 'If-None-Match': cachedInspection.etag }
            : undefined;
          const response = await fetchImpl(url, { signal: request.signal, ...(headers ? { headers } : {}) });
          const payload = await readJson(response);
          if (!isActive(request.sequence)) return;
          if (response.status === 304) {
            if (!cachedInspection) {
              showError({ code: 'INSPECTION_CACHE_MISS_304', message: '检查清单缓存不可用，无法处理 304。' });
              return;
            }
            if (cachedInspection.complete !== true) {
              showError({ code: 'INSPECTION_CACHE_INCOMPLETE', message: '检查清单缓存不完整，请重新加载。' });
              return;
            }
            blocks.push(...cachedInspection.blocks);
            chunks.push(...cachedInspection.chunks);
            anchors.push(...cachedInspection.anchors);
            manifest = cachedInspection.manifest || {};
            lastEtag = cachedInspection.etag || null;
            cursor = null;
            break;
          }
          const failure = response.status === 200 ? null : responseError(response, payload);
          if (response.status === 202 || failure?.code === 'INSPECTION_BUILDING') {
            showLoading('检查清单正在构建，稍后自动重试…');
            await new Promise((resolve) => {
              state.pollResolve = resolve;
              state.pollTimer = (rootScope.setTimeout || setTimeout)(resolve, retryAfterSeconds(response, payload) * 1000);
            });
            state.pollResolve = null;
            state.pollTimer = null;
            continue;
          }
          if (failure) {
            if (failure.code === 'INDEX_REBUILD_REQUIRED' || failure.code === 'INDEX_FINALIZE_REQUIRED') showMaintenance(failure.code);
            else showError(failure);
            return;
          }
          if (payload && Array.isArray(payload.blocks)) blocks.push(...payload.blocks);
          if (payload && Array.isArray(payload.chunks)) chunks.push(...payload.chunks);
          if (payload && Array.isArray(payload.anchors)) anchors.push(...payload.anchors);
          if (payload && payload.manifest && typeof payload.manifest === 'object') manifest = payload.manifest;
          lastEtag = responseHeader(response, 'ETag') || lastEtag;
          cursor = payload?.next_cursor || null;
          pageCount += 1;
          if (pageCount > 10000) {
            showError({ code: 'PAGINATION_LIMIT', message: '检查清单分页超过安全上限' });
            return;
          }
          const totalAnchors = Number(payload?.total?.anchors);
          const totalLabel = Number.isFinite(totalAnchors) && totalAnchors >= 0 ? ` / 约 ${totalAnchors}` : '';
          if (loading) loading.textContent = `正在加载定位关系：已获取 ${anchors.length}${totalLabel}`;
        } while (cursor);
        if (!isActive(request.sequence)) return;
        if (manifest?.mapping_algorithm_version && manifest.mapping_algorithm_version !== 'source-anchor-v2') {
          showMaintenance('INDEX_REBUILD_REQUIRED');
          return;
        }
        await renderSource(documentValue, blocks, request.sequence);
        if (!isActive(request.sequence)) return;
        // A PDF renderer failure must not hide already verified index chunks.
        // Keep its error visible, while leaving the right-hand inspection pane
        // usable until the source renderer can be retried.
        const sourceRenderFailed = documentValue.media_type !== 'text/markdown' && error && !error.hidden;
        state.inspectionCache.set(cacheKey, {
          blocks: blocks.slice(),
          chunks: chunks.slice(),
          anchors: anchors.slice(),
          manifest,
          etag: lastEtag,
          complete: true,
        });
        renderChunks(version, chunks, anchors, manifest);
        if (!sourceRenderFailed) resetStates();
      } catch (caught) {
        if (caught?.name === 'AbortError' || !isActive(request.sequence)) return;
        showError({ code: 'NETWORK_ERROR', message: '检查清单加载失败' });
      } finally {
        if (isActive(request.sequence)) state.controller = null;
      }
    }

    if (documentSelect) documentSelect.addEventListener('change', loadInspection);
    versionGroup?.querySelectorAll('input[name="kb-inspection-chunker"]').forEach((input) => {
      input.addEventListener('change', loadInspection);
    });
    bindPrimaryTabs();
    bindPaneTabs();
    chunkLoadMore?.addEventListener('click', renderChunkBatch);
    resetStates();
    clearInspectionView();

    return {
      activateTab,
      activatePane,
      cancel: cancelPending,
      loadDocuments,
      loadInspection,
      state,
    };
  }

  const api = {
    REQUIRED_SOURCE_BLOCK_FIELDS,
    SANITIZE_OPTIONS,
    PDFJS_VERSION,
    PDFJS_MODULE_URL,
    PDFJS_WORKER_SRC,
    PDFJS_MAIN_SHA256,
    PDFJS_WORKER_SHA256,
    PDF_GET_DOCUMENT_OPTIONS,
    isAllowedPdfWorkerSource,
    resolvePdfWorkerSource,
    escapeHtml,
    renderMarkdownBlock,
    validateSourceBlock,
    createKbInspectionController,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.KbInspectionRenderer = api;
    const boot = () => {
      if (!root.__kbInspectionController && root.document?.querySelector) {
        root.__kbInspectionController = createKbInspectionController(root);
      }
    };
    if (root.document?.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', boot, { once: true });
    else boot();
  }
}(typeof globalThis === 'object' ? globalThis : window));
