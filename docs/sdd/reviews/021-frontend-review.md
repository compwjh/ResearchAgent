# 前端评审报告 · spec-021/task-04 + spec-020/task-06（未提交改动）

- 评审范围：`frontend/app.js`、`frontend/index.html`、`tests/test_frontend_paper_contract.py`
- 分支：`fix/spec-015-paper-discovery-fixes`（工作树未提交）
- 评审角色：frontend-reviewer（只读，不改代码）
- 验证痕迹：`node --check frontend/app.js` 通过；`pytest tests/test_frontend_paper_contract.py` → 21 passed

## 结论：打回（1 个 P1 / HIGH 行为回归需修复）

四项必守全部 PASS，必查项 1/2/3/5/6/7 满足；但初始批量提交期间状态栏会误显红色"导入未完成"，与 BUG-04「状态栏准确可见」目标相悖，列为 P1，需修复后方可合。

---

## 四项必守（逐条 PASS/FAIL）

| # | 必守 | 结论 | 证据 |
|---|------|------|------|
| 1 | DOM 契约：新增/修改 class 须在 styles.css 真实存在 | PASS | 本次真正新增 class 仅 `paper-import-item-title`，`styles.css:1263` `#papers-view .paper-import-item-title` 存在。未新增/更名任何元素 id（`index.html` 仅改 `?v`）。注：`paper-import-batch-header` 在 `app.js:1147,1264` 使用但无 CSS 规则——该 class 在本次之前已用于 `renderPaperBatch`，非本 PR 引入，不计入新增回归。 |
| 2 | ?v=N 递增且两处一致 | PASS | `index.html` 中 `app.js?v=21→v=24`、`styles.css?v=21→v=24`（diff 一致），`tests/test_frontend_paper_contract.py` 已断言 `?v=24`。 |
| 3 | XSS：导入面板仅 textContent | PASS | `renderPaperBatch`(1141-1246) 与 `renderDirectImports`(1248-1289) 全部用 `createElement`+`textContent`/`setAttribute`。全文件 `innerHTML` 落点（10/118/129/139/188/248/293/1637/1680）均不在导入面板函数内。 |
| 4 | CSS 作用域：选择器限定本项目 | PASS | 新增 `paper-import-item-title` 规则位于 `#papers-view .paper-import-item-title`(1263)；导入相关 class 均带 `#papers-view` 前缀（`styles.css:1123,1233,1241,1250,1263,1277...`）。 |

---

## 必查项逐条结论（含文件:行号证据）

### 1. 相位判定是否真的去自我守卫 —— PASS
- `renderImportSummary()`（`app.js:920-1012`）：phase 完全由事实计算——
  - `app.js:948` `if (paperState.submitInflight > 0) phase='submitting'`
  - `app.js:950` `runningBatches>0 → 'running'`
  - `app.js:952-960` 终态判定分支（含 `app.js:956` `else if (totalFailed > 0 || skipped > 0) phase='failed'` 与 `app.js:958` `else phase='idle'`）
  - `app.js:961` `setImportPhase(phase)` **仅写不读**。
- grep 全文件 `importPhase`：`app.js:380`(定义)、`915`(函数)、`917`(写)、`1051`(写'failed')、`1055`(写'submitting')、`961`(写)。**无任何读取参与相位判定**。旧根因 `let phase = paperState.importPhase` 与 `importPhase !== 'submitting' && ...` 守卫已彻底删除（见 diff）。根因已消除。

### 2. submitInflight 计数是否成对 —— PASS
- 3 处 `+= 1`：`app.js:1063`(初始循环)、`1172`(单条重试)、`1201`(整批重试)。
- 对应 3 处 `-= 1` 均在 `finally`：`app.js:1088`、`1184`、`1212`。
- 去重路径：`app.js:1061` `if (paperState.inFlightImports.has(importKey)) continue;` 位于 `app.js:1063` `+= 1` **之前**，去重路径不计数。配对成立。

