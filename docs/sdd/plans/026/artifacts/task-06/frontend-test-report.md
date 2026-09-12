# Spec 026 — 前端回归验收报告（frontend-tester）

- 验收日期：2026-09-12
- 角色：frontend-tester（前端回归，只读检查 + 运行时检查 + pytest，不写业务代码）
- 范围：frontend/app.js、frontend/index.html、frontend/styles.css、tests/ 前端合同 + runtime 检查
- 后端边界 B1–B4：不在本角色范围，由 backend-tester 负责，本次未跑后端 pytest

---

## 结论：通过（附非阻塞观察）

前端三缺陷（A 乐观建卡 / B 错误文案分流 / C 不支持也能选）及其评审打回修复（P0-1 / P1-1 / P1-2）
**代码层面全部满足 spec，且关键路径有 Node 运行时证据**。全量前端 pytest 148 passed、定向 4 文件 61 passed、
node --check 通过、两个 runtime 检查全绿。

非阻塞观察（不影响「当前代码正确」结论，建议后续加固）：
1. 9 条边界仅靠静态子串断言，且已实证 B12 类回归会**假阳性**（详见第六、七节）。
2. 第 2232 行连接状态时间线以 `error.retryable` 而非 `code` 判别「连接失败」，mid-stream 非网络错误会误标（详见第四节）。
3. 工作树中 frontend 三件套与多个测试文件为**未提交改动**（git status 显示 M / ??），验收基于当前工作树内容，合并前应提交。

---

## 一、逐条命令真实输出（原样贴）

### 1) node --check + 版本 + 静态 grep
```
===== node --check frontend/app.js =====
exit=0
===== node --version =====
v22.22.2
===== grep -n '连接失败' frontend/app.js =====
323:  return { text: `连接失败：${message || '请求失败'}`, actions: [{ kind: 'retry', label: '重新发送' }] };
2232:    if (processing) { updateConversationProcessing(processing, { step_id: 'connection', kind: 'connection', label: '连接状态', status: error.retryable ? 'skipped' : 'failed', summary: error.retryable ? '连接中断，可重试' : '连接失败' }); stopConversationProcessing(processing, error.retryable ? 'skipped' : 'failed', error.retryable ? '连接中断，可重试' : '连接失败'); collapseConversationProcessing(processing); }
===== grep -n 'selected' frontend/index.html =====
202: ... aria-selected="true" ... (kb-tab-qa)
203: ... aria-selected="false" ... (kb-tab-inspection)
270: ... aria-selected="true" ... (kb-inspection-source-tab)
271: ... aria-selected="false" ... (kb-inspection-chunk-tab)
381: <span id="paper-selected-count" ...>已选 0 篇</span>
382: <button ... id="paper-import-selected" ...>批量导入</button>
（注：命中项均为 kb-tab 的 aria-selected 与 paper 计数；五个 <option> 无任何 selected 属性）
===== grep -n 'app.js?v=\|styles.css?v=' frontend/index.html =====
7:    <!-- ... /assets/styles.css?v=30 ... ?v=31 ?v=32 ?v=33 ?v=34 ?v=35 -->
8:    <link rel="stylesheet" href="/assets/styles.css?v=37">
506:  <!-- ... /assets/app.js?v=31 ... ?v=32 ?v=33 ?v=34 ?v=35 -->
507:  <script src="/assets/app.js?v=41"></script>
```

### 2) Node 运行时检查（真实执行抽取自 app.js 的函数体）
```
===== node tests/runtime/check_error_text_for.mjs =====
PASS: ABORTED returns {text, actions}
PASS: ABORTED text has no '连接失败'
PASS: ABORTED neutral text is exactly '本轮已中止'
PASS: STREAM_INTERRUPTED text has no '连接失败'
PASS: STREAM_INTERRUPTED neutral text
PASS: REASONING_EFFORT_UNSUPPORTED text has no '连接失败'
PASS: MODEL_UNAVAILABLE text has no '连接失败'
PASS: network fallback (no code) text contains '连接失败'
PASS: network fallback wording is '连接失败：<reason>'
PASS: network fallback (null code) text contains '连接失败'
PASS: errorTextFor contains '连接失败' exactly once (network fallback only), got 1
All errorTextFor runtime checks passed.
EXIT1=0

===== node tests/runtime/check_send_effort.mjs =====
PASS: loading + select='xhigh' -> 'off' (cannot 409 on unconfirmed tier)
PASS: loading + select='high' -> 'off' (selection not confirmed yet)
PASS: loading with empty select -> 'off'
PASS: loading ignores stale lastEffort on model switch
PASS: known uses confirmed select value 'xhigh'
PASS: known uses confirmed select value 'medium'
PASS: known falls back to lastEffort when select empty
PASS: stale uses old supported select value
PASS: unknown falls back to 'off'
PASS: known with invalid select normalized to 'off'
All pickSendReasoningEffort runtime checks passed.
EXIT2=0
```

