'use strict';

/**
 * 文献地图**卡片信息**契约（执行级，`node:vm`）。
 *
 * 覆盖两项被用户确认的展示缺陷：
 *   1. 卡片篇数：`renderMapList()` 曾把建图时选的**目标篇数** `requested_count`
 *      当作当前篇数渲染，于是通过「扩展关联论文」新增节点后数字不变。
 *      现在主显后端派生的当前活动节点数 `node_count`；缺失 / 非数 / 负数时
 *      回落 `requested_count`；两者不同时**不得**再显示「目标 N」等辅助信息。
 *   2. 状态徽标：历史建图作业的 `partial` 曾直接渲染成「部分完成」，看起来像
 *      地图坏了。当 `status === 'partial'` 且已有活动节点（`node_count > 0`）时
 *      徽标显示「可用」，并用 `title` / `aria-label` 保留完整说明；
 *      其余 status（generating / failed / stopped / ready …）保持原样。
 *
 * 测试方式：从 `frontend/literature-maps.js` 原样摘出真实函数放进 `node:vm`
 * 沙箱执行（不复制影子实现），DOM 只桩到 `renderMapList` 真正用到的 API。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MODULE = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.js'), 'utf8');
const CSS = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.css'), 'utf8');

const PARTIAL_BADGE_TITLE = '初始建图部分完成，已保留可用节点；不影响已保存节点与后续扩展';

// ---- 源码抽取（原样，不做文本改写） ----
function slice(name, signature) {
  const pattern = new RegExp(`  function ${signature}[\\s\\S]*?\\n  }\\n`);
  const match = MODULE.match(pattern);
  assert.ok(match, `literature-maps.js 必须定义 ${name}`);
  return match[0];
}

const createElementSrc = slice('createElement(tag, className, text)', 'createElement\\(tag, className, text\\)');
const normalizeMapNodeCountSrc = slice('normalizeMapNodeCount(value)', 'normalizeMapNodeCount\\(value\\)');
const normalizeMapViewInitializedSrc = slice('normalizeMapViewInitialized(map)', 'normalizeMapViewInitialized\\(map\\)');
const normalizeMapSrc = slice('normalizeMap(map)', 'normalizeMap\\(map\\)');
const mapTitleSrc = slice('mapTitle(map)', 'mapTitle\\(map\\)');
const mapStatusLabelSrc = slice('mapStatusLabel(status)', 'mapStatusLabel\\(status\\)');
const renderStatusBadgeSrc = slice('renderStatusBadge(status)', 'renderStatusBadge\\(status\\)');
const renderMapListSrc = slice('renderMapList()', 'renderMapList\\(\\)');
const mapCardNodeCountSrc = slice('mapCardNodeCount(map)', 'mapCardNodeCount\\(map\\)');
const mapCardStatusBadgeSrc = slice('mapCardStatusBadge(map)', 'mapCardStatusBadge\\(map\\)');
const filteredMapsSrc = slice('filteredMaps()', 'filteredMaps\\(\\)');
const setHiddenSrc = slice('setHidden(node, hidden)', 'setHidden\\(node, hidden\\)');

// ---- 最小 DOM 桩 ----
function makeEl(tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [],
    className: '',
    textContent: '',
    type: '',
    dataset: {},
    attributes: new Map(),
    hidden: false,
    listeners: new Map(),
    append(...nodes) {
      this.children.push(...nodes);
      return undefined;
    },
    replaceChildren() {
      this.children = [];
    },
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
    },
    getAttribute(name) {
      return this.attributes.has(name) ? this.attributes.get(name) : null;
    },
    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, []);
      this.listeners.get(type).push(handler);
    },
  };
  // 与真实 DOM 一致：`textContent` 既可直接赋值也可读取；读取时聚合子节点文本。
  Object.defineProperty(node, 'text', {
    get() {
      return node.children
        .map((child) => (child && typeof child === 'object' ? child.text : String(child)))
        .join('');
    },
  });
  return node;
}

function makeSandbox() {
  const sandbox = {
    console,
    state: {
      maps: [],
      listQuery: '',
      listStatus: 'all',
      selectedMapId: null,
    },
    refs: {
      mapList: makeEl('div'),
      count: makeEl('span'),
      listEmpty: makeEl('p'),
    },
    closeMobilePanel() {},
    isMobileViewport: () => false,
    selectMap() {},
    document: {
      createElement(tag) {
        return makeEl(tag);
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      `const PARTIAL_MAP_CARD_NOTICE = ${JSON.stringify(PARTIAL_BADGE_TITLE)};`,
      createElementSrc,
      setHiddenSrc,
      normalizeMapNodeCountSrc,
      normalizeMapViewInitializedSrc,
      normalizeMapSrc,
      mapTitleSrc,
      mapStatusLabelSrc,
      renderStatusBadgeSrc,
      mapCardNodeCountSrc,
      mapCardStatusBadgeSrc,
      filteredMapsSrc,
      renderMapListSrc,
      'this.__renderMapList = renderMapList;',
      'this.__normalizeMap = normalizeMap;',
      'this.__mapStatusLabel = mapStatusLabel;',
    ].join('\n'),
    sandbox,
  );
  return sandbox;
}

function renderCards(maps) {
  const sandbox = makeSandbox();
  sandbox.state.maps = maps.map((map) => sandbox.__normalizeMap(map));
  sandbox.__renderMapList();
  return sandbox.refs.mapList.children.map((item) => {
    const [title, topic, meta] = item.children;
    const badge = meta.children.find((child) => child.className === 'literature-map-badge') || null;
    const spans = meta.children.filter((child) => child !== badge);
    return {
      item,
      title,
      badge,
      badgeText: badge ? badge.textContent : null,
      badgeTitle: badge ? badge.getAttribute('title') : null,
      badgeAriaLabel: badge ? badge.getAttribute('aria-label') : null,
      badgeStatus: badge ? badge.dataset.status : null,
      badgeAvailability: badge ? badge.dataset.availability : null,
      metaTexts: spans.map((child) => child.textContent),
      metaText: meta.children.map((child) => child.textContent).join(' | '),
    };
  });
}

function countLabels(card) {
  return card.metaTexts.filter((text) => /篇$/.test(String(text).trim()));
}

// ---- 0. CSS 契约：徽标类名必须在样式表里有定义（DOM 契约自查） ----
assert.ok(
  CSS.includes('.literature-map-badge'),
  'literature-maps.css 必须定义 .literature-map-badge（徽标类名不能只在 JS 里出现）',
);
assert.ok(
  CSS.includes('.literature-map-list-meta'),
  'literature-maps.css 必须定义 .literature-map-list-meta（卡片 meta 容器）',
);
assert.ok(
  CSS.includes('.literature-map-badge[data-availability="usable"]'),
  '「可用」徽标必须有对应样式（data-availability="usable"），否则会套用 partial 的橙色',
);

// ---- 1. 主显 node_count ----
{
  const [card] = renderCards([
    { map_id: 'm1', name: '地图A', topic: 't', status: 'ready', requested_count: 20, node_count: 32 },
  ]);
  assert.deepEqual(countLabels(card), ['32 篇'], 'node_count 存在时必须显示当前活动节点数 32 篇');
  assert.ok(!card.metaText.includes('20 篇'), '目标篇数 requested_count 不得再当作当前篇数出现');
  assert.ok(!card.metaText.includes('目标'), '必须不显示「目标 N」等辅助信息（用户明确要求只显当前篇数）');
}

// ---- 2. node_count 缺失 / 非数 / 负数 → 回落 requested_count ----
for (const value of [undefined, null, '', 'abc', NaN, -3, {}, []]) {
  const [card] = renderCards([
    { map_id: 'm2', name: '地图B', topic: 't', status: 'ready', requested_count: 20, node_count: value },
  ]);
  assert.deepEqual(
    countLabels(card),
    ['20 篇'],
    `node_count=${JSON.stringify(value)} 属非法值，必须回落 requested_count（20 篇）`,
  );
}

// ---- 3. node_count === 0 是合法值，不得被 0 的假值语义吞掉 ----
{
  const [card] = renderCards([
    { map_id: 'm3', name: '地图C', topic: 't', status: 'ready', requested_count: 20, node_count: 0 },
  ]);
  assert.deepEqual(countLabels(card), ['0 篇'], 'node_count=0 必须显示 0 篇（不能回落到目标 20 篇）');
}

// ---- 4. 两者都缺失 → 不渲染任何「N 篇」 ----
{
  const [card] = renderCards([{ map_id: 'm4', name: '地图D', topic: 't', status: 'ready' }]);
  assert.deepEqual(countLabels(card), [], '两个计数都不存在时不得凭空造出篇数');
}

// ---- 5. 徽标局部映射：partial + 有节点 → 可用 ----
{
  const [card] = renderCards([
    { map_id: 'm5', name: '地图E', topic: 't', status: 'partial', requested_count: 20, node_count: 32 },
  ]);
  assert.equal(card.badgeText, '可用', 'partial 且 node_count>0 时卡片徽标必须显示「可用」');
  assert.equal(card.badge.getAttribute('title'), PARTIAL_BADGE_TITLE, '必须用 title 保留完整说明');
  assert.equal(
    card.badge.getAttribute('aria-label'),
    `可用：${PARTIAL_BADGE_TITLE}`,
    '必须用 aria-label 让读屏用户也拿到说明（以「可用」开头）',
  );
  assert.equal(card.badgeStatus, 'partial', '徽标 data-status 固定保留 partial（筛选用值不变）');
  assert.equal(
    card.badgeAvailability,
    'usable',
    '「可用」映射必须带 data-availability="usable"（否则样式仍套 partial 的橙色）',
  );
  assert.deepEqual(countLabels(card), ['32 篇'], '同一卡片必须并行显示当前篇数');
}

// ---- 6. partial 但无活动节点 → 保持「部分完成」（不谎称可用） ----
for (const value of [0, undefined, null, -1, 'x']) {
  const [card] = renderCards([
    { map_id: 'm6', name: '地图F', topic: 't', status: 'partial', requested_count: 20, node_count: value },
  ]);
  assert.equal(
    card.badgeText,
    '部分完成',
    `partial 且 node_count=${JSON.stringify(value)}（无活动节点）时必须保持「部分完成」`,
  );
  assert.equal(card.badge.getAttribute('title'), null, '非「可用」映射时不得挂说明 title');
  assert.equal(card.badgeAvailability, undefined, '非「可用」映射时不得带 data-availability');
}

// ---- 7. 其它 status 保持原样 ----
for (const [status, label] of [
  ['generating', '生成中'],
  ['failed', '失败'],
  ['stopped', '已停止'],
  ['ready', '可用'],
]) {
  const [card] = renderCards([
    { map_id: 'm7', name: '地图G', topic: 't', status, requested_count: 20, node_count: 5 },
  ]);
  assert.equal(card.badgeText, label, `status=${status} 的徽标文案必须保持「${label}」不变`);
  assert.equal(card.badge.getAttribute('title'), null, `status=${status} 不得挂 partial 说明 title`);
}

// ---- 8. 全局 label 表与筛选下拉不受影响 ----
{
  const sandbox = makeSandbox();
  assert.equal(sandbox.__mapStatusLabel('partial'), '部分完成', 'mapStatusLabel(partial) 必须保持「部分完成」');
  assert.ok(
    MODULE.includes("['partial', '部分完成']"),
    '状态筛选下拉里的 partial 仍是「部分完成」，不随卡片徽标局部映射改变',
  );
}

// ---- 9. normalizeMap 透传 node_count；非法值视为缺失 ----
{
  const sandbox = makeSandbox();
  const normalized = sandbox.__normalizeMap({
    map_id: 'm9',
    node_count: 32,
    requested_count: 20,
  });
  assert.equal(normalized.node_count, 32, 'normalizeMap 必须把合法 node_count 透传为数字 32');
  const fromString = sandbox.__normalizeMap({ map_id: 'm9', node_count: '32' });
  assert.equal(fromString.node_count, 32, '数字字符串必须规范化为数字（后端 JSON 数字被字符串化时仍可用）');
  for (const bad of [undefined, null, '', 'abc', NaN, -1, {}, [], Infinity]) {
    const result = sandbox.__normalizeMap({ map_id: 'm9', node_count: bad });
    assert.equal(
      result.node_count,
      undefined,
      `node_count=${JSON.stringify(bad)} 属非法值，normalizeMap 必须视为缺失（不写入 node_count）`,
    );
  }
  assert.equal(sandbox.__normalizeMap(null), null, 'normalizeMap(null) 必须仍返回 null');
}

// ---- 10. XSS：标题等字段只走 textContent ----
{
  const [card] = renderCards([
    {
      map_id: 'm10',
      name: '<img src=x onerror=alert(1)>',
      topic: '<script>bad()</script>',
      status: 'ready',
      node_count: 3,
    },
  ]);
  assert.equal(card.title.textContent, '<img src=x onerror=alert(1)>', '标题必须原样进 textContent，不被解析为 HTML');
  assert.deepEqual(countLabels(card), ['3 篇'], '计数必须是纯文本 span');
  assert.ok(!MODULE.includes('innerHTML'), 'literature-maps.js 不得使用 innerHTML');
}

console.log('ok - map card count (node_count) and availability badge (node:vm, real renderMapList)');
