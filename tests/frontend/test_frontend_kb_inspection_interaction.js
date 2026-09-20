'use strict';

const assert = require('node:assert/strict');
const { createKbInspectionController } = require('../frontend/kb-inspection.js');

class FakeElement {
  constructor(tagName, documentRef) {
    this.tagName = tagName.toLowerCase();
    this.ownerDocument = documentRef;
    this.nodeType = 1;
    this.parentNode = null;
    this.childNodes = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.hidden = false;
    this.value = '';
    this.checked = false;
    this.textContent = '';
    this.tabIndex = -1;
    this.scrollTop = 0;
    this.scrollCalls = 0;
    this.className = '';
    this.style = {};
    this.dataset = {};
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === 'id') this.ownerDocument.byId.set(String(value), this);
    if (name === 'value') this.value = String(value);
    if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
  }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  appendChild(child) { child.parentNode = this; this.childNodes.push(child); return child; }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  replaceChildren(...children) { this.childNodes = []; children.forEach((child) => this.appendChild(child)); }
  addEventListener(type, callback) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(callback); }
  dispatch(type, extra = {}) {
    const event = { type, target: this, preventDefault() { this.defaultPrevented = true; }, ...extra };
    (this.listeners.get(type) || []).forEach((callback) => callback(event));
    return event;
  }
  focus() { this.ownerDocument.activeElement = this; }
  scrollIntoView() { this.scrollCalls += 1; }
  querySelectorAll(selector) {
    const nodes = [];
    const visit = (node) => {
      node.childNodes.forEach((child) => {
        if (child.matches?.(selector)) nodes.push(child);
        visit(child);
      });
    };
    visit(this);
    return nodes;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  matches(selector) {
    if (selector === '[role="tab"]') return this.getAttribute('role') === 'tab';
    if (selector === '[data-block-id]') return this.attributes.has('data-block-id');
    if (selector === '[data-chunk-id]') return this.attributes.has('data-chunk-id');
    if (selector === '[data-block-ids]') return this.attributes.has('data-block-ids');
    if (selector === 'input[name="kb-inspection-chunker"]') return this.tagName === 'input' && this.getAttribute('name') === 'kb-inspection-chunker';
    if (selector === 'input[name="kb-inspection-chunker"]:checked') return this.matches('input[name="kb-inspection-chunker"]') && this.checked;
    if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
    return false;
  }
  getContext(kind) { return this.tagName === 'canvas' && kind === '2d' ? {} : null; }
}

class FakeDocument {
  constructor() { this.byId = new Map(); this.activeElement = null; }
  createElement(tagName) { return new FakeElement(tagName, this); }
  getElementById(id) { return this.byId.get(id) || null; }
  add(id, tagName, attrs = {}) {
    const element = this.createElement(tagName);
    element.setAttribute('id', id);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }
}

function response(payload) {
  return { status: 200, headers: { get() { return null; } }, async json() { return payload; } };
}

function makeHarness({ mediaType = 'text/markdown', blocks, chunks, anchors, manifest = {}, version = 'v1', pdfjsLoader = null, intersectionObserver } = {}) {
  const documentRef = new FakeDocument();
  const ids = [
    ['kb-tabs', 'div'], ['kb-tab-qa', 'button', { role: 'tab', 'aria-controls': 'kb-panel-qa', 'aria-selected': 'true' }],
    ['kb-tab-inspection', 'button', { role: 'tab', 'aria-controls': 'kb-panel-inspection', 'aria-selected': 'false' }],
    ['kb-panel-qa', 'section'], ['kb-panel-inspection', 'section'], ['kb-inspection-document', 'select'],
    ['kb-inspection-version-group', 'fieldset'], ['kb-inspection-maintenance', 'p'], ['kb-inspection-finalize', 'p'],
    ['kb-inspection-loading', 'p'], ['kb-inspection-error', 'p'], ['kb-source-empty', 'p'], ['kb-source-document', 'div'],
    ['kb-source-pdf', 'div'], ['kb-source-markdown', 'div'], ['kb-source-meta', 'p'], ['kb-source-kind', 'span'],
    ['kb-chunk-content', 'div'], ['kb-chunk-empty', 'p'], ['kb-chunk-meta', 'p'], ['kb-chunk-status', 'span'],
    ['kb-chunk-load-more', 'button'], ['kb-inspection-layout', 'div'], ['kb-inspection-view-switcher', 'div'],
    ['kb-inspection-source-tab', 'button', { role: 'tab', 'aria-controls': 'kb-source-panel', 'aria-selected': 'true', 'data-pane-target': 'source' }],
    ['kb-inspection-chunk-tab', 'button', { role: 'tab', 'aria-controls': 'kb-chunk-panel', 'aria-selected': 'false', 'data-pane-target': 'chunks' }],
    ['kb-source-content', 'div'], ['kb-chunk-panel', 'section'], ['kb-source-panel', 'section'],
  ];
  const elements = {};
  ids.forEach(([id, tag, attrs]) => { elements[id] = documentRef.add(id, tag, attrs); });
  elements['kb-tabs'].append(elements['kb-tab-qa'], elements['kb-tab-inspection']);
  elements['kb-inspection-view-switcher'].append(elements['kb-inspection-source-tab'], elements['kb-inspection-chunk-tab']);
  const v1 = documentRef.add('kb-inspection-chunker-v1', 'input', { name: 'kb-inspection-chunker', value: 'v1' });
  const v2 = documentRef.add('kb-inspection-chunker-v2', 'input', { name: 'kb-inspection-chunker', value: 'v2' });
  v1.checked = version === 'v1'; v2.checked = version === 'v2';
  elements['kb-inspection-version-group'].append(v1, v2);
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({ url, options });
    if (url.startsWith('/api/kb/documents?')) return response({ documents: [{ document_id: 'doc-1', file_name: 'fixture', media_type: mediaType }] });
    return response({ manifest, blocks, chunks, anchors });
  };
  const controller = createKbInspectionController({ fetch: fetchImpl, AbortController }, {
    document: documentRef,
    renderer: { renderMarkdownBlock: (dto) => {
      const article = documentRef.createElement('article');
      article.className = 'kb-source-block';
      article.tabIndex = 0;
      article.setAttribute('role', 'article');
      article.setAttribute('data-block-id', dto.block_id);
      return article;
    } },
    pdfjsLoader,
    IntersectionObserver: intersectionObserver,
  });
  return { controller, documentRef, elements, requests, v1, v2 };
}

