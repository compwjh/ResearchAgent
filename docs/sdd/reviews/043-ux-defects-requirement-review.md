# Spec043 缺陷修订 · 增量需求评审（Requirement Review）

| 项 | 值 |
|---|---|
| **评审者** | architect（子代理，本轮 Spec043 增量评审） |
| **角色** | 架构师 / `architect`（需求评审 + 技术评审 + 验签建议权） |
| **模型** | Deepseek-V4.1-Flash（按 spec 执行配置表 `043:441`；上下文上限 32k 档） |
| **分派方式** | 主会话一次性分派：只读代码 + 产出 `043-ux-defects-requirement-review.md` 与 `043-ux-defects-tech-review.md`，禁改业务代码 / spec / 台账 / 测试 |

## 评审基线（如实标注）

- 评审对象：`docs/sdd/specs/043-literature-map-topic-exploration.md` 三段 ——
  「2026-11-05 地图列表论文数显示缺陷」（`:309-363`）、「2026-11-05 人工验收阶段 UX 缺陷（二）」（`:365-422`）、「2026-11-05 用户确认与冻结范围」（`:424-459`）。
- **本轮是收口后的增量评审，不是实现前拦截**。用户已于 2026-11-05 对 4 项逐条确认（`spec:420-422`），冻结范围已成文（`spec:426-433`）。因此本评审**不追认「应更早拦截」**，只判定：冻结范围本身是否目标清晰 / 可测 / 边界完整 / 无范围扩张，以及落盘实现与冻结范围是否一致。
- **重要：评审期间工作区被并发写入。** 首次快照（约 23:41-23:44）时缺陷 A、B 零实现、版本号未升；随后实现陆续落盘。本文件所有结论基于 **23:48 之后的稳定快照**（`frontend/literature-maps.js` mtime 23:46:05、`app.js` 23:43:39、`styles.css` 23:43:44、`index.html` 23:47:13，此后 3 分钟无变更）。早期快照上的「零实现」判断已作废，不作为本轮结论依据。
- 所有结论基于 Grep + Read 真实文件行号 + 实跑测试，不含「应该没问题」式推断。

---

## 一、结论

# 结论：**通过（附强制约束清单）**

4 项冻结范围的目标清晰度、边界完整性、可测性经复核**全部成立**，且当前快照下四端实现与测试均已落盘并实测通过（见「五、实测证据」）。残留问题**不属需求缺陷，而是实现层 1 处漏接 + 若干验收判据补强**，已收敛为 P1/P2 约束清单，不构成打回理由。

| # | 冻结项 | 需求判定 | 实现现状（稳定快照） |
|---|---|---|---|
| 1 | 卡片篇数主显 `node_count` | **通过** | 已实现 + 后端/前端测试均通过 |
| 2 | 徽标 `partial + 有节点` → 「可用」 | **通过（附 C-5 / C-6）** | 已实现 + 测试通过 |
| 3 | 缺陷 A 跳转定位 | **通过（附 C-3 / C-4）** | 已实现（`app.js:5106-5178`、`styles.css:802-808`）+ 测试通过 |
| 4 | 缺陷 B 视图保存 | **通过（附 C-1 / C-2）** | 大部分已实现；**`keepLocalView` 无调用方接入**（P1 漏接）+ 测试通过但未覆盖该接线 |

> 结论类型说明：**通过（附意见）** = 可以进入验收/合并流程，但下列 C-* 必须在验收签字前逐条闭合。P1 项（C-1）闭合前不得部署验证。

---

## 二、强制约束清单（写入本文档即生效；不改 spec）

> dev / tester 可直接引用编号回传。C-1 未闭合则不算通过。

