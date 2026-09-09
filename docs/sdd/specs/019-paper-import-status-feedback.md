# 019 论文导入状态反馈一致性

> 用法：动手让 AI 写代码前，先和它一起把本 spec 填完整，并把实施工作拆到 `docs/sdd/plans/019/`。

## 状态

**当前状态：已完成**

> 2026-09-09 用户"处理吧"确认本 spec，遂转 `已确认` 并进入 `实施中`（Task02 开始）；
> Task02–05 全部完成、三份评审通过、运行时三类场景验收通过，转 `已完成`。
> 执行方式：主会话（架构师）主导编排，子代理调用 0.00 倍率 `hy3` 模型执行（实测可用）。
>
> 交付摘要：
> - 根因：单篇导入只查 `search_sessions`（catalog 检索恒空）→ 误报 `SEARCH_NOT_FOUND`；已回退 `search_jobs`，与批量路径同构。
> - 后端 5 处 `except Exception` 503 兜底 → 改 `logger.exception` + 424 `IMPORT_BATCH_ERROR`，`DATABASE_LOCKED` 保留 503 retryable。
> - 前端 `renderImportSummary()` 成为状态栏唯一入口；分组独立 try/catch；静默路径补反馈；`partial_success` 可区分；P1 计数累加器每轮重置。
> - 全量 786 passed；运行时单篇导入 `200 status=indexed`。
> - 遗留 P2 四项（非阻塞）见 [技术评审](../reviews/019-tech-review.md)。

## 一句话目标

让"添加到知识库"的整条链路只用**一个可信的状态来源**向用户表达进展：提交、进行中、部分成功、完成、失败各有确定且互不覆盖的表达；后端不再把未预期异常一律伪装成"导入服务暂时不可用"；点击"添加到知识库"时若检索上下文不可用，给出**可行动**的指引而非"搜索会话不存在"。

## 背景与证据（实测，2026-09-09）

1. **状态栏被多种语义覆写**：前端 `paperImportStatus` 同一节点被三处写入——单篇导入结果（`app.js:944`）、导入异常（`app.js:953`）、后台批次轮询进度（`app.js:1008`）。用户因此先看到"导入服务暂时不可用"，随后又被轮询改写为"导入完成"。
2. **分组循环一处失败即整体中断**：`importPaperCandidates`（`app.js:916-955`）按 `search_id` 分组循环提交，任一分组抛错即跳到外层 `catch`，`created` 中已创建批次不再启动轮询（`app.js:951` 被跳过），且错误文案覆盖已成功批次的状态。
3. **后端错误语义失真**：`routes_paper.py:697/724/743/762/841` 用 `except Exception` 兜底，一律返回 503 `IMPORT_BATCH_UNAVAILABLE`（"批量导入服务暂时不可用"，`retryable=true`）。真实异常被吞，用户被误导为"服务挂了"并反复重试。
4. **"搜索会话不存在"与事实不符**：实测 `data/paper_search/state.sqlite3` 中 `search_jobs` 全部 `expires_at` 未到期（状态 `partial`），`search_sessions` 为空。即检索上下文**存在且未过期**，却仍报 `SEARCH_NOT_FOUND`（`routes_paper.py:605/654`，前端 `app.js:413` 映射为"搜索会话不存在，请重新检索"）。真实触发路径需 Task02 只读定位（候选 `search_id` 来源见 `app.js:920` `candidateSearchIds` / `candidate.search_id`）。
5. **静默失败**：`app.js:921`（`!searchId` 跳过）与 `app.js:925`（`!groups.size` 直接 return）在无法解析 `search_id` 时不给任何反馈，用户点击后毫无变化。

## 数据模型

| 字段 | 类型 | 约束（必填？范围？默认？）|
|---|---|---|
| 前端导入状态机 `importPhase` | 枚举字符串 | 必填；取 `idle`/`submitting`/`running`/`partial_success`/`completed`/`failed`；单一来源，禁止多处直接写 DOM 文本 |
| 每批次独立状态 `batches: Map<batch_id, {state, error_code, updated_at}>` | 映射 | 必填；已有 `paperState.batches`，需补全终态与错误码 |
| 汇总视图（由各批次聚合） | `{total, completed, failed, waiting_login}` | 必填；终态汇总后才写状态栏，避免逐条覆盖 |
| 后端导入错误响应 `error.code` | 字符串 | 必填；禁止用 `IMPORT_BATCH_UNAVAILABLE` 兜底未预期异常，改为记录并返回 `IMPORT_BATCH_ERROR`（424）或显式 500 |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况（状态码）|
|---|---|---|---|
| `POST /api/papers/imports`（批量） | `{search_id, candidate_ids, idempotency_key?}` | 200 批次负载（`batch_id` + `items`） | 400 `BATCH_LIMIT_EXCEEDED`；404 `SEARCH_NOT_FOUND`；400 `SEARCH_EXPIRED`；400 `CANDIDATE_NOT_FOUND`；400 `SEARCH_NOT_READY`；**424 `IMPORT_BATCH_ERROR`**（原 503 兜底改为可诊断错误，不谎报"服务不可用"） |
| `POST /api/papers/imports`（单篇兼容形态） | `{search_id, candidate_id}` | 200 单篇结果（`status`/`paper_id`/`existing`） | 同上 |
| `GET /api/papers/imports/{batch_id}` | 路径 `batch_id` | 200 批次负载 | 404 `BATCH_NOT_FOUND`；**424**（原 503 兜底） |
| `POST /api/papers/imports/{batch_id}/retry` | 路径 `batch_id` | 200 批次负载 | 404 `BATCH_NOT_FOUND`；**424**（原 503 兜底） |