### 3. 重试/取消/单条重试的交互完整性 —— PASS（见 P1 旁注）
- **单条重试**：`app.js:1165-1190` — 点击即 `retryItem.disabled=true`(1170) → `retryingBatchIds.add`(1171) → `submitInflight+=1`(1172) → `renderPaperBatch`+`renderImportSummary`(1173-1174) → `fetch('/api/papers/import-items/${encodeURIComponent(item.item_id)}/retry',{POST})`(1177) → 成功 `batches.set`+`renderPaperBatch`+`schedulePaperBatchPoll`(1179)；`finally`(1182-1187) 删除 retryingBatchIds、`submitInflight-=1`、失败则 `renderPaperBatch(batch)`、并 `renderImportSummary`。URL 与契约一致。
- **整批重试**：`app.js:1196-1222` — 同构；URL `/api/papers/imports/${batch.batch_id}/retry`(1206)。`finally`(1211-1219) 恢复。
- **取消**：`app.js:1224-1244` — `cancel.disabled=true`(1231) → `fetch('/api/papers/import-batches/${encodeURIComponent(batch.batch_id)}/cancel',{POST})`(1233) → 成功 `batches.set`+`renderPaperBatch`(1235)；失败 `lastImportError`+`renderPaperBatch(batch)`(1238-1239)；末尾 `renderImportSummary()`(1242)。URL 与契约一致；仅在 `queued/waiting_login/failed` 态显示（1230）。
- 三处成功/失败均刷新 `renderImportSummary()`。

### 4. DOM 契约 —— PASS（见必守表 #1）

### 5. XSS —— PASS（见必守表 #3）

### 6. 不回归 spec-020 BUG-03 —— PASS
- `importPaperCandidates` 内已删除 `if (data.paper_id) jumpToKnowledgeBase(data.paper_id);`（`app.js:1074-1083` 改为 push 到 `paperState.directImports` 并 `renderDirectImports()`）。
- grep 确认 `importPaperCandidates`(1032-1095) 内无 `jumpToKnowledgeBase(`/`showView('kb')` 调用点（仅点击回调中存在）。
- direct 不伪造 `batch_id`：`directImports` 条目字段为 `candidate_id/paper_id/stored_name/existing`，无 `batch_id`（`app.js:1077-1082`、`renderDirectImports:1277-1286` 断言 `batch_id not in direct_fn`）。
- 导入完成不清空面板：`renderImportSummary()`(1094) 不清除 batches；`renderDirectImports()`(1093) 渲染直达成功论文。

### 7. 软提示不得谎报失败 —— PASS
- `app.js:1003-1010`：仅遍历非终态批次按 `updated_at` 阈值追加 `message += '（仍在导入，可离开此页）'`，**不修改 phase**；`slowSince` 仅记录、不进入相位计算区间（`app.js:948`→`961` 之间无 `slowSince` 引用，与契约测试 `test_paper_soft_import_hint_does_not_fail` 一致）。

---

## 问题清单

### [HIGH / P1] 初始批量提交期间状态栏误显红色"导入未完成"
- 文件：`frontend/app.js:1055-1057` 与循环体 `1063-1094`
- 现象：`importPaperCandidates` 在循环前 `setImportPhase('submitting')`(1055) 后立即 `renderImportSummary()`(1057)。此时 `submitInflight` 仍为 0，`renderImportSummary` 依据事实重算 → `phase='idle'`(958)，且因 `submitFailed=0/skipped=0/totalFailed=0` 落入 else 分支 `message='导入未完成'`、`kind='failed'`（红色，`app.js:986-997`）。循环体内不调用 `renderImportSummary()`，于是整个初始提交窗口（fetch 在途期间）状态栏持续显示误导性红色"导入未完成"。
- 根因：BUG-04 去掉了"读取 importPhase 决定相位"的自我守卫后，`app.js:1055` 的乐观 `setImportPhase('submitting')` 被 `renderImportSummary` 的事实重算覆盖，而初始提交又无在途渲染，导致"正在提交 N 个导入批次…"反馈在初始导入时丢失/变红。重试路径正常（点击回调里 `submitInflight>0` 时渲染，能看到"正在提交/正在重试"）。
- 修改建议（二选一，推荐其一）：
  1. 在循环体内 `paperState.submitInflight += 1;`(`app.js:1063`) 之后补一行 `renderImportSummary();`，使提交进行中显示"正在提交 N 个导入批次…"；并移除已无作用的 `setImportPhase('submitting')`(1055)。
  2. 或删除 `app.js:1055-1057` 三行，并将 `renderImportSummary()` 调用移到循环内每次提交前（保持 `submitInflight>0` 时渲染）。