### C-1（P1，必须闭合）`keepLocalView` 机制已建但无任何调用方接入 —— 缺陷 B「切回不覆盖 dirty」实际未生效
- **事实**：`frontend/literature-maps.js:2362-2369` 的 `resetMapSelectionState(mapId, options)` 已实现 `keepLocalView`（仅当 `options.keepLocalView && previousMapId === mapId && (positionsDirty || viewDirty)`），`:2442-2445` 的 `applyMapPayload(payload, keepLocalView)` 也已在 `keepLocalView` 为真时跳过 `applySavedView`（不用服务端旧值覆盖）。
- **但**：`grep -n "keepLocalView" frontend/literature-maps.js` 除定义处外**无任何调用方传 `{keepLocalView: true}`**。切回路径仍是 `:7084` 的 `selectMap(state.selectedMapId)`（无 options）、`:1486` 同样无 options → `keepLocalView` 恒为 `false` → `:2383-2388` 照旧清 `positionsDirty / viewDirty` → **`spec:408`「切回时若本地仍有 dirty，不在 `selectMap` 中清空」仍不成立**。
- **为何不是需求缺陷**：`spec:408` 的要求本身清晰；是实现少接了一根线。
- **要求**：`setActive(true)` 的重入路径（`:7084`）必须传 `{ keepLocalView: true }`；`renderMapList` 的换图点击（`:1843`）与其它「用户主动换图」路径**必须不传**（否则坐标串图，见 T-P1-5）。
- **配套测试**：现有 `test_frontend_map_view_save_on_leave.js:348` 只直接调 `resetMapSelectionState('m1', { keepLocalView: true })`（单元级），**没有**验证 `setActive(true)` → `selectMap` 的真实接线。必须补一条「`setActive(false)` 后有 dirty → `setActive(true)` → dirty 未被清空」的接线级断言，否则该缺陷会带着绿色测试上线。

### C-2（P1，必须闭合）`view_initialized` 后端写入缺失：前端读得到，后端不会写
- **事实**：前端 `normalizeMapViewInitialized`（`literature-maps.js`）与 `resolveInitialFitPending` 已优先读 `view_settings.view_initialized`；但 `grep -n "view_initialized" backend/app/literature_maps/infrastructure/store.py backend/app/api/routes_literature_maps.py` **零命中** —— 后端从不写入该键。
- **后果**：`resolveInitialFitPending` 的显式分支永不命中，实际走的是 `revision > 0 → return false` 这条兜底。**这恰好能满足「重置后不 fit」**（因为重置会 `PATCH /view` 使 revision 递增），所以**用户可见行为正确**；但「显式标记」这一层是空转，属**死代码 + 与 spec:409 表述不符**（spec 要求「改由显式标记…判定」）。
- **要求**：二选一并在代码注释里写明 ——（a）后端在 `store.update_view` 的 `if viewport is not None:` 分支内写 `view["view_initialized"] = True`（一行，**不加 PATCH body 字段**，`MapViewRequest` 为 `extra="forbid"`，`routes_literature_maps.py:74-84`），使标记真正生效；（b）若无后端改动预算，则删掉前端 `view_initialized` 读取分支，并把 `spec:409` 的「显式标记」改为「revision 判定」的等价表述（由主会话决定是否改 spec）。**不接受**留着空转分支不说明。

### C-3（P2）缺陷 A 的高亮类名与 spec 未对齐，且无「高亮何时消失」的规则
- **事实**：实现用 `KB_JUMP_HIGHLIGHT_CLASS = 'kb-item-jump-target'`（`frontend/app.js:5106`）、CSS `#kb-view .kb-item.kb-item-jump-target`（`frontend/styles.css:802-808`）与 `:focus` 规则。这是**正确的做法**（`tabIndex=-1` 元素必须有显式焦点/高亮样式，否则 `spec:430` 的「可见高亮」落空 —— 我最初的担心已由该 CSS 消除）。
- **缺口**：`clearKbJumpHighlight()` 只在**下一次跳转**时被调用（`applyKbJumpFocus` 开头、`jumpToKnowledgeBase` 的无 key 分支）。用户手动点别的列表项、切换视图、或重新渲染列表后，高亮可能残留。
- **要求**：明确高亮清除时机（建议：`showView` 离开 kb 时清、或渲染列表时清），并在验收材料里写清「高亮是临时提示还是持久」；同时把类名与 spec 措辞对齐（spec 只说「可见高亮」，需在验收材料登记实际类名，便于后续维护）。

