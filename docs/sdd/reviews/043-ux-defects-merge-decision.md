# Spec043 UX 缺陷修订 · 验收签字与合并裁决（Merge Decision）

| 项 | 值 |
|---|---|
| **文档类型** | 架构师合并裁决 + 验收签字（Gate 1/2/5 + DoD 自检） |
| **评审者** | architect（子代理，本轮 Spec043 缺陷修订验收签字与合并裁决） |
| **角色** | 架构师 / `architect`（需求评审、技术评审、合并裁决、验收签字） |
| **模型** | Deepseek-V4.1-Flash（按 spec 执行配置表 `043:441`；上下文上限 32k 档） |
| **分派方式** | 主会话一次性分派：**只读** + 仅产出本文件；禁改代码 / spec / 台账 / 其它评审文档 |
| **裁决日期** | 2026-11-06（Asia/Shanghai） |
| **基线** | 工作区未提交快照；`git log -1` = `09f4b6a3`；`git status --porcelain` = 36 项（11 M 源码/测试 + 2 M 文档 + 23 未跟踪） |
| **禁止事项（已遵守）** | 未改任何业务代码、测试、spec、`spec-status-changelog.md`、其它评审文档；未 git add / commit / push / 合 main |

## 结论速览

# 最终结论：**同意收口**

- **Gate 1 / Gate 2**：增量需求评审与技术评审均有**真实结论**、均为「通过」——**通过**（附条件成立，条件已由后续复审/回归/E2E 逐条闭合）。
- **Gate 5**：4 项冻结范围逐条对照真实 E2E 证据**全部成立**；「明确不做」**未被突破**；**P0 = 0 / P1 = 0**（分端最终复审口径）；关键产物路径存在；部署版本 `/api/health 200` 且**已确认加载新代码**。
- **DoD**：三份评审有真实结论 ✅、签字栏已在本文件填写 ✅、`spec-status-changelog.md` 已追加 ✅、引用路径核验 ✅；**验收报告（tester 并行）、复盘、本地 commit 未完成 → 列为主会话待完成项，按指令不构成打回**。

---

## 一、Gate 1 / Gate 2：增量需求评审与技术评审

### 1.1 如实标注（重要）

**本轮的需求评审与技术评审是「收口阶段并行补做的增量评审」，不是实现前拦截。** 用户已于 2026-11-05 逐条确认 4 项（`spec:420-422`），冻结范围成文（`spec:426-433`），实现随后落盘，两轮 P1 修复后评审才补齐。因此：

- **不追认**「评审在实现前拦截了缺陷」这一说法；两份文档自身也在「评审基线」里明确写了「本轮是收口后的增量评审，不是实现前拦截」，我对该标注**予以确认**。
- 该时序缺陷记录为流程改进项（见第五节 R-1），不计入本次合并阻塞：评审结论与实现证据可独立复核，且缺陷是在真实用户复现 + tester/E2E 双路径中被抓到的，未被掩盖。

### 1.2 需求评审（`docs/sdd/reviews/043-ux-defects-requirement-review.md`）

| 检查 | 判定 | 依据 |
|---|---|---|
| 有真实结论 | **通过** | 结论「通过（附强制约束清单）」；4 项逐条给出目标清晰度/可测性/边界完整性判定 |
| 结论非空泛 | **通过** | C-1 ~ C-9 共 9 条带 `文件:行` 与最小改法的约束清单，含 2 个 P1（C-1 keepLocalView 无调用方、C-2 view_initialized 后端不写） |
| 有实测证据 | **通过** | 亲自跑 3 个 node 测试 + `node --check`；后端测试未跑并**如实声明**（`五、实测证据` 注释） |
| 范围不扩张核查 | **通过** | `四、范围扩张核查` 12 行表格，逐项给出「无/已发生」与证据；唯 `styles.css` 落表外，转 T-7 裁决 |
| 未越权改 spec | **通过** | 文档末尾声明「禁改业务代码 / spec / 台账 / 测试」；`git status` 中 spec 的 M 由主会话产生 |

