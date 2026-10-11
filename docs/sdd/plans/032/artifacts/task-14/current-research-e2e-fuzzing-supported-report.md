# BLOCKED — Spec032 Task14 fuzzing 专题 qwen3.5:9b+xhigh 真实 API E2E

## 结论

本轮使用全新自然语言会话，入口请求明确使用 qwen3.5:9b 与 reasoning_effort=xhigh。
无刷新 capability 接口在启动前返回 supported_efforts=["xhigh"]，因此没有调用 refresh、
没有切换档位，也没有重试上一轮 low 失败会话。

Intake、计划、实际 hash 批准、s1/s2/e1/c1/syn 交接均有真实 API/SSE 证据。两个
USENIX search worker 各返回 5 个 2024 候选；evaluator 最终选择 5 个候选，5/5
论文真实下载并导入完成。可是 syn 在 MATRIX_NOT_READY 阶段失败，任务进入
status=partial，terminal.error_code=AGENT_OUTPUT_INVALID。Evidence Matrix GET
返回 409，legacy report 返回 409，canonical JSON/Markdown/HTML 均返回 404
REPORT_NOT_READY，artifacts 列表为空。因此本轮不能声称矩阵或 canonical 报告成功，
验收结论为 **BLOCKED**。

## 运行与部署

- run_id: spec032-task14-fuzzing-supported-20261011T035216Z
- 服务：http://127.0.0.1:8000
- 分支：codex/spec032-final-acceptance
- 部署提交：e83fdd6f8a43484f42e06d69a0d57f29f408bf51
- /api/ready：HTTP 200，ready=true；jieba、ollama_tags、embedding、qdrant 均 ready
- /：HTTP 200，62488 bytes；实际资源为 styles.css?v=56、app.js?v=57
- 无刷新 /api/chat/reasoning-options?model=qwen3.5:9b：HTTP 200，
  supported_efforts=["xhigh"]、default_effort="xhigh"、source="cache"、
  cached_at="2026-10-11T03:35:22.015092+00:00"
- 本次请求级模型：qwen3.5:9b；请求级 reasoning effort：xhigh
- 角色实际交接模型：s1/s2/c1=qwen3.5:9b；e1/syn=qwen3.8:27b-q4_K_M。
  这是后端按 role/model tier 的真实 resolved model；本轮没有改全局配置或环境。
- 已知观测问题：多条 processing_step 出现可重试 TRACE_PROJECTION_FAILED，但对应
  worker 状态仍有持久化的 completed/failed 事件。
- /api/models 的静态 capability 投影没有作为本轮 capability 判断依据；未调用
  refresh=1，也没有并发模型探针。

## 自然语言入口、计划与批准

入口请求内容为：

请进行一次新的深度研究。研究主题限定为 USENIX Security 2024 的模糊测试与漏洞发现。
研究目标是比较至少5篇研究的方法与局限。请最少选择5篇论文，最多选择5篇论文，目标
论文数为5；来源限定为 USENIX Security，时间范围为 2024-2024；输出中文 Markdown
报告并使用行内引用；生成计划后等待我批准。

真实入口响应为 HTTP 200 SSE：

- conversation_id=e222c0f6f2214eada3507df2672584df
- user_message_id=2622bc77a69f470cae8541b5f443bc3d
- assistant_message_id=daa3e11c068346fab0b33072ad393ea6
- 事件类型包含 meta、skill_activation、processing_step、plan、intake、done
- status=completed，research_session_id=a6fd24342d084811ae7abb144bf08ea6
- intake_draft_id=3433768d107f4786a65befd694f464d7
- approval_request_id=aba559909f284a7786e498b005925574
- plan_version=1
- 实际计划 output_hash=869643dc5f85dff50c41d83aad948d03709e3a69d02ec316e3f62118a1bc1f7a
- 计划 constraints 实测为 min_paper_count=5、max_paper_count=5、
  target_paper_count=5；sources=["usenix"]；time_range=2024..2024；
  language=zh；format=markdown；citations=inline

批准请求使用实际 hash，HTTP 200：

