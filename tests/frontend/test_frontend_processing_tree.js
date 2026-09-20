'use strict';

const assert = require('node:assert/strict');
const { createProcessingTree, normalizeStep } = require('../../frontend/processing-tree.js');

class FakeElement {
  constructor(tagName, documentRef) {
    this.tagName = tagName.toLowerCase(); this.ownerDocument = documentRef; this.parentNode = null;
    this.childNodes = []; this.attributes = new Map(); this.listeners = new Map(); this.dataset = {};
    this.className = ''; this.classList = { contains: (name) => this.className.split(/\s+/).includes(name) };
    this.hidden = false; this.textContent = ''; this.scrollTop = 0; this.scrollHeight = 200; this.clientHeight = 100;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  appendChild(node) { node.parentNode = this; this.childNodes.push(node); return node; }
  append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
  replaceChildren(...nodes) { this.childNodes = []; nodes.forEach((node) => this.appendChild(node)); }
  addEventListener(type, handler) { this.listeners.set(type, handler); }
  dispatch(type) { this.listeners.get(type)?.({ type, target: this }); }
  matches(selector) {
    if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
    const attr = selector.match(/^\[data-([\w-]+)(?:="([^"]*)")?\]$/);
    if (attr) { const key = attr[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase()); return this.dataset[key] !== undefined && (attr[2] === undefined || this.dataset[key] === attr[2]); }
    return false;
  }
  querySelectorAll(selector) { const out = []; const visit = (node) => { node.childNodes.forEach((child) => { if (child.matches?.(selector)) out.push(child); visit(child); }); }; visit(this); return out; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { let node = this; while (node) { if (selector.split(',').some((part) => node.matches?.(part.trim()))) return node; node = node.parentNode; } return null; }
}

class FakeDocument { createElement(tag) { return new FakeElement(tag, this); } }

const storage = new Map();
const store = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)) };
const documentRef = new FakeDocument();
const shell = documentRef.createElement('section'); shell.className = 'conversation-processing';
const list = documentRef.createElement('div'); shell.appendChild(list);
const tree = createProcessingTree({ document: documentRef, container: list, storageKey: 'message-1', storage: store });

assert.equal(normalizeStep({ label: '<unsafe>', node_type: 'agent', node_key: 'agent-1' }).label, '<unsafe>');
tree.upsert({ step_id: 'leaf-1', parent_step_id: 'agent-1', node_type: 'tool', node_key: 'tool-1', status: 'running', label: '<tool>' });
assert.equal(list.querySelectorAll('.conversation-processing-node').length, 0, 'orphan child stays cached');
tree.upsert({ step_id: 'phase-1', node_type: 'phase', node_key: 'phase-1', status: 'running', label: 'Research' });
tree.upsert({ step_id: 'agent-1', parent_step_id: 'phase-1', node_type: 'agent', node_key: 'agent-1', status: 'running', label: 'Agent' });
assert.equal(list.querySelectorAll('.conversation-processing-node').length, 3);
tree.upsert({ step_id: 'leaf-1', parent_step_id: 'agent-1', node_type: 'tool', node_key: 'tool-1', source_event_id: 'research-event:1:3', status: 'completed', label: '<tool>', summary: '<summary>' });
assert.equal(list.querySelectorAll('.conversation-processing-node').length, 3, 'node_key/source_event_id upsert does not duplicate');
const labels = list.querySelectorAll('.conversation-processing-node-label').map((node) => node.textContent);
assert(labels.includes('<tool>'), 'dynamic labels use textContent boundary');
tree.upsert({ node_key: 'phase-1', source_event_id: 'research-event:1:4', status: 'completed', label: 'Research done' });
tree.upsert({ node_key: 'phase-1', source_event_id: 'research-event:1:5', status: 'running', label: 'late running' });
assert.equal(tree.snapshot().find((node) => node.node_key === 'phase-1').status, 'completed', 'terminal status is a barrier');
tree.setSyncing(true);
assert.equal(list.querySelectorAll('.conversation-processing-syncing').length, 1);
tree.finalize('completed', 'done');
assert.equal(tree.isRunning(), false);
tree.upsert({ node_key: 'phase-1', status: 'failed', summary: 'failed' });
assert.equal(tree.snapshot().find((node) => node.node_key === 'phase-1').status, 'completed', 'completed terminal cannot be overwritten by failed');
tree.upsert({ node_key: 'phase-1', status: 'completed', summary: 'late completed' });
assert.equal(tree.snapshot().find((node) => node.node_key === 'phase-1').status, 'completed', 'same terminal remains idempotent');
const terminalTree = createProcessingTree({ document: documentRef, container: documentRef.createElement('div'), storageKey: 'terminal', storage: store });
terminalTree.upsert({ node_key: 'failed-root', status: 'failed' });
terminalTree.upsert({ node_key: 'failed-root', status: 'completed' });
assert.equal(terminalTree.snapshot()[0].status, 'failed', 'failed terminal cannot be overwritten by completed');
terminalTree.upsert({ node_key: 'partial-root', status: 'partial' });
terminalTree.upsert({ node_key: 'partial-root', status: 'cancelled' });
assert.equal(terminalTree.snapshot().find((node) => node.node_key === 'partial-root').status, 'partial', 'partial terminal cannot be overwritten by cancelled');

