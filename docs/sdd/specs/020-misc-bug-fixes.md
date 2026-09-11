# 020 零碎 bug 解决

> 用法：不便单独立项的小型缺陷统一收进本 spec，按**批次**记录现象、根因、修复与验收；修完即走，避免为每个小 bug 重复走完整立项流程。

## 状态

**当前状态：已完成（第 4 批 BUG-06 已实现并验收；前 3 批 BUG-01~05 亦已完成）**

> 2026-09-12：追加第 4 批 **BUG-06（「新建对话」在非对话视图下点击无反应）**。经 grill with docs 定位：`beginDraft()`
> 只重置会话内容、从不调用 `showView()`，因此从「模型库」等视图点「新建对话」时 `#chat.hidden` 仍为 `true`。
> 用户确认修复边界（改 `beginDraft()` 内部 / 本次只修这个 bug / 顺手统一「新会话」→「新对话」/ 走 AGENTS.md 流程分派 `frontend-dev`）。

> 2026-09-11：追加第 3 批 **BUG-05（首次部署空库上传被 `INDEX_REBUILD_REQUIRED` 拦截）**；
> 根因 `manifest_store.require_generation()` 把「空库首次部署」与「旧索引需全库重建」混为一谈。
> 用户确认后，**因本会话无法分派 `backend-dev`（重试 2 次失败），用户豁免代行**，由主会话实现并通过验收：
> 定向测试 **157 passed**，真实服务实测首次上传 **HTTP 201**（原为 409）。
> **未执行全量回归**（用户明确要求）。详见 `plans/020/task-07-empty-index-generation-bootstrap.md` §9。
> 前 4 项（BUG-01~04）均已实现并通过验证，历史结论如下，本批不推翻。
>
> 2026-09-10：BUG-01/BUG-02/BUG-03 均已实现并通过运行时验证；第 2 批 **BUG-04** 经用户确认后由 `frontend-dev`（hy3）实现，
> `frontend-reviewer` 首轮打回 P1（提交期间误显红色"导入未完成"）→ 修复后复审通过；单端回归 `node --check` OK、
> `tests/test_frontend_paper_contract.py` 22 passed；跨端验收通过（见 `reviews/020-acceptance-review.md` 追加段，
> 因 `tester` 子代理 429 限流由主会话代行并留痕）。复盘落盘
> `docs/sdd/retro/2026-09-10-import-sync-and-qdrant-lock.md`。容器 spec 继续开放，后续零碎 bug 可继续追加批次。

## 一句话目标

为零散的小型缺陷提供统一容器：每条记录"现象 → 根因（含文件行号）→ 修复 → 验收"，改完即验、验完即收口，不因流程开销拖慢小修小补。

## 本批修复项（2026-09-10 · 第 1 批）

### BUG-01 点击"批量导入"无即时反馈，且提示"正在提交 0 个导入批次"

- **现象**：点击批量导入后界面毫无变化；常需点第二次才出现提示，且提示为"正在提交 **0** 个导入批次…"，令人困惑。
- **根因**：
  - `importPaperCandidates`（`frontend/app.js` 约 1029-1030）执行 `setImportPhase('submitting')` 与面板展开后，**未调用 `renderImportSummary()`**，直到约 1057 行请求全部完成才渲染。导入需下载 PDF + 建索引，耗时可达数十秒，期间界面不重绘 → "点了没反应"。
  - 文案 `正在提交 ${totalBatches + submitFailed} 个导入批次…`（约 957）在提交阶段取**已创建**批次数，而 `renderImportSummary` 只统计本轮 `currentRoundBatchIds`（此时为空）→ 恒为 **0**。
  - 单篇直成功（无 `batch_id`，`directSuccess` 分支）在提交阶段无任何可见反馈。