- 置信度：~90%（行为回归，非崩溃/安全问题）。

### [LOW] `paperState.importPhase` / `PAPER_IMPORT_PHASES` / `setImportPhase` 成为只写死状态
- 文件：`frontend/app.js:913-918, 961`
- 现象：相位判定不再读取 `importPhase`，`setImportPhase` 仅写入无人消费的字段。
- 建议：确认无其它视图依赖后可清理（非阻断）。

### [LOW] `paperState.slowSince` 赋值但从未读取
- 文件：`frontend/app.js:1009`
- 现象：软提示逻辑只用局部 `slow` 变量，`slowSince` 未被任何代码使用（契约测试仅断言其存在）。
- 建议：接入真实用途或移除，避免死变量。

### [INFO] `paper-import-batch-header` 无 CSS 规则
- 文件：`frontend/app.js:1147, 1264`；`frontend/styles.css` 无对应选择器
- 现象：该 class 在 `renderPaperBatch` 与 `renderDirectImports` 均使用，但 `styles.css` 无 `#papers-view .paper-import-batch-header` 规则。**该 class 在本次之前已存在（旧 `renderPaperBatch` 即用），非本 PR 引入，不计入 DOM 契约回归。**
- 建议：后续统一补一条作用域内样式（如标题间距/字号），属体验优化，非阻断。

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 1     | warn   |
| MEDIUM   | 0     | info   |
| LOW      | 2     | note   |

Verdict: 打回 —— 1 个 HIGH(P1) 行为回归需修复：初始批量提交期间状态栏误显红色"导入未完成"（见上 [HIGH/P1]）。四项必守与必查 1/2/3/5/6/7 均 PASS；另 2 个 LOW、1 个 INFO 为可选清理项。

报告路径：`docs/sdd/reviews/021-frontend-review.md`
日志路径：`.codebuddy/agent-logs/spec-021/task-05/frontend-reviewer/20260910-203655.md`

---

# 复审结论（spec-021/task-05 P1 修复 · 仅针对本轮修复）

- 复审范围：`frontend/app.js` 的 P1 修复、`frontend/index.html` `?v` 递增、`tests/test_frontend_paper_contract.py` 新增 P1 回归断言。
- 复审角色：frontend-reviewer（只读，不改代码）。
- 验证痕迹：`node --check frontend/app.js` → `NODE_CHECK_OK`；`python3 -m pytest tests/test_frontend_paper_contract.py -q` → **22 passed**（上轮 21，本轮 +1 新增回归测试）。

## 复审结论：通过（Approve）

P1 的 7 条修复全部真实落盘，且未引入新回归（相位不再被读取参与判定、submitInflight 仍成对、状态栏无新增竞争写入点）。四项必守与必查项维持 PASS。

### 7 条修复逐条核对（文件:行证据）