const phaseButton = list.querySelector('.conversation-processing-node-toggle');
phaseButton.dispatch('click');
assert.equal(storage.has('processing-tree:message-1'), true, 'manual expansion is persisted');
store.setItem('processing-tree:message-2', JSON.stringify({ 'root-2': false }));
const list2 = documentRef.createElement('div'); const tree2 = createProcessingTree({ document: documentRef, container: list2, storageKey: 'message-2', storage: store });
tree2.upsertMany([{ node_key: 'root-2', node_type: 'operation', status: 'completed' }, { node_key: 'child-2', parent_step_id: 'root-2', node_type: 'operation', status: 'completed' }]);
assert.equal(list2.querySelector('.conversation-processing-node-toggle').getAttribute('aria-expanded'), 'false', 'manual expansion is restored');
assert.equal(list2.querySelectorAll('.conversation-processing-node-toggle')[1].getAttribute('aria-disabled'), 'true', 'leaf has explicit ARIA disabled state');
const ordered = createProcessingTree({ document: documentRef, container: documentRef.createElement('div'), storageKey: 'message-3', storage: store });
ordered.upsertMany([{ node_key: 'v1-2', logical_sequence: 2, label: 'second' }, { node_key: 'v1-1', logical_sequence: 1, label: 'first' }]);
assert.equal(ordered.snapshot()[0].display_order, 2, 'v1 display order remains available to sort');
const stable = createProcessingTree({ document: documentRef, container: documentRef.createElement('div'), storageKey: 'stable', storage: store });
stable.upsertMany([{ node_key: 'second' }, { node_key: 'first' }]);
assert.deepEqual(stable.snapshot().map((node) => node.node_key), ['second', 'first'], 'v1 without logical_sequence keeps insertion order');
const scrollPanel = documentRef.createElement('section'); scrollPanel.className = 'research-column-body'; scrollPanel.scrollHeight = 300; scrollPanel.clientHeight = 100; scrollPanel.scrollTop = 20;
const scrollList = documentRef.createElement('div'); scrollPanel.appendChild(scrollList);
const scrollTree = createProcessingTree({ document: documentRef, container: scrollList, storageKey: 'scroll', storage: store });
scrollTree.upsert({ node_key: 'scroll-root', status: 'running', label: 'scroll-safe' });
assert.equal(scrollPanel.scrollTop, 20, 'upward reader position is preserved');
scrollPanel.scrollTop = 220;
scrollTree.upsert({ node_key: 'scroll-child', parent_step_id: 'scroll-root', status: 'running', label: 'follow' });
assert.equal(scrollPanel.scrollTop, 300, 'near-bottom reader follows incremental content');
console.log('processing tree contract: PASS (v1/v2 adjacency, orphan cache, idempotent upsert, terminal barrier, syncing, XSS, localStorage)');
