# Spec030 视图互斥缺陷 — 前端独立评审报告

- **评审对象**：分支 `codex/spec030-report-quality`（worktree `/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`）未提交改动
- **改动清单**（`git status --porcelain` 实测，仅以下 5 项）：
  - `frontend/app.js`（M，+25/-0）
  - `frontend/index.html`（M，+1/-1）
  - `tests/frontend/test_frontend_management_contract.py`（M，+1/-1）
  - `tests/frontend/test_frontend_view_exclusivity.js`（新增）
  - `tests/frontend/test_frontend_view_exclusivity_runtime.js`（新增）
- **评审范围纪律**：只读评审 `frontend/**` 与前端测试；未改任何代码、未 commit、未跑后端 pytest；未触碰主工作区 `/Users/wjh/ResearchAgent`。
- **结论：通过（Approve）**，无阻塞项。3 条 LOW 建议不阻塞合并。

---

## 一、三项必查逐项结论

### 必查 1：DOM 契约 —— PASS

**核对命令与命中**：

```
$ grep -n "main-area" frontend/index.html
122:    <section class="main-area" id="chat">
190:    <section class="main-area" id="research-view" hidden aria-labelledby="research-title">
378:    <section class="main-area" id="models-view" hidden>
388:    <section class="main-area" id="memory-view" hidden aria-labelledby="memory-title">
480:    <section class="main-area" id="kb-view" hidden>
587:    <section class="main-area" id="papers-view" hidden aria-labelledby="papers-title">
687:    <section class="main-area" id="literature-maps-view" hidden aria-labelledby="literature-maps-title">
693:    <section class="main-area" id="skill-tool-view" hidden aria-labelledby="skill-tool-title">
```

`grep -c "main-area" frontend/index.html` = **8**，与 `frontend/app.js:5251-5260` 的 `MAIN_AREA_VIEW_IDS` 8 项**集合完全一致**（双向无遗漏、无多余）。

| MAIN_AREA_VIEW_IDS 项 | index.html 真实 id | 行号 | 结论 |
|---|---|---|---|
| `chat` | ✅ | 122 | 一致 |
| `research-view` | ✅ | 190 | 一致 |
| `models-view` | ✅ | 378 | 一致 |
| `memory-view` | ✅ | 388 | 一致 |
| `kb-view` | ✅ | 480 | 一致 |
| `papers-view` | ✅ | 587 | 一致 |
| `literature-maps-view` | ✅ | 687 | 一致 |
| `skill-tool-view` | ✅ | 693 | 一致 |

任务特别点名的 4 个 id（`papers-view` / `skill-tool-view` / `memory-view` / `literature-maps-view`）**全部真实存在**，**无幽灵 id**，不存在「隐藏不到」的隐患。`hideAllMainAreas()` 用 `getElementById` + `if (section)` 空值兜底，即使将来 id 改名也只会静默跳过而非抛错。

**时序核对（`frontend/app.js:5270-5284`）**：

```js
5271  const nextView = view === 'papers' && !paperState.enabled ? 'chat' : view;
5272  if (nextView !== 'papers' && !paperView?.hidden) cancelPaperSearchPolling();
5277  hideAllMainAreas();                                    // 先整体隐藏 8 个
5278  document.querySelector('#chat').hidden = !isChat;       // 再精确显形 7 个
5279  document.querySelector('#models-view').hidden = nextView !== 'models';
5280  if (memoryView) memoryView.hidden = nextView !== 'memory';
5281  document.querySelector('#kb-view').hidden = nextView !== 'kb';
5282  if (paperView) paperView.hidden = nextView !== 'papers' || !paperState.enabled;
5283  if (literatureMapsView) literatureMapsView.hidden = nextView !== 'literature-maps';
5284  if (stView) stView.hidden = nextView !== 'skill-tool';
```

- 5278-5284 七条均为**无条件布尔赋值**，覆盖 `hideAllMainAreas()` 隐藏的全部 7 个（`research-view` 除外，其保持隐藏是本修复的目的），因此不存在「被 hideAll 隐藏后无人恢复」的目标视图。
- **`cancelPaperSearchPolling()` 无干扰**：定义在 `app.js:4665-4670`，只改 `paperState.searchSerial` / `searchController` / `paperSearchButton.disabled`，**不碰任何 `hidden`**。且它位于 5277 **之前**，先判 `!paperView?.hidden` 再取消轮询，读的是「上一状态」，语义与原实现一致，未被本次改动影响。
- **`paperState.enabled` 分支**：`enabled === false` 时 5271 先把 `nextView` 降级为 `chat`，5278 `#chat` 显示；5272 因 `nextView !== 'papers'` 且 papers 视图当时可见则取消轮询（合理）。即使 `nextView` 被强行置为 papers，5282 的 `|| !paperState.enabled` 也保证 papers 不会显形。分支自洽。
- CSS 侧仅 `.main-area` 基础样式（`styles.css:9`、`styles.css:2233`），本次**未新增任何 class**，DOM 契约的「class 双向存在」不受影响；`git --no-pager diff -- frontend/styles.css | wc -l` = **0**。

