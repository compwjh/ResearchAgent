# Spec032 Task14：报告新版本显式动作前端修复

> 角色：frontend-dev  
> 时间：2026-10-08（Asia/Shanghai）  
> 分支：`codex/spec032-final-acceptance`  
> 状态：**实现完成，等待独立前端评审与重新部署验证**

## 范围与依据

本轮只读取并复用 `current-report-recovery-plan.md`、Spec032 的“修复后提示用户生成新版本、旧报告不变”语义，以及既有 `routes_paper` upload 和 `routes_research` report 接口契约。没有修改 backend、`.env`、下载/导入安全链，也没有创建或批准研究任务。

## 实际改动

1. `frontend/research-tasks.js`
   - upload 成功且返回 `report_action="generate_new_version"` 时，保存返回的 `research_task_ids`，继续只显示提示；`uploadIssue()` 本身没有报告 POST。
   - 在现有 issue action 区渲染显式“生成报告新版本”按钮。按钮单飞，生成/读取期间禁用；成功后显示已生成版本，读取失败显示可重试按钮，失败消息明确“旧报告保持不变”。
   - 点击按钮才调用既有 `POST /api/research-tasks/{task_id}/reports`，请求体只发送 `{"plan_version": ...}`，不发送 `report_version`、标题或新增字段。
   - 使用响应中的 `report_version` 读取既有 canonical JSON/Markdown 路由 `/api/research-tasks/{task_id}/reports/{version}?format=...`，校验返回版本一致且 Markdown 非空后更新当前视图，并把新版本并入已有版本选择器；旧版本仍通过原版本 GET 选择和读取。
   - POST 或 canonical 读取失败时恢复此前的 `state.report`、版本列表、视图缓存和格式，不调用会清空旧报告的 `loadReport()`。成功提示明确当前入口没有返回 canonical artifact 或会话通知，不把缺失投影冒充成功。
   - 所有新增 DOM 均使用 `createElement`、`textContent` 和既有 action 样式，没有 `innerHTML` 或新的公开 API/schema。
2. `frontend/index.html`
   - 将 `research-tasks.js` 静态资源缓存版本从 `?v=15` 更新为 `?v=16`。
3. `tests/frontend/test_paper_issue_ui_contract.py`
   - 增加按钮 POST 契约、请求不含 `report_version`、upload 不隐式调用报告 POST、失败恢复旧报告、canonical 读取/单飞按钮和资源版本断言。

## 验证

先行复现阶段：`.venv/bin/python -m pytest tests/frontend/test_paper_issue_ui_contract.py -q` 为 `3 failed, 3 passed`，退出码 `1`，失败对应尚不存在的报告动作接线。

实现后定向验证：

```text
.venv/bin/python -m pytest tests/frontend/test_paper_issue_ui_contract.py tests/frontend/test_evidence_report_frontend_contract.py tests/frontend/test_acquisition_progress_contract.py -q
退出码 0；12 passed

node --check frontend/research-tasks.js
退出码 0

node tests/frontend/test_research_report_notifications.js
退出码 0；Task08 frontend contract: PASS

node tests/frontend/test_research_session_workspace.js
退出码 0；Task09 frontend/Fake-DOM contract: PASS

git diff --check -- frontend/research-tasks.js frontend/index.html tests/frontend/test_paper_issue_ui_contract.py
退出码 0
```

## 交接与边界

- 本轮没有运行后端 pytest，没有提交 git。
- 这项前端修复证明的是“用户点击后调用既有报告版本接口并读取版本化 canonical JSON/Markdown”。现有 `/reports` POST 是否同时投影 `research_artifacts`、会话 final message 和 notification，仍以 `current-report-recovery-plan.md` 的条件性 backend 结论为准；本 UI 不作该能力已接通的声明。
- 需要下游独立 review、重新部署后再做真实浏览器/API 验证；本报告不冒充完整 Spec032 E2E 通过。

## 独立 review BLOCK 修复追加（2026-10-08）

针对 `current-report-action-ui-review.md` 的 P1/P2：

- 为任务切换增加 `taskGeneration`；`selectTask()` 和空工作区切换都会递增 token。upload、报告 POST/canonical 读取及其 catch/finally 均捕获任务 token，在每个延迟响应写回前确认仍是同一任务；旧请求不会清空或重绘新任务的 report、cache 或按钮状态。
- 版本选择改为事务式 `selectReportVersion()`：请求期间保留旧正文和旧标签；JSON/Markdown 均成功且版本一致后一次性提交。失败恢复旧 report、旧 `reportViews`、旧格式和选择器标签；`reportVersionRequest` 防止快速切换时晚到响应覆盖较新版本。
- paper-display 异步缓存与报告/矩阵延迟重绘也复用任务 guard，避免 A 的晚到缓存或重绘回写 B。
- 新增 `tests/frontend/test_report_action_race.js`，使用真实模块、延迟 fetch 响应和实际 `selectTask()` 切换覆盖生成/上传跨任务隔离、版本失败回滚和快速切换顺序；未创建新的业务 API/schema。
- 为延迟响应契约提供的三个函数仅在 CommonJS 测试模块导出，浏览器侧 `ResearchTasks` surface 未扩展。

追加验证：

```text
.venv/bin/python -m pytest tests/frontend/test_paper_issue_ui_contract.py tests/frontend/test_evidence_report_frontend_contract.py tests/frontend/test_acquisition_progress_contract.py -q
退出码 0；13 passed

node --check frontend/research-tasks.js
退出码 0

node tests/frontend/test_report_action_race.js
退出码 0；Report action race contract: PASS

node tests/frontend/test_research_report_notifications.js
退出码 0；Task08 frontend contract: PASS

node tests/frontend/test_research_session_workspace.js
退出码 0；Task09 frontend/Fake-DOM contract: PASS

git diff --check -- frontend/research-tasks.js frontend/index.html tests/frontend/test_paper_issue_ui_contract.py tests/frontend/test_report_action_race.js
退出码 0
```

独立 review 指出的 backend artifact/session/notification 条件仍未改变；本修复只关闭前端竞态，不把 `/reports` POST 冒充为完整 Spec032 链路。