- **修复**：提交阶段立即调用 `renderImportSummary()`；新增 `paperState.pendingGroups`（= 待提交分组数）作为提交阶段计数口径，任何路径不得显示 0；单篇直成功与跳过场景各给可见反馈；批次卡片创建即渲染，非终态加进行中样式与动画，终态停止。
- **验收**：① 单次点击即出现"正在提交 N（≥1）个导入批次…"；② 卡片立即出现、非终态有动画、终态停止；③ 单篇直成功有反馈；④ 重复点击计数不翻倍；⑤ `node --check` 与契约测试通过。

### BUG-02 导入的论文 v2 恒为"待索引"（导入路径未提交 v2）

- **现象**：跳转到知识库后，导入进来的论文 v2 一直是"待索引"；用户疑虑"是否后台在构建但前端没表现"。
- **根因**：**并非后台在构建，而是根本没提交**。
  - 上传路径（`backend/app/api/routes_kb.py:120-132`）：v1 同步 `run_index_task_sync(..., CHUNKER_V1, ...)`，随后第 131 行 `_submit_index_task(record.paper_id, path, CHUNKER_V2)` 异步提交 v2。
  - 导入路径（`backend/app/knowledge_base/application.py` `KnowledgeBasePaperImportAdapter._default_indexer`）：**只建 v1，未提交 v2**。
  - 两条入口不一致 → 导入论文的 `chunkers.v2.status` 永远停在 `pending`。
- **修复（方案 A，与上传对齐）**：v1 索引成功后，按 paper_id 与落盘路径**异步提交 v2**；导入响应**不等待** v2（不阻塞）；v2 失败不影响导入成功，但状态置 `failed` 并带原因，可通过既有 reindex 补救。必须复用同一单线程池（避免 bge-m3 与 27B 争显存）。
- **验收**：① 导入后 `GET /api/kb/papers` 中该论文 `chunkers.v2.status` 由 `pending` 变为 `indexing`/`indexed`；② 导入响应不被 v2 阻塞；③ v2 失败时导入仍成功且 v2 状态真实可见；④ 上传路径行为不回归；⑤ 后端 pytest 全绿。

### BUG-03 单篇导入自动跳转知识库，且成功导入的论文不在"导入进度"面板展示

- **现象**：
  1. 勾选 **1 篇**点击"批量导入"后，界面**自动跳转**到"知识库"视图，导入进度面板随 `#papers-view` 一起被隐藏，看不到论文信息与批次信息（用户原话："之前做的挺好的，点击了跳转才跳转到个人知识库"）。
  2. 该篇在导入进度面板中**没有任何记录**（只剩汇总计数），即"没了之前有的导入论文的信息"。
- **根因**：
  - `frontend/app.js:1042-1044`：`groups.size === 1 && candidate_ids.length === 1` 时请求体为 `{search_id, candidate_id}`，后端 `backend/app/api/routes_paper.py:725-730` 走 `_import_single_paper`，返回 **`paper_id` 而非 `batch_id`**。
  - `frontend/app.js:1049-1052` 的 `directSuccess` 分支：`paperState.directSuccess += 1` 后**无条件**执行 `jumpToKnowledgeBase(data.paper_id)`；而 `jumpToKnowledgeBase`（`app.js:1203-1210`）内部 `showView('kb')` 会隐藏 `#papers-view` → 面板连同论文信息一起消失。
  - 同一分支**从不调用 `renderPaperBatch`**，所以这条路径的论文在面板里彻底没有渲染入口 → 只有计数、没有论文。
  - 该行为**非 BUG-01 引入**：`git diff 60e71f3~1 60e71f3 -- frontend/app.js` 的 6 处改动均未触碰 1051 行；BUG-01 之前用户多选导入走 `batch_id` 分支不触发，且"点了没反应"掩盖了该路径，BUG-01 打通即时反馈后单篇一键直达即暴露。