- POST /api/research-sessions/a6fd24342d084811ae7abb144bf08ea6/commands
- body command=approve_plan、subject_version=1、
  scope={"plan_version":1,"output_hash":"869643dc5f85dff50c41d83aad948d03709e3a69d02ec316e3f62118a1bc1f7a"}
- fresh idempotency_key=plan-approval:a6fd24342d084811ae7abb144bf08ea6:1
- response=status=queued、approval.status=approved、
  research_task_id=8fed1bc44a8158b59e3d48812ab4016b

## Search worker、raw 候选与 evaluator 选择

任务 8fed1bc44a8158b59e3d48812ab4016b 的真实任务计划含 s1/s2/e1/c1/syn 五个
work item。事件显示 s1、s2 都由 qwen3.5:9b 的 search-worker 完成，且两个
/api/papers/searches/{id}/results 均为 HTTP 200、total=5：

- s1 search id a86edcca600c4e6ea6c304f1e6bb62b4，raw 5：
  - ef9e0846844e5b02834163586ea6ddc9 — Stop, Don't Click Here Anymore:
    Boosting Website Fingerprinting By Considering Sets of Subpages
  - 9793a4a35caad52ee99f926ae7c90810 — Cascade: CPU Fuzzing via Intricate
    Program Generation
  - bb826cac3486a295d93eb9b6cea0a6f8 — DARKFLEECE: Probing the Dark Side of
    Android Subscription Apps
  - 57e0402f82fe2ce354bea423b201fde3 — DNN-GP: Diagnosing and Mitigating
    Model's Faults Using Latent Concepts
  - c74fdf1babb53a9cbcb6a6ac9fa5cd0e — Batch PIR and Labeled PSI with
    Oblivious Ciphertext Compression
- s2 search id 43592c6feaf947daa46a62d8a0e8a6f6，raw 5：
  - ef9e0846844e5b02834163586ea6ddc9 — Stop, Don't Click Here Anymore:
    Boosting Website Fingerprinting By Considering Sets of Subpages
  - 9793a4a35caad52ee99f926ae7c90810 — Cascade: CPU Fuzzing via Intricate
    Program Generation
  - 57e0402f82fe2ce354bea423b201fde3 — DNN-GP: Diagnosing and Mitigating
    Model's Faults Using Latent Concepts
  - 4e6322a23b92a271dbec9906c51fe0ab — GhostRace: Exploiting and Mitigating
    Speculative Race Conditions
  - bb826cac3486a295d93eb9b6cea0a6f8 — DARKFLEECE: Probing the Dark Side of
    Android Subscription Apps

终态 SSE selected_count=5，acquisition HTTP 200 的 selection_version=3 显示
evaluator 选择为 s1 的五项：DNN-GP、Cascade、DARKFLEECE、Batch PIR、Stop。
没有人工补选，没有第六篇下载。

## 5 篇真实导入

GET /api/research-tasks/8fed1bc44a8158b59e3d48812ab4016b/acquisitions 返回 HTTP
200，batch=761195d6-c2f9-469f-8217-388cc03ba21f，5/5 item 为 state=completed：

| candidate_id | paper/document_id | import_item_id | title |
|---|---|---|---|
| 57e0402f82fe2ce354bea423b201fde3 | 527fe0c1515d48c78adec8f4eb7f4979 | 3229e397-b6f3-4259-80aa-294a8a1d7df8 | DNN-GP |
| 9793a4a35caad52ee99f926ae7c90810 | 929a342c0b8d4c8283198751cae9b327 | 40294538-4b1c-4064-8bd8-33bd336eb12f | Cascade |
| bb826cac3486a295d93eb9b6cea0a6f8 | fa82faf63802431da803e1a99ce1411b | ba13aeac-d6c0-49a2-b805-927055ca144e | DARKFLEECE |
| c74fdf1babb53a9cbcb6a6ac9fa5cd0e | 2f002c403d4e49e79b4d2781fea38fc6 | 21775682-9b25-4a09-835e-8ec4f6a091a5 | Batch PIR |
| ef9e0846844e5b02834163586ea6ddc9 | 56fc315e952342158e5ae2f5ef6f01a0 | d404a272-7ebb-4680-b703-f2d8b5cae502 | Stop |

## 矩阵、报告与终态核验

