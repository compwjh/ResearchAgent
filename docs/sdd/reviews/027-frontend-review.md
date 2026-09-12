# Spec027 Task04 前端最终只读复审

## 结论

**GO**（P0：0，P1：0，P2：1 条非阻塞验证建议）。

本轮仅做只读复审与静态验证，未修改业务代码、长期配置或测试代码。此前列出的合同缺口均已在当前工作树闭环：报告选集安全白名单投影、Worker 模型/槽位事件字段、前端安全展示、SSE 游标恢复、XSS 边界、资源版本、无 pause/resume，以及普通聊天不误创建研究任务。

## 复审范围

- `AGENTS.md`
- `docs/sdd/specs/027-research-task-dynamic-orchestration-mvp.md`
- `docs/sdd/plans/027/task-04-frontend-research-workspace.md`
- `frontend/index.html`
- `frontend/research-tasks.js`
- `frontend/styles.css`
- `backend/app/api/routes_research.py` 当前 diff
- `backend/app/research/application/orchestrator.py` 当前 diff

## 逐项复审

| 检查项 | 结论与依据 |
|---|---|
| `GET /report` selections 安全白名单 | **通过**。`routes_research.py:203-217` 仅返回 `catalog_paper_id`、`relevance`、解析后的 `facets`、`evidence_level`、`created_at`；`routes_research.py:425-450` 通过该投影返回报告，未复制 title/abstract 等论文元数据。非法或非数组 `facets_json` 退化为空数组。 |
| Worker 事件字段 | **通过**。`orchestrator.py:616-641` 从状态更新后的 WorkItem 安全构造 payload，携带实际存在的 `model_tier`、`resolved_model`、`worker_slot`；搜索 Worker 的 running/failed/completed 路径见 `orchestrator.py:431-468`，评估/coverage/synthesize 路径见 `orchestrator.py:283-390`。不包含 Prompt 或思维链。 |
| 前端安全展示 `report.selections` / `model_tier` | **通过**。`research-tasks.js:346-370` 读取报告选集；`research-tasks.js:265-300` 用 `textContent` 展示目录 ID、相关性、证据级别和 facets；`research-tasks.js:233-262` 将 `model_tier`、`resolved_model`、`worker_slot` 仅作为文本摘要展示。 |
| 研究 CSS 作用域 | **通过**。`index.html:9-68` 的研究内联样式均以 `#research-view` 作用域；`styles.css:3022-3342` 的 Task04 研究样式也均以 `#research-view` 作用域。机械审计未发现脱离该容器的研究选择器。 |
| SSE `event_seq` 去重/重连/合成 terminal | **通过**。`research-tasks.js:395-409` 仅接受正整数真实事件、丢弃旧/重复 seq，并令 `event_seq=null` 的合成 terminal 不推进游标；`research-tasks.js:411-436` 从最新 `lastSeq` 以 `after_seq` 重连；`research-tasks.js:122-126` 和 `408` 在 terminal 后关闭连接。 |
| XSS / 不可信内容 | **通过**。任务、事件、报告选集和限制均走 `textContent`/节点 API（如 `research-tasks.js:151-175`、`249-262`、`265-300`）；报告 Markdown 在 `research-tasks.js:321-343` 经 Marked、DOMPurify、DOMParser，依赖不可用或解析异常时回退纯文本；未发现 `innerHTML`、`insertAdjacentHTML`、`outerHTML`、`document.write` 或 `eval`。 |
| 资源版本 | **通过**。`index.html:8` 为 `/assets/styles.css?v=37`，`index.html:657` 加载 `/assets/research-tasks.js?v=1`，`index.html:659` 为 `/assets/app.js?v=36`。 |
| 无 pause/resume | **通过**。研究 UI 仅提供取消按钮（`index.html:180-183`、`research-tasks.js:512-525`）；当前前端三文件无 `pause`/`resume` 命中。 |
| 普通聊天不误创建研究任务 | **通过**。`research-tasks.js:551-569` 仅在 `mode-select === "research"` 时拦截聊天提交；研究任务的 POST 仅位于显式创建和显式取消流程（`research-tasks.js:502`、`517`），普通/Developer 模式直接保留原聊天路径。 |

## P0 / P1 / P2

### P0：0

未发现安全、数据泄露、终态错误或普通聊天路径破坏等阻塞问题。

### P1：0

未发现会阻止 Task04 前端合同放行的问题。此前 NO-GO 的四项重点缺口均已关闭并有源码行号与静态断言支持。

### P2：1（非阻塞）

1. 当前证据仍是静态/合同验证，未在本轮执行真实桌面和 390px 浏览器 smoke；相关运行入口位于 `research-tasks.js:419-436`、`616-623`。这不影响本轮前端代码审查 GO，但应在 Spec027 Task06 最终验收中补做运行时桌面/移动端验证。

## 命令与结果

| 命令 | 结果 |
|---|---|
| `node --check frontend/research-tasks.js` | 退出码 0 |
| `node --check frontend/app.js` | 退出码 0 |
| `git diff --check` | 退出码 0，无空白错误 |
| `for f in tests/test_frontend_*.js; do node "$f"; done` | 退出码 0，5/5 Node 合同通过 |
| `.venv/bin/python -m pytest tests/test_frontend_*.py -q` | 退出码 0，101 passed |
| 前端静态断言：内联/CSS 作用域、资源版本、XSS sink、SSE seq、report selections、model 字段、无 pause/resume | 退出码 0，全部 PASS |
| `grep -nE '[[:blank:]]$' frontend/research-tasks.js`（反向断言） | 退出码 0，无尾随空白 |
| 研究改动文件冲突标记扫描 | 退出码 0，未发现 `<<<<<<<` / `=======` / `>>>>>>>` |

## 复审人

frontend-reviewer（当前执行 Agent）