- **修复（仅前端）**：
  1. **移除自动跳转**：`directSuccess` 分支不再调用 `jumpToKnowledgeBase`；跳转只保留"在知识库中查看"按钮（`app.js:1128`）这一**点击式**入口。`jumpToKnowledgeBase` / `pendingKbPaperId` 函数本身保留不动。
  2. **direct 成功论文纳入面板**：新增 `paperState.directImports`，渲染该篇的标题 + `已完成` + "在知识库中查看"按钮；**该路径本就没有 batch，不得伪造批次号**。
  3. **保持既有可见性**：批量路径继续逐条展示所有状态（含未完成/等待登录/失败），导入结束**不清空**面板，已完成项与批次号保留。
- **验收**：① 单篇导入后**停留在论文检索视图**、不自动跳转，导入进度面板可见；② direct 成功论文在面板可见（标题 + 已完成 + 在知识库中查看按钮）；③ 点击"在知识库中查看"才跳转并定位该论文；④ 多篇批量路径逐条展示含未完成/失败/等待登录，完成后已完成项仍保留；⑤ `node --check` 与契约测试通过，`?v` 递增。

## 本批修复项（2026-09-10 · 第 2 批）

### BUG-04 导入状态栏永久停在"正在提交 1 个导入批次…"，且点击"重试失败项"毫无反应

- **现象**：批次卡片显示"批次 61621ad2-8725-4652-bcb3-42915ed68bfe · 失败"，状态栏却一直是"正在提交 1 个导入批次…"；点"重试失败项"后等待很久没有任何变化（用户原话："这个提示等待很久都没有反应"）。
- **根因**（实测证据）：
  - **相位死锁**：`frontend/app.js:947` 的 else-if 链用 `paperState.importPhase !== 'submitting'` 作为进入 `failed` 的守卫，而 `setImportPhase`（`app.js:908-911`）把计算结果写回 `paperState.importPhase`（`app.js:950`）。二者互锁：一旦进入 `submitting` 且本轮成功数为 0，**永远转不到 `failed`**，状态栏与批次卡片长期给出互相矛盾的结论。
  - **重试零反馈**：`app.js:1147-1151` 先把按钮 `disabled`，随后请求发出；成功路径**只** `renderPaperBatch` 不刷新状态栏，失败路径才 `renderImportSummary`。而后端 `retry_batch` 在请求线程内同步跑完整批（`paper_import_batch_service.py:434-439` → `run_batch`，实测本批 ~120s），期间前端既无中间态也无忙闲指示 → 视觉上"点了没反应"。
  - **重试后仍失败且不可判定**：该批次两条 item 均为 `KB_IMPORT_FAILED`；根因是 `data/kb/qdrant` 被**另一个项目实例独占**（见 spec-021 背景证据），前端无法据此给出可行动指引。
- **修复（仅前端）**：
  1. **相位不再自我守卫**：`submitting` 只在**确有提交/重试请求未返回**时成立（`paperState.submitInflight > 0`）；所有请求返回后立刻按成败重算 `completed` / `partial_success` / `failed`，禁用"上一次的相位"参与判断。
  2. **重试即时可见**：点击"重试失败项"后立即置该批次为进行中（`is-progressing`）+ 状态栏"正在重试 N 项…"；请求返回后无论成败都刷新批次卡片**与**状态栏汇总；失败时恢复按钮可用并给出可行动原因。
  3. **失败汇总必须落到 `failed`**：本轮成功数为 0 且有失败项时，状态栏必须显示"导入失败：N 篇（原因）"，禁止停留在"正在提交"。
- **验收**：① 本轮全部失败时状态栏显示"导入失败：2 篇（论文导入失败）"，不再出现"正在提交"；② 点击"重试失败项"后 1 秒内状态栏与批次卡片同时进入进行中态；③ 重试结束（无论成败）后状态栏与卡片同步刷新；④ 成功数 >0 且失败数 >0 时仍为"导入部分完成"；⑤ `node --check` 与前端契约测试通过，`index.html` 的 `?v=N` 递增。
- **明确不做**：不改后端任何接口与语义（本 bug 纯前端；根因 BK-存储占用与同步执行问题由 **spec-021** 承接）。

## 本批修复项（2026-09-11 · 第 3 批）

