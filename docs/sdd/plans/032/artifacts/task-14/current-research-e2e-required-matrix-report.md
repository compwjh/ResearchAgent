# BLOCKED — Spec032 真实自然语言 E2E（required-matrix run）

本轮结论是 **BLOCKED**，不是 Spec E2E 成功。真实自然语言消息入口在模型档位前置阶段返回不可重试错误，未进入 Intake、研究计划、审批、候选评估、自动导入、Evidence Matrix 或 canonical ResearchReport。没有用省略 `reasoning_effort`、替换模型、重试同一 run 或测试替身来掩盖失败。

## Run identity

- `run_id`: `spec032-task14-required-matrix-20261008T210806Z`
- 当前部署：`HEAD 6bacc29`，`http://127.0.0.1:8000`，restart session `2077`
- 验收开始/结束：`2026-10-08T21:08:06.008126Z` / `2026-10-08T21:08:06.050391Z`（约 42.265 ms）
- `/api/ready`：HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均 `ready`
- 全局模型：`qwen3.8:27b`（未修改）
- 请求级模型/档位：`qwen3.5:9b` / `off`
- 未改 `.env`、全局模型、阈值、旧任务或旧 evidence；本轮未下载论文。

## 真实请求与响应

请求：

```http
POST /api/conversations/messages
Content-Type: application/json
```

```json
{
  "content": "请进行一次深度研究。主题是USENIX Security 2024中的security/privacy方法，目标是比较至少5篇方法与局限，并且最少选择5篇论文，最多选择5篇论文，目标论文数: 5，来源限定为USENIX Security，输出中文Markdown报告并使用行内引用。时间范围是2024-2024。",
  "model": "qwen3.5:9b",
  "reasoning_effort": "off"
}
```

HTTP status 是 `200`，但 SSE 真实事件如下（已省略无关时间字段，无隐藏推理内容）：

1. `meta`, `event_seq=1`：创建 conversation `292695bcfa444e849ebddbef809f7974`、user message `98ba7a2eec6c442581417eb29be1afde`、assistant message `68fbc49c27ed4f529a7ed58aea7d7701`，模型 `qwen3.5:9b`。
2. `error`, `event_seq=2`：`code=REASONING_EFFORT_UNSUPPORTED`，`retryable=false`，消息“当前模型不支持该推理档位”。
3. `done`, `event_seq=3`：`status=failed`。

只读复核：

- `GET /api/conversations/292695bcfa444e849ebddbef809f7974` → HTTP 200；会话仍为 `active`，持久化 `reasoning_effort=off`。
- `GET /api/conversations/292695bcfa444e849ebddbef809f7974/messages` → HTTP 200；user message 为 `completed`，assistant message 为 `failed`，`last_event_seq=3`，错误正文与 SSE 一致。
- `research_session_id`、`intake_draft_id`、`research_task_id`、search/batch/paper/document ID 均不存在。

## 计划门禁与异步阶段

自然语言正文明确要求：USENIX Security 2024、security/privacy、比较至少 5 篇方法与局限、最少/最多/目标均为 5、来源限定 USENIX Security、2024 年范围。由于模型档位前置失败，服务没有返回可审核 Intake/plan，因此本轮不能声称约束已被解析，也没有发出 `approve_plan`：

- `min_paper_count`: 未到达计划阶段
- `max_paper_count`: 未到达计划阶段
- `target_paper_count`: 未到达计划阶段
- `budget_target_paper_count`: 未到达计划阶段
- `approve_plan`: 未调用
- 15–30 秒异步轮询：未执行；没有 research task 可轮询

没有候选评估、选择、自动导入、论文下载、evidence matrix 或报告产物。前次 `current-research-e2e-frozen-*` 失败证据保持原样，未被本轮覆盖。

## 产物检查

| 产物 | 本轮结果 |
|---|---|
| 5 篇 candidate/paper/document IDs | 未创建 |
| 自动导入 batch | 未创建；公开 PDF 下载数为 0 |
| evidence matrix | 未到达，不能读取 |
| canonical JSON/Markdown/HTML | 未到达，不能读取 |
| session artifact / artifact download | 未创建 |

artifact 元数据没有被当作全文或报告成功；本轮也没有对旧数据做删除、重索引或重试。

## 验收准备度（10 项）

1. 当前服务可访问：**PASS**（`/api/ready` HTTP 200）。
2. 真实自然语言入口持久化新消息：**PASS**（新 conversation/message ID，HTTP 200）。
3. 自然语言参数正确解析：**FAIL**（在 Intake 解析前模型档位前置失败）。
4. 研究实体状态推进：**FAIL**（没有 session/task）。
5. 前端处理中提示：**FAIL**（本轮在 API 入口即终止，未到产品处理态）。
6. 用户知道等待条件：**FAIL**（未产生等待阶段，终端错误为不可重试）。
7. 核心业务产物：**FAIL**（没有导入、matrix 或报告）。
8. 失败可操作恢复：**FAIL**（响应明确 `retryable=false`；本轮没有可验证的产品恢复动作）。
9. 页面状态与 API 状态一致：**FAIL**（研究任务页面状态未建立）。
10. 无上下文人工步骤可复现：**FAIL**（计划审批及产物查看路径不存在）。

得分为 `2/10`，且自然语言主路径失败、关键产物缺失；依据验收协议必须阻塞，不能交给用户人工验收。

## 最小阻塞建议

交给 backend-dev/model-runtime owner：核对当前部署对 `qwen3.5:9b` 的能力缓存/档位解析，与 `/api/models` 广告的 `off` 能力是否一致。修复或重新部署后，以全新 conversation/run 重试；不得通过省略档位、换模型、放宽 validator 或冒充报告产物绕过门禁。此建议不代表本轮已修复。

## 可复核证据与日志

- 结构化证据：[current-research-e2e-required-matrix-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-required-matrix-evidence.json)
- 本轮进展日志：`/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/tester/20261009-050735.md`
- 保留的旧失败证据：[current-research-e2e-frozen-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-frozen-report.md)、[current-research-e2e-frozen-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-frozen-evidence.json)

本报告不冒充完整 Spec E2E，不声称计划已批准、5 篇论文已导入、matrix 已生成或 canonical 报告可读。
