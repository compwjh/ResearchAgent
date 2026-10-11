# BLOCKED — Spec032 Task14 全新五篇 USENIX 2024 模糊测试 E2E 诊断

## 结论

本轮使用全新的自然语言会话、研究 session 和 task，在当前部署上真实完成了 Intake、计划生成、哈希批准、两个 USENIX 2024 search worker、evaluator/critic、5 篇选中论文的导入与知识库索引。任务最终为 `partial`；synthesizer 的矩阵合同校验在 attempt 1–4 均产生 `AGENT_OUTPUT_INVALID`，最终没有证据矩阵或 canonical 报告。

最终裁决：**BLOCKED**。不能把 5 篇导入、论文 ID 或空 artifact 列表冒充证据矩阵/报告，也不允许交给用户人工验收。具体失败、固定诊断字段和原始 HTTP 证据均保留在本文件及配套 JSON 中。

## 运行与前置门禁

- `run_id`: `spec032-task14-fuzzing-diagnostic-20261011T111924Z`
- 服务：`http://127.0.0.1:8000`；分支：`codex/spec032-final-acceptance`；候选 HEAD：`7d6834228b46496c96d951e2ba04280146f8d0cc`
- 任务开始：`2026-10-11T11:19:24.987980Z`；批准：`2026-10-11T11:19:58Z`；任务终态：`2026-10-11T11:29:19Z`
- `GET /api/ready`：HTTP 200，`ready=true`，jieba/ollama_tags/embedding/qdrant 均 ready。
- `GET /`：HTTP 200，62488 bytes。
- `GET /api/chat/reasoning-options?model=qwen3.5:9b`：HTTP 200，supported efforts 为 `off/low/medium/high/xhigh`，default=`xhigh`，source=`cache`；未调用 refresh。本轮请求使用实际支持的 `xhigh`。
- 未启动第二部署，未改业务代码、环境变量、全局模型、阈值或数据库 schema，未重试旧 task，未运行全量回归。

## 自然语言入口、计划与批准

自然语言请求（真实 `POST /api/conversations/messages`，HTTP 200，SSE）为：

> 请进行一次新的深度研究。研究主题限定为 USENIX Security 2024 的模糊测试与漏洞发现。研究目标是比较至少5篇研究的方法与局限。请最少选择5篇论文，最多选择5篇论文，目标论文数为5；来源限定为 USENIX Security，时间范围为2024-2024；输出中文 Markdown 报告并使用行内引用；生成计划后等待我批准。

- `conversation_id`: `a7f93eeab57f47a793f00f3e09f46a12`
- `user_message_id`: `ae408f73f2e94a00af030072d353b0da`
- `assistant_message_id`: `e33c22f548224f5ea37973060f6a238a`
- `intake_draft_id`: `7c06094ba1284368adfc15bbd2de983c`
- `research_session_id`: `e534d92caa5d4aa1be7b37c8f5a0c641`
- `approval_request_id`: `d94c306b7e2940199d04fc57af37bfb1`
- 计划 `version=1`，`output_hash=869643dc5f85dff50c41d83aad948d03709e3a69d02ec316e3f62118a1bc1f7a`。
- 实测约束：`min=max=target=5`；source=`usenix`；time range=`2024..2024`；language=`zh`；format=`markdown`；citations=`inline`。
- `POST /api/research-sessions/e534d92caa5d4aa1be7b37c8f5a0c641/commands` 使用 `approve_plan`、`subject_version=1`、实际 output hash 和全新幂等键，HTTP 200，approval=`approved`，创建 task `dd2291bec53954328c3c5ec94c2b457f`。

## Worker、选集和导入

- s1：search `1c259af18922401c93a58f3f488b3bf3`，HTTP 200，completed，结果 HTTP 200、8 条；全部 `conference_id=usenix-security`、`year=2024`。
- s2：search `cbbf5538beaa48bbb5c7b2961dad9b5c`，HTTP 200，completed，结果 HTTP 200、8 条；全部 `conference_id=usenix-security`、`year=2024`。
- 终态事件 `seq=32` 为 `partial`、`selected_count=5`；导入 batch `ae534c93-6725-4c38-becb-f71b458ca8e2`，`selection_version=4`，5/5 item=`completed`，links 中每条均有真实 document/import ID。