### BUG-05 首次部署（空库）上传被 `INDEX_REBUILD_REQUIRED` 拦截，无法上传任何文档

- **现象**：项目首次部署到一台新机器后，在知识库上传文档直接失败，提示：
  > 上传失败：索引尚未完成全库重建，请先执行 `python -m backend.app.knowledge_base.rebuild_index --confirm-replace`（`INDEX_REBUILD_REQUIRED`）

  用户判断合理：**首次部署时库是空的，本就无索引可"重建"，初始化应当自动完成，不该要求手工跑全库重建命令。**

- **根因**（实测 + 代码证据）：

  | 证据 | 位置 |
  |---|---|
  | 全新环境下 `data/kb` 目录**完全不存在**（无 `papers.json`、无 `index-generation.json`、无 `rebuild-runs`） | 实测 `ls data/kb` → 不存在 |
  | 代际门只检查 marker 文件是否存在，**不存在即报错**：`if not marker_path.exists(): raise ManifestStoreError("INDEX_REBUILD_REQUIRED", status=409)` | `backend/app/knowledge_base/infrastructure/manifest_store.py:599-603` |
  | 上传等接口统一过这道门，捕获后返回 409 与"请先执行 rebuild_index --confirm-replace"文案 | `backend/app/api/routes_kb.py:310-324`（`_require_generation`） |
  | 启动时也只打印一行日志，**不做任何初始化** | `backend/app/main.py:34-40` |
  | 同一函数内，`papers.json` 缺失却走另一个语义（`INDEX_FINALIZE_REQUIRED` / 503），说明"文件缺失"在本代码里本就被区别对待，唯独 marker 缺失被一律当成"需全库重建" | `manifest_store.py:606-613` |
  | spec-018 自己已定义"空库"是独立状态（`NO_DOCUMENTS_TO_REBUILD`），但**代际门没有区分它** | `docs/sdd/specs/018-...md` 全库替换语义 |

  **一句话根因**：代际门把两种完全不同的状态混为一谈——
  - **(a) 首次部署 / 空库**：从未有过索引，marker 从未生成 → 此时**没有任何东西需要重建**，应自动 bootstrap 一个初始代际；
  - **(b) 已有旧索引但代际不符**：才需要管理员停服执行全库重建 → 此时才该报 `INDEX_REBUILD_REQUIRED`。

- **修复方案**：

  1. **（根本，后端）`require_generation()` 增加空库 bootstrap 分支**：当 `papers.json` 不存在或为空数组 **且** marker 不存在时，判定为首次部署，**自动创建初始代际 marker**（`index-generation-v1`，`alias_target` 指向当前既有/新建的空 collection），不再抛错。
  2. **（启动自检）`main.py` lifespan 的 gate 处**，空库时自动完成上述 bootstrap，使首次启动即就绪（现状只 `print` 不动作）。
  3. **非空库保持 fail-closed**：只要 `papers.json` 有内容而 marker 缺失，仍然照旧返回 409 `INDEX_REBUILD_REQUIRED`，**绝不自动重建**。

- **验收**：
  1. 全新环境（删除 `data/kb` 或全新克隆）启动服务后，上传 PDF / Markdown → **200 成功**，不再出现 409。
  2. 已有文档数据但 marker 缺失的场景 → **仍返回 409 `INDEX_REBUILD_REQUIRED`**，行为不退化（回归保护）。
  3. KB 组件状态接口（`routes_kb.py:83` `kb_component_status`）中 `generation.ready` 在空库初始化后为 `true`。
  4. 后端 pytest 全绿，并新增"空库 bootstrap"与"非空库仍 fail-closed"两组定向用例。
  5. 空库首次启动时日志**不再出现** `[kb] index generation gate not ready`。

- **明确不做**：
  - 不改全库重建协议与 `--confirm-replace` 语义（非空库仍必须显式授权）。
  - 不改 `finalize` / `INDEX_FINALIZE_REQUIRED` 语义。
  - 不自动对**非空**库触发任何 embedding 或重建（严格避免"启动即重建"）。
  - 不改前端。

