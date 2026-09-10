> 关联：[spec-020 零碎 bug 解决](../../specs/020-misc-bug-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05；当前状态：`进行中`

# Task06 导入相位死锁与重试无反馈修复（BUG-04）

## 状态与一句话目标

`进行中`（用户 2026-09-10 确认 spec-020 第 2 批后启动）。修复"批次卡片显示失败、状态栏却永久停在'正在提交 1 个导入批次…'"的相位死锁，并让"重试失败项"从点击到结束全程可见。

## 背景与根因（含文件行号）

- **相位死锁**：`frontend/app.js:947` 的 else-if 链以 `paperState.importPhase !== 'submitting'` 作为进入 `failed` 的条件；而同一函数末尾 `setImportPhase(phase)`（`app.js:950`）会把计算结果写回 `paperState.importPhase`（`app.js:908-911`）。两者互锁 → 进入 `submitting` 后，只要本轮成功数为 0，就永远算不出 `failed`。
- **重试无反馈**：`app.js:1145-1152`（`重试失败项` 点击处理）先 `retry.disabled = true`，再 `POST /api/papers/imports/{batch_id}/retry`；成功分支只做 `renderPaperBatch(data)` + `schedulePaperBatchPoll()`，**不刷新状态栏汇总**；失败分支才 `renderImportSummary()`。
- **等待体感长**：后端 `retry_batch`（`backend/app/paper_discovery/application/paper_import_batch_service.py:434-439`）→ `run_batch`（418-428）在 HTTP 请求线程内同步跑完整批，实测本批 ~120s，期间前端不会有任何变化。
- 实测批次：`61621ad2-8725-4652-bcb3-42915ed68bfe`（state=failed，2 条 item 均 `KB_IMPORT_FAILED`；日志 `deploy/run-8123.log:41-44` 显示 1 次 imports + 3 次 retry 均为 200，但**没有任何 `GET /api/papers/imports/{id}` 轮询请求**）。

## 数据、配置与接口

- **不适用**：不改任何后端接口、不改 `backend/**`。
- 新增前端状态（spec-020 数据模型）：`paperState.submitInflight`（number，未返回的提交/重试请求数）、`paperState.retryingBatchIds`（Set，正在重试的批次）。
- 沿用既有符号：`renderImportSummary()`、`setImportPhase()`、`renderPaperBatch()`、`PAPER_ERROR_TEXT`、`paperBatchTerminal()`、`paperState.failedGroups`、`paperState.currentRoundBatchIds`。

## 实施步骤与文件边界

**文件边界**：只改 `frontend/app.js`、`frontend/index.html`（`?v=N` 递增）、`tests/test_frontend_paper_contract.py`（契约用例）。**不得改 `backend/**`**。

### 1. `frontend/app.js` — 相位判定去自我守卫

**(a)** `paperState`（约 391 行 `directImports: []` 旁）新增：

```js
  submitInflight: 0,
  retryingBatchIds: new Set(),
```

**(b)** `importPaperCandidates`（约 1010 行）：在每个分组请求发出前 `paperState.submitInflight += 1;`，在 `finally` 中 `paperState.submitInflight -= 1;`（必须保证成对，含 `continue` 的去重路径**不**进入计数——去重时被跳过不产生请求）。

**(c)** `renderImportSummary`（约 940-950 行）的相位计算改为以**事实**为依据，替换现 `paperState.importPhase !== 'submitting'` 守卫的写法：

```js
  let phase;
  if (paperState.submitInflight > 0) {
    phase = 'submitting';
  } else if (runningBatches > 0) {
    phase = 'running';
  } else if (totalSuccess > 0 && totalFailed > 0) {
    phase = 'partial_success';
  } else if (totalSuccess > 0) {
    phase = 'completed';
  } else if (totalFailed > 0 || skipped > 0) {
    phase = 'failed';
  } else {
    phase = 'idle';
  }
```

注意：不再读取 `paperState.importPhase` 参与判断；`setImportPhase(phase)` 只负责存值。

**(d)** `renderPaperBatch`（约 1107 行）的 batch 容器类名：

```js
  batchContainer.classList.toggle('is-progressing',
    !paperBatchTerminal(batch) || paperState.retryingBatchIds.has(batchId));
```

### 2. `frontend/app.js` — 重试全程可见

替换 `renderPaperBatch` 中的重试点击处理（约 1145-1152 行）：

- 点击后：`retry.disabled = true;` + `paperState.retryingBatchIds.add(batchId);` + 立即调用一次 `renderImportSummary()`（状态栏给出"正在重试 N 项…"，复用既有 `submitting` 文案口径或新增文案，但**不得**使用"正在提交 0 个…"）。
- 请求返回后（`finally` 保证）：`paperState.retryingBatchIds.delete(batchId);` → `renderPaperBatch(data)`（成功）→ `renderImportSummary()`（无论成败都要执行）。
- 失败分支：`retry.disabled = false;` 并写入 `paperState.lastImportError`，由 `renderImportSummary()` 给出带原因的结论。

### 3. 详细实施由 `frontend-dev` 落地

具体 diff 由 `Task(frontend-dev)` 产出，见下方「子代理分派」。

## 子代理分派

- 角色：`frontend-dev`（`hy3`，32k）。
- 最小上下文：本文件 + spec-020 §BUG-04 + `frontend/app.js` 的 `908-990`、`1010-1071`、`1107-1167` 三段行号范围。
- 单次范围：只改 `frontend/**`，≤2 个代码文件。
- 回传要求：先回传代码片段与验证结果，再回传说明；日志路径必给。
- 读回校验：主会话用 Read 确认 `app.js` 修改落位，再进入前端回归。

## 边界与明确不做

- 不改后端；不改 `renderImportSummary` 之外的状态写入点（状态栏仍由该函数单一出口写入，遵守 spec-019）。
- 不得引入框架/构建；不得新增或更名现有 DOM id。
- 重试期间不得重复创建批次、不得触发轮询风暴（复用既有 2.5s 间隔）。
- 不为所述后端同步执行问题做前端补偿（如本地假造进度）——那是 spec-021 的范围。

## 验收、风险与回滚

**验收**（可执行）：
1. `node --check frontend/app.js` 通过。
2. `python -m pytest tests/test_frontend_paper_contract.py -q` 通过。
3. 运行时：勾选 2 篇 → 全部失败 → 状态栏显示"导入失败：2 篇（论文导入失败）"，**不**出现"正在提交"。
4. 运行时：点击"重试失败项" → 1 秒内批次卡片进入进行中态且状态栏切到重试中；请求返回后卡片与状态栏同步刷新；失败时按钮恢复可用。
5. 运行时：部分成功场景仍显示"导入部分完成"，不回归 `partial_success`。

**风险**：`submitInflight` 计数若在异常路径漏减，会重现死锁 → 必须在 `finally` 中递减，并由审阅者逐条核对所有 return/continue 分支。

**回滚**：`git checkout -- frontend/app.js frontend/index.html` 回到任务 05 状态；BUG-04 纯前端，回滚无数据影响。

## 产出物、执行结果与变更日志

待执行后填写（真实命令、真实输出、改动文件与行数、日志路径）。