**判定：需求评审通过。** 其 P1 条件（C-1、C-2）在后续由 `frontend-reviewer` 第二轮复审与 `backend-reviewer` 第二轮复审确认闭合（见 1.4）。

### 1.3 技术评审（`docs/sdd/reviews/043-ux-defects-tech-review.md`）

| 检查 | 判定 | 依据 |
|---|---|---|
| 有真实结论 | **通过** | 结论「通过（附强制约束清单）」；后端 B-1~B-5、前端 F-1~F-4 逐项带 `文件:行` |
| 模块划分与边界 | **通过** | B-1 判定 `node_count` 由路由层拼装注入、不进 `to_dict()`（避免扩散到 `GET /{id}` 与 graph 的 `map`）；分层未被打破 |
| 并发 / 事务 / 外键 | **通过** | T-2 + DEC-4：`list_maps` 与 `active_node_counts` 两次独立连接**不加跨查询长事务**（展示用派生数，KISS）；`update_view` 全程单事务；无表结构/外键/迁移改动 |
| SSRF / 来源可信 | **通过（N/A 且已核）** | 无新增外发请求；`active_node_counts` 纯本地 SQLite 参数化查询；`styles.css`/`literature-maps.css` 为本地静态资源 |
| 是否复用既有实现（禁第二套） | **通过** | `node_count` 复用既有 `removed_at IS NULL` 口径（不另起口径函数）；跳转复用 `kbDocumentId` 优先级语义；导出复用既有白名单 `_export_view_settings` |
| 契约零改动 | **通过** | `PATCH /view` body 字段集合不变；`MapViewRequest` `extra="forbid"` 保持；DEC-2 明令禁止新增 body 字段 |
| 架构决策落盘 | **通过** | `九、架构裁决` DEC-1 ~ DEC-6 六条成文，可直接被下游引用 |

**判定：技术评审通过，DEC-1 ~ DEC-6 纳入本轮基线并继续有效。**

### 1.4 P1 条件闭合追踪（评审 → 修复 → 复审三段可查）

| 原始 P1 | 来源 | 修复证据 | 闭合判定 |
|---|---|---|---|
| C-1 / T-P1-1 `keepLocalView` 无调用方 | 需求评审 C-1、技术评审 T-P1-1 | `literature-maps.js` 唯一传参点 + 新增接线级测试 `test_frontend_map_view_keep_local_on_return.js` | **闭合**（frontend-review 第二轮） |
| C-2 / T-P1-2 `view_initialized` 后端不写 | 需求评审 C-2、技术评审 T-P1-2 | `store.py:673` 单点写入 + `service.py:2586-2587` 导出透传 + 5→7 条后端用例 | **闭合**（backend-review 第二轮，含双重反向验证） |
| T-7 `styles.css` 越表 | 技术评审 T-7 | `spec:457` 新增 FE-4 行 + `:460` 补登记说明 | **闭合**（文档登记） |
| 后端复审 P1-1 `service.py` 越表 + 导出面未测 | backend-review 第一轮 P1-1 | `spec:458` 新增 BE-3 行 + 2 条导出用例（未保存无键 / 保存后 `is True`） | **闭合**（backend-review 第二轮） |
| 前端复审 P1-1 / P1-2（flush 结果被旧 revision 覆盖 / `loadMapGraph` 跨图串位） | frontend-review 第一轮 | `:2612-2622` revision 合并、`:2603-2607` `positionsMapId` 守卫 + 2 个新测试文件 | **闭合**（frontend-review 第二轮 + 变异反证） |

---

## 二、Gate 5：冻结范围逐条对照 E2E 证据

证据主源：`docs/sdd/reviews/043-ux-defects-live-e2e.md`（真实 Chromium `playwright-cli` session `ra043` + 真实 curl，非 mock / 非内部函数直调）。