- GET /api/research-tasks/8fed1bc44a8158b59e3d48812ab4016b/evidence-matrix?plan_version=1
  → HTTP 409，MATRIX_NOT_READY，没有矩阵正文。
- syn 事件 seq 25/26：research-report-synthesis 与 syn worker 均 status=failed、
  error_code=MATRIX_NOT_READY。
- terminal 事件 seq 27：status=partial、error_code=AGENT_OUTPUT_INVALID、
  selected_count=5。
- GET .../report?plan_version=1 → HTTP 409，REPORT_NOT_READY。
- GET .../reports/1?format=json → HTTP 404，REPORT_NOT_READY。
- GET .../reports/1?format=markdown → HTTP 404，REPORT_NOT_READY。
- GET .../reports/1?format=html → HTTP 404，REPORT_NOT_READY。
- GET /api/research-sessions/a6fd24342d084811ae7abb144bf08ea6/artifacts?report_version=1
  → HTTP 200，artifacts=[]。没有 artifact 可被误当作 canonical。
- 任务详情最终为 HTTP 200、status=partial、completed_at=2026-10-11T04:10:54Z、
  runtime_observability.last_error_code=MATRIX_NOT_READY。

本轮未调用矩阵 POST 或报告生成 POST 来人为补齐产物，也未把 imports 或任何 artifact
冒充 canonical report。失败根因在 API 可见范围内只能定位为 synth 依赖的
MATRIX_NOT_READY；没有进一步臆测隐藏实现原因。

## 人工验收准备度（10 项）

1. 服务可访问：**PASS**（ready/home 实测）。
2. 真实自然语言 API 创建：**PASS**（HTTP 200 SSE，conversation/session/plan 实体）。
3. 主路径参数正确解析：**PASS**（min=max=target=5、来源/年份/语言/格式/引用均实测）。
4. 任务与实体状态推进：**PASS**（批准、s1/s2/e1/c1/syn、终态均有事件及 ID）。
5. 前端处理中提示：**未验证/FAIL**（本轮为 backend API 验收，未执行 UI）。
6. 等待与下一步提示：**未验证/FAIL**（未执行 UI，且 canonical 产物未就绪）。
7. 核心业务产物：**FAIL**（5 imports 成功，但 matrix 与 canonical report 缺失）。
8. 失败状态可操作恢复：**未验证/FAIL**（保留明确错误，但没有改变状态重试）。
9. 页面状态与 API 一致：**未验证/FAIL**（未执行 UI）。
10. 无上下文可复现人工步骤：**FAIL**（矩阵/报告门禁未通过）。

准备度为 **4/10**；存在关键产物缺失与 syn MATRIX_NOT_READY 阻塞，不能交付人工
验收。此前 low 档 REASONING_EFFORT_UNSUPPORTED 失败报告保持不变，本报告不覆盖历史
失败。

## 约束遵守与未验证事项

- 使用新 conversation、新 session、新 task；没有重试 low 失败任务或旧 task。
- 未改业务代码、环境变量、全局模型、阈值或部署；未启动第二部署；未运行全量测试。
- 未调用 reasoning refresh；未做并发模型探针；SSE/状态读取均有界并低频进行。
- 已验证：ready/home、无刷新 xhigh capability、计划参数/hash、批准、s1/s2 raw
  candidates、evaluator 5 选择、5 imports、task terminal。
- 未验证/失败：Evidence Matrix HTTP 200 正文、canonical JSON/Markdown/HTML 非空正文
  与 citations、artifact 下载、前端人工路径、错误恢复后的重新验收。

## 证据与日志

- 结构化证据：[current-research-e2e-fuzzing-supported-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-fuzzing-supported-evidence.json)
- backend-tester 日志：[/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-fuzzing-xhigh-supported-e2e.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-fuzzing-xhigh-supported-e2e.md)
- 历史 low 档失败：[current-research-e2e-fuzzing-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-fuzzing-report.md)

最终裁决：**BLOCKED**。本轮已经真实完成 5 篇导入，但未达到矩阵与 canonical 三格式
报告门禁；保留所有实体 ID、响应码、状态与失败阶段，未伪造成功。