async function flush() { await new Promise((resolve) => setImmediate(resolve)); }

async function loadFixture(harness) {
  harness.elements['kb-tab-inspection'].dispatch('click');
  await flush();
  harness.elements['kb-inspection-document'].value = 'doc-1';
  harness.elements['kb-inspection-document'].dispatch('change');
  await flush(); await flush(); await flush();
}

function activeNodes(container, attr) {
  return container.querySelectorAll(attr).filter((node) => node.getAttribute('data-active') === 'true');
}

async function testMarkdownOverlapKeyboardAndBatch() {
  const blocks = [1, 2, 3].map((ordinal) => ({ block_id: `b${ordinal}`, ordinal: ordinal - 1, text: `block ${ordinal}`, locator: {}, heading_path: [], block_type: 'paragraph' }));
  const chunks = Array.from({ length: 205 }, (_, index) => ({ chunk_id: `c${index}`, chunker: 'v1', chunk_index: index, text: `chunk ${index}` }));
  const anchors = [
    { block_id: 'b2', chunker: 'v1', chunk_index: 0, coverage: 0.4, is_primary: false },
    { block_id: 'b2', chunker: 'v1', chunk_index: 1, coverage: 0.8, is_primary: true },
    { block_id: 'b2', chunker: 'v1', chunk_index: 150, coverage: 0.3, is_primary: false },
    { block_id: 'b3', chunker: 'v1', chunk_index: 1, coverage: 0.5, is_primary: false },
    ...Array.from({ length: 202 }, (_, index) => ({ block_id: 'b1', chunker: 'v1', chunk_index: index + 3 })),
  ];
  const harness = makeHarness({
    blocks,
    chunks,
    anchors,
    manifest: { status: 'partial', mapped_count: 204, unmapped_count: 1, unmapped_reasons: { NO_SOURCE_BLOCK_OVERLAP: 1 } },
  });
  await loadFixture(harness);
  const source = harness.elements['kb-source-markdown'];
  const chunkContent = harness.elements['kb-chunk-content'];
  assert.equal(chunkContent.querySelectorAll('[data-chunk-id]').length, 100);
  const block2 = source.querySelector('[data-block-id]');
  const sourceBlock2 = source.querySelectorAll('[data-block-id]').find((node) => node.getAttribute('data-block-id') === 'b2');
  assert.equal(harness.controller.state.chunkRows.find((row) => row.chunkId === 'c0').anchorRelations[0].coverage, 0.4);
  assert.equal(harness.controller.state.chunkRows.find((row) => row.chunkId === 'c0').anchorRelations[0].is_primary, false);
  assert.equal(chunkContent.querySelectorAll('[data-chunk-id]').find((node) => node.getAttribute('data-chunk-id') === 'c2').getAttribute('data-unmapped-reason'), 'NO_SOURCE_BLOCK_OVERLAP');
  assert.equal(harness.elements['kb-chunk-status'].getAttribute('data-status'), 'partial');
  sourceBlock2.dispatch('click');
  assert.equal(activeNodes(chunkContent, '[data-chunk-id]').length, 3);
  assert.equal(harness.elements['kb-inspection-layout'].getAttribute('data-active-pane'), 'chunks');
  assert.equal(harness.documentRef.activeElement.getAttribute('data-chunk-id'), 'c1');
  assert.equal(harness.documentRef.activeElement.scrollCalls, 1);
  assert.equal(block2.getAttribute('data-active'), 'false');
  assert.equal(sourceBlock2.getAttribute('data-active'), 'true');

  const chunk1 = chunkContent.querySelectorAll('[data-chunk-id]').find((node) => node.getAttribute('data-chunk-id') === 'c1');
  chunk1.dispatch('keydown', { key: ' ' });
  assert.equal(activeNodes(source, '[data-block-id]').length, 2);
  assert.equal(harness.elements['kb-inspection-layout'].getAttribute('data-active-pane'), 'source');
  assert.equal(harness.documentRef.activeElement.getAttribute('data-block-id'), 'b2');

  assert.equal(chunkContent.querySelectorAll('[data-chunk-id]').length, 200);
  assert.equal(harness.elements['kb-chunk-load-more'].hidden, false);
  const callsBefore = harness.requests.length;
  harness.elements['kb-chunk-load-more'].dispatch('click');
  harness.elements['kb-chunk-load-more'].dispatch('click');
  assert.equal(chunkContent.querySelectorAll('[data-chunk-id]').length, 205);
  assert.equal(harness.elements['kb-chunk-load-more'].hidden, true);
  assert.equal(harness.requests.length, callsBefore);
  assert.equal(harness.requests.every(({ options }) => !options.method), true);
}

