'use strict';

/**
 * 主内容区视图互斥 —— 执行级验证（`showView` 真实跑一遍）。
 *
 * 静态读取只能证明「代码里写了什么」，无法证明「运行时只有一个 .main-area 可见」。
 * 本文件把 `frontend/app.js` 中 `showView()` 及其两个依赖（注册表 / 隐藏函数）
 * 摘出来放进 `node:vm` 沙箱，用最小 DOM 桩真实执行，再断言可见集合。
 *
 * 覆盖用户验收路径：
 *   - 直达 `/c/<id>#research-view`（research-tasks.js 先显示研究视图）
 *     随后 app.js 初始化 `showView('chat')` 的经典竞态 → 之前会两个视图同时可见；
 *   - 从研究视图点任一普通导航 → 研究视图必须隐藏；
 *   - 视图 idle（旧行为）对照：旧实现只在 `.main-area` 里漏掉 research-view。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');
const INDEX_HTML = fs.readFileSync(path.resolve(__dirname, '../../frontend/index.html'), 'utf8');

const IDS = [...INDEX_HTML.matchAll(/<section class="main-area" id="([a-z-]+)"/g)].map((m) => m[1]);
assert.ok(IDS.includes('research-view') && IDS.includes('chat'), 'index.html 必须包含 #chat 与 #research-view');

// ---- 最小 DOM 桩：只实现 showView 真正用到的 API ----
function makeEl(id, extra = {}) {
  return {
    id,
    hidden: false,
    dataset: extra.dataset || {},
    value: extra.value,
    classList: { toggle() {} },
    setAttribute() {},
    querySelectorAll: () => [],
    ...extra,
  };
}

function makeHarness() {
  const sections = new Map(IDS.map((id) => [`#${id}`, makeEl(id)]));
  const elements = new Map(IDS.map((id) => [id, sections.get(`#${id}`)]));
  const navItems = ['chat', 'research', 'models', 'kb', 'memory', 'papers', 'literature-maps', 'skill-tool']
    .map((view) => makeEl(`nav-${view}`, { dataset: { view } }));

  const document = {
    querySelector: (selector) => sections.get(selector) || null,
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: (selector) => (selector === '.nav-item' ? navItems : []),
  };

  // 引擎无关的空操作，保证 showView 各分支可跑不炸。
  const noop = () => {};
  const sandbox = {
    document,
    window: {},
    console,
    // showView 分支里用到的外部符号（本测试只关心 hidden 状态，全部桩成空操作/空值）
    paperState: { enabled: true, conferencesLoaded: true },
    paperView: sections.get('#papers-view'),
    memoryView: sections.get('#memory-view'),
    stView: sections.get('#skill-tool-view'),
    memoryScopeSelect: null,
    memoryProjectSelect: null,
    memoryProjectLabel: null,
    memoryState: { loaded: false, scope: null, projectId: null },
    modelLibraryLoaded: true,
    cancelPaperSearchPolling: noop,
    renderKbSkeleton: noop,
    loadKbPapers: noop,
    loadKbHealth: noop,
    loadModelLibrary: noop,
    restoreMemoryViewState: noop,
    loadSystemRule: noop,
    memoryDocumentKey: () => '',
    loadMemoryDocument: noop,
    loadPaperImportBatches: noop,
    loadPaperConferences: noop,
    loadSkills: noop,
    loadTools: noop,
  };

  // 摘出注册表 + 隐藏函数 + showView 三段源码，原样执行（不做文本改写，避免测到改写后的影子实现）。
  const registry = APP_JS.match(/const MAIN_AREA_VIEW_IDS = Object\.freeze\(\[[\s\S]*?\]\);/);
  const hideAll = APP_JS.match(/function hideAllMainAreas\(\) \{[\s\S]*?\n\}/);
  const showView = APP_JS.match(/function showView\(view\) \{[\s\S]*?\n\}/);
  assert.ok(registry, 'app.js 必须定义 MAIN_AREA_VIEW_IDS');
  assert.ok(hideAll, 'app.js 必须定义 hideAllMainAreas()');
  assert.ok(showView, 'app.js 必须定义 showView(view)');

  vm.createContext(sandbox);
  vm.runInContext(`${registry[0]}\n${hideAll[0]}\n${showView[0]}\nthis.__showView = showView;`, sandbox);

  return {
    showView: sandbox.__showView,
    sections: elements,
    visible: () => IDS.filter((id) => !elements.get(id).hidden),
    setVisible: (id) => { elements.get(id).hidden = false; },
    reset: () => IDS.forEach((id) => { elements.get(id).hidden = true; }),
  };
}

// ---- 1. 经典竞态：research-tasks.js 先显示研究视图，app.js 初始化 showView('chat') ----
{
  const h = makeHarness();
  h.reset();
  h.setVisible('research-view'); // research-tasks.js:872 showView() 的效果
  assert.deepEqual(h.visible(), ['research-view'], '前置：研究视图单独可见');

  h.showView('chat');
  assert.deepEqual(h.visible(), ['chat'], 'showView(\'chat\') 后必须只剩 #chat（不得与 #research-view 重叠）');
  assert.equal(h.sections.get('research-view').hidden, true, 'showView(\'chat\') 必须隐藏 #research-view');
}

// ---- 2. 从研究视图点每个普通导航，结果只能有目标视图 ----
// 键是 `showView()` 入参（导航项 data-view），值是它应显形的 `.main-area` id。
const NAV_TO_SECTION = {
  chat: 'chat',
  models: 'models-view',
  memory: 'memory-view',
  kb: 'kb-view',
  papers: 'papers-view',
  'literature-maps': 'literature-maps-view',
  'skill-tool': 'skill-tool-view',
};
for (const [view, sectionId] of Object.entries(NAV_TO_SECTION)) {
  const h = makeHarness();
  h.reset();
  h.setVisible('research-view');
  h.showView(view);
  assert.deepEqual(h.visible(), [sectionId], `从研究视图切到 ${view} 后可见视图必须恰好是 #${sectionId}`);
  assert.equal(h.sections.get('research-view').hidden, true, `切到 ${view} 后 #research-view 必须 hidden`);
}

// ---- 3. 反复切换不累积可见视图（幂等） ----
{
  const h = makeHarness();
  h.reset();
  h.setVisible('research-view');
  ['chat', 'kb', 'chat', 'models', 'chat'].forEach((view) => {
    h.showView(view);
    assert.equal(h.visible().length, 1, `切到 ${view} 后可见 .main-area 数量必须为 1`);
  });
}

// ---- 4. 研究视图不由 app.js 显示：research-tasks.js 负责可见性 ----
{
  const h = makeHarness();
  h.reset();
  h.showView('chat');
  h.setVisible('research-view'); // research-tasks.js 显示研究视图
  assert.deepEqual(h.visible().sort(), ['chat', 'research-view'].sort(), '本测试固化研究视图显示职责边界');
  // 随后任何一次普通导航都必须收敛回单视图（不依赖 research-tasks.js 配合）。
  h.showView('chat');
  assert.deepEqual(h.visible(), ['chat'], '普通导航必须收敛为单视图');
}

// ---- 5. 回归对照：旧实现（不隐藏 research-view）在此用例下会 FAIL ----
{
  const h = makeHarness();
  h.reset();
  h.setVisible('research-view');
  // 模拟旧 showView：只在 .main-area 里显隐七项，漏掉 research-view
  ['chat', 'models-view', 'memory-view', 'kb-view', 'papers-view', 'literature-maps-view', 'skill-tool-view']
    .forEach((id) => { h.sections.get(id).hidden = id !== 'chat'; });
  assert.deepEqual(
    h.visible(),
    ['chat', 'research-view'],
    '对照：旧实现正是「对话 + 深度研究同时可见」，证明本用例确实能抓住该缺陷',
  );
}

console.log('ok - frontend view exclusivity runtime (showView executed)');
