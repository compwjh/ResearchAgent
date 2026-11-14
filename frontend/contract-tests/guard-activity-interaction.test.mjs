// Spec050 Task04 契约测试：确认界面交互、刷新恢复、事件去重与未知状态降级。
// 零依赖：Node 内置 vm + 轻量假 DOM，直接加载真实源码 guard-activity.js。
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const FRONTEND = path.resolve(import.meta.dirname, '..');

class FakeEl {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.dataset = {};
    this._text = '';
    this.className = '';
    this.type = '';
    this.disabled = false;
    this.hidden = false;
    this.handlers = {};
    this.attributes = {};
    this.id = '';
    this.parentNode = null;
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join('');
  }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  addEventListener(evt, fn) { (this.handlers[evt] ||= []).push(fn); }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; }
  removeAttribute(k) { delete this.attributes[k]; }
  closest(selector) {
    let node = this;
    while (node) {
      if (selector.startsWith('.') && String(node.className || '').split(/\s+/).includes(selector.slice(1))) return node;
      node = node.parentNode;
    }
    return null;
  }
  _walk(out = []) {
    for (const child of this.children) { out.push(child); child._walk(out); }
    return out;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    const nodes = this._walk();
    const classTokens = selector.match(/\.([A-Za-z][\w-]*)/g) || [];
    const cls = classTokens.length ? classTokens[classTokens.length - 1].slice(1) : null;
    const tag = cls ? null : (selector.match(/^([A-Za-z][\w-]*)/) || [])[1] || null;
    const byAttr = selector.match(/\[data-([\w-]+)\]/);
    return nodes.filter((n) => {
      if (cls && !String(n.className || '').split(/\s+/).includes(cls)) return false;
      if (tag && n.tagName !== tag.toUpperCase()) return false;
      if (byAttr && !(byAttr[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase()) in n.dataset)) return false;
      return cls || tag || byAttr;
    });
  }
  click() { (this.handlers.click || []).forEach((fn) => fn.call(this)); }
}

function makeDom() {
  const root = new FakeEl('body');
  const byId = new Map();
  const findById = (id) => [root, ...root._walk()].find((n) => n.id === id) || null;
  const document = {
    readyState: 'complete',
    body: root,
    documentElement: root,
    getElementById: (id) => byId.get(id) || findById(id),
    createElement: (tag) => new FakeEl(tag),
    querySelector: (sel) => root.querySelector(sel),
    addEventListener: () => {},
  };
  return { document, byId, root };
}

function loadModule(document, fetchImpl) {
  const source = fs.readFileSync(path.join(FRONTEND, 'guard-activity.js'), 'utf8');
  const sandbox = {
    document,
    fetch: fetchImpl,
    Promise, Object, Array, Number, String, JSON, Error,
    encodeURIComponent, console,
    setInterval: () => 1,
    clearInterval: () => {},
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: 'guard-activity.js' });
  return sandbox;
}

const jsonResponse = (payload, ok = true) => Promise.resolve({
  ok,
  status: ok ? 200 : 409,
  json: () => Promise.resolve(payload),
});

const ACTIONS = [{
  action_ref: 'gact_1', task_id: 'task-1', tool_name: 'download_and_import_paper',
  target_summary: 'download_and_import_paper:usenix.org:A Paper',
  args_hash: 'hash-1', status: 'pending', scope_version: 'scope-v1',
  created_at: '2026-11-14T00:00:00Z',
  risk: { label: 1, reason_code: 'INJECTION_RISK_DETECTED', requires_hold: false, evidence_ref: 'pdf:abc' },
}];

const EVENTS = [
  { event_id: 'gev_1', status: 'blocked', reason_code: 'CONFIRMATION_REQUIRED', module: 'action-guard' },
  { event_id: 'gev_1', status: 'blocked', reason_code: 'CONFIRMATION_REQUIRED', module: 'action-guard' },
  { event_id: 'gev_2', status: 'unknown_status', reason_code: 'NEW_REASON', module: 'risk-detection' },
];

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function setup(actionRecords, eventRecords = []) {
  const dom = makeDom();
  const calls = [];
  const sandbox = loadModule(dom.document, (url, options) => {
    calls.push({ url, options });
    if (options && options.method === 'POST') {
      return jsonResponse({ reason_code: 'ACTION_ALLOWED', outcome: 'allow' });
    }
    return jsonResponse(
      url.includes('/actions') ? { records: actionRecords } : { records: eventRecords },
    );
  });
  sandbox.GuardActivity.mount();
  await settle();
  return { dom, sandbox, calls, cleanup: () => sandbox.GuardActivity.resetForTests() };
}

