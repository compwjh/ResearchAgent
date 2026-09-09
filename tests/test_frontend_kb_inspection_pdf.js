'use strict';

const assert = require('node:assert/strict');
const {
  createKbInspectionController,
  PDFJS_MODULE_URL,
  PDFJS_WORKER_SRC,
  PDF_GET_DOCUMENT_OPTIONS,
} = require('../frontend/kb-inspection.js');

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
    this.textContent = '';
    this.tabIndex = -1;
    this.className = '';
    this.dataset = {};
    this.style = {};
    this.checked = false;
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
    const event = { type, target: this, preventDefault() {}, ...extra };
    (this.listeners.get(type) || []).forEach((callback) => callback(event));
  }
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
    if (selector === 'input[name="kb-inspection-chunker"]') return this.tagName === 'input' && this.getAttribute('name') === 'kb-inspection-chunker';
    if (selector === 'input[name="kb-inspection-chunker"]:checked') return this.matches('input[name="kb-inspection-chunker"]') && this.checked;
    if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
    return false;
  }
  getContext(kind) { return this.tagName === 'canvas' && kind === '2d' ? {} : null; }
}

class FakeDocument {
  constructor() { this.byId = new Map(); }
  createElement(tagName) { return new FakeElement(tagName, this); }
  getElementById(id) { return this.byId.get(id) || null; }
  add(id, tagName, attrs = {}) {
    const element = this.createElement(tagName);
    element.setAttribute('id', id);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }
}

class FakeIntersectionObserver {
  constructor(callback, options) {
    this.callback = callback;
    this.options = options;
    this.targets = [];
    FakeIntersectionObserver.instance = this;
  }
  observe(target) { this.targets.push(target); }
  disconnect() { this.disconnected = true; }
  trigger() { this.callback(this.targets.map((target) => ({ isIntersecting: true, target }))); }
}

function response(status, payload) {
  return { status, headers: { get() { return null; } }, async json() { return payload; } };
}

function makeHarness({ pdfjsLoader, intersectionObserver = FakeIntersectionObserver, fetchImpl }) {
  const documentRef = new FakeDocument();
  const ids = [
    ['kb-tabs', 'div'], ['kb-tab-qa', 'button', { role: 'tab', 'aria-controls': 'kb-panel-qa', 'aria-selected': 'true' }],
    ['kb-tab-inspection', 'button', { role: 'tab', 'aria-controls': 'kb-panel-inspection', 'aria-selected': 'false' }],
    ['kb-panel-qa', 'section'], ['kb-panel-inspection', 'section'], ['kb-inspection-document', 'select'],
    ['kb-inspection-version-group', 'fieldset'], ['kb-inspection-maintenance', 'p'], ['kb-inspection-finalize', 'p'],
    ['kb-inspection-loading', 'p'], ['kb-inspection-error', 'p'], ['kb-source-empty', 'p'], ['kb-source-document', 'div'],
    ['kb-source-pdf', 'div'], ['kb-source-markdown', 'div'], ['kb-source-meta', 'p'], ['kb-source-kind', 'span'],
    ['kb-chunk-content', 'div'], ['kb-chunk-empty', 'p'], ['kb-chunk-meta', 'p'], ['kb-chunk-status', 'span'],
    ['kb-inspection-layout', 'div'], ['kb-inspection-view-switcher', 'div'],
    ['kb-inspection-source-tab', 'button', { role: 'tab', 'aria-controls': 'kb-source-panel', 'aria-selected': 'true', 'data-pane-target': 'source' }],
    ['kb-inspection-chunk-tab', 'button', { role: 'tab', 'aria-controls': 'kb-chunk-panel', 'aria-selected': 'false', 'data-pane-target': 'chunks' }],
    ['kb-source-content', 'div'], ['kb-chunk-panel', 'section'], ['kb-source-panel', 'section'],
  ];
  const elements = {};
  ids.forEach(([id, tag, attrs]) => { elements[id] = documentRef.add(id, tag, attrs); });
  elements['kb-tabs'].append(elements['kb-tab-qa'], elements['kb-tab-inspection']);
  elements['kb-inspection-view-switcher'].append(elements['kb-inspection-source-tab'], elements['kb-inspection-chunk-tab']);
  const v1 = documentRef.add('kb-inspection-chunker-v1', 'input', { name: 'kb-inspection-chunker', value: 'v1' });
  v1.checked = true;
  elements['kb-inspection-version-group'].append(v1);
  const controller = createKbInspectionController({ fetch: fetchImpl, AbortController }, {
    document: documentRef,
    pdfjsLoader,
    IntersectionObserver: intersectionObserver,
    renderer: { renderMarkdownBlock: () => documentRef.createElement('article') },
  });
  return { controller, documentRef, elements };
}

