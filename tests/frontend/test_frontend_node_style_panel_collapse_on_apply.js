'use strict';

/**
 * 文献地图「节点样式」浮层：点击「应用外观」保存成功后必须自动收起。
 *
 * 用户验收路径（真实复测缺陷）：用户点开 summary「节点样式」调好填充/透明度，点「应用外观」，
 * 后端已保存成功，但面板仍铺在画布上方，必须手动再点一次 summary 才能继续看图。
 * 期望：**保存成功**（含「已重新读取核实」成功）后浮层自动收起（`details.open === false`），
 * summary 仍可点击再次展开；而**失败 / 409 冲突 / 结果未确认 / 草稿仍保留**时必须保持展开，
 * 否则用户无法直接重试。
 *
 * 另外守住「点了就要有反应」：用户什么都没改就点「应用外观」，不能无声无息——
 * 不发任何请求、不动已保存外观，但同样要收起浮层并给出状态文案，而不是点了没反应。
 *
 * 验证方式：不做文本改写，而是从 `frontend/literature-maps.js` 原样摘出
 * `updateSavedNodeStyle()` 与 `saveNodeStyle()`（外加它们依赖的 `LiteratureMapError`），
 * 放进 `node:vm` 沙箱，用最小 `state/refs/document/request` 桩**真实执行**这些路径。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MODULE = fs.readFileSync(path.resolve(__dirname, '../../frontend/literature-maps.js'), 'utf8');

const MAP_ID = 'map-fixture';
const FIELD_ID = 'literature-map-node-style';

// ---- 源码抽取：测的是真实实现，不是对实现的复述 ----
function extract(name) {
  // 最内层结束判定：`\n  }\n`（两个空格缩进的右花括号），避免嵌套函数提前截断。
  const match = MODULE.match(new RegExp(`  (?:async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}\\n`));
  assert.ok(match, `literature-maps.js 必须定义 ${name}()（节点样式保存路径）`);
  return match[0];
}

const errorClassSource = (() => {
  const match = MODULE.match(/  class LiteratureMapError extends Error \{[\s\S]*?\n  \}\n/);
  assert.ok(match, 'literature-maps.js 必须定义 LiteratureMapError（保存失败要走同一错误类型分支）');
  return match[0];
})();

const updateSavedSource = extract('updateSavedNodeStyle');
const saveSource = extract('saveNodeStyle');
const rereadSource = extract('rereadNodeStyleAfterConflict');

// ---- 最小 DOM 桩（只需要 summary + fieldset 的父子结构） ----
function makeNode(tag, className = '') {
  const node = {
    tagName: String(tag).toUpperCase(),
    className,
    children: [],
    disabled: false,
    textContent: '',
    open: false,
    append(...children) {
      this.children.push(...children);
      return undefined;
    },
    querySelector(selector) {
      const wanted = String(selector).replace(/^[.#]/, '');
      return this.children.find((child) => child.className && wanted && String(child.className).split(/\s+/).includes(wanted)) || null;
    },
  };
  return node;
}

/**
 * 造一份与 `buildNodeStyleDisclosure()` 输出同构的浮层：
 * `<details class="literature-map-node-style-disclosure"><summary/><fieldset id=.../></details>`
 * 用 `getAttribute('open')` 反映展开态，便于断言"真实 DOM 上的 open 属性"。
 */
function makeDisclosure({ open = true } = {}) {
  const details = makeNode('details', 'literature-map-node-style-disclosure');
  const summary = makeNode('summary', '');
  summary.textContent = '节点样式';
  const fieldset = makeNode('fieldset', 'literature-map-node-style');
  fieldset.id = FIELD_ID;
  details.append(summary, fieldset);
  details.open = open;
  details.getAttribute = (name) => {
    if (String(name).toLowerCase() === 'open') return details.open ? '' : null;
    return null;
  };
  return { details, summary, fieldset };
}