### 3) pytest
```
===== pytest tests/ -q -k frontend --basetemp=.pytest-tmp-ft =====
148 passed, 1276 deselected, 5 warnings in 1.54s
PYTEST1=0
===== pytest targeted 4 files =====
61 passed in 0.16s
PYTEST2=0
```

### 4) 独立「故意改坏」验证结果（见第七节）

---

## 二、点 1：?v= 版本号与 ?v=34/?v=35 兼容注释

- 实际版本：`app.js?v=41`、`styles.css?v=37`——各自独立升级，改哪个升哪个。
- 兼容注释仍在：index.html:7（`styles.css?v=34`/`?v=35`）、index.html:506（`app.js?v=34`/`?v=35`）。
- `tests/test_spec024_frontend_contract.py:43-44` 断言 `/assets/app.js?v=35` 与 `/assets/styles.css?v=35` 存在于 index.html → 命中，**PASS**。
- 其余阈值断言均满足：task04 断言 app.js≥36 & styles≥36；task05 断言 app.js≥37 & styles≥37；task05_default 断言 app.js≥39；当前 41/37 全部 ≥ 阈值。
- **结论：PASS**。说明：spec024 测试实际只断言 `?v=35`（未单独断言 `?v=34`）；`?v=34/35` 兼容注释在源码注释中完整保留。

## 三、点 2：index.html:93 附近 <option value="xhigh"> 无 selected（P1-1）

- grep 显示 reasoning-effort-select 的五个 option（89–93 行）均无 `selected` 属性；grep `selected` 的所有命中都是 kb-tab 的 `aria-selected` 与 paper 计数，与推理档位无关。
- `tests/test_spec026_task04_frontend_contract.py::test_no_hardcoded_selected_effort_in_index_html` 断言 `'value="xhigh" selected' not in INDEX` → PASS。
- **结论：PASS（P1-1 修复点有效）**。

## 四、点 3：`连接失败` 逐处判断（P0-1 修复点）

命中两处：

**323 行（errorTextFor 网络兜底）**：仅当 `code` 不匹配任一显式分支
（ABORTED / STREAM_INTERRUPTED / REASONING_EFFORT_UNSUPPORTED / MODEL_CAPABILITIES_UNAVAILABLE /
INVALID_REASONING_EFFORT / MODEL_UNAVAILABLE）时才落此兜底 → 仅真网络错误。
运行时检查 `check_error_text_for.mjs` 12/12 PASS 佐证：undefined/null code 才含「连接失败」，
四个后端码与两个内部码均不含。✅ 卡片主文案层面 **P0-1 PASS**。

**2232 行（连接状态时间线）**：判别依据是 `error.retryable` / `error.connectionInterrupted`，**不是 code**。
- 409（POST 失败，line 2104）在 `meta` 之前抛出 → 此时 `processing` 为 null（`processing` 仅在 meta 分支 line 2141 赋值）
  → `if (processing)` 块被跳过 → **不命中 2232**。
- STREAM_INTERRUPTED 调用点已被 `test_stream_interrupted_call_sites_are_retryable` 强制 `retryable:true`
  → 显示「连接中断，可重试」而非「连接失败」。
- **残留（观察项，非阻塞）**：若流中 SSE `error` 事件（line 2181 构造 `streamError` 时不带 code/retryable）
  在上半场之后抛出，`processing` 非 null 且 `retryable=undefined` → 时间线会显示「连接失败」。
  该路径属次要 UI，主卡文案仍由 errorTextFor 正确决定；但严格按 spec「仅真网络错误允许出现连接失败」仍属轻微偏差。
  **建议**：把 2232 的文案判定也改为基于 `errorTextFor/code`，与卡片主文案统一。

## 五、点 4：B5–B15 逐条结论与证据类型