## 数据模型

| 字段 | 类型 | 约束 |
|---|---|---|
| `paperState.pendingGroups` | number | 必填；导入开始即置为待提交分组数，提交阶段文案取此值，不得为 0 |
| `paperState.importPhase` | 枚举 | 沿用 `idle/submitting/running/partial_success/completed/failed` |
| 批次卡片非终态表达 | DOM class + CSS 动画 | 非终态带进行中动画，终态移除（作用域限定 `#papers-view`） |
| 论文 `chunkers.v2.status` | 枚举 | 导入后 `pending → indexing → indexed`/`failed`，与上传一致 |
| `paperState.directImports` | array | 必填；单篇直达导入成功的论文记录（无 `batch_id`），必须在面板可见且**不得伪造批次号** |
| `paperState.submitInflight` | number | 必填（BUG-04）；当前未返回的提交/重试请求数；`submitting` 相位**唯一**依据，参与 judging 的**不是**上一次的 `importPhase` |
| `paperState.retryingBatchIds` | Set\<batch_id\> | 必填（BUG-04）；正在重试的批次，用于给批次卡片加进行中态并在返回后恢复按钮 |

## 端点 / 接口

| 动作 | 变化 |
|---|---|
| `POST /api/papers/imports` | **契约不变**（仅前端反馈与内部 v2 提交变化） |
| v2 异步提交 | 内部调用既有异步提交能力（`submit_index_task` 语义），不新增外部端点 |
| `GET /api/kb/papers` | 不变；需能反映 v2 进度（既有轮询能力） |
| `POST /api/kb/papers/{paper_id}/reindex` | 不变；作为 v2 失败后的补救入口 |

## 边界（每条变成一条测试）

- 点击导入后可见反馈不得依赖第二次点击。
- 提交阶段计数 N ≥ 1，任何路径（含单篇直成功、全部分组跳过）不得显示 0。
- 重复点击不产生重复批次、计数不翻倍。
- 导入响应不得因 v2 而阻塞。
- v2 失败不得把导入判定为失败；状态必须真实（不得假装成功）。
- 上传路径行为零回归。
- **任何导入路径都不得自动切换视图**（不得自动 `showView('kb')`）；跳转只能由用户点击"在知识库中查看"触发（BUG-03）。
- **direct 成功论文必须在导入进度面板有可见记录**；面板不得因导入完成而清空（BUG-03）。
- **不得为无批次的直达导入伪造 `batch_id`**（BUG-03）。

## 明确不做（防范围蔓延）

- 不改 v1 索引逻辑、spec-012 双版本检索语义与召回归并规则。
- 不改上传路径（`routes_kb.py`）现有行为。
- 不新建独立线程池；不在导入响应中同步等待 v2。
- 不改导入 CAS 状态机、并发领用与租约；不改下载安全策略。
- 不引入前端框架/构建；不新增/更名现有 DOM id。
- **不改后端接口与响应语义**（单篇 `_import_single_paper`、批量 `_create_paper_import_batch` 两条路径均不动）（BUG-03）。
- **不把单篇改走批量端点**（Q2(b) 未采纳；日后若要"每篇必有批次号"另行立项）。
- 不改 `jumpToKnowledgeBase` 自身行为（仅不再被自动调用）。

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-020（零碎 bug 容器） | 本文件 | — | 完成 |
| 02 | 前端即时反馈与批次卡片动画 | [`task-02-frontend-live-feedback.md`](../plans/020/task-02-frontend-live-feedback.md) | 01 | 完成 |
| 03 | 导入补齐 v2 异步索引 | [`task-03-v2-index-for-imports.md`](../plans/020/task-03-v2-index-for-imports.md) | 01 | 完成 |
| 04 | 评审、部署与复盘 | [`task-04-review-deploy-retro.md`](../plans/020/task-04-review-deploy-retro.md) | 02,03,05 | 完成 |
| 05 | 导入面板展示与跳转回归修复（BUG-03） | [`task-05-import-panel-and-jump-fix.md`](../plans/020/task-05-import-panel-and-jump-fix.md) | 01 | 完成 |
| 06 | 导入相位死锁与重试无反馈修复（BUG-04） | [`task-06-import-phase-and-retry-feedback.md`](../plans/020/task-06-import-phase-and-retry-feedback.md) | 05 | 完成 |
| 07 | 空库首次部署代际自动初始化（BUG-05） | [`task-07-empty-index-generation-bootstrap.md`](../plans/020/task-07-empty-index-generation-bootstrap.md) | 01 | 已完成（主模型代行） |