| candidate_id | 论文 | paper/document_id | import_item_id | 状态 |
|---|---|---|---|---|
| `0f27a017e67812a500bafbc4a0d76788` | RECORD | `bc763528f6444ad6af88513347cc0927` | `81c1b7df-41db-4c1d-b1b2-75f088286e5d` | completed/indexed |
| `57e0402f82fe2ce354bea423b201fde3` | DNN-GP | `527fe0c1515d48c78adec8f4eb7f4979` | `133a7c96-5aa9-4b9e-a100-4857ee3e21c3` | completed/indexed |
| `9793a4a35caad52ee99f926ae7c90810` | Cascade | `929a342c0b8d4c8283198751cae9b327` | `be0b60f0-a4c4-47b8-8126-1c4d7d3f07b2` | completed/indexed |
| `ef9e0846844e5b02834163586ea6ddc9` | Stop, Don't Click Here Anymore | `56fc315e952342158e5ae2f5ef6f01a0` | `1d755d1e-5355-40e7-8607-58181317c46c` | completed/indexed |
| `ceba49cde497dd75ad6b6d746e925472` | LaKey | `e3b0d5ec6e974d73a42c027792094e34` | `27074ac5-7362-4433-883b-c027c3c3dce9` | completed/indexed |

`GET /api/kb/documents?limit=100` HTTP 200 进一步确认上述五个 document 均为 `application/pdf`、`status=indexed`、`source_immutable=true`。这些是真实导入产物，不是报告替代物。

## 固定诊断与失败证据

任务事件中保留的 syn 校验诊断（不含模型正文、prompt、hidden reasoning、摘要、动态 locator 或 secret）：

| event_seq | attempt | error_code | rule_id | field_paths | feedback_sent | feedback_classification |
|---:|---:|---|---|---|---|---|
| 25 | 1 | `AGENT_OUTPUT_INVALID` | `agent.output_contract` | `[]` | `false` | `not_sent` |
| 26 | 2 | `AGENT_OUTPUT_INVALID` | `agent.output_contract` | `[]` | `false` | `not_sent` |
| 27 | 3 | `AGENT_OUTPUT_INVALID` | `agent.output_contract` | `[]` | `false` | `not_sent` |
| 28 | 4 | `AGENT_OUTPUT_INVALID` | `agent.output_contract` | `[]` | `false` | `not_sent` |

随后 `seq=29` 为 retry routing，`seq=30` 为 skill completed，`seq=31` 的 synthesizer fallback 仍未产生可用矩阵，`seq=32` 终态为 `partial / AGENT_OUTPUT_INVALID / selected_count=5`。本报告只记录 API/SSE 可见事实，不臆测隐藏实现原因。

## 矩阵、报告和 artifact 门禁

- `GET /api/research-tasks/dd2291bec53954328c3c5ec94c2b457f/evidence-matrix?plan_version=1`：HTTP 409，`MATRIX_NOT_READY`。
- `GET /api/research-tasks/dd2291bec53954328c3c5ec94c2b457f/report?plan_version=1`：HTTP 409，`REPORT_NOT_READY`。
- canonical `reports/1?format=json|markdown|html`：分别 HTTP 404，均 `REPORT_NOT_READY`，正文非空条件不成立。
- `GET /api/research-sessions/e534d92caa5d4aa1be7b37c8f5a0c641/artifacts?report_version=1`：HTTP 200，`artifacts=[]`；没有 artifact 被冒充 canonical report。

## 人工验收案例（当前不可执行）

入口 URL：`http://127.0.0.1:8000/`；版本/前置条件：当前分支 HEAD、服务 ready、Ollama 与 Qdrant ready。对应 API run/task：`spec032-task14-fuzzing-diagnostic-20261011T111924Z` / `dd2291bec53954328c3c5ec94c2b457f`。