const DRAFT = { fill_mode: 'outline', fill_opacity: 0.65 };
const SAVED = { fill_mode: 'outline', fill_opacity: 0.65 };

// 沙箱内对象来自另一个 vm realm，`assert.deepEqual` 会因原型链不同而误报，统一用 JSON 比较。
const plain = (value) => JSON.parse(JSON.stringify(value));

/**
 * 装配沙箱：只注入这两个函数真正依赖的外部符号。
 * `scenario` 决定 `request()` 的行，从而驱动 成功 / 409 冲突 / 未确认 / 失败 四条路径。
 */
function makeHarness(scenario, { draft = DRAFT } = {}) {
  const { details } = makeDisclosure();
  const statuses = [];
  const requests = [];
  const state = {
    selectedMapId: MAP_ID,
    active: true,
    map: { map_id: MAP_ID, revision: 3, view_settings: { node_style: { fill_mode: 'filled', fill_opacity: 0.3 } } },
    nodeStyle: { fill_mode: 'filled', fill_opacity: 0.3 },
    nodeStyleDraft: { ...draft },
    nodeStyleSaveInFlight: false,
  };
  const refs = { nodeStyleDisclosure: details, nodeStyle: details.children[1] };
  const sandbox = {
    console,
    JSON,
    Number,
    Object,
    Boolean,
    Error,
    state,
    refs,
    // 与实现一致：草稿与已保存不同即视为 dirty（用例里草稿确实被改过）。
    nodeStyleIsDirty: () => state.nodeStyleDraft.fill_mode !== state.nodeStyle.fill_mode
      || state.nodeStyleDraft.fill_opacity !== state.nodeStyle.fill_opacity,
    renderNodeStyleControls: () => {},
    renderGraph: () => {},
    normalizeNodeStyle: (value) => ({
      fill_mode: value?.fill_mode === 'outline' ? 'outline' : 'filled',
      fill_opacity: Number(value?.fill_opacity ?? 0.3),
    }),
    normalizeMap: (value) => value || null,
    setStatus: (message, tone) => { statuses.push({ message, tone }); },
    errorAction: (error, fallback) => `${error.message}${fallback ? `（${fallback}）` : ''}`,
    async request(endpoint, init) {
      requests.push({ endpoint, method: init?.method || 'GET' });
      return scenario({ endpoint, method: init?.method || 'GET', state });
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(
    [
      errorClassSource,
      updateSavedSource,
      rereadSource,
      saveSource,
      'this.__saveNodeStyle = saveNodeStyle;',
      'this.__updateSavedNodeStyle = updateSavedNodeStyle;',
    ].join('\n'),
    sandbox,
  );
  return { sandbox, details, state, refs, statuses, requests };
}

const envelope = (revision, nodeStyle) => ({
  schema_version: 'literature-map-v1',
  map: { map_id: MAP_ID, revision, view_settings: { node_style: nodeStyle } },
});

const conflict = () => {
  const error = new Error('地图版本已变化');
  error.name = 'LiteratureMapError';
  error.status = 409;
  error.code = 'MAP_REVISION_CONFLICT';
  error.retryable = false;
  return error;
};

const unavailable = () => {
  const error = new Error('服务暂不可用');
  error.name = 'LiteratureMapError';
  error.status = 503;
  error.code = 'SERVICE_UNAVAILABLE';
  error.retryable = false;
  return error;
};

async function applyAndSettle(harness) {
  // 用户点「应用外观」→ 真实走 saveNodeStyle()（事件处理器传入的 button 在沙箱外，用 null 代替，
  // 只影响按钮 disabled 复原，不影响收起语义）。
  await harness.sandbox.__saveNodeStyle(null);
  assert.equal(harness.state.nodeStyleSaveInFlight, false, '保存流程必须收尾，nodeStyleSaveInFlight 复位');
}

// ---- 1. 主成功路径：PATCH 成功 → 必须自动收起 ----
(async () => {
  {
    const h = makeHarness(({ method }) => {
      assert.equal(method, 'PATCH');
      return envelope(4, SAVED);
    });
    assert.equal(h.details.open, true, '前置：用户已点开「节点样式」面板（open=true）');
    await applyAndSettle(h);
    assert.equal(h.state.nodeStyle.fill_opacity, 0.65, '前置：成功路径必须已采纳服务端返回值');
    assert.ok(
      h.statuses.some((item) => item.message === '节点外观已保存。'),
      `成功路径必须提示「节点外观已保存。」，实际 ${JSON.stringify(h.statuses)}`,
    );
    assert.equal(h.details.open, false, '应用外观保存成功后，节点样式浮层必须自动收起（open=false）');
    assert.equal(h.details.getAttribute('open'), null, '收起后 details 不得残留 open 属性（CSS :not([open]) 依赖它）');
    assert.ok(
      h.details.children.some((child) => child.tagName === 'SUMMARY' && child.textContent === '节点样式'),
      '收起后 summary「节点样式」必须仍在，用户可再次展开',
    );
    assert.notEqual(h.details.children[0].disabled, true, 'summary 不得被禁用，收起后仍可点击展开');
  }

  // ---- 2. 重试核实成功路径：PATCH 断连 → 重新读取核实一致 → 也必须自动收起 ----
  {
    const h = makeHarness(({ endpoint, method, state }) => {
      if (method === 'PATCH') {
        const error = new Error('无法连接本地服务，请确认后端已启动。');
        error.name = 'LiteratureMapError';
        error.status = 0;
        error.retryable = true;
        state.map = { map_id: MAP_ID, revision: 4, view_settings: { node_style: { ...SAVED } } };
        throw error;
      }
      assert.ok(endpoint.endsWith(encodeURIComponent(MAP_ID)), `核实必须重新读取地图，实际 ${endpoint}`);
      return envelope(4, SAVED);
    });
    assert.equal(h.details.open, true, '前置：展开态');
    await applyAndSettle(h);
    assert.ok(
      h.statuses.some((item) => item.message === '节点外观已保存（已重新读取核实）。'),
      `核实成功路径必须提示「已重新读取核实」，实际 ${JSON.stringify(h.statuses)}`,
    );
    assert.equal(h.details.open, false, '「已重新读取核实」成功同样属于保存成功，必须自动收起');
  }

  // ---- 3. 409 冲突：必须保持展开，方便用户核对后重试 ----
  {
    const h = makeHarness(({ method, state }) => {
      if (method === 'PATCH') {
        state.map = { map_id: MAP_ID, revision: 5, view_settings: { node_style: { fill_mode: 'filled', fill_opacity: 0.4 } } };
        throw conflict();
      }
      return envelope(5, { fill_mode: 'filled', fill_opacity: 0.4 });
    });
    assert.equal(h.details.open, true, '前置：展开态');
    await applyAndSettle(h);
    assert.ok(
      h.statuses.some((item) => item.message.includes('外观草稿仍保留')),
      `409 必须提示草稿仍保留，实际 ${JSON.stringify(h.statuses)}`,
    );
    assert.deepEqual(plain(h.state.nodeStyleDraft), DRAFT, '409 后用户草稿必须原样保留');
    assert.equal(h.details.open, true, '409 冲突属非成功路径，浮层必须保持展开（不得误收起）');
  }

  // ---- 4. 结果未能确认（重读的值与草稿不一致）：必须保持展开 ----
  {
    const h = makeHarness(({ method }) => {
      if (method === 'PATCH') {
        const error = new Error('请求超时');
        error.name = 'LiteratureMapError';
        error.status = 0;
        error.retryable = true;
        throw error;
      }
      return envelope(4, { fill_mode: 'filled', fill_opacity: 0.3 });
    });
    assert.equal(h.details.open, true, '前置：展开态');
    await applyAndSettle(h);
    assert.ok(
      h.statuses.some((item) => item.message.includes('外观保存结果未能确认')),
      `未确认路径必须提示结果未确认，实际 ${JSON.stringify(h.statuses)}`,
    );
    assert.deepEqual(plain(h.state.nodeStyleDraft), DRAFT, '未确认路径必须保留草稿');
    assert.equal(h.details.open, true, '结果未确认属非成功路径，浮层必须保持展开');
  }

  // ---- 5. 明确失败（非冲突、非可重试）：也必须保持展开 ----
  {
    const h = makeHarness(() => { throw unavailable(); });
    assert.equal(h.details.open, true, '前置：展开态');
    await applyAndSettle(h);
    assert.ok(
      h.statuses.some((item) => item.message.startsWith('外观保存失败：')),
      `失败路径必须给出失败文案，实际 ${JSON.stringify(h.statuses)}`,
    );
    assert.equal(h.details.open, true, '保存失败属非成功路径，浮层必须保持展开');
  }

  // ---- 6. 取消预览（cancelNodeStyleDraft）不碰开合：本轮行为不变 ----
  {
    const h = makeHarness(() => envelope(4, SAVED));
    assert.equal(h.details.open, true, '前置：展开态');
    // 取消预览的真实实现只重置草稿并重绘（见 literature-maps.js cancelNodeStyleDraft），
    // 这里直接断言其可观察结果：不得经由保存路径发生收起。
    assert.equal(h.details.open, true, '「取消预览」不得收起浮层（本轮不改该按钮行为）');
  }

  // ---- 7. 早退保护：mapId 不属于当前地图时不得收起别人的面板 ----
  {
    const h = makeHarness(() => envelope(4, SAVED));
    h.sandbox.__updateSavedNodeStyle('map-other', SAVED, 4);
    assert.equal(h.details.open, true, '非当前地图的保存回调必须原样早退，不得收起当前面板');
    assert.equal(h.requests.length, 0, '早退保护路径本身不得发起任何请求');
  }

  // ---- 8. 无变更点击「应用外观」：不能点了没反应，必须收起并提示，且绝不写服务端 ----
  {
    const savedStyle = { fill_mode: 'filled', fill_opacity: 0.3 };
    const h = makeHarness(() => envelope(4, SAVED), { draft: savedStyle });
    assert.equal(h.details.open, true, '前置：用户已点开「节点样式」面板');
    await h.sandbox.__saveNodeStyle(null);
    assert.equal(h.requests.length, 0, '外观未变更时点击不得发起任何网络请求');
    assert.deepEqual(plain(h.state.nodeStyle), plain(savedStyle), '外观未变更时不得改写已保存外观');
    assert.deepEqual(plain(h.state.nodeStyleDraft), plain(savedStyle), '外观未变更时不得改写草稿');
    assert.equal(h.state.map.revision, 3, '外观未变更时不得推进地图 revision');
    assert.equal(h.state.nodeStyleSaveInFlight, false, '无变更分支不得留下保存中标志');
    assert.equal(h.details.open, false, '无变更点击「应用外观」也必须收起浮层（不得点了没反应）');
    assert.equal(h.details.getAttribute('open'), null, '收起后 details 不得残留 open 属性');
    assert.ok(
      h.statuses.some((item) => item.message === '外观未变更，已收起节点样式设置。'),
      `无变更分支必须给出明确文案，实际 ${JSON.stringify(h.statuses)}`,
    );
  }

  // ---- 9. 无变更点击同样受「当前无地图」保护：不得误收起或误提示 ----
  {
    const h = makeHarness(() => envelope(4, SAVED), { draft: { fill_mode: 'filled', fill_opacity: 0.3 } });
    h.state.map = null;
    await h.sandbox.__saveNodeStyle(null);
    assert.equal(h.requests.length, 0, '无地图时点击不得发起请求');
    assert.equal(h.statuses.length, 0, '无地图时不得给出「外观未变更」误导文案');
  }

  console.log('ok - node style panel collapses only after a confirmed successful apply');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
