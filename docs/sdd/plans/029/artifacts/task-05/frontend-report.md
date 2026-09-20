# Spec029 Task05 前端交接报告

## 结果状态和摘要

```text
result=IMPLEMENTED
candidate_edit_and_preview=GO
explicit_confirmation_before_download=GO
per_paper_progress_login_wait_and_retry=GO
fulltext_locator_entry=GO
runtime_smoke=NOT_RUN_BY_SUBAGENT
```

研究任务详情新增“全文获取与证据”区域：候选以复用报告选集为边界，可勾选增删；预览只调用 `acquisition-preview`，确认按钮才提交 `acquisitions`。确认带选集版本、服务端搜索快照句柄和幂等键，确认前不会下载。状态从既有 `GET .../acquisitions` 投影，逐篇显示已有、排队、下载/处理/索引、等待登录、失败和完成；失败项复用既有 import-item retry API。全文证据升级结果显示文档、页码、切片数量，并提供跳转知识库原文入口。

## 改动文件

- `frontend/index.html`：研究详情中加入候选、确认、导入进度、登录等待、失败恢复和全文证据定位 DOM。
- `frontend/research-tasks.js`：接入预览/确认/状态轮询/逐条重试，复用已有状态投影；所有不可信文本使用 `textContent`，不使用浏览器原生 `prompt`/`confirm`。
- `frontend/styles.css`：新增 `#research-view` 作用域的响应式状态卡片样式。
- `tests/test_spec029_frontend_acquisition_progress.py`：补充端点、候选编辑、状态恢复、证据跳转和 DOM 安全合同测试。

## 测试命令/退出码/结果

```text
.venv/bin/python -m pytest -q tests/test_spec029_frontend_acquisition_progress.py
exit=0 · 4 passed

.venv/bin/python -m pytest -q tests/test_frontend_spec028_task05_contract.py tests/test_frontend_spec034_task09_contract.py
exit=0 · 11 passed

node tests/test_frontend_spec034_task09.js
exit=0 · Task09 frontend Session/Fake-DOM contract: PASS

node --check frontend/research-tasks.js
exit=0

git diff --check -- frontend tests/test_spec029_frontend_acquisition_progress.py
exit=0
```

未运行全量回归、后端 pytest、部署或真实下载/登录流程，符合 Task05 分工边界。

## 产物路径

`docs/sdd/plans/029/artifacts/task-05/frontend-report.md`

## 决策依据

- 复用 Task03/04 已定义的 Research Acquisition API，不在前端复制下载器或导入状态机。
- 预览请求明确展示“不会下载”；确认只有用户点击按钮后发起，并保持客户端不可提交候选 URL/快照内容。
- 登录状态只显示等待提示，要求用户在既有浏览器会话完成登录，不自动登录或打开确认对话框。
- 失败重试调用既有 `/api/papers/import-items/{item_id}/retry`，随后重新读取 Research 投影。
- 证据定位使用已有知识库跳转入口，并显示后端验证过的 `document_id/page/page_end/chunk_ids`。

## 风险阻塞

- 当前后端确认契约要求服务端搜索快照 `search_id`；若任务详情/报告未返回该句柄，界面会安全地禁止确认并提示刷新，不会猜造 ID，也不会下载。
- 后端目前没有独立的 evidence-upgrade GET 路由；界面消费报告或状态响应中随附的 `evidence_upgrades/evidence`，后续若要跨刷新恢复全部升级记录需由后端提供读取投影。
- 未在真实浏览器中验证 PDF 原文切片自动聚焦；当前按钮复用已有知识库文档跳转入口并保留页码/切片元数据。

## 主 Agent 后续动作

- 在 Task06 运行真实前后端 smoke：确认候选预览不触发下载、显式确认后批次启动、waiting_login/failed/retry/partial_success 状态可恢复。
- 核对任务详情或报告是否稳定返回 `search_id`；若没有，应先补后端桥接字段并更新 Spec029/Task05 契约，再做运行时验收。
- 通过真实公开 PDF 完成全文索引后检查“打开原文切片”行为，并在最终验收报告记录页码/切片证据。

## 开始/结束/总耗时

```text
开始：2026-09-16T03:45:00+08:00（约）
结束：2026-09-16T04:07:46+08:00
总耗时：约 22 分 46 秒
```

## 模型/token/tool 统计

本子任务由当前分派 Agent 完成；未获得可审计的 token/tool 计数接口，故不填估算值。

