# Spec032 Task14：当前部署自然语言研究 E2E

## 最终裁决

**BLOCKED。**

自然语言主路径确实创建了一个新的独立研究会话并生成了待审批计划，但用户明确要求“最多 5 篇、目标论文数 5”，服务端实际将计划预算生成为 `target_paper_count=12`。为避免批准后超出用户上限，本轮在计划待审批状态停止，没有创建 ResearchTask、没有检索/下载/导入论文，也没有生成报告。不能用结构化表单补写约束来掩盖自然语言解析缺陷。

API E2E 证据：[current-research-e2e-evidence.json](./current-research-e2e-evidence.json)。上一轮 Semantic Scholar 证据仍保留在 [evidence.json](./evidence.json)，未被覆盖。

## 运行环境与范围

- `run_id`：`spec032-task14-research-e2e-20261006T144639Z`
- 服务：`http://127.0.0.1:8000`
- 分支：`codex/spec032-final-acceptance`
- 提交：`5b1b1d918db8858e848a73da4cee2df54f513ea2`
- 请求模型：`qwen3.5:9b`；`reasoning_effort=off`；未修改全局模型、阈值或长期配置。
- 自然语言请求：

  `请进行一次深度研究。主题是USENIX Security 2024中的security/privacy方法，目标是比较至少5篇方法与局限，并且最多选择5篇论文，目标论文数: 5，来源限定为USENIX Security，输出中文Markdown报告并使用行内引用。时间范围是2024-2024。`

- 只写入本轮用户明确请求的独立会话/消息/计划；没有读取 `.env` 或 API key，没有删除、reindex 或改动旧文档，没有登录，没有创建伪 issue/mock 替身。
- 已有交接材料 `candidate-import-integration.md` 只证明离线的候选评估→批准→自动导入接缝；本轮只认以下真实 HTTP 证据。

## 请求与真实响应

### 1. 自然语言入口

请求：`POST /api/conversations/messages`，Content-Type 为 `application/json`，无 Cookie/Authorization 入站头。HTTP 200，`TIME_TOTAL=0.209975s`。

响应是持久化 SSE，关键真实事件如下：

| 时间（UTC） | 事件 | 事实 |
|---|---|---|
| `2026-10-06T14:46:39.184183Z` | `meta` | conversation `c5a1fe652fb44a17bd648d7226588000`；user message `f92b1136b35541e6bdfa3b4c6e13da2d`；assistant message `16d8b471c685402ebc8114d66fb406da`；model `qwen3.5:9b` |
| `2026-10-06T14:46:39.185328Z` | `skill_activation` | `deep-research-orchestration`，`status=completed` |
| `2026-10-06T14:46:39.185898Z` | `processing_step` | 研究计划 `running`，摘要为“参数已齐，正在生成研究计划…” |
| `2026-10-06T14:46:39.242146Z` | `processing_step` | 研究计划 `completed`，摘要为“研究计划已生成，等待用户批准。” |
| `2026-10-06T14:46:39.245360Z` | `plan` | Session `d8e5b699c7fb448094f8c96323b5b3de`，版本 1，审批 pending |
| `2026-10-06T14:46:39.266026Z` | `intake` | `status=intake`，`missing=[]`；字段已持久化 |
| `2026-10-06T14:46:39.267001Z` | `done` | `status=completed`，`duration_ms=87.42775` |

自然语言字段投影：

- `topic`：`USENIX Security 2024中的security/privacy方法`（`user_explicit`）
- `objective`：`比较至少5篇方法与局限`（`user_explicit`）
- `time_range`：`{"from":2024,"to":2024}`（`user_explicit`）
- `sources`：`["usenix"]`，但来源为 `system_default`；与 USENIX Security 目标相符，却没有保存为用户显式来源。
- `constraints`：`[]`（`system_default`），没有保存用户句子中的“最多选择5篇论文，目标论文数: 5”。
- `output`/`citations`：默认 `markdown`/`inline`。

### 2. 计划结果

真实计划版本 1：

- `research_session_id`：`d8e5b699c7fb448094f8c96323b5b3de`
- `output_hash`：`9dfebea40ce6c03acdbd253c3c5e7f390724ad6b14fa9cee880546914aa6e8ba`
- `status`：`proposed`
- `approval_request_id`：`8160b199cbed4f0fa9bf3e960b0d5269`
- `approval.status`：`pending`
- `scope.sources`：`["usenix"]`
- `scope.time_range`：`2024–2024`
- `budget.quality_profile`：`balanced`
- `budget.target_paper_count`：**12（与用户要求 5 不一致）**
- `budget.soft_budget_seconds`：`1500`
- `report_structure`：Markdown、inline citations、标题 `深度研究报告`
- 计划工作项的检索 `source_ids` 为 `usenix`，每个 search item 的 `max_results` 为 6；但该计划没有被批准或执行。

### 3. 只读状态核对

