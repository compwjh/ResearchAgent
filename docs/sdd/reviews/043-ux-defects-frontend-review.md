# Spec043 缺陷修订 · 前端评审（Frontend Review）

| 项 | 值 |
|---|---|
| **评审者** | frontend-reviewer（子代理） |
| **角色** | 前端评审（只读；不改业务代码 / spec / 台账 / 测试） |
| **模型** | Deepseek-V4.1-Flash（按 spec 执行配置表 `043:441,446`，32k 档） |
| **分派方式** | 主会话一次性分派：只评 `frontend/**` + `tests/frontend/` 改动；后端 `backend/**` 不越界；产出本报告 |

## 评审基线

- 依据：`git diff -- frontend/`、`git diff -- tests/frontend/` 真实 diff（非 staged；本轮改动均在工作区）。
- 涉及文件：`frontend/literature-maps.js`(+267)、`frontend/app.js`(+89)、`frontend/index.html`(6)、`frontend/styles.css`(+9)、`frontend/literature-maps.css`(+3)；`tests/frontend/` 6 个 py + 1 fixture 版本断言同步，另有 4 个新增 `*.js` 测试。
- 已读依据：`docs/sdd/specs/043-literature-map-topic-exploration.md:424-458`（冻结范围）、`docs/sdd/reviews/043-ux-defects-tech-review.md`（结论与 P1 段）。
- 亲自执行：`node --check frontend/app.js` / `frontend/literature-maps.js` 均通过；4 个新 node 测试实跑全部 `ok`。

---

## 一、结论

# 结论：**通过（附 2 个 P1 前置条件 + 5 个 P2 收口项）**

四项必守 **4/4 PASS**，无 P0，XSS 干净，版本号与 10 处断言/1 处 fixture 完全一致。上轮 `T-P1-1`（`keepLocalView` 无调用方）**已接线并补了接线级测试**，形式闭合。但接线时把 `keepLocalView` 的成立条件从「显式传参 + 同图 + dirty」**放宽为「显式传参 + 同图」**，引入两个仅在「切回时本地仍 dirty」窗口下可触达的覆盖/串图风险（P1-1、P1-2），均定位精确、改动小，不构成打回。

---

## 二、三项必查 · 逐项结论

### 必查 1：DOM 契约 —— **PASS**

| 子项 | 判定 | 证据 |
|---|---|---|
| 卡片只显 `node_count`（不显目标数） | PASS | `literature-maps.js:1804-1810` `mapCardNodeCount()` 优先 `node_count`，仅缺失时回落 `requested_count`；`:1845-1847` 只 append `${cardNodeCount} 篇`；`sed -n '1836,1855p' \| grep -n "requested_count\|目标"` → 无命中（卡片区不出现「目标 N」） |
| partial 且有节点 → 显示「可用」 | PASS | `literature-maps.js:1815-1828` `mapCardStatusBadge()`：`status==='partial' && activeCount>0` → `badge.textContent = mapStatusLabel('ready')`（`'可用'`，见 `:448-454`） |
| 保留 `title` / `aria-label` | PASS | `:1825` `setAttribute('title', PARTIAL_MAP_CARD_NOTICE)`；`:1826` `setAttribute('aria-label', ...)`；常量定义 `:16-17` |
| partial 无节点仍「部分完成」 | PASS | `:1819-1820` `if (!(activeCount > 0)) return badge;` → 原样返回 `renderStatusBadge('partial')`（「部分完成」） |
| 筛选下拉仍含 partial | PASS | `literature-maps.js:1039` 选项数组仍含 `['partial','部分完成']`（未改） |
| `filteredMaps` 按原始 status | PASS | `:1642` `state.listStatus === 'all' \|\| map?.status === state.listStatus` —— 用 `map.status`，**不是**徽标文案；`mapCardStatusBadge` 只在渲染层改 `textContent`，`dataset.status` 仍 `partial`（`:834-837`） |
| 新增 class 在 CSS 真实存在（JS→CSS） | PASS | `data-availability="usable"`（`:1824`）↔ `literature-maps.css:39` `#literature-maps-view .literature-map-badge[data-availability="usable"]`；`kb-item-jump-target`（`app.js:5106`）↔ `styles.css:804,809` |
| CSS→JS 反向（无孤儿钩子） | PASS | `grep data-availability` 仅 `literature-maps.css:39` + `literature-maps.js:1824`；`grep kb-item-jump-target` 仅 `styles.css:804,809` + `app.js:5106` |
| `jumpToKnowledgeBase` 按 document_id 命中优先 | PASS | `app.js:5113-5125`：先收集 `[data-document-id]`，`find(dataset.documentId === key)` 优先于 `find(dataset.paperId === key)` |
| paper_id 兼容 | PASS | `:5120-5121` 收集 `[data-paper-id]` 去重后作为 fallback；`renderKbPapers:6415-6416` 两属性分别写入 |
| 未命中提示不覆盖「列表加载失败」 | PASS | `app.js:5172-5176` `reportMiss()` 首行 `if (kbListLoadFailed) return false;`；`kbListLoadFailed` 在 `:6260` 声明、`:6268` 置 false、`:6271` 置 true；测试 `test_frontend_kb_jump_focus.js:281-295` 逐字断言保留 `'列表加载失败：网络中断'` |
| 高亮清除时机 | PASS（附 P2-3） | `:5134` 命中前 `clearKbJumpHighlight()`；`:5157` 进入视图即清；`renderKbPapers:6397` `kbList.replaceChildren()` 重建 DOM 使旧高亮自然消失 |
| `research-tasks.js:1691` 同入口受益 | PASS | `research-tasks.js:1691` 传 `String(upgrade.document_id)`；`literature-maps.js:6941-6942` 调 `window.jumpToKnowledgeBase(documentId)`；新实现优先 `data-document-id` → 自动命中，**未改** `research-tasks.js`（符合 `spec:430`） |

### 必查 2：版本号 —— **PASS**

| 资源 | `index.html` | 断言 / fixture | 判定 |
|---|---|---|---|
| `literature-maps.js?v=41` | `:805` | `test_frontend_literature_map_contract.py:28`、`test_frontend_literature_map_expansion.py:28`、`test_frontend_map_analysis_contract.py:34`、`test_frontend_map_groups_exports.py:18,44`、`test_frontend_map_mobile_contract.py:94,97`、`fixtures/literature_map_component.html:1120` | PASS（7 处全 `41`） |
| `app.js?v=69` | `:807` | `test_frontend_management_contract.py:80` = `v=69` | PASS |
| `styles.css?v=68` | `:8` | `test_frontend_management_contract.py:79` = `v=68` | PASS |
| `literature-maps.css?v=26` | `:9` | 多处断言 = `26`，**本轮未改该文件内容以外的版本** | PASS（`literature-maps.css` 有 +3 行改动但版本未升 → 见 P2-4） |

**「本轮 P1 修复未再升版本是否合理」**：合理。P1 修复（`:7122-7130` 接线、`:2494-2503` 新增函数）与 FE-1 同属 `literature-maps.js` 的**同一未提交批次**，`?v=41` 从未发布，浏览器无 `v=41` 旧缓存，无需再递增；本次 `git log --oneline -5` 也确认工作区改动尚未提交。**但一旦 `v=41` 已随任何环境发布，后续任何 `literature-maps.js` 改动都必须再递增。**

### 必查 3：XSS —— **PASS**

