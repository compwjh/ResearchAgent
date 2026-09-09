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

  function createKbInspectionController(rootScope, options = {}) {
    const documentRef = options.document || rootScope.document;
    const fetchImpl = options.fetch || (rootScope.fetch && rootScope.fetch.bind(rootScope));
    const AbortControllerImpl = options.AbortController || rootScope.AbortController;
    const markedImpl = options.marked || rootScope.marked;
    const purifyImpl = options.DOMPurify || rootScope.DOMPurify;
    const renderer = options.renderer || { renderMarkdownBlock };
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
    const sourcePdf = elementById(documentRef, 'kb-source-pdf');
    const sourceMarkdown = elementById(documentRef, 'kb-source-markdown');
    const sourceMeta = elementById(documentRef, 'kb-source-meta');
    const sourceKind = elementById(documentRef, 'kb-source-kind');
    const chunkContent = elementById(documentRef, 'kb-chunk-content');
    const chunkEmpty = elementById(documentRef, 'kb-chunk-empty');
    const chunkMeta = elementById(documentRef, 'kb-chunk-meta');
    const chunkStatus = elementById(documentRef, 'kb-chunk-status');
    const layout = elementById(documentRef, 'kb-inspection-layout');
    const paneSwitcher = elementById(documentRef, 'kb-inspection-view-switcher');
    const state = {
      documentsLoaded: false,
      documentsPromise: null,
      documents: [],
      selectedDocument: null,
      selectedVersion: 'v1',
      sequence: 0,
      controller: null,
      pollTimer: null,
      pollResolve: null,
      paneScroll: { source: 0, chunks: 0 },
    };

    function isActive(sequence) { return state.sequence === sequence; }

    function cancelPending() {
      state.sequence += 1;
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
      const previous = layout.getAttribute('data-active-pane') || 'source';
      const previousPane = elementById(documentRef, previous === 'source' ? 'kb-source-content' : 'kb-chunk-content');
      if (previousPane) state.paneScroll[previous] = previousPane.scrollTop || 0;
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

    async function loadDocuments() {
      if (state.documentsLoaded) return state.documents;
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
          do {
            if (!isActive(request.sequence)) return [];
            const params = new URLSearchParams({ limit: '100' });
            if (cursor) params.set('cursor', cursor);
            const url = `/api/kb/documents?${params.toString()}`;
            const response = await fetchImpl(url, { signal: request.signal });
            const payload = await readJson(response);
            if (!isActive(request.sequence)) return [];
            if (response.status !== 200) {
              const failure = responseError(response, payload);
              if (failure.code === 'INDEX_FINALIZE_REQUIRED') showMaintenance(failure.code);
              else if (failure.code === 'INDEX_REBUILD_REQUIRED') showMaintenance(failure.code);
              else showError(failure);
              return [];
            }
            if (Array.isArray(payload.documents)) documents.push(...payload.documents);
            cursor = payload.next_cursor || null;
            pageCount += 1;
            if (pageCount > 1000) {
              showError({ code: 'PAGINATION_LIMIT', message: '文档列表分页超过安全上限' });
              return [];
            }
            if (cursor) showLoading(`正在加载文档列表第 ${pageCount + 1} 页…`);
          } while (cursor);
          state.documents = documents;
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

    function renderSource(documentValue, blocks) {
      clearChildren(sourcePdf);
      clearChildren(sourceMarkdown);
      setHidden(sourceEmpty, blocks.length > 0);
      setHidden(sourceDocument, false);
      if (sourceMeta) sourceMeta.textContent = `${String(documentValue.file_name || '未命名文档')} · ${blocks.length} 个原文块`;
      if (sourceKind) sourceKind.textContent = documentValue.media_type === 'text/markdown' ? 'Markdown' : 'PDF';
      if (documentValue.media_type !== 'text/markdown') {
        const placeholder = documentRef.createElement('p');
        placeholder.className = 'kb-inspection-empty';
        placeholder.textContent = 'PDF 原文渲染将在下一段接入 PDF.js。';
        sourcePdf?.appendChild(placeholder);
        setHidden(sourcePdf, false);
        setHidden(sourceMarkdown, true);
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
          sourceMarkdown.appendChild(block);
        } catch (caught) {
          const fallback = documentRef.createElement('p');
          fallback.textContent = '原文块无法渲染。';
          sourceMarkdown.appendChild(fallback);
        }
      });
    }

    function renderChunks(version, chunks, anchors) {
      clearChildren(chunkContent);
      if (chunkEmpty) chunkContent?.appendChild(chunkEmpty);
      setHidden(chunkEmpty, chunks.length > 0);
      if (chunkMeta) chunkMeta.textContent = `${version} · ${chunks.length} 个切片`;
      if (chunkStatus) chunkStatus.textContent = '已加载';
      const byChunk = new Map();
      anchors.forEach((anchor) => {
        const key = anchorKey(anchor, version);
        if (!byChunk.has(key)) byChunk.set(key, []);
        if (anchor.block_id) byChunk.get(key).push(String(anchor.block_id));
      });
      chunks.forEach((chunk) => {
        const chunkIndex = Number.isInteger(chunk.chunk_index) ? chunk.chunk_index : 0;
        const chunker = String(chunk.chunker || version);
        const chunkId = String(chunk.chunk_id || `${chunker}:${chunkIndex}`);
        const item = documentRef.createElement('article');
        item.className = 'kb-chunk-item';
        item.tabIndex = 0;
        item.setAttribute('role', 'listitem');
        item.setAttribute('data-chunk-id', chunkId);
        item.setAttribute('data-chunk-index', chunkIndex);
        const blockIds = byChunk.get(`${chunker}:${chunkIndex}`) || byChunk.get(`${version}:${chunkIndex}`) || [];
        item.setAttribute('data-block-ids', blockIds.join(' '));
        item.setAttribute('aria-label', `切片 ${chunkIndex + 1}`);
        const meta = documentRef.createElement('p');
        meta.className = 'kb-chunk-meta';
        meta.textContent = `${chunker} · #${chunkIndex}${chunk.section ? ` · ${String(chunk.section)}` : ''}`;
        const text = documentRef.createElement('p');
        text.className = 'kb-chunk-text';
        text.textContent = String(chunk.text || '');
        item.append(meta, text);
        chunkContent.appendChild(item);
      });
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
      showLoading('正在加载检查清单…');
      const blocks = [];
      const chunks = [];
      const anchors = [];
      let cursor = null;
      let pageCount = 0;
      try {
        do {
          if (!isActive(request.sequence)) return;
          const params = new URLSearchParams({ chunker: version });
          if (cursor) params.set('cursor', cursor);
          const url = `/api/kb/documents/${encodeURIComponent(documentId)}/inspection?${params.toString()}`;
          const response = await fetchImpl(url, { signal: request.signal });
          const payload = await readJson(response);
          if (!isActive(request.sequence)) return;
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
          cursor = payload?.next_cursor || null;
          pageCount += 1;
          if (pageCount > 10000) {
            showError({ code: 'PAGINATION_LIMIT', message: '检查清单分页超过安全上限' });
            return;
          }
          if (cursor) showLoading(`正在加载检查清单第 ${pageCount + 1} 页…`);
        } while (cursor);
        if (!isActive(request.sequence)) return;
        renderSource(documentValue, blocks);
        renderChunks(version, chunks, anchors);
        resetStates();
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