`GET /api/research-sessions/d8e5b699c7fb448094f8c96323b5b3de`：HTTP 200，耗时 `12.663 ms`。

- Session `status=plan_pending_approval`，`current_plan_version=1`
- `research_task_id=null`、`activity_message_id=null`、`final_message_id=null`
- 审批仍为 pending，`approved_scope_json=null`
- `artifacts=[]`、`notifications=[]`

`GET /api/conversations/c5a1fe652fb44a17bd648d7226588000/messages?target_chars=12000`：HTTP 200，耗时 `12.999 ms`。用户原文、助手“研究计划已生成，等待你批准后开始执行。”和上述 `constraints=[]`、`target_paper_count=12` 均可复核；没有报告投影。

## 状态轨迹与副作用边界

| 阶段 | 状态 | 实体/产物 | 判定 |
|---|---|---|---|
| 自然语言 Intake | 完成 | Conversation、user/assistant message、Session、Intake draft | 成功创建独立会话 |
| 计划生成 | `plan_pending_approval` | Plan v1、pending approval | 预算解析失败：12 ≠ 5 |
| 计划批准 | 未执行 | 无 approved scope | 为遵守用户上限而停止 |
| ResearchTask/候选评估 | 未执行 | `research_task_id=null` | 无候选、无来源抓取 |
| 自动导入 | 未执行 | 无 batch、无 document、无 issue | 没有 PDF 请求/导入 |
| 报告生成 | 未执行 | `artifacts=[]` | 报告路径 `null` |

最终报告查看路径：`null`。报告标题、字数、引用数量：均不可用（没有报告，不能填 0 或伪造值）。

## 阻塞缺陷与最小 backend-dev 建议

优先级：**P1（自然语言显式预算未生效，批准后可能超出用户上限）**。

证据链：

1. POST 自然语言请求明确包含“最多选择5篇论文，目标论文数: 5”。
2. Intake SSE 与历史消息都显示 `constraints=[]`，且 `constraints.source=system_default`。
3. 同一真实计划的 `budget_json.target_paper_count=12`。
4. 由于尚未批准，尚无超额导入副作用；当前 Session 保留在待审批状态。

最小修复建议（不扩大范围）：

- 在 `backend/app/research/application/intake.py` 的受控字段抽取中识别“最多 N 篇/目标论文数 N”等明确数量，并以 `user_explicit` 写入现有 `constraints` 或专用 `target_paper_count` 字段；不要依赖目标文本被逗号截断后再猜预算。
- 在 `session_plan_generation.py` 生成计划时只使用该显式值，确保 `budget.target_paper_count=5`，并对计划/批准前后保持同一上限做断言。
- 增加自然语言主路径回归：用户句子→Intake projection→plan budget 必须为 5；若数量非法/冲突，应返回可操作的稳定错误而不是静默回落默认 12。
- 修复后必须以新的 `run_id` 重跑真实 API E2E；本轮 Session 不应被批准来绕过缺陷。

本轮没有修改业务代码，也没有使用表单、旧会话、mock 或伪造候选掩盖问题。

## 准备度矩阵（本轮自然语言 API E2E）

| # | 检查项 | 结果 | 证据 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | POST/GET 均 HTTP 200 |
| 2 | 真实 API 创建入口成功 | PASS | 新 conversation、message、research session 和 plan 已持久化 |
| 3 | 主路径参数被正确解析 | FAIL | topic/objective/time_range 成功，但“最多 5 篇/目标 5”丢失，计划变为 12 |
| 4 | 任务/实体状态从初始态推进 | FAIL | 计划停在待审批；为避免超额执行未创建 ResearchTask |
| 5 | 前端显示处理中提示 | FAIL | 本轮只走 API，未验证当前 UI 文案；SSE 仅证明服务端 processing_step |
| 6 | 用户知道何时点击或等待 | FAIL | 服务端发出“等待批准”事件，但没有验证产品 UI 入口/提示 |
| 7 | 核心业务产物真实生成 | FAIL | 预算阻塞后无导入、无报告、无 artifact |
| 8 | 失败状态有可操作恢复 | FAIL | 当前仅能由实现修复后新 run；没有把改错计划作为恢复路径 |
| 9 | 页面状态与 API 状态一致 | FAIL | 未验证 UI；API 明确为 pending approval、无 task/artifacts |
| 10 | 步骤文档可由无上下文用户复现 | FAIL | 可复现到计划阻塞，无法完成批准→导入→报告主路径 |

本轮 `PASS=2/10`，且存在 P1 与关键产物缺失，不能标记 `READY_FOR_USER`。

## 交接文件

- 本报告：[current-research-e2e-report.md](./current-research-e2e-report.md)
- 结构化证据：[current-research-e2e-evidence.json](./current-research-e2e-evidence.json)
- tester 日志：`.codebuddy/agent-logs/spec-032/task-14/tester/20261006-224623.md`
