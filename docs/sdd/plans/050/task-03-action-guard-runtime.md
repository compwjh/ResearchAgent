# Task03 执行防护与确认后端

关联：[Spec050](../../specs/050-agent-safety-and-factuality.md) · [任务索引](README.md)

> 状态与结果回填由主会话代行（纯文档/配置改动，无代码文件）；代码改动由 `backend-dev` 完成，回归由 `backend-tester` 承担，主会话读回文件并落地校验。Spec050 整体已补正为「实施中」（Gate 1/2 正式评审仍未执行），本条只记录 Task03 实现与定向验收结论，不代表 Spec 级验收签字。

依赖：Task02。当前状态：已完成（实现 + 定向验收 + 真实部署 API E2E）。

## 目标、数据与接口

在实际分发前校验服务端授权与目标；实现单动作确认、消费、取消和恢复；发布独立安全事件。范围限工具、研究分发和必要 API/存储。

## 分派与边界

角色：backend-dev / backend-reviewer / backend-tester。模型与预算引用 Spec 执行配置和当次用户指派。只读取本任务契约、相关路径及直接依赖产物。涉及前后端分别分派。改动及交接结果需读回核对。

## 验收与回滚

正常动作可执行；注入、权限撤销、重放和并发均不能导致未授权执行；故障停止敏感动作。

发现缺陷先定向修复。发现超范围需求退回 Spec 评审。候选验证失败时维持既有可用版本与硬安全约束，记录具体阻塞。

## 产物、结果与变更

### 实现文件

- `backend/app/guard/`：`contracts.py` 增 `TaskScope.allow_read_only`；新增 `runtime.py`（服务端默认策略：`activate()` / `ensure_active()` / `default_capabilities()` / `default_hosts()`）；既有的 `service.py`、`store.py`、`hooks.py`、`signals.py`、`sources.py`。
- 三个分发收敛点接线：`backend/app/skills/tool_dispatch.py`、`backend/app/research/application/agent_runtime.py`、`backend/app/paper_discovery/application/worker_tool.py`；补齐 `backend/app/research/application/search_catalog_adapter.py` 的绕过点。
- 端点：`backend/app/api/routes_guard.py` 新增 `GET /api/guard/stream`（`id:` / `event: guard` / `data: guard-event-v1`，支持 `Last-Event-ID` 增量与心跳）。
- 测试：`tests/guard/test_runtime_scope_activation.py`、`test_guard_event_stream.py`、`test_guard_api_end_to_end.py`（按功能命名，不含 spec/task 编号）。

### 本次修好的真实问题

1. `register_scope()` 运行时零调用、启用后全量 `SCOPE_MISSING`：新增服务端默认策略，在分发收敛点 `check()` 前调 `ensure_active()`；`hooks.check()` / `service.authorize()` 的 fail-closed 语义保持不变。
2. `bind()` 无真实 owner/task 来源：owner 复用 `memory.repository.OWNER_ID`，默认 task 为 `local-session`；已显式绑定的 task 不被覆盖，线程池 ContextVar 传播保持。
3. worker 路径只 `check()` 不 `record_outcome()`：补齐执行后消费，且 `record_outcome` 先于 `reset`。
4. `search_catalog_adapter.py` 直接调 `worker.discover()` 绕过校验：补执行前检查与 finally 归还，blocking 时走既有 `SOURCE_UNAVAILABLE` 降级。
5. 前端面板 `root.hidden=true` 永不解隐藏、无 SSE：见 Task04 回填。

### 验证（命令 / 退出码 / 结果）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `pytest -q tests/guard` | 0 | `45 passed` |
| `pytest -q tests/guard tests/frontend/test_guard_activity_contract.py` | 0 | `60 passed` |
| `pytest -q tests/skills tests/paper_discovery tests/research tests/conversation`（默认关闭） | 0 | `2281 passed, 38 subtests passed` |
| `ruff check <改动面 11 文件>` | 0 | `All checks passed!` |
| `node --check` / `scripts/check_test_layout.py` / `git diff --check` | 0 | 通过 |
| 真实部署 `GET /api/guard/stream` | 200 | `text/event-stream`，7 个 `event: guard` 帧 |

受影响领域合计 **2326 passed / 0 failed**；全量 `ruff check .` 的 57 项均落在未改动的既有文件，与本次改动无关。

### 运行时验收与回滚证据

- 服务：`http://127.0.0.1:8317`（`GUARD_ACTION_AUTHORIZATION_ENABLED=true`；默认 8000 已被既有服务占用，故另选可用端口）。`/api/health`、`/`、`/assets/guard-activity.*?v=2`、`/api/guard/*` 全部 200。
- 真实 API E2E 成功案例（请求 / 响应 / `action_ref` / `args_hash` / 最终状态 / 产物路径）：`runs/task-03/api-e2e-success-case.json`；5 个 HTTP 请求全 200，覆盖确认 → 允许 → 消费、刷新恢复、注入案例、检测器故障降级。
- 回滚：`tests/guard/test_guard_api_end_to_end.py` 的关闭开关场景证明默认关闭时同一工具不产生 pending、保留既有行为；后端 2326 用例回归亦在默认关闭下完成。开关默认关闭，回滚即不设置 `GUARD_ACTION_AUTHORIZATION_ENABLED`。

### 已知限制（不扩大到本 Task 范围）

- 单机单 owner；未显式绑定会话入口时共用 `local-session` 作为 task_id，任务级隔离留待 Task05/08 按 `conversation_id` 扩展。
- 风险信号按 task 聚合历史故障，检测器恢复机制由 Task08 PIGuard 接入时定义（E2E 用独立 task 隔离故障场景）。
- 默认策略空白名单时不做主机限制，敏感动作仍必须用户确认。
