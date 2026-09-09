# 020 零碎 bug 解决

> 用法：不便单独立项的小型缺陷统一收进本 spec，按**批次**记录现象、根因、修复与验收；修完即走，避免为每个小 bug 重复走完整立项流程。

## 状态

**当前状态：已完成**

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

## 数据模型

| 字段 | 类型 | 约束 |
|---|---|---|
| `paperState.pendingGroups` | number | 必填；导入开始即置为待提交分组数，提交阶段文案取此值，不得为 0 |
| `paperState.importPhase` | 枚举 | 沿用 `idle/submitting/running/partial_success/completed/failed` |
| 批次卡片非终态表达 | DOM class + CSS 动画 | 非终态带进行中动画，终态移除（作用域限定 `#papers-view`） |
| 论文 `chunkers.v2.status` | 枚举 | 导入后 `pending → indexing → indexed`/`failed`，与上传一致 |

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

## 明确不做（防范围蔓延）

- 不改 v1 索引逻辑、spec-012 双版本检索语义与召回归并规则。
- 不改上传路径（`routes_kb.py`）现有行为。
- 不新建独立线程池；不在导入响应中同步等待 v2。
- 不改导入 CAS 状态机、并发领用与租约；不改下载安全策略。
- 不引入前端框架/构建；不新增/更名现有 DOM id。

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-020（零碎 bug 容器） | 本文件 | — | 完成 |
| 02 | 前端即时反馈与批次卡片动画 | [`task-02-frontend-live-feedback.md`](../plans/020/task-02-frontend-live-feedback.md) | 01 | 待执行 |
| 03 | 导入补齐 v2 异步索引 | [`task-03-v2-index-for-imports.md`](../plans/020/task-03-v2-index-for-imports.md) | 01 | 待执行 |
| 04 | 评审、部署与复盘 | [`task-04-review-deploy-retro.md`](../plans/020/task-04-review-deploy-retro.md) | 02,03 | 待执行 |

## 执行配置

> 沿用用户 2026-09-09 指定：主会话（架构师）主导编排，子代理调用 0.00 倍率 `hy3` 模型执行（spec-019 实测可用）。

| 角色 | 模型 | 上下文 | 分派 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（不写死代号） | 200k | 主会话 | spec 维护、技术决策、落地校验 |
| 后端开发 | `hy3` | 32k | `Task(backend-dev)` | 只改 `backend/**`（BUG-02） |
| 前端开发 | `hy3` | 32k | `Task(frontend-dev)` | 只改 `frontend/**`（BUG-01） |
| 后端/前端评审 | `hy3` | 32k | `Task(*-reviewer)` | 只评各自端 |
| 回归 | `hy3` | 32k | `Task(*-tester)` | 单端回归 |
| 验收总控 | `hy3` | 32k | `Task(tester)` | 跨端验收与报告 |

## 评审记录

- 需求评审：`docs/sdd/reviews/020-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/020-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/020-acceptance-review.md`（待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-10 | 架构师(自身) | 按用户"就放进 spec，统称为零碎 bug 解决"的要求，建立本容器 spec；纳入第 1 批两项：BUG-01 导入即时反馈与 0 批次文案、BUG-02 导入未提交 v2 索引 |
