# BLOCKED — Spec032 Task14 普通 output 合同反馈真实 E2E

## Final Decision

**BLOCKED**。本轮在当前部署、全新自然语言会话和全新 Research Task 上完成了 ready、Intake、计划批准、两个 USENIX 2024 search worker、evaluator 合同反馈重试、critic、synthesizer、5 篇候选选择及 5/5 PDF 导入。Synthesizer 最终只产生 `partial / REPORT_NOT_READY`；Evidence Matrix 不是 200，canonical JSON/Markdown/HTML 均不可用，因此不能交付人工验收。

固定诊断仅保留安全字段：`error_code`、`rule_id`、`field_paths`、`attempt`、`feedback_sent`、`feedback_classification`。没有落盘模型原文、prompt、hidden reasoning、动态错误文本、凭据或环境秘密。

## Run 与前置门禁

- `run_id`: `spec032-task14-contract-feedback-live-20261011T114437Z`
- Spec/Task：`032` / `14`
- 服务：`http://127.0.0.1:8000`；分支：`codex/spec032-final-acceptance`；HEAD：`4070323a5fcb277a03f34912b57a62d80267bbea`
- 服务重启会话：`67497`（主会话提供）；未启动第二部署、未改业务代码/环境/阈值/schema、未重试旧 Task、未运行全量回归。
- `GET /api/ready`：HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均 ready。
- `GET /`：HTTP 200，62488 bytes。
- `GET /api/chat/reasoning-options?model=qwen3.5:9b`：HTTP 200，支持 `off/low/medium/high/xhigh`，默认 `xhigh`，source=`cache`；未调用 refresh。
- 自然语言请求实际使用 `model=qwen3.5:9b`、`reasoning_effort=xhigh`；SSE `meta` 事件确认实际请求档位为 `xhigh`。

## 自然语言、计划与批准

真实 `POST /api/conversations/messages` 返回 HTTP 200、SSE `plan_pending_approval`。输入为：

> 请进行一次新的深度研究。研究主题限定为 USENIX Security 2024 的模糊测试与漏洞发现。研究目标是比较至少5篇研究的方法与局限。请最少选择5篇论文，最多选择5篇论文，目标论文数为5；来源限定为 USENIX Security，时间范围为2024-2024；输出中文 Markdown 报告并使用行内引用；生成计划后等待我批准。

真实实体：

- `conversation_id=05836dd31b78495481eab3fa757c3038`
- `user_message_id=c2d40dbdb9a84698b1a72d08134bd2a2`
- `assistant_message_id=542ab48d264a44c6a97cc2e87b382a3c`
- `research_session_id=abc7f5d019cc4d7ca8d269d1d1fc041b`
- `intake_draft_id=c6b611d962394dba9c3e7578ac6583ae`
- `approval_request_id=b89115a24c5546aca2c299f2cf1dc22b`

计划核对：`plan_version=1`、`output_hash=869643dc5f85dff50c41d83aad948d03709e3a69d02ec316e3f62118a1bc1f7a`、`min=max=target=5`、source=`usenix`、时间范围 `2024..2024`、语言 `zh`、格式 `markdown`、引用 `inline`。自然语言字段 `missing=[]`。

只提交一次真实 `approve_plan`：HTTP 200，`approval.status=approved`，`research_task_id=6184c29c7f32577e8c44e4eeb4a3b4c4`，幂等键为该 session 的唯一批准键。

## 实际阶段与固定诊断

1. s1 search completed，`search_id=1d9a4397682548d68cdf74e9274cd9a8`，结果 `total=5`，5 条均为 USENIX Security 2024。
2. s2 search completed，`search_id=d218150e8f3e47f4be041faeeaf849b6`，结果 `total=8`，结果均为 USENIX Security 2024。
3. evaluator 第 1、2 次分别产生固定 `AGENT_OUTPUT_INVALID`，之后通过反馈重试完成。两次失败诊断均为 `rule_id=agent.output.safety`、`field_paths=["output"]`；失败事件 `feedback_sent=false`，对应 validation-feedback 事件 `feedback_sent=true`、`feedback_classification=output_contract`。
4. critic completed。
5. synthesizer 第 1 次固定诊断为 `MATRIX_NOT_READY`、`rule_id=matrix.evidence_matrix.required`、`field_paths=["evidence_matrix"]`、`attempt=1`、`feedback_sent=false`；validation-feedback 事件为 `feedback_sent=true`、`feedback_classification=matrix_validation`。随后 synthesizer completed，但 terminal 仍为 `partial / REPORT_NOT_READY`、`selected_count=5`。

## 选集与真实 PDF 导入

真实 acquisition：batch=`faa15b89-e375-4f26-830d-1656bbffa99f`、`selection_version=3`、5/5 item completed。每个 link 均有真实 document/import ID：