## 第 4 批：BUG-06 —「新建对话」在非对话视图下点击无反应（视图未切回）

- 状态：`已完成`（2026-09-12 由 `frontend-dev` 实现，`frontend-tester` 验收通过）
- 范围：**仅 `frontend/**`**（`app.js` + `index.html`）；不碰后端，不涉及会话持久化

### 现象与复现

新部署实例（空数据）上：① 点左侧导航「模型库」→ 正常切到模型库视图；② 再点左上角「新建对话」→ **界面停在模型库，毫无变化**，用户感知为"点击没反应"。

### 复现证据（已实测）

- 视图切换机制是**原生 `hidden` 属性**，不是 class：`app.js:2831-2836` 的 `showView()` 内
  `#chat.hidden = !isChat;`、`#models-view.hidden = nextView !== 'models';`
  共 6 个视图：`#chat` / `#models-view` / `#memory-view` / `#kb-view` / `#papers-view` / `#skill-tool-view`。
- 导航绑定：`app.js:2861-2878` 遍历 `.nav-item` → `app.js:2871 showView(item.dataset.view)`。
- 「新建对话」按钮：`index.html:17` `<button class="new-chat">`；`app.js:12` 取元素、`app.js:1589` 调用 `beginDraft()`。
- `beginDraft()`（`app.js:1102-1110`）只做：置空会话状态、移除 `has-started`、标题/状态改「新会话」、清消息、`input.focus()`。
  **全程未触碰 `hidden`，也未调用 `showView()`**。

### 根因

点「模型库」后 `#chat.hidden = true` 持续留存；`beginDraft()` 只重置会话内容，**不负责把对话视图切回前景**，模型库面板继续占据主区。
对比证据：`openConversation()` 首行即 `showView('chat')`（`app.js:1063`），而 `beginDraft()` 从未调用。
同一缺陷波及 `beginDraft()` 的全部调用点：`app.js:1589`（新建按钮）、`app.js:1651`（popstate 后退）、`app.js:1170`（删除会话/项目后）。
附带症状：`app.js:1108` 的 `input.focus()` 对隐藏元素静默失败，连光标都不动。

### 修复方案

1. `beginDraft()` 内补 `showView('chat');`（`showView` 为函数声明可提升，调用顺序无影响）。放**函数内部**而非 click handler，以覆盖上述全部调用点。
2. 术语统一：前端「新会话」→「新对话」（`index.html:52`、`index.html:74`、`app.js:879/880/882/1105/1106`）。已核实 `tests/` 无任何断言依赖这些文案。代码库主流用词为 `conversation`（`routes_conversations.py` / `conversation_service.py`），故统一为「对话」。
3. 静态资源版本号：`index.html:492` 的 `/assets/app.js?v=33` → `?v=34`，并把 `v33` 并入第 491 行兼容标记注释（沿用既有写法）。

### 明确不做

- 不做会话持久化 / 未保存草稿二次确认（属产品行为决策，另立 spec）。
- 不修静态资源 `Cache-Control` 缺失与 `?v` 手工令牌问题（`main.py:79` 的 FileResponse 无缓存头），另立 spec。
- 不动除 `#chat` 以外的视图切换逻辑。

### 验收标准