| 检查 | 判定 | 证据 |
|---|---|---|
| 改动段无 `innerHTML` | PASS | `awk` 抽取 `app.js:5100-5200,6255-6280,6505-6525` grep `innerHTML\|outerHTML\|insertAdjacentHTML` → **零命中**；`grep -n "innerHTML" frontend/literature-maps.js` → **零命中**（exit=1） |
| `title` / `aria-label` 用 `setAttribute` | PASS | `literature-maps.js:1825-1826`，值为**常量** `PARTIAL_MAP_CARD_NOTICE` + `mapStatusLabel('ready')`，无用户输入 |
| 文本用 `textContent` | PASS | `app.js:5136` `kbStatus.textContent = ...`；`:5175` 常量文案；`:5149/5166` 只操作状态 |
| 无用户输入拼进选择器 | PASS | `app.js:5127` 模板串只插**常量** `.${KB_JUMP_HIGHLIGHT_CLASS}`，`identifier` 仅用于 `dataset` 等值比较 |
| `app.js` 存量 `innerHTML`（8 处） | 不在本轮范围 | `:11/290/483/1624/3842/3847/6114` 均为既有代码，未在本 diff 内 |

---

## 三、重点风险复审（逐条结论 + 文件:行）

### R-1 `resetMapSelectionState` 的 `keepLocalView` 条件放宽（去 dirty）—— **风险成立，判 P1（见 P1-1）**

`literature-maps.js:2376`：
```js
const keepLocalView = Boolean(options.keepLocalView) && previousMapId === mapId;
```
（上轮为 `... && (positionsDirty || viewDirty)`，见 tech-review `:141`。）

- **用户主动点选同一张地图**：`renderMapList:1849-1851` 调 `selectMap(map.map_id)` **不传 options** → `Boolean(undefined) === false` → `keepLocalView === false` → 照旧清空。**不会错误保留，也不会串图。PASS。**
- **409 重读**：`reloadAfterColorConflict:2142`、`selectMap:2026`、`saveNodeGroup:6655`、`repreviewAfterConflict:4461`、刷新按钮 `:1490` 全部**不传 options** → `keepLocalView === false`。**PASS。**
- **跨图**：`previousMapId === mapId` 硬守卫，`selectMap('m2', {keepLocalView:true})` 仍清空（测试 `test_frontend_map_view_save_on_leave.js:369-371`）。**不串图，PASS。**
- **唯一的语义变化点**：切回同一张地图且**本地仍 dirty** 时（flush 失败 / 请求在途 / 用户在别视图期间列表被其它入口重读），现在**无条件保留本地 positions/view 与 dirty**。这条路径上真实风险见 P1-1 / P1-2。

### R-2 `waitForPendingViewFlush` 是否削弱 stale-request 防护 —— **未削弱，PASS（附 P2-1）**

`literature-maps.js:2494-2503`：
- 只在 `mapId === state.selectedMapId` 时等待（`:2495`），跨图立即返回 → 旧地图响应仍会被后续 `resetMapSelectionState` 的 `state.viewRequest += 1`（`:2420`）判为 stale。**跨图防护未削弱。**
- 反方向「跨图等待」不存在：`if (!mapId || mapId !== state.selectedMapId) return;` 在 `await` 之前，无阻塞。
- **未处理 rejection**：无。`saveView` 的 `try/catch` 两分支都显式 `return`（`:5388` / `:5401` / `:5404`），异常不会逃逸出 `saveView`，因此 `flushPendingViewSave` 返回的 promise 永不 reject；`waitForPendingViewFlush` 仍用 `try/finally`（`:2498-2502`），`flushPendingViewSave:5341-5345` 也**注册了 onRejected handler**，双保险。**无 unhandled rejection。**
- **`state.viewFlushPromise` 悬挂**：无。`flushPendingViewSave:5341-5345`（成功/失败都清）与 `waitForPendingViewFlush:2500-2502` 都在 `=== pending` 时清引用，语义正确（不会清掉更新的 promise）。
- **既有 stale 防护 + flush 的交互**：同图切回时 flush 仍在途，`waitForPendingViewFlush` 先等它完成，再 `await waitForPendingViewFlush(mapId)` **之后** 才 `resetMapSelectionState`（`:2507-2508`）→ `viewRequest += 1` 发生在 flush 落地之后，flush 能被 `stillCurrent`（`:5386-5387`）认领并清 dirty。**这正是 T-P1-1 要求的效果，逻辑正确。**

### R-3 `loadMaps(options)` / `selectMap(mapId, options)` 新增参数对其它调用点的影响 —— **无影响，PASS**

- `selectMap(` 全部 7 个调用点：`:1490`（刷新按钮）、`:1850`（卡片点击）、`:2026`（分组 409）、`:2142`（颜色 409）、`:4461`（预览 409）、`:6655`（节点分组 409）、`:7130`（**唯一传 `{keepLocalView:true}`**）。前 6 处不传 → `options = {}` → 行为与改动前完全一致。
- `loadMaps(` 全部 3 个调用点：`:1491`（无选项）、`:2352`（创建成功后，无选项）、`:7123`（传 `{keepLocalView}`）。前两处 `options = {}` → `:2278` `selectMap(existing.map_id, {})` 等价于旧行为。
- 形参均为**可选默认 `{}`**，无破坏性变更。

### R-4 `PATCH /view` 请求体字段集与 409 策略 —— **确实未变，PASS**

`saveView` body（`literature-maps.js:5366-5372`）：`expected_revision` / `positions` / `viewport` / `layers` / `label_mode` —— 与改动前一致（diff 未触及该段）。409 处理在 `errorAction`（`:244-245`）与 catch 分支（`:5398-5405`）均**未改策略**，仅把 `stillCurrent` 的 `state.active` 放宽为 `(state.active || allowInactive)`。符合 `spec:433`「不改 `PATCH /view` 契约与 409 冲突策略」。

---

## 四、问题清单

### P0：**无**

---

### P1-1（P1）切回同图且本地仍 dirty 时，读路径会用「地图已拿到的服务端旧值」覆盖随后落地的 flush 结果

- **位置**：`frontend/literature-maps.js:2376`（条件放宽）+ `:2455-2459`（`applyMapPayload` keepLocalView 时**完全不**更新 `state.map`）+ `:2599-2601`（本地有位置的节点不覆盖）+ `:5389`（flush 成功后 `state.map = normalizeMap(payload.map)`）
- **场景**（可达）：拖动节点后 **<500ms** 切走 → `setActive(false)` 的 `flushPendingViewSave()`（`:7139`）请求在途；用户在 KB 停留 >500ms；切回 → `setActive(true)` 立即 `selectMap(id, {keepLocalView:true})`（`:7130`）→ `waitForPendingViewFlush` 等 flush 落地 → `resetMapSelectionState` 保留本地 positions 与 **旧 revision** → 拿到旧 `map` 后 `applyMapPayload(payload, true)` **跳过** `applySavedView` → 紧接着 `loadMapGraph(mapId, {keepLocalView:true})`（`:2514`）用**未更新的** `state.map.revision` 继续。
- **后果**：`initialFitPending` 保持 `false`（`resetMapSelectionState:2421`），本地视口沿用（正确）；但 `state.map` 的 `revision` / `status` / `job` 仍是**旧**值 → 下一次 `saveView` 用旧 `expected_revision` → **409**，用户看到「视图保存失败…」且本次整理结果需再操作一次才落地。
- **为什么测试没抓到**：`test_frontend_map_view_keep_local_on_return.js:470-553` 的竞态用例在 `waitForPendingViewFlush` 落地后**只断言本地值保留与 dirty 收口**，未断言「读回的 `state.map.revision` 已被 flush 响应推进」。
- **建议修复（二选一，均小改）**：
  1. `applyMapPayload` 在 `keepLocalView` 时**只不覆盖 view 字段**，仍吸收 `payload.map` 的 `revision` / `status` / `view_settings` 元数据（如 `state.map = { ...normalizeMap(payload.map), view_settings: state.map?.view_settings ?? ... }`）；
  2. 或在 `selectMap` 读完 payload 后，若 `keepLocalView` 且 `payload.map.revision < state.map.revision`，采用 `state.map.revision`（取更新者）。