| # | 冻结项（`spec:428-431`） | E2E 证据 | 判定 |
|---|---|---|---|
| 1 | 列表每项新增 `node_count`（`removed_at IS NULL`）；卡片**只**显 `${node_count} 篇`，**不显示「目标 20」**；缺失/非数回落 `requested_count` | `GET /api/literature-maps` 7 张图全带 `node_count`（`0/0/20/20/20/21/32`）；目标图 `partial / requested_count 20 / node_count 32`；卡片 `innerText` = `… 可用 32 篇`。**我本机只读复跑一致**（32/0/0/21/20/20/20） | **通过** |
| 2 | `status==='partial'` 且已有活动节点 → 徽标「可用」+ `title`/`aria-label` 保留说明；`generating/failed/stopped` 原样；**不改后端 status / 不改持久化 / 不清历史作业** | 目标图显示「可用 32 篇」；`node_count=0` 的地图仍显「部分完成 0 篇」；后端 `status` 仍为 `partial`（复跑确认）；筛选下拉与 `mapStatusLabel` 未改（frontend-review 必查 1 + 测试第 8 段） | **通过** |
| 3 | `jumpToKnowledgeBase` 优先 `data-document-id`、`data-paper-id` 兼容；命中→滚动到视口中央 + focus + 可见高亮；未命中→明确提示；消费 `pendingKbPaperId`；**不自动展开详情**；`research-tasks.js` 不改代码 | 真实点击链路（节点→「在知识库中查看」）返回 `highlighted:true / focused:true / rectTop 467 / inViewport:true / status 已定位…`；修复前对照为 `highlighted:false / rectTop 10505 / inViewport:false` 而文案仍称「已定位」= 假阳性，现已消除；`research-tasks.js` 在 `git status` 中**未出现**（未改），经 UMD `globalThis` 同入口受益 | **通过** |
| 4 | `setActive(false)` 前 flush dirty、`saveView` 允许该次落地；切回不覆盖本地 dirty；`initialFitPending` 改显式标记，不再以 `(0,0,1)`/最小缩放猜测 | 真实链路「zoom-out 后 **60ms（< 500ms 防抖）**立即切走」→ PATCH 真实发出，后端 `revision 287→288`、`viewport` = 缩小后新值、`view_initialized:true`；切回后 DOM `transform` 与 zoom-out 后**逐字一致**（未回 `scale(2.8)`）。修复前同链路 PATCH 从未发出。`view_initialized` 亦经我本机 `GET /{id}` 复跑确认 `true` | **通过** |

**每项均有「修复前 → 修复后」对照，非单点快照。**

### 2.1 「明确不做」（`spec:433`）逐条未被突破

| 明确不做 | 核查 | 判定 |
|---|---|---|
| 不改 `PATCH /view` 契约与 409 冲突策略 | 两轮复审均核 `saveView` body 仍为 `expected_revision/positions/viewport/layers/label_mode`；`MapViewRequest` `extra="forbid"` 保持，且后端用例断言传 `view_initialized` → **422**；409 处理策略未改（仅 `stillCurrent` 放宽 `allowInactive`） | **未突破** |
| 不改后端 `status` 语义 | `git diff` 未触及 `status` 写入；复跑 `GET` 仍 `partial`；徽标改的是渲染层 `textContent`，`dataset.status` 仍 `partial` | **未突破** |
| 不改导入／索引流程与 `/api/kb/*` | 后端 diff 仅 3 文件（routes/store/service），无 kb 相关改动；E2E 只读 `GET /api/kb/papers` | **未突破** |
| 不改 Task11 预览／批次／分析逻辑 | 无相关文件改动 | **未突破** |
| 不改节点拖拽与「整理间距」交互 | 交互代码未改；只改保存时机；`allowLayoutPreview` 守卫未动 | **未突破** |
| 不引入 localStorage 草稿 | `grep` 无新增 localStorage 写入通路 | **未突破** |
| 不改知识库列表分页／搜索 | `frontend/app.js` 改动局限跳转定位与 `showView` 清理；分页/搜索未动 | **未突破** |
| 不改其他视图切换逻辑 | `showView` 仅新增「离开 kb 清 pending/高亮」与 kb 分支渲染，其余分支未动 | **未突破** |

### 2.2 P0 / P1 计数

