'use strict';

/**
 * 主内容区「hash 直达」契约（**执行级**验证）。
 *
 * 背景（真实缺陷）：`app.js` 初始化曾无条件 `showView('chat')`，于是用户把
 * `#literature-maps-view` 加进书签/刷新页面后仍然停在「对话」，必须手动点左侧导航。
 * 反向风险同样存在：`#research-view` 由 `frontend/research-tasks.js` 自己掌管
 * （它监听 hashchange、初始化时自行 showView、还会 replaceState 写 hash），
 * app.js 若也去处理它，两个视图切换器会互相打架。
 *
 * 本文件把 `frontend/app.js` 里的**真实**实现摘进 `node:vm` 沙箱执行
 * （不复制一份影子实现，避免测到的不是线上代码）：
 *   - `MAIN_AREA_VIEW_IDS` / `hideAllMainAreas()` / `showView(view)`
 *   - `viewForLocationHash(hash)`：hash → showView 入参的纯映射
 *   - `syncViewFromLocationHash(hash)`：初始化与 hashchange 共用的入口
 *
 * 覆盖的被测能力：
 *   1. 带 `#literature-maps-view` 刷新/直达 → 立刻切到文献地图（缺陷 1 的验收路径）；
 *   2. 其余 app.js 掌管的 hash 都能直达；
 *   3. 未知 / 空 hash → 回落 chat；
 *   4. `#research-view` 不被 app.js 接管（返回 null 且不调用 showView）；
 *   5. `papers` 在 `paperState.enabled === false` 时仍按 `showView()` 既有逻辑回落 chat；
 *   6. 任何时刻只有一个 `.main-area` 可见（`hideAllMainAreas()` 未被跳过）。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');
const INDEX_HTML = fs.readFileSync(path.resolve(__dirname, '../../frontend/index.html'), 'utf8');

const IDS = [...INDEX_HTML.matchAll(/<section class="main-area" id="([a-z-]+)"/g)].map((m) => m[1]);
assert.ok(IDS.includes('chat') && IDS.includes('literature-maps-view'), 'index.html 必须包含 #chat 与 #literature-maps-view');

// ---- 最小 DOM 桩：只实现 showView / hideAllMainAreas 真正用到的 API ----
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
  const elements = new Map(IDS.map((id) => [id, sections.get(`#${id}`) ]));
  const navItems = ['chat', 'research', 'models', 'kb', 'memory', 'papers', 'literature-maps', 'skill-tool']
    .map((view) => makeEl(`nav-${view}`, { dataset: { view } }));

  const document = {
    querySelector: (selector) => sections.get(selector) || null,
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: (selector) => (selector === '.nav-item' ? navItems : []),
  };

  const noop = () => {};
  const showViewCalls = [];
  const sandbox = {
    document,
    // 真实初始化时 hashchange 事件挂在 window 上；这里只给 syncViewFromLocationHash 用到的空壳。
    window: { addEventListener() {} },
    console,
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

  // 摘真实源码片段（不做文本改写，避免测到改写后的影子实现）。
  const registry = APP_JS.match(/const MAIN_AREA_VIEW_IDS = Object\.freeze\(\[[\s\S]*?\]\);/);
  const hideAll = APP_JS.match(/function hideAllMainAreas\(\) \{[\s\S]*?\n\}/);
  const showView = APP_JS.match(/function showView\(view\) \{[\s\S]*?\n\}/);
  const hashMap = APP_JS.match(/const HASH_VIEW_MAP = Object\.freeze\(\{[\s\S]*?\}\);/);
  const mapFn = APP_JS.match(/function viewForLocationHash\(hash\) \{[\s\S]*?\n\}/);
  const syncFn = APP_JS.match(/function syncViewFromLocationHash\(hash\) \{[\s\S]*?\n\}/);
  assert.ok(registry, 'app.js 必须定义 MAIN_AREA_VIEW_IDS');
  assert.ok(hideAll, 'app.js 必须定义 hideAllMainAreas()');
  assert.ok(showView, 'app.js 必须定义 showView(view)');
  assert.ok(mapFn, 'app.js 必须定义 viewForLocationHash(hash)（hash → showView 入参的纯映射）');
  assert.ok(hashMap, 'app.js 必须定义 HASH_VIEW_MAP（hash → 短 view 名的映射表）');
  assert.ok(syncFn, 'app.js 必须定义 syncViewFromLocationHash(hash)（初始化与 hashchange 共用入口）');

  // 生产代码的 syncViewFromLocationHash 直接调用 showView；沙箱里换成记账版本，
  // 以便断言「#research-view 时根本没调用 showView」，同时仍走真实 showView 逻辑。
  vm.createContext(sandbox);
  vm.runInContext(
    `${registry[0]}\n${hideAll[0]}\n${showView[0]}\nthis.__realShowView = showView;\n${hashMap[0]}\n${mapFn[0]}\n${syncFn[0]}\n`
      + 'this.__viewForLocationHash = viewForLocationHash;\nthis.__syncViewFromLocationHash = syncViewFromLocationHash;',
    sandbox,
  );

  sandbox.showView = (view) => {
    showViewCalls.push(view);
    sandbox.__realShowView(view);
  };
  // 重新执行 sync 片段不可行（函数体已绑定旧 showView 引用），改为真实函数路径：
  // syncViewFromLocationHash 内部引用的是同名全局 `showView`，替换后即生效。
  vm.runInContext('this.__syncViewFromLocationHash = syncViewFromLocationHash;', sandbox);

  return {
    sandbox,
    showViewCalls,
    sync: (hash) => sandbox.__syncViewFromLocationHash(hash),
    map: (hash) => sandbox.__viewForLocationHash(hash),
    sections: elements,
    visible: () => IDS.filter((id) => !elements.get(id).hidden),
    reset: () => IDS.forEach((id) => { elements.get(id).hidden = true; }),
  };
}

// hash → 期望可见的 .main-area id。research-view 刻意缺席（不归 app.js）。
const HASH_TO_SECTION = {
  '#models-view': 'models-view',
  '#memory-view': 'memory-view',
  '#kb-view': 'kb-view',
  '#papers-view': 'papers-view',
  '#literature-maps-view': 'literature-maps-view',
  '#skill-tool-view': 'skill-tool-view',
  '#chat': 'chat',
};

// ---- 1. 缺陷 1 的验收路径：带 #literature-maps-view 刷新/直达 ----
{
  const h = makeHarness();
  h.reset();
  h.sync('#literature-maps-view');
  assert.deepEqual(h.visible(), ['literature-maps-view'], '带 #literature-maps-view 直达必须切到文献地图（不得停在对话）');
  assert.equal(h.sections.get('chat').hidden, true, '文献地图下 #chat 必须 hidden');
  assert.equal(h.sections.get('research-view').hidden, true, '文献地图下 #research-view 必须 hidden');
  assert.deepEqual(h.showViewCalls, ['literature-maps'], '必须通过 showView(\'literature-maps\') 切换，而不是直接改 hidden');
}

// ---- 2. 其余 app.js 掌管的 hash 全部直达，且可见视图恰好一个 ----
for (const [hash, sectionId] of Object.entries(HASH_TO_SECTION)) {
  const h = makeHarness();
  h.reset();
  h.sync(hash);
  assert.deepEqual(h.visible(), [sectionId], `${hash} 直达后可见 .main-area 必须恰好是 #${sectionId}`);
  assert.equal(h.visible().length, 1, `${hash} 直达后可见 .main-area 数量必须为 1（hideAllMainAreas 不得被跳过）`);
}

// ---- 3. 未知 / 空 hash 回落 chat ----
for (const hash of ['', '#', '#nope', '#models', '#RESEARCH-VIEW-x', undefined, null]) {
  const h = makeHarness();
  h.reset();
  h.sync(hash);
  assert.deepEqual(h.visible(), ['chat'], `hash=${JSON.stringify(hash)} 必须回落 chat`);
  assert.deepEqual(h.showViewCalls, ['chat'], `hash=${JSON.stringify(hash)} 必须调用 showView('chat')`);
}

// ---- 4. #research-view 不被 app.js 接管 ----
{
  const h = makeHarness();
  h.reset();
  assert.equal(h.map('#research-view'), null, '#research-view 的映射必须是 null（不归 app.js）');
  h.sync('#research-view');
  assert.deepEqual(h.showViewCalls, [], '#research-view 时 app.js 不得调用 showView（避免与 research-tasks.js 打架）');
  assert.deepEqual(h.visible(), [], '#research-view 时 app.js 不改动任何 .main-area 可见性');
}

// ---- 5. papers 关闭时仍走 showView() 既有回落逻辑，本层不做二次判断 ----
{
  const h = makeHarness();
  h.sandbox.paperState.enabled = false;
  h.reset();
  h.sync('#papers-view');
  assert.deepEqual(h.showViewCalls, ['papers'], 'hash 映射只负责映射成 showView 入参 papers');
  assert.deepEqual(h.visible(), ['chat'], 'paperState.enabled=false 时仍按 showView() 既有逻辑回落 chat');
}

// ---- 6. 反复 hashchange 不累积可见视图（幂等） ----
{
  const h = makeHarness();
  h.reset();
  ['#kb-view', '#chat', '#literature-maps-view', '#chat'].forEach((hash) => {
    h.sync(hash);
    assert.equal(h.visible().length, 1, `hash=${hash} 后可见 .main-area 数量必须为 1`);
  });
  assert.deepEqual(h.visible(), ['chat'], '最后一次 hash 决定可见视图');
}

console.log('ok - frontend view hash deep link (syncViewFromLocationHash executed)');