- **配套测试**：构造「flush 落地 revision=2 → 随后 GET 返回 revision=1」的顺序，断言 `state.map.revision === 2` 且随后 `saveView` 的 `expected_revision === 2`。

---

### P1-2（P1）`loadMapGraph(keepLocalView)` 的晚到响应未校验地图归属，跨图切换后可把**上一张地图**的节点位置写进**新地图**的 `state.positions`

- **位置**：`frontend/literature-maps.js:2599-2606`
```js
if (keepLocalView && state.positions[node.node_id]) {
  // 本地已有该节点位置：保留本地值（不排队重排、不覆盖）。
} else if (...) { state.positions[node.node_id] = {...}; } else { ... state.positions[node.node_id] = initialPosition(...); }
```
- **机制**：`state.positions` 的清空只发生在 `resetMapSelectionState:2396-2401`，且被 `if (!options.keepLocalView)` 包住。旧地图 A 的一次 **stale** `loadMapGraph('A', {keepLocalView:true})` 即便在 `:2588` 被 `mapId !== state.selectedMapId` 拦下 `return`，也**不会写入**；但**新地图 B** 的 `loadMapGraph('B', ...)` 是「当前请求」，其 `else` 分支会遍历 B 的节点 —— 若 `state.positions` 里因 `keepLocalView` 保留了 A 的节点位置且**节点 ID 复用**（同一 document 在两图共存，ID 相同；`initialPosition(index, n)` 见 `:2605`），则 B 会**直接沿用 A 的坐标**，且不排队重排 → B 的布局被 A 污染。
- **可达性**：需要 `resetMapSelectionState` 以 `keepLocalView:true` 进入 B —— 而 `keepLocalView` 要求 `previousMapId === mapId`（`:2376`），因此**必须** A === B。当前唯一传参点 `:7130` 传的是 `state.selectedMapId`，且 `:7123` 的 `loadMaps({keepLocalView})` 也只传 `existing.map_id`。**因此该路径在当前调用点组合下不可达**，属「防范性缺口」而非已发生缺陷 —— 故判 **P1 而非 P0**：它把「跨图不串位」这一硬约束从「结构保证」降级为「调用点自律 + 注释」。
- **建议修复**：`loadMapGraph` 内对 `state.positions` 做地图归属校验（如 `state.positionsMapId` 缓存键，或 `keepLocalView` 仅在 `mapId === state.positionsMapId` 时生效），使「保留本地位置」具备结构性边界，而非依赖调用方永不为跨图传参。
- **配套测试**：直接对 `loadMapGraph('m2', {keepLocalView:true})` 断言不沿用 m1 的节点坐标（当前无此用例；`test_frontend_map_view_save_on_leave.js:369-371` 只测了 `resetMapSelectionState` 的跨图清空）。

---

### P2 清单

| 编号 | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| P2-1 | P2 | `literature-maps.js:2507` | `selectMap` 在 `await waitForPendingViewFlush` 期间**无 loading 反馈**（`setStatus('正在读取已保存地图…')` 在 `:2509`，即等待**之后**）；flush 请求慢时用户点图后界面无变化 | 把 `setStatus('正在读取已保存地图…')` 提到 `await` 之前 |
| P2-2 | P2 | `literature-maps.js:2376` vs `:2396` | 同函数内两处判定口径不一致：局部变量 `keepLocalView`（含 `previousMapId === mapId`）已算好，`:2396` 却重新判 `if (!options.keepLocalView)` —— 若将来有人传 `{keepLocalView:true}` 且换图，会「保留 positions 却其它状态全清」的混合态；靠 `:2376` 的守卫才安全 | `:2396` 改用局部变量 `if (!keepLocalView)`，让 `return {requestId, keepLocalView}`（`:2451`）与实际行为**同源** |
| P2-3 | P2 | `app.js:5134/5157` | 高亮只在「下一次跳转」与「进入 kb 视图」时清除；用户手动点其它列表项或切走 kb 视图后，`kb-item-jump-target` 会残留到下次进入（上轮 T-8 的完整收口未做） | 在 `showView` 离开 kb 分支清一次；或明确在验收材料写「高亮为持久提示，直至下次跳转」 |
| P2-4 | P2 | `frontend/index.html:9` + `frontend/literature-maps.css:37-39` | `literature-maps.css` 有 +3 行内容改动，但 `?v=26` **未递增**（与 `styles.css:67→68`、`app.js:68→69`、`literature-maps.js:40→41` 不一致） | 若 `v=26` 已在任何环境发布过，须升 `v=27` 并同步 `test_frontend_map_*` 中 6 处 `literature-maps.css?v=26` 断言 + fixture |
| P2-5 | P2 | `literature-maps.js:2536-2543` 注释 vs `:2544-2557` 实现 | 注释仍写「3. revision 已知：revision === 0 且根本没有任何视口字段 → 新图，fit 一次」的**四级判定**，但实现里**没有任何 revision 分支**，实际是「显式 → viewSavedOnce → 无 viewport → `(0,0,1)`」三级 | 注释与实现对齐（保留 revision 判定或改注释），避免维护者误读 |

---

## 五、四项必守 · 逐条 PASS/FAIL

| # | 必守项 | 判定 | 核对依据（命令 + 命中行） |
|---|---|---|---|
| 1 | **DOM 契约**（JS class ↔ CSS 双向存在） | **PASS** | JS→CSS：`grep -n "kb-item-jump-target" frontend/styles.css frontend/app.js` → `styles.css:804,809` + `app.js:5106`；`grep -n "data-availability" frontend/literature-maps.css frontend/literature-maps.js` → `literature-maps.css:39` + `literature-maps.js:1824`。CSS→JS：反向 grep 无孤儿钩子（`.literature-map-badge` 基础样式 `:34` 由 `renderStatusBadge:835` 产出） |
| 2 | **版本号 `?v=N`** | **PASS**（附 P2-4） | `grep -n "?v=" frontend/index.html` → `:8 styles.css?v=68`、`:9 literature-maps.css?v=26`、`:805 literature-maps.js?v=41`、`:807 app.js?v=69`；`grep -rn "literature-maps\.js?v=" tests/` → 7 处全 `41`；`test_frontend_management_contract.py:79,80` → `v=68` / `v=69`。**唯 `literature-maps.css?v=26` 有内容改动未升版（P2-4）** |
| 3 | **XSS**（禁 `innerHTML` 拼用户输入） | **PASS** | `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|document.write" frontend/literature-maps.js` → **exit=1 零命中**；`awk` 抽 `app.js` 三个改动段 grep 同集合 → **零命中**；`title/aria-label` 走 `setAttribute`（`literature-maps.js:1825-1826`，值全常量）；提示文案走 `textContent`（`app.js:5136,5175`） |
| 4 | **CSS 作用域**（不得裸写全局标签选择器） | **PASS** | `styles.css:804,809` 均以 `#kb-view .kb-item` 前缀限定；`literature-maps.css:39` 以 `#literature-maps-view .literature-map-badge[data-availability="usable"]` 限定；本轮新增 CSS 无任何裸标签选择器（diff 仅 +9 / +3 行，全部带容器前缀） |