1. `node --check frontend/app.js` 通过。
2. `showView('chat')` 出现在 `beginDraft()` 函数体内。
3. 静态核对：在 `models` 视图下触发 `beginDraft()` 后，`#chat.hidden === false` 且 `#models-view.hidden === true`（由 `showView()` 保证）。
4. `grep -rn "新会话" frontend/` 返回 0 命中。
5. 既有前端契约测试不回归：`tests/test_frontend_management_contract.py`、`tests/test_frontend_task10_system_rule_contract.py`、`tests/test_frontend_paper_contract.py`。

## 执行配置

> 沿用用户指定：主会话（架构师）主导编排，子代理调用 `Deepseek-V4.1-Flash` 模型执行（2026-09-10 起；同日早些时候为 `hy3`，与 `AGENTS.md` 选型表一致）。

| 角色 | 模型 | 上下文 | 分派 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（不写死代号） | 200k | 主会话 | spec 维护、技术决策、落地校验 |
| 后端开发 | `Deepseek-V4.1-Flash` | 32k | `Task(backend-dev)` | 只改 `backend/**`（BUG-02） |
| 前端开发 | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 只改 `frontend/**`（BUG-01） |
| 后端/前端评审 | `Deepseek-V4.1-Flash` | 32k | `Task(*-reviewer)` | 只评各自端 |
| 回归 | `Deepseek-V4.1-Flash` | 32k | `Task(*-tester)` | 单端回归 |
| 验收总控 | `Deepseek-V4.1-Flash` | 32k | `Task(tester)` | 跨端验收与报告 |

## 评审记录