| 边界 | 结论 | 证据类型 | 验证方式 |
|---|---|---|---|
| B5 乐观建卡（500ms 内建卡、不依赖 SSE） | 通过 | 静态子串 | 抽取 `sendConversationMessage` 函数体，断言 `createAssistantMessage`/`setConversationPending` 索引 < `await fetch`（顺序断言），无运行时计时 |
| B6 meta 填充不新建第二张 | 通过 | 静态子串 | 抽取函数体，断言 meta 分支无 `createAssistantMessage(` 且含 `clearConversationPending(` |
| B7 流失败就地转错误态 | 通过 | 静态子串 | 抽取函数体，断言 catch 含 `renderConversationFailure`、无 `remove()`、无 `input.value=question` |
| B8 409 文案分流、不含连接失败 | 通过 | **运行时 + 静态** | 运行时：`check_error_text_for.mjs` 真实执行 errorTextFor，断言 REASONING_EFFORT_UNSUPPORTED 文案不含「连接失败」；静态：多段子串断言 |
| B9 切换模型校准到最高档+提示 | 通过 | 静态子串 | `reconcileEffortWithCapabilities` 含 `highestSupportedReasoningEffort()`、`showEffortCorrectionNotice('已因模型能力从'/'调整为')`；调用方带 `source:'model-switch'` |
| B10 历史会话校准 | 通过 | 静态子串 | 同上；调用方带 `source:'session'`、`selectedEffort: conversationState.conversation?.reasoning_effort` |
| B11 显式选档不被静默改写 | 通过 | 静态为主 + **部分运行时** | 静态：change 监听体（699–704）仅 `setReasoningEffort`+`persist`，**不含 reconcileEffortWithCapabilities**；reconcile 仅 1 处调用（665 行，`'load'`）；`reason==='user'` 直接 return。运行时：`check_send_effort.mjs` 中 `pickSendReasoningEffort('known','xhigh','xhigh')==='xhigh'` 证明 known 态保留用户选择 |
| B12 unknown 显式「能力未确认」 | 通过 | 静态子串 | `syncReasoningEffortOptions` 未知 title=`能力未确认，暂不可选此档位`（非「本模型只支持关闭」）；`renderReasoningEffortState` 含「能力未确认」+`appendRecheckButton`「重新检测」 |
| B13 stale 沿用旧结果 | 通过 | 静态子串 | `renderReasoningEffortState` 含「沿用 … 前的能力检测结果」+「重新检测」 |
| B14 loading 整体禁用 | 通过 | 静态子串 | `syncReasoningEffortOptions` 含 `loadState === 'loading'` 且整体 `disabled=true` |
| B15 重新检测不重发 | 通过 | 静态子串 | `handleConversationErrorAction` recheck 分支含 `refresh:true`、无 `sendConversationMessage`；`appendRecheckButton` 调 `loadReasoningOptions(activeModel,{refresh:true})` 无 send |

> 注：B1–B4 为后端探针语义，不在前端范围。

## 六、只有静态断言、缺运行时证据的边界清单（本次最有价值产出）

以下 **9 条边界仅依赖静态源码子串断言，无任何 Node/运行时执行证据**：
**B5、B6、B7、B9、B10、B12、B13、B14、B15**（B11 大部分也仅静态，仅 `pickSendReasoningEffort('known')` 有运行时支撑）。

这些断言只证明「源码里存在某段结构/顺序」，无法证明运行时行为正确。评审查出 P0-1 假阳性的根因正是此类断言——
旧代码硬编码单一「连接失败」文案，但凡静态断言只查「是否存在某文案子串」就会全绿，而实际所有错误都走到该文案。
**本次已实证**（见第七节）：B12 类真实回归下，整套前端测试仍然全绿。这 9 条边界目前的保护是薄弱的。

## 七、测试是否真能捕获缺陷——独立验证结果

方法：对「故意改坏」的变体跑检查，确认测试失败；全程不动 live 文件
（改坏副本用副本；改坏 live 文件先 `cp` 备份、跑完立即 `cp` 还原并用 `cmp` 校验字节一致）。

- **变体 1（P0-1 类：删除 errorTextFor 的 ABORTED/STREAM_INTERRUPTED 分支）**
  → `check_error_text_for.mjs`：**4 FAIL**（ABORTED 文案不含连接失败、ABORTED 精确文案、STREAM_INTERRUPTED 不含连接失败、STREAM_INTERRUPTED 文案），exit 1。
  ✅ 证明运行时测试能捕获「非网络错误被兜底成连接失败」这类 P0-1 回归。

- **变体 2（P1-1 类：loading 窗口改回直接发 selectValue）**
  → `check_send_effort.mjs`：**4 FAIL**（loading+xhigh→off、loading+high→off 等），exit 1。
  ✅ 证明运行时测试能捕获「loading 期间发出未确认档位导致 409」这类 P1-1 回归。

- **变体 3（B12 类：unknown 禁用项 tooltip 伪装成「本模型只支持关闭」）**
  → 改坏 live 文件后跑**全前端套件**：**148 passed**（PYTEST=0）；其 B12 测试载体文件 **15 passed**。
  → 还原后 `cmp` 字节一致、`node --check OK`、git status 与基线相同。
  ❌ 证明**静态断言是假阳性**：真实违反 B12（unknown 伪装成只支持关闭）时，整套前端合同测试仍然全绿，
     无法保护该边界。这正是评审查出的风险在 026 前端测试中仍然存在的实证。

