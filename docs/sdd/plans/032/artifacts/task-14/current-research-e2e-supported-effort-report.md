# BLOCKED — Spec032 真实自然语言 E2E（supported-effort run）

本轮真实自然语言主路径已到达计划批准、USENIX 2024 检索、评估和 5/5 论文导入，但最终任务为 `partial`，没有 Evidence Matrix 或 canonical ResearchReport。因此结论是 **BLOCKED**，不冒充 Spec E2E 全部通过，也不建议交给用户人工验收。

上一轮 `qwen3.5:9b/off` 的 `REASONING_EFFORT_UNSUPPORTED` 证据保持不变。本轮先只读确认 `/api/models` 后，按授权改用同一模型广告支持的请求级 `low`；全局模型仍未修改。

## Run identity and runtime

- `run_id`: `spec032-task14-supported-effort-20261008T211709Z`
- 当前部署：`HEAD 6bacc29`，端口 `8000`，restart session `2077`
- `/api/ready`：HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均 ready
- `/api/models`：HTTP 200；`qwen3.5:9b` 为 ready，广告档位包含 `low`
- 全局模型：`qwen3.8:27b`（未改变）
- 请求级模型/档位：`qwen3.5:9b` / `low`
- 任务开始：`2026-10-08T21:17:09.860800Z`
- 任务终态：`2026-10-08T21:18:37Z`，约 77.14 秒
- 未修改 `.env`、全局模型、阈值、旧任务；本轮受控导入正好 5 篇，没有超过上限。

## 自然语言入口

实际请求：

```http
POST /api/conversations/messages
Content-Type: application/json
```

```json
{
  "content": "请进行一次深度研究。主题是USENIX Security 2024中的security/privacy方法，目标是比较至少5篇方法与局限，并且最少选择5篇论文，最多选择5篇论文，目标论文数: 5，来源限定为USENIX Security，输出中文Markdown报告并使用行内引用。时间范围是2024-2024。",
  "model": "qwen3.5:9b",
  "reasoning_effort": "low"
}
```

HTTP 200，SSE 完整完成：

- conversation：`8373721f37b7426a94ee318e835a6e42`
- user message：`6de6e9c920434165a25644f502a05784`
- assistant message：`92aaad2928e74bbcae1e0ec52d0be3d1`
- `deep-research-orchestration` 激活成功；研究计划 processing step running → completed；Intake `missing=[]`。
- 返回 plan version `1`、hash `f7cdc582002b1c9ddbf086fe029a00bf55652d80168a218e2e39e3c7d28adcb8`，状态 `plan_pending_approval`。

## 预算门禁与批准

真实计划范围：

- `min_paper_count=5`
- `max_paper_count=5`
- `target_paper_count=5`
- `budget.target_paper_count=5`
- s1/s2 `max_results=5`
- source：`usenix`
- time range：`2024..2024`
- objective：`比较至少5篇方法与局限`

只发送一次批准：

```json
{
  "command": "approve_plan",
  "subject_version": 1,
  "scope_json": {
    "plan_version": 1,
    "output_hash": "f7cdc582002b1c9ddbf086fe029a00bf55652d80168a218e2e39e3c7d28adcb8"
  },
  "idempotency_key": "plan-approval:85c550c81f1a4d97bd44d0242b9f6c34:1"
}
```

响应 HTTP 200，approval=`approved`，创建：

- research session：`85c550c81f1a4d97bd44d0242b9f6c34`
- intake draft：`ab94b6c61f244f809bc291627ae9a2fb`
- approval request：`ba29f40a0fc04f7fbb7d44fbbb6b4499`
- research task：`2761a22515d5509d8e846debd7a05df5`

## 异步真实阶段

按约 20 秒边界读取 task/events，task GET 和 events SSE 均为真实部署响应：

1. s1 `search_catalog` completed，resolved model `qwen3.5:9b`，search ID `dd9fb8065b854903924ccf8b9f2cffb9`；事件摘要报告 5 篇候选。
2. s2 `search_catalog` completed，resolved model `qwen3.5:9b`，search ID `3f2ddaa5379f4948a4feb60506061b01`；事件摘要报告 8 篇候选，尽管计划 `max_results=5`，该观察已原样记录，最终选择和导入仍为 5。
3. e1 `evaluate_papers` 运行并在工作项表中为 completed；只读 DB 摘要显示其 output_json 未落到 work item，但存在 checkpoint，checkpoint 输出形状含 `candidate_id`、`evidence_refs`、`keep`、`output_hash`、`reason`、`relevance_score`、`safe_summary`、`schema_version`、`source_refs`。不把此形状解释为完整评估成功。
4. c1 `check_coverage` failed，真实错误 `UPSTREAM_WORK_ITEM_FAILED`。
5. syn `synthesize_preliminary_report` failed，真实错误 `UPSTREAM_WORK_ITEM_FAILED`；本轮没有完成的 synth input/output 或 `matrix_context` 可记录。
6. terminal event：`status=partial`、`selected_count=5`、`error_code=AGENT_OUTPUT_INVALID`；task runtime `last_error_code=UPSTREAM_WORK_ITEM_FAILED`、retry_count=0。事件中出现的 retryable `TRACE_PROJECTION_FAILED` 仅是投影帧，不是终态错误。

未进行额外模型探针或同一 task 重试；任务已经明确进入 partial 终态。

## 五篇选择与自动导入

