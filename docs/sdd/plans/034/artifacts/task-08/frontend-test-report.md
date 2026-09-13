# Spec034 Task08 前端验收报告

**角色**：frontend-tester（只验收，不修改业务代码，不 commit）  
**时间**：2026-09-13 14:32 CST  
**范围**：`frontend/app.js`、`frontend/research-tasks.js`、`frontend/index.html`、`frontend/styles.css` 及 Task08/Task07 前端合同。

## 结论

**自动化与静态验收：GO。**  
**最终浏览器验收：NO-GO（阻塞项）**：`http://127.0.0.1:8000/` 当前连接失败（HTTP 000），未部署服务，无法执行真实浏览器 smoke、报告下载/HTML 新窗口、通知点击跳转和窄屏视觉检查。待服务启动后需补做一次浏览器验收。

## 验收结果

| 检查 | 命令/证据 | 结果 | 退出码/计数 |
|---|---|---:|---:|
| JS 语法 | `node --check frontend/*.js` | PASS | 0 |
| Task08 JS/Fake-DOM | `node tests/test_frontend_spec034_task08.js` | PASS | 0；1 个 contract |
| Task07 processing-tree Fake-DOM | `node tests/test_frontend_processing_tree.js` | PASS | 0；1 个 contract |
| Task07 conversation-research Fake-DOM | `node tests/test_frontend_conversation_research.js` | PASS | 0；1 个 contract |
| Task08 + Task07 Python 合同 | `python -m pytest -q tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task07_contract.py` | PASS | 0；12 passed |
| 全量前端 Python 合同/回归 | `python -m pytest -q tests/test_frontend*.py`（17 个文件） | PASS | 0；198 passed |
| 前端差异空白 | `git diff --check -- frontend/... tests/test_frontend_spec034_task08.*` | PASS | 0 |
| 冲突标记 | `rg '^<<<<<<<\|^=======\|^>>>>>>>' frontend tests/test_frontend_spec034_task08.*` | PASS | 0 命中 |

## 重点覆盖核对

- 历史助手消息可从 `report`/`report_metadata`/`research_report`/`report_output` 投影报告状态、版本、摘要、Artifact 和 citation manifest；动态摘要、引用和报告操作使用 `textContent`/DOM API，报告区域不使用不安全的 `innerHTML`。
- Artifact 类型仅允许 `markdown`、`html`、`citation_manifest`；下载 URL 受同源 `/api/research-sessions/<id>/artifacts/<id>/download` allowlist 约束。HTML 动作追加 `?mode=inline` 并新窗口打开；Markdown/manifest 保留下载 URL 并设置 `download`，预置 query、外部 URL 和危险 scheme 被拒绝。
- 通知监听五类 `completed`、`partial`、`failed`、`waiting_approval`、`interrupted`；failed 的 `retryable`/`retry_attempt` 显示可重试文案。heartbeat 不入列表；未知 kind、status、无效/非正 event_seq 被丢弃或标记同步错误。
- 通知 REST 首次/增量请求携带 `after_seq`，SSE 显式携带 `after_seq` 并依赖 `Last-Event-ID`；按 `event_seq` 去重和单调游标处理。点击通知先调用 owner-scoped read API（`POST .../<notification_id>/read`，后端 CAS），再按 conversation/session/task/message 目标跳转和聚焦。
- Task07 三级 processing tree 的乱序父子缓存、幂等 upsert、终态屏障、SSE `processing_step` 游标、XSS text boundary、ARIA/localStorage 展开状态和 reduced-motion 合同均通过。
- live 资源版本为 `/assets/app.js?v=47`、`/assets/styles.css?v=47`；新增 CSS 使用通知/报告作用域选择器。

## 阻塞与后续

1. 启动部署服务后，使用真实浏览器验证：历史报告内容与 citation manifest、Markdown 下载、HTML `mode=inline` 新窗口、五类通知 SSE 断线补发/heartbeat、已读 CAS、通知定位，以及桌面/窄屏布局。
2. 本报告未修改业务代码；工作树中的实现与测试改动属于上游 Task08 实施范围。

**进展日志**：`.codebuddy/agent-logs/spec-034/task-08/frontend-tester/20260913-000000.md`
