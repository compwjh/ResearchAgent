# 任务 05 — 接入聊天与知识库 RAG 链路埋点

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02、04 ｜ 被依赖：任务 06、07 ｜ 当前状态：`待执行`

## 一句话目标

把任务 04 已实现的直连 Ollama 客户端和 Langfuse 埋点封装接入真实业务链路，使聊天和知识库问答都能形成完整 trace，同时保证观测关闭或故障时业务行为不变。

## 当前证据（2026-09-03）

- `backend/app/services/ollama_direct.py` 与 `backend/app/observability/` 已存在。
- `tests/test_ollama_direct.py`、`tests/test_observability.py` 共 28 个测试通过。
- `routes.py`、`services/ollama.py` 和 `services/kb/*` 已接入聊天、KB generation、embedding/retrieval 观测；双链路基准脚本及离线契约测试已存在。
- Task 04 真实上报门禁已通过：v4 `events_only/direct` 以 `events_full/events_core` 为权威落库表。
- 当前剩余范围是独立 `kb.rerank` 事件、观测故障隔离覆盖，以及真实聊天/KB 事件证据回填。

## 前置门禁

1. spec-013 需求评审与技术评审通过，且用户明确确认 spec。
2. 任务 04 完成真实 Langfuse 上报冒烟，确认 SDK v4 接口可用。
3. 执行前记录工作区状态；不得覆盖 spec-014 独立 worktree 的 reranker 实现。
4. 若需要与 spec-014 共同修改 KB 检索链路，只能基于双方明确 commit 集成，不复制脏工作树。

## 实施步骤

### A. 聊天链路

1. 在请求入口生成一次调用级上下文，记录模型、route、session 和请求开始时间。
2. `OLLAMA_ROUTE=langchain` 时保持当前 LangGraph/ChatOllama 行为，不改变默认返回协议。
3. `OLLAMA_ROUTE=direct` 时调用 `chat_direct()`，把 `thinking` 与 `content` 分开采集；对外仍按现有 SSE 事件格式输出正式内容。
4. 调用结束后使用 `record_ollama_generation()` 上报 prompt、正式输出、thinking、原生 timings 和派生指标。
5. 流式中断或 Ollama 失败时记录失败状态，但沿用现有业务错误处理，不让埋点异常覆盖原异常。

### B. 知识库 RAG 链路

6. 为一次 KB 问答建立根 observation，并在同一上下文中记录：
   - `kb.embedding`
   - `kb.retrieval`
   - `kb.rerank`（若能力存在；否则记录 skipped/degraded）
   - `kb.generation`
7. 阶段 span 记录耗时、模型、候选数、输出数、降级原因等结构化字段。
8. prompt 的组成按 spec 要求可回看，但必须遵守截断阈值；密钥、环境变量和本地绝对路径不得上报。
9. 保持现有引用、SSE、chunker v1/v2 隔离和 RRF 降级语义。

### C. 双链路基准

10. 提供独立基准入口，让同一问题按需依次执行 `langchain` 与 `direct`，输出两条链路的 TTFT、总耗时、服务端耗时和差值。
11. 基准入口不进入默认请求路径，避免正常请求执行两次。
12. 若采用 HTTP 端点，需在技术评审中固定路径、输入上限和仅本机访问约束；若采用脚本，需记录可重复命令和 JSON 输出结构。

## 子任务拆分与分派

所有代码任务必须在 spec 确认后先分派 `junior-dev`，每批最多两个文件、改动不超过 150 行：

1. 聊天路由与 route 切换：`backend/app/api/routes.py` + `backend/app/services/ollama.py`。
2. LangGraph 最小埋点适配：`backend/app/graphs/chat.py` + 对应测试文件。
3. KB embedding/retrieval 阶段：每批最多两个 `backend/app/services/kb/*.py` 文件。
4. KB generation/rerank 阶段：按实际稳定接口另拆一批，不能猜测 spec-014 的最终实现。
5. 双链路基准：单独一批，优先一个脚本或一个路由文件加一个测试文件。

架构师负责上下文边界、跨分支集成与最终读回；测试由 `tester` 独立执行。模型选择以执行时 `MODEL_REGISTRY.md` 和已注册模型为准。

## 测试与验收标准

| 场景 | 预期 |
|---|---|
| `LANGFUSE_ENABLED=false` | 不创建 client、不发网络请求，聊天与 KB 行为不变 |
| Langfuse 不可达 | 只记警告，业务返回不受影响 |
| `OLLAMA_ROUTE=langchain` | 保持现有默认链路和 SSE 契约 |
| `OLLAMA_ROUTE=direct` | 正式输出可用，thinking 单独记录，timings 完整 |
| KB 普通问答 | 一个 trace 中包含 embedding/retrieval/generation |
| KB 启用重排 | trace 额外包含 rerank；失败时记录 degraded 并回退 |
| 双链路基准 | 同一问题返回两条链路指标与差值，互不遮蔽错误 |
| 回归 | 全量测试不少于任务 03 的 253 个且无失败 |

## 风险与回滚

- 风险：直连路径与 LangGraph 的消息组装或 SSE 语义不一致。先用固定问题做对照，再开放 route 切换。
- 风险：观测上下文跨线程/流式生成丢失。测试必须覆盖流中断和并发请求。
- 风险：spec-014 同时修改 KB retrieve/routes。只接入明确 commit，并逐文件做语义冲突审查。
- 回滚：默认保持 `OLLAMA_ROUTE=langchain`，设置 `LANGFUSE_ENABLED=false` 可关闭全部埋点；必要时撤销本任务独立 commit。

