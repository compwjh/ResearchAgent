# Spec034 Task08 前端交付报告

## 结果状态和摘要

**GO（前端实现完成，等待主 Agent 进行前后端联调与真实浏览器 smoke）。**

本轮复用现有会话消息、Research Tab 和 Task07 ProcessingTree，新增安全的报告 Artifact 操作与 owner 级通知体验：

- 最终助手消息可读取 `report`/`report_metadata`/`artifacts` 投影，展示报告状态、版本、摘要、引用 manifest，并只为 `markdown`、`html`、`citation_manifest` 构造安全下载/打开操作；HTML 将同一 owner-bound 下载路由转换为 `?mode=inline`，Markdown/manifest 保持 attachment；失败、等待审批、中断、可重试状态不会伪装成完成。
- Research Tab 在报告完成后按 session owner-bound 路由读取 Artifact metadata，提供 Markdown 下载、HTML 新窗口打开和引用 manifest 下载；保留加载、空、未就绪、失败状态。
- 侧栏新增研究通知列表，严格支持后端固定五类 `completed`、`partial`、`failed`、`waiting_approval`、`interrupted`；failed payload 的 `retryable`/`retry_attempt` 显示“研究失败，可重试”，但不创建独立 retry kind；heartbeat 与未知 kind 明确丢弃。通知按 `event_seq` 游标合并、断线从最后序号重连、重复帧不重复显示；点击通知执行 owner read CAS 并跳转对应会话/任务。
- 动态报告/通知文本均使用 `textContent`；Artifact URL 仅接受 owner-bound 下载路由；外链打开带 `noopener noreferrer`；新增样式限定在通知/报告类或 `#research-view`，并保留 reduced-motion 规则。

## 改动文件

- `frontend/research-tasks.js`：Artifact/通知规范化、URL 白名单、通知列表/SSE/read CAS/跳转、Research Tab Artifact metadata 与引用 manifest 展示。
- `frontend/app.js`：会话历史及流式最终助手消息的报告摘要、引用 manifest、Artifact 操作投影；接入 `report` 事件。
- `frontend/index.html`：侧栏研究通知列表和报告 Artifact/manifest 容器；资源版本递增到 `app.js?v=47`、`styles.css?v=47`，并保留 v46 兼容标记。
- `frontend/styles.css`：通知、报告操作、manifest 列表及窄屏/减弱动画样式。
- `tests/test_frontend_spec034_task08.js`：Artifact 路由、类型白名单、五类通知、failed retryable/retry_attempt 文案、heartbeat/未知 kind/status 丢弃、游标去重 Fake-DOM/HTTP 探针。
- `tests/test_frontend_spec034_task08_contract.py`：报告 XSS/下载、通知 SSE/read、DOM/CSS 作用域及资源版本静态契约。

## 测试命令 / 退出码 / 结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js && node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node tests/test_frontend_spec034_task08.js` | 0 | Task08 Fake-DOM/HTTP 探针通过；HTML `?mode=inline`、附件类型与恶意 query/外链合同通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task08_contract.py` | 0 | **5 passed** |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | **7/7 PASS** |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | **198 passed** |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_conversation_contract.py` | 0 | **32 passed** |
| `git diff --check -- frontend/app.js frontend/index.html frontend/research-tasks.js frontend/styles.css tests/test_frontend_spec034_task08.js tests/test_frontend_spec034_task08_contract.py` | 0 | 通过 |
| 机械门禁：冲突标记、报告新增区域 `innerHTML`、Artifact URL、CSS 作用域、版本号 | 0 | 通过；报告/通知新增 DOM 使用 `textContent`，历史 Markdown 渲染仍沿用既有净化管线 |

未运行后端 pytest，未执行部署、commit、push、merge、reset、stash 或 clean，符合前端分端边界。

## 决策依据

- 后端 Artifact API 只公开 metadata 与 owner-bound `download_url`，前端再次以固定路径正则校验，不接受任意 `storage_ref`、外部 URL、既有 query 或 `javascript:`；只有 HTML 经 `artifactActionUrl` 在校验后的同一路径上追加固定 `?mode=inline`。
- HTML 使用新窗口并设置 `noopener noreferrer`；Markdown/manifest 使用 `download`，避免把不可信报告文本当作页面 HTML。
- SSE 使用 `after_seq`，并记录 EventSource 自动发送 `Last-Event-ID`；本地 `event_seq` 屏障同时防止重连补发重复。heartbeat 是 SSE 注释帧，不进入通知集合。
- 通知点击先调用 `POST /api/research-notifications/{id}/read`，再通过 session 获取 conversation_id 或直接使用 payload 目标；Research Tab 与聊天仍调用既有导航/会话函数，没有新增第二套任务数据模型或处理树。

## 风险与阻塞

- 尚未运行真实浏览器/服务 smoke；主 Agent 需在后端服务启动后验证通知 SSE 重连、实际 owner 隔离、最终消息 metadata 投影和三类 Artifact 响应头。
- 当前历史 `/api/conversations/{id}/messages` payload 尚未在本轮前端中强制要求 `report` 字段；代码兼容 `report`、`report_metadata`、`research_report`、`report_output` 多种投影，待后端统一字段后应优先使用 `report`。
- 引用 manifest 在会话消息 metadata 可直接展示；Research Tab 列表接口仅返回 metadata，不读取 Artifact 内容，因此 Tab 只有在报告接口额外提供 `citation_manifest` 时展示引用条目。

## 主 Agent 后续动作

1. 复核并合并本轮前端文件与两份 Task08 前端测试。
2. 与后端报告消息 payload 做真实联调，确认 `conversation_id`、`research_session_id`、Artifact `download_url` 与 manifest 字段命名。
3. 启动服务后补做浏览器 smoke：完成/partial/failed（含 retryable/retry_attempt）/waiting_approval/interrupted 五类通知、断线补发去重、read CAS、Markdown/HTML/manifest 下载与 HTML XSS。
4. 在 Spec034 收口阶段运行全量前端/后端回归、更新状态台账并执行部署验证。

## 执行元数据

- 开始：约 2026-09-13（Asia/Shanghai）
- 结束：2026-09-13（Asia/Shanghai）
- 总耗时：约 45 分钟
- 可用时模型：当前执行 Agent 自身；主 Agent 指定临时 Luna high
- token 统计：子任务上下文未提供可查询 token 计数
- 工具统计：`apply_patch` 17 次，`exec_command` 13 次；未使用网络或子 Agent
- 进展日志：`.codebuddy/agent-logs/spec-034/task-08/frontend-dev/20260913-frontend.md`