### C-4（P2）缺陷 A 的未命中提示会覆盖 `kbStatus` 的加载失败文案
- **事实**：`loadKbPapers():6188-6199` 用 `kbStatus` 承载「列表加载失败：…」；`jumpToKnowledgeBase`（`app.js:5170-5177`）在未命中时写 `KB_JUMP_NOT_FOUND_TEXT` 到同一 `kbStatus`。若列表加载失败（`loadKbPapers` reject），`.then(onRejected)` 分支也会写 `KB_JUMP_NOT_FOUND_TEXT`，**用户看到的是「未找到该文档」而不是「列表加载失败」**，误导排查方向。
- **要求**：加载失败与未命中必须可分（例如失败时保留失败文案 + 追加跳转提示，或未命中提示带「列表可能未加载完成，可点重试」）。验收材料须覆盖「列表加载失败时点跳转」这一场景。

### C-5（P2）徽标三项不变量必须在验收中逐条核对（「可掩盖真实状态」的兜底）
- **事实**：`mapCardStatusBadge` 只在 `partial && node_count>0` 时改文案；`renderStatusBadge` 的 `dataset.status` 保持 `partial`；`mapStatusLabel` 与筛选下拉 `['partial','部分完成']` 未改；`filteredMaps` 仍按 `map.status` 筛选。`title` + `aria-label` 同时给出（`:1794-1795`）。
- **判定**：「partial 改显可用是否掩盖真实状态」——**在本设计下可接受**。理由：用户已明确要求（`spec:429`）；信息未丢失（`title` + `aria-label` + `dataset.status` + 筛选仍可按 partial 筛出，四点叠加）。属「局部渲染层映射」而非「状态篡改」，后端 `status` 与持久化零改动。
- **要求（三条不变量，不可退让）**：① `dataset.status` 必须仍是 `partial`；② `mapStatusLabel` 与筛选下拉不得改动；③ `title` 与 `aria-label` 必须同时存在。已在 node:vm 测试第 5-8 段断言，**复核时不得删减**。

### C-6（P3）徽标注释措辞与实际条件需一致
- **事实**：`literature-maps.js` 注释写「历史建图作业的 partial」，实现条件只有 `partial && node_count>0`。经核实 `service.py:237/247/255` + `_finish`：`map.status='partial'` 只在作业收尾时写入（`store.py:1249` 的 `'partial'` 是 **job** 表字段，不是 map 表），故结论正确、措辞不够严谨。
- **要求**：注释改为「`partial` 只在作业收尾时写入，因此必然是已结束作业的残留」，避免后续角色误以为要排除在跑作业。

### C-7（P2）缺陷 B 的 E2E 判据存在假阳性，必须补时间戳证据
- **事实**：`saveView` 在 PATCH 成功后才清 dirty。若 500ms 防抖在切走前已成功，**即使 flush 没生效**，`spec:416` 的「切回后 viewport 一致」也会通过。
- **要求**：E2E 必须构造「拖动后 <500ms 立即切视图」，并记录 PATCH 时间戳**晚于** `showView('kb')` 时间戳。

### C-8（P2）`research-tasks.js:1691` 入口须实测，不能只靠推断「自动受益」
- **事实**：`research-tasks.js:1691` 传 `String(upgrade.document_id)`；新版 `selectKbJumpTarget`（`app.js:5113-5125`）优先 `data-document-id` → 该入口应自动修复，无需改 `research-tasks.js`（符合 `spec:430`「不改其代码」，避免第二套实现）。
- **要求**：验收材料记录一次真实点击「打开原文切片」的实测结果。若未命中，说明匹配有 bug，不得推给数据问题。