## 产出物

- 聊天与 KB 链路的最小埋点改动及测试。
- 双链路基准入口与可重复结果。
- 一次聊天、一次 KB 问答的真实 Langfuse trace 证据。
- 本文档“执行结果”回填。

## 执行结果

### Task 05-R1（2026-09-03，junior-dev）

- 新增 `kb.rerank` 事件，覆盖成功、禁用/候选不足和异常降级；事件包含 `status`、输入/输出数量、启用状态及降级原因。
- 改动文件：`backend/app/services/kb/retrieve.py`、`tests/test_kb_observability.py`。
- 验证：`.venv/bin/python -m pytest -q tests/test_kb_observability.py` → `8 passed`，退出码 0。
- 结果：通过；排序、异常回退和业务返回语义未改变。

### Task 05-R2（2026-09-03，junior-dev）

- 补齐观测初始化异常、`LANGFUSE_ENABLED=false`、检索失败、生成失败和流式中断路径的隔离；`end_trace()` 失败不会改变业务结果或 SSE 契约。
- 改动文件：`backend/app/api/routes.py`、`tests/test_kb_ask_trace.py`。
- 验证：`.venv/bin/python -m pytest -q tests/test_kb_ask_trace.py tests/test_chat_route.py` → `15 passed`，退出码 0；全量 `.venv/bin/python -m pytest -q` → `322 passed`，退出码 0。
- 结果：通过；默认 `langchain` 路由及既有业务异常语义保持不变。

### 当前门禁

Task 05 已完成。真实聊天请求返回 SSE `done`；真实 KB 请求产生 `kb.embedding`、`kb.retrieval`、`kb.rerank`、`kb.generation` 事件。ClickHouse v4 `events_full` 事件汇总可查询，旧 `traces/observations` 为空不构成失败。

### 真实链路验收（2026-09-03）

- 聊天：`POST /api/chat`，模型 `qwen3.5:9b`，返回 `token`、`debug`、`done`，退出码 0；`events_full` 出现 `ollama-chat`。
- KB：`POST /api/kb/ask`，模型 `qwen3.5:9b`，返回检索引用与生成结果，退出码 0；`events_full` 出现 `kb.embedding`、`kb.retrieval`、`kb.rerank`、`kb.generation`。
- 查询：ClickHouse `SELECT name,count() FROM events_full GROUP BY name` 可见上述事件；服务端 MinIO bucket `langfuse/` 正常。
- 结论：Task 05 验收通过，可进入 Task 06/07。

### 双链路 A/B 基准入口（task-05，2026-09-03，junior-dev）

新增独立脚本 `scripts/bench_ollama_routes.py`，作为按需对比 `langchain` / `direct`
两条链路开销的基准入口。**不进入默认请求路径**：未改动 `backend/app/api/routes.py`，
正常聊天 / KB 请求仍只跑一次，本脚本仅在被显式执行时跑。

**命令行用法**（用项目解释器 `.venv/bin/python`）：

```
.venv/bin/python scripts/bench_ollama_routes.py                 # 默认 langchain,direct，各 1 轮
.venv/bin/python scripts/bench_ollama_routes.py --runs 3        # 每链路 3 轮取均值
.venv/bin/python scripts/bench_ollama_routes.py --json > bench.json   # 仅输出 JSON
.venv/bin/python scripts/bench_ollama_routes.py --routes direct,langchain --question "解释 RAG"
```

参数：`--question`（默认一句简短中文问题）、`--model`（默认取 `config.MODEL_NAME`）、
`--runs`（每链路重复次数，默认 1）、`--routes`（逗号分隔，默认 `langchain,direct`）、
`--json`（只输出 JSON，便于重定向）。非 `--json` 时先打印人类可读摘要表（每链路一行：
TTFT / 总墙钟 / load / prefill / eval / tokens/s），再打印 JSON。

**JSON 输出结构**（键名固定、可重复；单次异常记入该 route 的 `errors` 不中断）：

```json
{
  "question": "...", "model": "...", "runs": 1,
  "routes": {
    "langchain": {"samples": [ {"ttft_ms":…, "load_ms":…, "prompt_eval_ms":…, "eval_ms":…,
                                "total_ms":…, "overhead_ms":…, "client_wall_ms":…,
                                "tokens_per_sec":…, "is_cold_start":…} ],
                  "avg": {…同字段…}, "errors": []},
    "direct":    {"samples": [ … ], "avg": {…}, "errors": []}
  },
  "diff": {"ttft_ms":…, "client_wall_ms":…, "overhead_ms":…, "total_ms":…}
}
```

`diff` 语义固定为 **langchain - direct**（正数表示 direct 更快 / 中间层开销更大）；
`direct` 因无原生 timings 而 `total_ms=0` 时，对应项按数值如实相减，不伪造。
聚合逻辑抽成可导入纯函数 `bench_ollama_routes.run_benchmark(question, model, routes=…, runs=…) -> dict`，
测试 `tests/test_bench_routes.py` 通过 patch `backend.app.services.ollama.run_chat` 覆盖
结构契约、diff 语义、异常隔离与默认路由，7 个用例 0.23s 通过且不触达真实模型。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 对照现有代码确认链路尚未接入，补齐任务计划，状态保持待执行 |
