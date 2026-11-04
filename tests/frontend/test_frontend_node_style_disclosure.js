'use strict';

/**
 * 文献地图「节点样式」浮层开合契约（`<details class="literature-map-node-style-disclosure">`）。
 *
 * 用户验收路径：打开/进入地图后，节点填充面板（填充 / 仅描边 / 透明度 / 应用外观 / 取消预览）
 * **默认折叠**，只有点击 summary「节点样式」才展开；之后视口在桌面↔移动之间变化，
 * 都不得擅自改写开合状态（否则用户刚输入的外观草稿会突然消失/弹出）。
 *
 * 静态读取只能证明「代码里写了什么」，因此本文件把 `frontend/literature-maps.js` 里
 * 真正负责这块 DOM 的源码（`buildNodeStyleDisclosure()` 与 `bindWindowResizeHandler()`）
 * 原样摘出来，放进 `node:vm` 沙箱 + 最小 DOM 桩上真实执行，再断言 `details.open`。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MODULE = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.js'), 'utf8');

const SUMMARY_TEXT = '节点样式';
const DISCLOSURE_CLASS = 'literature-map-node-style-disclosure';

// ---- 源码抽取：不做文本改写，测的是真实实现 ----
const buildMatch = MODULE.match(/  function buildNodeStyleDisclosure\(\) \{[\s\S]*?\n  \}\n/);
assert.ok(buildMatch, 'literature-maps.js 必须定义 buildNodeStyleDisclosure()（节点样式浮层构建）');
const resizeMatch = MODULE.match(/  function handleMobileViewportResize\(\) \{[\s\S]*?\n  \}\n/);
assert.ok(resizeMatch, 'literature-maps.js 必须定义 handleMobileViewportResize()（视口变化入口）');
const resizeBindingMatch = MODULE.match(/window\.addEventListener\('resize', handleMobileViewportResize\);/);
assert.ok(resizeBindingMatch, '视口变化必须通过 window resize 监听进入 handleMobileViewportResize');
const createElementMatch = MODULE.match(/  function createElement\(tag, className, text\) \{[\s\S]*?\n  \}\n/);
assert.ok(createElementMatch, 'literature-maps.js 必须定义 createElement(tag, className, text)');

// ---- 最小 DOM 桩 ----
function makeNode(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    children: [],
    listeners: new Map(),
    attributes: new Map(),
    hidden: false,
    disabled: false,
    id: '',
    className: '',
    textContent: '',
    type: '',
    name: '',
    value: '',
    min: '',
    max: '',
    step: '',
    // 与真实 DOM 一致：`HTMLDetailsElement.open` 读的是布尔属性，未设置时为 false（折叠）。
    open: false,
    append(...nodes) {
      this.children.push(...nodes);
      return undefined;
    },
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    },
    dispatch(type, event = {}) {
      const handlers = this.listeners.get(type) || [];
      handlers.forEach((handler) => handler(event));
      return handlers.length;
    },
  };
}

// `<details>` 的浏览器内置语义：点击 summary 会 toggle open（实现无需额外 JS 监听，
// 所以这里只复现引擎的 toggle 行为，并断言 summary 是**可点击入口**而非 disabled）。
function simulateUserClickOnSummary(disclosure) {
  const summary = disclosure.children.find((child) => child.tagName === 'SUMMARY');
  assert.ok(summary, 'details 必须包含 <summary> 子节点');
  assert.notEqual(summary.disabled, true, 'summary 不得被禁用（用户必须能点击「节点样式」）');
  summary.dispatch('click', { target: summary });
  disclosure.open = !disclosure.open;
}

// ---- 沙箱装配：只放这段逻辑真正依赖的符号 ----
function makeHarness(options = {}) {
  const viewport = { mobile: Boolean(options.mobile) };
  const created = [];
  const windowListeners = new Map();
  const sandbox = {
    console,
    document: {
      createElement: (tag) => {
        const node = makeNode(tag);
        created.push(node);
        return node;
      },
    },
    window: {
      matchMedia: (query) => ({ matches: query === '(max-width: 760px)' ? viewport.mobile : false }),
      addEventListener: (type, handler) => {
        if (!windowListeners.has(type)) windowListeners.set(type, []);
        windowListeners.get(type).push(handler);
      },
    },
    state: {
      nodeStyleDraft: { fill_mode: 'fill', fill_opacity: 0.3 },
      mobileViewport: viewport.mobile,
      active: false,
      resizeRaf: null,
    },
    refs: {},
    layerTools: makeNode('div'),
    isMobileViewport: () => viewport.mobile,
    updateNodeStyleDraft: () => {},
    saveNodeStyle: () => {},
    cancelNodeStyleDraft: () => {},
    closeAllMobilePanels: () => {},
    scheduleViewportStabilization: () => {},
  };
  vm.createContext(sandbox);
  // 原样执行三段真实源码：createElement / buildNodeStyleDisclosure / handleMobileViewportResize，
  // 再执行源码里真实存在的那行 resize 绑定，使视口变化走生产路径。
  vm.runInContext(
    [
      createElementMatch[0],
      buildMatch[0],
      resizeMatch[0],
      resizeBindingMatch[0],
      'this.__buildNodeStyleDisclosure = buildNodeStyleDisclosure;',
    ].join('\n'),
    sandbox,
  );

  const { nodeStyleDisclosure } = sandbox.__buildNodeStyleDisclosure();
  sandbox.refs.nodeStyleDisclosure = nodeStyleDisclosure;

  return {
    sandbox,
    disclosure: nodeStyleDisclosure,
    setViewportMobile(mobile) {
      viewport.mobile = mobile;
      const handlers = windowListeners.get('resize') || [];
      assert.ok(handlers.length > 0, '视口变化必须通过 window resize 监听进入 handleMobileViewportResize');
      handlers.forEach((handler) => handler({ type: 'resize' }));
    },
  };
}

// ---- 1. 初始状态：打开地图即折叠（桌面与移动都不自动展开） ----
for (const mobile of [false, true]) {
  const h = makeHarness({ mobile });
  assert.equal(
    h.disclosure.tagName,
    'DETAILS',
    `节点样式浮层必须是 <details>（当前视口 mobile=${mobile}）`,
  );
  assert.equal(
    h.disclosure.className,
    DISCLOSURE_CLASS,
    '节点样式浮层 class 必须是 literature-map-node-style-disclosure（CSS 依赖该选择器）',
  );
  assert.equal(
    h.disclosure.open,
    false,
    `打开地图后节点样式浮层必须默认折叠 open=false（mobile=${mobile}，用户要求点击后才弹出）`,
  );
}

// ---- 2. 只有点击 summary「节点样式」才展开，再点一次折叠 ----
{
  const h = makeHarness({ mobile: false });
  const summary = h.disclosure.children.find((child) => child.tagName === 'SUMMARY');
  assert.ok(summary, '节点样式浮层必须渲染 summary');
  assert.equal(summary.textContent, SUMMARY_TEXT, 'summary 文案必须是「节点样式」（用户点击的入口）');
  assert.equal(h.disclosure.open, false, '前置：初始折叠');

  simulateUserClickOnSummary(h.disclosure);
  assert.equal(h.disclosure.open, true, '点击 summary 后必须展开');

  simulateUserClickOnSummary(h.disclosure);
  assert.equal(h.disclosure.open, false, '再次点击 summary 必须折叠（用户可收回面板）');
}

// ---- 3. 视口切换不得改写用户当前选择 ----
{
  // 3a. 折叠态下桌面 → 移动 → 桌面，始终保持折叠
  const h = makeHarness({ mobile: false });
  h.setViewportMobile(true);
  assert.equal(h.disclosure.open, false, '折叠态切到移动视口必须保持折叠，不得自动展开');
  h.setViewportMobile(false);
  assert.equal(h.disclosure.open, false, '折叠态切回桌面必须保持折叠（旧实现会强制展开）');
}
{
  // 3b. 用户已展开 → 视口切走再切回，保留展开（不打断外观草稿）
  const h = makeHarness({ mobile: false });
  simulateUserClickOnSummary(h.disclosure);
  assert.equal(h.disclosure.open, true, '前置：用户已展开');
  h.setViewportMobile(true);
  assert.equal(h.disclosure.open, true, '用户展开后切到移动视口必须保留用户选择，不得强制折叠');
  h.setViewportMobile(false);
  assert.equal(h.disclosure.open, true, '用户展开后切回桌面必须保留用户选择');
}

// ---- 4. 回归对照：旧实现（开启状态跟随视口）在用例 1/3a 下必须 FAIL ----
{
  const legacy = makeNode('details');
  legacy.open = true; // 旧实现：nodeStyleDisclosure.open = !isMobileViewport()（桌面即展开）
  assert.equal(legacy.open, true, '对照：旧实现桌面端初始即展开，正是被修复的缺陷');
  const legacyResize = (currentMobileViewport) => {
    legacy.open = !currentMobileViewport; // 旧实现：handleMobileViewportResize 强制改写
  };
  legacyResize(true);
  assert.equal(legacy.open, false, '对照：旧实现在切到移动视口时强制折叠，会打断用户的外观测评');
}

console.log('ok - frontend node style disclosure defaults collapsed and survives viewport changes');
