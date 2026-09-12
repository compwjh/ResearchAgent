# Spec027 Task04 前端交接报告

## 状态

**完成（frontend-dev 最小可运行闭环）**。本交接只覆盖 `frontend/index.html` 与 `frontend/research-tasks.js`；未修改 `app.js`、`styles.css`、`backend/**`、长期模型配置、AGENTS、MODEL_REGISTRY 或 `.codebuddy/agents/**`。

## 修改文件

- `frontend/index.html`
  - 增加“深度研究”显式模式与工作区导航。
  - 增加研究任务工作台：任务列表、详情/计划 facets 与 rationale、事件时间线、Worker/模型/coverage/re-plan 摘要、论文选集摘要、只读报告、创建表单和显式取消按钮。
  - 使用语义三栏 DOM；窄屏切换为单栏并支持 `details` 折叠。
  - 在现有 vendor 脚本之后、`app.js` 之前加载 `/assets/research-tasks.js?v=1`。

- `frontend/research-tasks.js`
  - 从当前 `/c/{conversation_id}` 获取会话；无会话时显示可操作提示。
  - `POST /api/research-tasks` 创建任务；`GET` 列表/详情/报告；显式 `POST .../cancel` 取消。
  - `EventSource` 连接 `/events?after_seq=N`；按真实正整数 `event_seq` 去重和推进游标，合成 `terminal` 的 `null` 游标不参与续传；断线后按最新游标重连。
  - 刷新顺序为会话、列表、详情/报告，再建立 SSE；页面关闭没有取消请求。
  - 论文/报告/事件文本均通过 `textContent` 或安全 Markdown 路径渲染；报告使用 Marked + DOMPurify + DOMParser，依赖未就绪时回退纯文本。
  - 提供 `TASK_DELETED`、`RESEARCH_CASCADE_FAILED`、`INTERNAL_ERROR` 和未知错误码兜底文案。
  - 通过 DOM 事件接入 `app.js`，不依赖其未导出的 `const`；普通/Developer 模式保持普通聊天路径，只有显式选择深度研究模式才引导到工作台。

## 验证命令 / 结果

| 命令 | 结果 |
|---|---|
| `node --check frontend/research-tasks.js` | 退出码 0，通过 |
| `git diff --check` | 退出码 0，无空白错误 |
| `rg -n 'innerHTML|\\bpause\\b|\\bresume\\b' frontend/research-tasks.js` | 无匹配；rg 退出码 1，符合预期 |

未运行后端 pytest，也未修改后端。当前工作树核对时发现 `frontend/styles.css` 存在不属于本子任务的外部变更；本 Agent 未触碰该文件。

## 风险

- 本轮只完成静态/语法闭环，尚未进行真实浏览器 390px smoke 或真实后端 SSE 运行时验收。
- Task03 当前没有独立的 WorkItem/论文选集 GET 投影；前端对 Worker、coverage 和安全事件摘要进行展示，报告正文保持只读。
- “先审核计划”字段可随创建请求提交；本 Task 未新增计划批准交互，继续执行由后续范围处理。

## 日志路径

`.codebuddy/agent-logs/spec-027/task-04/frontend-dev/20260912-frontend-workspace.md`
