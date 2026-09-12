# Spec024 Task05 跨端最终验收报告

## 结果状态和摘要

**PASS with environment-deferred。** HEAD `b00e098` 已修复显式 `reasoning_completed` 终态缺陷，并迁移 13 项旧回归合同。主 Agent 在该 HEAD 执行的唯一一次全量 pytest 为 **1341 passed、1 skipped、47 subtests passed，退出码 0**；前端 96 项合同和 `node --check` 也通过。当前唯一延期项是固定 Ollama chat 推理通道连续超时，无法取得真实 xhigh/low/off 的阶段 telemetry；这属于环境阻塞，不再为超时修改业务代码。

验收没有修改业务代码，不修改测试断言，不执行 reset/stash/clean/push/merge。仅更新本报告、验收评审和复盘三份文档。Spec 是否允许以 environment-deferred 收口为“已完成”，交由架构师裁决。

## 验收范围与最新交接

- Spec：`docs/sdd/specs/024-visible-reasoning-controls.md`
- Task：`docs/sdd/plans/024/task-05-review-regression-deploy.md`
- 最新 HEAD：`b00e098 fix(spec024): align final regression contracts`
- 最新修复报告：`docs/sdd/plans/024/artifacts/task-05/repair-report.md`
- 后端最终复审：GO，P0=0、P1=0、P2=5（非阻塞）。
- 验收实例：`127.0.0.1:8010`，PID `43896`；默认 8000 已有 PID `31553` 占用，未触碰。

## 命令、退出码和结果

### 唯一一次全量 pytest（引用主 Agent 在最新 HEAD 的结果）

```text
.venv/bin/python -m pytest -q
```

- 退出码 **0**。
- 完整统计：**1341 passed, 1 skipped, 47 subtests passed**。
- 本轮不重复执行全量 pytest；此前 1326/14-failure 结果已由 `b00e098` 的终态修复和合同迁移闭环。

### 前端语法与合同

```text
node --check frontend/app.js
```

- 退出码 **0**，PASS。

```text
.venv/bin/python -m pytest -q tests/test_spec024_frontend_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_management_contract.py tests/test_frontend_paper_contract.py tests/test_frontend_skill_tool_contract.py tests/test_frontend_task05_repair_contract.py tests/test_frontend_task06_mobile_contract.py tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_task10_system_rule_contract.py
```

- 退出码 **0**，**96 passed**，PASS。

### 最新 fake adapter 定向复验

```text
.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_provider_failure_after_reasoning_completed_keeps_reasoning_completed tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics
```

- 退出码 **0**，**3 passed**。
- 修复报告另记录：合同迁移集合 57 passed；Spec024/backend/假适配器集合 55 passed、1 deselected；均退出码 0。

### HTTP health/home smoke

```text
curl -sS --max-time 10 -o /tmp/spec024-health-8010-latest.json -w 'health_http:%{http_code} bytes:%{size_download}\\n' http://127.0.0.1:8010/api/health
curl -sS --max-time 10 -o /tmp/spec024-home-8010-latest.html -w 'home_http:%{http_code} bytes:%{size_download}\\n' http://127.0.0.1:8010/
```

- 两个请求退出码均 **0**；health **HTTP 200**、327 bytes；home **HTTP 200**、35670 bytes，PASS。
- health 返回 `{"status":"ok", ...}`，模型列表包含 `qwen3.8:27b-mlx`。
- 验收实例实际端口 `8010`、PID `43896`，保持运行供用户/架构师复验；默认 8000 的已有进程未停止。

## 真实桌面 Chromium 检查

本 Task 已在 Codex In-app Browser（Chromium）打开 `http://127.0.0.1:8010/` 并记录以下证据；最新 HEAD 只改后端/测试/文档，未修改 `frontend/**`，故 v35 证据仍适用。

- DOM 实际解析到 `/assets/styles.css?v=35`、`/assets/app.js?v=35`，PASS。
- `#reasoning-effort-select` 存在，选项为 `off/low/medium/high/xhigh`，初值 `xhigh`，PASS。
- `#model-select` 可切换到固定 `qwen3.8:27b-mlx`。
- 能力探针不可用时前端安全降级为 `off` 并禁用其他档位；未静默冒充支持，PASS（环境阻塞路径）。
- 普通消息顺序合同：assistant bubble 挂载后，reasoning panel 插入 answer 前；错误/完成/中止都会停止 processing 动画并收敛终态，PASS（代码及静态合同）。真实模型不可达，因此不把真实 Chromium 消息发送记为 PASS。

## Ollama 固定 fixture smoke（环境延期）

固定模型：`qwen3.8:27b-mlx`；固定问题：`请用三点解释什么是向量数据库`。