function makePdfjs() {
  const pages = [1, 2].map((number) => ({
    getViewport() { return { width: 100, height: 100 }; },
    async getTextContent() { return { items: [{ str: `page ${number}` }] }; },
    render() { return { promise: Promise.resolve(), cancel() {} }; },
  }));
  return {
    version: '4.10.38',
    GlobalWorkerOptions: {},
    getDocument() {
      return { promise: Promise.resolve({ numPages: 2, async getPage(number) { return pages[number - 1]; }, destroy() {} }) };
    },
  };
}

class LazyIntersectionObserver {
  constructor(callback) {
    this.callback = callback;
    this.targets = [];
    LazyIntersectionObserver.instance = this;
  }
  observe(target) { this.targets.push(target); }
  disconnect() { this.disconnected = true; }
  trigger(pageNumber) {
    const target = this.targets.find((candidate) => Number(candidate.getAttribute('data-page')) === pageNumber);
    if (target) this.callback([{ isIntersecting: true, target }]);
  }
}

async function testPdfCrossPageAndNarrowScroll() {
  const blocks = [1, 2].map((page) => ({ block_id: `pdf-${page}`, ordinal: page - 1, text: `pdf ${page}`, locator: { kind: 'pdf_bbox', page, bbox: [0.1, 0.1, 0.8, 0.2] }, heading_path: [], block_type: 'paragraph' }));
  const chunks = [{ chunk_id: 'v2:0', chunker: 'v2', chunk_index: 0, text: 'cross page' }];
  const anchors = blocks.map((block) => ({ block_id: block.block_id, chunker: 'v2', chunk_index: 0 }));
  const harness = makeHarness({
    mediaType: 'application/pdf',
    blocks,
    chunks,
    anchors,
    version: 'v2',
    pdfjsLoader: async () => makePdfjs(),
    intersectionObserver: LazyIntersectionObserver,
  });
  await loadFixture(harness);
  await flush(); await flush();
  const pdf = harness.elements['kb-source-pdf'];
  assert.equal(pdf.querySelectorAll('[data-block-id]').length, 0);
  LazyIntersectionObserver.instance.trigger(1);
  await flush(); await flush();
  assert.equal(pdf.querySelectorAll('[data-block-id]').length, 1);
  const chunk = harness.elements['kb-chunk-content'].querySelector('[data-chunk-id]');
  harness.elements['kb-source-content'].scrollTop = 17;
  harness.elements['kb-chunk-content'].scrollTop = 29;
  chunk.dispatch('click');
  await flush(); await flush();
  const overlays = pdf.querySelectorAll('[data-block-id]');
  assert.equal(overlays.length, 2);
  assert.equal(activeNodes(pdf, '[data-block-id]').length, 2);
  assert.equal(harness.documentRef.activeElement.getAttribute('data-block-id'), 'pdf-1');
  assert.equal(harness.elements['kb-inspection-layout'].getAttribute('data-active-pane'), 'source');
  assert.equal(harness.controller.state.paneScroll.chunks, 29);
  const secondOverlay = overlays[1];
  secondOverlay.dispatch('keydown', { key: 'Enter' });
  assert.equal(activeNodes(harness.elements['kb-chunk-content'], '[data-chunk-id]').length, 1);
  assert.equal(harness.elements['kb-inspection-layout'].getAttribute('data-active-pane'), 'chunks');
  assert.equal(harness.controller.state.paneScroll.source, 17);
  assert.equal(harness.requests.length, 2);
  assert.equal(harness.requests.every(({ options }) => !options.method), true);
}

(async () => {
  await testMarkdownOverlapKeyboardAndBatch();
  await testPdfCrossPageAndNarrowScroll();
  console.log('frontend interaction contract: PASS (overlap/cross-page, click-keyboard, narrow scroll, batching, GET-only)');
})().catch((error) => { console.error(error); process.exitCode = 1; });
