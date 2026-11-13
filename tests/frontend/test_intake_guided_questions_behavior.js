'use strict';

/**
 * 深度研究 Intake「逐轮引导式询问」**执行级行为契约**（node:vm）。
 *
 * 从 `frontend/app.js` 原样摘取真实实现到沙箱执行（不复制影子实现），
 * 用最小 fake DOM 驱动 `renderIntakePrompt` 与回答协议纯函数，验证：
 *   - 进度 / 问题 / 按 choices 实际长度渲染（q_topic 可少于 3）/ ★推荐 / 自定义入口 / quick_actions；
 *   - 点候选、「用推荐」、「都按推荐」、自定义输入发出的文本逐字符合跨端契约 2.5；
 *   - 自定义输入 trim / 去换行与控制字符 / 限长 400 / 方括号防护；
 *   - 点击后 disabled 防重复提交、`prompt=null` 隐藏区块；
 *   - 渲染出的每个 class 都能在 styles.css 找到选择器（CSS ↔ DOM 双向契约）。
 *
 * 本文件由 test_intake_guided_questions_contract.py 经 subprocess 调用。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP_JS = fs.readFileSync(path.resolve(__dirname, '../../frontend/app.js'), 'utf8');
const CSS = fs.readFileSync(path.resolve(__dirname, '../../frontend/styles.css'), 'utf8');

// ---- 1. 原样摘取真实实现（从连续源码块，不复制影子实现） ----
const START = 'const INTAKE_CUSTOM_MAX';
const END = 'function createConversationIntake';
const start = APP_JS.indexOf(START);
const end = APP_JS.indexOf(END);
assert.ok(start >= 0 && end > start, 'app.js 必须定义 INTAKE_CUSTOM_MAX … renderIntakePrompt 连续块');
const SRC = APP_JS.slice(start, end);

// ---- 2. 最小 fake DOM 桩 ----
function makeEl(tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [], className: '', textContent: '', hidden: false,
    disabled: false, type: '', placeholder: '', maxLength: null, value: '',
    dataset: {}, attributes: {}, listeners: {},
    classList: {
      add(name) {
        if (!node.className.split(/\s+/).includes(name)) node.className = `${node.className} ${name}`.trim();
      },
      remove(name) {
        node.className = node.className.split(/\s+/).filter((part) => part && part !== name).join(' ');
      },
      contains(name) { return node.className.split(/\s+/).includes(name); },
    },
    setAttribute(key, value) { node.attributes[key] = String(value); },
    getAttribute(key) {
      return Object.prototype.hasOwnProperty.call(node.attributes, key) ? node.attributes[key] : null;
    },
    addEventListener(type, handler) { node.listeners[type] = handler; },
    appendChild(child) { node.children.push(child); return child; },
    append(...items) { node.children.push(...items); },
    replaceChildren(...items) { node.children = []; items.forEach((item) => node.children.push(item)); },
    focus() { node.focused = true; },
    click() { return node.listeners.click ? node.listeners.click({ preventDefault() {} }) : undefined; },
  };
  return node;
}

function walk(node, visit) {
  visit(node);
  for (const child of node.children) walk(child, visit);
}

function findAll(root, className) {
  const hits = [];
  walk(root, (node) => {
    if (String(node.className || '').split(/\s+/).filter(Boolean).includes(className)) hits.push(node);
  });
  return hits;
}

function texts(root, className) {
  return findAll(root, className).map((node) => node.textContent);
}

const sandbox = { document: { createElement: (tag) => makeEl(tag) } };
vm.createContext(sandbox);
vm.runInContext(SRC, sandbox);
vm.runInContext(
  'this.__api = { sanitizeIntakeCustom, intakeChoiceAnswer, intakeQuickAnswer, intakeCustomAnswer, renderIntakePrompt, INTAKE_CUSTOM_MAX };',
  sandbox,
);
const api = sandbox.__api;

// ---- 3. 契约样例数据（跨端契约 2.4 / 2.5，字段与 id 不得自改） ----
const PROMPT = {
  key: 'q_sources_capabilities', index: 5, total: 9,
  label: '来源与能力', question: '这次研究要从哪些来源检索、启用哪些能力？',
  choices: [
    { id: 'full', label: '全部能力', recommended: true },
    { id: 'search_eval', label: '检索+评估', recommended: false },
    { id: 'catalog_only', label: '仅目录检索', recommended: false },
  ],
  allow_custom: true, custom_label: '自定义（直接输入）',
};
const TOPIC_PROMPT = {
  key: 'q_topic', index: 1, total: 9,
  label: '研究主题', question: '请确认这次研究的主题',
  choices: [{ id: 'reuse', label: '沿用我刚才的描述', recommended: true }],
  allow_custom: true, custom_label: '自定义（直接输入）',
};
const QUICK_ACTIONS = [
  { id: 'use_recommended', label: '用推荐' },
  { id: 'use_all_recommended', label: '都按推荐' },
];
const PROGRESS = { answered: 4, total: 9 };

function render(prompt, quick = QUICK_ACTIONS) {
  const root = makeEl('div');
  root.className = 'conversation-intake-prompt';
  const sent = [];
  api.renderIntakePrompt(root, prompt, quick, PROGRESS, (text) => { sent.push(text); });
  return { root, sent };
}

function submitCustom(prompt, raw) {
  const { root, sent } = render(prompt);
  const input = findAll(root, 'conversation-intake-prompt-custom-input')[0];
  const button = findAll(root, 'conversation-intake-prompt-custom-submit')[0];
  assert.ok(input && button, 'allow_custom 为 true 时须渲染输入框 + 提交按钮');
  input.value = raw;
  button.click();
  return sent;
}

// ---- 4. 渲染：进度 / 问题 / 3 候选 / ★推荐 / 自定义入口 / quick_actions ----
{
  const { root } = render(PROMPT);
  assert.equal(root.hidden, false, '有 prompt 时区块须可见');
  assert.deepEqual(texts(root, 'conversation-intake-prompt-progress'), ['第 5 / 9 项']);
  assert.deepEqual(texts(root, 'conversation-intake-prompt-label'), ['来源与能力']);
  assert.deepEqual(texts(root, 'conversation-intake-prompt-question'), ['这次研究要从哪些来源检索、启用哪些能力？']);

  const choices = findAll(root, 'conversation-intake-prompt-choice');
  assert.equal(choices.length, 3, '按 choices 实际长度渲染，不得硬编码 3 个');
  assert.ok(choices[0].classList.contains('is-recommended'), '★推荐项须带 .is-recommended');
  assert.equal(choices[0].textContent, '全部能力（推荐）', '★推荐项须标注「（推荐）」');
  assert.ok(!choices[1].classList.contains('is-recommended'));
  assert.equal(choices[1].textContent, '检索+评估');
  assert.equal(choices[2].textContent, '仅目录检索');
  assert.equal(choices[0].dataset.intakeChoice, 'full');

  assert.equal(findAll(root, 'conversation-intake-prompt-custom-input').length, 1, 'allow_custom 须有自定义输入框');
  assert.equal(findAll(root, 'conversation-intake-prompt-custom-submit').length, 1, 'allow_custom 须有提交按钮');
  assert.equal(findAll(root, 'conversation-intake-prompt-custom')[0].children.length, 2);

  const quicks = findAll(root, 'conversation-intake-prompt-quick-action');
  assert.equal(quicks.length, 2, '按 payload.quick_actions 渲染');
  assert.deepEqual(quicks.map((b) => b.textContent), ['用推荐', '都按推荐']);
  assert.deepEqual(quicks.map((b) => b.dataset.intakeQuick), ['use_recommended', 'use_all_recommended']);
}

// ---- 5. q_topic / q_objective 允许少于 3 个候选 ----
{
  const { root } = render(TOPIC_PROMPT);
  const choices = findAll(root, 'conversation-intake-prompt-choice');
  assert.equal(choices.length, 1, 'q_topic 的 choices 允许少于 3 个，前端按实际长度渲染');
  assert.equal(choices[0].textContent, '沿用我刚才的描述（推荐）');
}

// 无 choices / 无 quick_actions 时容器仍存在且为空，不伪造候选
{
  const { root } = render({ key: 'q_objective', index: 2, total: 9, label: '研究目标', question: '目标？', choices: [], allow_custom: false }, []);
  assert.equal(findAll(root, 'conversation-intake-prompt-choice').length, 0);
  assert.equal(findAll(root, 'conversation-intake-prompt-custom-input').length, 0, 'allow_custom=false 不得渲染自定义入口');
  assert.equal(findAll(root, 'conversation-intake-prompt-quick-action').length, 0);
}

// ---- 6. 点候选 → 契约 2.5 协议文本（逐字） ----
{
  const { root, sent } = render(PROMPT);
  const choices = findAll(root, 'conversation-intake-prompt-choice');
  choices[0].click();
  assert.deepEqual(sent, [
    '【研究参数】来源与能力：全部能力（推荐） [intake:q_sources_capabilities=full]',
  ]);
  assert.ok(choices.every((button) => button.disabled), '点击后须给按钮 loading/disabled 态');
  assert.ok(choices[0].classList.contains('is-selected'), '选中态 .is-selected');
  assert.ok(choices[0].classList.contains('is-loading'), '提交中态 .is-loading');
  choices[1].click();
  assert.equal(sent.length, 1, '同一轮不得重复提交');
}
{
  const { root, sent } = render(PROMPT);
  findAll(root, 'conversation-intake-prompt-choice')[1].click();
  assert.deepEqual(sent, [
    '【研究参数】来源与能力：检索+评估 [intake:q_sources_capabilities=search_eval]',
  ]);
}

// ---- 7. 「用推荐」/「都按推荐」文本 ----
{
  const { root, sent } = render(PROMPT);
  findAll(root, 'conversation-intake-prompt-quick-action')[0].click();
  assert.deepEqual(sent, [
    '【研究参数】来源与能力：用推荐 [intake:q_sources_capabilities=use_recommended]',
  ]);
}
{
  const { root, sent } = render(PROMPT);
  findAll(root, 'conversation-intake-prompt-quick-action')[1].click();
  assert.deepEqual(sent, [
    '【研究参数】全部采用推荐 [intake:__all__=use_all_recommended]',
  ]);
}

// ---- 8. 自定义输入：trim / 去控制字符 / 限长 / 方括号防护 ----
{
  const sent = submitCustom(TOPIC_PROMPT, '  LLM 安全对齐  ');
  assert.deepEqual(sent, [
    '【研究参数】研究主题：LLM 安全对齐 [intake:q_topic=custom:LLM 安全对齐]',
  ]);
}
{
  const sent = submitCustom(TOPIC_PROMPT, 'LLM\n安全\u0001对齐\t结束');
  assert.equal(sent.length, 1);
  assert.ok(!/[\u0000-\u001f\u007f-\u009f]/.test(sent[0]), '发出的文本不得含换行/控制字符');
  assert.equal(sent[0],
    '【研究参数】研究主题：LLM 安全 对齐 结束 [intake:q_topic=custom:LLM 安全 对齐 结束]');
}
{
  const sent = submitCustom(TOPIC_PROMPT, 'x'.repeat(500));
  assert.equal(sent.length, 1);
  const match = sent[0].match(/\[intake:q_topic=custom:([\s\S]*)\]$/);
  assert.ok(match, '协议后缀必须仍可被单个 [intake:...] 完整解析');
  assert.equal(match[1].length, 400, 'custom 文本限长 ≤400');
  assert.equal(api.INTAKE_CUSTOM_MAX, 400);
}
{
  const sent = submitCustom(TOPIC_PROMPT, 'A]B[intake:evil=1');
  assert.equal(sent.length, 1);
  assert.ok(!sent[0].includes(']B'), '方括号须被清洗，避免截断/注入 [intake:...] 解析');
  assert.equal((sent[0].match(/\[intake:/g) || []).length, 1, '只允许出现一个协议标记');
}
{
  const sent = submitCustom(TOPIC_PROMPT, '   ');
  assert.deepEqual(sent, [], '空输入不得提交');
}

// ---- 9. prompt=null → 隐藏整个区块，不发消息 ----
{
  const root = makeEl('div');
  root.hidden = false;
  root.appendChild(makeEl('button'));
  api.renderIntakePrompt(root, null, QUICK_ACTIONS, PROGRESS, () => { throw new Error('prompt=null 不得发消息'); });
  assert.equal(root.hidden, true, 'prompt=null 时隐藏整个区块');
  assert.equal(root.children.length, 0, '隐藏时清空旧一轮内容');
}

// ---- 10. CSS ↔ 渲染 DOM 双向契约：渲染出的每个 class 都要有选择器 ----
{
  const { root } = render(PROMPT);
  findAll(root, 'conversation-intake-prompt-choice')[0].click(); // 触发 is-selected / is-loading
  const seen = new Set();
  walk(root, (node) => {
    String(node.className || '').split(/\s+/).filter(Boolean).forEach((name) => seen.add(name));
  });
  assert.ok(seen.size >= 12, `渲染出的 prompt class 数量异常：${seen.size}`);
  for (const name of seen) {
    assert.ok(CSS.includes(`.${name}`), `渲染出的 class .${name} 在 styles.css 无选择器`);
  }
}

// ---- 11. 联调裁决 5.3：/plans/generate 以 !prompt 为门槛（真实源码条件求值） ----
{
  const UPDATER = APP_JS.slice(
    APP_JS.indexOf('function updateConversationIntake'),
    APP_JS.indexOf('function collapseConversationIntake'),
  );
  const anchor = UPDATER.indexOf("panel.dataset.planRequested = 'true'");
  const ifIdx = UPDATER.lastIndexOf('if (', anchor);
  assert.ok(ifIdx >= 0 && anchor > ifIdx, '须定位到 /plans/generate 触发 if');
  let depth = 0;
  let condEnd = -1;
  for (let i = ifIdx + 4; i < UPDATER.length; i += 1) {
    const ch = UPDATER[i];
    if (ch === '(') depth += 1;
    else if (ch === ')') {
      if (depth === 0) { condEnd = i; break; }
      depth -= 1;
    }
  }
  assert.ok(condEnd > ifIdx, '须能括号配对提取触发条件');
  const COND = UPDATER.slice(ifIdx + 4, condEnd);
  assert.ok(COND.includes('!prompt'), '触发条件须以 !prompt 为门槛');
  assert.ok(!COND.includes('!missingNames.length'), '触发条件不得再用 !missingNames.length');
  assert.ok(UPDATER.includes('/plans/generate'), '/plans/generate 端点仍在');

  function fires({ status = 'intake', prompt = null, missingNames = [],
    sessionId = 's1', hasPlan = false, planRequested = 'false' } = {}) {
    const sb = {
      status, prompt, missingNames,
      panel: { dataset: { researchSessionId: sessionId, planRequested } },
      assistantMessage: { querySelector: () => (hasPlan ? {} : null) },
    };
    vm.createContext(sb);
    return Boolean(vm.runInContext(`(${COND})`, sb));
  }

  // 首句说全 topic/objective/time_range：missing=[] 但 9 轮刚开始 → 不得提前生成计划
  assert.equal(fires({ prompt: { key: 'q_time_range', index: 3, total: 9 }, missingNames: [] }), false,
    'prompt 存在（逐轮询问中）不得触发 /plans/generate');
  assert.equal(fires({ prompt: { index: 5, total: 9 }, missingNames: ['language'] }), false);
  // 收齐：prompt=null → 触发
  assert.equal(fires({ prompt: null, missingNames: [] }), true, 'prompt=null 时照常触发');
  // 老投影无 prompt 键（undefined）→ 归一化等价于 null → 历史回放仍触发
  assert.equal(fires({ prompt: undefined, missingNames: [] }), true, '老投影无 prompt 键仍按原行为触发');
  // 既有其余门槛不回归
  assert.equal(fires({ status: 'completed', prompt: null }), false);
  assert.equal(fires({ prompt: null, hasPlan: true }), false);
  assert.equal(fires({ prompt: null, planRequested: 'true' }), false);
  assert.equal(fires({ prompt: null, sessionId: '' }), false);
}

// ---- 12~14. 联调裁决 5.4 / 5.5：状态文案、半角分号、旧轮次按钮、面板收尾 ----
{
  const STATUS_SRC = APP_JS.slice(
    APP_JS.indexOf('function intakeStatusLabel('),
    APP_JS.indexOf('function prepareNewResearchDraft('),
  );
  const FINALIZE_SRC = APP_JS.slice(
    APP_JS.indexOf('function collapseConversationIntake'),
    APP_JS.indexOf('function setIntakeEditStatus('),
  );
  assert.ok(STATUS_SRC.includes('正在确认研究参数'), '须有逐轮进度文案');
  assert.ok(FINALIZE_SRC.includes('.conversation-intake-prompt:not([hidden])'), '须感知可见引导区块');
  const sb2 = {};
  vm.createContext(sb2);
  vm.runInContext(STATUS_SRC + ';' + FINALIZE_SRC, sb2);
  const L = sb2.intakeStatusLabel;
  const finalize = sb2.finalizeConversationIntake;
  assert.equal(typeof L, 'function');
  assert.equal(typeof finalize, 'function');

  // 12. 逐轮文案取 prompt.index / prompt.total，且不显示「参数已齐」
  assert.equal(L('intake', [], { index: 5, total: 9 }), '正在确认研究参数 · 第 5/9 项');
  assert.equal(L('intake', [], { index: 1, total: 9 }), '正在确认研究参数 · 第 1/9 项');
  assert.equal(L('intake', ['topic'], { index: 9, total: 9 }), '正在确认研究参数 · 第 9/9 项');
  assert.ok(!L('intake', [], { index: 5, total: 9 }).includes('参数已齐'), '逐轮期间不得显示「参数已齐」');
  // 无 prompt（收齐 / 老投影）与各 status 分支语义不变
  assert.equal(L('intake', [], null), '参数已齐');
  assert.equal(L('intake', [], undefined), '参数已齐');
  assert.equal(L('intake', ['topic'], null), '收集中');
  assert.equal(L('completed', [], null), '参数已齐');
  assert.equal(L('ready', [], null), '参数已齐');
  assert.equal(L('running', [], null), '正在准备…');
  assert.equal(L('active_conflict', [], null), '已有进行中的研究');
  assert.equal(L('clarification', [], null), '需要补充说明');
  assert.equal(L('failed', [], null), '研究 Intake 失败');

  // 13. 半角分号与 [ / ] 同等剥离；协议文本格式不变
  const S = api.sanitizeIntakeCustom;
  assert.equal(S('A;B'), 'A B', '半角分号须剥离');
  assert.equal(S('A;B[C]D'), 'A B C D');
  assert.equal(S('LLM;安全对齐'), 'LLM 安全对齐');
  assert.equal(S(';'), '', '仅分号清洗后为空');
  const semiSent = submitCustom(TOPIC_PROMPT, '研究 A;B 两方面');
  assert.equal(semiSent.length, 1);
  assert.ok(!semiSent[0].includes(';'), '发出文本不得含半角分号（后端检出即拒绝）');
  assert.equal(semiSent[0],
    '【研究参数】研究主题：研究 A B 两方面 [intake:q_topic=custom:研究 A B 两方面]');
  // 旧轮次按钮：每条消息各自绑定自己那轮的 prompt.key，不硬编码
  const older = { key: 'q_time_range', index: 3, total: 9, label: '时间范围',
    question: '时间范围？', allow_custom: false,
    choices: [{ id: 'recent_3y', label: '近 3 年', recommended: true }] };
  const r1 = render(older);
  const r2 = render(PROMPT);
  findAll(r1.root, 'conversation-intake-prompt-choice')[0].click();
  findAll(r2.root, 'conversation-intake-prompt-choice')[0].click();
  assert.equal(r1.sent[0], '【研究参数】时间范围：近 3 年（推荐） [intake:q_time_range=recent_3y]');
  assert.equal(r2.sent[0], '【研究参数】来源与能力：全部能力（推荐） [intake:q_sources_capabilities=full]');
  assert.ok(r1.sent[0].includes('q_time_range') && !r1.sent[0].includes('q_sources_capabilities'),
    '旧轮次按钮只发自己那轮的 key（呼应裁决 5.2）');

  // 14. finalizeConversationIntake：可见引导区块 → 不折叠、不改 completed；既有收尾不回归
  function makePanel({ status = 'intake', missing = false, choices = false, promptVisible = false } = {}) {
    const body = makeEl('div');
    const toggle = makeEl('button');
    const summary = makeEl('p');
    const panel = {
      dataset: { status }, attributes: {}, _body: body, _toggle: toggle, _summary: summary,
      setAttribute(k, v) { panel.attributes[k] = String(v); },
      querySelector(sel) {
        if (sel.includes('conversation-intake-missing')) return missing ? { textContent: '待补充：时间范围' } : null;
        if (sel.includes('conversation-intake-choice')) return choices ? makeEl('button') : null;
        if (sel.includes('conversation-intake-prompt')) return promptVisible ? makeEl('div') : null;
        if (sel === '.conversation-intake-summary') return summary;
        if (sel === '.conversation-intake-toggle') return toggle;
        if (sel === '.conversation-intake-body') return body;
        return null;
      },
    };
    return panel;
  }
  const collapsed = (p) => p._body.hidden === true || p._toggle.attributes['aria-expanded'] === 'false';

  // 逐轮询问中：面板保持展开、status 保持 'intake'
  const p1 = makePanel({ status: 'intake', promptVisible: true });
  finalize(p1, 'completed');
  assert.equal(collapsed(p1), false, '逐轮询问期间不得折叠面板');
  assert.equal(p1.dataset.status, 'intake', '逐轮询问期间 dataset.status 不得改成 completed');
  // prompt=null 已隐藏引导区块：按既有规则折叠并标 completed
  const p2 = makePanel({ status: 'intake', promptVisible: false });
  finalize(p2, 'completed');
  assert.equal(collapsed(p2), true, '收齐后按既有规则折叠');
  assert.equal(p2.dataset.status, 'completed');
  // active_conflict / clarification 收尾不回归
  for (const st of ['active_conflict', 'clarification']) {
    const p = makePanel({ status: st });
    finalize(p, 'completed');
    assert.equal(collapsed(p), false, `${st} 保持可达`);
    assert.equal(p.dataset.status, st, `${st} 保持原 status`);
  }
  // hasMissing / hasChoices 既有判定不回归
  const pm = makePanel({ status: 'intake', missing: true });
  finalize(pm, 'completed');
  assert.equal(collapsed(pm), false, 'hasMissing 仍算待用户操作');
  const pc = makePanel({ status: 'intake', choices: true });
  finalize(pc, 'completed');
  assert.equal(collapsed(pc), false, 'hasChoices 仍算待用户操作');
  // failed 分支既有语义
  const pf = makePanel({ status: 'intake', promptVisible: true });
  finalize(pf, 'failed');
  assert.equal(pf._summary.textContent, '研究 Intake 失败');
}

console.log('ok - intake guided questions contract');