| # | 声称修复 | 证据 | 结论 |
|---|----------|------|------|
| 1 | 移除 `importPaperCandidates` 内两处乐观 `setImportPhase` 写入 | `importPaperCandidates` 1032-1093 内无 `setImportPhase('submitting'|'failed')`；全文件 Grep `setImportPhase(` 仅 916(def)/918(写)/962(`setImportPhase(phase)` 变量调用) | PASS |
| 2 | 循环体内 `submitInflight += 1;` 之后补 `renderImportSummary()` | `app.js:1060` `paperState.submitInflight += 1;` → `app.js:1061` `renderImportSummary();`（顺序正确，+=1 在前） | PASS |
| 3 | 保留 `groups.size === 0` 路径可见失败反馈（"未能确定该论文所属检索，请重新检索后再导入"） | `app.js:1049-1052` 早期 return 块内 `renderImportSummary();`(1051) 在 `return;`(1052) 之前；`renderImportSummary` 因 `skipped>0` → `phase='failed'` → `app.js:993` 文案，非 idle/导入未完成 | PASS（未被误伤） |
| 4 | LOW-1：删除只写不读的 `paperState.slowSince` | 全文件 Grep `slowSince` **0 命中**；`paperState` 定义 370-395 无该字段；`renderImportSummary` 1004-1010 仅用局部 `slow` | PASS |
| 5 | LOW-2：`setImportPhase` 上方补注释"仅作状态留痕，不参与判定" | `app.js:914-915` 注释存在；Grep `importPhase` 仅 385(def)/914(注释)/918(写)，**0 处读取** | PASS（选保留+注释路径，已证 0 读取） |
| 6 | 版本号 `?v=24 → 25`（两处）并同步契约断言 | `index.html:7` `styles.css?v=25`、`index.html:250` `app.js?v=25` 两处一致；`test_paper_app_version_bumped` 断言 `?v=25` | PASS |
| 7 | 新增 P1 回归断言 `test_paper_submit_window_shows_submitting_not_unfinished` | `tests/test_frontend_paper_contract.py:148-201`，含 5 项断言（乐观写消失 / +=1 后紧接 render / 早期 return 与循环间无渲染 / submitting 文案 / 轻量状态机模拟） | PASS |

### 反引入检查（复审要求）

- **`importPhase` 若仍被读取参与判定 → 打回**：全文件 `importPhase` 仅定义(385)与写入(918)，`renderImportSummary` 相位完全由事实重算（949-961），无任何读取参与判定。PASS，不构成打回。
- **`submitInflight` 出现不成对 → 打回**：`+=1` 三处（1060/1170/1199）与 `-=1` 三处（1086/1182/1210）均成对，且减操作均在 `finally`；去重 `continue`(1058) 位于 `+=1`(1060) 之前，去重路径不计数。PASS，不成对风险消除。
- **状态栏出现多写入点 → 打回**：`importPaperCandidates` 内状态栏写入仅 1051(早期 return)、1061(每批提交前)、1092(循环结束) 三处，语义清晰、无竞争写点；旧的乐观写相位 + 提前渲染组合已删除。PASS。

### 四项必守（逐条 PASS/FAIL）

| # | 必守 | 结论 | 证据 |
|---|------|------|------|
| 1 | DOM 契约 | PASS | 本轮未新增/更名任何 class 或 id（`app.js` 仅调整调用顺序，未引入新钩子）；无需在 `styles.css` 新增规则。 |
| 2 | ?v=N 递增且两处一致 | PASS | `index.html:7,250` 均为 `?v=25`；`test_paper_app_version_bumped` 断言通过。 |
| 3 | XSS | PASS | 导入面板（`renderPaperBatch`/`renderDirectImports`/`renderImportSummary`）仍只用 `textContent`/DOM API；全文件 `innerHTML` 落点（10/118/129/139/188/248/293/1635/1678）均不在导入面板路径，本轮无新增拼接。 |
| 4 | CSS 作用域 | PASS | 本轮未改动 `styles.css`，未新增全局/裸标签选择器。 |

### 问题清单

- 无 CRITICAL / HIGH / MEDIUM / LOW 新问题。上轮 P1 已修复；上轮 2 个 LOW（slowSince、importPhase 留痕）本轮已一并清理，INFO（paper-import-batch-header 无 CSS）非本 PR 引入、非阻断，维持原建议。

## Review Summary（复审）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 0     | pass   |

Verdict: 通过（Approve）—— P1 与附带 2 个 LOW 已全部真实落盘，验证全绿（node --check OK；pytest 22 passed），四项必守 PASS，无新引入回归。可合。

报告路径：`docs/sdd/reviews/021-frontend-review.md`
日志路径：`.codebuddy/agent-logs/spec-021/task-05/frontend-reviewer/20260910-210051.md`
