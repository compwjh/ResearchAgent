# Spec030 Task10：自然语言真实 API E2E 准备

日期：2026-10-29  
状态：`BLOCKED`（仅完成 API 执行准备；未调用服务、未写数据库、未生成报告，不能作为 E2E 成功证据或用户验收结论）。

## 验收案例与固定论文集

自然语言主路径使用**在线账户与密码认证安全**。固定目标为 USENIX Security 2022 “Passwords” session 的五篇真实论文；USENIX 官方 session 页列出全部五项，individual presentation 页面用于在真实 API 返回后核对目录标题：

1. [Pre-hijacked accounts: An Empirical Study of Security Failures in User Account Creation on the Web](https://www.usenix.org/conference/usenixsecurity22/presentation/sudhodanan)
2. [Leaky Forms: A Study of Email and Password Exfiltration Before Form Submission](https://www.usenix.org/conference/usenixsecurity22/presentation/senol)
3. [Might I Get Pwned: A Second Generation Compromised Credential Checking Service](https://www.usenix.org/conference/usenixsecurity22/presentation/pal)
4. [Why Users (Don't) Use Password Managers at a Large Educational Institution](https://www.usenix.org/conference/usenixsecurity22/presentation/mayer)
5. [Gossamer: Securely Measuring Password-based Logins](https://www.usenix.org/conference/usenixsecurity22/presentation/sanusi-bohuk)

官方 [USENIX Security '22 Passwords session](https://www.usenix.org/conference/usenixsecurity22/session/passwords) 是本固定集合的来源。固定标题只用于真实候选的核对；**真实 API 尚未返回的 paper ID、abstract、Evidence ID、report_version、运行分支和成功状态均留空，禁止按标题构造候选或证据。**

案例需要检验用户账户生命周期的不同环节：注册前/注册阶段的 pre-hijacking、表单输入泄露、凭证泄露检查、密码管理器采纳与安全登录测量。人工语义评审需要核对各论文的研究对象和证据边界，不能因为主题相邻就强行宣称五篇采用同一种方法。

## 主路径与精确请求

本项目把 `POST /api/conversations/messages` 作为首条自然语言消息入口：新会话在该请求中创建，Research Intake 从消息解析字段并生成 Session/计划。继续补字段时用同一个 conversation 的 `POST /api/conversations/{conversation_id}/messages`。`POST /api/research-sessions` 是结构化 intake 边界，不替代自然语言验收。路由依据：[`routes_conversations.py`](../../../../backend/app/api/routes_conversations.py:2053)、[`routes_research.py`](../../../../backend/app/api/routes_research.py:1310)。

### 0. 运行前记录

由主 Agent 在当前部署版本确认实际 `BASE_URL`、端口、分支/版本、开始时间和健康状态。下面命令中的 `${BASE_URL}`、`${RUN_DIR}` 及所有实体 ID 都是执行时填入的变量，不是已发生运行值。不得从旧运行复制 ID，不得记录 Authorization、Cookie、API key 或其它凭据。

```sh
export BASE_URL='http://127.0.0.1:<本次实际端口>'
export RUN_DIR='docs/sdd/plans/030/artifacts/task-10/api-e2e/<本次唯一run-id>'
mkdir -p "$RUN_DIR"
curl -sS -D "$RUN_DIR/00-health.headers" -o "$RUN_DIR/00-health.json" \
  "$BASE_URL/api/health"
```

只有 health 返回成功且版本/端口记录完整后才继续。旧运行审计所用 `127.0.0.1:8000` 是历史记录，不可自动认作本次部署。

### 1. 自然语言创建对话、Intake Session 和计划

首条消息使用一份完整输入，确保 Intake 的确定性抽取能读到主题、目标、范围和 5 篇约束。`至少5篇` 和 `目标论文数为5篇` 同时提供，分别用于冻结下限和精确目标；自然语言解析使用 `topic/objective/time_range/constraints` 字段。消息示例：

> 关于在线账户与密码认证安全进行深度研究，目标是以 USENIX Security 2022 官方 Passwords session 为唯一来源，围绕账户注册/接管、表单输入隐私、泄露凭证检测、密码管理器使用和登录测量，比较以下五篇论文的研究问题、方法、实证对象、主要发现、适用范围和局限：Pre-hijacked accounts: An Empirical Study of Security Failures in User Account Creation on the Web；Leaky Forms: A Study of Email and Password Exfiltration Before Form Submission；Might I Get Pwned: A Second Generation Compromised Credential Checking Service；Why Users (Don't) Use Password Managers at a Large Educational Institution；Gossamer: Securely Measuring Password-based Logins。时间范围为2022-2022；目标论文数为5篇，至少5篇。报告用中文撰写，正文至少1500个 CJK 字符，逐篇分析五篇论文，至少有一项跨论文比较和三条由不少于两篇论文证据支持的综合发现；若官方摘要没有说明具体方法、结果或限制，必须明确写未知，不得推断为全文结论。

```sh
curl -N -sS -D "$RUN_DIR/01-natural-intake.headers" \
  -o "$RUN_DIR/01-natural-intake.sse" \
  -H 'Content-Type: application/json' \
  -d '{"content":"关于在线账户与密码认证安全进行深度研究，目标是以 USENIX Security 2022 官方 Passwords session 为唯一来源，围绕账户注册/接管、表单输入隐私、泄露凭证检测、密码管理器使用和登录测量，比较以下五篇论文的研究问题、方法、实证对象、主要发现、适用范围和局限：Pre-hijacked accounts: An Empirical Study of Security Failures in User Account Creation on the Web；Leaky Forms: A Study of Email and Password Exfiltration Before Form Submission；Might I Get Pwned: A Second Generation Compromised Credential Checking Service；Why Users (Don't) Use Password Managers at a Large Educational Institution；Gossamer: Securely Measuring Password-based Logins。时间范围为2022-2022；目标论文数为5篇，至少5篇。报告用中文撰写，正文至少1500个 CJK 字符，逐篇分析五篇论文，至少有一项跨论文比较和三条由不少于两篇论文证据支持的综合发现；若官方摘要没有说明具体方法、结果或限制，必须明确写未知，不得推断为全文结论。","mode":"normal"}' \
  "$BASE_URL/api/conversations/messages"
```

这是流式响应。保留完整脱敏 SSE 和 HTTP headers；从真实 `meta` 帧取 `conversation_id` / `user_message_id`，从 `intake` 帧取 `research_session.research_session_id`、解析字段及 `missing`，从 `plan` 帧取 `plan.plan_version`、`plan.output_hash` 和审批状态。它们全部记入本次 Evidence JSON/Markdown，不得照抄测试夹具值。

成功继续条件：自然语言触发 `intake`，`missing=[]`，`topic/objective/time_range` 与输入匹配，`constraints` 表示 min=5/target=5；随后计划存在、plan version 与 output hash 可读、approval 为待批准状态。等待 `done` SSE 帧结束首个响应。若字段缺失，按响应 `missing/question` 使用同一 conversation 的自然语言 follow-up：

```sh
curl -N -sS -D "$RUN_DIR/02-intake-followup.headers" \
  -o "$RUN_DIR/02-intake-followup.sse" \
  -H 'Content-Type: application/json' \
  -d '{"content":"<只补充 intake missing/question 明确要求的自然语言字段>"}' \
  "$BASE_URL/api/conversations/${CONVERSATION_ID}/messages"
```

再次按 `intake` 与 `plan` 帧复核。若自然语言主路径失败，保留原始响应并将运行记为 BLOCKED；不得改走结构化 `/research-sessions` 请求后称为自然语言成功。计划自动生成失败时，允许使用 `POST /api/research-sessions/{session_id}/plans/generate` 恢复同一已完成 Intake，并将该 POST 的原始请求/响应和重试关系记下；只有自然语言 Intake 本身已完成时才可走此恢复。

### 2. 明确审批计划

先人工审阅真实 plan 内容，确认范围仍是五篇官方 2022 论文、目标篇数为 5、中文报告和 1500 CJK 要求没有丢失/被扩大。使用 SSE `plan` 帧中的真实 `plan_version` 和 `output_hash`。执行 approve：

```sh
export APPROVE_KEY="$(uuidgen | tr '[:upper:]' '[:lower:]')"
curl -sS -D "$RUN_DIR/03-approve.headers" -o "$RUN_DIR/03-approve.json" \
  -H 'Content-Type: application/json' \
  -d "{\"command\":\"approve_plan\",\"subject_version\":${PLAN_VERSION},\"scope_json\":{\"plan_version\":${PLAN_VERSION},\"output_hash\":\"${PLAN_OUTPUT_HASH}\"},\"idempotency_key\":\"${APPROVE_KEY}\"}" \
  "$BASE_URL/api/research-sessions/${RESEARCH_SESSION_ID}/commands"
```

这里 `subject_version` 必须等于当前计划版本；`scope_json` 用该计划的版本和 hash 回显；审批 payload **没有** approval ID 字段。审批 response 应提供实际 `research_task_id`/task 状态和审批决定。记录 plan/task/session ID 的绑定和 HTTP status。网络重试复用原幂等 key；用户主动重新审批/修订计划不复用此 key。

API 源：[`ResearchSessionCommandRequest` 与命令路由](../../../../backend/app/api/routes_research.py:243)、[`execute_research_session_command`](../../../../backend/app/api/routes_research.py:1369)、[`PlanApprovalService.command`](../../../../backend/app/research/application/approval_service.py:157)。

### 3. 轮询研究阶段与核对真实五篇 Evidence

按 5 秒退避轮询 task 状态；只轮询到 completed/partial/failed/interrupted/cancelled 或到达本次记录的总超时。先保存每次 HTTP 响应和时间戳：

```sh
curl -sS -D "$RUN_DIR/poll-task.headers" -o "$RUN_DIR/poll-task.json" \
  "$BASE_URL/api/research-tasks/${RESEARCH_TASK_ID}"
curl -sS -D "$RUN_DIR/poll-report.headers" -o "$RUN_DIR/poll-report.json" \
  "$BASE_URL/api/research-tasks/${RESEARCH_TASK_ID}/reports/1?format=json"
curl -sS -D "$RUN_DIR/poll-matrix.headers" -o "$RUN_DIR/poll-matrix.json" \
  "$BASE_URL/api/research-tasks/${RESEARCH_TASK_ID}/evidence-matrix?plan_version=${PLAN_VERSION}"
```

新建 task 且未有历史报告/Artifact 时，reservation 的首个 report_version 应为 1；必须以 report/API/Artifact 实际响应交叉核对，不能把 plan_version 当 report_version。报告尚未 reserved / matrix 尚未准备时，保存真实 404/409 响应作为阶段证据并继续有限轮询；其它错误按真实错误码停止或恢复，不能把错误响应改写成 generating。

task detail `GET /api/research-tasks/{id}` 是只读状态投影；matrix GET 返回真实的 `claims/evidence/dimensions/cells/limitations`。检查 `task_id`、`plan_version` 与批准计划一致；矩阵中至少有五个不同已选 Paper 的可用 `abstract` Evidence，不能将 `catalog` 当摘要，不能把 abstract 说成 fulltext。对矩阵里的真实 paper IDs 再用只读展示投影核对标题：

```sh
curl -sS -D "$RUN_DIR/paper-display.headers" -o "$RUN_DIR/paper-display.json" \
  -H 'Content-Type: application/json' \
  -d '{"paper_ids":["<来自当前 task/matrix 的 ID>"]}' \
  "$BASE_URL/api/research-tasks/${RESEARCH_TASK_ID}/paper-displays"
```

`paper_ids` 实际请求体为矩阵/报告中全部 5 个不同 ID。把 `papers[].title/year/venue` 与上面的五个官方标题逐个比对；同时核对五个矩阵 Evidence 的 ID→paper、source level、status 与引用定位。paper-displays 是 POST 只读投影；不得将显示名或官方 URL 写成 API 接受的 Evidence locator。Matrix/纸面显示路由：[`get_research_evidence_matrix`](../../../../backend/app/api/routes_research.py:1707)、[`resolve_research_paper_displays`](../../../../backend/app/api/routes_research.py:1634)。

`GET /api/research-sessions/{session_id}` 会执行 session projection reconciliation；`GET /api/research-tasks/{task_id}/events` 会 drain processing projection retry。不要将它们当成无写探测轮询。本次 E2E 若产品界面/实时用户链路实际使用它们，应把请求及可能产生的状态投影/重试写入状态轨迹，按 Task10 要求说明其副作用。

### 4. 报告终态、质量和 Artifact 验真

对 `GET /api/research-tasks/{task_id}/reports/1?format=json` 继续轮询，成功门槛不是 HTTP 202 或 task completed 的孤立状态。唯一成功条件为真实 JSON 同时满足：

- `report_version` 是本次 reservation 版本（首版新任务应为 1），`plan_version` 与已批准 plan 相同；
- `status=completed`、`generation.published=true`、`generation.path=agent_runner`、`generation.output_disposition=accepted`；
- `quality_validation.status=pass`、`cjk_count >= 1500`、`paper_count >= 5`、`comparison_count >= 1`、`supported_finding_count >= 3`、`invalid_evidence_count=0`、`revision_count <= 2`；
- `report_content.evidence_scope.paper_ids` 与五篇经 title/display 核验的真实 paper IDs 一致；正文结构、Evidence 等级和报告语义通过机器/人工独立 rubric；
- `generation` 的报告版本、task usage、AgentRun IDs、reason/fallback 字段都按实际响应记录。不能以五个目录候选、模型声称的引文或 Artifact 存在推断模型输出通过质量验证。

然后用 Artifact list 获取服务端 Artifact IDs、版本、类型、hash、run ID 和下载 URL：

```sh
curl -sS -D "$RUN_DIR/artifacts.headers" -o "$RUN_DIR/artifacts.json" \
  "$BASE_URL/api/research-sessions/${RESEARCH_SESSION_ID}/artifacts?report_version=${REPORT_VERSION}"
```

必须恰有同一 `report_version` 的 `markdown`、`html`、`citation_manifest`。按 JSON 中真实 `download_url` 逐一 GET 下载，保存 HTTP headers 和字节到本次 run 目录；对每个下载内容计算 SHA-256 并与元数据 `content_hash` 比较。解析 manifest：至少五个不同 paper ID；其 paper IDs 与 canonical report 的 Evidence scope 一致；引用的 Evidence ID 必须能回查当前 matrix。下载链接示例由真实 list response 提供，代码形状为 `GET /api/research-sessions/{session_id}/artifacts/{artifact_id}/download`；只允许 `attachment` 默认模式，HTML inline 可选。路由只公开已 published 版本。不能从 API 返回的路径字段访问本地存储路径。

成功后，执行 Task10 的人工语义 rubric：逐篇忠实度、实际跨论文比较、至少三条跨论文综合发现、未知/研究缺口、非填充内容；每项保存章节位置、paper_id/Evidence ID 与理由。字符数用 canonical `quality_validation.cjk_count` 和 `count_method=report-quality-v1` 记录；不把标题、目录、ID、引用清单或 Artifact 附录的长度加进正文计数。

## 当前证据不足时的最小复用路径

当前交接仅证明 fake Runner 的五篇摘要 Evidence 测试和当前自然语言路由实现；历史运行审计也只展示了两篇旧报告的 Artifact/结构，且没有可核对的五个论文标题或 canonical report。没有本次自然语言真实 API、真实 candidate IDs、摘要 snapshots、矩阵、生成状态和 Artifact 下载 hash。因此当前不能证明固定五篇已进入实际部署的可信矩阵。

执行时先复用当前已批准计划下的自然语言 synthesis → 受控 catalog 搜索/详情 → 已选 Paper → `EvidenceMatrixService` 持久矩阵链。若 5 个精确标题都被选中且矩阵有至少 5 个不同 Paper 的真实可用 abstract Evidence，再继续报告生成；无需下载全文，且最终报告须标明摘要范围。若具体选中集不足五篇、官方标题不匹配、摘要 snapshot 缺失/哈希不匹配或 Evidence ID 回查失败：

1. 立即保存真实 task/matrix/错误响应和 IDs，标记本次 `BLOCKED`；无可读正文的 generation 终态应为 `failed`，并记录真实 reason code。
2. 不构造 `Evidence` / `Claim` ID，不拿 `catalog:<paper_id>` 充当持久 Evidence，不手工 POST 伪造 evidence matrix，不把目录 metadata 补成摘要或全文。
3. 最小重用现有官方 USENIX catalog search/detail 路径：用精确五标题与同一 USENIX Security 2022 来源重新检索；对缺少摘要快照的候选走既有 official detail fetch，把实际摘要及其 snapshot provenance 写入目录来源后，再从新鲜自然语言 Session/Task 运行同一 approved-plan 流程。若当前服务/受控来源链不能返回其中某篇真实摘要，记录缺项并停止；不以扩大为不同论文集制造成功。
4. 已终态 Task/WorkItem 不回退、不重开；重试使用全新会话/task。报告 report_version 必须从 reservation/响应/Artifact 实际读出，不复用旧版本 ID。

这里“重新检索/详情抓取”是待主 Agent 执行的最小复用方案，不是已执行事实。若人工选集/目录详细检索不具备公开 API，不绕过受控 Tool；将能力限制作为阻塞事实写入 E2E Artifact。

## 执行时保存的 Evidence

本次 run 应至少包含：

- `runtime.json`：BASE_URL、实际端口、branch/version、开始/结束 UTC、health HTTP 状态；不含凭据；
- 每个请求的脱敏 headers、实际 body、status code、response body/SSE（例如 `01-natural-intake.sse`）及 SHA-256；
- `entities.json`：真实 conversation/user/assistant/session/plan/approval/task/work_item/AgentRun/report/artifact IDs、版本绑定和终态；不记录内部本地路径；
- `state-trace.json`：每次真实 poll 的时间、请求路径、HTTP status、task/report status、stage/revision/reason/budget 可见字段；
- `matrix.json` / `paper-display.json`：当前 task/plan 矩阵和五个真实标题映射；必要时按验收隐私规则脱敏 abstract，不虚构摘要；
- 下载的三类 Artifact、各自元数据 `content_hash` 与实际 SHA-256；Markdown/Citation Manifest 语义与完整性检查；
- `machine-quality.json`：canonical report 的质量/预算/branch 机器字段；`human-rubric.md`：Task10 五项人工结论与具体 Evidence refs；
- `result.json` / `report.md`：最终只能填写真实 `success` 或 `blocked`、失败码、重试关系、已完成步骤和剩余阻塞。

失败原始证据不得被后续 retry 覆盖。网络响应禁止记录 cookie、Authorization、API key、隐藏思维链和原始模型 prompt。实际自然语言正文和论文内容按 Task10 的脱敏规则保存；不要复制报告正文全文到交接材料。

## 就绪判断

| 门禁 | 当前结果 | 理由 |
|---|---|---|
| 当前部署 health/version/端口 | `FAIL / 未执行` | 本文只准备 API 方案，未启动或探测服务。 |
| 自然语言 API 主路径 | `FAIL / 未执行` | 没有真实 create/send SSE 请求和响应。 |
| 计划审批及 task 状态转移 | `FAIL / 未执行` | 没有真实审批、任务 ID 或状态轨迹。 |
| 固定五篇实际入选且摘要 Evidence 足量 | `FAIL / 未执行` | 只有官方论文页面可核对题名；没有当前部署目录 ID 或任务矩阵。 |
| CJK ≥1500、比较/综合发现 machine quality | `FAIL / 未执行` | 没有真实 canonical report/质量 JSON。 |
| Artifact 三类型、hash、会话消息和下载 | `FAIL / 未执行` | 没有本次运行 Artifact 或下载响应。 |
| 无背景用户步骤可复现 | `PASS / API 步骤已准备，UI文案待真实运行校准` | 路由和请求字段来自当前源码；真实按钮文案不在本文猜写。 |

**当前结论：`BLOCKED`。** 已完成接口梳理、固定论文集准备、自然语言输入和精确请求/核验步骤；尚未完成真实 API E2E。主 Agent 应在当前分支真实运行后补齐真实 IDs、响应、运行态和产物 hash，再独立完成验收；不得把本准备文档作为 `READY_FOR_USER`、API 成功证据或部署证明。