### C-9（P2）「修了 = 一并修掉」的解读：成立，但只覆盖这 4 项
- **判定**：`spec:422` 的解读**合理**。理由：① 用户四条答复逐条对齐 4 个冻结项；② 每项在 spec 内已有目标 / 边界 / 验证方式，不存在「用户说一个词、方案全靠猜」；③ 三个未回答的默认项（不自动展开详情、接受离开即保存、`initialFitPending` 一并改造）在 `spec:387-388 / :408-409 / :431` 都有具体行为描述，且 `:422` 明确声明按默认值执行。
- **边界**：**不得**因「用户说都修了」而延伸至 `spec:341-348 / :389 / :410 / :433` 的「明确不做」。特别是不改 `/api/kb/*`、`paper_id` 生成规则、节点拖拽与「整理间距」交互、知识库分页与搜索、`PATCH /view` 契约与 409 策略。

---

## 三、四项逐条需求评审

### 项 1：卡片篇数（`spec:428`）
- **目标清晰**：是。「卡片显示当前活动论文篇数，与图谱节点数一致」可一句话判定。
- **可测**：是，双端覆盖。后端 `tests/literature_maps/test_map_list_node_count.py:78-81` 断言 `node_count == 32 == len(graph 活动节点)`；前端 node:vm 断言 `countLabels == ['32 篇']` 且 `!metaText.includes('目标')`。
- **边界完整**：是（`spec:343-348`）。
- **回落语义**：`spec:428`「缺失／非数时回落 `requested_count`」；实现把负数也视为缺失（更严），可接受。`node_count === 0` 不被假值吞（渲染层用 `!== null`），正确。
- **判定：通过**。

### 项 2：状态徽标（`spec:429`）
- **目标清晰 / 可测 / 边界完整**：均是（`spec:429` 已写明「不改后端 status 值、不改持久化、不清理历史作业状态」）。
- **「是否掩盖真实状态」专项判定**：见 C-5 —— **信息未丢失，可接受**。`title` 单独兜底不足（触屏/读屏拿不到），但实现同时给了 `aria-label`，且筛选仍可按 `partial` 找到该地图，故「看不出来它曾经 partial」这一最坏情况不成立。
- **判定：通过（附 C-5 / C-6）**。

### 项 3：缺陷 A（`spec:430`）
- **目标清晰**：是（document_id 优先、paper_id 兼容、滚动+高亮、未命中提示、消费 pendingKbPaperId）。
- **可测**：是。`tests/frontend/test_frontend_kb_jump_focus.js` 实测通过，覆盖 document_id 命中 / paper_id 兼容 / 未命中提示 / pending 消费。
- **边界完整**：是（`spec:389` 五项明确不做）。实现**未**自动展开详情（`applyKbJumpFocus` 只 `scrollIntoView` + `focus` + 加 class + 写状态），与用户默认项一致。
- **默认项采纳正确**：不自动展开详情 —— 合理，用户诉求是「定位到这篇」而非「打开这篇」，自动展开会改变详情面板状态、扩大回归面。
- **判定：通过（附 C-3 / C-4 / C-8）**。

### 项 4：缺陷 B（`spec:431`）
- **目标清晰**：是（离开 flush、切回不覆盖 dirty、显式 (0,0,1) 不 fit）。
- **可测性**：flush 与 initialFit 两条已可测（`test_frontend_map_view_save_on_leave.js` 通过）；**「切回不覆盖 dirty」当前实际不可达**（C-1），且 E2E 判据有假阳性（C-7）。
- **默认项采纳正确**：「接受离开即保存」合理且必要 —— 现状（`setActive(false)` 只 `clearTimeout`）是丢改动的直接原因；既然用户明确不引入 localStorage 草稿，flush 是唯一自洽方案。
- **判定：通过（附 C-1 / C-2 / C-7）**。

---

## 四、范围扩张核查

