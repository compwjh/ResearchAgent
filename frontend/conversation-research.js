/* Desktop conversation research UI: safe RAG source cards and progress details. */
(function exposeConversationResearch(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ConversationResearch = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function conversationResearchFactory() {
  const MAX_SOURCES = 5;

  // 任务 C：ID / hash / 版本号只显示短码，全文交给原生 title 悬浮查看。
  function formatShortHash(value, n = 8) {
    const text = value == null ? '' : String(value);
    return text.length > n ? `${text.slice(0, n)}…` : text;
  }

  function withTooltip(el, fullText) {
    if (!el) return el;
    const text = fullText == null ? '' : String(fullText);
    el.title = text;
    if (typeof el.setAttribute === 'function') el.setAttribute('aria-label', text);
    return el;
  }

  const SOURCE_ROUTE = /^\/api\/kb\/documents\/[^/?#]+\/source(?:\?[^#]*)?$/;

  function normalizeSources(value) {
    if (!Array.isArray(value)) return [];
    return value.filter((item) => item && typeof item === 'object').slice(0, MAX_SOURCES);
  }

  function safeSourceUrl(value) {
    const url = typeof value === 'string' ? value.trim() : '';
    return SOURCE_ROUTE.test(url) ? url : '';
  }

  function displayPage(source) {
    const page = Number.isInteger(source.page) && source.page > 0 ? source.page : null;
    const pageEnd = Number.isInteger(source.page_end) && source.page_end >= page ? source.page_end : page;
    if (page && pageEnd && pageEnd > page) return `第 ${page}-${pageEnd} 页`;
    if (page) return `第 ${page} 页`;
    const start = Number.isInteger(source.start_line) && source.start_line > 0 ? source.start_line : null;
    const end = Number.isInteger(source.end_line) && source.end_line >= start ? source.end_line : start;
    if (start && end && end > start) return `行 ${start}–${end}`;
    if (start) return `行 ${start}`;
    return '无页码';
  }

  function appendDetail(documentRef, parent, label, value) {
    const row = documentRef.createElement('div');
    row.className = 'conversation-source-detail-row';
    const key = documentRef.createElement('dt');
    key.className = 'conversation-source-detail-label';
    key.textContent = label;
    const content = documentRef.createElement('dd');
    content.className = 'conversation-source-detail-value';
    content.textContent = value == null || value === '' ? '—' : String(value);
    row.append(key, content);
    parent.appendChild(row);
    return content;
  }

  function appendSourceLink(documentRef, parent, source) {
    const url = safeSourceUrl(source.source_url);
    if (!url) return;
    const row = documentRef.createElement('div');
    row.className = 'conversation-source-detail-row conversation-source-link-row';
    const key = documentRef.createElement('dt');
    key.className = 'conversation-source-detail-label';
    key.textContent = '原文';
    const value = documentRef.createElement('dd');
    value.className = 'conversation-source-detail-value';
    const link = documentRef.createElement('a');
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer nofollow';
    link.textContent = '打开知识库原文';
    value.appendChild(link);
    row.append(key, value);
    parent.appendChild(row);
  }

  // 第二入口：在既有「打开知识库原文」之外，提供页内「定位到召回片段」按钮。
  // fail-closed：缺 onLocateChunk 回调 / 缺 chunk_id 与 chunk_index 时不渲染任何内容，不留死链。
  // 全部文本走 textContent，不拼接任何 URL，不触碰 appendSourceLink 的既有 link 行为。
  function appendChunkLocateLink(documentRef, parent, source, onLocateChunk) {
    if (typeof onLocateChunk !== 'function') return;
    const chunkId = source.chunk_id != null ? source.chunk_id : source.chunk_index;
    if (chunkId == null) return;
    const row = documentRef.createElement('div');
    row.className = 'conversation-source-detail-row conversation-source-link-row';
    const key = documentRef.createElement('dt');
    key.className = 'conversation-source-detail-label';
    key.textContent = '片段';
    const value = documentRef.createElement('dd');
    value.className = 'conversation-source-detail-value';
    const button = documentRef.createElement('button');
    button.type = 'button';
    button.className = 'conversation-source-locate-button';
    button.textContent = '定位到召回片段';
    button.addEventListener('click', (event) => {
      try {
        event.preventDefault();
        event.stopPropagation();
        onLocateChunk({
          documentId: source.document_id || source.paper_id || null,
          chunkId: String(chunkId),
          source,
        });
      } catch (caught) {
        // 回调异常不冒泡、不中断页面。
      }
    });
    value.appendChild(button);
    row.append(key, value);
    parent.appendChild(row);
  }

  function createSourceDetail(documentRef, source, index, onLocateChunk = null) {
    const detail = documentRef.createElement('article');
    detail.className = 'conversation-source-detail';
    detail.id = `conversation-source-detail-${index + 1}`;
    detail.hidden = true;
    detail.setAttribute('aria-label', `来源 ${index + 1} 详情`);
    const title = documentRef.createElement('h4');
    const sourceTitle = String(source.file_name || source.document_id || source.paper_id || `来源 ${index + 1}`);
    title.className = 'conversation-source-detail-title clamp-3';
    title.textContent = sourceTitle;
    withTooltip(title, sourceTitle);
    detail.appendChild(title);
    const fields = documentRef.createElement('dl');
    fields.className = 'conversation-source-detail-fields';
    const docValue = source.document_id || source.paper_id;
    const docRow = appendDetail(documentRef, fields, '文档', formatShortHash(docValue));
    docRow.className += ' hash-inline';
    withTooltip(docRow, docValue == null ? '' : String(docValue));
    const fileValue = source.file_name;
    const fileRow = appendDetail(documentRef, fields, '文件', formatShortHash(fileValue, 24));
    withTooltip(fileRow, fileValue == null ? '' : String(fileValue));
    appendDetail(documentRef, fields, '位置', displayPage(source));
    const chunkValue = source.chunk_id || source.chunk_index;
    const chunkRow = appendDetail(documentRef, fields, '切片', formatShortHash(chunkValue));
    chunkRow.className += ' hash-inline';
    withTooltip(chunkRow, chunkValue == null ? '' : String(chunkValue));
    appendDetail(documentRef, fields, '得分', source.score == null ? null : source.score);
    const textRow = appendDetail(documentRef, fields, '正文', source.text);
    textRow.className += ' clamp-3';
    withTooltip(textRow, source.text == null ? '' : String(source.text));
    appendSourceLink(documentRef, fields, source);
    appendChunkLocateLink(documentRef, fields, source, onLocateChunk);
    detail.appendChild(fields);
    return detail;
  }

  function createSourceRenderer({ document: documentRef, container, onLocateChunk = null }) {
    let activeIndex = -1;
    let renderedSources = [];

    function setExpanded(index, expanded) {
      const buttons = container.querySelectorAll('[data-source-index]');
      const details = container.querySelectorAll('.conversation-source-detail');
      buttons.forEach((button, buttonIndex) => {
        const selected = expanded && buttonIndex === index;
        button.setAttribute('aria-expanded', selected ? 'true' : 'false');
        button.classList.toggle('is-active', selected);
      });
      details.forEach((detail, detailIndex) => { detail.hidden = !(expanded && detailIndex === index); });
      activeIndex = expanded ? index : -1;
    }

    function render(value) {
      renderedSources = normalizeSources(value);
      activeIndex = -1;
      container.replaceChildren();
      container.hidden = renderedSources.length === 0;
      if (!renderedSources.length) return renderedSources;
      container.setAttribute('aria-label', '参考来源');
      const list = documentRef.createElement('div');
      list.className = 'conversation-sources-list';
      renderedSources.forEach((source, index) => {
        const item = documentRef.createElement('div');
        item.className = 'conversation-source-item';
        const button = documentRef.createElement('button');
        button.type = 'button';
        button.className = 'conversation-source-button';
        button.dataset.sourceIndex = String(index);
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-controls', `conversation-source-detail-${index + 1}`);
        button.setAttribute('aria-label', `展开来源 ${index + 1}`);
        button.textContent = String(index + 1);
        const detail = createSourceDetail(documentRef, source, index, onLocateChunk);
        button.addEventListener('click', () => {
          const shouldExpand = activeIndex !== index;
          setExpanded(index, shouldExpand);
        });
        item.append(button, detail);
        list.appendChild(item);
      });
      container.appendChild(list);
      return renderedSources;
    }

    function clear() { render([]); }

    return { render, clear, get sources() { return renderedSources; }, get activeIndex() { return activeIndex; } };
  }

  return { MAX_SOURCES, normalizeSources, safeSourceUrl, createSourceRenderer, appendChunkLocateLink };
}));