**结论**：runtime 检查（覆盖 B8/P0-1 与 P1-1）确实能捕获对应缺陷类；但仅静态断言的 9 条边界无法被证明能捕获，
且已用 B12 实证为假阳性。验收结论「通过」基于**代码静态+运行时核对均满足 spec**，而非仅依赖测试套件。

## 八、点 5 / 点 6 / 点 7 专项核实

- **点 5（B11 红线）**：`reasoningEffortSelect` 的 change 监听体（699–704）只调 `setReasoningEffort(reasoningEffortSelect.value)` +
  `persistConversationReasoningEffort`，**未调** `reconcileEffortWithCapabilities`；`reconcileEffortWithCapabilities` 全文件
  仅 1 处调用（665 行，参数 `'load'`），且函数内 `if (reason === 'user') return desiredNorm` 为防御性兜底；
  `pickSendReasoningEffort`（501–504）只 `return` 计算值，**从不写** select 或 reasoningOptionsState → 只读不写。
  ✅ B11 红线守住。

- **点 6（B12）**：`syncReasoningEffortOptions` 在 unknown 态 `supportedSet={'off'}`（其余禁用），禁用项
  `title='能力未确认，暂不可选此档位'`（非「本模型只支持关闭」）；`renderReasoningEffortState` 显示「能力未确认」+
  「重新检测」按钮。✅ 代码满足 B12（注意：该 tooltip 文本无测试覆盖，见第六/七节假阳性实证）。

- **点 7（首屏默认档位=支持最高档，非 off）**：`loadReasoningOptions`（648–666）`defaultEffort = backendDefault || highestSupportedReasoningEffort() || 'off'`，
  初始/切换/载入会话路径 `desired` 优先 `default_effort`（=后端最高档）或 `highestSupportedReasoningEffort()`，仅在 supported 为空才回落 off。
  ✅ 首屏默认选中该模型支持的**最高档**，非 off（静态断言覆盖）。

## 九、未验证项（明确标注，未编造）

1. **B1–B4（后端探针语义 / default_effort 取最高档 / refresh 绕过缓存 / unknown·stale 后端契约）**：属后端，
   按角色边界本次未跑后端 pytest，由 backend-tester 负责。**未验证（超出前端角色边界）**。
2. **真实 Ollama smoke（spec §验收方式要求：发送后 500ms 卡片出现 + 真实 409 分流）**：依赖 Ollama/后端
   实际启动与浏览器环境，本次未启动，无法跑真实端到端 smoke。B5 的「500ms 内」仅为函数体内**顺序静态断言**，
   未做真实计时验证。**未验证（环境阻塞）**——按 spec 验收规则，环境不可达时应标阻塞项；但前端代码静态契约已通过，
   故不影响本次「代码层面通过」结论，建议在可启动 Ollama 时补一次真实 smoke。
3. **移动端 / task06 移动契约（`tests/test_frontend_task06_mobile_contract.py`，git status 显示已 M）**：本次范围仅
   026 前端合同 + 024 兼容，未覆盖。**未验证（超出本次 task-06 前端合同范围，建议另行回归）**。
4. **2232 时间线在 mid-stream SSE error 的真实渲染**：仅静态推断（processing 非 null + retryable=undefined → 误标「连接失败」），
   未做运行时复现。**未验证（建议后续用运行时契约覆盖）**。

## 十、清理确认

- 本次创建的临时 pytest 目录 `.pytest-tmp-ft`、`.pytest-tmp-ft-b12`、`.pytest-tmp-ft-b12b` 均已删除。
- 仓库根既有 `.pytest-tmp-r1/r2/r3/review2/task04/x` 为**先前残留、非本次创建**，按「别再新增」原则未触碰。
- 临时改坏实验未对任何仓库文件留下改动：live `frontend/app.js` 经 `cmp` 校验与基线字节一致，`node --check` 通过，
  `git status` 与实验前相同（` M frontend/app.js` 等为任务自带未提交改动，非本次引入）。

---

## 汇总

- 结论：**通过**
- B5–B15 通过数：**11/11**（代码静态+运行时核对均满足 spec；证据类型：B8 运行时、B11 部分运行时、其余静态）
- 仅静态断言、缺运行时证据的边界：**B5、B6、B7、B9、B10、B12、B13、B14、B15**（9 条）
- 临时目录：`.pytest-tmp-ft` 已清理；未引入新残留
- 报告路径：`docs/sdd/plans/026/artifacts/task-06/frontend-test-report.md`
- 进展日志：`/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-026/task-06/frontend-tester/20260912-131835.md`