- 需求评审：`docs/sdd/reviews/020-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/020-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/020-acceptance-review.md`（**通过（代行，非独立评审）**——BUG-05 由主会话代行实现并按第 3 批验收项逐条运行时验证，见 `plans/020/task-07-*.md` §9；未执行独立子代理评审，因用户豁免代行且本会话无法分派 `backend-dev`）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-10 | 架构师(自身) | 按用户"就放进 spec，统称为零碎 bug 解决"的要求，建立本容器 spec；纳入第 1 批两项：BUG-01 导入即时反馈与 0 批次文案、BUG-02 导入未提交 v2 索引 |
| 2026-09-10 | 架构师(自身) | 用户反馈新回归（单篇导入自动跳转知识库、成功论文不在面板展示）。经 grill with docs 定位：`app.js:1042-1044` 单篇走 `_import_single_paper` 返回 `paper_id`，`app.js:1049-1052` directSuccess 分支**无条件** `jumpToKnowledgeBase` 且**从不渲染**，面板随 `showView('kb')` 隐藏。纳入 **BUG-03 / Task05**；用户确认修复边界：移除自动跳转、direct 论文入面板（不伪造批次号）、保持未完成项可见、仅改 `frontend/**` |
| 2026-09-10 | 架构师(自身) | 新回归：批次卡片显示"失败"但状态栏永久停在"正在提交 1 个导入批次…"，点"重试失败项"无任何反应。经 grill with docs 定位三处：`app.js:947` 与 `setImportPhase` 互锁导致 `submitting` 永不转 `failed`；`app.js:1147-1151` 重试无中间态且成功后不刷状态栏；后端 `retry_batch` 在请求线程内同步跑完整批（实测 ~120s）。追加第 2 批 **BUG-04 / Task06**（仅前端）；向后承接同步执行与存储占用的结构性问题至 **spec-021**；同期按用户要求将全部角色子代理模型统一为 `hy3` 并同步 `AGENTS.md` 选型表 |
| 2026-09-11 | 架构师(自身) | 新缺陷：首次部署到新机器后上传即报 `INDEX_REBUILD_REQUIRED`。实测 `data/kb` 目录**完全不存在**（无 `papers.json`/`index-generation.json`/`rebuild-runs`）；根因为 `manifest_store.py:599-603` 的 `require_generation()` 只判 marker 是否存在、不存在即 409，把「空库首次部署」与「已有旧索引需全库重建」两种状态混为一谈（`routes_kb.py:310-324` 过这道门；`main.py:34-40` 启动时仅打印不初始化；同函数内 `papers.json` 缺失却走 503 `INDEX_FINALIZE_REQUIRED`，语义本就区别对待）。纳入第 3 批 **BUG-05 / Task07**（仅后端），方案为「空库自动 bootstrap 初始代际 + 非空库保持 fail-closed 仍 409」；spec 转 `待确认`，确认前不动业务代码 |
| 2026-09-11 | 架构师(自身) | 用户确认「按这个执行，不需要全量回归」。分派 `backend-dev` 实施 Task07 **失败 2 次**：当前会话的 `Task` 工具无法解析项目自定义子代理 `backend-dev`（`.codebuddy/agents/backend-dev.md` 文件存在但工具报 `Subagent "backend-dev" not found`，加 `subagent_path` 显式指定仍失败，工具仅暴露内置只读的 `code-explorer`）。已按门禁硬规则 #2 停下并记录：**阻塞：Task07 未执行（原因：本会话无法分派 backend-dev 子代理）**；按硬规则 #3，改动含 `.py` 时**禁止主会话代行**，故未自行实现。已备妥可直接执行的 task 文件，待用户豁免代行或换用可调用子代理的环境后继续 |
| 2026-09-12 | 架构师(自身) | 新缺陷：从「模型库」等视图点「新建对话」不切回对话视图。经 grill with docs 定位：`beginDraft()`（`app.js:1102-1110`）只重置会话内容、**从不调用 `showView()`**，而视图切换靠原生 `hidden` 属性（`app.js:2831-2836`），故 `#chat.hidden` 一直为 `true`；`openConversation()` 首行即有 `showView('chat')` 可作对照。追加第 4 批 **BUG-06**（仅前端）。用户确认边界：改 `beginDraft()` 内部（覆盖 `1589`/`1651`/`1170` 三个调用点）、本次只修这个 bug、顺手统一「新会话」→「新对话」、按 AGENTS.md 分派子代理 |
| 2026-09-12 | `frontend-dev` + `frontend-tester`（架构师(自身)编排） | 实施并验收 BUG-06：① `app.js:1103` 前置于 `beginDraft()` 首行；② 7 处「新会话」→「新对话」；③ `index.html:492` `app.js?v=33`→`?v=34`、491 行兼容注释追加 `v33`。验收：`node --check` OK、前端契约 pytest **35 passed / 0 failed**、`grep "新会话"` 0 命中；架构师另用 Playwright+Chromium 在 8300 做真实点击验证——模型库 → 新建对话后 `#chat.hidden=false`、`#models-view.hidden=true`、`activeNav=['chat']`、`page_errors=[]`、加载 `app.js?v=34`。**未跑全量回归**（单端改动，按规则只跑前端回归）。详见 `reviews/020-acceptance-review.md` 第 4 批段 |
| 2026-09-11 | 架构师(自身)（**主模型代行**） | 用户豁免代行后实施 Task07：① `manifest_store.py` 新增 `_is_empty_library()` / `_bootstrap_empty_generation()`，`require_generation()` 增加 `allow_bootstrap` 参数（**默认 `False`**，保证启动/状态/检查清单等读路径零副作用）；② `routes_kb.py` `_require_generation()` 透传该参数，**仅上传端点** opt-in `allow_bootstrap=True`；③ 新增 `tests/test_kb_empty_generation_bootstrap.py` 5 条定向测试。**未改 `main.py`**（默认即只读，天然满足既有启动只读测试）。同步按授权变更更新冻结清单 `upload-closure-matrix.json`（`routes_kb.py` sha256 与 `inventory_digest`）。定向测试 **157 passed / 0 failed**；运行时实测：全新环境首次上传 **HTTP 201**（原 409）、启动不创建 `data/kb`、第二次上传无 503、测试文档已清理（`papers.json` 归零）。**未跑全量回归**（用户要求）。已完成代行三处留痕 |
