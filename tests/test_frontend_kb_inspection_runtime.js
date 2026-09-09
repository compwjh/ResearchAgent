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
    this.textContent = '';
    this.tabIndex = -1;
    this.scrollTop = 0;
    this.className = '';
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
  removeChild(child) { this.childNodes = this.childNodes.filter((value) => value !== child); child.parentNode = null; }
  addEventListener(type, callback) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(callback); }
  dispatch(type, extra = {}) {
    const event = { type, target: this, preventDefault() { this.defaultPrevented = true; }, ...extra };
    (this.listeners.get(type) || []).forEach((callback) => callback(event));
    return event;
  }
  focus() { this.ownerDocument.activeElement = this; }
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
    return false;
  }
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

function response(status, payload, retryAfter = null) {
  return {
    status,
    headers: { get(name) { return name.toLowerCase() === 'retry-after' ? retryAfter : null; } },
    async json() { return payload; },
  };
}

function makeHarness(fetchImpl, renderer = null) {
  const documentRef = new FakeDocument();
  const ids = [
    ['kb-tabs', 'div'], ['kb-tab-qa', 'button', { role: 'tab', 'aria-controls': 'kb-panel-qa', 'aria-selected': 'true' }],
    ['kb-tab-inspection', 'button', { role: 'tab', 'aria-controls': 'kb-panel-inspection', 'aria-selected': 'false' }],
    ['kb-panel-qa', 'section'], ['kb-panel-inspection', 'section'],
    ['kb-inspection-document', 'select'], ['kb-inspection-version-group', 'fieldset'],
    ['kb-inspection-state', 'div'], ['kb-inspection-maintenance', 'p'], ['kb-inspection-finalize', 'p'],
    ['kb-inspection-loading', 'p'], ['kb-inspection-error', 'p'], ['kb-source-empty', 'p'],
    ['kb-source-document', 'div'], ['kb-source-pdf', 'div'], ['kb-source-markdown', 'div'],
    ['kb-source-meta', 'p'], ['kb-source-kind', 'span'], ['kb-chunk-content', 'div'],
    ['kb-chunk-empty', 'p'], ['kb-chunk-meta', 'p'], ['kb-chunk-status', 'span'],
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
  const v2 = documentRef.add('kb-inspection-chunker-v2', 'input', { name: 'kb-inspection-chunker', value: 'v2' });
  v1.checked = true; v2.checked = false; elements['kb-inspection-version-group'].append(v1, v2);
  const controller = createKbInspectionController({ fetch: fetchImpl, AbortController }, { document: documentRef, renderer: renderer || { renderMarkdownBlock: (dto) => { const node = documentRef.createElement('article'); node.setAttribute('data-block-id', dto.block_id); return node; } } });
  return { controller, documentRef, elements, v1, v2 };
}

async function flush() { await new Promise((resolve) => setImmediate(resolve)); }

async function testTabsPaginationAndSafety() {
  const calls = [];
  const queue = [
    response(200, { documents: [{ document_id: 'doc-1', file_name: '<unsafe>.md', media_type: 'text/markdown' }], next_cursor: 'docs-2', total: 2 }),
    response(200, { documents: [{ document_id: 'doc-2', file_name: 'second.pdf', media_type: 'application/pdf' }], next_cursor: null, total: 2 }),
    response(200, { blocks: [{ block_id: 'b1', ordinal: 0, text: '# Safe', locator: {}, heading_path: ['H'], block_type: 'heading' }], chunks: [{ chunker: 'v1', chunk_index: 0, text: '<chunk>' }], anchors: [{ block_id: 'b1', chunker: 'v1', chunk_index: 0 }], next_cursor: 'opaque-1', total: { blocks: 2, chunks: 2, anchors: 2 } }),
    response(200, { blocks: [{ block_id: 'b2', ordinal: 1, text: 'body', locator: {}, heading_path: [], block_type: 'paragraph' }], chunks: [{ chunker: 'v1', chunk_index: 1, text: 'tail' }], anchors: [{ block_id: 'b2', chunker: 'v1', chunk_index: 1 }], next_cursor: null, total: { blocks: 2, chunks: 2, anchors: 2 } }),
    response(200, { blocks: [], chunks: [], anchors: [], next_cursor: null, total: { blocks: 0, chunks: 0, anchors: 0 } }),
  ];
  const harness = makeHarness(async (url, options) => { calls.push({ url, options }); return queue.shift(); });
  const { elements, documentRef, v1, v2 } = harness;
  assert.equal(elements['kb-chunk-empty'].parentNode, elements['kb-chunk-content']);
  assert.equal(elements['kb-chunk-empty'].hidden, false);
  elements['kb-tab-inspection'].dispatch('click');
  await flush();
  assert.equal(elements['kb-inspection-document'].childNodes.length, 3);
  assert.equal(elements['kb-inspection-document'].childNodes[1].textContent, '<unsafe>.md · text/markdown');
  assert.equal(elements['kb-inspection-document'].childNodes[2].textContent, 'second.pdf · application/pdf');
  assert.ok(calls[0].url.includes('/api/kb/documents?limit=100'));
  assert.ok(calls[1].url.includes('cursor=docs-2'));
  elements['kb-inspection-document'].value = 'doc-1';
  elements['kb-inspection-document'].dispatch('change');
  await flush(); await flush();
  assert.equal(calls.length, 4);
  assert.ok(calls[2].url.includes('chunker=v1'));
  assert.ok(calls[3].url.includes('cursor=opaque-1'));
  assert.equal(calls.every(({ options }) => !options.method), true);
  assert.equal(elements['kb-inspection-maintenance'].hidden, true);
  assert.equal(elements['kb-inspection-error'].hidden, true);
  assert.equal(elements['kb-chunk-content'].childNodes.length, 3);
  const chunkItems = elements['kb-chunk-content'].childNodes.filter((node) => node.className === 'kb-chunk-item');
  assert.equal(chunkItems.length, 2);
  assert.equal(chunkItems[0].getAttribute('data-chunk-id'), 'v1:0');
  assert.equal(chunkItems[0].getAttribute('data-block-ids'), 'b1');
  assert.equal(elements['kb-chunk-empty'].parentNode, elements['kb-chunk-content']);
  assert.equal(elements['kb-chunk-empty'].hidden, true);
  assert.equal(elements['kb-source-markdown'].childNodes.length, 2);
  assert.equal(documentRef.activeElement, null);
  elements['kb-inspection-chunk-tab'].dispatch('click');
  assert.equal(elements['kb-inspection-layout'].getAttribute('data-active-pane'), 'chunks');
  elements['kb-inspection-chunk-tab'].dispatch('keydown', { key: 'ArrowLeft' });
  assert.equal(elements['kb-inspection-layout'].getAttribute('data-active-pane'), 'source');
  v1.checked = false; v2.checked = true; v2.dispatch('change');
  await flush();
  assert.ok(calls[4].url.includes('chunker=v2'));
}

async function testMaintenanceAndCancellation() {
  const queue = [
    response(200, { documents: [{ document_id: 'doc-1', file_name: 'a.pdf', media_type: 'application/pdf' }], next_cursor: null, total: 1 }),
    response(409, { error_code: 'INDEX_REBUILD_REQUIRED', message: '<unsafe message>', retryable: false }),
  ];
  const calls = [];
  const harness = makeHarness(async (url, options) => { calls.push({ url, options }); return queue.shift(); });
  const { elements } = harness;
  elements['kb-tab-inspection'].dispatch('click'); await flush();
  elements['kb-inspection-document'].value = 'doc-1'; elements['kb-inspection-document'].dispatch('change'); await flush();
  assert.equal(elements['kb-inspection-maintenance'].hidden, false);
  assert.equal(elements['kb-inspection-error'].hidden, true);
  assert.equal(elements['kb-inspection-error'].textContent.includes('<unsafe message>'), false);
  assert.equal(calls.some(({ url }) => url.includes('/reindex')), false);

  const pending = [];
  const cancelHarness = makeHarness(async (url, options) => {
    pending.push({ url, options });
    if (url.startsWith('/api/kb/documents?')) return response(200, { documents: [{ document_id: 'doc-1', file_name: 'a.md', media_type: 'text/markdown' }], next_cursor: null, total: 1 });
    return response(202, { error_code: 'INSPECTION_BUILDING', message: 'building', retryable: true }, '30');
  });
  cancelHarness.elements['kb-tab-inspection'].dispatch('click'); await flush();
  cancelHarness.elements['kb-inspection-document'].value = 'doc-1'; cancelHarness.elements['kb-inspection-document'].dispatch('change'); await flush();
  cancelHarness.controller.cancel(); await flush();
  assert.equal(pending.length, 2);
  assert.equal(pending[1].options.signal.aborted, true);
  assert.equal(pending.some(({ url }) => url.includes('/reindex')), false);
}

(async () => {
  await testTabsPaginationAndSafety();
  await testMaintenanceAndCancellation();
  console.log('frontend runtime contract: PASS (tabs, roving keyboard, pagination, status, cancellation, GET-only safety)');
})().catch((error) => { console.error(error); process.exitCode = 1; });