1. **输入**：在研究聊天入口输入上面的自然语言请求并提交。**点击后提示**：API 已实测 HTTP 200、计划版本 1 和等待批准状态；前端真实按钮文案未验证。**等待**：等待计划事件和 `research_session_id`。**等待中显示**：前端处理中提示未验证。**下一步**：查看计划并批准。**失败恢复**：若收到可重试 Intake 错误，记录该错误并回到同一会话重试；本轮 API Intake 成功。
2. **输入**：点击“批准计划”对应控件（真实 UI 文案未验证），提交实际 plan hash。**点击后提示**：API 实测 approval=`approved`、task=`dd2291…b457f`。**等待**：等待 task 进入终态。**等待中显示**：worker 阶段卡片/进度文案未验证。**下一步**：等待 search/evaluator/import 状态。**失败恢复**：不要重复批准或创建第二 task；按页面给出的重试入口恢复，若无入口记录阻塞码。
3. **输入**：查看五篇导入条目。**点击后提示**：API 实测 5/5 completed，KB 文档 indexed。**等待**：等待每个条目进入 completed。**等待中显示**：下载/校验/索引阶段的真实 UI 文案未验证。**下一步**：等待矩阵和 canonical 报告。**失败恢复**：按具体 import item 的 retry/login/upload 能力恢复；本轮没有失败导入，不执行人工补选。
4. **输入**：打开证据矩阵与报告入口。**点击后提示**：本轮实际返回 MATRIX_NOT_READY、REPORT_NOT_READY。**等待**：不可通过继续等待绕过 syn 合同失败。**等待中显示**：页面错误提示和可操作恢复控件未验证。**下一步**：不交付人工验收，交由实现/评审修复后重新以新 run_id 验证。**失败恢复**：保留本 run 的失败证据，禁止用旧 task、imports 或空 artifact 替代报告。

## 准备度矩阵

1. 服务启动并可访问：**PASS**（ready/home）。
2. 真实 API 创建入口：**PASS**（自然语言 SSE、conversation/session/plan）。
3. 主路径参数解析：**PASS**（5/5、USENIX/2024、zh/markdown/inline）。
4. 任务/实体状态推进：**PASS**（approve、s1/s2/e1/c1/syn、terminal、5 imports）。
5. 前端处理中提示：**FAIL**（backend API 任务未执行 UI，文案未验证）。
6. 用户知道何时等待/点击：**FAIL**（UI 文案未验证，且报告门禁失败）。
7. 核心业务产物真实生成：**FAIL**（imports 成功，但 matrix/canonical report 缺失）。
8. 失败状态有可操作恢复：**FAIL**（诊断具体，但本轮未证明页面/API 恢复入口）。
9. 页面状态与 API 状态一致：**FAIL**（未执行 UI）。
10. 无上下文步骤可复现：**FAIL**（矩阵/报告门禁未通过，人工步骤不可交付）。

准备度：**4/10**；存在关键产物缺失与 P1 级主路径阻塞，不能交付用户验收。需要实现/评审角色修复 syn 矩阵合同失败并重新进行全新真实 E2E；本轮不重试、不补 POST、不改代码。

P0/P1 清单：P0 无；P1 为 syn 在四次有界校验后仍以 `AGENT_OUTPUT_INVALID` 终止，导致 `MATRIX_NOT_READY`、canonical JSON/Markdown/HTML 均 `REPORT_NOT_READY`。

## 证据文件

- 结构化证据：[current-research-e2e-diagnostic-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-diagnostic-evidence.json)
- backend-tester 日志：[/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-fuzzing-diagnostic-e2e.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-fuzzing-diagnostic-e2e.md)
- 既有 xhigh supported 失败报告：[current-research-e2e-fuzzing-supported-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-fuzzing-supported-report.md)

**Final Decision: BLOCKED**。
