# Spec024 Task02 运行时 Go/No-Go 报告

## 结果状态和摘要

**CONDITIONAL GO。** 本轮仅修改了本报告和合同探针测试，没有修改 `backend/**`、`frontend/**`、真实数据库、Ollama 配置或部署。局域网 Ollama 可达，三模型的最小五档 HTTP 探针、临时数据库迁移回滚和协议参考测试均完成；当前业务实现缺口明确移交 Task03，不把未实现误判为运行时不可行：

1. xhigh 没有满足“响应字段 + server 日志 xhigh + evidence_id”的完整证据；`qwen3.8:27b` 的 `high` 明确被模板拒绝。
2. 现有 direct adapter/`run_chat` 只接受布尔 `think`，无法按合同透传 low/medium/high 字符串；LangChain 图只读取正文 `content`，丢失 `additional_kwargs.reasoning_content`。
3. 现有 SSE helper/会话路由没有 `message_id`、`event_seq`、UTC `timestamp` envelope，也没有 reasoning 事件或终态时长字段。
4. 现有观测 metadata 仍写入原始 `thinking` 文本；当前 schema 仍为 v6，没有生产 v7 一次性清理迁移。

因此允许启动 Task03 实现，但必须保留以下门槛：xhigh 在证据补齐前不得标记 supported/default；`qwen3.8:27b` 的 high 必须按模型级 unsupported 返回 409；Task03 完成统一 resolver、隔离、生产迁移和 SSE 后必须重跑本报告探针。

## 基线、范围和安全边界

- 分支：`feature/spec-024-visible-reasoning-controls-impl`
- 基线 commit：`53bc4c067ed423760715524d7f88b104aeffdc17`
- 项目 `.env` 的 Ollama 地址：`http://192.168.31.180:11434`
- 真实记忆库仅以 SQLite read-only URI 读取：`data/memory/memory.sqlite3`
- 真实库基线：schema `6`；`conversations=2`、`messages=26`、`processing_steps=37`、`raw_events=15`、`conversation_summaries=2`、`evolution_checkpoints=2`、`memory_analysis_jobs=8`、`memory_analysis_items=1`、`memory_evidence=2`、`projects=1`、`memories=4`、`system_rules=1`、`skill_improvement_proposals=0`
- `data/agent_tasks.sqlite3` 未触碰（仅记录为独立数据库，行数 5029）。
- 初次访问 `localhost:11434` 被沙箱阻止/随后连接拒绝；读取 `.env` 后对局域网地址执行探针并成功。未持续轮询 Ollama 日志；本机未发现可读的 Ollama server 日志文件。

## 一、真实 Ollama 五档探针

### 方法

每个模型每个档位发送一次最小请求：

```json
{
  "model": "<model>",
  "messages": [{"role": "user", "content": "Reply with exactly OK."}],
  "stream": false,
  "think": false | "low" | "medium" | "high" | true,
  "options": {"temperature": 0, "num_predict": 1}
}
```

HTTP 200 只表示 provider 接受了请求；支持判定仍遵循 Spec024：off 需无 `message.thinking`，low/medium/high 需字符串被接受且返回 thinking 或明确拒绝，xhigh 还必须有 server 日志中的 xhigh 证据。`provider_value` 与 `route_payload.think` 为本次真实发送值；`evidence_id` 是本报告内部引用。

