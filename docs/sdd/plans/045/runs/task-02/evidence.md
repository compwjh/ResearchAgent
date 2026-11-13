# Task 02 验收硬前置证据（接手机器，2026-11-08）

> 接手机器：**Apple M3 Max / arm64**，brew `/opt/homebrew`，磁盘可用 297Gi。
> 与交接文档描述的发送方（x86_64、brew `/usr/local`、磁盘仅剩 2.1Gi）不同；
> 发送方的两大阻塞（events_only 404、Next .next 撑爆磁盘）在本机均不成立。

## 1. Langfuse 栈（v4.27.0，dual 模式）

```
bash deploy/langfuse/start-infra.sh   → 8123 ClickHouse / 5432 PostgreSQL / 6379 Redis / 9002 MinIO 全 [OK]
bash deploy/langfuse/start-langfuse.sh → Node v24.19.0 / pnpm 11.22.0，web :3000 + worker :3030 LISTEN
GET /api/public/health                 → 200
GET /api/public/traces?limit=2         → 200（dual 模式已解除 events_only 404）
GET /api/public/scores?limit=2         → 200
```

`.env` 已含 `LANGFUSE_MIGRATION_V4_WRITE_MODE=dual`；根 `.env` 的
`LANGFUSE_PUBLIC_KEY/SECRET_KEY` 与 `vendor/langfuse/.env` 的初始化密钥逐字一致。
主服务由 `launchctl` 托管 label `com.researchagent.recovery8000`，重启后 PID 37370，
`/` 与 `/api/health` 均 200；SDK `langfuse==4.15.1` 重新初始化成功。

## 2. 可复现样本（Q10 前置）

```
LANGFUSE_*=.env 值  .venv/bin/python scripts/generate_observability_fixtures.py --send
→ EXIT=0，sample_count=20 / success_count=16 / failure_count=4 / sent_count=20
→ fixture_id=spec013-task06-20261108T060158Z
```

Langfuse `GET /api/public/traces` 可查到 3 条最新 `spec013-task06-fixture`，
`totalItems=316`（发送样本后）。产物：`fixtures-send.json`。

## 3. 真实端到端对话（非 mock，Q10 证据 ③）

```
POST /api/conversations/messages  {"content":"用一句话说明什么是可观测性。",
  "reasoning_effort":"off","model":"qwen3.8:27b","mode":"normal"}
→ HTTP=200 bytes=6558；帧型 meta 1 / progress 5 / token 28 / done 1，无 error
→ status="completed"，duration_ms=28031.59
→ conversation_id=7bc9ffdcaabb4cdfaaa065592902045b
→ assistant_message_id=c8e39f8e1871495b9f2311d50fbdcfa2
→ trace_id=98b91aa39d22b54a50f6dba1364eccdd（name=ollama-chat）
```

> 首次用 `qwen3.5:9b` 失败：该模型能力缓存 `supported_efforts=[low,medium,high,xhigh]`
> **不含 `off`**，返回 `REASONING_EFFORT_UNSUPPORTED`。改用 `qwen3.8:27b`
> （缓存含 `off`）后成功。此为调用参数问题，非功能缺陷；失败原始输出保留在
> `real-chat-sse.txt` 的前一版记录说明中，成功版本覆盖该文件。

`GET /api/public/observations?traceId=98b91aa3…` → 200，**5 条 observations**：

| type | name |
|---|---|
| GENERATION | `ollama-chat` |
| SPAN | `phase:prefill` |
| SPAN | `phase:load` |
| SPAN | `phase:overhead` |
| SPAN | `phase:decode` |

四段 phase span 齐全，构成 Q10 ③ 的「完整 trace」证据与 ④ 的时间轴顺序依据；
瀑布图**浏览器截图仍待 Task 08 采集**。
**脱敏说明**：Langfuse 原始响应含系统提示与召回历史明文，按 spec-045 F12
口径已替换为结构摘要 `trace-summary.json`（仅保留 ID / 名称 / 计时 / token 数 /
input-output 字符数），原始 `trace-detail.json` 与 `observations.json` 已删除，
不入库、不留存明文。产物：`real-chat-sse.txt`、`trace-summary.json`。

## 4. 真实评测产物（Q10 证据 ②）

```
LANGFUSE_*=.env 值  .venv/bin/python -m backend.eval_042.cli --export \
  --output-dir docs/sdd/plans/045/runs/task-02/eval-baseline --task chat_quality --max-items 3
→ EXIT=0，status=completed，scored=2 / written=2 / verified=2 / skipped=1 / failed=0
→ report.json + report.md + .report.writer.lock（文件锁真实生成）
```

`report.json` metadata 五类指纹全部存在：

```
dataset_sha256    = 19f49906f5e105ff255f641eab3c0380354689e58150e453fdaf668664977bfb
judge_model_digest= 888f03bdc66326065533f76c1b66ea0878331d271f3f8179ee2df54ccf791db8
prompt_sha256     = c77ee587c9fb237d0c14bbd63a266036ce458dba7d8800926a21dda6d1d272d8
seed              = 42
tie_break_rule    = majority_label: among labels tied at the top count, prefer the label ...
```

`GET /api/public/scores?limit=5` 可见真实回写：
`eval042-688cb81c…`(value 0)、`eval042-24ab881c…`(value 1)，`totalItems=979`。

## 5. score 幂等真实验证（Task 04 加固项 08）

同一命令以 `--output-dir …/eval-rerun` 重跑：`EXIT=0`、同样的 2 scored / 2 written。
Langfuse `GET /api/public/scores?limit=100`：重跑前 `totalItems=979`，重跑后 `979`，
**delta=0，无新 `eval042-*` score**。幂等键在真实链路上生效。

## 6. 尚未完成（如实声明，不得判「已完成」）

- **Q10 证据 ④ 瀑布图截图**：四段 span 已可由 API 查证，但浏览器截图尚未采集。
- **Q10 证据 ① 红绿测试记录**：需 Task 08 汇总 03/04/09 项的先红后绿输出。
- **Task 07**：retention / `processing-steps` 分页 / `benchmark_summary` 死 UI
  三项均未落地（只读核实：backend 无 retention/VACUUM 命中、`get_processing_steps`
  无 cursor/limit、`benchmark_summary` 仅前端读取）。
- **Task 08**：真 SDK 并发/流中断测试、`--send` 与 dashboard 契约测试、最终全量回归、
  三份评审与双签均未完成。
- `human_agree_rate` 仍为 `null`、两套分数口径仍不统一（spec 已声明为 P2 边界，非缺陷）。

## 7. 接手基线（代码与测试）

```
.venv/bin/python -m pytest tests/evaluation/ tests/observability/ tests/platform/ -q
→ 214 passed，EXIT=0
```

代码接线只读核实（比交接文档第 3 节更新）：
- `backend/eval_042/runner.py:563` 已调用 `post_score_idempotent`（**Task 04 已收口**，非半完成）。
- `backend/app/platform/observability/spans.py:45-46,356,378-389,425-431,469-535`
  已接入 `redaction` / `ensure_request_id` / thinking 正文（**Task 06 已完成**，非骨架）。
- Task 03/05 的契约测试文档已回填执行结果。

即交接文档 `HANDOVER.md:34-38` 的 Task 04/06 状态已过时，
以 `spec-status-changelog.md` 最新条目与实际代码/测试为准。
