# 019 前端评审报告（task-03 统一导入状态单一来源）

- 评审角色：frontend-reviewer（只读，未改业务代码）
- 评审对象：`frontend/app.js`、`frontend/index.html`、`tests/test_frontend_paper_contract.py`
- 评审依据：spec-019、task-03 计划、实际 `git diff HEAD -- frontend/`、回归护栏（DOM 契约 / ?v=N / XSS / 无构建）
- 旁挂信息：工作树同时含 `backend/app/api/routes_paper.py`、`tests/test_paper_discovery_api.py` 改动（属 Task04，不在本评审范围内，仅做一致性交叉核对）

---

## 结论

**通过（Warning）**。四项硬契约全部 PASS，无 CRITICAL / P0。存在 2 个 P1（HIGH）状态泄漏问题，建议在合入前修复；不触发硬打回。

---

## 一、四项必守逐条核对

| # | 必守项 | 结果 | 核对依据 |
|---|--------|------|----------|
| 1 | DOM 契约（不新增/更名现有 id；JS 新 class 在 CSS 真实存在） | PASS | diff 未新增任何 `id=`；引用 `paperImportStatus/paperImportSummary/paperImportPanel/paperImportSelected/paper-results` 均已在 index.html 存在（行 214/216/210/198/201）；`setPaperStatus` 设置的 `is-running/is-completed/is-partial/is-failed` 均在 styles.css:848-851 且作用域 `#papers-view`（无全局污染） |
| 2 | 版本号 `?v=N` 同步递增 | PASS | index.html:7 `styles.css?v=19`、index.html:250 `app.js?v=19`；契约测试 `tests/test_frontend_paper_contract.py:89-92` 断言两处均为 `?v=19`（8 passed） |
| 3 | XSS（用户输入仅 textContent，禁 innerHTML 拼接） | PASS | `renderImportSummary` 经 `setPaperStatus` 用 `element.textContent = text`（app.js:888、983）；`paperImportSummary.textContent = ...`（app.js:946）；message 由固定映射 `PAPER_ERROR_TEXT[code]` 与数字拼接，无用户自由文本；改动区无 `innerHTML` 命中 |
| 4 | 无构建（不引入框架/依赖/构建工具） | PASS | diff 仅原生 JS/CSS/HTML，无新依赖/框架/打包 |

---

## 二、DOM 契约核对表（逐 id）

| id | index.html 存在 | app.js 引用 | 结论 |
|----|----------------|------------|------|
| `#paper-import-status` | 是（214） | `paperImportStatus`（343）；汇总唯一写入点 `setPaperStatus(paperImportStatus,...)`（983） | PASS |
| `#paper-import-summary` | 是（216） | `paperImportSummary`（344）textContent（946） | PASS |
| `#paper-import-panel` | 是（210） | `paperImportPanel`（342）`hidden=false`（1018/1024） | PASS |
| `#paper-import-selected` | 是（198） | `paperImportSelected`（341）监听器（1271） | PASS |
| `#paper-results` | 是（201） | 监听器（1271）；本 diff 未改动 | PASS |

> 结论：diff 未新增/更名任何 id，既有 id 引用关系完整 → DOM 契约 PASS。

---

## 三、评审重点逐项结论

1. **状态栏是否只在汇总终态写入一次？**
   - 是。原三处覆写已移除：单篇结果（原 944）、异常（原 953）、`renderPaperBatch` 内逐批覆写（diff `-1104` 两行）、`schedulePaperBatchPoll` 轮询 catch（diff `-1079` 改为记录 `lastImportError`）。唯一写入入口为 `renderImportSummary()`（910）→ `setPaperStatus()`（983）。提交末尾调用（1044 后 `renderImportSummary()`），轮询终态调用（`schedulePaperBatchPoll` 1067-1071）。
   - 例外：登录子流程 `paperLogin`/`paperResume`（1178/1179/1189）仍直写 `paperImportStatus.textContent`。属 Task04/受控登录范围，task-03 计划明确"故意保留"，非本次根因 → **可接受（范围外）**，但单一来源不变量在登录子流程并发时不成立，建议 Task04 收敛。

2. **分组失败是否不影响其余组？失败原因是否可见？**
   - 是。各组独立 `try/catch`（1026-1043），单组抛错 push 到 `failedGroups`（`{search_id, candidate_ids, code}`），不中断其余组；任一成功即 `schedulePaperBatchPoll()`（1044）。失败原因在 `renderImportSummary` 经 `PAPER_ERROR_TEXT[g.code]` 聚合显示（962/969）。可见、可行动。