| model | requested | provider_value | HTTP | response/message 字段与最小结果 | evidence_id | 合同判定 |
|---|---|---:|---:|---|---|---|
| `qwen3.8:27b-mlx` | off | `false` | 200 | response keys 含 `done`, `done_reason`, timings；message=`role,content`，content=`OK` | `OLLAMA-20260912-MLX-OFF` | 支持 |
| `qwen3.8:27b-mlx` | low | `"low"` | 200 | message=`role,content,thinking`，thinking=`The` | `OLLAMA-20260912-MLX-LOW` | 支持 |
| `qwen3.8:27b-mlx` | medium | `"medium"` | 200 | message=`role,content,thinking`，thinking=`The` | `OLLAMA-20260912-MLX-MEDIUM` | 支持 |
| `qwen3.8:27b-mlx` | high | `"high"` | 200 | message=`role,content,thinking`，thinking=`The` | `OLLAMA-20260912-MLX-HIGH` | 支持 |
| `qwen3.8:27b-mlx` | xhigh | `true` | 200 | message=`role,content,thinking`，thinking=`The` | `OLLAMA-20260912-MLX-XHIGH` | **不支持：缺 server xhigh 日志** |
| `qwen3.8:27b` | off | `false` | 200 | message=`role,content`，content=`OK` | `OLLAMA-20260912-27B-OFF` | 支持 |
| `qwen3.8:27b` | low | `"low"` | 200 | message=`role,content,thinking`，thinking=`The` | `OLLAMA-20260912-27B-LOW` | 支持 |
| `qwen3.8:27b` | medium | `"medium"` | 200 | message=`role,content,thinking`，thinking=`The` | `OLLAMA-20260912-27B-MEDIUM` | 支持 |
| `qwen3.8:27b` | high | `"high"` | 500 | `{"error": "... Unexpected reasoning effort high. Supported types are xhigh (default), medium, and low."}` | `OLLAMA-20260912-27B-HIGH` | **不支持：provider 明确拒绝** |
| `qwen3.8:27b` | xhigh | `true` | 200 | message=`role,content,thinking`，thinking=`We` | `OLLAMA-20260912-27B-XHIGH` | **不支持：缺 server xhigh 日志** |
| `qwen3.5:9b` | off | `false` | 200 | message=`role,content`，content=`OK` | `OLLAMA-20260912-9B-OFF` | 支持 |
| `qwen3.5:9b` | low | `"low"` | 200 | message=`role,content,thinking`，thinking=`Thinking` | `OLLAMA-20260912-9B-LOW` | provider 接受；需实现层证据 |
| `qwen3.5:9b` | medium | `"medium"` | 200 | message=`role,content,thinking`，thinking=`Thinking` | `OLLAMA-20260912-9B-MEDIUM` | provider 接受；需实现层证据 |
| `qwen3.5:9b` | high | `"high"` | 200 | message=`role,content,thinking`，thinking=`Thinking` | `OLLAMA-20260912-9B-HIGH` | provider 接受；需实现层证据 |
| `qwen3.5:9b` | xhigh | `true` | 200 | message=`role,content,thinking`，thinking=`Thinking` | `OLLAMA-20260912-9B-XHIGH` | **不支持：缺 server xhigh 日志** |

`GET /api/tags` 返回 200；服务端列出的目标模型均存在。`qwen3.8:27b` 的 tags 能力声明只有 completion，但实际 HTTP 探针仍接受 low/medium/xhigh；因此不能只依赖 tags 声明，必须保留逐档探针证据。

当前没有 `/api/chat/reasoning-options` 实现，故 `capabilities_source`、`cached_at` 和稳定的能力 JSON 目前均为 **unavailable**，不是可写入 `ollama_probe` 的生产能力缓存。

对当前本地 FastAPI 服务做只读 GET：`GET /api/chat/reasoning-options` 返回 HTTP `404 {"detail":"Not Found"}`；这与代码审计结论一致。`GET /api/conversations` 返回 HTTP 200，但本次服务实例返回空列表，未对其执行任何写操作。

## 二、LangChain/direct 推理提取与隔离

### 运行时探针

用假的 NDJSON 响应喂给现有 `ollama_direct._stream_chunks`，返回事件为：

```text
[{"type": "thinking", "content": "raw-thought"},
 {"type": "token", "content": "answer"}]
result.thinking == "raw-thought"
```

这证明 direct 采集器当前能识别原生 `message.thinking`，但它只是原始累积，没有 Spec024 过滤、NFC 规范化或 20,000 code point 截断。

代码审计证据：

- `backend/app/chat/application/chat_graph.py` 的 `ask_model` 只取 `chunk.content`，没有读取 `chunk.additional_kwargs.reasoning_content`。
- `backend/app/chat/application/chat_runner.py` 的 `_langchain_drive` 只转发 graph 事件并固定合成 `thinking=""`；`run_chat(..., think: bool=True)` 只表达布尔开关。
- `backend/app/platform/ollama_direct.py` 的 `think` 参数为 bool，当前 direct route 没有 `provider_value="low"/"medium"/"high"` 的参数接缝。
- `backend/app/platform/observability/spans.py::_build_metadata` 当前包含 `"thinking": _truncate(result.thinking, ...)` 和 `thinking_chars`。实测 fake result 的 metadata 仍出现 `thinking="raw-thought"`，违反“观测不含原始 reasoning”。
- `redact_prompt_messages` 可清空 Prompt 正文，但不能抵消上述 reasoning metadata 泄漏；记忆分析/长期记忆隔离也尚未有 reasoning 字段接缝可验证。

## 三、临时 SQLite schema v7 与清理/回滚