| 检查项 | 结论 | 证据 |
|---|---|---|
| 改 `requested_count` 语义/持久化 | **无** | `models.py:69` 未动；后端测试断言 `requested_count == 20` |
| 改后端 `status` 值 / 清理历史作业 | **无** | `service.py` 的 `partial` 赋值未动；`to_dict()` 原样输出 |
| 改 `PATCH /view` 契约或 409 策略 | **无** | `git diff` 未触及 `routes_literature_maps.py:739-751`、`MapViewRequest:74-84`、`update_view:645-678`；`saveView` 的 body 字段集合仍是 `expected_revision/positions/viewport/layers/label_mode` |
| 后端新增 `view_initialized` 写入 | **未做（见 C-2）** | `grep view_initialized` 后端零命中 |
| 改 `/api/kb/*`、导入/索引 | **无** | `git status` 无 kb 后端改动 |
| 新增轮询 / SSE / localStorage | **无** | 无新增 |
| 新增表 / 迁移 / 索引 | **无** | `git status` 无 migration 新文件 |
| `node_count` 塞进 graph 的 `map` 对象 | **无** | `to_dict()` 未改，仅路由层拼装 |
| 改 `research-tasks.js` | **无** | `git status` 未列该文件 |
| 改 `styles.css`（任务表未列） | **已发生** | `spec:454-456` 任务表无 `styles.css`，但缺陷 A 的「可见高亮」必需 → 见 T-7 裁决 |

**范围扩张结论：实质无扩张；但 `styles.css` 落盘在任务表之外，须主会话登记（T-7）。**

---

## 五、实测证据（本轮亲自执行）

| 命令 | 结果 |
|---|---|
| `node tests/frontend/test_frontend_map_card_count_and_availability_badge.js` | `ok - map card count (node_count) and availability badge` |
| `node tests/frontend/test_frontend_kb_jump_focus.js` | `ok - kb jump focus (document_id 命中 / paper_id 兼容 / 未命中提示 / pending 消费)` |
| `node tests/frontend/test_frontend_map_view_save_on_leave.js` | `ok - map view save on leave (flush dirty / 不覆盖本地 / 显式 initialFit 标记)` |
| `node --check frontend/app.js` / `node --check frontend/literature-maps.js` | syntax ok |
| 版本号 | `index.html:8 styles.css?v=68`、`:805 literature-maps.js?v=41`、`:807 app.js?v=69`，10 处断言已同步（含 fixture `:1120`） |

后端测试未在本轮执行（本轮聚焦需求/技术评审，且 tester 职责为跑全量）；`tests/literature_maps/test_map_list_node_count.py` 的断言质量已通过静态审读（见技术评审 B-4）。

---

## 六、阻塞项汇总

| ID | 级别 | 内容 | 归属 |
|---|---|---|---|
| C-1 | **P1** | `keepLocalView` 无调用方接入 → 「切回不覆盖 dirty」实际未生效；测试只覆盖单元级，未覆盖接线 | `frontend-dev` |
| C-2 | **P1** | `view_initialized` 后端从不写入，前端显式分支空转（行为正确但属死代码/与 spec 表述不符） | `frontend-dev` / `backend-dev` |
| C-3 | P2 | 高亮清除时机未定，可能残留 | `frontend-dev` |
| C-4 | P2 | 未命中提示覆盖 `kbStatus` 的加载失败文案 | `frontend-dev` |
| C-5 | P2 | 徽标三条不变量须在验收逐条核对 | `frontend-reviewer` / `tester` |
| C-6 | P3 | 徽标注释措辞 | `frontend-dev` |
| C-7 | P2 | E2E 假阳性，须补时间戳证据 | `tester` |
| C-8 | P2 | `research-tasks.js` 入口须实测 | `tester` |
| C-9 | P2 | 「修了」不延伸到「明确不做」 | 主会话 |

**无 P0。C-1 / C-2 为 P1，须在验收签字前闭合。**

---

## 七、转「无保留通过」的条件

1. C-1 闭合（接线 + 接线级测试）。
2. C-2 二选一落地并写注释。
3. C-3 / C-4 有明确实现与用例。
4. C-7 / C-8 落在验收材料。
5. 与技术评审 `043-ux-defects-tech-review.md` 的 T-* 清单交叉闭合。

---

*本文件由 architect 子代理生成，禁改业务代码 / spec / 台账 / 测试；约束清单以本文件为唯一权威副本。*
