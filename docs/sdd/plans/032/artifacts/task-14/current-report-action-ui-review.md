# Spec032 Task14：报告显式动作前端独立评审

- 角色：`frontend-reviewer`
- 日期：2026-10-08（Asia/Shanghai）
- 范围：`frontend/research-tasks.js`、`frontend/index.html`、`tests/frontend/test_paper_issue_ui_contract.py` 最新 diff
- 日志：`.codebuddy/agent-logs/spec-032/task-14/frontend-reviewer/20261008-005932.md`
- 明确排除：后端业务代码、后端 pytest、真实登录/上传/报告生成、backend artifact/session/notification 接线

## 结论

**BLOCK：P1=1，P2=1。**

同一任务内的显式按钮、错误重试、旧报告状态保存、DOM/XSS 和资源缓存版本静态检查通过；但新增报告动作没有任务切换后的异步隔离，旧任务请求完成后可把报告和按钮状态写入当前新任务。报告版本选择器另有既存的失败回滚/请求竞态缺口，阻碍“旧版本可可靠切换”的完整签收。

此外，本次前端验证**没有证明 backend artifact、Session final message 或 notification 已接通**。UI 明确提示当前报告入口没有返回 canonical artifact/会话通知，不能把 `ResearchReport` POST 成功当作 Spec032 全链路完成。

## 发现

### [P1] 报告生成/上传响应缺少 task-generation guard，切换任务后会串写状态

相关位置：

- `frontend/research-tasks.js:1780-1840`：`generateReportVersion()` 只用全局 `state.acquisition.reportActionInFlight`，POST/JSON/Markdown 请求完成后没有再次确认 `state.selectedTaskId === taskId` 或 generation token。
- `frontend/research-tasks.js:1927-1937`：`uploadIssue()` 新增的 `report_action` 写回同样没有确认请求发起时的任务仍是当前任务。
- `frontend/research-tasks.js:2611-2629`：`selectTask()` 会把 `reportActionInFlight` 重置为 `false`、清空 `state.report`/`reportViews`，但不会取消旧 Promise 或提升 generation。

可复现的受控时序：

1. 打开任务 A，上传 issue 后点击“生成报告新版本”，让报告 POST 或 canonical GET 暂缓返回。
2. 切换到任务 B；`selectTask()` 清空报告并把全局 `reportActionInFlight` 设回 `false`。
3. 任务 A 的请求完成。`readGeneratedReportVersion()` 仍会写 `state.report`、`state.reportViews`、`reportFormat` 并重绘；`generateReportVersion()` 仍会写全局 `reportActionMessage/status`。

结果是任务 A 的报告可能显示在任务 B，且 B 的按钮可在 A 仍未收尾时再次发起动作。旧 upload 响应也可能把 A 的 `report_action` 按钮写入 B。报告/任务数据属于用户私有状态，该串写必须在放行前修复。

最小修复方向：为报告动作和 upload 关联请求捕获 task/generation token；每个异步响应、catch、finally 在写全局状态前验证 token，任务切换时递增 token/取消旧请求。不能只在按钮上禁用，因为任务切换已显式重置了当前 in-flight 标志。

### [P2] 版本选择失败没有事务式回滚，存在旧内容与新版本标签短暂/错误混合

`frontend/research-tasks.js:2829-2835` 的既有版本选择器在请求前就把
`state.report.report_version` 改成目标版本并清空 `reportViews`；canonical GET 或
随后 Markdown GET 失败时只写错误提示，不恢复此前版本。此时旧正文仍可能留在
`state.report.markdown`，但 UI 版本标签已经是用户刚选择的版本；连续快速切换时也
没有请求 generation 检查，晚到响应可以覆盖较新的选择。

这不是本轮新增 action 的生产代码 diff，但新动作会产生更多可切换版本，因此它是
“旧报告可读取且不可混淆”验收的剩余缺口。建议把目标版本读取成功后再一次性提交
`report`/`reportViews`/选择器状态，失败或过期响应恢复原版本。

## 逐项检查