### 必查 2：`?v=N` —— PASS

- **只改一处、无遗漏**：`frontend/index.html:807` `src="/assets/app.js?v=67"`（原 `?v=66`）。全仓库仅 `frontend/index.html` 一个文件引用 `assets/app.js?v=`，无第二份入口页。
- **`styles.css` 无需递增**：`frontend/styles.css` 本次零改动（diff 为 0 行），其 `index.html:8` 的 `styles.css?v=67` 早已存在，不需动。
- **历史 compatibility 注释必须保留且已保留**：`index.html:806 / 809 / 810` 三行旧版本标记（`v=31..62`、`research-tasks.js?v=2/3/9/10/11`、`app.js?v=54`）被多个既有静态契约测试依赖，实例：`tests/frontend/test_research_report_notifications_contract.py:48`（v=47）、`tests/frontend/test_frontend_conversation_contract.py:64`（v=31）、`:221`（v=54）、`tests/frontend/test_frontend_map_analysis_contract.py:36`（v=62）、`tests/frontend/test_research_session_workspace_contract.py:60`（v=54）。本次改动**未删除也未篡改**这些注释，做法正确。
- **测试断言同步**：`tests/frontend/test_frontend_management_contract.py:80` 由 `v=66` 改为 `v=67`，与 HTML 真实值一致（该文件 `:79` 的 `styles.css?v=67` 未受影响）。

### 必查 3：XSS —— PASS

```
$ git --no-pager diff -U0 -- frontend/app.js | grep "^+" | grep -c "innerHTML"
0
```

新增 25 行全部为：中文注释、`Object.freeze([...])` 字符串字面量 id 数组、`forEach` + `section.hidden = true`、以及一处 `hideAllMainAreas();` 调用。**无 `innerHTML` / `insertAdjacentHTML` / `outerHTML` / `document.write`，无任何用户输入参与拼接**（`MAIN_AREA_VIEW_IDS` 是硬编码常量，不来自 URL / hash / 接口）。不引入新注入面。

---

## 二、额外风险问答

### Q1. 初始化 `showView('chat')`（app.js:5343）与 URL `#research-view` 直达并存时，`openForConversation()` 能否仍显示研究视图？`hideAllMainAreas()` 会不会让研究视图不可达？

**结论：可达，无功能回归。** 真实加载顺序实测如下。

`index.html` 中 `research-tasks.js`（804 行）先于 `app.js`（807 行）加载；`research-tasks.js:8` 在 IIFE 结束后立即 `api.boot(root.document)`，而 `boot()`（3583-3591）在 `hash === '#research-view'` 时用 `setTimeout(..., 0)` 排一次 `showView()` + `refreshWorkspace()`。因此**执行序恒为**：`research-tasks.boot` 同步 → `app.js:5343 showView('chat')` 同步 → 之前排入的 `setTimeout` 回调显示研究视图。

用与仓储一致的 vm 沙箱（原样摘取 `MAIN_AREA_VIEW_IDS` / `hideAllMainAreas` / `showView` 三段源码执行）复现，结果：

```
1) research-tasks 直达后可见: [ 'research-view' ]
2) app.js init showView(chat) 后可见: [ 'chat' ]      ← 缺陷已消除：不再「chat + research」双可见
3) 点深度研究后可见: [ 'research-view' ]              ← research-tasks.js:874 局部 showView() 仍能显示
```

- `openForConversation()`（`research-tasks.js:3478-3485`）内部依次调 `history.replaceState(...#research-view)` → 局部 `showView()` → `refreshWorkspace()`。局部 `showView()`（872-882）用 `doc.querySelectorAll('.main-area').forEach(s => s.hidden = s.id !== 'research-view')` **全量重算所有 8 个 `.main-area`**，天然与 `hideAllMainAreas()` 语义一致，不依赖 app.js 配合。
- 关键点：`hideAllMainAreas()` **只在 `showView()` 内部被调用**（`grep -n "hideAllMainAreas(" frontend/app.js` → 仅定义 5262 + 调用 5277），不会被 `setTimeout` 独立触发，因此不会「在 research-tasks 显示之后又把它藏掉」。
- 与主工作区侧栏「深度研究」入口（`app.js:2272-2276` 「查看研究进度」按钮：`nav.click()`，兜底 `location.hash = '#research-view'`）配合也成立：`nav.click()` 命中 `research-tasks.js:3519` 的 capture 监听 → 局部 `showView()`；兜底改 hash 则触发 `research-tasks.js:3575` 的 `hashchange` → `syncHistoryView()` → 局部 `showView()`。两条路径都能显示。

