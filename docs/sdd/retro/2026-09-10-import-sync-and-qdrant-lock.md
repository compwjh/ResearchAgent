# 复盘：导入"同步执行导致进度 UI 失效"与"本地 Qdrant 单实例限制被兜底掩盖"

> 时间：2026-09-10 ｜ 关联：spec-020（BUG-04）、spec-021（论文导入异步化与进度反馈）
> 触发：用户报告"批次 61621ad2 · 失败；点重试后提示'正在提交 1 个导入批次…'等待很久没反应"

## 现象与真实根因（三层，缺一不可）

| 层 | 现象 | 根因 |
|---|---|---|
| 前端 | 状态栏永久停在"正在提交 1 个导入批次…"，与卡片"失败"并存 | `app.js:947` 的 `paperState.importPhase !== 'submitting'` 守卫与 `setImportPhase` 写回**互锁**：进入 `submitting` 后只要本轮成功数为 0，永远算不出 `failed` |
| 前端 | 点"重试失败项"毫无反应 | 重试成功分支只 `renderPaperBatch` 不刷状态栏；无中间态；后端同步跑完整批（~120s），期间 UI 零变化 |
| 后端 | 导入失败且**不可诊断** | `data/kb/qdrant` 被**另一个同项目 uvicorn 实例独占**（本机另开客户端直接抛 `RuntimeError: ... already accessed by another instance`）；KB 写入/索引/查重全失败，被压成无差别 `KB_IMPORT_FAILED` |
| 架构 | "进度面板"物理上拿不到中间态 | `create_batch(auto_run=True)` / `retry_batch` 在 HTTP 请求线程内同步跑完整批 → POST 返回时批次已终态 → 轮询首 tick 即退出。日志佐证：3 次 retry 全部 200，但**没有任何 `GET /api/papers/imports/{id}`** |

## 关键判断

1. **UI 承诺的进度必须有异步后端支撑**。前端把"轮询 + 逐条状态"做齐了，但后端同步执行让轮询永远只看到终态。先补 UI 再补后端，用户只会看到一个更精致的空面板。
2. **本地 Qdrant 是单进程独占资源**（`deploy/start.sh` 注释已写明"同一目录不允许被多个进程同时打开"），但违反它时既不报错也不告警，只是把 KB 写入失败压成通用错误码 → 用户在完全无关的界面上承受后果。这类"环境约束"必须前置为**可诊断、可行动**的错误（本轮新增 `KB_STORAGE_LOCKED`），而不是兜底错误码。
3. **错误文案的可行动性是可测的**。"论文导入失败"和"知识库存储被另一个实例占用，请关闭其他服务实例后重试"对用户是两种世界：前者只能反复重试，后者一次就能自救。
4. **唯一索引冲突不是异常，是业务状态**。部分唯一索引 `import_item_title`（只覆盖活跃态）拒绝"重试一篇已在别的批次成功的论文"是**正确**的，错误的是把它兜底成 424 `IMPORT_BATCH_ERROR`。

## 流程经验

- **grill with docs 有效**：先按文档（spec-019/020）核对既有需求，再让用户拍板五项决策（执行模型 / 相位口径 / 重试粒度 / 是否纳入环境根因 / 归属），一次性收敛，避免边写边猜。
- **实测 > 推断**：`sqlite3` 直查批次表 + `ps` 找出第二个 uvicorn 实例 + 本机另开 Qdrant 客户端复现锁，三步就把"导入失败"从玄学变成确定性结论。
- **评审仍抓到真问题**：`frontend-reviewer` 打回的 P1（提交期间误显红色"导入未完成"）正是"移除乐观写相位"后的顺序陷阱——`submitInflight += 1` 必须先于 `renderImportSummary()`。
- **flaky 用例要在同轮清掉**：`test_create_batch_auto_run_returns_queued_without_finishing_any_item` 依赖后台线程时序，用"桩化 `submit_batch` + 捕获 Future"改为确定性后才允许回归通过。

## 遗留（不阻塞，已记录）

- **语义待评审**：失败/取消条目是否应释放 `import_item_title` 唯一性，以便"重新导入"而不必回原批次。本轮**只做冲突可读化**，索引语义未动（spec-021「明确不做」已圈定）。
- **INFO（backend-reviewer）**：进程重启且崩溃落在 submit 与 runner 启动之间的极小窗口，条目可能停在 `queued` 直至用户重试——属 process-local 快照设计的固有边界，已接受。
- **LOW×3**：`_is_storage_locked_error` 两处重复实现；`retry_item` 走整批 `run_batch` 需补不变量注释；模块级 executor 注释措辞不准。