describe('guard activity contract', () => {
  test('mount 幂等，确认卡片含三个选项与风险提示', async () => {
    const { dom, sandbox, cleanup } = await setup(ACTIONS, EVENTS);
    const first = sandbox.GuardActivity.mount();
    const second = sandbox.GuardActivity.mount();
    assert.equal(first, second);
    await settle();
    const cards = first.querySelectorAll('.guard-action-card');
    assert.equal(cards.length, 1);
    const choices = first.querySelectorAll('button')
      .filter((b) => b.attributes['data-choice']);
    assert.deepEqual(choices.map((b) => b.attributes['data-choice']).sort(), ['allow', 'cancel', 'reject']);
    assert.ok(cards[0].textContent.includes('来源含注入风险'));
    assert.ok(cards[0].textContent.includes('证据定位'));
    cleanup();
  });

  test('事件按 event_id 去重，未知状态/原因安全降级', async () => {
    const { dom, cleanup } = await setup([], EVENTS);
    const root = dom.document.getElementById('guard-activity-root');
    const items = root.querySelectorAll('.guard-activity-event');
    assert.equal(items.length, 2, 'duplicate event_id must be collapsed');
    assert.ok(items.some((i) => i.textContent.includes('未知状态')));
    // 未知原因码原样显示以便诊断，但不做任何动作、不注入 HTML。
    assert.ok(items.some((i) => i.textContent.includes('NEW_REASON')));
    cleanup();
  });

  test('刷新后从服务端重建状态，不依赖内存中的旧动作', async () => {
    const dom = makeDom();
    let serverActions = ACTIONS;
    const sandbox = loadModule(dom.document, (url) => {
      if (!url.includes('/actions')) return jsonResponse({ records: [] });
      return jsonResponse({ records: serverActions });
    });
    sandbox.GuardActivity.mount();
    await settle();
    const root = dom.document.getElementById('guard-activity-root');
    assert.equal(root.querySelectorAll('.guard-action-card').length, 1);
    serverActions = [];
    await sandbox.GuardActivity.refresh();
    assert.equal(root.querySelectorAll('.guard-action-card').length, 0);
    assert.ok(root.querySelector('.guard-activity-actions').textContent.includes('没有待确认'));
    sandbox.GuardActivity.resetForTests();
  });

  test('确认请求绑定 action_ref 与 args_hash，成功后按钮禁用', async () => {
    const { dom, sandbox, calls, cleanup } = await setup(ACTIONS);
    const root = dom.document.getElementById('guard-activity-root');
    const allow = root.querySelectorAll('button').find((b) => b.attributes['data-choice'] === 'allow');
    assert.ok(allow, 'allow button must exist');
    allow.click();
    await settle();
    const post = calls.find((c) => c.options && c.options.method === 'POST');
    assert.ok(post);
    assert.equal(post.url, '/api/guard/actions/gact_1/decision');
    const body = JSON.parse(post.options.body);
    assert.equal(body.choice, 'allow');
    assert.equal(body.args_hash, 'hash-1');
    const card = root.querySelector('.guard-action-card');
    assert.ok(card.querySelectorAll('button').every((b) => b.disabled));
    cleanup();
  });

  test('服务端文本不注入 HTML：恶意 target_summary 只作为文本', async () => {
    const malicious = [{
      ...ACTIONS[0],
      target_summary: '<img src=x onerror=alert(1)>',
      tool_name: '<script>alert(1)</script>',
      risk: { label: 0, reason_code: 'BENIGN_DETECTED', requires_hold: false, evidence_ref: '' },
    }];
    const { dom, cleanup } = await setup(malicious);
    const root = dom.document.getElementById('guard-activity-root');
    const cards = root.querySelectorAll('.guard-action-card');
    assert.equal(cards.length, 1);
    assert.ok(cards[0].textContent.includes('<img src=x'));
    assert.equal(root.querySelectorAll('img').length, 0, 'no element created from server text');
    assert.equal(root.querySelectorAll('script').length, 0);
    cleanup();
  });

  test('检测器不可用时显示暂停提示', async () => {
    const held = [{
      ...ACTIONS[0],
      risk: { label: 1, reason_code: 'GUARD_CHECK_UNAVAILABLE', requires_hold: true, evidence_ref: '' },
    }];
    const { dom, cleanup } = await setup(held);
    const root = dom.document.getElementById('guard-activity-root');
    assert.ok(root.textContent.includes('注入检测不可用，该动作已暂停'));
    cleanup();
  });
});