---

## 六、测试与实跑

| 测试 | 运行结果 |
|---|---|
| `node --check frontend/app.js` | PASS |
| `node --check frontend/literature-maps.js` | PASS |
| `tests/frontend/test_frontend_kb_jump_focus.js` | `ok - kb jump focus (document_id 命中 / paper_id 兼容 / 未命中提示 / pending 消费)` |
| `tests/frontend/test_frontend_map_card_count_and_availability_badge.js` | `ok - map card count (node_count) and availability badge (node:vm, real renderMapList)` |
| `tests/frontend/test_frontend_map_view_keep_local_on_return.js` | `ok - map view keep local on return (接线级：keepLocalView / 不覆盖 / 竞态 flush / 跨地图清空)` |
| `tests/frontend/test_frontend_map_view_save_on_leave.js` | `ok - map view save on leave (flush dirty / 不覆盖本地 / 显式 initialFit 标记)` |

测试质量：4 个 `*.js` 均从真实 `frontend/app.js` / `frontend/literature-maps.js` 用正则**原样抽取**函数进 `node:vm`，`slice()` 内 `assert.ok(match)` 防静默失效；断言为逐字期望字符串，无恒真断言，无 `if (!x) return` 式守卫。**覆盖缺口**：P1-1（flush 后 revision 未推进）、P1-2（跨图 `loadMapGraph` 串位）无对应用例。

## 七、Summary（ECC 格式）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 2 | warn |
| MEDIUM | 5 | info |
| LOW | 0 | note |

Verdict: **WARNING → 本报告结论「通过（附前置条件）」** —— 无 CRITICAL；2 个 HIGH 均有精确行号与最小改法，建议作为本批 P1 收口后再签字「无保留通过」。

---

## 八、转「无保留通过」的条件

1. **P1-1 闭合**：`applyMapPayload` 在 `keepLocalView` 时仍吸收 `payload.map.revision`（或 `selectMap` 取更大 revision），并补「flush 后 revision 已推进」的断言。
2. **P1-2 闭合**：`loadMapGraph` 对 `state.positions` 加地图归属边界（`positionsMapId` 或等价），并补「`loadMapGraph('m2', {keepLocalView:true})` 不沿用 m1 坐标」的断言。
3. **P2-4 确认**：明确 `literature-maps.css?v=26` 是否曾在任何环境发布；若是，升 `v=27` 并同步 6 处断言 + fixture。
4. **P2-2 建议同批**：`:2396` 改用局部 `keepLocalView`，消除同函数双口径。

---

## 第二轮最终复审

| 项 | 值 |
|---|---|
| **复审范围** | 上轮 2 个 P1 前置条件 + 2 个回归阻塞的修复复核（只读，不改代码/测试/spec/台账） |
| **复核依据** | `git diff -- frontend/`、`git diff -- tests/frontend/`、Read 真实行；6 个新增 node 测试实跑；变异测试（临时改实现→跑测试→还原并 `diff -q` 校验） |
| **日志** | `.codebuddy/agent-logs/spec-043/task-00/frontend-reviewer/20261106-004407.md` |

### 一、修复项逐条结论

| # | 修复项 | 判定 | 证据（文件:行） |
|---|---|---|---|
| 1 | **P1-1** `loadMapGraph` 补 revision / `view_initialized` 收口 | **PASS** | `frontend/literature-maps.js:2612-2622`：`graphMap` 与 `state.map` 同图时走 `merged`，`:2617` 仅在 `Number.isInteger(Number(graphMap.revision))` 为真时写入，`:2618` 否则回落 `state.map.revision`（**不会写成 undefined**）；`:2619-2620` 仅在 `normalizeMapViewInitialized(graphMap) !== undefined` 时吸收 `view_initialized`。测试 `tests/frontend/test_frontend_map_initial_fit_and_positions_guard.js:359-394`（4 与 4b）钉住「吸收 42」与「缺字段保留 7」 |
| 2 | **P1-2** `state.positionsMapId` 跨图守卫 + `resetMapSelectionState` 归属维护 | **PASS（附 P2-1）** | 守卫 `literature-maps.js:2603-2607`（归属不符即清空 positions 并清 `positionsDirty`）；归属登记 `:2624`；维护 `:2399-2409`（未保留→置 `null`；同图保留→标 `mapId`）。测试 `..._positions_guard.js:276-357`（跨图丢弃 / 归属未知按跨图 / 同图保留 / 归属维护）4 例全绿 |
| 3 | **回归阻塞 1** `resolveInitialFitPending` 显式证据 → 绝不 fit；无证据 → 旧启发式 | **PASS** | `literature-maps.js:2553-2567`；`MIN_MAP_SCALE=0.35` 见 `:12`，`INITIAL_FIT_SCALE_EPSILON=0.01` 见 `:15` |
| 4 | **回归阻塞 2** `literature-maps.css?v=26 → 27` + 9 处断言/fixture | **PASS** | `frontend/index.html:9` → `?v=27`；`grep -rn "literature-maps\.css?v=26" frontend/ tests/` → **0 命中**；5 个 py 测试共 8 处断言 + `tests/frontend/fixtures/literature_map_component.html:8` 全为 `v=27` |
| 5 | 新增 2 个 node vm 测试文件 | **PASS（附 P2-2）** | 新增 `test_frontend_map_initial_fit_and_positions_guard.js`、`test_frontend_map_view_revision_on_reentry.js`；6 个新测试全部 `EXIT=0` |

### 二、必查 1：`resolveInitialFitPending` 四场景矩阵（逐条实跑）

| 场景 | 期望 | 分支路径 | 实跑结果 |
|---|---|---|---|
| a) `view_initialized===true` 且 scale=0.35 | 不 fit | `:2557` `explicit===true → return false`（**最前**，先于一切启发式） | PASS（测试 `:249-260`） |
| a') `view_initialized===true` 且 (0,0,1) | 不 fit | 同上 `:2557` | PASS（逻辑同源；`:2566` 不可达） |
| b) 无标记 + scale=0.35 | fit | `:2565` `savedScale <= 0.36 → return true` | PASS（测试 `:224-233`，用 fixture 真实值 `{218.19,185.00,0.35}`） |
| b') 无标记 + scale=0.36 边界 | fit | `:2565` 边界含等号 | PASS（测试 `:234-240`） |
| c) 无标记 (0,0,1) | fit | `:2565` 先命中（0.35 ≤ 0.36） | PASS（`:2566` 仅作兜底，不可达但无害） |
| d) 普通已存视图（x≠0 / scale=1.2 等） | 不 fit | 全部前置为假 → `:2566` 返回 false | PASS（测试 `:241-248`） |
| e) `view_initialized===false` | fit | `:2561`（在 `viewSavedOnce` **之后**） | PASS（测试 `:267-274`） |
| f) `viewSavedOnce===true` + 0.35 | 不 fit | `:2560`（在 `explicit===false` 之前） | PASS（测试 `:261-266`） |

**分支顺序评估**：`explicit===true → viewSavedOnce → explicit===false → 无 viewport → scale 未知 → 极小缩放 → (0,0,1)`。`state.viewSavedOnce`（`:2560`）优先于 `explicit===false`（`:2561`）是**正确方向**——后端仅在 `store.update_view` 成功时写 `view["view_initialized"]=True`（`backend/app/literature_maps/infrastructure/store.py:673`），`service._export_view_settings` 只在值为 `True` 时输出（`backend/app/literature_maps/application/service.py:2586-2587`），故 `explicit===false` 只可能出现在「本会话确实没保存过」的情形，二者不会真冲突。**无分支漏洞。**

