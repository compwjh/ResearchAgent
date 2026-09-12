# Spec 026 前端独立评审报告（Task 04 + Task 05）

- 评审角色：frontend-reviewer（只读评审，未改动任何业务代码）
- 评审范围：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`（`backend/**` 不在本次范围，交 backend-reviewer）
- 评审依据：`docs/sdd/specs/026-reasoning-effort-feedback-fixes.md`、`docs/sdd/plans/026/task-04-frontend-optimistic-card.md`、`docs/sdd/plans/026/task-05-frontend-selector-states.md`
- 被评审改动：`git diff`（工作区未提交）`frontend/app.js +363`、`frontend/index.html`、`frontend/styles.css +40`；新增测试 `tests/test_spec026_task04_frontend_contract.py`、`tests/test_spec026_task05_frontend_selector_states.py`、`tests/test_spec026_task05_frontend_default_effort.py`；被修订的既有合同 `tests/test_spec024_frontend_contract.py`、`tests/test_frontend_task05_repair_contract.py`、`tests/test_frontend_task06_mobile_contract.py`

---

## 1. 结论

**打回（BLOCK）**

理由：存在 1 条 P0 —— 新增的 `errorTextFor` 兜底分支（`frontend/app.js:315`）被 5 个**非网络类**失败调用点命中，运行时仍会向用户显示「连接失败：本轮已中止」「连接失败：事件流中断」，直接违反 spec §前端错误文案映射的硬约束（「只有最后一类允许出现『连接失败』字样。其余一律不得使用该措辞」），也正是用户报出的缺陷 B 本体。三条静态合同测试**全部通过**却无法发现它（测试只统计 `errorTextFor` 函数体内部的字面量出现次数，看不见调用点）。另有 2 条 P1。

---

## 2. 实测输出（命令与结果，均为真实执行）

```
$ node --check frontend/app.js
（无输出，退出码 0）

$ grep -n "连接失败" frontend/app.js
315:  return { text: `连接失败：${message || '请求失败'}`, actions: [{ kind: 'retry', label: '重新发送' }] };
2215:    if (processing) { updateConversationProcessing(processing, { step_id: 'connection', kind: 'connection', label: '连接状态', status: error.retryable ? 'skipped' : 'failed', summary: error.retryable ? '连接中断，可重试' : '连接失败' }); ... }

$ grep -n "?v=" frontend/index.html
7:    <!-- ... /assets/styles.css?v=30 ... /assets/styles.css?v=35 -->
8:    <link rel="stylesheet" href="/assets/styles.css?v=37">
502:  <script src="/assets/vendor/purify.min.js?v=13"></script>
503:  <script src="/assets/vendor/marked.min.js?v=13"></script>
504:  <script src="/assets/kb-inspection.js?v=23"></script>
505:  <script src="/assets/conversation-research.js?v=1"></script>
506:  <!-- ... /assets/app.js?v=31 ... /assets/app.js?v=35 -->
507:  <script src="/assets/app.js?v=39"></script>

$ .venv/bin/python -m pytest tests/ -q -k "frontend" --basetemp=.pytest-tmp-review
141 passed, 1276 deselected, 5 warnings in 1.48s

$ .venv/bin/python -m pytest tests/test_spec026_task04_frontend_contract.py tests/test_spec026_task05_frontend_selector_states.py tests/test_spec026_task05_frontend_default_effort.py tests/test_spec024_frontend_contract.py -q --basetemp=.pytest-tmp-review
54 passed in 0.09s
```

补充 grep（DOM 契约双向核对，逐项命中）：

```
class                         JS 命中   CSS 命中
conversation-pending          3         1   (styles.css:52)
conversation-error-card       2         1   (styles.css:53)
conversation-error-actions    2         2   (styles.css:54-55)
conversation-error-action     1         2   (styles.css:55)
reasoning-effort-state        2         5   (styles.css:2323-2342)
reasoning-effort-recheck      1         1   (styles.css:2343)
reasoning-effort-notice       1         2   (styles.css:2349,2355)
is-loading / is-unknown / is-stale   1 / 1 / 1   1 / 1 / 1
```

```
$ git diff -U0 -- frontend/app.js | grep -n "innerHTML"
（无输出，退出码 1 → 新增 hunk 内无 innerHTML）
```

> 环境说明：沙箱拒建 pytest 临时目录，已统一加 `--basetemp=.pytest-tmp-review`（仓库内目录），属环境噪音，不影响结论。

---

## 3. 逐条核实（对应评审指令 12 条）

### 1) B5：点发送后 assistant 卡片在 `await fetch` 之前创建，且卡内显示「模型正在准备…」——**PASS**

- `frontend/app.js:2081` `let assistantMessage = createAssistantMessage(activeModel);`
- `frontend/app.js:2082` `setConversationPending(assistantMessage);`
- `frontend/app.js:2086` `const response = await fetch(endpoint, ...)` ← 在 2081/2082 之后
- 占位实现：`frontend/app.js:319-335`（`pending.textContent = text`，默认 `'模型正在准备…'`，`role="status"`），插入位置在 `.answer` 之前（`:326-330`）。
- 2081 之前的调用链全部同步（`:2071` `abortConversationStream()`、`:2073` `setConversationStatus`、`:2074-2076` `addMessage`），因此 500ms 由「同步执行」保证，不依赖任何 SSE 事件。
- 空输入守卫：`frontend/app.js:2070` `if (!String(question || '').trim()) return;` 位于 `createAssistantMessage` 之前，落实了 Task 04 §风险「输入校验失败不得留下空乐观卡片」。

### 2) B6：`meta` 到达时填充既有卡片，不新建第二张——**PASS**

- `frontend/app.js:2093-2108`：`meta` 分支内 **无** `createAssistantMessage(` 调用；只有 `clearConversationPending(assistantMessage)`（`:2106`）与 `modelTag.textContent = ...`（`:2107-2108`）。
- 二次 `meta` 由 `assistantMessage.dataset.metaSeen !== 'true'`（`:2094`）+ `acceptConversationEvent` 内 `:944` 双重拦截。
- 旧代码的 `assistantMessage.remove()`（原 meta 失败分支）已删除；现在 meta 未被接受时只设 `streamError`（`:2101-2104`），卡片保留由失败终态接管。

### 3) B7：流失败时卡片保留、就地转错误态、用户消息不动、占位被清——**部分 PASS（有残留风险）**

- 卡片保留：`frontend/app.js:2223` `renderConversationFailure(assistantMessage, error, { question })`；`catch` 内无 `assistantMessage.remove()`；`renderConversationFailure` 只 `classList.add('is-failed')`（`:347`）+ `dataset.phase = 'error'`（`:348`），样式 `.message.assistant.is-failed .bubble`（`styles.css:160`）已存在。
- 用户消息不动：`sendConversationMessage` 全文无 `input.value = question` 回填。
- 占位清理：
  - 成功路径 `:2106`；
  - 失败路径 `:346`（`clearConversationPending`）；
  - **中止/abort 分支**：`:2204-2212` 新增 `if (assistantMessage?.dataset.phase === 'pending') { clearConversationPending(...); dataset.phase = 'aborted'; }` → 中止后不会永久停在「模型正在准备…」。可达性确认：`abortConversationStream()`（`:2071`/`:1661`/`:1702`）会 `streamController.abort()` 并自增 `streamGeneration`（`:1653`），旧一轮 `fetch`/`read()` 必然以 `AbortError` 落进该分支。
- **残留风险（P2-4）**：`:2185` 的 `if (generation !== conversationState.streamGeneration) return;` 位于 `try` 内，`return` **不会**进入 `catch`，因此既不清理占位也不渲染错误态。当 generation 变化但控制器未被 abort（例如 `conversationState.streamController` 已被 `finally`（`:2226`）置空后再自增 generation）时，卡片可能永久停在「模型正在准备…」。我无法用静态证据证明该路径可达，列入「缺运行时证据」与 P2。

### 4) B8 + 文案表：五类文案与 spec 表格一一对应；409 含档位名 + 支持档位列表 + 两个按钮——**FAIL（409 基础形态 PASS，但兜底类别越界）**

逐行对照 `frontend/app.js:290-316` 与 spec §前端错误文案映射表：

| spec error.code | spec 文案 | 实现位置 | 实现文案 | 判定 |
|---|---|---|---|---|
| `REASONING_EFFORT_UNSUPPORTED` | 该模型不支持『<档位中文名>』推理档位，可选：<支持档位列表> | `:292-304` | 同 | PASS |
| `MODEL_CAPABILITIES_UNAVAILABLE` | 无法确认模型能力 | `:305-307` | 同 + `recheck` | PASS |
| `INVALID_REASONING_EFFORT` | 推理档位无效 | `:308-310` | 同 + `actions: []` | PASS |
| `MODEL_UNAVAILABLE` | 无法连接 Ollama 服务 | `:311-313` | 同 + `retry` | PASS |
| 真网络错误 | 连接失败：<原因> | `:315` | 同 + `retry` | PASS（但被越界复用，见 P0-1） |

- 409 档位名与列表：`:293` `supportedReasoningEfforts().map(reasoningEffortLabel).join('、')`；`:296` 拼「该模型不支持『X』推理档位，可选：…」；档位名取自**实际发送值** `error.effort`（`:2087` `error.effort = payload.reasoning_effort`）而非当前选择，语义正确。
- 两个按钮：`:297-302` `switch`（`用『<最高支持档>』重发`）+ `switchOnly`（`仅切换不重发`）；`handleConversationErrorAction`（`:401-421`）中 `switch` 先 `setReasoningEffort` + `persistConversationReasoningEffort` 再重发（`:411-417`），`switchOnly` 直接 `return`（`:416`）→ B15 语义正确。
- **缺陷（P2-1）**：当 `supportedReasoningEfforts()` 为空（`loadState === 'unknown'` 或后端返回空数组）时，`:296` 的「，可选：」段整体省略、`:297` 的 `highest` 为 `null` → `actions: []` → 卡片**既无支持档位列表也无任何操作按钮**，与 B8「必须包含支持档位列表、两个操作按钮」不符，且用户在卡片上没有任何恢复入口。可达性低（unknown 态下 `:635` 会把选中强制为 `off`，需后端连 `off` 都 409），故列 P2 而非 P1。

### 5) 硬约束：除「真网络错误」外，其它四类文案不得混入「连接失败」——**FAIL（P0）**

- `grep -n "连接失败" frontend/app.js` 只命中 `:315` 与 `:2215`。字面量层面看似干净，**但 `:315` 的兜底分支被以下 5 个非网络调用点命中**（这些调用点自身不含「连接失败」字面量，所以 grep 与静态测试都看不见）：

| 调用点 | 传入的 error | `error.code` | 实际显示文案 | 是否网络错误 |
|---|---|---|---|---|
| `frontend/app.js:1646`（`abortConversationStream`） | `new Error('本轮已中止')` | `undefined` | **「连接失败：本轮已中止」** | 否（用户主动中止） |
| `frontend/app.js:951`（`acceptConversationEvent` 序号无效） | `new Error('事件流中断：缺少有效事件序号')` | `undefined` | **「连接失败：事件流中断：缺少有效事件序号」** | 否（协议/序号问题） |
| `frontend/app.js:962`（`acceptConversationEvent` 序号跳变） | `new Error('事件流中断')` | `undefined` | **「连接失败：事件流中断」** | 否 |
| `frontend/app.js:2097`（首个 meta 序号无效） | `new Error('事件流中断：首个 meta 序号无效')` | `undefined` | **「连接失败：事件流中断：首个 meta 序号无效」** | 否 |
| `frontend/app.js:2199`（流结束但无 `done`） | `new Error('流式连接中断')` | `undefined` | 「连接失败：流式连接中断」 | 边缘（可接受） |

  调用链：`addConversationErrorNotice(message, error)`（`:384-389`，`context` 默认 `null`）→ `renderConversationFailure`（`:344`）→ `errorTextFor(error?.code, error?.message, error?.effort)`（`:363`）→ 四个 code 分支全部不匹配 → 落到 `:315`。

  可达性（`:1646` 那条最典型、最容易撞上）：
  - 流式输出**进行中**再点发送第二条 → `:2071` `abortConversationStream()` → `:1640` 命中 `[data-stream-active="true"]` 的卡片 → `:1646`；
  - 流式进行中切换历史会话 → `:1661`；流式进行中点「新会话」→ `:1702`。

  这三条都是日常操作，且显示的是「连接失败」，正是用户抱怨的缺陷 B。
- 结论：`grep` + `test_only_the_network_fallback_mentions_connection_failure`（只对 `_function_source("errorTextFor")` 做 `source.count("连接失败") == 1`）**均无法发现**该问题——这是本次评审最关键的发现，也说明静态契约测试在本缺陷上失效。
- 另外 `:2215`（processing 步骤 label，未改动行）在**流式途中失败**时会写 `summary: '连接失败'`。对 409/400/503 这类「响应非 ok」的失败，`processing` 仍为 `null`（`:2083` 初始化，`:2124` 才被 meta 赋值），故不会触发；仅在流中途失败时触发，措辞尚可接受，**不单独计为问题**，仅登记。

### 6) B15：「重新检测能力」不重发用户消息——**PASS（静态）**

- 卡片内按钮：`frontend/app.js:403-410`，`action.kind === 'recheck'` 分支只 `await loadReasoningOptions(activeModel, { refresh: true })` 后 `return`，分支内无 `sendConversationMessage(`。
- 状态条按钮：`frontend/app.js:573-581`（`appendRecheckButton`）同样只调 `loadReasoningOptions(activeModel, { refresh: true })`。
- `refresh=1` 真正拼进 URL：`frontend/app.js:613` `...${refresh ? '&refresh=1' : ''}`。
- 「用『Y』重发」才重发：`:418-420`（仅 `switch`/`retry` 落到该行）。
- 运行时未验证：未用浏览器 Network 面板确认「点重新检测后无新的 `/messages` POST」。

### 7) B11 红线：用户经 `change` 显式选择的档位绝不被 `reconcileEffortWithCapabilities` 改写——**PASS（静态）**

- `frontend/app.js:682-687`：
  ```
  reasoningEffortSelect?.addEventListener('change', () => {
    const previous = reasoningOptionsState.lastEffort;
    const previousDefault = reasoningOptionsState.defaultEffort;
    const effort = setReasoningEffort(reasoningEffortSelect.value);
    persistConversationReasoningEffort(effort, previous, previousDefault);
  });
  ```
  监听体内**没有** `reconcileEffortWithCapabilities`、没有 `loadReasoningOptions`；`persistConversationReasoningEffort`（`:663-680`）成功分支只更新 `conversationState.conversation`，不触发重载。
- `reconcileEffortWithCapabilities` 的唯一调用点是 `frontend/app.js:648`（`loadReasoningOptions` 成功分支，`reason` 恒为 `'load'`）。
- `setReasoningEffort`（`:489-495`）不再含 `'xhigh'` 兜底（`grep "defaultEffort || 'xhigh'"` 无命中）；`normalizeReasoningEffort(value, fallback = 'off')`（`:484`）。
- **附带问题（P2-2）**：`reconcileEffortWithCapabilities` 的 `if (reason === 'user') return desiredNorm;`（`:530`）**在仓库内没有任何调用者**（唯一调用点传 `'load'`）→ 死参数。B11 的实际保障只是「change 监听不调 reconcile」，而 `reason === 'user'` 这行给读者造成「有代码在守 B11」的错觉，测试 `test_reconcile_corrects_unsupported_but_respects_user_explicit` 也只断言该字符串存在。

### 8) B9/B10：切换模型、载入历史会话时校准到支持的最高档 + 一次性提示、不重复刷——**PASS（静态）**

- 来源标注：`:481` `loadReasoningOptions(activeModel, { source: 'model-switch' })`；`:1683` `{ selectedEffort: conversation.reasoning_effort || null, source: 'session' }`；`:247` `{ source: 'initial' }`。
- 期望值链：`:643-647`
  ```
  const callSource = source || (refresh ? 'refresh' : 'initial');
  const keepCurrent = callSource === 'refresh';
  const desired = keepCurrent
    ? (selectedEffort || lastEffort || conversation.reasoning_effort || defaultEffort || 'off')
    : (selectedEffort || defaultEffort || 'off');
  ```
  非刷新路径 `desired` 取 `selectedEffort || defaultEffort`。`defaultEffort` 在用户显式改档时被 `setReasoningEffort`（`remember: true`，`:493`）写成用户选择值，因此「切换模型 → 用户原档位越界 → 校准」成立。
- 校准与一次性提示：`:648` → `reconcileEffortWithCapabilities('load', desired)`（`:528-542`）：`supported.includes(desiredNorm)` 直接返回；否则取 `highestSupportedReasoningEffort()`，并用 `correctedKeys`（`Set`，key = `${model}|${conversationId || ''}`）去重（`:536-540`）→ 同一模型/会话只弹一次。提示 4s 自动隐藏（`:603`），新提示会 `clearTimeout` 重置。
- 档位序位不信任接口顺序：`:279-286` 用 `REASONING_EFFORTS.filter(...)` 再 `.at(-1)`，与 spec §数据模型「序位最高者」一致。
- 运行时未验证：真实模型切换 / 真实历史会话载入的选中值与提示次数。

### 9) B12：`unknown` 明确显示「能力未确认」，不得伪装成「本模型只支持关闭」；除 `off` 外全禁用——**PASS（静态）**

- 禁用集：`frontend/app.js:512-514` `const known = loadState === 'known' || loadState === 'stale'; const supportedSet = new Set(known && Array.isArray(supported) && supported.length ? supported : ['off']); supportedSet.add('off');` → `unknown` 时集合为 `{'off'}` → 仅 `off` 可用。
- 提示语明确是「未确认」而非「不支持」：`:515` `disabledTitle = loadState === 'unknown' ? '能力未确认，暂不可选此档位' : '该模型不支持此档位'`，并写进 `option.title`（`:520`）+ `aria-disabled`（`:519`）。
- 状态条：`:557-561` `'能力未确认'` + `appendRecheckButton`（重新检测）。
- 失败分支不再编造：`:654` `reasoningOptionsState.supported = null;`（`grep "supported = \['off'\]"` 无命中）；`:655-656` `defaultEffort = 'off'`、`loadState = 'unknown'`。同时 `:658` `syncReasoningEffortOptions('unknown', null, null)`。
- 「不得渲染成只支持关闭」这一点在文案层已满足（选择器内只显示「关闭」可用，但状态条明写「能力未确认」+ 重新检测）。

### 10) B13/B14：`stale` 按旧能力集禁用并显示缓存时间；`loading` 整体禁用且不闪烁——**PASS（静态）**

- `stale`：`:621-623` 按 `data.source === 'stale'` 置 `loadState='stale'` 且 `staleCachedAt = data.cached_at`（旧时间，不刷新）；`:512-514` 的 `known` 判定把 `stale` 纳入 → 禁用集来自旧 `supported_efforts`；`:563-568` 文案「沿用 X 前的能力检测结果」+ 重新检测。
- 时间格式化：`:583-595` `formatStaleTime` 用 `new Date(cachedAt)`；后端 `cached_at` 为 ISO 字符串（`backend/app/api/routes_conversations.py:225-229`），可解析；不可解析或未来时间返回 `''`，退化为「沿用旧能力检测结果」（`:565`），不显示 `NaN`。
- `loading`：`:610-611` 在 `await fetch` **之前**同步置 `loadState='loading'` 并 `syncReasoningEffortOptions('loading', null, null)`；`:500-509` 整体 `disabled = true` + 每个 option 禁用 + `:552-555` 「检测能力中…」+ `.is-loading` 转圈（`styles.css:2332-2340`，含 `@keyframes reasoning-effort-spin`）→ 不会出现「全灰只剩 off」的闪烁。
- 注意：`loading` 期间 `select.value` 未被重置（见 P1-1）。

### 11) 首屏默认档位：全新加载选中该模型支持的最高档，而不是 `off`——**加载完成后 PASS；加载窗口内存在 P1**

- 加载完成后：`:631-632` `const backendDefault = normalizeReasoningEffort(data?.default_effort, null); reasoningOptionsState.defaultEffort = backendDefault || highestSupportedReasoningEffort() || 'off';`
- 非刷新路径 `desired = selectedEffort || defaultEffort || 'off'`（`:647`）→ `reconcileEffortWithCapabilities('load', desired)`（`:648`）→ `setReasoningEffort(corrected, { remember: false })`（`:649`）。后端 `default_effort` 已按 Task 02/03 修正为「支持的最高档」，因此全新页面会选中最高支持档（`xhigh` 支持就用 `xhigh`，否则取支持的最高档）。初值 `lastEffort='off'`（`:28`）不再压过 `defaultEffort`——这正是 `tests/test_spec026_task05_frontend_default_effort.py:54-61` 所断言的修复。
- **但**：`frontend/index.html:93` 仍硬编码 `<option value="xhigh" selected>`，而 `loadReasoningOptions` 在 `loading` 期间不重置 `select.value`。`frontend/app.js:2077` 的 payload 直接读 `reasoningEffortSelect?.value`：
  ```
  reasoning_effort: normalizeReasoningEffort(reasoningEffortSelect?.value || reasoningOptionsState.lastEffort || 'off')
  ```
  → 见 P1-1。

### 12) 三项自查（DOM 契约 / `?v=N` / XSS / CSS 作用域）

- **DOM 契约：PASS**。见 §2 双向 grep 表：新增/修改的 10 个 class 全部在 `styles.css` 有真实定义，`styles.css` 新增的 13 条选择器全部在 `app.js`/`index.html` 有对应创建点（`styles.css:52-55`、`:2323-2356` ↔ `app.js:321/324/339/351/354/368/370/374/547/550/554/559/566/576/598`、`index.html:96-97`）。反向也成立：没有「只写 CSS 不渲染」或「只写 class 没样式」的孤儿。
- **`?v=N`：PASS**。`app.js` 35 → **39**（`index.html:507`），`styles.css` 35 → **37**（`index.html:8`），均较改动前递增；`?v=35` 兼容注释在两处保留（`index.html:7`、`:506`），满足 `tests/test_spec024_frontend_contract.py:43-44` 与三个 spec026 测试的 `_live_asset_version(...) >= N` 断言。
- **XSS：PASS**。新增 hunk 内 `innerHTML` 命中 0（`git diff -U0 | grep innerHTML` 退出码 1）。新增代码全部使用 `textContent`（`:332`、`:364`、`:376`、`:549`、`:553`、`:558`、`:565`、`:577`、`:600`、`:429`、`:2108`）或 `createElement` + `setAttribute`（`:325`、`:504`、`:519`、`:578`）。`error.message` 等后端可控文本一律经 `textContent` 落 DOM（`:364`），无字符串拼 HTML。既有 `innerHTML` 使用点（`:260`、`:445`、`:1062`、`:4002`）均为本次未改动代码，且 `:3959` 注明「先净化、后 innerHTML」策略。
- **CSS 作用域：PASS（有一致性瑕疵）**。Task 05 新增样式全部以 `.workspace` 限定（`styles.css:2323/2331/2332/2341/2342/2343/2349/2355`），而 `.workspace` 确为 `index.html:61` 的 `section.workspace`，且 `#reasoning-effort-state`（`index.html:96`）位于其内（`section.workspace` → `form.composer` → `.composer-footer`）→ 选择器可命中，不是死样式。Task 04 的 `.conversation-pending` / `.conversation-error-card` / `.conversation-error-actions`（`styles.css:52-55`）未加 `.workspace` 前缀，但均为类选择器、且与既有 `.conversation-error-notice`（`styles.css:50`）同风格，**未出现裸全局标签选择器**，不构成污染。仅登记为一致性瑕疵（P2-5）。

---

## 4. 四项必守逐条判定

| # | 必守项 | 判定 | 核对依据（命令 + 命中行） |
|---|---|---|---|
| 1 | DOM 契约（JS↔CSS 双向存在） | **PASS** | `grep -c` 逐项：`conversation-pending` JS=3/CSS=1(`styles.css:52`)、`conversation-error-card` 2/1(`:53`)、`conversation-error-actions` 2/2(`:54-55`)、`conversation-error-action` 1/2(`:55`)、`reasoning-effort-state` 2/5(`:2323-2342`)、`reasoning-effort-recheck` 1/1(`:2343`)、`reasoning-effort-notice` 1/2(`:2349,2355`)、`is-loading`/`is-unknown`/`is-stale` 各 1/1；反向 `grep -n` styles.css 新选择器全部在 `app.js`/`index.html` 有创建点 |
| 2 | `?v=N` 同步递增 | **PASS** | `grep -n "?v=" frontend/index.html` → `styles.css?v=37`（:8，原 35）、`app.js?v=39`（:507，原 35）；`?v=35` 兼容注释保留（:7、:506） |
| 3 | XSS（禁 `innerHTML` 拼接用户输入） | **PASS** | `git diff -U0 -- frontend/app.js \| grep innerHTML` → 退出码 1（无命中）；新代码仅 `textContent`/`setAttribute`（`app.js:332,364,376,549,553,558,565,577,600`） |
| 4 | CSS 作用域（不污染全局） | **PASS** | 新增样式限定 `.workspace`（`styles.css:2323-2356`）或为项目专属类选择器（`:52-55`）；无裸标签选择器新增 |

---

## 5. 问题清单（P0 / P1 / P2）

### P0-1 非网络类失败仍显示「连接失败：…」，违反 spec 文案硬约束（缺陷 B 未修净）

- **位置**：`frontend/app.js:315`（兜底分支）被 `frontend/app.js:1646`、`:951`、`:962`、`:2097`（另含边缘的 `:2199`）命中。
- **为什么是问题**：
  1. spec §前端错误文案映射（用户明确说明「那张表是硬合同」）写死「只有最后一类允许出现『连接失败』字样。其余一律不得使用该措辞」。用户主动中止（`:1646`）与事件流中断（`:951`/`:962`/`:2097`）都不属于「真网络错误（fetch 抛出 / 无响应）」。
  2. 这正是用户报出的缺陷 B（「所有错误都被显示成『连接失败：…请确认后重新发送。』」）的同一条症状，只是把硬编码从 `addConversationErrorNotice` 搬到了 `errorTextFor` 的兜底分支。
  3. 可达性高：流式输出进行中「再发一条 / 切会话 / 点新会话」都会走 `:1646`，用户会看到「连接失败：本轮已中止」——把主动中止说成连接失败，比原缺陷更具误导性。
  4. **静态测试全部通过却漏掉它**：`tests/test_spec026_task04_frontend_contract.py:79-85` 只在 `_function_source("errorTextFor")` 内数「连接失败」出现次数，不检查调用点；`grep -n "连接失败"` 同样看不到（调用点无字面量）。
- **建议改法**（择一，均属小改动）：
  - 给非网络失败显式打码：在 `:1646` 传 `Object.assign(new Error('本轮已中止'), { code: 'ABORTED' })`，在 `:951`/`:962`/`:2097` 传 `{ code: 'STREAM_INTERRUPTED' }`，并在 `errorTextFor` 增加两个分支（`ABORTED` → 「本轮已中止」，`STREAM_INTERRUPTED` → 「事件流中断」，两者均**不含**网络措辞、按 spec 可不给按钮或只给「重新发送」）；
  - 或把兜底收紧：仅当 `code == null && !error.aborted && !error.connectionInterrupted && !error.streamInterrupted` 时才输出「连接失败：…」，否则输出中性文案；
  - 并补一条**跨函数**的静态断言（对整个 `APP` 断言「连接失败」只出现在 `errorTextFor` 内且仅 1 处）＋一条「`:1646` 调用点带 `code`」的断言，防止回归。

### P1-1 `loading` 窗口内 payload 直接读 `reasoningEffortSelect.value`，缺陷 C 在窗口内残留

- **位置**：`frontend/index.html:93`（`<option value="xhigh" selected>`）+ `frontend/app.js:2077`（payload）+ `frontend/app.js:610-611`、`:500-509`（loading 只禁用、不重置选中值）。
- **为什么是问题**：`loadReasoningOptions` 进入 `loading` 时只做 `select.disabled = true` 与 option 禁用，**不改变 `select.value`**。因此：
  - 全新页面：`select.value` 仍是 HTML 硬编码的 `xhigh`；
  - 切换模型：`select.value` 仍是**上一个模型**的档位（如 `xhigh`）。
  此时用户若点发送，`frontend/app.js:2077` 会把该值原样写进 `reasoning_effort` → 若模型不支持 → 后端 409 → 正是 spec 要消灭的缺陷 C（「不支持的档位也能选、选了才报 409」）。窗口不是瞬时：按 spec 描述，能力探测是 5 档串行、每档 `timeout=5`，最坏约 25s。发送按钮在此期间**未被禁用**（`sendButton.disabled` 只在 `:2231` 提交处理与 `:2226` finally 中管理）。
- **建议改法**：`frontend/app.js:2077` 改为在 `loadState === 'loading'` 或 `reasoningEffortSelect.disabled` 时退回已知安全值，例如
  `reasoning_effort: normalizeReasoningEffort(reasoningOptionsState.loadState === 'loading' ? (reasoningOptionsState.lastEffort || 'off') : (reasoningEffortSelect?.value || reasoningOptionsState.lastEffort || 'off'))`；
  或在 `loading` 期间同步 `sendButton.disabled = true`（配合状态条文案「检测能力中…」），能力返回后再放开。

### P1-2 错误卡片重发复用「最后一个 `.message.user`」，会覆盖新提问气泡的 `messageId`

- **位置**：`frontend/app.js:2074-2076`（`appendUser: false` 时取 `[...messages.querySelectorAll('.message.user')].at(-1)`）、`frontend/app.js:420`（新错误卡片按钮触发该路径）、`frontend/app.js:2120`（`userMessage.dataset.messageId = userMessageId`）。
- **为什么是问题**：这条路径在改动前**是死代码**（`git show HEAD:frontend/app.js | grep sendConversationMessage` 只有定义与表单提交两处），本次新增的错误卡片按钮（`:418-420`）让它首次可达。触发序列：发送 Q1 得到 409 卡片 → 用户忽略卡片、另发 Q2 → 点击 Q1 卡片上的「重新发送」→ `userMessage` 取到的是 **Q2 的气泡**，随后 `:2120` 把 **Q1 的 `user_message_id`** 写进 Q2 气泡，覆盖其原有正确值。下游 `startMemoryAnalysisPolling(userMessageId, ...)` 与轮询校验（`app.js:1140`/`:1148` 比对 `messageElement.dataset.messageId !== messageId`）会指向错误消息 → 记忆分析结果可能挂到错误的气泡下。
- **建议改法**：建卡时把该卡对应的 user 气泡引用一并存入 `context`（例如 `renderConversationFailure(assistantMessage, error, { question, userMessage })`），重发时通过 `context.userMessage` 定位，而不是重新查询「最后一个 user 气泡」；或在 `appendUser: false` 分支显式要求调用方传入目标气泡。

### P2 级（建议修，不阻塞）

- **P2-1** `frontend/app.js:293-302`：`supportedReasoningEfforts()` 为空时，409 卡片既无「可选：」列表也无任何按钮（`highest === null` → `actions: []`），与 B8 不符且用户无恢复入口。建议在该情形下追加 `recheck` 动作（「重新检测能力」）。
- **P2-2** `frontend/app.js:530`：`reconcileEffortWithCapabilities` 的 `if (reason === 'user')` 分支**无任何调用者**（唯一调用点 `:648` 传 `'load'`），属死参数；B11 的真实保障是「change 监听不调 reconcile」。建议删除该参数，或在注释中写明「保留以备将来显式触发」并补测试说明。
- **P2-3** `frontend/app.js:391-395`：`addConversationError(error, context)` 已成死代码——`assistantMessage` 现在恒非 `null`（`:2081` 无条件创建），`:2224` 的 `else if (!streamError) addConversationError(...)` 永远不执行。建议删除该函数与调用分支，避免读者误以为存在「无卡片」失败路径。
- **P2-4** `frontend/app.js:2185`：`if (generation !== conversationState.streamGeneration) return;` 位于 `try` 内，`return` 不经过 `catch`，既不 `clearConversationPending` 也不渲染失败态。若该路径可达（generation 变化但控制器未被 abort），卡片会永久停在「模型正在准备…」。建议在 `finally` 中兜底：若 `assistantMessage.dataset.phase === 'pending'` 则清占位并转中性终态。
- **P2-5** `frontend/app.js:368`：`renderConversationFailure` 在 `card.querySelector('.conversation-error-actions')` 已存在时提前 `return`，但 `:364` 已经更新了 `notice.textContent` → 若同一卡片二次失败且 `code` 不同，会出现「文案是新类别、按钮是旧类别」的不一致。当前调用顺序下基本不可达，建议把按钮组与文案一起重建（或同时早退），保证二者同源。
- **P2-6** `frontend/index.html:96`：`#reasoning-effort-state` 是 `role="status"` + `aria-live="polite"` 的 live region，但 `appendRecheckButton`（`:573-581`）会往里插 `<button>`。live region 内放可交互元素会被读屏器反复朗读且可能被跳过。建议把「重新检测」按钮移到 live region 之外（或把 live region 只包住文本节点）。已确认 `btn.type = 'button'`（`:575`），位于 `<form id="chat-form">`（`index.html:82`）内不会误触发提交。
- **P2-7（一致性）** Task 04 的 `.conversation-*` 新增样式（`styles.css:52-55`）未按 Task 05 的方式加 `.workspace` 前缀。不构成污染（无裸标签选择器），仅风格不一致。

---

## 6. 缺运行时证据的边界（本次评审最重要的产出）

**结论：本次所有 spec 026 前端边界的行为证据，100% 来自「静态源码子串断言」，没有任何一条有运行时证据。** 三个测试文件（`tests/test_spec026_task04_frontend_contract.py`、`tests/test_spec026_task05_frontend_selector_states.py`、`tests/test_spec026_task05_frontend_default_effort.py`）都只用 `_function_source(name)` 从 `app.js` 源码里按大括号配对抽取函数体文本，再做 `assert "字符串" in source`。它们验证的是**文本存在性**，不是**运行时行为**。

由此带来的两个已被证实的失真：

1. **假阳性**：P0-1 就是活证据——`test_only_the_network_fallback_mentions_connection_failure`（`tests/test_spec026_task04_frontend_contract.py:79-85`）断言 `source.count("连接失败") == 1` 并通过，但运行时 `:1646` 会显示「连接失败：本轮已中止」。测试看不到调用点。
2. **断言可被注释/死代码满足**：例如 `test_reconcile_corrects_unsupported_but_respects_user_explicit`（`tests/test_spec026_task05_frontend_selector_states.py:126-138`）断言 `"reason === 'user'" in body`，而该分支实际无调用者（P2-2）；`test_reconcile_corrects_unsupported_but_respects_user_explicit` 与 `test_change_handler_does_not_invoke_reconcile`（`:141-147`）合起来只证明「change 监听体内没有那个字符串」，不证明「用户选档后不会被改写」。

逐边界列出**只有静态断言、缺运行时证据**的项：

| 边界 | 静态断言位置 | 缺什么运行时证据 |
|---|---|---|
| B5（发送后 500ms 内卡片存在） | `task04:173-178` | 真实浏览器里 `document.querySelectorAll('.message.assistant').length` 的时序/耗时；`setConversationPending` 的 DOM 插入位置与可见性 |
| B6（`meta` 后卡片不重复） | `task04:181-188` | 真实 SSE 到达后 assistant 卡片计数仍为 1；`clearConversationPending` 真的移除了占位节点 |
| B7（失败时卡片保留 + 就地错误态） | `task04:208-223` | 真实 409/断网后卡片仍在 DOM、`is-failed` 生效、`.answer` 已生成内容未被清空 |
| B7-abort（中止不留占位） | 无任何断言 | 流式中途再发一条后，旧卡片 `data-phase` 变为 `aborted` 且无 `.conversation-pending` 残留（含 P2-4 的 `:2185` 路径） |
| B8（409 文案 + 两个按钮可点） | `task04:97-122` | 真实 409 下文案完整（含档位名与列表）、两个按钮真的出现在 DOM 且点击行为正确 |
| 硬约束（非网络类不得出现「连接失败」） | `task04:79-85` | **已证实失效**（P0-1）：需要跨函数的运行时/DOM 断言 |
| B15（重新检测不重发） | `task04:235-243`、`task05:117-120` | 浏览器 Network 面板确认点击后无新的 `POST /api/conversations/messages` |
| B9/B10（切模型/载入会话校正 + 一次性提示） | `task05:126-138`、`default_effort:54-74` | 真实切换模型与打开历史会话后 `select.value` 等于最高支持档；提示恰好出现一次、不重复刷 |
| B11（用户显式选择不被改写） | `task05:141-147` | 真实用户 `change` 后发送，payload 的 `reasoning_effort` 与所选一致（含后端 409 兜底路径） |
| B12（`unknown` 不伪装成「只支持关闭」） | `task05:83-96`、`spec024:106-115` | 真实 `unknown` 响应下：选择器除 `off` 外全禁用、状态条显示「能力未确认」、DOM 中不存在「只支持关闭」类文案 |
| B13（`stale` 显示旧缓存时间） | `task05:99-108` | 真实 `stale` 响应下 `formatStaleTime` 的实际输出（含 `cached_at` 为 ISO 字符串时的「X 分钟」文案）与禁用集合一致性 |
| B14（`loading` 整体禁用、不闪烁） | `task05:111-114` | 真实加载期间无「全灰只剩 off」闪烁；`@keyframes reasoning-effort-spin` 实际渲染 |
| 首屏默认档位（支持 xhigh 用 xhigh，否则最高档） | `default_effort:54-61` | 真实首屏加载后 `select.value` 的值（且需覆盖 P1-1 的 loading 窗口） |
| P0-1 / P1-1 / P1-2 | 无 | 全部无静态断言，纯逻辑推演得出（已在 §5 给出 `文件:行` 证据链，但未在真实浏览器复现） |

**建议的补证手段**（供 Task 06 / 后续回归参考，非本次评审要求）：引入 jsdom（或 Playwright/Puppeteer）加载 `app.js`，用可注入的 `fetch` mock 驱动 `sendConversationMessage` / `loadReasoningOptions`，对 DOM 做断言；至少在真实浏览器里跑一次 spec §验收方式 要求的「真实 Ollama smoke」：① 发送后 500ms 内卡片出现；② 真实 409 被分流为「该模型不支持…」而非「连接失败」；③ 中止/流中断不出现「连接失败」。

---

## 7. 未验证项（明确声明，未作结论）

1. **真实 Ollama / 后端 smoke 未执行**：本机未拉起 Ollama 与后端，未验证真实 409、真实 `stale`/`unknown` 响应下的前端表现。spec §验收方式 要求的「必须跑一次真实 Ollama smoke」**本次未做**，不得以静态测试结果替代。
2. **未在浏览器中加载页面**：无 DOM 断言、无 Network 面板核对、无截图；P0-1 / P1-1 / P1-2 的可达性由代码路径推演得出，**未在真实运行环境复现**。
3. **`loading` 窗口的最坏时长未实测**：约 25s 来自 spec 对「5 档串行 × timeout=5」的描述，未实测；P1-1 的影响面因此为估算。
4. **`cached_at` 的实际取值格式未实测**：仅从 `backend/app/api/routes_conversations.py:225-229` 读出为 `utc_now().isoformat()`（后端不在本次评审范围，未进一步核对 `utc_now` 的时区/格式）。
5. **`?v=` 历史编号空洞未核实**：`styles.css?v=36`、`app.js?v=36/37/38` 是否曾被占用（兼容注释只列到 35）未验证；因递增与 `>=N` 断言均满足，不影响结论。
6. **移动端布局未验证**：新增的 `#reasoning-effort-state` / `#reasoning-effort-notice`（`index.html:96-97`）插入 `.composer-footer` 后是否挤压移动端布局，未验证（`tests/test_frontend_task06_mobile_contract.py` 只做字符串断言）。
7. **既有测试的修订正当性只做了书面核对**：`tests/test_spec024_frontend_contract.py`、`tests/test_frontend_task05_repair_contract.py`、`tests/test_frontend_task06_mobile_contract.py` 的断言被改写。逐条读 diff 后认为修订有 spec 026 依据（B5/B6 取代「meta 分支建卡」、B12 取代「编造 supported=['off']」、文案表取代「请确认后重新发送」），且均附了理由注释，**未发现以「改测试」掩盖缺陷的情况**；但未做「旧断言是否仍有其他隐含约束」的穷尽分析。

---

## 8. 评审统计

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL(P0) | 1 | fail |
| HIGH(P1) | 2 | warn |
| MEDIUM(P2) | 7 | info |
| LOW | 0 | note |

**Verdict: BLOCK —— 1 条 P0 必须修复后方可合入（P0-1：非网络类失败仍显示「连接失败」，违反 spec 文案硬约束、即用户缺陷 B 未修净）。2 条 P1 建议同批修复（P1-1 loading 窗口仍可能发出不支持档位；P1-2 重发覆盖新提问气泡的 `messageId`）。**

四项必守：DOM 契约 **PASS** / `?v=N` **PASS** / XSS **PASS** / CSS 作用域 **PASS**。
静态门禁：`node --check` 通过、`-k frontend` 141 passed、指定 4 文件 54 passed —— 但**门禁全绿不等于行为正确**（见 §6）。
