# Spec 030 Task10：真实 E2E 证据整合与准备度

日期：2026-10-30  
角色：tester（跨端验收）  
**初始快照结论：BLOCKED（历史保留）。** 本文整合已有自然语言 E2E、公开 report-only 重试、v5/v6 与后续案例；以下各历史 BLOCKED 不由新案例抹除。

## 2026-10-31 最终交付更新（主会话状态同步）

当前 methods-topic 案例已 READY_FOR_USER：3020 CJK、5篇、4比较、5综合发现，独立内容5/5、三产物HTTP/hash、浏览器和最终前后端回归通过，readiness10/10。最终权威结论为[tester 与独立 architect 双签](../../reviews/030-report-quality-acceptance-review.md)，操作见[人工步骤](2026-10-31-manual-acceptance.md)，真实请求/响应和产物见[methods 目录](artifacts/20261031-methods-e2e/)。Spec030 已由主会话按DoD收口，用户人工验收待执行；旧认证案例仍是失败/partial，不冒充成功。

记录勘误：下文 `exit3` 是回归轮次目录名，不是退出码；该轮真实退出码为0。最终后端是 b43bbea0 的3476通过/3跳过/82.25%，前端是58803f8c的388通过/0跳过，运行生产树与候选一致。

## 0.1 最新确认进展（2026-10-30；不解除 BLOCKED）

- 独立审查 prompt 的当时候选提交为 `6f70303f`；已记录部署在 8000 且 `/api/health` 返回 HTTP 200。该候选回归轮次为 exit3，真实退出码0，详见最终回归报告；本段是当时快照，不作为当前最终候选结论。
- 前端 v21 的 root 真实浏览器路径已实测：从精确通知 **`研究已完成：研究已完成 · 报告 v5`** 打开报告；页面 **`研究摘要与报告`** 稳定显示 v5 正式发布状态，指标为 `2912/1500`、`5/5` 逐篇、`5/1` 比较、`6/3` 发现、`0/2` 改写，正文渲染正常。截图见 [`browser-v5.jpg`](artifacts/20261030-report-v6/browser-v5.jpg)。这证明当前通知→报告展示路径可观察，不改变 v5 人工语义 rubric 的既有 FAIL。
- v6 已真实提交并返回 HTTP 202；执行证据 [`execution-manifest.json`](artifacts/20261030-report-v6/execution-manifest.json)、`request.json`、`response-headers.txt`、[`01-submit.json`](artifacts/20261030-report-v6/01-submit.json) 与终态 [`06-report.json`](artifacts/20261030-report-v6/06-report.json) 已落盘在 [`artifacts/20261030-report-v6/`](artifacts/20261030-report-v6/)。终态为 `failed`、`published=false`、`reason=AGENT_OUTPUT_INVALID`，不能把 v6 受理当作 v6 成功。
- v6 诊断证据见 [`2026-10-29-report-context-backend.md`](2026-10-29-report-context-backend.md) 新增 v6 段：`paper_ids` 结构约束（2–64 个不同 ID）失败；具体是 type、count 还是 duplicate 子因没有可用证据，本文不猜。确有 local 30s timeout→DeepSeek fallback 事件；Run 的模型名称属于陈旧投影。实际预算为 `1455/1500`，原 JSON 的 `1233` 已知陈旧，结算未超限。三项后端缺陷已指派 `report_context` 修复，但不代表已完成。

## 0.2 2026-10-31 自然语言 E2E 真实案例（machine PASS；人工 BLOCKED）

### 执行 manifest 与可追溯 IDs

本案例来自 [`20261031-natural-e2e/execution-manifest.json`](artifacts/20261031-natural-e2e/execution-manifest.json)，部署提交为 `4e63615f`，入口 `http://127.0.0.1:8000`。manifest 记录的核心实体如下；不从缺失字段反推额外 ID：

| 实体 | 实际值 |
|---|---|
| conversation | `d63f178266934ab6a790d932fd15baea` |
| research session | `eb423a0ae279472d9709cda75e957da3` |
| task | `387a5090b27550c59de86adb415eb26e` |
| report | `f8ccfb15-0670-47fc-af6b-d78ed23ea626`；version `1`；plan version `1` |
| request key | `cb37173d-6d06-59d7-b03d-38cc822250a7` |
| agent runs | `387a5090b27550c59de86adb415eb26e:syn:run-1`；`387a5090b27550c59de86adb415eb26e:syn:report-1:comparison-58f7ccbc0a664a228a73615c705f5a32`；`387a5090b27550c59de86adb415eb26e:syn:report-1:drafting-009a0456156544d0bc9f13ea1c989c77` |
| claim IDs | `6727a98b-6421-4d31-b7a2-41801615fdde`；`c3c08b80-122f-43b5-9b74-18ab43a169e8`；`8d585289-1210-4763-b1a1-5c002e6d785e` |

### 已保存的请求顺序与观察结果