合同探针在 pytest `tmp_path` 创建独立 schema v6 文件，使用 SQLite `backup()` 生成备份并以 SHA-256 作为 `backup_id`，不打开真实库写连接。成功路径执行 `BEGIN IMMEDIATE`、创建 marker/preference、增加会话/消息推理字段、按 FK 顺序清理、置空 `memory_evidence` 引用、写 marker、写 schema 7 并提交。

### 清理矩阵（临时库实测）

| 表 | before | after | action | foreign-key/result |
|---|---:|---:|---|---|
| conversations | 1 | 0 | 物理删除 | 先清理依赖后通过 |
| messages | 1 | 0 | 物理删除 | 先清理 processing/analysis 后通过 |
| processing_steps | 1 | 0 | 物理删除 | CASCADE 依赖已清 |
| raw_events | 1 | 0 | 物理删除 | conversation 依赖已清 |
| conversation_summaries | 1 | 0 | 物理删除 | conversation 依赖已清 |
| evolution_checkpoints | 1 | 0 | 物理删除 | conversation 依赖已清 |
| memory_analysis_jobs | 1 | 0 | 物理删除 | user message 依赖已清 |
| memory_analysis_items | 1 | 0 | 物理删除 | analysis job 依赖已清 |
| memory_evidence | 1 | 1 | 保留正文，conversation_id/message_id 置 NULL | 记忆行保留，引用可空 |
| projects | 1 | 1 | 保留 | 未触碰 |
| memories | 1 | 1 | 保留 | 长期记忆未删除 |
| system_rules | 1 | 1 | 保留 | 未触碰 |
| skill_improvement_proposals | 1 | 1 | 保留 | 未触碰 |
| user_chat_preferences | 0→1 | 1 | 缺失 owner 以 xhigh 初始化 | 主键/默认值通过 |
| migration_markers | 0→1 | 1 | 写 `conversation_history_reset_v1` | before_counts_json、backup_id 已落盘 |

消息字段探针确认新增 `reasoning_content`、`reasoning_status`、`reasoning_started_at`、`reasoning_completed_at`、`first_reasoning_at`、`first_answer_token_at`、`reasoning_truncated`、`reasoning_chars`、`last_event_seq`；会话增加 `reasoning_effort`。

### 异常回滚矩阵

在以下每个阶段注入异常：`create-metadata`、`alter-conversations`、`alter-messages`、`delete-derived`、`delete-core`、`null-evidence`、`marker`、`version`。8/8 均回滚成功：schema 仍为 6、所有表计数和原始引用恢复、marker 表不存在；成功路径 schema 为 7 且所有保留行存在。测试没有代替生产迁移实现，生产库当前仍为 v6。

## 四、SSE envelope、event_seq 和终态

合同探针覆盖：

- 首事件必须具备 `type/message_id/event_seq/timestamp`；
- 重复或旧序号丢弃；
- `last_event_seq+1` 之外的缺口触发 `EVENT_SEQUENCE_GAP`；
- `done` 映射到 completed/failed/interrupted 后，终态事件全部丢弃；
- terminal 后不得重新接受 token/reasoning/error/done。

现有实现审计结果为 Task03 实现缺口（不构成 Task02 provider 可行性阻塞）：

```text
stream_event("meta", ...) ->
data: {"type":"meta", "project_id":..., "conversation_id":..., ...}
```

它没有 `message_id`、`event_seq`、`timestamp`。`routes_conversations._message_stream` 的 progress/memory/token/sources/done/error 也都直接调用该 helper；当前没有 reasoning_started/delta/completed，done 也没有 duration 字段。现有真实 helper 形状由 `tests/test_spec024_protocol.py::test_current_sse_helper_is_not_yet_v7_envelope` 固定记录为当前缺口。

## 五、定向测试

### 命令、退出码和结果

```text
PYTHONPATH=. /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/test_spec024_protocol.py
退出码 0；13 passed

PYTHONPATH=. /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/test_task10_backend.py -k 'role_aware_direct_payload_preserves_system_and_user_roles or observation_input_is_redacted_but_role_metadata_is_preserved'
退出码 0；2 passed，7 deselected

git diff --check
退出码 0；无空白错误
```

13 个 Task02 合同探针包括 1 组 event_seq/终态、1 组跨 chunk 过滤/NFC/Unicode 截断、1 组清理成功、8 组逐阶段回滚、1 组当前 SSE helper 缺口审计、1 组当前 LangChain/direct/observability 路径审计。没有运行全量回归。

## 决策依据、风险与阻塞

