# Spec032 Task14：真实自然语言研究 E2E（新 run，矩阵/版本化报告验收）

## 状态

**BLOCKED** — 本报告只记录本轮新 conversation/run；不覆盖此前失败、暂停或复审运行。真实任务终态为
`partial`，终止码为 `MATRIX_NOT_READY`，且只选择了 4 篇（计划要求 min=max=target=5）。

## 运行身份

- `run_id`: `spec032-task14-research-e2e-matrix-20261008T183733Z`
- 服务：`http://127.0.0.1:8000`
- 分支：`codex/spec032-final-acceptance`
- 代码提交：`68315ba`
- 服务启动会话：`96818`（由主 agent 提供）
- 开始时间：`2026-10-08T18:37:33Z`（UTC）
- 请求级模型：待发送自然语言请求时使用 `qwen3.5:9b`、`reasoning_effort: off`；未修改全局模型/阈值/env。

## 门禁前置

`GET /api/ready` HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均为 `ready`。
`GET /api/health` HTTP 200，`status=ok`、`paper_discovery_enabled=true`；服务默认模型为
`qwen3.8:27b`。完整脱敏响应摘要见 `current-research-e2e-matrix-evidence.json` 的 `ready-01`、`health-01`。

## 目标主路径

自然语言入口必须明确：USENIX Security 2024、研究主题 security/privacy、比较至少 5 篇方法与
局限、最多 5 篇、目标论文数 5、来源限定 USENIX Security、中文 Markdown/行内引用输出。
收到计划后只在真实计划同时满足 `min=max=target=5` 且 `budget.target_paper_count<=5` 时批准；
否则停止并以 BLOCKED 记录，不创建批准任务、不下载论文。

后续成功判据：真实候选评估、最多 5 篇公开论文自动导入、每篇最终状态及 `paper_id/document_id`、
非空 Evidence Matrix、canonical ResearchReport 新版本与旧版本可读链接；Markdown/HTML 下载可读且
旧版本内容不可变。Artifact metadata 仅说明不可变产物，不冒充全文或矩阵证据。

## 已完成阶段：自然语言 Intake 与计划门禁

真实 `POST /api/conversations/messages`（SSE，HTTP 200）已完成，使用请求级
`qwen3.5:9b` / `reasoning_effort=off`。新实体如下：

- conversation：`81661d4218724b56a2d35017e2cb5c5a`
- user message：`40f43ce818c74a2b8db1654b172d8a43`
- assistant plan message：`554a1175c5374490ba0b9cfcd6c8d7b7`
- research session：`3b74b17ca3b949f8919cab5db62e5f45`
- intake draft：`992c7423d7524bb5a32c7c82f0174016`
- plan version/hash：`1` / `de7ce0245c7b6468164e2f224a2744238fe73765e29e663b38dd1e4ef5648a7f`

Intake 已确认主题、目标、USENIX 来源和 2024–2024 时间范围；计划 `scope_json` 明确
`min_paper_count=5`、`max_paper_count=5`、`target_paper_count=5`，`budget_json` 的
`target_paper_count=5`。Intake 完成当时状态为 `plan_pending_approval`，随后才批准并创建本轮
ResearchTask；该阶段尚未下载或导入。
完整脱敏 SSE/GET 摘要见 `current-research-e2e-matrix-evidence.json`。

## 已完成阶段：计划批准与任务启动

复核计划预算后执行唯一一次 `approve_plan`：

- 请求：`POST /api/research-sessions/3b74b17ca3b949f8919cab5db62e5f45/commands`
- `subject_version=1`、`plan_version=1`、`output_hash` 与计划一致，幂等键为
  `plan-approval:3b74b17ca3b949f8919cab5db62e5f45:1`
- HTTP 200，批准状态 `approved`，session 状态 `queued`
- 新 ResearchTask：`e1591ee5833954e7a6e98221ff60cc01`，目标论文数 5；首次任务读取已进入
  `running`

后续轮询只针对该新 task，不重试此前旧 batch。

## 执行阶段记录：真实目录搜索、评估与自动导入

任务事件流已确认真实执行 `usenix-catalog-orchestration` → `search_paper_catalog`；s1、s2 搜索工具
均完成，服务摘要各命中 3 篇 USENIX Security 2024 候选。随后 e1 候选评估、c1 覆盖检查和 syn
初步合成均运行到终止。终端事件 `event_seq=27` 为 `status=partial`、
`error_code=MATRIX_NOT_READY`、`selected_count=4`。

系统自动创建 2 个全文批次并完成 4/4 导入（没有手动下载或补救调用）：

