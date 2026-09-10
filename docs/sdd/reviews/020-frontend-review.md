# spec-020 / Task02 前端评审（BUG-01 即时反馈与批次卡片动画）

> 评审角色：frontend-reviewer（只读，只评 `frontend/**`）
> 关联：spec-020 `020-misc-bug-fixes.md` BUG-01；task-02 `task-02-frontend-live-feedback.md`

## 结论

**通过（Approve）** — 无 P0、无 P1；1 处 P2（边角场景，不阻塞合入）。

## 评审范围

- `frontend/app.js`：新增 `pendingGroups` 字段（391）；`importPaperCandidates` 在 `setImportPhase('submitting')` + 面板展开后**立即** `renderImportSummary()`（1033），导入开始置 `pendingGroups = groups.size`（1020）；`renderImportSummary` 提交文案改用 `pendingGroups`（958），加守卫（946）；`renderPaperBatch` 非终态卡片加 `is-progressing`（1109）。
- `frontend/styles.css`：新增 `@keyframes paperBatchPulse`（1243-1246）；作用域内规则 `#papers-view .paper-import-batch.is-progressing`（1241-1243）；`prefers-reduced-motion` 降级（1247-1249）。
- `frontend/index.html`：`?v=20 → ?v=21`（第 5、250 行）。
- `tests/test_frontend_paper_contract.py`：版本断言 21（91-92）；新增 `test_paper_submit_feedback_uses_pending_groups`（117-128）、`test_paper_import_batch_progress_indicator`（131-134）。

## 逐项核对表

| # | 评审重点 | 结论 | 依据（文件:行） |
|---|---|---|---|
| 1 | 即时反馈：setImportPhase('submitting') 后立即 renderImportSummary() | PASS | app.js:1031→1032→1033 连续调用；renderImportSummary 经 setPaperStatus 同步写入 paperImportStatus（988），点击即重绘文案 |
| 2 | 计数口径：pendingGroups=groups.size；文案取它；任何路径 N≥1 | PASS | 赋值 app.js:1020；取用 958；1025 早返回（groups.size 为 0 走 failed）保证进入 submitting 时 groups.size≥1 → pendingGroups≥1 |
| 2a | 守卫"防 skipped 误判 failed"是否正确 | PASS（含 P2 副作用，见下） | 守卫 app.js:946 `paperState.importPhase !== 'submitting'` 正确；提交进行中即使 skipped>0 也不会翻 failed |
| 3 | 卡片动画：非终态加 is-progressing、终态移除；作用域 + 降级 | PASS | 非终态 toggle app.js:1109 `!paperBatchTerminal(batch)`；renderPaperBatch 在创建(1048)与轮询更新(1089)均调用 → 终态自动移除；CSS 作用域 styles.css:1241；降级 1247 |
| 4 | 单篇直成功 / 跳过场景各有可见反馈 | PASS | 跳过（全）：1025-1029 走 failed，文案 977「未能确定该论文所属检索…」；跳过（部分）：守卫防误判，终态 completed/partial 文案含 skipped（964）；直成功：1050 directSuccess++，终态 completed 文案（963-964） |
| 5 | 去重：重复点击不增批次、计数不翻倍 | PASS | inFlightImports 逻辑未动（1037-1038、1056）；pendingGroups 为确定性 `groups.size`，重置亦同值，计数不翻倍 |
| 6 | 四项必守 | 全 PASS | 见「四项必守」小节 |

## 四项必守

| 必守项 | 结论 | 核对依据 |
|---|---|---|
| DOM 契约（无新增/更名 id） | PASS | 仅新增 class `is-progressing`；app.js:1109 使用，styles.css:1241/1247 定义；Grep `is-progressing` 双向一致（3 处命中），无新增/更名 id |
| `?v=N` 同步递增且契约测试断言一致 | PASS | index.html 第 5、250 行均 20→21；test 91-92 断言 `/assets/app.js?v=21` 与 `/assets/styles.css?v=21`，一致 |
| XSS（无 innerHTML 拼接用户输入） | PASS（限本次 diff） | 本次改动仅 `classList.toggle`（1109），无 innerHTML；既有 innerHTML（10/118/129/139/188/248/293/1552）为静态模板或经 renderMarkdown 净化（1509 注释），未改动且非 CRITICAL，不在本评审范围 |
| 无构建 | PASS | 纯原生 JS/CSS/HTML，无打包/框架引入 |

## 问题清单（按 P0/P1/P2）

### P0（阻塞）
无。

### P1（警告）
无。

### P2（建议，不阻塞）
- **P2-1 全提交失败场景卡在 submitting 文案**
  - 现象：当所有提交请求失败（`created.length === 0` 且无 `directSuccess`）时，提交循环结束后 `importPhase` 仍为 `'submitting'`；守卫（946）因 `importPhase !== 'submitting'` 为假不翻转终态，且 `created.length === 0` 不触发 `schedulePaperBatchPoll`（1059），面板永久显示「正在提交 N 个导入批次…」而非失败态。
  - 根因：守卫在修复「skipped 误判 failed」的同时，把「全部提交失败」这一边角也挡在了 failed 之外；该分支无轮询兜底。
  - 文件：`frontend/app.js:946`、`frontend/app.js:1059-1060`
  - 建议：提交循环结束后，若 `created.length === 0 && !paperState.directSuccess`，显式将 `importPhase` 退出 `'submitting'`（如置 `'failed'`/`'idle'`）再 `renderImportSummary()`；或收窄守卫语义。
  - 严重度：低（需全部提交请求同时失败，罕见），不影响本次 BUG-01 验收，不阻塞合入。

## 验证命令结果

- `node --check frontend/app.js`：**通过**（exit=0）。
- `grep -n "?v=" frontend/index.html`：`app.js?v=21`、`styles.css?v=21`。
- 契约测试：据 task-02 回填为 **11 passed**（含 2 条新增）；本次逐条核对断言与实现一致（pendingGroups=groups.size / `正在提交 ${paperState.pendingGroups}` / `is-progressing` / `#papers-view .paper-import-batch.is-progressing` / `?v=21`）。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 1 (P2) | note |

Verdict: APPROVE — 无 CRITICAL/HIGH 问题，1 条 LOW（P2）建议项不阻塞。