### 三、必查 2：`loadMapGraph` 守卫与合并

| 子项 | 判定 | 证据 |
|---|---|---|
| 跨图串位是否修复 | PASS | `:2603-2607` 归属不符即清空，`:2624` 更新归属；测试 `:276-298` 断言 `shared-node` 从 `(-999,-999)` 变为服务端 `(11,22)` |
| 归属未知是否默认放行 | PASS（按跨图，偏保守） | `:2603` 用 `!==`，`null !== 'm1'` → 清空；测试 `:299-319` |
| 同图 `keepLocalView` 是否误清 | PASS | `:2632` `keepLocalView && state.positions[node.node_id]` 保留本地；测试 `:320-340` |
| revision 是否可能被覆盖成 undefined | **PASS（不会）** | `:2617-2618` 互斥赋值，`else` 分支回落旧值；测试 4b `:379-394` |
| `normalizeMap` 合并是否丢键 | PASS | `:399-411` `{...map, view_settings, ...(nodeCount===undefined ? {} : {node_count})}`；`view_initialized` 仅在 `!== undefined` 时注入，未污染原对象 |
| `state.job` 是否回退 | **PASS** | `:2623` `payload.latest_job \|\| state.job`。经查 `service.graph()` 恒返回 `latest_job` 键（`backend/.../service.py:816`），且 `selectMap` 先 `applyMapPayload` 置 `state.job = payload.latest_job \|\| null`（`:2465`），故 `\|\|` 不会保留上一张图的 job |

### 四、必查 3：四项必守（逐条 PASS/FAIL + 核对命令）

| # | 必守 | 判定 | 核对依据 |
|---|---|---|---|
| 1 | **DOM 契约** | **PASS** | JS→CSS：`kb-item-jump-target`（`app.js:5106` 常量，`app.js:5128` 落到 DOM）↔ `styles.css:804,809` ✅；`data-availability="usable"`（`literature-maps.js:1829`）↔ `literature-maps.css:37-39` ✅。CSS→JS：`git diff -U0 -- frontend/*.css \| grep '^+'` 命中的 class 仅上述两项，均有 JS 赋值 ✅ |
| 2 | **版本号 `?v=N`** | **PASS** | `grep -n "?v=" frontend/index.html` → `:8 styles.css?v=68`、`:9 literature-maps.css?v=27`、`:805 literature-maps.js?v=41`、`:807 app.js?v=69`。四者均较上轮递增（67→68 / 26→**27** / 40→41 / 68→69），无遗漏；`grep -rn "literature-maps\.css?v=26" frontend/ tests/` → 0 命中 |
| 3 | **XSS** | **PASS** | `git diff -U0 -- frontend/ \| grep -E '^\+.*(innerHTML\|outerHTML\|insertAdjacentHTML\|document.write\|eval\(\|new Function)'` → **0 命中**；新增用户可见文本全部走 `textContent`（`app.js:5133`、`literature-maps.js:1817,1825-1826` `setAttribute('title'/'aria-label', ...)` 仅取常量 `PARTIAL_MAP_CARD_NOTICE` 与 `mapStatusLabel('ready')`，无外部输入拼接） |
| 4 | **CSS 作用域** | **PASS** | 新增 3 条选择器全部带项目作用域前缀：`#literature-maps-view .literature-map-badge[data-availability="usable"]`（`literature-maps.css:37-39`）、`#kb-view .kb-item.kb-item-jump-target`（`styles.css:804-808`）、`:focus`（`styles.css:809`）；无裸标签选择器 |

### 五、必查 5：新增测试有效性（含变异反证）

| 检查 | 结论 |
|---|---|
| 是否从真实实现取函数 | PASS —— `slice()` 用正则从 `frontend/literature-maps.js` 原样抽取（`..._positions_guard.js:31-46`），并 `assert.ok(match)` 防静默失效（`:33`） |
| 是否恒真断言 | 未发现（同一文件）—— 断言均为硬编码期望值（如 `revision === 42`、`{x:11,y:22}`）。`..._keep_local_on_return.js:513` 存在 1 处 `assert.equal(h.requests ? 0 : 0, 0);` 恒真、无覆盖价值，建议删除（P2-2） |
| 门禁是否真实生效 | PASS —— 变异测试：删掉 `resetMapSelectionState` 的 `state.viewDirty = false`（`:2404`）后 `test_frontend_map_view_keep_local_on_return.js` **FAIL**（`AssertionError: 跨地图必须清空 viewDirty`，`EXIT=1`）；还原后 `diff -q` 校验实现文件与备份一致 |

### 六、本轮问题清单

| # | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| P2-1 | P2 | `literature-maps.js:2603-2607` | 跨图守卫清空了 `positions` / `layoutPendingIds` / `positionsDirty`，但**未清 `viewDirty`**。若切图瞬间存在未落地改动（`:3440` 节点新增后、`:4809` layout 帧预算耗尽均会置 `positionsDirty=true`），守卫清空后 `:2641-2647` 首开重排又置 `positionsDirty=true` → `:2654 scheduleViewSave()` → `saveView` 把**新地图**的 position 矩阵连同**旧地图**的 `state.view` 一并写入（`:5420` 起的 PATCH 载荷）。属 P1-2 同类「跨图串位」的窄口径残留，触发窗口为「切图前 500ms 内有未落地位置改动」，代价为服务端视口被旧图值覆盖（可再次拖回，非数据损坏） | 在 `:2606` 后补 `state.viewDirty = false;`，并把既有断言 `test_frontend_map_view_keep_local_on_return.js:568` 的覆盖面移到 `loadMapGraph` 路径（当前该断言由 `resetMapSelectionState:2404` 满足，故守卫缺 `viewDirty` 时测试仍绿） |
| P2-2 | P2 | `tests/frontend/test_frontend_map_view_keep_local_on_return.js:513` | `assert.equal(h.requests ? 0 : 0, 0);` 恒真，无任何覆盖价值（恒为 `0 === 0`） | 删除该行，或替换为「flush 在途时 `viewPatch` 尚未 resolve」的真实状态断言 |
| P2-3 | P2 | `literature-maps.js:110, 2560` | `state.viewSavedOnce` 是**会话级**标记，**不按地图重置**（`resetMapSelectionState` 未复位）。会话内保存过 A 图后，再打开一张「无 `view_initialized` 标记（旧数据）+ 极小缩放 0.35」的历史图 B，`:2560` 会直接返回 `false`（不 fit），且 `:2429` 已把 `initialFitPending` 置 false，`applySavedView` 又不再被调用 → 停在 0.35 不可读视图，与提交 `61096ed6 fix(maps): fit unreadable opening views` 的契约冲突（正是本轮回归阻塞 1 要修的那类症状） | 改为按地图记录（如 `state.viewSavedMapIds = new Set()`，`:2560` 判定 `has(state.selectedMapId)`，`:5425` 写入当前 mapId），或在 `resetMapSelectionState` 切换到**不同** mapId 时复位 |
| P2-4 | P2 | `literature-maps.js:2613-2614` | `if (!(graphMap && state.map && graphMap.map_id === state.map.map_id)) state.map = graphMap \|\| state.map;` —— 当 graph 响应的 `map` 缺失（`graphMap === null`）且 `state.map` 存在时走右支保留旧值；但若 `state.map` 也为 `null`（异常路径），`state.map` 保持 `null`，后续 `saveView` 的 `:5410` `state.map?.map_id` 守卫会静默 `return false`。当前后端 `service.graph()` 恒返回 `map`（`service.py:816`），实际不可达 | 仅需注释说明该分支为防御性代码，无需改动 |