- batch：`f10f2307-ec0e-484e-ae9c-4221366c0ea7`、`18bb9c71-1805-4d31-88ed-84ca394b7061`
- `candidate_id → paper_id/document_id`：
  - `57e0402f82fe2ce354bea423b201fde3 → 527fe0c1515d48c78adec8f4eb7f4979 / 527fe0c1515d48c78adec8f4eb7f4979`
  - `4e6322a23b92a271dbec9906c51fe0ab → a151fcff09944e7cbd1f4086376ae914 / a151fcff09944e7cbd1f4086376ae914`
  - `9793a4a35caad52ee99f926ae7c90810 → 929a342c0b8d4c8283198751cae9b327 / 929a342c0b8d4c8283198751cae9b327`
  - `ef9e0846844e5b02834163586ea6ddc9 → 56fc315e952342158e5ae2f5ef6f01a0 / 56fc315e952342158e5ae2f5ef6f01a0`

4 个 acquisition item 与 link 均为 `completed`、无错误；但 `selected_count=4` 违反批准计划的
最小/目标 5，因此不能把自动导入的 4 篇当作满足验收的 5 篇。

## 终态产物检查

- Evidence Matrix：GET 返回 HTTP 409 `MATRIX_NOT_READY`，没有非空 matrix。
- canonical ResearchReport v1：JSON、Markdown、HTML 三种 GET 均返回 HTTP 404
  `REPORT_NOT_READY`；不存在可验收的 canonical 版本化报告、旧/新版本链接或 canonical 下载路径。
- session artifacts：只读列表可见 v1 的 `citation_manifest`、`html`、`markdown` 元数据；对应摘要产物
  下载为 Markdown 9307 bytes、HTML 9921 bytes，各 4 个引用条目，下载内容 hash 与元数据一致。
  仅有的摘要 artifact 下载路径是 `/api/research-sessions/3b74b17ca3b949f8919cab5db62e5f45/artifacts/cc16eb2b3753471198cefd6cd14766e6/download?mode=attachment`
  和 `/api/research-sessions/3b74b17ca3b949f8919cab5db62e5f45/artifacts/f7c3ee2f49bd45c6bebfcf10987b5730/download?mode=attachment`；
  它们不属于 canonical report GET，不能作为验收替代。
  但内容是目录摘要级合成，不是全文证据矩阵，也不能冒充 canonical ResearchReport。
- 旧版本不可变性：本 run 没有 canonical 旧/新报告可比；仅验证了现有 v1 artifact 下载 hash 与元数据
  一致，不能据此宣称“旧 canonical artifact immutable”。

## 验收准备度（10 项）

1. 当前部署 `/api/ready`：通过。
2. 自然语言入口、USENIX Security 2024 与 security/privacy 目标：通过。
3. `min=max=target=5` Intake/plan：通过。
4. 版本/hash 绑定批准：通过。
5. 真实目录搜索、候选评估与覆盖检查：通过。
6. 选中至少 5 篇：不通过，真实 `selected_count=4`。
7. 公开论文自动导入并提供 ID：部分通过（4/4 完成），但不满足最小/目标 5。
8. 非空 Evidence Matrix：不通过，`MATRIX_NOT_READY`。
9. canonical ResearchReport v1 及 Markdown/HTML 下载：不通过，均 `REPORT_NOT_READY`。
10. 旧/新 canonical 版本可读且旧版本不可变：不通过/不可评估；仅 artifact 元数据和摘要下载存在。

## BLOCKED 结论与最小后端建议

本轮不能交付 `READY_FOR_USER`，也不冒充 Spec 全 E2E 成功。阻塞点位于真实任务的
“候选选择数量→证据矩阵→canonical 报告”链：已批准 `target_paper_count=5`，但实际只有 4 个
selected candidates，终止为 `MATRIX_NOT_READY`；自动导入本身没有失败 item。

最小修复建议交给 backend-dev：在既有候选评估/选择阶段保留并执行 `min_paper_count=5` 的缺口/澄清
或可解释失败路径，禁止以 4 篇进入终止合成；只有满足矩阵前置后，沿现有报告生成链创建 canonical
ResearchReport v1 并暴露现有 JSON/Markdown/HTML GET。不要把 artifact metadata/目录摘要作为全文矩阵
替代，也不要新增报告系统或扩大下载范围。

## 证据文件

- 结构化证据：[current-research-e2e-matrix-evidence.json](./current-research-e2e-matrix-evidence.json)
- 本轮日志：`.codebuddy/agent-logs/spec-032/task-14/tester/20261009-023706.md`