| 来源 | 最终 P0 | 最终 P1 | 判定 |
|---|---|---|---|
| 增量需求评审 | 0 | 2（C-1/C-2，已闭合） | 通过 |
| 增量技术评审 | 0 | 1（T-P1-1，已闭合）+ 1 登记项（T-7，已登记） | 通过 |
| 后端复审（第二轮） | **0** | **0** | Approve |
| 前端复审（第三轮，E2E 修复后） | **0** | **0** | Approve |
| 后端回归（第二轮） | — | — | READY（240 passed） |
| 前端回归（第二轮） | — | — | READY（396 passed / 0 failed；node 22/22） |

**合并口径 P0 = 0 / P1 = 0。** 说明：前端/后端回归在各自时点为 READY；E2E 之后又落了「缺陷 C / A2」修复批次并再升版本号（`literature-maps.js 41→42`、`app.js 69→70`），该批次已由 **frontend-review 第三轮** 独立复审（0 P0 / 0 P1）与 **live-e2e** 真实运行时证据覆盖。版本号以工作区实况为准：**`styles.css?v=68` / `literature-maps.css?v=27` / `literature-maps.js?v=42` / `app.js?v=70`**（早前文档里的 `v=41 / v=69` 为过期快照，不据此判定）。

### 2.3 关键产物路径存在性（我逐一 Read / 核对）

| 路径 | 状态 |
|---|---|
| `docs/sdd/specs/043-literature-map-topic-exploration.md`（含 `:309-462` 三段修订 + 冻结范围 + 任务表含 FE-4/BE-3） | 存在 ✅ |
| `docs/sdd/reviews/043-ux-defects-requirement-review.md` | 存在 ✅ |
| `docs/sdd/reviews/043-ux-defects-tech-review.md` | 存在 ✅ |
| `docs/sdd/reviews/043-ux-defects-backend-review.md` / `-frontend-review.md` | 存在 ✅ |
| `docs/sdd/reviews/043-ux-defects-backend-regression.md` / `-frontend-regression.md` | 存在 ✅ |
| `docs/sdd/reviews/043-ux-defects-live-e2e.md` | 存在 ✅ |
| `docs/sdd/reviews/043-ux-defects-acceptance-review.md` | **不存在（tester 并行产出中）** — 按指令不因此打回，见第四节 |
| `docs/sdd/retro/2026-11-06-*ux-defects*`（复盘） | **不存在** — 主会话待完成，见第四节 |
| 关键实现：`backend/.../routes_literature_maps.py`、`store.py`、`service.py`、`frontend/literature-maps.js`、`app.js`、`styles.css`、`literature-maps.css`、`index.html` | 均在工作区且已改 ✅ |
| 新增测试：`tests/literature_maps/test_map_list_node_count.py`、`test_map_view_initialized_flag.py`、6 个 `tests/frontend/test_frontend_*.js` | 存在 ✅ |

### 2.4 真实部署版本健康检查（我亲自执行）

| 命令 | 结果 |
|---|---|
| `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/health` | **200** |
| `GET /api/literature-maps?limit=100` | 13 字段全集，7 图全部含 `node_count`；目标图 `node_count=32` |
| `GET /api/literature-maps/0baabeae…` | `revision 288`、`view_settings.view_initialized: true`、`viewport {scale:2.3333, x:-597.696, y:-597.703}` |

→ **部署进程已加载新后端代码**，`backend-regression` R2.7 留的「待部署验证」项就此实质闭合（E2E 阶段重启后已复验，我的只读复跑再次确认）。

---

## 三、DoD 逐项自检