**上轮所述 P1 是否全部闭合**：P1-1 ✅ 闭合（`:2612-2622` + 测试 4/4b）；P1-2 ✅ 闭合（`:2603-2607` + 测试 3/3b-0/3b/3c），仅余 P2-1 窄口径残留。**本轮无 P0、无 P1。**

### 七、Summary（ECC 格式）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 4 | info |
| LOW | 0 | note |

Verdict: **APPROVE —— 通过（无保留）**。0 个 CRITICAL、0 个 HIGH；上轮 2 个 P1 与 2 个回归阻塞全部闭合且有可反证的测试门禁。4 个 P2 均为窄口径 / 清理项，不阻塞合并。

### 八、执行记录（本轮亲自跑）

```text
node --check frontend/app.js                     → OK
node --check frontend/literature-maps.js         → OK
node tests/frontend/test_frontend_map_initial_fit_and_positions_guard.js → ok (EXIT=0)
node tests/frontend/test_frontend_map_view_revision_on_reentry.js        → ok (EXIT=0)
node tests/frontend/test_frontend_kb_jump_focus.js                       → ok (EXIT=0)
node tests/frontend/test_frontend_map_card_count_and_availability_badge.js → ok (EXIT=0)
node tests/frontend/test_frontend_map_view_keep_local_on_return.js       → ok (EXIT=0)
node tests/frontend/test_frontend_map_view_save_on_leave.js              → ok (EXIT=0)
变异反证：删除 literature-maps.js:2404 `state.viewDirty=false` → 上述 keep_local 测试 FAIL(EXIT=1) → 已还原并 diff -q 校验
环境说明：pytest tests/frontend 全量因缺 langchain_ollama / playwright 在 collection 阶段报错（既有环境缺失，与本次改动无关），故版本号断言采用静态精确比对（见第四节 #2）
```

---

## 第三轮最终复审（E2E 发现修复）

> 复审对象：主会话在真实 Chromium E2E 抓到的两个单测未覆盖的时序缺陷（缺陷 C：离开视图 flush 早退；缺陷 A2：KB 跳转定位落在被重建的旧 DOM 上）及其由 `frontend-dev` 提交的修复。
> 本轮为**只读复审**：未修改任何业务代码、测试、spec、台账。评审范围严格限定 `frontend/**`（`backend/**` 改动按项目约束交由 `backend-reviewer`，本轮仅在论证 409 契约时引用其行号）。
> 基线：`git diff`（工作区未提交）+ `git log --oneline -5`（HEAD = `09f4b6a3`）。

### 一、缺陷 C 修复：`saveView` 的 `allowInactive` 放行

改动核心（`frontend/literature-maps.js`）：

| 行号 | 代码事实 |
|---|---|
| `:5366-5380` | `flushPendingViewSave()` 先 `clearTimeout(state.saveTimer)`，仅当 `state.map?.map_id` 且存在 dirty 时才 `saveView({ ...options, allowInactive: true })`，并把 promise 存进 `state.viewFlushPromise`，用 `then` 双回调（`:5374-5378`）清引用 |
| `:5383-5384` | `const allowInactive = Boolean(options.allowInactive);` → `if (!state.map?.map_id \|\| (!allowInactive && !state.active) \|\| (!state.positionsDirty && !state.viewDirty)) return false;` |
| `:5393` | `if (!viewport.valid && !allowInactive) return false;`（本轮放行点） |
| `:5425-5427` | 响应落地守卫 `stillCurrent = mapId === state.selectedMapId && state.map?.map_id === mapId && (state.active \|\| allowInactive)` |
| `:5438-5440` | 失败分支同形守卫 `stillCurrentOnError` |
| `:7175-7178` | `setActive(false)` 分支首个动作即 `flushPendingViewSave()`（唯一调用点） |

#### ① 放行是否 resurrect 历史「零尺寸写入 bogus 视口」——**否（PASS）**

- PATCH body 逐字核对（`:5405-5411`）：`{ expected_revision, positions, viewport: state.view, layers, label_mode }`。`mapViewportWorldSize()` 返回的 `x / y / width / height / cssScale` **一次都没有进入 payload**；`viewport.valid` 仅作为 `:5393` 的布尔守卫参与，不参与序列化。**结论：测量数值不进请求体。**
- 历史缺陷的真实入口是「0×0 时用 `viewport.width/height` 反算 `state.view`」。逐点核对 `state.view` 的全部写点：
  - `:1564` 重置视图 → 常量 `{x:0,y:0,scale:1}`，不读测量值；
  - `:2575-2579` `applySavedView` → 服务端值 + `Number.isFinite` 兜底；
  - `:4872` 取消间距预览 → 快照回滚；
  - `:5313-5316` `fitView` → **前置 `:5306-5307 if (!viewport.valid) return false;`**，0×0 时根本走不到 `:5314-5316`；
  - `:5128-5130` pinch / `:5247-5249` `changeScale` → 由 `svgPointFromClient` / `clientPoint` 驱动，不读 SVG rect；
  - `:5348-5349` `locateSelectedNode` → 常量 `MAP_WIDTH/2 / MAP_HEIGHT/2`。
- `mapViewportWorldSize` 在 rect 0 时（`:5262-5263`）返回的是 viewBox 尺寸且 `valid:false`，**不会被误当成 `state.view`**。
- 因 `scheduleViewSave`（`:5355-5361`）保留了 `!state.active` 与 `!viewport.valid` 双重早退，**唯一的绕过口就是 `:5372` 的 flush**；而 flush 只搬运「上一次合法交互已经写好的 `state.view`」。**不存在「0×0 → bogus 视口落库」的新通路。**

#### ② 普通 active 路径的 valid 守卫——**完好（PASS）**

- `:5393` 的 `!viewport.valid` 在 `allowInactive === false` 时**完全等价于改动前**。
- `:5384` 的 `state.active` 守卫对非 flush 调用同样等价于改动前（原式 `!state.active` 被提为 `(!allowInactive && !state.active)`）。
- 唯一的另一处 `saveView` 调用 `:4891`（`confirmSpacingPreview`，`{ allowLayoutPreview: true }`）**不传 `allowInactive`**，仍受 `:5393` 与 `:5384` 双重约束。
- `:5385` 的 `layoutPreviewActive` 守卫未被触碰，间距预览期间依旧不写库。

#### ③ `flushPendingViewSave` 是否唯一 `allowInactive:true` 来源——**是（PASS）**

```text
$ grep -n "flushPendingViewSave|allowInactive" frontend/
literature-maps.js:5366  function flushPendingViewSave(options = {})      ← 定义
literature-maps.js:5372  const pending = saveView({ ...options, allowInactive: true });  ← 唯一注入点
literature-maps.js:5383-5393 / 5426 / 5439                                   ← 消费点
literature-maps.js:7178  flushPendingViewSave();                             ← 唯一调用点
（app.js / research-tasks.js / index.html：0 命中）

$ grep -n "saveView\(" frontend/
literature-maps.js:4891  await saveView({ allowLayoutPreview: true });   ← 不传 allowInactive
literature-maps.js:5372  （flush，唯一 allowInactive）
literature-maps.js:5382  async function saveView(options = {})           ← 定义
```
`setActive` 的 `else` 分支是唯一入口，故「后台反复写库」的担忧不成立（`scheduleViewSave` 已由 `:5356` 的 `!state.active` 拦住）。

#### ④ 是否引入 409 / 重复 PATCH / unhandled rejection——**均未新增（PASS，附 1 个 P2 观察）**