- **门禁诊断：原报告的“全合同 NO-GO”过于保守；按 Task02 的真实目标（provider 可行性、临时迁移可回滚、协议可测试）建议标记为“条件 GO”。** direct/LangChain/SSE/观测/schema v7 是 Task03 应实现的当前代码缺口，不是 Task02 要求在实现前已经存在的前置条件。
- 模型级 provider 矩阵已经足够冻结：`qwen3.8:27b-mlx` 的 off/low/medium/high 均 HTTP 200 且返回 `message.thinking`（off 除外）；`qwen3.5:9b` 的 off/low/medium/high 也均被 HTTP 200 接受且返回 `message.thinking`。这证明 provider 层可表达这些档位；应用层是否支持仍由 Task03 的统一 adapter resolver 验证，不能把当前 bool-only 接缝误写成已实现。
- xhigh 缺 server log 是**证据采集环境阻塞**，不是 provider 已拒绝或不可行：三模型显式 `think=true` 均 HTTP 200 并带 `message.thinking`；`qwen3.8:27b` 的 high 错误体还明确写出 `xhigh (default)`。但因 Spec024 的硬门槛要求 server-log xhigh，当前只能将 xhigh 记为 `conditional/pending-evidence`，不得标为 supported/default，也不得静默降档。
- `qwen3.8:27b` 的 high 应记录为**该模型的 model-level unsupported**（HTTP 500，模板明确拒绝），不应阻塞整个 Spec024；能力接口应对该模型排除 high，并在用户请求 high 时返回 409，而不是改成 medium/xhigh。
- Task03 缺口仍需列为后续实现/验收门槛：统一 string/boolean resolver、LangChain reasoning 提取与过滤、完整 SSE envelope/event_seq、观测 allowlist、schema v7 生产事务迁移。它们不应反向改变 Task02 的 provider 可行性结论。
- 风险：真实库存在 2 个会话和 26 条消息；本轮确认其 schema/count 未被改变，但生产 v7 尚未落地，不能在真实库上复用临时迁移脚本。

## 主 Agent 后续动作

1. 将 Task02 记录为**条件 GO**：冻结上述逐模型 provider 矩阵，明确 xhigh 为 `pending-evidence`；不要因为当前业务实现尚未完成而把 Task02 判为全局 NO-GO。若流程台账只能使用二值状态，则在备注中写清“GO 仅指进入 Task03 实现，xhigh 仍不可宣称支持”。
2. Task03 先实现统一 `resolve_reasoning_effort`（low/medium/high 字符串与 xhigh 条件证据），能力缓存必须按 model 返回集合；`qwen3.8:27b` high 的 409 行为必须保留。
3. 实现 LangChain/direct 共用的 reasoning extraction/filter/truncate，观测只允许 `reasoning_present`、过滤后字符数、状态和耗时；这些是 Task03 验收项，不是本次 Task02 provider 阻塞。
4. 以临时库测试矩阵为基础实现一次性 schema v7 事务迁移和完整 SSE envelope/event_seq；真实库执行前必须重新备份、落盘计数并做 dry-run。
5. 单独补采 xhigh server-log 证据（或由环境负责人提供等价的受信日志证据）。在证据补齐前，UI/API 不得把 xhigh 作为 supported/default；若环境始终无法提供日志，保持 xhigh pending/unsupported，但不回滚已确认的其他档位条件 GO。

## 产物、改动文件和执行统计

- 改动文件：
  - `docs/sdd/plans/024/artifacts/task-02/protocol-report.md`
  - `tests/test_spec024_protocol.py`
- 未改动：`backend/**`、`frontend/**`、`data/memory/memory.sqlite3`、`data/kb/**`、Ollama 模型/配置。
- 产物路径：本文件；合同测试见 `tests/test_spec024_protocol.py`。
- 执行时间：开始 `2026-09-11T23:54:00+08:00`（按任务接收记录，分钟粒度）；结束 `2026-09-12T00:24:00+08:00`；总耗时约 `30 分钟`。
- 执行模型：当前主 Agent 临时 `Luna high`；未启动子 Agent。
- Ollama 工具统计：`GET /api/tags` 1 次；目标模型 `POST /api/chat` 15 次；qwen3.8:27b high 错误体补采 1 次；direct synthetic stream 1 次。
- 工具调用统计：只读 shell/运行时检查、合同测试、`apply_patch`；无 reset/stash/clean/push/merge。
- token 统计：运行时工具未提供精确 token 计数，本报告不估算。
