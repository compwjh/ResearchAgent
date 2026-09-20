'use strict';

const assert = require('node:assert/strict');
const { createSourceRenderer, normalizeSources, safeSourceUrl } = require('../../frontend/conversation-research.js');

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toLowerCase();
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.listeners = new Map();
    this.dataset = {};
    this.hidden = false;
    this.textContent = '';
    this.className = '';
    this.classList = {
      toggle: (name, enabled) => {
        const classes = new Set(this.className.split(/\s+/).filter(Boolean));
        if (enabled) classes.add(name); else classes.delete(name);
        this.className = [...classes].join(' ');
      },
    };
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
  }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  appendChild(node) { node.parentNode = this; this.childNodes.push(node); return node; }
  append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
  replaceChildren(...nodes) { this.childNodes = []; this.append(...nodes); }
  addEventListener(type, handler) { this.listeners.set(type, handler); }
  dispatch(type) { this.listeners.get(type)?.({ type, target: this }); }
  matches(selector) {
    if (/^[a-z]+$/.test(selector)) return this.tagName === selector;
    if (selector === '[data-source-index]') return this.attributes.has('data-source-index') || this.dataset.sourceIndex != null;
    if (selector === '.conversation-source-detail') return this.className.split(/\s+/).includes('conversation-source-detail');
    if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
    return false;
  }
  querySelectorAll(selector) {
    const result = [];
    const visit = (node) => {
      node.childNodes.forEach((child) => { if (child.matches?.(selector)) result.push(child); visit(child); });
    };
    visit(this);
    return result;
  }
}

const documentRef = { createElement: (tagName) => new FakeElement(tagName) };
const container = documentRef.createElement('section');
const renderer = createSourceRenderer({ document: documentRef, container });

assert.deepEqual(normalizeSources(null), []);
assert.equal(normalizeSources(Array.from({ length: 7 }, () => ({}))).length, 5);
assert.equal(safeSourceUrl('/api/kb/documents/doc-1/source'), '/api/kb/documents/doc-1/source');
assert.equal(safeSourceUrl('https://evil.invalid/source'), '');

renderer.render(Array.from({ length: 7 }, (_, index) => ({
  document_id: `doc-${index}`,
  file_name: `<unsafe-${index}>.md`,
  page: index + 1,
  chunk_id: `chunk-${index}`,
  score: 0.9,
  text: '<img src=x onerror=alert(1)>',
  source_url: index === 0 ? '/api/kb/documents/doc-0/source' : 'https://evil.invalid/source',
})));

const buttons = container.querySelectorAll('[data-source-index]');
const details = container.querySelectorAll('.conversation-source-detail');
assert.equal(buttons.length, 5);
assert.deepEqual(buttons.map((button) => button.textContent), ['1', '2', '3', '4', '5']);
assert.equal(details[0].querySelectorAll('a').length, 1);
const sourceText = details[0].querySelectorAll('.conversation-source-detail-value').map((node) => node.textContent).join('\n');
assert.match(sourceText, /<img src=x onerror=alert\(1\)>/);
assert.equal(details[1].querySelectorAll('a').length, 0, 'external links must not be mounted');

buttons[0].dispatch('click');
assert.equal(details[0].hidden, false);
assert.equal(buttons[0].getAttribute('aria-expanded'), 'true');
buttons[1].dispatch('click');
assert.equal(details[0].hidden, true, 'only one source may be expanded');
assert.equal(details[1].hidden, false);
buttons[1].dispatch('click');
assert.equal(details[1].hidden, true, 'clicking active source collapses it');

console.log('conversation research contract: PASS (deferred-safe renderer, 0-5 cap, mutual expansion, XSS text boundary)');