- `curl ... http://192.168.31.180:11434/api/tags`：HTTP **200**，目标模型存在。
- `GET /api/chat/reasoning-options?model=qwen3.8%3A27b-mlx`：应用探针 15 秒无响应，HTTP **000**。
- 短预热请求（`think=false`、`temperature=0`、`num_predict=4`）：`request_sent_at=2026-09-12T03:06:41.300+08:00`，curl 退出码 **28**，20.003526s，0 bytes。
- 环境分类：**Ollama inference channel busy/unavailable**；tags/health 可达不等于 chat 推理可用。
- 因此 xhigh/low/off 的真实 SSE 阶段字段均记为 **deferred/N/A**：`reasoning_started_at`、首个过滤后非空 reasoning delta、`reasoning_completed_at`、`first_answer_token_at`、`done_at`、真实 `event_seq`、冷/热启动均未伪造。
- 复验步骤：确认 `192.168.31.180:11434/api/chat` 能在 20 秒内返回；先用固定问题执行一次 `think=false` 预热，再从 UI 分别选择 xhigh、low、off，记录 request_sent_at、各阶段时间、effort、event_seq 和 Ollama 忙状态。xhigh 首个真实 reasoning delta 需在预热后 20 秒内出现。

## Fake adapter 故障矩阵

以下使用临时 SQLite 和 `_message_stream`，不触碰真实数据库；SSE `seq` 为服务端 envelope 序号，DOM 终态按前端终态守卫记录。

| 场景 | SSE 序列（type:seq/status/code） | DOM 终态 | 持久化状态 | 结论 |
|---|---|---|---|---|
| started 无 delta，正常完成 | `meta:1 → progress:2/running → progress:3/completed → progress:4/running → reasoning_started:5 → reasoning_completed:6/completed → token:7 → progress:8/completed → done:9/completed` | completed；面板完成并折叠 | message completed；reasoning completed；content=`答案`；last_event_seq=9 | PASS |
| started 后失败（无 delta） | `meta:1 → progress:2/running → progress:3/completed → progress:4/running → reasoning_started:5 → progress:6/failed → reasoning_completed:7/failed → error:8/CHAT_FAILED → done:9/failed` | failed；动画停止 | message failed；reasoning failed；content 为空；last_event_seq=9 | PASS |
| 首 token 后 provider 失败 | `meta:1 → progress:2/running → progress:3/completed → progress:4/running → reasoning_started:5 → reasoning_completed:6/completed → token:7 → progress:8/interrupted → error:9/STREAM_INTERRUPTED → done:10/interrupted` | interrupted；面板中止并折叠 | message interrupted；reasoning completed；content=`首字`；last_event_seq=10 | PASS |
| 正文后断线（客户端 close，无可写终态） | `meta:1 → progress:2/running → progress:3/completed → progress:4/running → reasoning_started:5 → reasoning_completed:6/completed → token:7`，无 done/error | interrupted（EOF/无 done 收敛） | message interrupted；reasoning completed；content=`正文`；last_event_seq=7 | PASS |
| 重复/乱序 adapter event_seq | `meta:1 → progress:2/running → progress:3/completed → progress:4/running → token:5`；adapter seq=1 重复丢弃，seq=3 跳号后 `error:6/EVENT_SEQUENCE_GAP → done:7/failed` | interrupted（前端 gap 粘滞优先） | message failed；reasoning null；content=`第一`；last_event_seq=7 | PASS |
| 显式 reasoning_completed 后、首 token 前失败（修复后） | `meta:1 → progress:2/running → progress:3/completed → progress:4/running → reasoning_started:5 → reasoning_completed:6/completed → progress:7/failed → error:8/CHAT_FAILED → done:9/failed` | failed；不重复显示 reasoning 终态 | message failed；reasoning completed；content 为空；last_event_seq=9 | PASS |

最新新增用例 `test_provider_failure_after_reasoning_completed_keeps_reasoning_completed` 明确断言：只出现一次 `reasoning_completed(completed)`，随后 `CHAT_FAILED → done(failed)`，持久化 reasoning 仍为 completed，generation step 为 failed。

## Spec025 与机械收口检查

- `docs/sdd/specs/025-conversation-context-compaction.md` 仍为占位、状态 **待确认**，明确“不创建 Task、不写数据模型或公开接口”，PASS。
- `docs/sdd/plans/025/` **不存在**，PASS。
- 最新 HEAD 的改动未包含 Spec025 或上下文压缩入口，PASS。
- `git diff --check`：验收文档更新前后均退出码 **0**。
- 严格冲突标记检查（排除 `.git/.venv/.venv-py39.bak`）无真实 `<<<<<<<`、`=======`、`>>>>>>>` 标记；宽匹配命中两个既有文档分隔线，均非冲突标记。
- 本轮只新增/更新三份验收产物，未修改业务代码。

## 风险、阻塞与主 Agent/架构师后续动作

1. 验收结论为 **PASS with environment-deferred**；是否将 Spec024 状态从“实施中”改为“已完成”，由架构师依据项目收口门禁裁决。
2. Ollama chat 通道恢复后，补跑固定 fixture 的 xhigh/low/off 真实性能记录；不得以 fake adapter 或 tags 响应替代。
3. 若架构师要求“真实 smoke 必须完成才收口”，则保持 Spec024 实施中并仅补运行时证据，不需重新修改业务代码。

## 时间与统计

- 最新修复 HEAD：2026-09-12 03:32（Asia/Shanghai）。
- 本轮复验：2026-09-12（Asia/Shanghai）；未重复全量 pytest。
- 执行模型：临时 Luna high。
- 业务代码改动：0；验收产物改动：3 份指定文档。
