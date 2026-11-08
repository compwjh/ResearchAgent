'use strict';

// Behaviour probe for the task-C short-text helpers. Each frontend entry defines
// the same two tiny helpers locally (no extra <script>, no load-order coupling);
// we slice their source out of the real files and execute them in a VM so the
// assertions exercise production code rather than a copy.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const FRONTEND = path.resolve(__dirname, '../../frontend');
const FILES = [
  'literature-maps.js',
  'research-tasks.js',
  'app.js',
  'conversation-research.js',
];

function sliceFunction(source, name) {
  const marker = new RegExp('function\\s+' + name + '\\s*\\(');
  const found = marker.exec(source);
  assert.ok(found, `${name} must be declared in the source under test`);
  const brace = source.indexOf('{', found.index);
  let depth = 0;
  for (let i = brace; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(found.index, i + 1);
    }
  }
  throw new Error(`unbalanced braces while slicing ${name}`);
}

function fakeElement() {
  return {
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
}

for (const file of FILES) {
  const source = fs.readFileSync(path.join(FRONTEND, file), 'utf8');
  const bundle = [
    sliceFunction(source, 'formatShortHash'),
    sliceFunction(source, 'withTooltip'),
    'globalThis.__helpers = { formatShortHash, withTooltip };',
  ].join('\n');
  const context = vm.createContext({});
  vm.runInContext(bundle, context);
  const { formatShortHash, withTooltip } = context.__helpers;

  assert.equal(
    formatShortHash('0123456789abcdef0123456789abcdef'),
    '01234567…',
    `${file}: a 32+ char hash must show the 8-char short form plus an ellipsis`,
  );
  assert.equal(formatShortHash('short'), 'short', `${file}: short values must not gain an ellipsis`);
  assert.equal(formatShortHash(''), '', `${file}: empty value is safe`);
  assert.equal(formatShortHash(null), '', `${file}: null is safe`);
  assert.equal(formatShortHash('abcdefghijk', 4), 'abcd…', `${file}: custom length n`);

  const el = fakeElement();
  const full = `${'a'.repeat(80)}<b>not-html</b>`;
  assert.equal(withTooltip(el, full), el, `${file}: withTooltip returns the element for chaining`);
  assert.equal(el.title, full, `${file}: native title keeps the full literal text`);
  assert.equal(el.attributes['aria-label'], full, `${file}: aria-label mirrors the full text`);
  assert.equal(el.textContent, undefined, `${file}: helper must not rewrite textContent`);
  assert.equal(withTooltip(null, full), null, `${file}: null element is safe`);
}

console.log('short-text helpers: PASS (4 entries, hash truncation + native tooltip, verbatim full text)');