| # | DoD 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | 三份评审（需求 / 技术 / 验收）有**真实结论** | **部分✅** | 需求评审 ✅、技术评审 ✅（均含强制约束清单，非空泛）；**验收报告由 tester 并行产出，我读取时不存在** → 列主会话待完成，**以 tester 报告最终结论为准**，不打回 |
| 2 | 验收签字栏 | **✅（本文件已填）** | 架构师签字栏见第六节；tester 签字栏归其验收报告 |
| 3 | `spec-status-changelog.md` 已追加 | **✅** | 末尾两条：`待确认 → 已确认`（用户逐条确认 4 项 + 冻结范围 + 执行配置 + 任务拆分）与「地图列表论文数显示缺陷修订 / UX 缺陷 A/B」两条补充记录 |
| 4 | 引用路径存在 | **✅** | 见 2.3；唯一缺口是 tester 验收报告，非引用错误 |
| 5 | 复盘文档 | **待主会话完成** | `docs/sdd/retro/` 下尚无本轮复盘；按指令由主会话收口时补，不代做、不因此打回 |
| 6 | 本地 commit | **待主会话完成** | `git status` 显示 36 项未提交，HEAD 仍 `09f4b6a3`；按指令由主会话收口时提交，我未执行任何 git 写操作 |
| 7 | 两处越表补登记已在 spec 任务表登记 | **✅** | `spec:457` FE-4（`literature-maps.css` / `styles.css`）、`spec:458` BE-3（`service.py`），并有 `:460` 补登记说明 |
| 8 | P0/P1 = 0 | **✅** | 见 2.2 |
| 9 | 真实部署 `/api/health 200` | **✅** | 见 2.4 |

**DoD 缺口 3 项（验收报告 / 复盘 / 本地 commit）均为流程性收尾项，不涉及代码正确性，不构成打回理由。**

---

## 四、主会话待完成项（收口清单，非阻塞）

| # | 事项 | 依据 | 谁做 |
|---|---|---|---|
| M-1 | 等 `tester` 产出 `docs/sdd/reviews/043-ux-defects-acceptance-review.md`，核对其结论为「通过 / READY_FOR_USER」并补 tester 签字；**本裁决以 tester 报告最终结论为准** | 材料清单 + 2.3 | 主会话 + tester |
| M-2 | 落盘复盘 `docs/sdd/retro/2026-11-06-*-ux-defects*.md`（至少覆盖：评审与实现并行的时序问题、P1 接线级测试缺失、「测了函数没测接线」、E2E 才抓到缺陷 C/A2、越表补登记机制） | 指令 + R-1/R-2 | 主会话 |
| M-3 | 本地 commit（建议把本文件、7 份 ux-defects 评审/回归/E2E、spec 三段修订、`spec-status-changelog.md` 与代码/测试**同一提交**，避免报告与实现分离）；提交前自查 `git diff -- backend/` 与 `git diff --numstat` 与 backend-review 基线一致（`4/2`、`4/0`、`25/0`） | 指令 + DoD 6 + backend-review 第二轮 mtime 提示 | 主会话 |
| M-4 | `spec` 主状态维持「已完成」（本轮为 Bug 修订，不新建编号、不改变主状态）；如后续再改，版本号必须再递增（`v=42/v=70` 已随本次部署曝光） | `spec:311`、frontend-review 必查 2 | 主会话 |
| M-5 | 提交前确认 `.playwright-cli/`、`artifacts/jd-agent-infra-capability-map.md` 等与本次无关的未跟踪项**不被误带入** | `git status` 36 项中含无关项 | 主会话 |

---

## 五、残余 P2 与后续建议

**合并口径：以下均不阻塞，建议并入后续迭代（下一轮 Spec043 修订或独立技术债项），不扩大本轮范围。**

### 5.1 功能/体验类