| 检查项 | 结论 | 证据 |
|---|---|---|
| 显式新报告按钮 | 通过（同任务内） | upload 只保存 action 状态；按钮 click 才调用既有 `/reports` POST |
| Single-flight | 静态通过，跨任务不通过 | `reportActionInFlight` 可防同一任务双击；P1 race 可因 `selectTask()` 重置该标志而绕过 |
| POST 请求字段 | 通过 | 仅发送 `{"plan_version": planVersion}`，不发送 `report_version`/标题 |
| 返回字段读取 | 静态通过，未做真实 API 验证 | upload 读取 `report_action`/`research_task_ids`；POST 读取 `report_version`；canonical JSON 必须返回同版本 `report_version`；Markdown 必须为非空字符串 |
| 生成失败可重试 | 通过（静态） | POST 失败恢复 `available`；canonical/Markdown 读取失败保存版本并显示“重试读取” |
| 旧报告保持 | 同任务请求失败通过；版本切换存在 P2 | 新动作保存旧 `report`/views；既有 selector 失败不回滚 |
| DOM/XSS | 通过 | 新节点均 `createElement` + `textContent`；ID 用白名单和 `encodeURIComponent`；无新增 `innerHTML` |
| CSS/DOM 契约 | 通过 | `research-issue-item`、`research-issue-actions`、`secondary-button` 已有样式；按钮挂在既有 issue queue |
| 静态缓存刷新 | 通过 | `frontend/index.html` 从 `research-tasks.js?v=15` 升到 `?v=16` |

## Backend artifact 接线状态（本轮不签收）

`readGeneratedReportVersion()` 成功后把 `artifacts` 设为空数组并直接读取已有
versioned JSON/Markdown；成功提示也明确“当前入口未返回 canonical artifact 或会话
通知”。因此本轮只能证明前端消费了 `ResearchReport` 版本字段，不能证明：

- `/reports` POST 同时创建 `research_artifacts`；
- Session `final_message_id` 已更新；
- `research-report:{task_id}:{version}` activity/notification 已产生；
- 上传的新全文已经经过既有 EvidenceUpgrade/ClaimEvidence 进入新报告。

这些属于 backend/application 接线和真实 API E2E，超出本次 frontend-reviewer 范围；在独立 backend 证据补齐前，Spec032 全链路仍不可签收。

## 定向验证

未运行后端 pytest、未启动服务、未执行真实上传/登录/报告 POST：

```text
.venv/bin/python -m pytest -q \
  tests/frontend/test_paper_issue_ui_contract.py \
  tests/frontend/test_evidence_report_frontend_contract.py \
  tests/frontend/test_acquisition_progress_contract.py
12 passed in 0.21s

node --check frontend/research-tasks.js
exit 0

node tests/frontend/test_research_report_notifications.js
Task08 frontend contract: PASS (artifact allowlist, safe URLs, notification states, cursor de-duplication)

node tests/frontend/test_research_session_workspace.js
Task09 frontend/Fake-DOM contract: PASS

git diff --check -- frontend/research-tasks.js frontend/index.html tests/frontend/test_paper_issue_ui_contract.py
exit 0
```

新增 Python 契约主要是源码静态断言，未覆盖 P1 跨任务异步竞态、真实双击
single-flight、版本切换失败回滚或 backend 返回字段/产物。未修改任何业务代码，未提交 git。

## 独立复审追加（2026-10-08 01:18 CST）

### 复审结论

**原报告的 P1 跨任务报告动作串写和 P2 版本选择回滚/乱序缺陷已由最新 diff 关闭；本轮前端复审不再发现同等级的报告内容串写。** `tests/frontend/test_report_action_race.js` 的延迟响应合同通过，定向前端回归通过。该结论只覆盖前端状态隔离；backend artifact、Session final message、notification 以及真实上传/报告 E2E 仍未验证，不能据此签收 Spec032 全链路。

### A/B 延迟 upload/generate 复核

