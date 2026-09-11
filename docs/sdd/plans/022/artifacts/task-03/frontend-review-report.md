# Spec022 Task03 前端评审报告

## 结论

**GO（可进入跨端验收）**。未发现 P0/P1/P2；上一轮发现的键盘可访问性问题已修复并由新增定向契约测试覆盖。

本报告只评审 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 的 Task03 增量及其对 Task02/论文前端契约的影响；`backend/app/api/routes_conversations.py` 与 `schemas.py` 仅用于接口契约交叉核对，不替代后端评审。

## 严重级别汇总

| 级别 | 数量 | 状态 |
|---|---:|---|
| P0 | 0 | 通过 |
| P1 | 0 | 通过 |
| P2 | 0 | 已关闭 |

## 问题清单

### [P2] “记忆治理”导航无法用键盘激活（已关闭）

- 文件：`frontend/index.html:43`
- 文件：`frontend/app.js:1975-1979`
- 原问题：Task03 新增入口是没有 `href` 的 `<a role="button" tabindex="0">`，初版脚本只监听 `click`，键盘用户无法进入治理页。
- 修复证据：`frontend/app.js:1980-1984` 为 `.nav-item` 统一绑定 Enter/Space `keydown`，调用 `showView(item.dataset.view)`；鼠标路径仍由 `frontend/app.js:1976-1979` 保留。
- 测试证据：`tests/test_frontend_management_contract.py:78-81` 新增 `test_memory_navigation_is_keyboard_activatable`，验证 keydown、Enter/Space 判断和 `showView` 调用；本次三组前端 Python 合同共 35 passed。
- 结论：**已关闭**。新增记忆治理入口可通过鼠标及键盘激活。

## 四项项目必守核对

| 必守项 | 结论 | 代码证据 |
|---|---|---|
| DOM 契约 | PASS | Task03 新增治理 class 在 `frontend/styles.css:29-33,71-90` 均有定义；`#memory-view`、治理控件与列表在 `frontend/index.html:21-35,77-81,110-146` 定义；静态检查未发现 app.js `querySelector('#...')` 缺失 ID。 |
| 资源版本号 | PASS | `frontend/index.html:7` 与 `:389` 同步使用 `?v=27`；Task02/论文版本断言同步更新。 |
| XSS / 用户内容边界 | PASS | 记忆列表与来源使用 `textContent`（`frontend/app.js:600-631`）；会话历史用户/tool 内容使用 `textContent`（`:251-254`），回答经 `setConversationAnswer` → `renderMarkdown` → DOMPurify（`:279-280,2183-2192`）；本次治理 renderer 片段无 `innerHTML`。 |
| CSS 作用域 | PASS | 新增记忆页面主布局使用 `#memory-view` 限定（`frontend/styles.css:71-73`）；其余新增为项目专用 class，无裸写新增全局标签选择器，未见污染既有论文/知识库 DOM 的选择器。 |

## Spec022 Task03 契约核对

| 场景 | 结论 | 证据 |
|---|---|---|
| 项目重命名/归档/恢复/删除 | PASS | `frontend/app.js:495-526` 通过项目 PATCH/DELETE；归档按钮依据状态切换“归档/恢复”；删除确认文案明确项目级联删除、全局记忆保留（`:521-524`）。 |
| 会话重命名/归档/恢复/删除 | PASS | `frontend/app.js:528-559` 通过会话 PATCH/DELETE；删除文案明确消息删除而不联动记忆（`:554-557`）。 |
| 绑定/解绑/跨项目移动 | PASS | `frontend/app.js:561-579` 在确认后发送 `confirm_move: true`，并发送 `from_binding` 或 `include_prior_history`；失败使用 `conversationFetch` 的稳定错误 message 恢复选择并展示可读状态。后端 schema 接受这些字段：`backend/app/api/schemas.py:36-41`。 |
| 记忆 scope/status/list | PASS | `frontend/index.html:121-146` 提供 global/project、项目筛选和五种状态；`frontend/app.js:636-645` 发送 `scope/status/project_id`；后端列表契约见 `backend/app/api/routes_conversations.py:293-301`。 |
| evidence / confirm / edit-superseding / disable / delete / undo | PASS | `frontend/app.js:659-684` 分别调用 `/evidence`、`/confirm`、PATCH（服务端版本化）、`/disable`、DELETE、`/undo`；对应路由见 `backend/app/api/routes_conversations.py:321-380`。 |
| SSE 与 Task02 聊天 | PASS（静态） | `frontend/app.js:692-725` 保留唯一消息入口、AbortController/generation 保护及 `meta/progress/memory/token/error/done` 分支；Task02 对话合同测试通过。 |
| 旧论文 DOM 契约 | PASS（静态） | Task03 只新增 memory 视图并将 app/styles 版本升至 27；论文前端合同和 4 个既有 Node 合同均通过。 |

## 验证命令

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_management_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_paper_contract.py` | 0 | **35 passed** |
| `rg --files tests \| rg 'test_frontend_.*\\.js$' \| sort \| while read -r test_file; do node "$test_file" \|\| exit 1; done` | 0 | **4/4 PASS** |
| `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css` | 0 | 通过 |

按任务边界未运行全量 pytest、后端 pytest、浏览器 E2E、部署或运行时 smoke。

## 风险与后续动作

- 已关闭 P2：记忆治理入口现支持 Enter/Space 键盘激活，并有静态契约测试覆盖。
- 真实浏览器仍需由跨端验收角色验证项目级联删除提示、全局记忆保留、跨项目移动双确认、证据展开及网络失败提示。
- Task02 报告中已知的真实 SSE `progress` 与切换会话流中断行为，仍应在部署 smoke 中验证；本次静态审查确认前端保留对应处理分支。

## 运行信息

- 评审角色：`frontend-reviewer`
- 模型：临时 Luna high（按主 Agent 分派）
- 开始：约 2026-09-11 05:13（Asia/Shanghai）
- 初审结束：2026-09-11 05:18（Asia/Shanghai）
- 增量复审：2026-09-11 05:33（Asia/Shanghai）
- 总耗时：初审约 5 分钟，增量复审约 2 分钟
- 模型 token 统计：当前子代理运行时不可用
- 工具统计：运行时未提供精确计数；增量复审使用文件读取、静态检索、Node 语法检查、pytest 和 Node 合同检查
- 进展日志：`.codebuddy/agent-logs/spec-022/task-03/frontend-reviewer/20260911-000000.md`
