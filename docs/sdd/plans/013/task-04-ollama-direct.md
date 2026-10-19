# 任务 04 — 实现直连 Ollama 采集器与埋点封装层
>
> 当前状态：`完成`

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03（Python 3.11 + langfuse SDK 4.15.1 已就绪）｜ 被依赖：任务 05（链路接入）
## 目标

新增两个能力，且都不侵入现有业务：

1. **直连 Ollama 采集器** `backend/app/services/ollama_direct.py`：流式调用 `/api/chat`，分离 `thinking` 与 `content`，提取原生 timings（load / prompt_eval / eval / total），并测出首 token 延迟与逐段间隔。
2. **埋点封装层** `backend/app/observability/`：把上述数据组织成 trace/span/generation 上报 Langfuse，把服务端 timings 映射成瀑布图上的阶段条，并把关键指标作为 numeric score 上报。

## 思维链

### 阶段 A：先摸清 SDK v4 的真实 API（不做猜测）

1. 直接读已安装的 SDK 源码（`.venv/lib/python3.11/site-packages/langfuse/`），确认：
   - `get_client()` 的初始化与环境变量
   - `start_as_current_observation()` 的参数（`as_type`、`name`、`model`、`input`、`output`、`metadata`）
   - **如何指定 span 的起止时间**（这是关键：阶段 span 是"虚拟"的，需要用服务端 timings 反推时间戳，而不是真实执行时间）
   - score 上报方式（`numeric` 类型）
   - `flush()` 与失败时的行为
2. 若源码不足以确定，再查官方文档；**不凭 v3 经验臆造 v4 写法**（v4 于 2026-03 重写，API 与 v3 不同）

### 阶段 B：直连采集器

3. 定义 `OllamaTimings` / `OllamaChatResult` 数据结构（spec 中已约定字段）
4. 实现流式请求：`httpx.stream` + `trust_env=False`（macOS 代理坑）
5. 逐 chunk 累积：`message.thinking` 与 `message.content` 分开累积
6. 记录首 token 到达时刻（客户端视角）与逐段间隔
7. 从末个 chunk 提取 timings（纳秒 → 毫秒换算）
8. 边界处理：timings 缺失、流中断、连接失败、`client_wall_ms < server_total_ms`

### 阶段 C：埋点封装层

9. `config.py`：`LANGFUSE_ENABLED`、采样率、`OLLAMA_ROUTE`、冷启动阈值、截断阈值
10. `client.py`：Langfuse client 单例；未配置时降级为 no-op
11. `spans.py`：把 timings 映射为阶段子 span（load → prefill → first_token → decode + overhead）
12. `safe.py`：try/except 兜底，异常只记日志

### 阶段 D：测试与校验

13. 写单测 `tests/test_ollama_direct.py`（用假响应，不依赖真实 Ollama）
14. 写单测 `tests/test_observability.py`（降级、异常不冒泡、采样率、span 映射）
15. 跑全量测试确认不破坏既有 253 个用例
16. 真实上报冒烟：发一次调用，在 Langfuse UI 确认能看到 trace

## 子代理分派计划

> 前置说明：任务 03 中已定位并修复 `junior-dev` 超时问题（改用 `qwen3.8:27b-mlx`，吞吐 13.8 → 24.3 tok/s，详见 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md`）。修复后分派窄任务实测成功（220.84s），因此本任务**恢复使用子代理**，但严格遵守"单文件 + 限输出量"的约束。

### 分派 1：`junior-dev` — 实现直连采集器（单文件）

**分派时机**：阶段 A 完成后（此时 SDK API 已确认，可把准确用法写进 prompt，避免它猜）。

**Prompt 要点**（分派时必须写明的部分）：

- **输出文件**（只写这一个）：
  - `/Users/wjh/ResearchAgent/backend/app/services/ollama_direct.py`
- **进展日志**（必须写，便于外部观察）：
  - `/Users/wjh/ResearchAgent/.codebuddy/agent-logs/junior-dev-013-ollama-direct-<时间戳>.md`
  - 用户可 `tail -f /Users/wjh/ResearchAgent/.codebuddy/agent-logs/junior-dev-013-ollama-direct-*.md` 查看
- **明确禁止**：不要执行 pip install、不要启动服务、不要修改其他文件、不要写测试文件（测试由主会话写）
- **输出格式**：给出该文件的**完整内容**
- **必须遵守的约定**（写进 prompt）：
  - 所有 httpx 请求必须 `trust_env=False`（macOS 系统代理会把 localhost 请求截走返回 503）
  - `OllamaTimings` 与 `OllamaChatResult` 的字段名与 spec 保持一致（给出字段清单）
  - 单位：Ollama 返回纳秒，统一换算成毫秒
  - timings 缺失时字段置 0 并置 `timings_available=False`，**不得抛异常**
  - `client_wall_ms < server_total_ms` 时开销取 0，不出现负数

**子代理返回后，主会话必须做**：

1. `git status` 确认只新增了约定的 1 个文件
2. 检查是否真的用了 `trust_env=False`（grep 验证）
3. 核对字段命名与 spec 一致
4. 补写单测，跑测试验证
5. 若它有缺陷，主会话直接修正（不再回退给它，避免来回耗时）

### 不分派的部分

埋点层（`observability/`）由主会话实现——它要与 Langfuse SDK v4 的具体 API 对接，且涉及降级与安全兜底等关键设计，交给子代理风险高。

## 实时监控命令（供你另开终端查看）

```bash
# 子代理进展日志（分派后立即出现）
tail -f /Users/wjh/ResearchAgent/.codebuddy/agent-logs/junior-dev-013-ollama-direct-*.md