| candidate_id | 论文 | document_id | import_item_id | 原件核对 |
|---|---|---|---|---|
| `4e6322a23b92a271dbec9906c51fe0ab` | GhostRace | `a151fcff09944e7cbd1f4086376ae914` | `d833b098-4206-4057-afec-798a0f8c179e` | PDF 2172524 bytes |
| `57e0402f82fe2ce354bea423b201fde3` | DNN-GP | `527fe0c1515d48c78adec8f4eb7f4979` | `bb56ca11-e6da-4f5e-a8b0-b4b24810992c` | PDF 2818784 bytes |
| `9793a4a35caad52ee99f926ae7c90810` | Cascade | `929a342c0b8d4c8283198751cae9b327` | `41bb1914-c982-461b-b330-91089112e550` | PDF 1078847 bytes |
| `bb826cac3486a295d93eb9b6cea0a6f8` | DARKFLEECE | `fa82faf63802431da803e1a99ce1411b` | `0b440051-92ba-4fa9-918f-357b4939f25a` | PDF 1524684 bytes |
| `ef9e0846844e5b02834163586ea6ddc9` | Stop, Don't Click Here Anymore | `56fc315e952342158e5ae2f5ef6f01a0` | `11b034bd-badf-46ab-ac4d-1183b6353ef5` | PDF 676785 bytes |

五个 `/api/kb/documents/{document_id}/source` HEAD 均 HTTP 200、`content-type=application/pdf`、`content-length>0`；KB 列表均为 `status=indexed`、`source_immutable=true`。这证明真实导入产物存在，但不证明报告已生成。

## Matrix、报告和 artifact 边界

- Evidence Matrix：`GET /api/research-tasks/6184c29c7f32577e8c44e4eeb4a3b4c4/evidence-matrix?plan_version=1` → HTTP 409，`MATRIX_NOT_READY`。
- Legacy report：HTTP 200，但 `status=partial`、`report_id=artifact:a8a1bd03f12c4ad1a3fa5ea20fc00586`、`limitations.artifact_backed=true`，只能作为 partial 投影，不能替代 canonical ResearchReport。
- Canonical `format=json`、`markdown`、`html`：均 HTTP 404，`REPORT_NOT_READY`；三种 canonical 正文非空条件均不成立。
- Session artifact 列表 HTTP 200，存在 citation_manifest、html、markdown 三个 artifact；它们均由 `syn:run-1:attempt-2` 产生，但 artifact 不冒充 canonical report，未用来绕过 Matrix 门禁。

## 当前人工验收案例（不可执行）

入口 URL：`http://127.0.0.1:8000/`；前置条件为当前分支 HEAD、服务 ready、Ollama/Qdrant ready。对应 run/task：`spec032-task14-contract-feedback-live-20261011T114437Z` / `6184c29c7f32577e8c44e4eeb4a3b4c4`。

1. 在研究聊天入口输入上面的自然语言并提交；API 已真实返回 HTTP 200、计划版本 1 和等待批准状态，但本 backend-only 轮次未验证页面的精确按钮/处理中提示。
2. 在计划卡片点击批准并提交实际计划 hash；API 已真实返回 approved 和 task ID，但本轮未把未验证 UI 文案当作证据。
3. 等待候选评估和导入；API 已真实返回 5 个 selected、5/5 completed 及上述 document/import IDs。页面阶段文案未验证。
4. 打开 Evidence Matrix 和 canonical report；真实 API 当前分别返回 `MATRIX_NOT_READY` 和三个 `REPORT_NOT_READY`。不能继续等待绕过已结束的 syn 合同门禁，也不能用 legacy partial 或 artifact 代替 canonical。实现修复后必须以全新 run_id 重跑。

因此该案例不能交给无上下文用户执行，失败恢复需由实现/评审修复后重新部署和验收；本轮不人工补选、不 POST 矩阵/报告、不重试旧 task。

## 准备度矩阵

1. 服务启动并可访问：**PASS**（ready/home）。
2. 真实 API 创建入口：**PASS**（自然语言 SSE、conversation/session/plan）。
3. 主路径参数解析：**PASS**（5/5、USENIX/2024、zh/markdown/inline）。
4. 任务/实体状态推进：**PASS**（s1/s2/evaluator retry/critic/syn/terminal/5 imports）。
5. 前端处理中提示：**FAIL**（本轮只做 backend API，UI 文案未验证）。
6. 用户知道何时等待/点击：**FAIL**（UI 文案未验证，且 canonical 报告门禁失败）。
7. 核心业务产物真实生成：**FAIL**（PDF 导入成功，但 Evidence Matrix/canonical report 缺失）。
8. 失败状态有可操作恢复：**FAIL**（服务端 feedback 事实已记录，但本轮未验证用户可操作恢复入口）。
9. 页面状态与 API 状态一致：**FAIL**（未执行 UI）。
10. 无上下文步骤可复现：**FAIL**（canonical JSON/Markdown/HTML 不可查看）。

准备度：**4/10**；存在 P1 级报告产物阻塞，不能交付用户验收。

## 证据路径

- 结构化证据：[current-research-e2e-contract-feedback-evidence.json](./current-research-e2e-contract-feedback-evidence.json)
- backend-tester 日志：[/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-contract-feedback-live-e2e.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-contract-feedback-live-e2e.md)
- 普通 Synthesizer 合同复审（APPROVED）：[current-synthesis-contract-review.md](./current-synthesis-contract-review.md)
