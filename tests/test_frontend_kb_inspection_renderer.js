'use strict';

const assert = require('node:assert/strict');
const marked = require('../frontend/vendor/marked.min.js');
const {
  renderMarkdownBlock,
  validateSourceBlock,
} = require('../frontend/kb-inspection.js');

class FakeNode {
  constructor(tagName, nodeType = 1, value = '') {
    this.tagName = tagName;
    this.nodeType = nodeType;
    this.parentNode = null;
    this.childNodes = [];
    this.attributes = new Map();
    this.className = '';
    this.tabIndex = -1;
    this._text = value;
  }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }

  appendChild(node) {
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }

  replaceChild(next, previous) {
    const index = this.childNodes.indexOf(previous);
    if (index < 0) throw new Error('child not found');
    next.parentNode = this;
    this.childNodes[index] = next;
    previous.parentNode = null;
    return previous;
  }

  replaceWith(next) {
    if (this.parentNode) this.parentNode.replaceChild(next, this);
  }

  set textContent(value) {
    this.childNodes = [];
    this._text = String(value ?? '');
  }

  get textContent() {
    if (this.nodeType === 3) return this._text;
    return this._text + this.childNodes.map((child) => child.textContent).join('');
  }
}

const documentRef = {
  createElement(tagName) {
    return new FakeNode(tagName);
  },
};

function textNode(value) { return new FakeNode('#text', 3, value); }

function parseAttributes(raw) {
  const attrs = {};
  const pattern = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;
  let match;
  while ((match = pattern.exec(raw))) attrs[match[1].toLowerCase()] = match[2] ?? match[3] ?? match[4];
  return attrs;
}

function parseSanitizedHtml(html) {
  const fragment = new FakeNode('#fragment', 11);
  const stack = [fragment];
  const tokenPattern = /<\/?[a-z][^>]*>|[^<]+/gi;
  let match;
  while ((match = tokenPattern.exec(html))) {
    const token = match[0];
    if (token.startsWith('</')) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    if (!token.startsWith('<')) {
      stack[stack.length - 1].appendChild(textNode(token));
      continue;
    }
    const opening = token.match(/^<([a-z][a-z0-9]*)\b([^>]*)>/i);
    if (!opening) continue;
    const node = new FakeNode(opening[1].toLowerCase());
    const attrs = parseAttributes(opening[2]);
    Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, value));
    stack[stack.length - 1].appendChild(node);
    if (node.tagName !== 'img' && !token.endsWith('/>')) stack.push(node);
  }
  return fragment;
}

function walk(node, result = []) {
  result.push(node);
  node.childNodes.forEach((child) => walk(child, result));
  return result;
}

function sourceBlock(overrides = {}) {
  return {
    block_id: 'block-<unsafe>',
    ordinal: 2,
    text: '# Heading\n\n<img src="https://remote.invalid/image.png" srcset="x 2x" onerror="alert(1)">\n\n<script>alert(1)</script>',
    locator: { kind: 'markdown_lines', start_line: 1, end_line: 4 },
    heading_path: ['<Unsafe heading>'],
    block_type: 'paragraph',
    ...overrides,
  };
}

function testPipelineAndImageReplacement() {
  const calls = { marked: 0, sanitize: 0, errors: [] };
  const purify = {
    sanitize(html, options) {
      calls.sanitize += 1;
      assert.match(html, /<h1>Heading<\/h1>/);
      assert.ok(options.FORBID_TAGS.includes('script'));
      assert.ok(!options.FORBID_TAGS.includes('img'), 'img must survive detached sanitization for replacement');
      return html
        .replace(/<script[\s\S]*?<\/script>/gi, '')
        .replace(/\sonerror="[^"]*"/gi, '');
    },
  };
  const markedSpy = {
    parse(text, options) {
      calls.marked += 1;
      assert.equal(text, sourceBlock().text);
      assert.deepEqual(options, { gfm: true, breaks: true });
      return marked.parse(text, options);
    },
  };

  const block = renderMarkdownBlock(sourceBlock(), {
    document: documentRef,
    marked: markedSpy,
    DOMPurify: purify,
    parseSanitizedHtml,
    onError: (error) => calls.errors.push(error),
  });

  assert.equal(calls.marked, 1);
  assert.equal(calls.sanitize, 1);
  assert.deepEqual(calls.errors, []);
  assert.equal(block.getAttribute('data-block-id'), 'block-<unsafe>');
  assert.equal(block.getAttribute('data-ordinal'), '2');
  assert.equal(block.tabIndex, 0);
  assert.equal(block.getAttribute('aria-label'), '原文块 3');
  assert.equal(block.childNodes[0].textContent, 'paragraph · <Unsafe heading>');
  assert.equal(block.childNodes[0].childNodes.length, 0, 'metadata must be textContent, not HTML');

  const nodes = walk(block);
  assert.equal(nodes.filter((node) => node.tagName === 'img').length, 0);
  assert.equal(nodes.filter((node) => node.tagName === 'script').length, 0);
  const placeholder = nodes.find((node) => node.className === 'kb-image-placeholder');
  assert.ok(placeholder, 'image placeholder must be mounted');
  assert.match(placeholder.textContent, /^图片已阻止：https:\/\/remote\.invalid\/image\.png$/);
  assert.equal(placeholder.getAttribute('src'), null);
  assert.equal(placeholder.getAttribute('srcset'), null);
  assert.equal(block.childNodes[1].getAttribute('data-renderer-status'), 'ready');

  const longAddress = 'x'.repeat(3000);
  const longBlock = renderMarkdownBlock(sourceBlock({ text: `<img src="${longAddress}">` }), {
    document: documentRef,
    marked,
    DOMPurify: { sanitize: (html) => html },
    parseSanitizedHtml,
  });
  const longPlaceholder = walk(longBlock).find((node) => node.className === 'kb-image-placeholder');
  assert.equal(longPlaceholder.textContent, `图片已阻止：${'x'.repeat(2048)}`);
}

function testRendererUnavailableFallback() {
  const errors = [];
  const block = renderMarkdownBlock(sourceBlock({ text: '<script>literal</script> & text' }), {
    document: documentRef,
    marked: null,
    DOMPurify: null,
    onError: (error) => errors.push(error),
  });
  const body = block.childNodes[1];
  assert.equal(body.textContent, '<script>literal</script> & text');
  assert.equal(body.getAttribute('data-renderer-status'), 'fallback');
  assert.equal(body.getAttribute('data-error-code'), 'RENDERER_UNAVAILABLE');
  assert.deepEqual(errors, [{ error_code: 'RENDERER_UNAVAILABLE', detail: 'Marked or DOMPurify is unavailable' }]);
}

function testDtoContract() {
  assert.throws(() => validateSourceBlock({}), /SourceBlock missing/);
  assert.throws(() => validateSourceBlock(sourceBlock({ block_id: '' })), /block_id/);
  assert.throws(() => validateSourceBlock(sourceBlock({ ordinal: -1 })), /ordinal/);
  assert.throws(() => validateSourceBlock(sourceBlock({ text: null })), /text/);
  assert.throws(() => validateSourceBlock(sourceBlock({ locator: null })), /locator/);
}

testPipelineAndImageReplacement();
testRendererUnavailableFallback();
testDtoContract();
console.log('frontend renderer contract: PASS (pipeline, hostile HTML/image, fallback, DTO validation)');