## 边界（每条之后会变成一条测试）

- 多选候选分属 **多个 `search_id`**：必须逐组独立提交，一组失败**不影响**其余组，且失败组单独呈现原因。
- 导入中**部分成功**（`partial_success`）：状态栏必须同时给出成功数与失败数，不得只显示"完成"。
- 同一批次**并发轮询**：状态栏只在汇总终态时更新一次，禁止逐条覆写导致"先错后成对"。
- 检索上下文**存在但未就绪**（`SEARCH_NOT_READY`）：提示"结果正在整理，请稍后重试"，与"不存在"区分。
- 检索上下文**已过期**：提示"搜索会话已过期，请重新检索"，与"不存在"区分。
- 后端**未预期异常**：不得返回 `IMPORT_BATCH_UNAVAILABLE`；必须落日志并返回带可诊断 code 的 424/500。
- 无法解析 `search_id`（静默跳过路径）：必须给出可见反馈，禁止无响应。
- 重复点击导入：由 `inFlightImports` 去重，不得产生重复批次或覆盖状态。

## 明确不做（划出范围，防 AI 自由发挥）

- 不改 `paper_import_batch_store.py` 的 CAS 状态机与并发领用语义。
- 不改 USENIX/DBLP 检索来源与下载安全策略（`_peer_from_response`、allowlist、对端复核）逻辑。
- 不新增导入方式（不做"一键导入全部/导入整个检索结果"）。
- 不动 `search_jobs`/`search_sessions` 的过期时间策略与清理机制（Task02 只做只读定位，不调整有效期）。
- 不重构前端整体架构（不引入框架/构建），仅在现有无构建静态站范围内收敛状态表达。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 以下为基于用户实际反馈的初稿，`doc-updater` 在确认后补写完整用户旅程。

- 步骤 1：用户检索论文，勾选若干候选，点击"添加到知识库"。
- 步骤 2：状态栏进入"正在导入 N 篇"，逐条展示每篇/每批次进展，不出现相互矛盾的文案。
- 步骤 3：全部完成后状态栏给出确定结论：N 篇成功；若有失败，同时给出失败篇数与原因（可行动）。
- 步骤 4：若检索上下文不可用（未就绪/已过期/不存在），点击后给出**对应且可行动**的提示，而不是"搜索会话不存在"这一笼统说法。
- 验收场景：
  1. 选中跨两个 `search_id` 的候选且其一失败：另一组照常完成，界面同时显示"1 篇成功、1 篇失败（原因）"，**不出现先报错后完成**。
  2. 在检索 job 仍有效时点击导入：不再报"搜索会话不存在"。
  3. 后端抛未预期异常：返回可诊断 code 并落日志，前端不显示"导入服务暂时不可用"。

## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 / 文档更新 | `qwen3.5:9b`（本地 Ollama，`doc-updater`） | 32k | `Task(doc-updater)` | 补写产品使用步骤、用户旅程与验收场景 |
| 后端开发 | `qwen3.8:27b-mlx`（本地 Ollama，`backend-dev`） | 32k | `Task(backend-dev)` | 只改 `backend/**`：导入错误语义与日志 |
| 前端开发 | `qwen3.8:27b-mlx`（本地 Ollama，`frontend-dev`） | 32k | `Task(frontend-dev)` | 只改 `frontend/**`：状态机与汇总展示 |
| 后端评审 | `qwen3.8:27b-mlx`（`backend-reviewer`） | 32k | `Task(backend-reviewer)` | 只评 `backend/**` |
| 前端评审 | `qwen3.8:27b-mlx`（`frontend-reviewer`） | 32k | `Task(frontend-reviewer)` | 只评 `frontend/**`（DOM 契约/`?v=N`/XSS） |
| 后端回归 | `qwen3.5:9b`（`backend-tester`） | 32k | `Task(backend-tester)` | 只跑后端 pytest |
| 前端回归 | `qwen3.5:9b`（`frontend-tester`） | 32k | `Task(frontend-tester)` | 前端契约/静态核对 |
| 验收总控 | `qwen3.5:9b`（`tester`） | 32k | `Task(tester)` | 跨端验收与报告 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-019 | 本文件 | — | 完成 |
| 02 | 只读定位"搜索会话不存在"真实触发路径 | [`task-02-diagnose-search-id.md`](../plans/019/task-02-diagnose-search-id.md) | 01 | 待执行 |
| 03 | 前端导入状态反馈统一（单一状态源） | [`task-03-unify-import-status.md`](../plans/019/task-03-unify-import-status.md) | 02 | 待执行 |
| 04 | 后端导入错误语义修正（消除 503 兜底） | [`task-04-backend-error-semantics.md`](../plans/019/task-04-backend-error-semantics.md) | 02 | 待执行 |
| 05 | 评审、部署与复盘 | [`task-05-review-deploy-retro.md`](../plans/019/task-05-review-deploy-retro.md) | 03,04 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/019-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/019-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/019-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-09 | 架构师(自身) | 编写本 spec：基于用户"先报导入暂不可用、后显示导入完成；点添加到知识库报搜索会话不存在"的连贯性反馈，实测定位三类根因（状态栏多语义覆写、分组循环中断、后端 503 兜底掩盖） |