- `selectTask()` 和空工作区切换都会递增 `state.taskGeneration`，同时失效进行中的 `reportVersionRequest`。
- `generateReportVersion()` 在 POST 返回、canonical JSON/Markdown 读取、catch 和 finally 写回前都检查发起时的 task/generation；切到 B 后，A 的响应只返回 `null`，不会提交 `state.report`、`reportViews`、版本列表或报告动作提示。
- `uploadIssue()` 捕获发起时 task/generation；`report_action`、返回任务 ID、按钮状态和成功/失败提示仅在仍处于同一任务时写入。其持有的旧 `issueActions` 集合也不会清理 B 的新集合。
- 复核了 ID 白名单（`[A-Za-z0-9._~-]{1,240}`）与 `encodeURIComponent` 路径边界，未发现通过任务 ID 把 A 的响应导向 B 的路径。

`test_report_action_race.js` 用真实模块和延迟 `fetch` 覆盖了 A 生成后切到 B、A 上传后切到 B 两个场景；断言旧响应不会产生 B 的报告按钮或 v2 缓存。

### 版本失败回滚与乱序复核

`selectReportVersion()` 现在保留旧正文/标签直到目标版本的 JSON 和 Markdown 都成功且版本号一致，再一次性提交；失败恢复旧 `report`、`reportViews` 和格式。每次选择递增 `reportVersionRequest`，并同时检查 task generation，因此 v2 的晚到响应不会覆盖随后选中的 v3。成功渲染引用和矩阵的延迟 paper-display 回调也使用同一 guard。

合同测试覆盖了 v2 读取失败回滚以及 v2/v3 快速选择；静态复核还确认 Markdown 第二次 GET 返回后仍有过期检查（测试本身主要让 v2 在 canonical 阶段失效）。

### 残余低风险状态串写（P2，非报告内容）

`frontend/research-tasks.js:1615-1637` 的 `loadAcquisitionStatus()` 成功路径会检查 `selectedTaskId`，但 catch 路径在 A 请求失败且用户已切到 B 时仍调用 `setAcquisitionStatus(..., 'failed')`。`uploadIssue()` 在 A 上传响应通过 guard 后会启动这次状态刷新（约 1966 行），因此“上传成功后状态刷新 500、期间切到 B”的受控时序仍可能把 A 的错误提示留在 B 的导入状态节点；它不改 `state.report`/报告按钮，属于 P2 UI 提示污染，不是本轮已关闭的 P1 报告串写。最新 race 合同没有覆盖该失败分支。最小后续修复是在 `loadAcquisitionStatus()` catch 写 DOM 前复用 task/generation guard，或让调用方传入 token；不应借机改 API 或状态模型。

### DOM、XSS 与缓存版本复核

- 新增报告动作和版本选择器均使用 `createElement`、`textContent`、数值版本和受限 ID；未新增 `innerHTML`，Markdown/HTML 仍走既有安全渲染边界。
- 报告动作 POST 只发送 `plan_version`，按钮是显式单飞；upload 不隐式生成报告，读取失败保留可重试版本。
- `frontend/index.html` live asset 已升到 `/assets/research-tasks.js?v=16`。

### 本轮验证

```text
.venv/bin/python -m pytest tests/frontend -q
244 passed in 0.57s

node tests/frontend/test_report_action_race.js
Report action race contract: PASS (task isolation, rollback, delayed response ordering)

node tests/frontend/test_research_report_notifications.js
Task08 frontend contract: PASS

node tests/frontend/test_research_session_workspace.js
Task09 frontend Session/Fake-DOM contract: PASS

node --check frontend/research-tasks.js
退出码 0

git diff --check -- frontend/research-tasks.js frontend/index.html tests/frontend/test_paper_issue_ui_contract.py tests/frontend/test_report_action_race.js
退出码 0
```

未运行后端 pytest、未启动服务、未执行真实登录/上传/报告 POST，也未修改业务代码或提交 git。一次无关的全量 frontend Node 文件枚举在既有 `tests/frontend/test_plan_approval_select.js` 处因 `../frontend/research-session-ui.js` 路径不存在而停止；本轮相关 Node 合同均单独通过，未将该既有测试路径问题归因于本 diff。