| ID | 级别 | 内容 | 出处 |
|---|---|---|---|
| R-1 | P2（流程） | 评审与实现并行导致「先实现后评审」，本轮未出现掩盖，但削弱拦截效力。建议后续 Bug 修订**先在 spec 冻结范围内完成增量评审结论落盘再分派实现**，或明确接受并行时必须在 E2E 前补齐评审并标注 | 本裁决观察 |
| R-2 | P2（流程/测试） | 两轮 P1 均源于「测了机制没测接线」（`keepLocalView`、`view_initialized`）。建议 agent 规则增加硬约束：**任何 options/flag 型契约必须有「调用方传参」的接线级断言** | 需求评审 C-1、技术评审 T-P1-1 |
| P2-A | P2 | flush 的 409/网络失败后 `positionsDirty` 在 `state.active === false` 期间残留 → 需 `setActive(true)` 显式 `scheduleViewSave()` 补偿（当前靠下次交互自愈） | frontend-review 第三轮 P2-1 |
| P2-B | P2 | `allowInactive` 放行 + 「测量值不进 PATCH payload」的因果链**无单测覆盖**（`grep flushPendingViewSave tests/` → 0 命中），仅 E2E 验证过。建议补 node 测试：`allowInactive` 且 `viewport.valid === false` 时仍发 1 次 PATCH，且 body 不含 `width/height/cssScale` | frontend-review 第三轮 P2-4（建议优先） |
| P2-C | P2 | `state.viewSavedOnce` 是会话级标记、不按地图复位；同会话内先保存 A 图再开「旧数据 + 极小缩放」的 B 图会停在不 fit 的不可读视图。建议改 `Set` 按 mapId 记录 | frontend-review 第二轮 P2-3 |
| P2-D | P2 | `loadMapGraph` 跨图守卫清空 `positions/layoutPendingIds/positionsDirty` 但未清 `viewDirty`（窄口径串位，可拖回，非数据损坏） | frontend-review 第二轮 P2-1 |
| P2-E | P2 | 高亮清除时机：已在进入 kb / 离开 kb 时清（E2E 修复后补），但「用户手动点其它列表项」后仍可能残留到下次进入；验收材料已登记为「临时提示」语义即可 | 需求评审 C-3、技术评审 T-8、frontend-review 第二轮 P2-3 |
| P2-F | P2 | KB `indexing` 窗口内 2.5s 轮询每次重渲染会再次 `scrollIntoView`（目标不变，可接受）；可在 `consumePendingKbJump` 记录「已定位过」跳过重复 scroll | frontend-review 第三轮 P2-2 |
| P2-G | P2 | `selectMap` 在 `await waitForPendingViewFlush` 期间无 loading 反馈（`setStatus` 在 await 之后） | frontend-review 第一轮 P2-1 |

### 5.2 后端/文档类

| ID | 级别 | 内容 | 出处 |
|---|---|---|---|
| P2-H | P2 | `active_node_counts` docstring 未写「调用方需保证 ids 有界（列表端点上限 100）」；`update_view` 无 docstring，「`view_initialized` 单向单调」仅在行内注释 | backend-review 第二轮 P2-2 / P2-4 |
| P2-I | P2 | `test_map_view_initialized_flag.py::_stored_view_json` 直连 `sqlite3.connect`（故意绕开 service 投影做交叉验证，合理），建议加一行注释；若 store 将来切 WAL 需复查 | backend-review 第二轮 P2-3 |
| P2-J | P2 | `test_frontend_map_view_keep_local_on_return.js:513` 有 1 处恒真断言 `assert.equal(h.requests ? 0 : 0, 0)`，建议删除或替换为真实状态断言（命中回归清单第 12 条） | frontend-review 第二轮 P2-2 |
| P2-K | P2 | `resolveInitialFitPending` 的注释仍描述「revision 四级判定」，实现为「显式 → viewSavedOnce → 无 viewport → 极小缩放 → `(0,0,1)`」；注释需与实现对齐 | frontend-review 第一轮 P2-5 |
| P2-L | P2 | ruff 4 条既有 SIM 告警（`service.py:1141/1246` SIM105、`store.py:2651` SIM114、`store.py:3151` SIM102）与本轮基线逐条一致，零新增；建议单独立技术债项清理，避免污染后续门禁判定 | backend-regression §3 / R2.2 |
| P2-M | P3 | 徽标注释措辞（「历史建图作业的 partial」→「`partial` 只在作业收尾时写入，因此必然是已结束作业的残留」） | 需求评审 C-6、技术评审 T-6 |
| P2-N | P2 | `_export_view_settings` 白名单让导出 JSON 新增 `view_initialized` 键（按存在性输出，非破坏性）；产品需明确「导出是否应暴露内部标记」的长期口径（当前已登记 BE-3 并补 2 条用例） | backend-review P2-1 / P1-1 |