1. **健康检查**：读取 [`health.json`](artifacts/20261031-natural-e2e/health.json)，服务报告 `status=ok`，模型/论文检索能力字段可见。
2. **自然语言 Intake**：提交 [`request.json`](artifacts/20261031-natural-e2e/request.json) 中的中文目标，保留 `01-intake.headers`（HTTP 200）与 [`01-intake.sse`](artifacts/20261031-natural-e2e/01-intake.sse)。目标明确写出 authentication security、USENIX 2022、5 篇、逐篇/比较/综合发现、中文字符数和证据边界。
3. **补充约束**：提交 [`supplement-request.json`](artifacts/20261031-natural-e2e/supplement-request.json)（目标 5 篇、至少 5 篇），保留 `02-supplement.headers`（HTTP 200）与 [`02-supplement.sse`](artifacts/20261031-natural-e2e/02-supplement.sse）。该次 Intake 的冗余篇数澄清已修复，仍待复审是否彻底消除。
4. **审批计划**：以 [`approval-request.json`](artifacts/20261031-natural-e2e/approval-request.json) 的 `approve_plan`、`plan_version=1` 和 `output_hash` 提交审批，保留 [`03-approval.json`](artifacts/20261031-natural-e2e/03-approval.json) 与 `03-approval.headers`（HTTP 200）。
5. **读取任务与事件**：按顺序保留 `04-task.json`/`05-task.json`/`06-task.json`/`07-task.json` 与对应请求证据；[`08-events.sse`](artifacts/20261031-natural-e2e/08-events.sse) 的事件流读取返回 HTTP 200。事件流说明中的两秒 cutoff 是读取边界，不把它写成生成失败。
6. **读取报告终态**：早期 [`06-report.headers`](artifacts/20261031-natural-e2e/06-report.headers) 为 HTTP 404，随后 [`09-report.headers`](artifacts/20261031-natural-e2e/09-report.headers) 为 HTTP 200，终态 [`09-report.json`](artifacts/20261031-natural-e2e/09-report.json)/[`10-report.json`](artifacts/20261031-natural-e2e/10-report.json) 记录 `completed`、`published=true`、machine quality `pass`。这证明本案例报告最终可读，不掩盖此前等待中的 404。
7. **读取产物与论文展示**：[`11-artifacts.json`](artifacts/20261031-natural-e2e/11-artifacts.json)、[`12-matrix.json`](artifacts/20261031-natural-e2e/12-matrix.json)、[`13-paper-displays.json`](artifacts/20261031-natural-e2e/13-paper-displays.json) 均有保存；三份下载 hash 核对为 HTTP 200 且 `matches=true`，浏览器观察截图为 [`browser-report.jpg`](artifacts/20261031-natural-e2e/browser-report.jpg)。

### 当前案例结果与人工边界

- 机器结果：`completed/published=true`、machine `pass`、`2920` CJK、`5` papers、`3` comparisons、`5` supported findings、`0` invalid evidence、`0` rewrites、revision `0`；manifest 的 `human_acceptance=blocked_pending_independent_review`。这只证明机器结构/计数和产物链路，不等于目标认证主题或人工语义通过；manifest 已明确记录“初始自然语言需要不必要的篇数澄清”和“选集与认证安全主题不充分”两项 blocker。
- 三份下载产物 hash 均实测通过：citation manifest `0376e5c47c2946ea813ba5fa44b91c2b`，`1437` bytes，SHA-256 `9aa93e73da178473ef2f05f32f8bf6e4aa09e279ea70506978f129c495aa3d16`；HTML `4ecfa805bab340e793aeaa40254e2478`，`14977` bytes，SHA-256 `d291454c1f3019f9bf21b4c88af5d09bf0dc2aa9e7b49b5e8367b4a3922fee2c`；Markdown `4ab008dd475d485a9ec7f3410b04d5d1`，`12171` bytes，SHA-256 `370af56603ac292915dcca319ac86b5965e48e7c2a56e75837e10f7060f5ae4f`。
- 独立 [`content-review.md`](artifacts/20261031-natural-e2e/content-review.md) 结论为 **4 PASS / 1 FAIL**：逐篇忠实度、综合发现支持、研究缺口/未知、非填充内容 PASS；比较有效性 FAIL，且目标认证主题未达成，原因是五篇实际选集偏向 ML 安全评估、Web 缓存欺骗、LGBTQ+ 安全建议、内核利用可靠性和 RPKI 降级攻击，不能代表请求的认证机制类别。WCD 的“认证门后”背景和 RPKI 的路由 validation 不得当作用户登录认证。
- 初次 Intake 的冗余补篇数问题已修复，待独立复审；当前检索偏题由另一 agent 诊断中，本文不预判其结果。前 v5 的 DANE 语义局部 FAIL 与 v6 的 `AGENT_OUTPUT_INVALID` 失败均继续保留。
- 本案例机器 PASS 不解除人工内容 FAIL、选集偏题或现有 readiness 阻塞；不把机器成功写成全链路成功，也不把任何排查转交用户。
- 旧 v5 的语义 FAIL（DANE gap 将已报告的纵向结果表述为未报告）仍是当前阻塞；必须等待未来完成版本再重新执行人工 rubric，不能覆写 v5。

## 0.3 2026-10-31 R3 自然语言 Intake（已启动；仍 BLOCKED）

### 部署、实体与真实请求顺序

- 安全诊断 review 的提交 `44752b60` 已部署；该 review 的结论是 PASS，但它只覆盖安全诊断范围，不是 Spec030 的内容验收或全链路通过证明。
- R2 的 partial 结果继续保留为历史证据：evaluator 只选出 `1/5`，安全评估为未知，具体子因没有可复核证据；不把 partial 或未知原因解释成成功。相关快照仍在 [`20261031-natural-e2e-r2/`](artifacts/20261031-natural-e2e-r2/)。
- R3 的线上实体由 [`entities-online.json`](artifacts/20261031-natural-e2e-r3/entities-online.json) 记录：deployment commit `44752b60`；conversation `252609a6130e40a4818ac1560656111d`；research session `9ff213128bd14ea8841e7bd65b7ace13`；task `3efcee5268f25980ae09d0d0fbe7a145`；plan version `1`；入口模型 `deepseek:deepseek-flash`；reasoning effort `off`。这些是可追溯实体 ID，不是凭据。
- 旧的 Qwen/off 入口与模型能力不一致而失败；随后使用显式 DeepSeek/off 的自然语言入口，Intake 返回 `missing=[]`，该事实只证明 Intake 阶段通过。请求快照见 [`request.json`](artifacts/20261031-natural-e2e-r3/request.json)、[`online-request.json`](artifacts/20261031-natural-e2e-r3/online-request.json)、[`retry-request.json`](artifacts/20261031-natural-e2e-r3/retry-request.json)，过程 SSE 见 `01-intake.sse`、`02-intake-retry.sse`、`03-intake-retry.sse`、`04-online-intake.sse`。
- `05-approval.headers` 为真实 HTTP 200；[`05-approval.json`](artifacts/20261031-natural-e2e-r3/05-approval.json) 记录 plan version 1 的 approval 已受理，task status 为 `queued`。随后 `06-task.headers` 真实 HTTP 200， [`06-task.json`](artifacts/20261031-natural-e2e-r3/06-task.json) 的 task `3efcee5268f25980ae09d0d0fbe7a145` 仍为 `running`。
- 当前 R3 目录只有 Intake/审批/运行中证据；尚无该 R3 的 completed/published report、内容 rubric、产物 hash 或浏览器复核。因此不能写 R3 成功，也不能用 `missing=[]`、HTTP 200 或 running 替代完整验收。

### 待提交证据的明显敏感内容审计（只记路径/分类/数量）

本次只对 `docs/sdd/plans/030/artifacts/` 下 **152 个**非 `.env`、非图片证据文件做静态模式检查，包含 [`20261031-natural-e2e-r3/`](artifacts/20261031-natural-e2e-r3/)；没有读取 `.env`，没有打印疑似值，没有删除或修改任何产物。

| 检查分类 | 文件数 | 匹配数 | 结论 |
|---|---:|---:|---|
| 明显凭据字段标签（authorization/token/secret/private-key/cookie 等） | 0 | 0 | 未发现明显凭据字段标签 |
| 隐藏思维字段标签（chain-of-thought/scratchpad/internal reasoning/deliberation 等） | 0 | 0 | 未发现隐藏思维字段标签 |
| 私钥、Bearer token、云密钥、GitHub token、JWT 等明显值模式 | 0 | 0 | 未发现这些明显值模式 |

该审计只是“明显模式未发现”的提交前检查，不是凭据安全证明；若后续新增证据文件，需按同一分类重新检查。该检查不改变 R2 partial、R3 running 或既有 v5/v6 内容阻塞。

## 1. API E2E 证据

### 运行实体与自然语言入口

本次证据链不是“新建任务后一次成功”。它由一个真实 Intake/审批任务、首版报告失败，以及该任务上的 report-only 新版本重试组成。重试一直复用同一个 ResearchTask；没有为 v2–v5 另建 Task。

| 实体 | 实际值 | 证据 |
|---|---|---|
| 对话 / 用户消息 | `conversation_id=cd5d8b1c3648462d9d5a59a903b832b4`；`user_message_id=78db8754ef52466cb5a5e4731feb0a20` | [`20261030-real-report-r2/01-intake.sse`](artifacts/20261030-real-report-r2/01-intake.sse) 的 SSE meta 帧 |
| ResearchSession | `50585f56b1b641fd9a5bd00a6379ff81` | [`02-approve.json`](artifacts/20261030-real-report-r2/02-approve.json)；v5 `05-artifacts.json` |
| ResearchTask | `bdcd7fc185425e0f8443599e9cdbe8ec` | [`02-approve.json`](artifacts/20261030-real-report-r2/02-approve.json)、[`03-task.json`](artifacts/20261030-real-report-r2/03-task.json) 与所有 report submit snapshots |
| Plan / approval | `plan_version=1`；`subject_version=1`；approval `94447c688bae43469539d08856b81041`，`approved` | [`02-approve.json`](artifacts/20261030-real-report-r2/02-approve.json) |
| Intake 确认字段 | `topic=password security`；`objective=password authentication login security`；`time_range=2022–2022`；`constraints=target_paper_count:5,min_paper_count:5`；`sources=usenix`；`language=zh` | `01-intake.sse` 的 `intake.fields`；`02-approve.json` 的实际 plan |

原始自然语言消息文本没有保存在 `01-intake.sse`；它保留了消息 ID、SSE Intake 输出以及 `user_explicit` 字段。审批文件保存的是响应 JSON，没有原始 HTTP headers/body。这里不从解析结果反向拼造原始 prompt。初始 `03-task.json` 快照为 `running`；后续报告记录称首版失败后没有重开原 Task，但没有单独保存 terminal Task 的 API 响应。

### 报告重试链

| 版本 | report_id / WorkItem | 已保存的请求/响应事实 | 终态与结果 |
|---|---|---|---|
| v1 | `5c48535f-0480-4568-bb3c-3614031743cb`；`bdcd7fc185425e0f8443599e9cdbe8ec:syn` | [`04-report.json`](artifacts/20261030-real-report-r2/04-report.json) 是失败报告快照 | `REPORT_QUALITY_CONTEXT_UNAVAILABLE`；`published=false`、`output_disposition=not_run`。文件没有 durable `status` 字段，故此处只记录已存 reason/published 事实。 |
| v2 | `4e71c52b-ff5e-4c15-8ffe-347af2dd6376`；WorkItem `report-041cdf7fe5da4622afa3381f02894cf8` | [`result.md`](artifacts/20261030-report-only/result.md) 明确记录公开 `POST /api/research-tasks/bdcd7fc185425e0f8443599e9cdbe8ec/reports`、`plan_version=1`、HTTP 202；[`01-submit.json`](artifacts/20261030-report-only/01-submit.json) 是 `generating/pending/unpublished` 响应体 | [`03-report.json`](artifacts/20261030-report-only/03-report.json) 为 machine accepted/published；2,428 CJK、5 篇、2 项比较、4 条支持发现、0 无效 Evidence、revision 0。随后 v2 内容评审发现 MIGP 部署/模拟结果表述矛盾和相关性过度概括，故不作为最终人工语义通过版。 |
| v3 | `558d1fc6-5128-495b-942f-378b7d15e118`；WorkItem `report-9d5e254e00f840f9bb11d772dbb93176` | [`01-submit.json`](artifacts/20261030-report-v3/01-submit.json) 保存新版本受理体；没有保存此版本的原始 HTTP status/header/body envelope | [`02-report.json`](artifacts/20261030-report-v3/02-report.json) 为 unpublished，`TASK_TIME_LIMIT_REACHED`。只读诊断 [`03-budget-diagnosis.md`](artifacts/20261030-report-v3/03-budget-diagnosis.md) 记录 task 总用时 `380/1500s`、loops `12/160`、tools `2/640`；失败在当时比较阶段 120s claim 内，不是 Task 总预算耗尽。 |
| v4 | `4ec945cd-77eb-4f3a-9d4c-e0a83ec2f60a`；WorkItem `report-44ae23331fea4cf4b2e5f4f83a3f9d0f` | [`01-submit.json`](artifacts/20261030-report-v4/01-submit.json) 保存新版本受理体；该目录未保存原始 HTTP status/header/body envelope | [`02-report.json`](artifacts/20261030-report-v4/02-report.json) 为 unpublished，reason `AGENT_OUTPUT_INVALID`，task 用量 `647/1500s`。现有文件未提供可据以归因的更多正文诊断，本报告不推测。 |
| v5 | `9710646c-0c7b-491b-8355-669787bc9c8c`；WorkItem `report-ee3dc27ae7b24218a1a3aaeaa6e100b4` | [`01-submit.json`](artifacts/20261030-report-v5/01-submit.json) 是 `generating/pending/published=false` 的受理体；v5 目录未保存 POST 的 HTTP 状态码、请求 headers 或完整原始 request body。随后 [`07-current-report.json`](artifacts/20261030-report-v5/07-current-report.json) 是读取到的当前 durable report JSON body | durable GET 投影为 `status=completed`、`published=true`、`output_disposition=accepted`、`path=agent_runner`；v5 是 report-only retry 链最终成功版本。 |
| v6 | report_id / WorkItem：以终态 artifact 为准，未在本次同步中补造 | 真实 POST 已返回 HTTP 202；[`request.json`](artifacts/20261030-report-v6/request.json)、[`response-headers.txt`](artifacts/20261030-report-v6/response-headers.txt)、[`01-submit.json`](artifacts/20261030-report-v6/01-submit.json) 与 [`06-report.json`](artifacts/20261030-report-v6/06-report.json) 已保存 | **失败终态：`failed`、`published=false`、`reason=AGENT_OUTPUT_INVALID`**。不具备 completed/published 成功证据，不能解除 v5 语义阻塞。 |

由 v2 `result.md` 可证公开 report-only 路径至少成功受理一次；v3/v4/v5/v6 的提交快照与版本 URL/Artifact 表明同 task 的后续版本。v3/v4/v5 目录没有保存各次 POST 的完整原始 envelope；v6 则已保存 request/headers/submit、execution manifest 与失败终态。`07-current-report.json` 和 `06-read-markdown.md` 保存了 GET response body，不带 HTTP status/header。以上证据不伪造缺失的 API 元数据，也不把内部函数或测试替代真实链路。

### v5 机器结果、Run 与正式产物

v5 的 [`04-report.json`](artifacts/20261030-report-v5/04-report.json) 与 [`07-current-report.json`](artifacts/20261030-report-v5/07-current-report.json) 的 `report_id`、`report_version`、`report_content`、`quality_validation` 和 `generation` 一致；后者另投影 durable task/report `status=completed`、`published=true`、`plan_version=1`。

- Machine quality：`report-quality-v1 / pass`；`count_method=report-quality-v1`；`cjk_count=2912`；`paper_count=5`；`comparison_count=5`；`supported_finding_count=6`；`invalid_evidence_count=0`；`revision_count=0`；`failure_codes=[]`。
- 报告预算：`elapsed_seconds=1139/1500`；`model_loops_used=26/160`；`tool_calls_used=2/640`；token/cost 为 `null`；实际 provider/model 为 `deepseek / deepseek:deepseek-flash`，fallback reason 为 `null`。
- 最终 canonical `agent_run_ids`：比较 `report-ee3dc27ae7b24218a1a3aaeaa6e100b4:report-5:comparison-7e765b39643a4336912a3cb9528e9c98:attempt-4`；drafting `report-ee3dc27ae7b24218a1a3aaeaa6e100b4:report-5:drafting-a774c60e364a4a989203f01b359c3f8c`。本段只列 canonical 响应中登记的最终 IDs，不补造未登记的中间尝试。
- `report_url`：`/api/research-tasks/bdcd7fc185425e0f8443599e9cdbe8ec/reports/5?format=json`。当前 Markdown/HTML/manifest 下载路径见对应 Artifact 表。

| Artifact | artifact_id | SHA-256 | v5 download URL |
|---|---|---|---|
| Markdown | `15668170259d411aa5c5e192ff266a7a` | `0d2bdd440943e3d592de8228eaab0b08992367db9f24aaf8be77e0109e69e019` | `/api/research-sessions/50585f56b1b641fd9a5bd00a6379ff81/artifacts/15668170259d411aa5c5e192ff266a7a/download` |
| HTML | `d3c40bd9e64d417ba156dd4b74a45493` | `718443a16cbd280b983c6a1f32f8325164e8e322d23250c3c3e2608c928147b8` | `/api/research-sessions/50585f56b1b641fd9a5bd00a6379ff81/artifacts/d3c40bd9e64d417ba156dd4b74a45493/download` |
| Citation manifest | `1086a6af4aef41d68a3c1c4f58a88a24` | `c5cef3829a3921ef41fcc1ffe735d19c690c3c6985b2ca66e69e2da5ee3a52f1` | `/api/research-sessions/50585f56b1b641fd9a5bd00a6379ff81/artifacts/1086a6af4aef41d68a3c1c4f58a88a24/download` |

本轮独立读取计算得到：[`06-read-markdown.md`](artifacts/20261030-report-v5/06-read-markdown.md) 为 **11,905 bytes**，SHA-256 与 markdown Artifact 一致；落盘 [`report.html`](artifacts/20261030-report-v5/report.html) 为 **14,952 bytes**，hash 与 html Artifact 一致；[`citations.json`](artifacts/20261030-report-v5/citations.json) 为 **807 bytes**，hash 与 citation manifest Artifact 一致。三个产物文件均与 [`05-artifacts.json`](artifacts/20261030-report-v5/05-artifacts.json) 中的版本 5 hash 匹配。该证据验证了当前落盘响应/产物内容与 Artifact hash 的一致性；v5 目录没有随响应保存 HTTP status/header 或当前部署 commit，因此不能据此填造这些值。v2 的 [`result.md`](artifacts/20261030-report-only/result.md) 记录的是较早部署 `a955e2ee` 与 `http://127.0.0.1:8000/`，不能自动当作 v5 部署身份。

### v6 失败终态与诊断边界

v6 的真实终态是 `failed`、`published=false`、`reason=AGENT_OUTPUT_INVALID`，因此没有新的正式报告可供人工语义验收。执行 manifest、提交响应和终态响应均保留在 [`artifacts/20261030-report-v6/`](artifacts/20261030-report-v6/)。诊断只确认 `paper_ids` 的 2–64 个不同 ID 结构约束失败；type/count/duplicate 的具体子因不可得，不能从错误码推断。另有 local 30s timeout→DeepSeek fallback 事件；Run 模型名称是陈旧投影，实际预算以 `1455/1500` 为准，未超限。三项 `report_context` 后端缺陷已指派修复，但修复尚未验收。

### 真实 Evidence 映射

`05-matrix.json` 有 5 篇 selected paper、5 条 `available/abstract` Evidence、2 个批准 dimension 和 50 个 cell。报告与 matrix 的实际 paper/Evidence IDs 为：

| 范围 | paper_id | evidence_id | 与口令登录问题的关系 |
|---|---|---|---|
| Browser fingerprint / phishing | `ebd22ee1f1afa72047b92e07cb9626a1` | `evidence-1` | adjacent |
| MIGP / compromised credential checking | `6d765c25b0f48ab1306c39f9911e9169` | `evidence-2` | direct |
| PAL / ARM Pointer Authentication / kernel CFI | `179cb9c78ac1f2cb590a40d29e3a3350` | `evidence-3` | cross-domain |
| DANE / SMTP TLSA | `f6da8b41ce47fdb68cf10608582960d2` | `evidence-4` | cross-domain |
| Facial liveness verification | `d85997790b8c073de475edc280f32413` | `evidence-5` | adjacent |

这些 IDs 来自 [`05-matrix.json`](artifacts/20261030-real-report-r2/05-matrix.json)；没有按论文标题生成或替换 ID。v5 内容评审只读 primary catalog abstracts/provenance，5 个 abstract digest 均与冻结 matrix snapshot 匹配；未检查全文，也未复制全文内容。

## 2. 人工语义 rubric（Task10）

Machine `quality_validation=pass` 仅证明 schema、计数、选集与引用映射，不等于以下人工语义通过。v5 结构中有 5 篇分析、5 个 comparisons、6 个 findings 和 6 个 research gaps；人工判定如下。

| Task10 项目 | 判定 | 对应证据 / 理由 |
|---|---|---|
| 1. 逐篇忠实度与相关性边界 | **PASS（qualified）** | v5 独立内容评审逐一核对 `paper_analyses` 与五个摘要：e1 指纹/钓鱼、e2 MIGP、e3 PAL kernel CFI、e4 DANE SMTP、e5 FLV 均与摘要主要事实相符；关系显式标为 `adjacent/direct/cross-domain`，没有把 PAL 内核 CFI 冒充口令登录机制。限定：只有 MIGP 是 direct password-credential study；其余四篇是 adjacent/cross-domain，故不能把这份混合选集表述为五篇直接相关的口令认证综述。参见 [v5 内容评审](artifacts/20261030-report-v5/content-review.md)。 |
| 2. 跨论文比较有真实关系 | **PASS（qualified）** | `cross_paper_comparisons[1..5]` 均引用至少两个实际 paper IDs/Evidence IDs；评审确认比较保持系统层级分离并区分模拟与部署事实。局限：两种 dimension 标签重复，且 PAL 的“consistency issue”措辞不够准确；建议修饰，但评审没有认定为无比较或凑引用。 |
| 3. 至少三条多论文支持的综合发现 | **PASS** | `synthesis_findings` 有 `syn-1..syn-6` 共 6 条；每条的 `paper_ids` 和 `evidence_ids` 至少覆盖两个不同论文。具体跨论文组合包括 `syn-2`=`evidence-1/evidence-5`、`syn-3`=`evidence-3/evidence-4`；其余项覆盖多篇或全五篇。独立内容评审认为这些综合保留了各系统层边界，不是把五个摘要全部说成密码登录证据。 |
| 4. 研究缺口、未知与已报告事实 | **FAIL（局部）** | 6 个 gaps 均明确标为 reviewer-derived inference；但 `research_gaps[6]` 仅由 `evidence-4`（DANE）支持，声称摘要未给出“部署纵向结果”。同一 DANE 摘要确有纵向测量及高层运营结果；实际缺失的是测量窗口、详细时间序列和代表性。故此句把可知结果说成未报告，违反 Task10 对未知/缺口的精确标注。需在未来的新 report version 修正到“摘要未给详细窗口/时序/代表性”；不可覆写 v5 或把该问题改成 machine result。 |
| 5. 非填充内容 | **PASS** | 独立内容评审从 `report_content` 重算 CJK=2,912，与 machine count 一致；篇章内容由逐篇方法/发现、跨论文比较、综合和有证据范围的 gaps 组成。评审未发现依赖重复空话凑字。 |

人工语义 rubric 为 **4 PASS / 1 FAIL**。因此按 Task10 的“任一人工项 FAIL 则语义验收 FAIL”规则，v5 不能签语义验收通过。内容评审列出的其他非阻断改进是：citation manifest 只给 opaque paper/Evidence IDs（缺标题/作者/DOI/来源链接）；第一条 gap 应更精确区分详细抽样框架与摘要已报告的样本规模；comparison labels 重复；PAL 比较措辞需改为更贴近摘要的 hindsight 问题。这些与 DANE gap 的严格式 FAIL 分开记录。

## 3. 分端评审与回归记录

### 当前可用评审结论

各独立代码评审文档保留首次 BLOCK 作为历史；其后附的当前窄复审为 PASS：

- 后端 quality foundation、report-content output/rendering、Runtime/context、generation helper、state/budget store、canonical store/reservation successor、publication、artifact visibility、provider deadline，以及空 Markdown/HTML Artifact read-back：见 `docs/sdd/reviews/030-quality-foundation-backend-review.md`、`030-report-content-output-review.md`、`030-report-content-rendering-review.md`、`030-report-runtime-context-review.md`、`030-report-generation-helper-review.md`、`030-report-state-backend-review.md`、`030-report-canonical-store-review.md`、`030-report-publication-review.md`、`030-report-artifact-visibility-review.md`、`030-report-reservation-backend-review.md`、`030-report-provider-deadline-review.md`。本报告只采用各文档最新的 follow-up 结论，不把首轮历史 BLOCK 当作当前代码阻塞。
- Task09 前端静态/竞态评审最新结论为 PASS：`docs/sdd/reviews/030-report-quality-frontend-review.md`。它验证了代码级报告版本选择、通知恢复、旧列表响应竞态与 v5 JSON/Markdown 选择；该评审和 `2026-10-30-report-quality-frontend.md` 明确未完成当前部署版本的最终浏览器复测。
- 内容评审：[`v5 content-review.md`](artifacts/20261030-report-v5/content-review.md) 是 **qualified content PASS**，但 Task10 第4项存在上表的局部 FAIL。该评审不声称 Spec030 已完成。

### 全量回归状态

未重复运行全量回归。已有 [`2026-10-30-final-regression.md`](2026-10-30-final-regression.md) 记录当前候选 `6f70303f` 的结果为 **exit 3**、`3450 passed`、`3 skipped`、coverage `82.15%`、耗时 `250.43s`；该退出码不是全量门禁通过，且本次同步没有补造未提供的失败计数。历史后端候选曾记录 `3,441 passed, 3 skipped, 0 failed`、coverage `82.13%`，不能覆盖当前 exit 3；Ruff 基线差分 0 新增的旧结论也不能把当前回归写成全绿。Ruff 绝对检查曾有 57 条基线诊断（退出码 1），相对基线没有新增项；不要把绝对 Ruff 退出码写成全绿。

## 4. 人工验收案例（实测与待验证分层）

### 4.1 当前 v21/v5 浏览器路径（已实测，仍不是最终人工验收）

以下只记录当前候选真实浏览器已经观察到的 v5 展示路径；它不覆盖 v6 失败后的用户恢复路径，也不通过 v5 语义 rubric。

| 步骤 | 点击/输入 | 点击后提示 | 等待与等待中显示 | 下一步 | 失败恢复 |
|---|---|---|---|---|---|
| 1. 打开当前候选 | 在当前前端 root 打开 `http://127.0.0.1:8000/`；当前审查候选为 `6f70303f`。 | 当前部署 `/api/health` 实测 HTTP 200；页面入口与资源可继续进行浏览器观察。 | 等待页面加载完成；本次观察以 root 页面可交互为准。具体加载中的 UI 文案**待验证**。 | 继续等待精确完成通知出现。 | 若 root 或 health 不可达，保存真实地址、状态和页面提示；不要改用历史端口或把历史 v5 读取结果当当前部署成功。 |
| 2. 识别已完成通知 | 在通知区域查找并点击精确文本 **`研究已完成：研究已完成 · 报告 v5`**。 | 已实测该通知可打开报告入口。 | 等待通知对应的报告视图打开；本次实测只确认 v5 展示，未把 v6 失败状态混入 v5 展示。 | 进入标题为 **`研究摘要与报告`** 的报告页面。 | 若通知缺失、文本不同或点击后未打开报告，记录实际文本并标为待验证；不要用 API 受理体替代 UI 通知。 |
| 3. 核对 v5 报告页 | 在 **`研究摘要与报告`** 页面查看 v5 的发布状态和指标。 | 已实测页面稳定显示 v5 正式发布；指标为 `2912/1500`、`5/5` 逐篇、`5/1` 比较、`6/3` 发现、`0/2` 改写。 | 等待页面稳定后再核对正文；本次观察中报告正文渲染正常。 | 继续滚动查看正文与报告结构，并保存截图 [`browser-v5.jpg`](artifacts/20261030-report-v6/browser-v5.jpg)。 | 若页面跳回其他版本、正文空白或指标变化，记录当前 report version、实际提示和截图；该项不得记为通过。 |
| 4. 区分展示通过与语义通过 | 阅读正文并把当前展示结果与 v5 内容评审分开记录。 | 正文展示正常，但 v5 内容评审仍有 DANE `research_gaps[6]` 的语义 FAIL；v6 终态为 `AGENT_OUTPUT_INVALID`。 | v6 未形成可供阅读的 completed/published 报告；等待后端修复和新的真实版本。 | 仅在新的版本有真实 completed/published 证据后，重新核对正文、指标、逐篇/比较/发现/改写和语义 rubric。 | v5 语义 FAIL 不可通过刷新或重新打开页面解除；保留 v5 版本和 hash，v6 失败也不能冒称成功。 |

### 4.2 待验证的完整人工路径

以下只作为后续浏览器复测提纲。未观察的按钮名、提示、等待界面和失败恢复均保留“待验证”，不虚构产品文案。2026-10-31 自然语言请求正文已保存于 [`request.json`](artifacts/20261031-natural-e2e/request.json)，但用户人工点击入口与失败恢复文案仍未独立实测。

**入口与前置条件**：v2 记录曾使用 `http://127.0.0.1:8000/`、提交记录标注部署提交 `a955e2ee`；这不是 v5 当前部署身份。root 完成最后浏览器复测时须记录当时 URL/端口/提交、health 状态及浏览器/资源版本。现有 session/task IDs 仅用于读历史报告，不得冒充新鲜 E2E 实体。

| 步骤 | 点击/输入 | 点击后提示 | 等待与等待中显示 | 下一步 | 失败恢复 |
|---|---|---|---|---|---|
| 1. 创建研究 | 在当前部署打开研究自然语言入口；输入 [`request.json`](artifacts/20261031-natural-e2e/request.json) 中已保存的真实中文 prompt，确认目标为 5 篇、USENIX、2022、中文。入口与输入框名称现场未验证。 | 2026-10-31 Intake SSE 与 `01-intake.headers` 已保存；UI 是否显示同样内容未独立观察。 | 等待 plan 帧；本次 SSE 有“研究计划已生成，等待用户批准。”摘要；页面等待样式未验证。 | 检查真实 plan 内容后再批准。 | 字段或 plan 不一致则保存真实错误体并停止；不要改走结构化 session API 冒充自然语言成功。 |
| 2. 审批计划 | 点击审批操作（准确按钮文案待现场验证），审批当前 plan_version 与 output_hash。 | `02-approve.json` 实际响应为 `status=queued`、approval `approved`、Task `planning`。当前 UI 文案未验证。 | 等待 Task 的可观察推进；UI/SSE 阶段文案未验证。 | 查看真实选集与 Evidence Matrix，确认至少五个唯一 paper/Evidence 且来源级别为 abstract/fulltext。 | 计划哈希/版本冲突时保留响应，按 UI 实际可重试指引恢复；不重建或伪造实体 ID。 |
| 3. 报告提交与失败恢复 | 初始合成失败后，从现有 Task 通过公开“生成/重试报告”操作申请新版本；按钮名待浏览器确认。真实公开重试例子是同 task 上的版本 2–6，不是新 task 的单次成功。 | v2 `POST` 实际记录 HTTP 202；v3/v4 submit 快照之后分别出现预算/输出失败，v6 终态为 `failed/published=false/AGENT_OUTPUT_INVALID`。UI 提示未验证。 | 等待 JSON 版本状态；从实际 API 判定 `completed + published=true + quality pass` 才算正式报告。页面实际进度未验证。 | 对最终成功版记录 report/version/WorkItem/AgentRun IDs 并打开同版本正文/Artifact；v6 失败后不得打开其作为正式报告。 | 网络结果不确定时 UI 应复用同一幂等请求；用户主动重试应生成新版本。错误码、重试按钮文案与失败后的可操作恢复均待浏览器现场核实。 |
| 4. 阅读与校验 | 在报告版本控件中选择该报告版本，分别查看 Markdown/HTML/JSON 和 Citation Manifest；控件名称待现场验证。 | 2026-10-31 report v1 已 `completed/published=true`，三份产物下载 HTTP 200 且 hash 匹配；浏览器正文/指标截图见 [`browser-report.jpg`](artifacts/20261031-natural-e2e/browser-report.jpg)。 | 等待目标版本 API/Artifact 返回；通知或终态 SSE 刷新期间必须仍选中目标 report_version。 | 对照同版本的 5 篇分析、3 个比较、5 个综合发现、Evidence IDs 和质量指标；再执行独立内容 rubric。 | 若版本控件跳回 plan-version 默认值、正文为空、视图/hash 不一致或选集偏离目标认证主题，保留请求和状态轨迹，停止交付；不得用 machine `completed` 替代人工语义通过。 |

**成功判据草稿**：当前部署可访问；真实自然语言被解析并审批；同一新鲜 Task 经报告生成/必要的公开重试得到 `completed + published=true` 的新 report version；机器质量达到合同门槛且人工 rubric 全 PASS；Markdown/HTML/manifest 与同版 Artifact/hash 相符；浏览器所选版本在通知/SSE/刷新后仍与 API 一致。当前尚不满足这些全部现场条件。

## 5. 十项准备度矩阵

| # | Task10 readiness 项 | 结果 | 当前依据 / 缺口 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | **PASS（6f70303f root 浏览器实测；health 200）** | 当前审查记录部署在 8000 且 `/api/health` HTTP 200；完整资源/提交绑定仍以当前候选证据为准。 |
| 2 | 真实 API 创建入口成功 | **PASS（公开 retry 链 + 2026-10-31 natural E2E machine PASS；R3 尚运行中）** | v2 `result.md` 记录公开 POST HTTP 202；v3–v6 有同 task 的独立 submit snapshots；2026-10-31 新 task `387a5090b27550c59de86adb415eb26e` 的真实 Intake/补充/审批/报告链已保存，机器报告 `completed/published=true`。R3 的显式 DeepSeek/off Intake 返回 `missing=[]`、审批 HTTP 200，但 task 仍运行中，不能当作终态成功。人工内容仍 FAIL。 |
| 3 | 主路径参数正确解析 | **PASS（R3 Intake missing[]；历史选集主题 FAIL）** | R3 的显式 DeepSeek/off 自然语言 Intake 返回 `missing=[]`，请求/重试快照见 [`20261031-natural-e2e-r3/`](artifacts/20261031-natural-e2e-r3/)；2026-10-31 [`request.json`](artifacts/20261031-natural-e2e/request.json) 与历史 Intake SSE 保存目标认证类别和 5 篇约束，但历史实际选集偏离认证主题，比较有效性/目标主题人工 FAIL。 |
| 4 | Task/报告状态推进 | **PASS（历史新案例 completed/published；R3 running 未终态；旧 v6 失败保留）** | 2026-10-31 task `387a5090b27550c59de86adb415eb26e`/report `f8ccfb15-0670-47fc-af6b-d78ed23ea626` 的终态为 `completed/published=true`，v5 durable JSON 仍为 completed，v6 终态为 `failed/published=false/AGENT_OUTPUT_INVALID`；R3 task `3efcee5268f25980ae09d0d0fbe7a145` 当前 `running`，初始 task 快照及版本路径均保留。 |
| 5 | 前端显示处理中提示 | **FAIL / v6 生成失败** | v21 已实测完成通知与 v5 报告稳定展示，但没有可交付的 v6 生成中终态；v6 最终为 `failed/AGENT_OUTPUT_INVALID`，无法证明处理中阶段和恢复提示。 |
| 6 | 用户知道何时点击或等待 | **PASS（v5 完成通知已实测；失败恢复文案待验证）** | 已观察精确通知 `研究已完成：研究已完成 · 报告 v5`，用户可据此点击查看报告；v6 失败后的 UI 下一步/等待/重试文案尚未观察。 |
| 7 | 核心业务产物真实生成 | **PASS（机器产物；人工主题仍 FAIL）** | v5 与 2026-10-31 新案例均有 Markdown/HTML/citations；新案例三份下载 HTTP 200 且 hash `matches=true`，并有 `browser-report.jpg`。机器产物存在不等于目标认证专题或人工语义通过。 |
| 8 | 失败状态有可操作恢复 | **PASS（API retry；UI 操作未验证）** | v1–v4 失败/改进记录没有被覆盖；同一 Task 经公开新版本 retry 到 v5。用户通过 UI 发起 retry 的具体按钮与失败恢复显示仍未观测。 |
| 9 | 页面状态与 API 状态一致 | **PASS（v5 展示路径实测；v6 为失败终态）** | v21 root 浏览器从精确 v5 完成通知打开页面，稳定显示 v5 正式发布与对应指标；v6 API 终态为 `failed/published=false`，没有可供页面展示的成功版本，不能将 v5 展示外推到 v6。 |
| 10 | 无上下文用户可复现步骤 | **FAIL / 草稿** | 本文草稿明确标记了未观测项，但缺原始 prompt、当前入口/按钮文案、当前部署身份、实测等待和恢复提示；不满足 Task10 的独立可执行案例。 |

当前针对已实测 v5 展示路径的暂计数为：**8 PASS / 2 FAIL / 0 N/A**。N/A 未使用。该计数不代表最终候选准备度：v5 人工 rubric 项 4 仍 FAIL，v6 已失败且修复未验收，R3 task 仍 `running` 且没有 completed/published report，6f70303f 全量退出码为 3，因此继续保持 BLOCKED，不进入用户验收。

## 6. Final Decision 与解除条件

**BLOCKED — 不允许交给用户人工验收，不标记 Spec030 完成。**

已完成/已观察：真实 Intake/审批/Task/Matrix 记录；同一 Task 的 v1 失败与 v2–v6 report-only 公开版本链（v6 失败终态）；v5 machine quality、durable completed/published、Markdown/HTML/citation Artifact 和逐项 SHA-256；v21 root 浏览器 v5 展示复核；2026-10-31 自然语言 E2E 的 machine `completed/published=true`、三份下载 hash PASS、browser screenshot 与 manifest IDs；安全诊断 review `44752b60` 已部署并 PASS；R3 显式 DeepSeek/off Intake `missing=[]`、审批 HTTP 200 和 running task；各分端当前代码评审结论汇总。2026-10-31 内容评审为 4 PASS / 1 FAIL（目标认证主题/比较有效性失败），6f70303f 全量 exit 3，不构成通过。

剩余门禁：

1. 内容：DANE `research_gaps[6]` 的纵向结果表述须在未来新 report version 里与已报告证据对齐；2026-10-31 新案例的比较有效性与目标认证选集也必须修正。保留 v5/v6 及新案例旧 hash/产物，不改写历史版本。
2. 诊断修复：`paper_ids` 结构约束失败的具体 type/count/duplicate 子因不可得，三项 `report_context` 后端缺陷已指派但未完成；local 30s timeout→DeepSeek fallback 与陈旧 Run 模型投影需在后续证据中保持区分。
3. 检索与 Intake：冗余补篇数问题已修复但待复审；2026-10-31 选集偏题正在另一 agent 诊断，不能将当前五篇机器成功报告当作目标认证安全专题完成。
4. 浏览器：v21 已实测 v5 完成通知→`研究摘要与报告`→正文/指标稳定展示；2026-10-31 browser report 仅证明新案例正文/产物展示，不能解除其人工内容 FAIL或代替目标主题复核。
5. 回归：6f70303f 当前全量记录为 exit 3、3450 passed、3 skipped、82.15%、250.43s；退出码非零，不能签通过，也不能用历史 `3441/3/0` 快照覆盖当前结果。
6. E2E Artifact 完整性：v6 的 HTTP 202、执行 manifest、request/headers/submit 与 `failed/published=false/AGENT_OUTPUT_INVALID` 终态，以及 2026-10-31 新案例的 manifest/请求/报告/产物 hash 均已保存；后续修复版本必须再保存真实 completed/published 响应、report_id/WorkItem、运行时间与产物路径。
7. 人工案例：当前 v5 与 2026-10-31 新案例展示路径已补入实测按钮/通知/页面/正文证据；完整创建、审批、处理中提示、失败恢复、目标认证选集与修复后最终版本仍待验证，不能把占位替换成猜测文案。
8. R3 终态：R3 的显式 DeepSeek/off Intake 虽返回 `missing=[]`、审批 HTTP 200，task `3efcee5268f25980ae09d0d0fbe7a145` 仍为 `running`，尚无 completed/published report、内容评审、产物 hash 或浏览器复核；不得把 R3 启动写成成功。

只在上述阻塞解除、人工 rubric 全 PASS、最新全量与浏览器/API E2E 证据通过且 readiness 至少 9/10 后，才可继续正式验收签字与 Spec 收尾。本报告未签 Spec 完成。