async function flush() { await new Promise((resolve) => setImmediate(resolve)); }

function makePdfjs(options = {}) {
  const calls = { getDocument: [], getPage: [], viewport: [], text: [], render: [] };
  const fakePage = {
    getViewport(args) { calls.viewport.push(args); return { width: 200, height: 100 }; },
    async getTextContent() { calls.text.push(true); return { items: [{ str: '安全文本' }] }; },
    render(args) {
      calls.render.push(args);
      return { promise: Promise.resolve(), cancel() { calls.cancelled = true; } };
    },
  };
  const pdf = { numPages: 1, async getPage(pageNumber) { calls.getPage.push(pageNumber); return fakePage; }, destroy() { calls.destroyed = true; } };
  const loadingTask = { promise: Promise.resolve(pdf), destroy() { calls.loadingDestroyed = true; } };
  const pdfjs = {
    version: '4.10.38',
    GlobalWorkerOptions: {},
    getDocument(args) { calls.getDocument.push(args); return options.getDocumentTask || loadingTask; },
  };
  return { pdfjs, calls };
}

async function testPdfLazyOptionsAndOverlay() {
  const { pdfjs, calls } = makePdfjs();
  const requests = [];
  const harness = makeHarness({
    pdfjsLoader: async () => pdfjs,
    fetchImpl: async (url, opts) => {
      requests.push({ url, opts });
      if (url.startsWith('/api/kb/documents?')) return response(200, { documents: [{ document_id: 'doc/pdf', file_name: 'paper.pdf', media_type: 'application/pdf' }] });
      return response(200, { blocks: [{ block_id: 'b-pdf', ordinal: 0, text: 'source', locator: { kind: 'pdf_bbox', page: 1, bbox: [0.1, 0.2, 0.7, 0.8] }, heading_path: [], block_type: 'paragraph' }], chunks: [], anchors: [] });
    },
  });
  harness.elements['kb-tab-inspection'].dispatch('click');
  await flush();
  harness.elements['kb-inspection-document'].value = 'doc/pdf';
  harness.elements['kb-inspection-document'].dispatch('change');
  await flush(); await flush();
  assert.equal(calls.getDocument.length, 1);
  assert.equal(calls.getDocument[0].url, '/api/kb/documents/doc%2Fpdf/source');
  assert.deepEqual({
    isEvalSupported: calls.getDocument[0].isEvalSupported,
    enableXfa: calls.getDocument[0].enableXfa,
    useWorkerFetch: calls.getDocument[0].useWorkerFetch,
    stopAtErrors: calls.getDocument[0].stopAtErrors,
    disableAutoFetch: calls.getDocument[0].disableAutoFetch,
  }, PDF_GET_DOCUMENT_OPTIONS);
  assert.equal(pdfjs.GlobalWorkerOptions.workerSrc, PDFJS_WORKER_SRC);
  assert.equal(FakeIntersectionObserver.instance.options.root, harness.elements['kb-source-content']);
  assert.equal(calls.render.length, 0);
  FakeIntersectionObserver.instance.trigger();
  await flush(); await flush();
  assert.equal(calls.getPage[0], 1);
  assert.equal(calls.viewport[0].scale, 1);
  assert.equal(calls.text.length, 1);
  assert.equal(calls.render.length, 1);
  const page = harness.elements['kb-source-pdf'].childNodes[0];
  const overlay = page.childNodes[2].childNodes[0];
  assert.equal(overlay.getAttribute('data-block-id'), 'b-pdf');
  assert.equal(overlay.style.left, '10%');
  assert.equal(overlay.style.top, '20%');
  assert.equal(requests.every(({ url, opts }) => url.startsWith('/api/kb/documents') && !opts.method), true);
  assert.equal(requests.some(({ url }) => url.includes('reindex')), false);
  assert.equal(PDFJS_MODULE_URL, '/assets/vendor/pdfjs/pdf.min.mjs?v=4.10.38');
}

