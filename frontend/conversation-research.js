/* Desktop conversation research UI: safe RAG source cards and progress details. */
(function exposeConversationResearch(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ConversationResearch = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function conversationResearchFactory() {
  const MAX_SOURCES = 5;
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

  function createSourceDetail(documentRef, source, index) {
    const detail = documentRef.createElement('article');
    detail.className = 'conversation-source-detail';
    detail.id = `conversation-source-detail-${index + 1}`;
    detail.hidden = true;
    detail.setAttribute('aria-label', `来源 ${index + 1} 详情`);
    const title = documentRef.createElement('h4');
    title.className = 'conversation-source-detail-title';
    title.textContent = source.file_name || source.document_id || source.paper_id || `来源 ${index + 1}`;
    detail.appendChild(title);
    const fields = documentRef.createElement('dl');
    fields.className = 'conversation-source-detail-fields';
    appendDetail(documentRef, fields, '文档', source.document_id || source.paper_id);
    appendDetail(documentRef, fields, '文件', source.file_name);
    appendDetail(documentRef, fields, '位置', displayPage(source));
    appendDetail(documentRef, fields, '切片', source.chunk_id || source.chunk_index);
    appendDetail(documentRef, fields, '得分', source.score == null ? null : source.score);
    appendDetail(documentRef, fields, '正文', source.text);
    appendSourceLink(documentRef, fields, source);
    detail.appendChild(fields);
    return detail;
  }

  function createSourceRenderer({ document: documentRef, container }) {
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
        const detail = createSourceDetail(documentRef, source, index);
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

  return { MAX_SOURCES, normalizeSources, safeSourceUrl, createSourceRenderer };
}));
