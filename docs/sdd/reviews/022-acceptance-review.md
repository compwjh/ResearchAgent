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

---

# Spec022 Task03 验收评审

> 验收角色：tester（临时 Luna high）
> 关联：`docs/sdd/specs/022-project-conversation-memory.md`、`docs/sdd/plans/022/task-03-management-global-memory.md`
> 验收范围：Task03 后端管理/全局记忆、前端治理契约、Task02 受影响回归、旧聊天兼容及当前服务 API smoke；未运行全量 pytest。

## 结论：PASS（无 P0/P1/P2）

Task03 的受影响后端、前端和旧聊天回归均通过；当前工作树服务重启后，项目/全局记忆 CRUD、候选确认、版本化编辑、停用/删除/撤销、作用域召回、会话移动确认、项目级联删除和全局记忆保留均完成真实 API smoke。未发现 P0/P1/P2。此前前端评审记录的记忆治理导航键盘可达性问题已修复，并由新增契约测试覆盖。

## 执行信息

| 字段 | 结果 |
|---|---|
| 开始 | 2026-09-11 约 05:14 +0800 |
| 结束 | 2026-09-11 05:27 +0800 |
| 耗时 | 约 13 分钟（含一次运行服务版本校正与临时数据清理） |
| 业务代码修改 | 无；仅新增/更新验收报告与进度日志 |
| 模型 | 临时 Luna high（按主 Agent 分派） |
| token / 工具统计 | 当前子代理运行时不可用；真实命令与退出码如下 |
| 进度日志 | `.codebuddy/agent-logs/spec-022/task-03/tester/20260911-acceptance.md` |

## 定向测试与结果

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Task03 + Task02 后端及旧聊天 | `.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_api.py` | 0 | **36 passed in 4.29s** |
| Task03 + Task02 + 论文前端契约（含键盘激活修复） | `.venv/bin/python -m pytest -q tests/test_frontend_management_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_paper_contract.py` | 0 | **35 passed** |
| JavaScript 语法 | `node --check frontend/app.js` | 0 | PASS |
| 前端交互/PDF/渲染/runtime Node 合同 | `for test_file in tests/test_frontend_*.js; do node "$test_file" || exit 1; done` | 0 | **4/4 PASS** |

按 Task03 边界未运行全量 pytest、浏览器 E2E 或与本 Task 无关的领域测试。

## API smoke（当前工作树服务）

初次检查发现端口已有旧服务：health=200，但其 OpenAPI 仅暴露 `GET /api/memories`，与当前工作树不一致；已停止该项目 PID，并以 `RERANKER_ENABLED=false ./deploy/start.sh` 前台启动当前服务。重启后 health=200，OpenAPI 同时暴露 POST/PATCH/DELETE、confirm/disable/undo、evidence/source 端点。该环境校正未修改业务代码。

使用唯一 tag 的临时项目 A/B、global/project memory 和一条会话完成以下断言，全部通过；结束后项目、会话（随项目级联）和两条临时 global memory 均已清理，tag 查询无残留：

| 场景 | 结果 | 观察到的 HTTP/数据 |
|---|---|---|
| health | PASS | `GET /api/health`=200 |
| 项目创建 | PASS | A/B `POST /api/projects`=201 |
| global candidate → confirm | PASS | create=201；confirm=200，status=`active` |
| 记忆编辑版本化 | PASS | PATCH=200；返回新 `memory_id`，`supersedes_id` 指向旧记录，旧记录 status=`superseded` |
| 停用/删除/撤销 | PASS | disable=200；delete=204；undo=200，恢复 `active` |
| global/project 列表与召回 | PASS | 两作用域列表均返回对应记录；首条消息 SSE=200，meta/progress/memory/token/done 完整，global 与 project 各 1 条 `memory used` |
| 会话跨项目移动确认 | PASS | 无 `confirm_move` PATCH=409；带 `confirm_move=true` PATCH=200，项目 ID 切换到 B |
| 项目级联删除 | PASS | 删除附着会话的 B=204；会话 GET=404 |
| 全局记忆保留 | PASS | 删除 A/B 后 `GET /api/memories?scope=global&status=active`=200，临时 global memory 仍可见，随后清理=204 |
| 会话删除不联动记忆 | PASS | 补充 disposable 会话 SSE HTTP=200 且 `done=1`；DELETE conversation=204；关联 project memory GET=200；随后删除项目=204 清理 |

## 固定用户旅程与代码依据