---

## 六、两处越表补登记（已在 spec 任务表登记）

| 补登记 | 文件 | 裁决依据 | 登记位置 |
|---|---|---|---|
| **FE-4** | `frontend/literature-maps.css`、`frontend/styles.css` | 缺陷 A 的「**可见高亮**」是 `spec:430` 自己写明的要求，`kb-item` 为 `tabIndex=-1`，缺 `#kb-view .kb-item.kb-item-jump-target` 与 `:focus` 规则则该要求落空；`data-availability="usable"` 是冻结项 2 的样式载体。→ **冻结项必要组成，非范围扩张**；`?v` 三处均已同步（`styles.css 67→68`、`literature-maps.css 26→27`） | `spec:457` FE-4 行 + `spec:460` 补登记说明 ① |
| **BE-3** | `backend/app/literature_maps/application/service.py` | `_export_view_settings` 为**白名单投影**，不把 `view_initialized` 加进去则 `GET /{id}/export` 会丢失该键 → 导出与 API 口径分叉（正确性缺陷）。该白名单**只在导出 JSON 一条通路生效**，`PATCH /view` 与 `GET /graph` 走 `to_dict()` 原样输出，故契约零改动。→ **必要配套，非范围扩张**；已补 2 条导出用例（`240 passed`） | `spec:458` BE-3 行 + `spec:460` 补登记说明 ② |

**裁决**：两处越表均**予以追认**，性质为「冻结项的必要配套文件」，理由是文件改动与冻结范围存在不可分割的验收依赖（不做则该冻结项无法成立）。补登记已落 `spec` 任务表（主会话纯文档补记，无业务代码改动），满足可追溯性要求；backend-review P1-1 的第一项与 tech-review T-7 就此闭合。

**约束（继续有效）**：今后再出现「任务表外文件为实现所必需」，必须**先裁决后落盘**（或至少在同一提交内完成 spec 补登记），不得累积到合并裁决阶段才补。

---

## 七、架构师签字

| 项 | 内容 |
|---|---|
| **评审者** | architect（子代理，Spec043 UX 缺陷修订验收签字与合并裁决） |
| **角色** | 架构师 / `architect` |
| **模型** | Deepseek-V4.1-Flash（`spec:441`，32k 档） |
| **分派方式** | 主会话一次性分派：只读 + 仅产出本文件；禁止改代码 / spec / 台账 / 其它评审文档 |
| **日期** | 2026-11-06（Asia/Shanghai） |
| **结论** | **同意收口（Approve for closure）** |
| **签字生效条件** | ① 本裁决即为架构师签字；② 主会话完成 M-1 ~ M-5（tester 验收报告 + 复盘 + 本地 commit + 提交范围自查）；③ 若 tester 验收报告给出非「通过」结论，或提交前 `git diff` 偏离 backend-review 基线，本签字自动失效，须重新裁决 |
| **不涵盖** | 不涵盖 push / 合 `main`（按项目规范仅本地提交）；不代替用户人工验收（用户人工验收仍待执行） |

---

## 八、裁决摘要（一句话版）

4 项冻结范围均有「修复前 → 修复后」的真实 Chromium + curl 证据，8 条「明确不做」全部未被突破，分端最终复审与单端回归均 0 P0 / 0 P1，`styles.css` 与 `service.py` 两处越表经裁决为必要配套并已在 spec 任务表登记；DoD 仅余 tester 验收报告、复盘与本地 commit 三项流程收尾，由主会话完成——**架构师同意收口，签字生效以主会话完成 M-1 ~ M-5 为条件。**

---

*本文件由 architect 子代理生成。仅本文件为新增，未修改任何代码 / 测试 / spec / 台账 / 其它评审文档；未执行 git add / commit / push / 合 main。技术裁决以 `043-ux-defects-tech-review.md` 的 DEC-1 ~ DEC-6 为准，本文件仅作验收裁决与追认。*