`GET /api/research-tasks/2761a22515d5509d8e846debd7a05df5/acquisitions` 返回 HTTP 200：batch `2a9d69bb-0811-45d0-a02b-2a5639022cd1`，selection version `1`，5/5 items 和 links 均 `completed`。

| candidate ID | paper/document ID | import item ID | 论文 | 状态 |
|---|---|---|---|---|
| `4e6322a23b92a271dbec9906c51fe0ab` | `a151fcff09944e7cbd1f4086376ae914` | `36ae8411-935c-4b00-813c-5f6eca6b614b` | GhostRace: Exploiting and Mitigating Speculative Race Conditions | completed |
| `57e0402f82fe2ce354bea423b201fde3` | `527fe0c1515d48c78adec8f4eb7f4979` | `873aee35-3038-4c0d-88b7-0ec75e44fed1` | DNN-GP: Diagnosing and Mitigating Model's Faults Using Latent Concepts | completed |
| `9793a4a35caad52ee99f926ae7c90810` | `929a342c0b8d4c8283198751cae9b327` | `ffdfc6ea-94bb-42ad-bb74-13d7223d1b7c` | Cascade: CPU Fuzzing via Intricate Program Generation | completed |
| `bb826cac3486a295d93eb9b6cea0a6f8` | `fa82faf63802431da803e1a99ce1411b` | `7e5bdbb1-627a-4c20-986e-23d7d95828d4` | DARKFLEECE: Probing the Dark Side of Android Subscription Apps | completed |
| `ef9e0846844e5b02834163586ea6ddc9` | `56fc315e952342158e5ae2f5ef6f01a0` | `ed700701-a3ef-4304-928a-3968f21d9b7a` | Stop, Don't Click Here Anymore: Boosting Website Fingerprinting By Considering Sets of Subpages | completed |

这证明了本轮 5 篇受控候选已自动导入；它不证明报告合成成功，也不把 item 元数据当作 PDF 全文或 canonical report。

## Evidence Matrix 与报告产物

- `GET /api/research-tasks/2761a22515d5509d8e846debd7a05df5/evidence-matrix` → HTTP 409，`MATRIX_NOT_READY`。
- `GET /api/research-tasks/2761a22515d5509d8e846debd7a05df5/report` → HTTP 409，`REPORT_NOT_READY`。
- canonical `/reports/1?format=json` → HTTP 404，`REPORT_NOT_READY`。
- canonical `/reports/1?format=markdown` → HTTP 404，`REPORT_NOT_READY`。
- canonical `/reports/1?format=html` → HTTP 404，`REPORT_NOT_READY`。
- `GET /api/research-sessions/85c550c81f1a4d97bd44d0242b9f6c34/artifacts` → HTTP 200，`artifacts=[]`。
- canonical 标题、正文长度、引用数量、查看/下载路径：均不可提供（不存在）。

因此没有最终报告字数、标题或引用数；不能以 5 篇导入、candidate IDs 或 artifacts 元数据替代完整 ResearchReport。

## 失败边界与最小建议

本轮实际失败链为：`e1` work-item 输出持久化/契约状态异常（工作项 completed 但 `output_json` 缺失）→ `c1`/`syn` `UPSTREAM_WORK_ITEM_FAILED` → terminal `AGENT_OUTPUT_INVALID` → `MATRIX_NOT_READY` → canonical `REPORT_NOT_READY`。这是基于公开事件和只读 SQLite 结构摘要的事实，不推断隐藏推理内容。

建议 backend-dev / research evaluator-orchestrator 核对 evaluator 输出持久化与 c1/syn 上游错误传播，修复后重新部署再启动全新 run；保持 `min=max=target=5`、USENIX 2024 来源限制和严格 matrix validator，不用 artifact 元数据、放宽校验或重试旧 task 冒充成功。

## 验收准备度（10 项）

1. 当前服务可访问：**PASS**（ready HTTP 200）。
2. 真实自然语言入口成功：**PASS**（新 conversation，SSE Intake/plan 完成）。
3. 自然语言参数正确解析：**PASS**（missing=[]，计划 min/max/target/budget 均 5）。
4. 任务实体状态推进：**PASS**（plan approved，planning → running → partial；检索/评估事件可追踪）。
5. 前端处理中提示：**FAIL**（本轮仅用 API，未验证前端显示）。
6. 用户知道何时等待：**FAIL**（未验证 UI；最终未产生成功报告等待条件）。
7. 核心业务产物真实生成：**FAIL**（matrix 与 canonical report 缺失）。
8. 失败有可操作恢复：**FAIL**（记录了 partial/error，但未验证可恢复到 canonical report）。
9. 页面与 API 状态一致：**FAIL**（前端未运行；仅确认 session/task 为 partial）。
10. 无上下文人工步骤可复现：**FAIL**（成功产物查看/下载路径不存在）。

准备度为 `4/10`，且存在核心产物阻塞；不能交付人工验收。

## 本轮日志与证据

- 结构化证据：[current-research-e2e-supported-effort-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-supported-effort-evidence.json)
- 本轮日志：`/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/tester/20261009-051626.md`
- 原 `off` 失败证据：[current-research-e2e-required-matrix-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-required-matrix-report.md)
- 更早冻结 run 证据：[current-research-e2e-frozen-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-frozen-report.md)

本报告不声称 canonical JSON/Markdown/HTML 成功，不声称报告有字数/标题/引用数量，也不把本轮 partial 结果冒充完整 Spec E2E。