async function testPdfImportErrorAndCancellation() {
  const failed = makeHarness({
    pdfjsLoader: async () => { throw new Error('missing local module'); },
    fetchImpl: async (url) => url.startsWith('/api/kb/documents?')
      ? response(200, { documents: [{ document_id: 'd', file_name: 'd.pdf', media_type: 'application/pdf' }] })
      : response(200, { blocks: [], chunks: [], anchors: [] }),
  });
  failed.elements['kb-tab-inspection'].dispatch('click'); await flush();
  failed.elements['kb-inspection-document'].value = 'd'; failed.elements['kb-inspection-document'].dispatch('change');
  await flush(); await flush();
  assert.equal(failed.elements['kb-inspection-error'].getAttribute('data-error-code'), 'PDFJS_IMPORT_FAILED');

  const mismatchPdfjs = makePdfjs();
  mismatchPdfjs.pdfjs.workerVersion = '4.10.37';
  const mismatch = makeHarness({
    pdfjsLoader: async () => mismatchPdfjs.pdfjs,
    fetchImpl: async (url) => url.startsWith('/api/kb/documents?')
      ? response(200, { documents: [{ document_id: 'd', file_name: 'd.pdf', media_type: 'application/pdf' }] })
      : response(200, { blocks: [], chunks: [], anchors: [] }),
  });
  mismatch.elements['kb-tab-inspection'].dispatch('click'); await flush();
  mismatch.elements['kb-inspection-document'].value = 'd'; mismatch.elements['kb-inspection-document'].dispatch('change');
  await flush(); await flush();
  assert.equal(mismatch.elements['kb-inspection-error'].getAttribute('data-error-code'), 'PDFJS_WORKER_MISMATCH');

  let resolvePdf;
  const pendingTask = { promise: new Promise((resolve) => { resolvePdf = resolve; }), destroy() { this.cancelled = true; } };
  const { pdfjs, calls } = makePdfjs({ getDocumentTask: pendingTask });
  const pending = makeHarness({
    pdfjsLoader: async () => pdfjs,
    fetchImpl: async (url) => url.startsWith('/api/kb/documents?')
      ? response(200, { documents: [{ document_id: 'd', file_name: 'd.pdf', media_type: 'application/pdf' }] })
      : response(200, { blocks: [], chunks: [], anchors: [] }),
  });
  pending.elements['kb-tab-inspection'].dispatch('click'); await flush();
  pending.elements['kb-inspection-document'].value = 'd'; pending.elements['kb-inspection-document'].dispatch('change');
  await flush(); await flush();
  pending.controller.cancel();
  assert.equal(pendingTask.cancelled, true);
  assert.equal(calls.render.length, 0);
  resolvePdf({ numPages: 0 });
}

(async () => {
  await testPdfLazyOptionsAndOverlay();
  await testPdfImportErrorAndCancellation();
  console.log('frontend PDF renderer contract: PASS (local module, worker/options, lazy canvas/text/bbox, error/cancel, GET allowlist)');
})().catch((error) => { console.error(error); process.exitCode = 1; });