| 验收点 | 判定 | 证据 |
|---|---|---|
| 项目与会话生命周期（创建、重命名/归档/恢复/删除、稳定 URL） | PASS | 前端管理动作 `frontend/app.js:495-559`；后端项目/会话 CRUD 与 restore `backend/app/api/routes_conversations.py:51-87,237-283`；`tests/test_conversations_api.py:72-110` 覆盖归档/恢复与稳定记录 |
| 绑定/解绑/跨项目移动确认及旧历史隔离 | PASS | `backend/app/memory/repository.py:306-354,418-431` 要求确认、记录 binding cutoff、清理旧项目 evidence 并按 `from_binding` 过滤；`tests/test_memory_repositories.py:159-177,196-206` 通过；真实 smoke 无确认 409/确认 200 |
| 全局/项目记忆隔离、优先级与治理 | PASS | recall owner + global/current project 且 global 优先 `repository.py:493-506`；前端 scope/status/filter/evidence/action `frontend/app.js:583-684`；后端 API `routes_conversations.py:293-380`；`tests/test_memory_repositories.py:54-82,180-193` 与 `tests/test_conversations_api.py:72-90,112-122` 通过 |
| 项目删除级联、全局保留 | PASS | 单事务项目删除 `repository.py:253-256`，FK cascade/schema v2 证据见 `repository.py:100-203`；`tests/test_memory_repositories.py:84-95,129-140` 通过；真实 smoke 已验证附着会话 404、global 仍在 |
| 会话删除不联动记忆 | PASS | repository 仅软删会话 `repository.py:356-359`；项目/记忆删除及版本撤销测试通过（`tests/test_memory_repositories.py:71-95`）。真实 smoke 的项目删除级联与全局保留不改变该单会话契约 |
| 前端安全/兼容 | PASS | Task03 前端评审确认 DOM/CSS/资源版本/XSS 通过；治理渲染器使用 `textContent`，版本 `?v=27`；新增键盘契约已覆盖记忆治理入口 Enter/Space 激活 |

## 风险与主 Agent 后续动作

1. 当前服务已由验收 session 启动并保持运行；主 Agent 收口时应确认端口/进程归属，并按 Spec022 收口规则决定是否复用或重启。
2. 本轮未做独立浏览器点击；运行时 API + 静态契约覆盖了项目级联、移动确认、记忆 evidence/governance 端点，后续若需 UX 级验收可在主 Agent 可见浏览器中补做。
3. 一次带较长临时 tag 的 disposable 首条消息在生成阶段达到客户端 90 秒上限，后续简化为 `hello` 重试在 45 秒内完成；对象均已清理。该次延迟未改变 CRUD/删除结论，但提示运行时模型响应耗时具有波动。
4. 不把本报告的定向通过当作 Spec022 完成条件；Spec 收口仍需最终全量回归、验收签字、状态台账更新、部署与运行时验证。

## 签字

- 验收执行：tester（临时 Luna high）
- 架构师签字：待主 Agent 按收口流程确认

---

# Spec022 Task04 后端验收章节

> 验收角色：backend-tester（临时 Luna high）
> 关联：`docs/sdd/specs/022-project-conversation-memory.md`、`docs/sdd/plans/022/task-04-memory-evolution-recall.md`
> 范围：Task04 后端精确测试、Task02/03 受影响后端回归、旧聊天兼容、Python 静态检查；未运行前端、全量回归或部署。

## 结论：PASS（后端定向范围）

Task04 精确测试 **34 passed**；纳入 `tests/test_chat_route.py`、`tests/test_api.py` 的受影响与旧聊天兼容回归 **50 passed**。`py_compile` 与 `git diff --check` 均退出码 0。未发现 P0/P1 阻塞项；worker 重启触发时机存在 P2 生命周期提示。

## 验收证据

- Raw append-only、重复 trigger 幂等、message/cursor/session 隔离：通过。
- v3 migration 原子性与半成品 fail-closed：通过。
- Map/Reduce 分批、checkpoint 重启、stale lease 接管、同 session mutex、失败 retry、1001+ 完整分页：通过。
- candidate evidence gate、evidence 原子回滚、correction `supersedes`、project 不升 global：通过。
- recall scope 隔离、memory/summary 独立预算、无匹配 summary 空结果、当前问题不重复 history：通过。
- worker enqueue、worker/初始化失败不阻塞 SSE：通过，HTTP 仍返回 `done=completed` 且 durable raw event 保留。

详细命令、退出码、测试名称、API/service smoke 与风险见 [`docs/sdd/plans/022/artifacts/task-04/acceptance-report.md`](../plans/022/artifacts/task-04/acceptance-report.md)。当前 tester 沙箱无法监听本机端口，外部 health/OpenAPI smoke 由主 Agent 在可部署环境补做。

## 主 Agent 后续动作

1. 完成可部署环境的 health/OpenAPI/最小临时项目与 SSE smoke，并清理临时数据。
2. 汇总跨端验收并由架构师签字；Spec 收口阶段继续执行全量回归、状态台账、部署与运行时验证。

## 签字

- 验收执行：backend-tester（临时 Luna high）
- 进展日志：`.codebuddy/agent-logs/spec-022/task-04/backend-tester/20260911-acceptance.md`
- 架构师签字：待主 Agent 按收口流程确认