- **重复 PATCH**：`flushPendingViewSave` 入口先 `clearTimeout` + `state.saveTimer = null`（`:5367-5368`），再 `:5370` 做 dirty 判空，同一轮离开视图只发一次；`setActive(false)` 重复触发时 `positionsDirty/viewDirty` 已被上一次成功响应清掉（`:5429-5430`），不会二次发。**无重复 PATCH**。
- **unhandled rejection**：`saveView` 是 `async` 且 `try/catch` 全覆盖（`:5402-5444`），失败分支 `return false` 不抛；`flushPendingViewSave` 的返回值在 `:7178` 未被接（未 await、未 catch），但已由 `:5374-5378` 的 `then(onFulfilled, onRejected)` 双回调吞掉；`waitForPendingViewFlush`（`:2502-2511`）另加 `try/finally` 兜底。**不会产生 unhandled rejection。**
- **409**：路径为 `store.py:655-656 raise ValueError("revision conflict")` → `routes_literature_maps.py:290-293` 映射 `409 / MAP_CONFLICT` → 前端 `:5437-5443` catch。改动**没有新增**任何并发写，故 409 概率不因本轮上升；`waitForPendingViewFlush`（`:2502-2511`，由 `:2515` 在 `selectMap` 入口调用）反而是**降低** 409 的设计（同图切回时先等 flush 收口 revision，再重置状态）。
- **P2-1（不阻塞）**：catch 分支 `:5441 state.positionsDirty = true;` 发生在 `state.active === false` 期间，而 `scheduleViewSave` 的 `:5356` 会拒绝重排 → 该 dirty 会**残留到下次进入**。评估：`applyMapPayload`（`:2460`）/ `selectMap`（`:2521`）重新读取服务端 `map` 会带回最新 `revision`，用户下一次任意交互触发的 `scheduleViewSave` 会**用新 revision 重试同一份数据并自动自愈**。可观测后果仅限「离开瞬间 `#literature-map-status` 留着 error 文案 + dirty 多留一轮」，无数据损坏、无风暴。**P2，建议后续在 `setActive(true)` 时 `if (state.positionsDirty) scheduleViewSave();` 显式补偿。**

### 二、缺陷 A2 修复：KB 跳转定位统一落在重渲染后的新 DOM

改动核心（`frontend/app.js`）：

| 行号 | 代码事实 |
|---|---|
| `:5106-5108` | `KB_JUMP_HIGHLIGHT_CLASS = 'kb-item-jump-target'` 等三个常量 |
| `:5113-5124` | `selectKbJumpTarget` 先 `[data-document-id]` 再 `[data-paper-id]` |
| `:5126-5130` | `clearKbJumpHighlight` 按 class 清扫 |
| `:5136-5144` | `applyKbJumpFocus`：`:5137 if (!item \|\| item.isConnected === false) return false;` → `:5139` 加 class → `:5140` scrollIntoView → `:5141` focus → `:5142` 写「已定位」 |
| `:5153-5159` | `consumePendingKbJump` **不清空** pending，命中即 `applyKbJumpFocus` |
| `:5161-5189` | `jumpToKnowledgeBase` 删除旧 DOM 立即 `focusNow` 分支；改为 `:5183 return loadKbPapers().then(...)` |
| `:5367-5376` | `showView`：`nextView==='kb'` → `renderKbSkeleton + loadKbPapers + loadKbHealth`；否则 `:5371-5375` 清 pending + 清高亮 |
| `:6271-6285` | `kbListLoadFailed` 声明 / 成功置 false / 失败置 true |
| `:6528` | `renderKbPapers` 末尾 `consumePendingKbJump()` |

#### ① 两次渲染后是否确实落在最后一次的新 DOM——**是（PASS）**

- `renderKbPapers` `:6408 kbList.replaceChildren()` **每次全量重建**，旧节点必然 `isConnected === false`。
- 两条渲染链：`showView('kb')` 内 `:5369 loadKbPapers()`（A，fire-and-forget）与 `jumpToKnowledgeBase` 内 `:5183 loadKbPapers()`（B，await）。
- 关键：定位动作挂在 **`:6528`，即每次渲染的尾部**，而不是某一次 promise 的结算点。因此无论 A、B 谁最后落地，**最后落地的那一次渲染都会在新 DOM 上重新执行定位**；旧的「只对跳转前 DOM 定位一次」已删除（diff 中 `- const item = [...document.querySelectorAll('[data-paper-id]')]...`）。
- `applyKbJumpFocus` 的 `:5137 isConnected` 拒绝是第二道保险：即便将来有人误对旧节点调用，也会返回 `false` 而**不写「已定位」文案**。

#### ② pending 保留是否导致 KB 轮询无限重复滚动——**不会无限，属可接受 P2**

- `scheduleKbPoll`（`:6208-6213`，2.5s `setInterval`）只在 `renderKbPapers` 判定 `hasRunning` 时启动（`:6524`），`hasRunning` 仅由 `status === 'processing' | 'indexing'` 或 chunker `indexing` 置真（`:6416`、`:6450`）；一旦全部完成 `:6525 stopKbPoll()` 停表。
- `loadKbPapers` 的全部调用点：`:5369`（进视图）、`:5183`（跳转）、`:6211`（轮询）、`:6284`（计数重试回调）、`:6377`、`:6498`（删除后）、`:6605`（上传后）。稳定态（无索引中）下**没有任何周期调用** → 不会重复滚动。
- 唯一残留窗口：跳转后该列表仍有 `indexing`，则 2.5s 轮询会**每次重渲染后再滚动一次**。此时用户就在 KB 视图内、滚动目标未变（同一 `document_id`），体验上是「保持可见」而非「被抢滚动」。**判定 P2，不阻塞。**

#### ③ C-4「列表加载失败文案不被覆盖」是否仍成立——**成立（PASS）**

- `reportMiss`（`:5178-5182`）首行 `if (kbListLoadFailed) return false;`，在写 `KB_JUMP_NOT_FOUND_TEXT` 之前短路。
- 交叉场景逐个推演：
  - A 失败 / B 失败 → `kbListLoadFailed = true`（`:6282`），`:6283` 写「列表加载失败：…」；`reportMiss` 短路 → **失败文案保留** ✅
  - A 成功 / B 失败 → 最终 `kbListLoadFailed = true`，仍报失败（列表确实没读到最新数据，方向保守正确）✅
  - A 失败 / B 成功 → `kbListLoadFailed = false`（`:6279`），`:6532/:5186` 走 `selectKbJumpTarget(key)`：命中 → 保持「已定位」；未命中 → `reportMiss` 报「未找到该文档」（列表数据是成功的，此判断正确）✅

#### ④ `clearKbJumpHighlight` / 离开 KB 清 pending 是否与 C-3 冲突——**不冲突（PASS）**

- `:5371-5375`：`nextView !== 'kb'` 且存在 pending 时，清 pending + 清所有高亮 class。语义与 C-3「离开 KB 不得残留跳转目标/高亮」一致。
- `:5166`：每次进入 KB 即清上一次高亮，保证「同一时刻只有一处目标」。
- 顺序安全：`:5153` `consumePendingKbJump` 若在 `nextView !== 'kb'` 后再被意外调用会命中 `if (!pending) return false`，不会复活旧目标。

#### ⑤ 状态文案是否还有「写了已定位但没定位」的路径——**无（PASS）**

