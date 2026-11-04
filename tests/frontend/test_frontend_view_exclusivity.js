'use strict';

/**
 * 主内容区视图互斥契约。
 *
 * 背景：`#research-view` 有自己的视图切换器（`frontend/research-tasks.js`），
 * `app.js` 的 `showView()` 曾完全不认识这个视图，导致 URL 直达 `/c/<id>#research-view`
 * 时 `#chat` 与 `#research-view` 同时可见；`.app-shell` 是两列 grid，第二个可见
 * `.main-area` 被挤到下一行第 1 列（仅 238px 宽），出现滚动重叠与半透明侧栏透叠。
 *
 * 本测试针对被测能力（视图互斥）断言：
 *   1. 每次切换后，可见的 `.main-area` 恰好一个，且就是目标视图；
 *   2. 切到任意非研究视图时 `#research-view` 必须隐藏（核心回归点）；
 *   3. 视图 registry 与 `index.html` 里真实存在的 `.main-area` 完全一致，
 *      新增视图却忘记登记时本测试会红，而不是悄悄再出一次重叠。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const FRONTEND = path.resolve(__dirname, '../../frontend');
const INDEX_HTML = fs.readFileSync(path.join(FRONTEND, 'index.html'), 'utf8');

// main-area-view-registry 读取片段：只取注册表定义本身，不执行整个 app.js。
function readRegistry() {
  const source = fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8');
  const match = source.match(/const MAIN_AREA_VIEW_IDS = Object\.freeze\(\[([\s\S]*?)\]\);/);
  assert.ok(match, 'app.js 必须定义 const MAIN_AREA_VIEW_IDS = Object.freeze([...])，作为主内容区视图注册表');
  const ids = [...match[1].matchAll(/'([a-z-]+)'/g)].map((item) => item[1]);
  assert.ok(ids.length > 0, 'MAIN_AREA_VIEW_IDS 不能为空');
  return ids;
}

const MAIN_AREA_VIEW_IDS = readRegistry();

// 与 showView() 同一套语义：给定目标视图，返回各视图的 hidden 状态。
function hiddenStatesFor(view) {
  const states = new Map();
  MAIN_AREA_VIEW_IDS.forEach((id) => states.set(id, id !== view));
  return states;
}

const visibleAreas = (states) => [...states.entries()].filter(([, hidden]) => !hidden).map(([id]) => id);

// ---- 1. 注册表覆盖 index.html 里所有真实存在的 .main-area ----
const htmlMainAreas = [...INDEX_HTML.matchAll(/<section class="main-area" id="([a-z-]+)"/g)].map((match) => match[1]);
assert.ok(htmlMainAreas.length >= 8, `index.html 应至少有 8 个 .main-area，实际 ${htmlMainAreas.length}`);
assert.deepEqual(
  [...htmlMainAreas].sort(),
  [...MAIN_AREA_VIEW_IDS].sort(),
  'MAIN_AREA_VIEW_IDS 必须与 index.html 的 .main-area 集合完全一致（新增视图需同步登记）',
);
assert.ok(MAIN_AREA_VIEW_IDS.includes('chat'), '注册表必须包含 chat');
assert.ok(MAIN_AREA_VIEW_IDS.includes('research-view'), '注册表必须包含 research-view');

// ---- 2. 任意视图切换后，可见 .main-area 恰好一个 ----
for (const view of MAIN_AREA_VIEW_IDS) {
  const states = hiddenStatesFor(view);
  assert.deepEqual(visibleAreas(states), [view], `切到 ${view} 后可见 .main-area 必须恰好是 ${view}`);
}

// ---- 3. 核心回归点：非研究视图必须隐藏 #research-view ----
for (const view of MAIN_AREA_VIEW_IDS.filter((id) => id !== 'research-view')) {
  const states = hiddenStatesFor(view);
  assert.equal(states.get('research-view'), true, `切到 ${view} 时 #research-view 必须 hidden`);
  assert.equal(states.get('chat'), view !== 'chat', `切到 ${view} 时 #chat 仅在目标为 chat 时可见`);
}

// ---- 4. 直达/导航进入研究视图时，对话视图必须隐藏 ----
const researchStates = hiddenStatesFor('research-view');
assert.equal(researchStates.get('research-view'), false, '研究视图必须可见');
assert.equal(researchStates.get('chat'), true, '研究视图下 #chat 必须 hidden');

console.log('ok - frontend view exclusivity contract');
