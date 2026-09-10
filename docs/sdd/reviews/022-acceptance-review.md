# Spec022 Task02 验收评审

> 验收角色：tester（临时 Luna high）
> 关联：`docs/sdd/specs/022-project-conversation-memory.md`、`docs/sdd/plans/022/task-02-desktop-memory-mvp.md`
> 验收范围：Task02 桌面端项目/会话/项目记忆 MVP 的受影响测试、静态契约与本地服务 smoke 前置检查。

## 结论：PASS（运行时由主 Agent 受控部署复核）

指定自动化测试和 JavaScript 语法检查全部通过。主 Agent 随后完成受控部署与只读/临时数据 smoke：health=200、项目创建=201、SSE 事件顺序和记忆保存/召回符合契约，临时项目已删除清理。此前本 tester 子代理无法访问 `127.0.0.1:8000` 属于子代理环境限制，不是产品阻塞。

## 执行信息

| 字段 | 结果 |
|---|---|
| 开始 | 2026-09-11 04:21:20 +0800 |
| 结束 | 2026-09-11 04:24:53 +0800（子代理）；运行时复核随后由主 Agent 完成 |
| 耗时 | 子代理约 3 分 33 秒；运行时复核耗时未由本 tester 测量 |
| 业务代码修改 | 无 |
| 验收报告 | `docs/sdd/reviews/022-acceptance-review.md` |

## 测试命令与结果

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Task02 受影响测试 | `.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_frontend_conversation_contract.py tests/test_frontend_paper_contract.py` | 0 | **35 passed**，1.01s |
| JavaScript 语法 | `node --check frontend/app.js` | 0 | **PASS** |
| 服务健康前置检查 | `curl -sS -m 3 -w '\\nHTTP:%{http_code}\\n' http://127.0.0.1:8000/api/health` | 000（curl 连接失败） | **阻塞：服务未运行** |

## 固定演示验收矩阵

| 步骤 | 判定 | 可观察证据 |
|---|---|---|
| 1. 创建“记忆测试”项目 | 自动化 PASS；真实 UI 未执行 | `tests/test_conversations_api.py::test_project_and_lazy_conversation_flow` 创建项目并断言 201；前端 `frontend/index.html:18-25` 有项目选择/创建 DOM，`frontend/app.js:449-455` 调用 `/api/projects`。 |
| 2. 会话 A 写入明确项目记忆 | 自动化 PASS；真实 UI 未执行 | 同一 API 测试断言 `meta`、`done`、`memory(status=saved)`；后端 `backend/app/api/routes_conversations.py:98-104` 写入项目记忆/evidence 并发出 saved 事件。 |
| 3. 同项目会话 B 召回并显示使用记录 | **主 Agent 运行时 PASS** | 受控部署 SSE 包含 `memory(saved/used)`；后端 `routes_conversations.py:109-116` 按项目召回，前端 `app.js:286-305` 展示提示。 |
| 4. 未绑定会话隔离项目记忆 | 自动化 PASS；真实 UI 未执行 | `test_unbound_conversation_does_not_recall_project_memory` 通过，断言未绑定流无 `memory(status=used)`；后端 `routes_conversations.py:111` 对空 project 不召回。 |
| 5. 刷新/重启后恢复项目、消息、记忆 | **代码/持久化 PASS；浏览器重启现场由主 Agent 复核范围外** | repository 测试覆盖 SQLite WAL/持久化；前端 `app.js:325-331,416-438` 支持稳定 `/c/{conversation_id}` 与加载历史。主 Agent smoke 验证消息流及项目数据持久化后删除临时项目完成清理。 |
| 6. 模糊/普通/分类不可用降级 | 部分通过，运行时阻塞 | `test_ambiguous_memory_is_not_saved` 通过并断言 `needs_confirmation`；`conversation_service.py` 有 `none` 分类，`routes_conversations.py:87-97` 有 `skipped/not_analyzed` 降级路径；本轮未运行服务验证 none 与分类器不可用现场表现。 |

## 主 Agent 受控部署运行时证据

主 Agent 在受控服务实例上完成以下复核，使用临时项目并在结束后删除，未留下持久测试数据：

| 验收项 | 结果 | 证据 |
|---|---|---|
| `GET /api/health` | PASS | HTTP 200 |
| 临时项目创建 | PASS | `POST /api/projects` HTTP 201 |
| 首条消息 SSE | PASS | `/tmp/spec022-sse`；事件顺序为 `meta → progress(memory_classification running/completed) → memory(saved/used) → progress(memory_recall running/completed) → progress(generation running/completed) → done(completed)` |
| 项目记忆保存/召回 | PASS | SSE 同时出现 `memory(saved)` 与 `memory(used)`，符合项目范围契约 |
| 临时数据清理 | PASS | `DELETE /api/projects/{id}` HTTP 204 |

说明：本 tester 子代理先前对 `127.0.0.1:8000` 的 HTTP 000 仅表示其隔离执行环境无法访问主 Agent 服务；结合上述主 Agent 受控部署证据，不构成产品阻塞。

## 契约与兼容核对

- SSE：`tests/test_conversations_api.py` 通过；后端 `routes_conversations.py:80-140` 生成 `meta`、三阶段 `progress`、`memory`、`token`、`error`、`done`，前端 `app.js:474-486` 解析并展示对应事件。
- 分页：repository/API 测试通过；前端 `app.js:378-406` 使用 `target_chars`、`before` 游标并在插入旧消息后恢复滚动锚点。
- 未绑定隔离：API 测试通过；服务端使用 owner 与 project 约束，空 project 不查询项目记忆。
- 旧聊天入口：`backend/app/api/routes.py:8-13` 仍同时注册 `routes_chat`、`routes_article` 和 `routes_conversations`；旧 `/api/chat`、`/api/agent/run` 声明仍存在（本轮按任务范围未重复运行其历史测试；Task02 测试报告记录旧兼容回归 16 passed）。
- 前端安全与资源版本：前端 conversation/paper 契约测试通过 29 项；`frontend/index.html` 的 `app.js/styles.css` 均为 `?v=26`，用户内容路径使用 `textContent`。

## 风险与阻塞

无产品阻塞。此前子代理环境的服务不可达已由主 Agent 受控部署复核覆盖；未执行独立浏览器点击，但前端静态契约、SSE 事件处理和稳定 URL/分页路径均通过，运行时 SSE smoke 已证明核心纵向闭环。

## 主 Agent 后续动作

1. 架构师复核本报告及主 Agent 运行时证据后签字。
2. 按 Spec022 收口流程更新状态台账；后续全量验收仍按 Spec 末期门禁执行。

## 签字

- 验收执行：tester（临时 Luna high）
- 架构师签字：待主 Agent 按收口流程确认