### Q2. 「深度研究」导航（research-tasks.js:3519 capture + stopImmediatePropagation）与「对话」导航（app.js:5324-5335）来回切换，是否恒只有一个 `.main-area` 可见？

**结论：是，恒为 1。** 实测（同一沙箱，含真实 nav 项集合）：

```
3) 点深度研究后可见: [ 'research-view' ]
4) 点对话后可见:    [ 'chat' ]
5) research→chat            [ 'chat' ]                OK
   research→models          [ 'models-view' ]         OK
   research→kb              [ 'kb-view' ]             OK
   research→memory          [ 'memory-view' ]         OK
   research→papers          [ 'papers-view' ]         OK
   research→literature-maps [ 'literature-maps-view' ] OK
   research→skill-tool      [ 'skill-tool-view' ]     OK
6) paperState.enabled=false 且请求 papers 可见: [ 'chat' ]   （降级正确，未出现双视图）
```

机制上是**双保险**，两条路径都能把可见集合收敛到 1：

1. **research → 其它**：`app.js:5334 showView(item.dataset.view)` → `hideAllMainAreas()` 先把 `research-view` 置 hidden。同时 `research-tasks.js:3553-3556` 的 capture 监听见 `event.target.closest('.nav-item[data-view], .new-chat')` 也会 `closeResearchView()`（884-893）。任一条生效即正确，两条同时生效结果一致。
2. **其它 → research**：`research-tasks.js:3519` capture + `stopImmediatePropagation()` 阻断 `app.js:5324` 的 bubble 监听，局部 `showView()` 把除 `research-view` 外 7 个置 hidden。

`history` 护栏（`research-tasks.js:3558-3569`）在 hash 非 `#research-view` 时调 `closeResearchView()`，与 app.js 的 `updateConversationUrl()`（2753-2760）/ `beginDraft()`（3057）不会互相打架到「两个都显示」——最坏情况是研究视图被关掉，即回到单视图。

### Q3. 是否存在绕过 `showView` 直接改 `hidden` 导致修复失效的路径？

**结论：不存在能造成「双视图」的绕过路径。**

```
$ grep -n "\.hidden\s*=" frontend/app.js | grep -v "hidden = true;"
```
逐一核对 60 处命中，全部是 `#chat` 内部的**子元素**（`contextStatus`、`memoryProjectLabel`、`paperImportPanel`、`loadOlderMessagesButton`、`projectList`、`conversationAction*Field` 等），**没有一处直接写 7 个 `.main-area` 容器的 `hidden`**（这些只出现在 5278-5284 的 `showView` 内）。

唯一在 app.js 之外全量写 `.main-area` 的地方是 `research-tasks.js:874`，其语义与注册表一致（全量重算）。`grep -rn "hidden = section.id" frontend/*.js` 仅命中该行。`closeResearchView()`（884-893）只把 `research-view` 置 hidden，只会更安全。`grep -n "style.display" frontend/app.js` 无命中，不存在用 display 绕过 `hidden` 的路径。

---

## 三、四项必守逐条判定

| # | 必守项 | 判定 | 核对依据 |
|---|---|---|---|
| 1 | **DOM 契约**（JS class ↔ styles.css 双向存在；`.main-area` id 全覆盖） | **PASS** | `grep -c "main-area" frontend/index.html` = 8，id 集合与 `app.js:5251-5260` 完全一致（详见必查 1 表）；本次未新增/修改任何 class，`git diff --stat -- frontend/` 显示仅 app.js +25、index.html +1/-1，`styles.css` diff 0 行 |
| 2 | **版本号 `?v=N`** | **PASS** | `grep -n "?v=" frontend/index.html` → 807 行为真实引用 `app.js?v=67`（唯一入口，全仓仅此一处）；`styles.css` 未改动无需递增；历史 compatibility 注释（806/809/810）保留 |
| 3 | **XSS**（禁 innerHTML 拼用户输入） | **PASS** | 新增 25 行 `grep -c innerHTML` = 0；全部为注释、常量数组、`section.hidden = true`；无用户输入参与 |
| 4 | **CSS 作用域** | **PASS（不适用但无污染）** | `git --no-pager diff -- frontend/styles.css \| wc -l` = **0**，本次零 CSS 改动，未新增选择器，无全局污染可能 |

---

## 四、问题清单（按严重级别）

### CRITICAL（0）— 无

### HIGH（0）— 无

### MEDIUM（0）— 无

### LOW（3 条，均为建议，不阻塞）