```text
$ grep -rn "已定位到知识库" frontend/
frontend/app.js:5142:  if (kbStatus) kbStatus.textContent = `已定位到知识库中的该文档（${String(identifier)}）。`;
```
唯一写点 `:5142`，位于 `applyKbJumpFocus` 内、在 `:5137` `isConnected` 拒绝之后、与 `:5139` 加 class / `:5140` scroll / `:5141` focus **同一成功分支**，文案与动作原子绑定。`jumpToKnowledgeBase` 自身的 `:5184-5187` 只写「未找到」或保持静默，不会再写「已定位」。

#### ⑥ `research-tasks.js:1691` 同入口是否仍受益——**是（PASS）**

- `research-tasks.js:1691`：`if (typeof root.jumpToKnowledgeBase === 'function') root.jumpToKnowledgeBase(String(upgrade.document_id));`
- `root = globalThis`（`research-tasks.js:9-10` 的 UMD 包装），而 `frontend/app.js` 在 `index.html:807` 以**经典脚本**引入（无 `type="module"`，`grep -n 'type="module"' frontend/index.html` → 0 命中），顶层 `function jumpToKnowledgeBase` 声明直接挂到 `globalThis`。**同一入口、同一新逻辑**，直接受益于 `:6528` 的渲染后定位。
- 备选链路 `literature-maps.js:6980-6981`（`typeof window.jumpToKnowledgeBase === 'function'` 为真时走同一入口）同样受益；其为 false 时 `:6985` 回落到 `[data-view="kb"]` 点击，不回归。

### 三、四项必守（本轮逐条 grep 核对）

| # | 必守项 | 结论 | 核对依据（命令 + 命中行） |
|---|---|---|---|
| 1 | **DOM 契约**（JS class ↔ CSS 双向） | **PASS** | `grep -rn "kb-item-jump-target" frontend/` → `styles.css:804`、`styles.css:809`、`app.js:5106`（双向命中）；`grep -rn "data-availability\|dataset.availability" frontend/` → `literature-maps.js:1827`、`literature-maps.css:39`（双向命中）。其余新增均为**复用既有 class**（`literature-map-badge` 由 `:838 renderStatusBadge` 经 `createElement` 生成，`:1824-1829` 只改 textContent/dataset/setAttribute）。 |
| 2 | **版本号 `?v=N`** | **PASS** | `grep -n "?v=" frontend/index.html` → `:8 styles.css?v=68`、`:9 literature-maps.css?v=27`、`:805 literature-maps.js?v=42`、`:807 app.js?v=70`。四个被改动资源**版本均已递增**（styles 67→68、lm.css 26→27、lm.js 40→42、app.js 68→70），`tests/frontend/fixtures/literature_map_component.html` 与 7 个断言文件同步。按本轮题面约定不因版本号判 P1。 |
| 3 | **XSS** | **PASS** | `git diff -U0 frontend/app.js frontend/literature-maps.js \| grep '^+' \| grep -E "innerHTML\|insertAdjacentHTML\|eval\(\|new Function\|document.write\|outerHTML"` → **0 命中**；`tests/frontend/test_frontend_literature_map_expansion.py` 也断言 `"innerHTML" not in MODULE`。新增用户可见文本全部走 `textContent`（`app.js:5142/5168/5180/6283`）或常量 `setAttribute`（`literature-maps.js:1828/1829`）。 |
| 4 | **CSS 作用域** | **PASS** | `git diff frontend/styles.css` 新增 `#kb-view .kb-item.kb-item-jump-target`（`:804`）与 `#kb-view .kb-item.kb-item-jump-target:focus`（`:809`）；`git diff frontend/literature-maps.css` 新增 `#literature-maps-view .literature-map-badge[data-availability="usable"]`（`:39`）。**两条均以 `#kb-view` / `#literature-maps-view` 容器前缀限定**，无裸标签 / 无全局选择器污染。 |

**静态检查**：`node --check frontend/app.js` → OK；`node --check frontend/literature-maps.js` → OK；`node --check frontend/research-tasks.js` → OK。

### 四、本轮问题清单

| # | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| P2-1 | P2 | `literature-maps.js:5437-5443` | flush 的 409/网络失败把 `positionsDirty` 置回 `true`，但此时 `state.active === false`，`scheduleViewSave`（`:5356`）永不再排期 → dirty 残留到下次进入；重新进入后靠 `applyMapPayload` 带回新 revision + 用户下一次交互自动自愈 | `setActive(true)` 分支补 `if (state.positionsDirty \|\| state.viewDirty) scheduleViewSave();` 显式补偿，避免「切回后必须再动一次才落库」 |
| P2-2 | P2 | `app.js:6528` + `:6208-6213` | pending 保留期间若列表仍有 `indexing`，2.5s 轮询每次重渲染都会再 `scrollIntoView` 一次（目标不变，用户已被滚到该条） | 无需改；若要做绝，可在 `consumePendingKbJump` 内记录「本目标已定位过」并跳过重复 scroll，仅保留高亮 |
| P2-3 | P2 | `app.js:5183` | `jumpToKnowledgeBase` 返回的 promise 在两处调用点（`:4938`、`:5054`）未被消费；`loadKbPapers` 内部已 catch，`then(_, onRejected)`（`:5188`）也已兜底，不产生 unhandled rejection | 可选：调用点加 `void` 前缀表达「故意忽略」，纯可读性 |
| P2-4 | P2 | `frontend/literature-maps.js:5366-5393` | `allowInactive` 放行与 `state.view` 不进 payload 的因果链**无单测覆盖**（`grep -rn "flushPendingViewSave" tests/` → 0 命中），本轮仅靠 E2E 验证；后续若有人把 `viewport.width/height` 写进 PATCH body，回归不会被门禁拦住 | 补 `tests/frontend/test_frontend_map_view_save_on_leave.js` 用例：断言 `allowInactive` 时 `mapViewportWorldSize().valid === false` 仍发出 1 次 PATCH，且 body 中**不含** `width/height/cssScale` 键（防「测量值混入 payload」的静默回归） |

**P0 = 0，P1 = 0。**

### 五、Summary（ECC 格式）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 4 | info |
| LOW | 0 | note |

Verdict: **APPROVE —— 通过。**

### 六、最终结论

**通过（Approve）。** 缺陷 C 与缺陷 A2 的修复在代码事实上均成立：

- **缺陷 C**：`allowInactive` 放行**不会** resurrect 零尺寸 bogus 视口——`mapViewportWorldSize()` 的测量数值被证明不进入 PATCH body（`:5405-5411` 逐字核对），历史缺陷的唯一入口 `fitView` 仍保留 `:5307` 的 `valid` 守卫；普通 active 路径守卫完好（`:5384`、`:5393`、`:5385`）；`allowInactive:true` 仅由 `flushPendingViewSave`（唯一调用点 `:7178`）注入；无新增重复 PATCH、无 unhandled rejection、409 概率不升反降。
- **缺陷 A2**：定位已从「跳转前的旧 DOM」彻底迁移到「每次渲染后的新 DOM」（`:6528` + `:5137` 双保险），「已定位」文案与 class/scroll/focus 在同一次成功分支内原子写入（`:5142` 唯一写点）；C-4 失败文案不被覆盖成立；C-3 离开清 pending/高亮不冲突；`research-tasks.js:1691` 与 `literature-maps.js:6981` 两个跨模块入口均走同一新逻辑并受益。
- **四项必守全部 PASS**（DOM 契约 / 版本号 / XSS / CSS 作用域）。

4 个 P2 均为窄口径可观测项与测试覆盖建议，**不阻塞合并**；建议至少落实 **P2-4**（补一条「payload 不含测量值」的回归用例），以把本轮靠 E2E 才抓到的因果链固化为门禁。
