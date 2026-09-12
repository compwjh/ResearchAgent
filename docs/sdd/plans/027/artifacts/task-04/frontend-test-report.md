# Spec027 Task04 前端验收报告

## 状态

**PASS**

本验收只做 frontend-tester 范围内的前端静态/契约核对：未修改业务代码，未运行后端 pytest。

## 执行环境与范围

- 角色：frontend-tester
- 模型：用户本轮指定 Luna high；调用层未提供独立模型回执，本报告不把该项作为验收证据；未修改长期配置、模型注册或角色规则。
- 读取交接物：`AGENTS.md` frontend-tester 约束、`docs/sdd/ROLE-ONBOARDING.md`、Spec027、Task04、Task03 backend report、Task04 前端交接/样式报告及当前实际 diff。
- 当前工作树存在其他并行改动；本验收未修改这些文件。

## 命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `for f in tests/test_frontend_*.js; do node "$f"; done` | 0 | 5/5 个现有 Node 合同通过 |
| `.venv/bin/python -m pytest tests/test_frontend_*.py -q` | 0 | **101 passed** |
| `git diff --check && node --check frontend/research-tasks.js` | 0 | 通过 |
| `rg -ni '\b(innerHTML|pause|resume)\b' frontend/research-tasks.js frontend/index.html frontend/styles.css` | 1 | 无匹配，符合预期 |
| DOM/SSE/XSS/导航静态契约断言脚本 | 0 | **20/20 通过** |
| `rg -n '/assets/styles.css\\?v=37|data-view="research"|value="research"|research-tasks.js' frontend/index.html` | 0 | 研究入口与 v37 资源版本存在 |
| `git status --short -- frontend tests docs/sdd/plans/027/artifacts/task-04/frontend-test-report.md` | 0 | 仅显示当前工作树既有前端/测试/报告改动，验收未改业务代码 |

## 通过项

- 研究入口存在：侧栏 `data-view="research"`、模式选择 `research`、`#research-view` 工作台及创建表单存在。
- 工作台 DOM 契约完整：任务列表、详情、计划 facets、事件时间线、论文选集、执行摘要、只读报告、刷新和显式取消入口均存在。
- `frontend/index.html` 使用 `/assets/styles.css?v=37`，并加载 `/assets/research-tasks.js?v=1`。
- 研究模块不使用 `innerHTML`，不包含 `pause` / `resume`，不显示隐藏思维链或完整 Prompt。
- 普通/Developer 模式保持普通聊天路径；只有 `mode-select === "research"` 时拦截聊天提交并转到研究工作台，普通模式不会创建研究任务。
- 真实正整数 `event_seq` 才进入去重与游标推进；重复/旧 seq 被丢弃。
- 合成 `terminal` 的 `event_seq=null` 不推进 `lastSeq`，并按 `event: terminal` 收尾后关闭流。
- 断线使用当前 `lastSeq` 构造 `after_seq` 重连，错误后调度重连。
- 事件、论文摘要和报告限制使用 `textContent`；Markdown 路径经过 Marked + DOMPurify + DOMParser，依赖不可用时回退纯文本。
- 离开研究导航、历史变化、hash 变化时关闭 EventSource；取消仅调用显式 `/cancel`，终态任务不会再次取消。
- Task04 没有专用 `tests/test_spec027_frontend*` 合同；已运行仓库全部现有前端 Node/Python 合同。

## 阻塞项

无。

`tests/test_frontend_spec025_context_meter.py` 已按当前资源版本要求断言 `/assets/styles.css?v=37`，全部 101 个前端 Python 合同通过。

未执行后端 pytest；本轮按 frontend-tester 范围只执行前端静态/契约验收。仓库未发现 Task04 专用浏览器合同，因此未将浏览器 smoke 作为本轮阻塞项。

## 结论

研究模块静态契约、SSE/XSS 安全边界、研究入口、无 pause/resume 约束、资源版本、全部前端 Node/Python 合同及 diff 检查均通过，Task04 前端验收结论为 PASS。

## 日志路径

`.codebuddy/agent-logs/spec-027/task-04/frontend-tester/2026-09-12-static-contract.md`