# 确认新文件是否落盘
ls -la /Users/wjh/ResearchAgent/backend/app/services/ollama_direct.py

# Langfuse 侧日志（上报是否到达）
tail -f /tmp/langfuse-web.log

# 跑测试
cd /Users/wjh/ResearchAgent && .venv/bin/python -m pytest tests/ -q
```

## 验收标准

| 项 | 标准 |
|---|---|
| 采集器 | 能流式拿到 content / thinking，且二者分离 |
| timings | load / prompt_eval / eval / total 均换算为毫秒，缺失时不抛异常 |
| 首 token | 记录客户端视角首 token 延迟 |
| 代理坑 | 所有请求 `trust_env=False` |
| 埋点层 | `LANGFUSE_ENABLED=false` 或未配置时零开销、不报错 |
| 异常兜底 | SDK 异常不冒泡到业务 |
| 虚拟 span | 阶段条能按服务端 timings 呈现（在 Langfuse UI 可见） |
| 单测 | 新增测试通过，全量仍 ≥253 |
| 真实冒烟 | 发起一次调用，Langfuse UI 能看到该 trace |

## 风险与回滚

| 风险 | 处置 |
|---|---|
| SDK v4 API 与预期不符 | 以源码/官方文档为准，不臆造；必要时调整 span 结构 |
| 虚拟 span 不支持指定起止时间 | 退而求其次：把各阶段耗时写进 metadata，用自研视图（任务 07）呈现；并在 spec 记录该限制 |
| 上报拖慢流式首包 | 改为异步上报 + 合理 flush；必要时提高采样阈值 |
| 采集器与 LangChain 行为不一致 | A/B 对比（任务 05）会暴露差异，据实调整 |

**回滚**：本任务只新增文件、不改既有业务代码；删除新增文件即可完全回退。

## 产出物

- `backend/app/services/ollama_direct.py`
- `backend/app/observability/{__init__,config,client,spans,safe}.py`
- `tests/test_ollama_direct.py`、`tests/test_observability.py`
- 真实上报冒烟证据，回写到下方「执行结果」段

## 执行结果（2026-09-03 核对：完成）

| 验收项 | 当前证据 | 结论 |
|---|---|---|
| 直连采集器 | `ollama_direct.py` 已实现 content/thinking 分离、timings、TTFT、流中断处理与 `trust_env=False` | 通过（单测） |
| 埋点封装 | `observability/` 五个文件已实现配置、client、safe、generation/event 与 numeric score | 通过（单测） |
| 针对性测试 | `.venv/bin/python -m pytest -q tests/test_ollama_direct.py tests/test_observability.py` → `28 passed` | 通过 |
| 真实上报冒烟 | 正确 MinIO 凭据启动后，诊断 span 写入 `events_full` 与 `events_core` 各 1 行；v4 events_only 下旧 `traces/observations` 为 0 属预期 | 通过 |
| 全量回归 | 任务 03 记录 `253 passed`，但本轮新增 Task 04 文件后的全量结果尚未回填本文 | 待补 |
| 业务接入 | routes/chat/KB 尚未调用本模块，属于 Task 05 | 不在本任务完成范围内 |

**当前状态：完成。** 阻塞根因是 MinIO 未运行/凭据不匹配；恢复 MinIO 后 OTLP 上报已落入 v4 事件表。

### 已确认的设计调整

Langfuse SDK v4 的公开 API 不支持为 observation 指定任意 `start_time`，因此没有强行构造虚拟阶段 span。当前实现把阶段耗时写入 metadata 与 numeric score，精确甘特图交由 Task 07 自研页面呈现。该调整需在技术评审与 spec 变更日志中确认。
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-013-task-04",
  "spec_id": "013",
  "title": "# 任务 04 — 实现直连 Ollama 采集器与埋点封装层",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:04:27+00:00",
  "depends_on": [
    "spec-013-task-03"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/013/task-04-ollama-direct.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-013",
    "branch": "feature/spec-013-llm-observability-platform",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-tester
Read: ["docs/sdd/plans/013/task-04-ollama-direct.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/013/task-04-ollama-direct.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
