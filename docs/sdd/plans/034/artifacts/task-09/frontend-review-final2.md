# Spec034 Task09 前端最终复审报告（Final2）

评审角色：frontend-reviewer（只评审 `frontend/**` 与 Task09/相关前端测试）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：当前工作树、Task09 计划与交付报告、前轮 `frontend-review-final.md`、共享 Session projection、真实 Session detail 响应接缝及前端定向测试。未修改业务代码，未 commit/push。

## 结论

**GO**。前轮两个 P1 已在当前工作树闭环：

1. hydrate 后的真实会话标题现在优先使用 `conversation.title`，不会被列表投影的默认“深度研究”覆盖。
2. 共享 projector 现在读取嵌套 `plan.work_items(_json)` 与 `plan.capabilities(_json)`，对 Agent/Tool 名称去重计数；真实 API 的嵌套 JSON 形状已通过合同测试。

Task09 要求的共享 projection、Session/Tab 接缝、XSS 防线、普通会话旧研究按钮移除和资源版本检查均通过。未发现 P0/P1/P2 阻断。

## P1 复核

### P1-01：hydrate 后 conversation 标题优先级 — 已关闭

- `frontend/research-tasks.js:607-628` 先取得 Session detail，并在有 `conversation_id` 时读取 `/api/conversations/{id}`，再把 conversation 传入 canonical projector。
- `frontend/research-session-ui.js:44-45` 明确按 `conversation.title || value.title || ...` 取标题；`goal_excerpt` 同样优先 conversation 标题（:59）。
- `tests/test_frontend_spec034_task09.js` 的真实形状 probe 验证 `深度研究：真实会话标题` 不会退化为通用标题；Task09 contract 通过。

### P1-02：真实 API 嵌套 plan 的 Agent/Tool 摘要 — 已关闭

- 后端 Session detail 的 `plan` 可能提供 `work_items_json/capabilities_json`；projector 在 `frontend/research-session-ui.js:48-52` 同时支持数组和 JSON 字符串，并按 role/agent 与 tools 名称去重计数。
- 同一真实形状 probe 验证三类 WorkItem 去重为 `Agent 2`、两类工具去重为 `Tool 2`，卡片通过 `textContent` 展示。
- 若后端已有白名单 `agent_tool_summary`，仍按显式摘要优先；无摘要时才从嵌套 plan 推导。

## 其他必查项

- **共享 projection/接缝**：聊天和 Research Tab 均加载 `research-session-ui.js` 并调用 `ResearchSessionUI.projectSession/planField`；聊天命令成功通过 `research-session-command-success` 回接 Tab，继续复用既有 Task/SSE/report 管线。
- **XSS**：Task09 会话标题、状态、摘要、ID 使用 DOM API/`textContent`；`research-tasks.js` 与 `research-session-ui.js` 无 `innerHTML`。恶意 topic 的 Fake-DOM 合同通过。既有聊天 Markdown `innerHTML` 路径不属于本轮新增 renderer，仍沿用既有净化管线。
- **旧入口**：Research Tab 创建/列表仅调用 `/api/research-sessions`；未发现普通会话旁 `research-conversation-action` 或旧 POST 启动旁路。
- **资源版本/CSS**：`index.html` 使用 `styles.css?v=48`、`app.js?v=48`、`research-tasks.js?v=2`、`research-session-ui.js?v=1`；新增卡片样式均限定在 `#research-view`。

## 验证记录

| 检查 | 退出码/结果 |
|---|---:|
| `node --check frontend/research-session-ui.js && node --check frontend/research-tasks.js && node --check frontend/app.js && node --check frontend/processing-tree.js` | 0 |
| `node tests/test_frontend_spec034_task09.js` | 0，真实 Session 标题/嵌套 plan 摘要/XSS probe PASS |
| `node tests/test_frontend_processing_tree.js && node tests/test_frontend_spec034_task08.js && node tests/test_frontend_conversation_research.js` | 0，全部 PASS |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task09_contract.py` | 0，8 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task04_contract.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task08_contract.py` | 0，20 passed |
| `git diff --check -- frontend tests/test_frontend_spec034_task09.js tests/test_frontend_spec034_task09_contract.py` | 0 |

## 遗留与边界

本次是前端只读复审，未运行后端 pytest 或真实浏览器/Ollama smoke；主 Agent 仍需按收口流程执行创建→会话→Research Tab→审批→Task/树/报告的运行时验证。该项不构成当前前端代码 GO 的阻断。

## 进展日志

`.codebuddy/agent-logs/spec-034/task-09/frontend-reviewer/20260915-012901.md`