3. **静默路径提示文案是否清晰可行动？**
   - `!searchId`：计数 `skippedImports`（1010-1011）；`!groups.size` 时 `renderImportSummary` 显示"未能确定该论文所属检索，请重新检索后再导入"（'failed' 分支 skipped 子句 971-972）。`!searchId` 与 `!groups.size` 组合场景在 `completed` 分支附加"；N 篇未能确定所属检索"（960）。文案清晰、可行动 → PASS。

4. **`partial_success` 与 `completed` 是否区分？**
   - 区分明确。`completed`：文案"导入完成：X 篇成功"+ `is-completed`（#45BA77）；`partial_success`：文案"导入部分完成：X 篇成功，Y 篇失败（原因）"+ `is-partial`（#b26a00）。由 `totalSuccess>0 && totalFailed>0` 判定（928-929）。PASS。

5. **是否越界改后端接口/错误码映射？**
   - 前端 diff（`git diff HEAD -- frontend/`）仅含 `app.js` 与 `index.html`，**未改后端**。
   - 工作树内含 `backend/app/api/routes_paper.py`、`tests/test_paper_discovery_api.py` 改动（Task04：503→424 `IMPORT_BATCH_ERROR` + 日志、`SEARCH_NOT_READY`/`SEARCH_NOT_FOUND` 修正），由 backend-reviewer 评审。
   - 交叉核对：前端新增依赖的 `error.code`（`IMPORT_BATCH_ERROR`/`SEARCH_NOT_READY`/`SEARCH_EXPIRED`/`CANDIDATE_NOT_FOUND`）均在 `PAPER_ERROR_TEXT`（415-429）存在，映射一致，无耦合冲突。

---

## 四、发现的问题

### P0（CRITICAL）：无

### P1（HIGH）
- **P1-1 状态泄漏：`paperState.directSuccess` 未在 `importPaperCandidates` 起始重置**
  - 位置：`frontend/app.js:1014-1016` 仅重置 `skippedImports/failedGroups/lastImportError`，遗漏 `directSuccess`（初值 388，累加点 1041 `paperState.directSuccess += 1;`）。
  - 后果：同一会话重复点击"添加到知识库"，`directSuccess` 跨次累加，汇总成功数虚高。
  - 修复建议：在 1014-1016 处补 `paperState.directSuccess = 0;`。
- **P1-2 状态泄漏：`paperState.batches`（Map）全程不清空，汇总聚合旧批次**
  - 位置：`renderImportSummary` 聚合 `const batches = [...paperState.batches.values()];`（912）；`paperState.batches` 无 `.clear()`/重赋值（仅 `set` 于 1039/1080/1130/1188）。
  - 后果：重复导入时旧批次仍计入汇总，`total/completed/failed` 虚高，可能误判为完成。
  - 修复建议：在 `importPaperCandidates` 起始重置批次集合（注意 `paperLogin`/`paperResume` 会向同一 Map push，需确认清空不会误伤在途批次；或改为仅按当前导入的 `created` batch_id 集合聚合）。
  - 严重度说明：spec 明确要求"界面同时显示成功/失败数量"，single-source 汇总必须反映本次操作，累积计数直接违背"一致反馈"目标；但单次导入（验收场景）不受影响，故定为 P1（HIGH）而非 P0。

### P2（LOW）
- **P2-1 `submitting` 相位实际不可见**：`setImportPhase('submitting')` 后未立即渲染，`renderImportSummary` 仅在提交结束后调用，此时已非 submitting（running/终态），"正在提交 N 个导入批次…"文案基本失效。建议提交前调用一次 `renderImportSummary()` 或在首个批次创建后即时渲染。
- **P2-2 登录子流程**（1178/1179/1189）仍直写 `paperImportStatus.textContent`，破坏单一来源；范围外（Task04），建议后续收敛。
- **P2-3 批次内逐条 item 失败原因**（`item.error_code`，`renderPaperBatch` 1114 显示于批次行）未聚合进顶部汇总文案，仅显示失败计数 + 提交阶段/轮询错误原因。与 spec"失败篇数与原因"略有差距，但批次行已可见，可接受。

---

## 五、Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 2     | warn   |
| MEDIUM   | 0     | info   |
| LOW      | 3     | note   |

Verdict: **WARNING** — 2 个 HIGH（P1）状态泄漏问题建议在合入前修复；四项硬契约全 PASS，不触发硬打回。

---

## 六、产出与回传

- 结论：通过（Warning）
- P0 问题数：0
- 评审文件路径：`docs/sdd/reviews/019-frontend-review.md`
- 日志路径：`.codebuddy/agent-logs/spec-019/task-05/frontend-reviewer/20260910-001615.md`
- 自检复核：`node --check frontend/app.js` 通过；`tests/test_frontend_paper_contract.py` 8 passed（task 自报，未在本评审重跑 pytest）
