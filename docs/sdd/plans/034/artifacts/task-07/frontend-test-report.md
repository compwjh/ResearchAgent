# Spec034 Task07 前端验收报告

## 结论

**GO（自动化前端验收通过）**。Task07 前端 Fake-DOM、v1/v2 树契约、SSE/upsert 分流、终态屏障、滚动保护、XSS/DOM、CSS class、资源版本与前端回归均通过；未发现 P0/P1/P2 前端验收缺陷。

真实浏览器/SSE smoke 未通过环境门槛：验收时 `127.0.0.1:8000` 未启动，curl 返回退出码 7，in-app browser 返回 `net::ERR_CONNECTION_REFUSED`。该项留给主 Agent 启动服务后补验，不以 Fake-DOM 结果替代真实运行验收。

本次仅验收，未修改业务代码，未执行 commit/push/merge/reset/stash/clean。

## 验收范围

- `frontend/processing-tree.js` 共享 ProcessingStep 树：v1 扁平、v2 二级/三级邻接、乱序父子缓存、source_event_id/node_key/step_id 幂等 upsert。
- 运行/完成/partial/failed/cancelled 等状态，终态不可被不同迟到状态覆盖；失败强展、完成折叠、localStorage 展开恢复。
- 真实 Research 滚动容器的阅读位置保护与近底部跟随。
- `Research Tab` 仅消费 `processing_step/upsert` envelope；raw ResearchEvent 继续只进入原始时间线；`TRACE_PROJECTION_FAILED` 显示同步中。
- DOM/XSS、ARIA、reduced-motion、CSS class 作用域、静态资源版本和 diff 空白。

## 命令与结果

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| Node 语法 | `node --check frontend/processing-tree.js && node --check frontend/app.js && node --check frontend/research-tasks.js` | 0 | 3 个文件通过 |
| Task07 Fake-DOM | `node tests/test_frontend_processing_tree.js` | 0 | 通过；覆盖 v1/v2、乱序父节点、幂等、终态屏障、syncing、XSS、localStorage、ARIA、滚动保护 |
| Task07 专项契约 | `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task07_contract.py` | 0 | **7 passed** |
| 前端组合契约 | `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_frontend_project_tree_contract.py tests/test_frontend_conversation_contract.py` | 0 | **44 passed** |
| 全部前端 JS 合同 | `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | **6/6 PASS** |
| 全部前端 pytest | `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | **193 passed** |
| diff 空白 | `git diff --check -- frontend/app.js frontend/index.html frontend/research-tasks.js frontend/styles.css frontend/processing-tree.js tests/test_frontend_processing_tree.js tests/test_frontend_spec034_task07_contract.py` | 0 | 通过 |
| 静态机械门禁 | Task07 文件 trailing whitespace/conflict scan；required CSS class selector 检查；危险 HTML/eval API 扫描 | 0 | `trailing=0`、`conflict_markers=0`、required CSS **11/11**、`innerHTML/outerHTML/insertAdjacentHTML/document.write/eval/new Function` **none** |
| 版本号 | 检查 `frontend/index.html` 资源标签 | 0 | `processing-tree.js?v=1`、`app.js?v=46`、`styles.css?v=46`，并保留历史 `v45` marker |
| 本地服务探针 | `curl -sS -I http://127.0.0.1:8000/` | 7 | 未监听；`Couldn't connect to server` |
| 浏览器 smoke | in-app browser 打开 `http://127.0.0.1:8000/` | — | `net::ERR_CONNECTION_REFUSED`，服务未启动 |

## 行为验收证据

1. Fake-DOM 首先提交三级叶节点再提交父节点，孤儿节点不伪造根；父节点到达后挂载，重复 source event/node key 不增加节点。
2. 终态屏障覆盖 `completed → failed`、`failed → completed`、`partial → cancelled` 等竞争，首次终态保持不变；同一终态可幂等补充摘要。
3. v1 缺少排序字段时保持接收顺序；提供 `logical_sequence` 时按排序字段；v2 `parent_step_id` 形成树。
4. 用户不在底部时新增节点保持 `scrollTop`；接近底部时跟随新增内容；Research 使用真实 `.research-column-body` 滚动层。
5. Research `renderTimeline()` 不调用树 `upsert()`；树只通过 `applyProcessingStepFrame()` 处理 `processing_step` payload/upsert，处理该类型时不推进 raw `lastSeq`。
6. `TRACE_PROJECTION_FAILED`、`trace_syncing` 进入 `setSyncing(true)`；成功 upsert/clear syncing 后树级状态恢复为 running。
7. 动态 label/summary/status 均走 `textContent`；树 renderer 无危险 HTML/eval API；按钮提供 `aria-expanded`/`aria-label`，叶节点 `aria-disabled`；reduced-motion CSS 保留。

## 风险与后续

- 自动化前端验收为 GO；真实浏览器端到端仍需主 Agent 启动可用端口后验证 Research SSE 重连、后端 projector retry、父子乱序刷新和真实滚动行为。
- 本报告不运行后端 pytest，符合前端单端验收边界；后端与跨端 smoke 由对应 tester/主 Agent 负责。

## 日志

- 进展日志：[frontend-tester 日志](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-034/task-07/frontend-tester/20260913-124214.md)
- 验收时间：2026-09-13 12:42（Asia/Shanghai）
