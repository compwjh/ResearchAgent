# Spec034 Task09 前端最终复审报告

评审角色：frontend-reviewer（只评审 `frontend/**` 与相关前端测试）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：当前工作树、Task09 计划/交付物、前轮 `frontend-review.md`，以及真实 Session API 响应形状的前端接缝核对。未修改业务代码，未运行后端 pytest、未 commit/push。

## 结论

**NO-GO**。前轮 P1 的两个目标在当前工作树仍未闭环：

1. 真实 Session hydrate 后，conversation 标题仍会被通用标题“深度研究”覆盖。
2. 真实 Session detail 的 Agent/Tool 来源位于嵌套 `plan` 的 `work_items_json`/`capabilities_json`，当前 projector 不读取该位置，因此卡片仍显示 `Agent/Tool：—`。

会话/Tab 命令桥接、旧入口移除、Task07 SSE/Task08 report 接缝、Task09 动态渲染的 XSS 防线和资源版本检查通过；但以上两个 P1 直接违反 Task09 卡片可观测性与真实会话标题要求，不能放行。

## P1-01：hydrate 后 conversation 标题优先级仍错误

证据：

- `frontend/research-session-ui.js:34` 的标题优先级是 `value.title || conversation.title || ...`。
- `frontend/research-tasks.js:607-628` 的 `hydrateSession()` 先生成 `base = projectSession(raw)`；对真实列表 Session，`base.title` 已被 projector 默认成“深度研究”。随后合并 `...base`，但会话对象只放在独立的 `conversation` 字段，导致再次投影时 `value.title` 仍优先于 `conversation.title`。
- `frontend/research-tasks.js:571` 使用 `task.goal_excerpt` 作为卡片标题，`projectSession()` 又在 `:48` 将其从同一个通用 `title` 派生，因此刷新/重新 hydrate 后会显示“深度研究”，而不是后端创建返回的“深度研究：<主题>”。

真实响应形状下的最小 probe（退出码 0，但输出证明错误）得到：

```text
base_title: 深度研究
hydrated_title: 深度研究
goal_excerpt: 深度研究
```

建议修复：在 canonical projection 中让真实 `conversation.title` 优先于 projector 默认值，或 hydrate 时不要把默认 `base.title/goal_excerpt` 当作已确认值覆盖 conversation；同时补充“列表 Session → hydrate detail + conversation → 卡片标题”的回归测试。

## P1-02：真实 API 形状无法恢复 Agent/Tool 摘要

证据：

- `backend/app/research/domain/models.py:335-353` 的 `ResearchSession.to_dict()` 只返回 Session 标量字段，不包含标题、Agent/Tool 摘要或 work items。
- `backend/app/api/routes_research.py:716-737` 的 Session detail 将计划放在 `plan` 字段；`ResearchSessionPlan.to_dict()`（`backend/app/research/domain/models.py:111-129`）返回 `work_items_json`、`capabilities_json` 字符串，而非顶层 `work_items`/`capabilities`。
- `frontend/research-session-ui.js:35-42` 只从 `value` 或 `task` 顶层读取 `agent_tool_summary`、`work_items(_json)`、`capabilities(_json)`，没有读取 `value.plan`。`hydrateSession()`（`frontend/research-tasks.js:622-627`）虽传入 `plan: latestPlan`，但 projector 不消费该嵌套字段。
- 针对真实形状的 probe 输出 `summary: ""`。现有 `tests/test_frontend_spec034_task09.js:11-25` 直接注入顶层 `title` 与 `agent_tool_summary`，因此合同通过不能证明真实 hydrate 路径已修复。

建议修复：明确 Agent/Tool 统计的 canonical 来源；若来源是 Session detail 的 `plan`，在 projector 中解析 `plan.work_items_json`/`plan.capabilities_json`（或由后端提供白名单的 `agent_tool_summary`），并增加真实 API 形状测试，禁止只用 Fake-DOM 顶层注入字段验收。

## 已通过项

- **Session/Tab 接缝**：聊天侧 `frontend/app.js:1730-1743` 发布 `research-session-command-success`；Tab 侧 `frontend/research-tasks.js:1466-1477` 监听并调用 `mergeSessionCommandResult()`，批准后复用 `selectTask()`、既有 ProcessingTree SSE 与报告加载管线。未发现第二套 Task/SSE 状态入口阻断本轮范围。
- **入口与 API**：Research Tab 列表/创建分别使用 `/api/research-sessions`；`frontend/research-tasks.js` 未发现普通会话旁独立研究按钮或旧 POST 创建旁路。旧 `/api/research-tasks/{id}` 仅作为任务详情兼容读取。
- **XSS**：`frontend/research-tasks.js`、`frontend/research-session-ui.js`、`frontend/index.html` 未发现 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、`eval`；Task09 动态会话标题、摘要、ID、状态均经 `textContent`/DOM API 写入。`app.js` 的既有 Markdown `innerHTML` 路径不属于 Task09 新增 renderer，且沿用既有净化管线。
- **资源版本/CSS**：`frontend/index.html` 使用 `styles.css?v=48`、`app.js?v=48`、`research-tasks.js?v=2`、`research-session-ui.js?v=1`；新增 Research CSS 以 `#research-view` 限定，未见未版本化 Task09 资源。

## 验证记录

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-session-ui.js` | 0 | 通过 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `node tests/test_frontend_spec034_task09.js` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task09_contract.py` | 0 | 7 passed |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | 全部前端 JS 合同通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | 205 passed |
| `git diff --check -- frontend tests/test_frontend_spec034_task09.js tests/test_frontend_spec034_task09_contract.py` | 0 | 通过 |
| Task09 XSS/旧按钮/资源版本静态检查 | 0 | 无新增危险渲染、无旧按钮、4 项资源版本齐全 |

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0/CRITICAL | 0 | pass |
| P1/HIGH | 2 | **阻断** |
| P2/MEDIUM | 0 | pass |
| P3/LOW | 0 | pass |

Verdict: **NO-GO**。请修复 P1-01/P1-02 后重新执行真实 API 形状测试与前端最终复审；本轮没有执行全量后端回归或真实浏览器 smoke。
