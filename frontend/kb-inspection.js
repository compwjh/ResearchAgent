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

  const api = {
    REQUIRED_SOURCE_BLOCK_FIELDS,
    SANITIZE_OPTIONS,
    escapeHtml,
    renderMarkdownBlock,
    validateSourceBlock,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KbInspectionRenderer = api;
}(typeof globalThis === 'object' ? globalThis : window));