**[LOW-1] 静态契约测试部分断言未真正覆盖被测代码，属「构造-断言自身」式自证**
- 文件：`tests/frontend/test_frontend_view_exclusivity.js:37-73`
- 现象：`hiddenStatesFor(view)`（38-42）是按 `id !== view` **本地构造**的 Map，第 58-73 行的断言全部只在断言这个本地构造物，并未读取 `app.js` 的 `showView` 实现。唯一真正校验代码的是第 47-53 行的 id 集合比对。故若有人把 `showView` 里 5277 的 `hideAllMainAreas();` 删掉，本文件**仍会通过**（第 160-173 行的「旧实现对照」同样只是手写模拟，属恒真对照）。
- 影响：不产生回归风险（`_runtime.js` 已真实执行 `showView` 覆盖该点），但会误导后人以为静态文件在守护 `showView` 行为。
- 建议：删除 37-73 行的构造式断言，或改为断言 `app.js` 源码中 `showView` 函数体内 `hideAllMainAreas();` 出现在 7 条显隐赋值之前（文本顺序断言即可，不需执行）。

**[LOW-2] 视图注册表在 app.js 与 index.html 两处重复声明，新增视图存在漂移窗口**
- 文件：`frontend/app.js:5251-5260` vs `frontend/index.html:122/190/378/388/480/587/687/693`
- 现象：8 个 id 是手工同步的。`tests/frontend/test_frontend_view_exclusivity.js:49-53` 已加集合比对，能及时报红，风险已被测试收敛。
- 建议（可选）：后续可将 `.main-area` 改为运行时收集（`document.querySelectorAll('.app-shell > .main-area')`）以彻底消除双写，但会改变测试的静态可读性，属重构范畴，非本次缺陷必需。

**[LOW-3] `research-tasks.js:874` 与 `app.js` 各有一套「全量重算」逻辑（概念重复）**
- 文件：`frontend/research-tasks.js:874`
- 现象：两处都在做「遍历 `.main-area` 只留目标视图」。当前语义一致、行为正确，但未来若一侧增加视图或改变规则，仅同步一侧即会复发同类缺陷（`research-tasks.js` 的 v=21 与 `app.js` 的 v=67 是两个独立缓存版本，更容易分先后上线）。
- 建议：由 `research-tasks.js` 复用 `app.js` 暴露的同一入口（例如让 app.js 导出 `showMainArea(id)`），或在 `research-tasks.js` 头注释中明确「必须与 app.js `MAIN_AREA_VIEW_IDS` 保持一致」，便于后续维护者发现耦合点。

---

## 五、AI 生成代码专项检查

1. **行为回归与边界**：已覆盖 `paperState.enabled=false`、`#research-view` 直达、7 个导航互切、重复切换幂等（`_runtime.js:137-146` 与本次独立复现 Q2）。未发现行为回归。
2. **安全假设与信任边界**：无新增输入面；`MAIN_AREA_VIEW_IDS` 为常量，不受 URL/hash 污染。（`research-tasks.js:3558` 对 `history.pushState/replaceState` 的 monkey-patch 属既有代码，不在本次改动范围，且未在本次评审口径内变更。）
3. **隐式耦合 / 架构漂移**：Q1-Q3 已确认两个视图切换器的职责边界被写进注释（`app.js:5248-5250`、`5275-5276`），比修复前更清晰；残余耦合见 LOW-3。
4. **不必要的成本**：无模型调用、无新增依赖、无网络请求；净增 25 行 JS，零新增构建产物。

---

## 六、验证命令留证

```bash
$ node --check frontend/app.js
app.js syntax OK

$ node tests/frontend/test_frontend_view_exclusivity.js
ok - frontend view exclusivity contract          # exit=0

$ node tests/frontend/test_frontend_view_exclusivity_runtime.js
ok - frontend view exclusivity runtime (showView executed)   # exit=0
```

（按任务口径未运行后端 pytest。）

---

## 七、Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 3 | note |

**Verdict：通过（Approve）** —— 无 CRITICAL / HIGH / MEDIUM 问题。修复精准（25 行、单一入口、先全隐再精确显形），三项必查与三项风险问答全部实测通过，四项必守全 PASS。3 条 LOW 为测试写法与去重建议，可在后续 spec 中顺手处理，**不阻塞合并**。

**阻塞项：无。**

### 建议合并前由人工在浏览器确认的一点
自动化证据为 vm 沙箱 + 静态断言，**未做真实浏览器 DOM 渲染验证**。建议人工按原复现路径（`/c/<id>#research-view` → 滚动整页）确认页面总高已回落、sticky 侧栏不再透叠；再点「对话」/「深度研究」来回各一次确认无闪烁双视图。此为体验验收，不改变本报告通过结论。

---

## 附：评审日志路径

`.codebuddy/agent-logs/spec-030/task-00/frontend-reviewer/20261105-035739.md`
