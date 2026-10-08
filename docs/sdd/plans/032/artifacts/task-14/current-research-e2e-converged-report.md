# Spec032 Task14 真实自然语言研究 E2E（converged run）

结论：**BLOCKED（真实运行失败，未冒充成功）**。

本轮使用当前部署 `HEAD 00cdb6b`、端口 `8000`、重启会话 `51534`，创建了全新的 conversation/run，没有重试或覆盖历史失败 run。`GET /api/ready` 返回 HTTP 200，`ready=true`，jieba/Ollama tags/embedding/Qdrant 均为 ready。

## Run identity

- run_id：`spec032-task14-converged-20261008T195755Z`
- conversation_id：`9810466c33e0403c8515026818f00af2`
- research_session_id：`fd2b95c359da4923a876a026cb4c5b9c`
- intake_draft_id：`4b70af6819694b90942d297560439a14`
- research_task_id：`bf474433be705e479bca55c4b2dbe9c2`
- search_id（s1）：`5a747b4604a04e01a6b3e228212d92d6`
- search_id（s2）：`8ed93aa8639a4c8f92a9be9ec82dafb0`
- 请求级模型：`qwen3.5:9b`；`reasoning_effort=off`；实际事件中的模型解析见下文。

## 真实请求与 Intake/计划门禁

首个公开自然语言请求经 `POST /api/conversations/messages` 返回 HTTP 200/SSE，正确解析了 `min_paper_count:5`、`max_paper_count:5`、`target_paper_count:5`，但返回缺少 `topic/objective/time_range`。一次带有显式“研究”措辞的补充触发了产品自己的 `active_conflict`（HTTP 200，choices 为 `modify_current`、`cancel_then_new`、`new_conversation`），未绕过该冲突。

随后在同一全新会话发送仅回答字段的自然语言：主题 `security/privacy`、目标比较至少 5 篇 USENIX Security 2024 论文的方法与局限、时间范围 `2024-2024`、最少/最多/目标均为 5。SSE 真实返回 `plan_pending_approval`：

- plan version：`1`
- subject version：`1`
- output hash：`7deaa0a57c53cefd00c69eb5f862a187c9767157b2414f6b2f5f264d80cd3e35`
- constraints：`min=5, max=5, target=5`
- plan budget：`target_paper_count=5`
- s1/s2 `max_results=5`
- source：`usenix`，time range `{from: 2024, to: 2024}`

使用既有 `POST /api/research-sessions/{session_id}/commands`、version/hash 和唯一 idempotency key 批准；返回 HTTP 200，approval 为 `approved`，只创建了上述新 ResearchTask，初始状态 `planning`。

## 异步真实运行

按 15–30 秒边界读取任务、事件、acquisition 和 evidence matrix。安全事件流记录的阶段顺序为：

1. s1 USENIX catalog search：完成；
2. s2 USENIX catalog search：完成并返回 5 篇 2024 候选；
3. e1 paper evaluation：完成；
4. c1 coverage review：完成；
5. syn / `research-report-synthesis`：运行约 94 秒后完成，但输出校验失败。

终端安全事件 `event_seq=27`：`status=partial`、`error_code=AGENT_OUTPUT_INVALID`、`selected_count=5`。这表示评估阶段报告了 5 个选择，但不是 5 个成功导入的论文，也不是可用报告。

实际事件中，fast worker（s1/s2/e1）记录 `qwen3.5:9b`；c1/syn 启动事件记录 strong `qwen3.8:27b-q4_K_M`，对应完成事件又记录 strong `qwen3.5:9b`。该运行时解析不一致已原样记录，未将请求级模型声明扩大解释为全链路模型保证。

事件投影还多次返回安全的 retryable `TRACE_PROJECTION_FAILED` 帧；原始安全事件仍可读取，任务最终错误明确为 `AGENT_OUTPUT_INVALID`，不是把投影警告冒充根因。

## 论文、导入、矩阵与报告结果

任务终态：`partial`（完成时间 `2026-10-08T20:03:48Z`）。

- 论文候选：s2 事件中确实有 5 个 USENIX Security 2024 catalog 候选，但本报告不复制其内容或隐藏链接；最终 acquisition 没有产生可确认的 paper/document ID。
- acquisition：HTTP 200，`status=failed`、`approval_status=failed`、`selection_version=3`、`batch_id=null`、`items=[]`、`links=[]`、`events=[]`、`issues=[]`。
- evidence matrix：HTTP 409，`MATRIX_NOT_READY`。
- legacy `/report`：HTTP 409，`REPORT_NOT_READY`。
- canonical `/reports/1?format=json`：HTTP 404，`REPORT_NOT_READY`。
- canonical `/reports/1?format=markdown`：HTTP 404，`REPORT_NOT_READY`。
- canonical `/reports/1?format=html`：HTTP 404，`REPORT_NOT_READY`。
- session artifacts：HTTP 200，`artifacts=[]`。

因此最终报告查看路径不存在；canonical report version/title/正文/字数/引用数均为“未生成”（正文长度 0，引用数 0），不能以 artifact metadata 或 selected_count=5 代替。没有可验证的 paper IDs、document IDs、非空 matrix、Markdown/HTML/JSON canonical 版本或 artifact 下载路径。

## 阻塞阶段与最小后端建议

阻塞阶段是 `syn`/`research-report-synthesis` 的 agent-output validation，错误码为 `AGENT_OUTPUT_INVALID`；它发生在检索、评估、coverage 已完成且终端选择计数为 5 之后、acquisition/matrix/report 持久化之前。建议 backend-dev 仅检查该现有 synthesizer 输出 schema/validator 与失败传播：让真实无效输出保留可诊断的安全错误，并在有效输出时将同一 5 项集合传给既有 matrix/acquisition/report 链；不要通过手工批准、伪造候选或直接调用报告 POST 绕过该失败，也不要改变全局模型、阈值、env 或安全下载策略。

本结果只证明当前自然语言主链的真实失败位置，不冒充 Spec032 完整 E2E 通过。详细脱敏请求、响应、实体 ID、状态和端点证据见同目录 `current-research-e2e-converged-evidence.json`。
