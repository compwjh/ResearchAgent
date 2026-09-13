# Spec034 Task08 后端评审

评审角色：backend-reviewer（只读代码评审）  
评审范围：Task08 当前工作树、Task08 交付报告、Task08 计划、Spec034 Artifact/最终消息/通知/引用边界、`research-report-synthesis` Skill，以及 Task02–07/Spec027/conversations 相关后端接缝。  
评审结论：**NO-GO**（存在多个 P1，不能进入 Task08 收口）。

## 通过项

- Markdown→HTML 使用固定、可复现的转义渲染器；不解释原始 HTML、Markdown link/image，且固定 CSP/`nosniff`/`no-store` 响应头接缝存在：`backend/app/research/application/report_synthesis.py:135-177`、`backend/app/api/routes_research.py:413-437`。
- Artifact 下载通过 `artifact_id` 查询并经 owner→task join 与 session→task 双重边界校验，不解引用 `storage_ref`：`backend/app/api/routes_research.py:413-425`、`backend/app/research/infrastructure/research_store.py:2499-2529`。
- Artifact 表使用 `(research_task_id, report_version, artifact_type)` 唯一约束，创建时校验内嵌内容哈希；通知使用 owner+幂等键、owner event_seq、read 状态约束及 owner 条件 CAS：`backend/app/research/infrastructure/research_store.py:665-695`、`2435-2478`、`2531-2646`。
- 最终助手消息复用既有 `MemoryRepository.create_activity_message`，键为 `research-report:{task}:{version}`，未新建第二套会话消息流；通知与 Artifact 也使用既有 ResearchStore 独立表：`backend/app/research/application/report_synthesis.py:289-412`。
- 两条编排路径均可到达 Task08 delivery seam，deterministic path 与 AgentWorkItem path 都使用同一 Artifact/消息/通知服务；取消/终态刷新接缝仍保留：`backend/app/research/application/orchestrator.py:257-265`、`388-451`、`474-612`。

## 阻断问题（P1）

### P1-1：Synthesizer 的验证标记使用 truthiness，`verified="false"` 会被接受

`ReportSynthesizer.synthesize()` 对 `verified`/`validated`/`evidence_validated` 只做 `if not marker` 判断，字符串 `"false"`、非空数字等非布尔值会被当成已验证候选。评审已用最小行为探针复现：`{"candidate_id":"c1","verified":"false"}` 成功生成报告。该路径违背“只接收已验证证据”，可让未验证候选进入报告。

证据：`backend/app/research/application/report_synthesis.py:211-219`。

### P1-2：Synthesizer 输入的 title/section 未经过安全边界校验，Prompt/URL/路径等可进入 Markdown

安全递归校验只在 `validate_report_synthesis_output()` 对已生成 payload 执行；`synthesize()` 直接把 `title` 和 section `heading` 转入 Markdown。调用方可以传入含 URL、文件路径、Prompt/凭据字样的 heading/title，随后生成可见报告内容。固定 HTML renderer 会转义 HTML，但不能满足 Skill 明确要求的“拒绝任意 URL 或文件路径、不得展示 Prompt/凭据”。

证据：输入读取与拼接在 `backend/app/research/application/report_synthesis.py:249-286`；输出校验仅在 `:120-132`。

### P1-3：AgentWorkItem 路径没有消费/校验真实 Synthesizer 输出

Agent Runner 完成 `synthesizer` WorkItem 后仅记录 `synthesis_run_id`，其 `result.output_json` 从未传给 `ReportSynthesizer` 或 `ReportDeliveryService`；随后代码重新从 evaluator 输出拼装 `selected/citations` 并调用 deterministic `ReportSynthesizer`。因此模型 Synthesizer 即使输出错误、越界或与验证证据不一致，只要 Run 标记 completed，就会被忽略并可能产生另一份报告，不符合“真实 Synthesizer 基于验证证据生成”的接线要求。

此外，evaluator 的 `kept` 与 `evidence_refs` 在此处直接信任；Runner 的通用 `_validate_output` 只检查少量必填字段，并未对 `kept`/引用做 Task08 语义校验。

证据：`backend/app/research/application/orchestrator.py:545-552`、`:568-598`；通用校验：`backend/app/research/application/agent_runtime.py:855-874`。

### P1-4：AgentWorkItem 路径在无入选证据时仍可能收敛为 completed

当 evaluator 无 `kept` 候选、所有 WorkItem 均成功且 deterministic synthesizer 生成空报告时，`failures == 0`，最终状态被设为 `completed`；返回值的 `selected_count` 仍为 0。Spec034/Task08 要求证据不足或空结果必须是 partial/有真实诊断，不能把空报告作为成功完成。

证据：空报告允许注释及调用在 `backend/app/research/application/orchestrator.py:582-598`；最终状态只按 item/failures 判断在 `:606-612`。

### P1-5：Artifact 插入竞态的异常回读没有再次校验 hash，可接受冲突版本

`ReportDeliveryService.deliver()` 插入 Artifact 发生任意异常后回读同版本同类型 Artifact；只要回读到一行就直接复用，没有比较回读 Artifact 的 `content_hash` 与本次内容哈希。因此并发重试写入不同内容时，可能错误地接受另一版本内容而不抛 `ARTIFACT_IMMUTABLE_CONFLICT`，违反不可变 Artifact 合同。

证据：`backend/app/research/application/report_synthesis.py:339-365`。正常已有行的 hash 校验在 `:341-343`，但仅覆盖异常前读到的行，未覆盖竞态回读。

### P1-6：通知 SSE 只回放一次后结束，无法可靠送达连接期间新通知

`_notification_event_stream()` 仅调用一次 `list_notifications()`，遍历当前最多 500 条后 generator 结束；没有轮询、heartbeat、终态策略或后续 cursor 推进。建立 SSE 后产生的 completed/partial/failed/waiting_approval/interrupted 通知不会推给仍在线客户端，不能满足应用内通知 SSE 的可靠送达与断线补发语义。

证据：`backend/app/api/routes_research.py:459-477`。对比任务事件 SSE 的持续轮询/heartbeat：`:703-755`。

### P1-7：五类通知没有完整接线，synthesis 失败只发 failed，任务随后变 partial 却不发 partial

Task08 Skill 要求完成、partial、失败、重试和需要用户操作等通知。当前新服务的实际调用只有 delivery 的 completed/partial 和 synthesis failure 的 failed；没有 waiting_approval/interrupted 的 Task08 发送点。尤其 deterministic 与 AgentWorkItem 路径在 synthesis 失败后都只调用 `_emit_synthesis_failure_notification()`，随后任务状态收敛为 partial，但没有对应 partial 通知；重试事实也没有独立通知。

证据：调用点 `backend/app/research/application/orchestrator.py:430-451`、`:597-612`、`:1255-1269`；服务仅声明类型集合在 `backend/app/research/application/report_synthesis.py:415-437`。Skill 要求见 `.agents/skills/research-report-synthesis/SKILL.md:16-27`。

## 非阻断问题（P2）

- 通知 SSE/list 按 cursor 回放所有通知，不过滤已读；Task08 计划写明断线补发未读。若产品语义确实是“事件历史重放”可保留，否则应在查询/游标策略中明确 unread 行为：`backend/app/research/infrastructure/research_store.py:2648-2654`、`backend/app/api/routes_research.py:474-477`。
- `ResearchStore.create_artifact()` 的 `owner_id` 仍是可选参数，且未校验 `report_version >= 1`；直接使用存储 seam 时可绕过 owner 写入检查或写入 0 版本。API 读取边界目前正确，但建议将 owner/版本约束收紧到存储层：`backend/app/research/infrastructure/research_store.py:2435-2455`。
- API 将 `intermediate` 也作为可下载内容（fallback `application/octet-stream`/`.txt`），若该类型含内部交接物，可能越过“报告公开 Artifact”边界；建议仅开放 markdown/html/citation_manifest：`backend/app/research/infrastructure/research_store.py:2435-2439`、`backend/app/api/routes_research.py:426-432`。

## 验证记录

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task07_backend.py tests/test_conversations_api.py tests/test_spec027_backend_research_slice.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task06_contract.py` | 0；169 passed，5 subtests passed |
| `.venv/bin/python -m py_compile`（Task08 改动后端文件及测试） | 0；通过 |
| `.venv/bin/ruff check`（`E9,F63,F7,F82,I001`） | 0；All checks passed |
| `git diff --check` | 0；通过 |
| 行为探针：`verified="false"` | **错误接受**，对应 P1-1 |

## 评审决策

**NO-GO。** 现有定向测试覆盖了基本 XSS、owner 隔离、幂等和 CAS，但未覆盖上述负向边界、竞态、持续 SSE 和 AgentWorkItem 真实输出消费。修复全部 P1 后应补充针对性回归，再重新执行本评审；在此之前不得将 Task08/Spec034 标记为已完成。

## 复审（2026-09-13，P1 修复后）

复审结论：**NO-GO**。上一轮的 7 个 P1 均已看到对应修复，且定向回归为 `180 passed，5 subtests passed`；但真实 AgentWorkItem 数据流仍断在 Synthesizer 入参之前，并新增发现两项会破坏证据/审计边界的 P1。

### 已修复并验证

- 严格布尔验证已改为字面量 `is True`，title/heading 统一经过 URL、路径、Prompt/凭据和长度边界：`backend/app/research/application/report_synthesis.py:188-202`、`:230-239`、`:273-285`、`:325-338`。
- AgentWorkItem 现在确实读取 `result.output_json`，校验 Synthesizer schema/version/hash，并经 evaluator evidence allowlist 后交给 `consume_validated_output` 和统一 Delivery：`backend/app/research/application/orchestrator.py:562-630`；空 evaluator/空 evidence 收敛到 `NO_VALIDATED_EVIDENCE`、partial，并发送失败/partial 事实：`:638-665`、`:1310-1348`。
- Artifact 竞态回读再次比较内容哈希；下载只开放三类最终报告 Artifact，不解引用 `storage_ref`，响应头含固定类型、CSP、nosniff、no-store：`backend/app/research/application/report_synthesis.py:429-463`、`backend/app/api/routes_research.py:413-439`。
- 通知 SSE 已按 owner cursor 有界轮询并发送 heartbeat；waiting_approval、interrupted（含启动恢复）、completed/partial、failed 及失败重试独立幂等键均有调用点：`backend/app/api/routes_research.py:461-498`、`backend/app/research/application/research_service.py:402-423`、`:443-481`、`:517-525`、`backend/app/research/application/orchestrator.py:148-162`、`:1310-1348`。

### 仍然阻断（P1）

#### P1-R1：真实 AgentWorkItem 的上游证据没有注入 Synthesizer（也没有按依赖执行）

生产 Agent 路径从库中逐项读取原始 `input_json` 并立即调用 Runner；没有读取 `depends_on_json`、没有等待上游状态，也没有把 Search Worker/Evaluator 的输出回填到下游输入。Planner 给 Evaluator 的 `catalog_paper_ids` 和 Synthesizer 的 `selected_paper_ids` 固定为空，Synthesizer 入参也不含 evaluator evidence/citation allowlist：`backend/app/research/application/planner.py:173-206`、`backend/app/research/application/orchestrator.py:522-552`。虽然输出在 `:612-627` 被事后校验，但这不能使模型调用本身“只收到验证证据”；在真实 Agent 路径上，模型无法可靠生成与 evaluator 证据相符的 sections/manifest，通常只能被后置校验成 partial。该问题直接违反 Spec034 的 Synthesizer 最小上下文及 DAG 接线（Spec034:249），也是“两条路径真实接线”未完成的阻断项。

#### P1-R2：Synthesizer 重试成功后的 Artifact 生成 Run 归因错误

`ResearchAgentRunner` 在输出无效时创建新的 `...:attempt-N` Run：`backend/app/research/application/agent_runtime.py:687-749`；成功返回的 `AgentRunOutput` 没有携带最终 Run ID（`:210-228`、`:1164-1169`）。Orchestrator 却始终把第一次计算的 `work_item_id:run-N` 作为 `synthesis_run_id` 并传给 Delivery：`backend/app/research/application/orchestrator.py:531`、`:564-570`、`:622-626`。Store 只验证该 ID 是同任务 `role='synthesizer'`，所以会接受“由 attempt-2 输出生成、却标记为 attempt-1（已 limit_reached）生成”的 Artifact：`backend/app/research/infrastructure/research_store.py:2463-2467`。这破坏 `generated_by_agent_run_id` 的审计/可追溯合同；需要返回并使用最终成功 Run ID，或在 Delivery 前重新解析 continuation 链。

#### P1-R3：`source_refs` 可脱离 evaluator allowlist 被模型杜撰

`consume_validated_output()` 只把 `citation_manifest` 的每条 `(candidate_id, citation_ref)` 与 evaluator evidence 比较，未检查模型输出的 `source_refs`；清洗后的输出又原样保留该字段：`backend/app/research/application/report_synthesis.py:339-349`、`:376-380`。最小行为探针已复现：manifest 仅为 `catalog:c1`、evaluator 仅允许 `catalog:c1` 时，`source_refs=['catalog:c2']` 仍成功消费。虽然当前 Markdown 不直接渲染 `source_refs`，它仍是持久化/返回的 Synthesizer 输出元数据，违背“所有来源/引用只来自验证 allowlist”；应要求其集合等于 manifest/evaluator allowlist 的子集（最好与 manifest 精确一致）。

### 非阻断（P2）

- `ResearchStore.create_artifact(..., owner_id=None)` 仍允许兼容调用绕过写入 owner 校验，且 `ReportDeliveryService.deliver()` 没有独立断言 `result.output.report_version == task.current_plan_version`；当前 API 与正式 Delivery 调用点已传 owner，建议下一轮收紧存储/服务边界：`backend/app/research/infrastructure/research_store.py:2444-2467`、`backend/app/research/application/report_synthesis.py:413-421`。
- Artifact 下载目前没有显式大小上限/`Content-Length`，而 Spec034 接口表提到“大小上限”；建议增加固定上限后返回稳定 `ARTIFACT_NOT_READY`/拒绝码。SSE 采用文档明确的有界轮询（默认 20、最大 120 polls），客户端需用最后 cursor 重连：`backend/app/api/routes_research.py:461-498`。
- 通知 replay 当前按 cursor 返回 owner 的历史（含已读），不是只返回 unread；若产品继续要求“断线补发未读”，需在接口契约中明确事件历史语义或增加过滤：`backend/app/research/infrastructure/research_store.py:2648-2654`。

### 复审验证记录

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task07_backend.py tests/test_conversations_api.py tests/test_spec027_backend_research_slice.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task06_contract.py` | 0；`180 passed，5 subtests passed` |
| `.venv/bin/python -m py_compile`（Task08 改动后端文件及测试） | 0；通过 |
| `.venv/bin/ruff check [Task08 改动文件] --select E9,F63,F7,F82,I001` | 0；All checks passed |
| `git diff --check` | 0；通过 |
| 行为探针：`consume_validated_output(source_refs=['catalog:c2'])` | **错误接受**；对应 P1-R3 |

### 复审决策

**NO-GO。** P1-R1 使生产 Agent 路径没有收到验证证据，P1-R2 使重试 Artifact 的生成 Run 归因错误，P1-R3 允许输出元数据携带未授权来源。修复三项并补充真实 AgentWorkItem（含 retry、空 evidence、上游注入）行为测试后，方可重新评审并考虑 GO。

## 最终复审（2026-09-13，R1–R3 修复后）

最终结论：**NO-GO**。R1–R3 的目标修复均已落地，上一轮 P1 的严格 bool、安全 title/heading、空证据 partial、Artifact 竞态 hash、SSE 轮询、五类通知接线也保持通过；但 evaluator 证据仍缺少对真实搜索候选的语义绑定，且 Synthesizer 入参候选来源过宽。

### R1–R3 验证通过

- WorkItem 现在先做拓扑排序，再以 `completed_ids/failed_ids` 做依赖屏障；搜索输出候选被注入 Evaluator，Evaluator 产出的验证候选与 citation allowlist 被注入 Synthesizer，失败依赖会落 `UPSTREAM_WORK_ITEM_FAILED/NOT_READY`：`backend/app/research/application/orchestrator.py:550-623`。
- 空 evaluator/空 evidence 在 Synthesizer 调用前即失败并收敛 partial：`backend/app/research/application/orchestrator.py:606-617`、`:740-767`。
- Runner 在 continuation 成功返回最终 `agent_run_id`，Orchestrator 将该 ID 传入 Delivery，Artifact 生成 Run 归因不再固定初始 Run：`backend/app/research/application/agent_runtime.py:210-234`、`:733-752`、`:1166-1171`、`backend/app/research/application/orchestrator.py:657-672`、`:724-729`。
- `source_refs` 必须与已验证 citation manifest 精确相等；越界 source ref 已有负向测试：`backend/app/research/application/report_synthesis.py:339-354`、`tests/test_spec034_task08_backend.py:83-89`。

### 仍然阻断（P1）

#### P1-F1：Evaluator 证据未绑定上游搜索候选，模型可伪造 candidate/ref

Evaluator 的 `catalog_paper_ids` 虽来自上游 Search Worker：`backend/app/research/application/orchestrator.py:598-605`，但其完成输出随后只按字面量 `keep/verified`、非空 `candidate_id` 和非空 `evidence_refs` 接受：`backend/app/research/application/orchestrator.py:77-89`。没有检查 candidate 是否属于对应 Search Worker 的候选集合，也没有检查 citation 是否为该候选的真实来源（例如 `catalog:{candidate_id}` 或既有目录证据）。因此恶意/错误的 Evaluator 可以输出 `keep=True, candidate_id=unknown, evidence_refs=["catalog:unknown"]`，这些数据会被写入 Synthesizer 的 `validated_candidates`/`citation_allowlist`（`:606-623`），并在 `consume_validated_output()` 中被视为合法 evaluator allowlist。应在 Orchestrator 中保存直接上游搜索 candidate allowlist，并拒绝 evaluator 越界候选/引用；否则“只基于验证证据”仍没有真实证据根。

#### P1-F2：Synthesizer 入参筛选包含所有 completed output，而非仅 evaluator output

注入 Synthesizer 时使用 `completed_outputs.values()` 并以 `kept`/`candidate_id` 作为启发式筛选：`backend/app/research/application/orchestrator.py:606-609`。`ResearchAgentRunner._validate_output()` 对各角色只做通用必填字段检查，未禁止额外字段：`backend/app/research/application/agent_runtime.py:855-874`。因此 Critic 或其他上游模型可附加 `kept`/`candidate_id` 字段，进入 Synthesizer 上下文，即使最终 Delivery 的后置列表只记录 evaluator 输出。这违反 Synthesizer 最小上下文“只收验证证据、引用”，应改为仅从已识别的 `paper_evaluator` WorkItem 输出构建注入，并对角色 schema/额外字段做收窄。

### 非阻断（P2，仍存在）

- `ResearchStore.create_artifact(..., owner_id=None)` 仍保留兼容绕过写入 owner 校验；`ReportDeliveryService.deliver()` 仍未独立断言结果版本等于当前 Task 版本：`backend/app/research/infrastructure/research_store.py:2444-2467`、`backend/app/research/application/report_synthesis.py:416-424`。
- 下载没有显式大小上限/`Content-Length`；通知 replay 按 owner cursor 返回历史（含已读），与“未读补发”措辞仍需契约澄清：`backend/app/api/routes_research.py:413-439`、`:445-498`、`backend/app/research/infrastructure/research_store.py:2648-2654`。

### 最终复审验证记录

| 检查 | 结果 |
|---|---|
| Task08 + Task02–07 + Spec027 + conversations 定向 pytest | 0；`180 passed，5 subtests passed` |
| Task08 相关后端与测试 `py_compile` | 0；通过 |
| 聚焦 Ruff（`E9,F63,F7,F82,I001`） | 0；All checks passed |
| `git diff --check` | 0；通过 |
| `consume_validated_output(source_refs != manifest)` 负向探针 | 拒绝；R3 已修复 |

### 最终评审决策

**NO-GO。** R1–R3 已通过，但 P1-F1 允许 evaluator 伪造根证据，P1-F2 允许非 evaluator 输出进入 Synthesizer 上下文。修复两项并补充“越界 candidate/ref、Critic 额外字段、真实 retry continuation”的行为测试后，才能进入 Task08 收口。

## 最终复审（2026-09-13，证据链修复后）

最终结论：**NO-GO**。本轮已确认 candidate/ref 的 Search Worker allowlist 校验，以及 Synthesizer 仅消费祖先链上已完成 Evaluator 的改动；定向回归和静态检查全部通过。但“source 必须来自同 Task Search Worker allowlist”仍未实现，故不能给 GO。

### 本轮通过项

- 当前 WorkItem 先拓扑排序，再以依赖完成/失败集合决定是否执行；Synthesizer 通过 `ancestors()` 找到祖先链上的 `paper-evaluator` WorkItem，仅从 `evaluator_outputs_by_id` 注入验证候选与 citation allowlist，Critic/其他输出不再进入：`backend/app/research/application/orchestrator.py:592-640`、`:662-700`。
- Evaluator 的 candidate 与 evidence/citation ref 已按直接 Search Worker 上游建立 allowlist，并在 Run 完成后越界即转 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`：`backend/app/research/application/orchestrator.py:640-661`、`:736-753`。最小探针确认越界 candidate/ref 返回 `False`。
- 空证据仍在 Synthesizer Run 前阻断，retry 成功使用最终 `agent_run_id`，`source_refs` 与最终 citation manifest 精确相等；上一轮 strict bool、安全 title/heading、Artifact 竞态、通知 SSE/五类通知接线均未回归：`backend/app/research/application/orchestrator.py:684-700`、`backend/app/research/application/agent_runtime.py:1166-1171`、`backend/app/research/application/report_synthesis.py:339-354`。

### 仍然阻断（P1）

#### P1-F3：Evaluator 的 `source`/`source_refs` 未绑定 Search Worker allowlist

`_validate_evaluator_scope()` 只检查 candidate、`evidence_refs`、嵌套/顶层 `citation_manifest`，没有检查 evaluator 输出的 `source` 或 `source_refs`：`backend/app/research/application/orchestrator.py:98-129`。Search Worker 的合法来源/来源引用实际在输出中分别是 `source` 与 `source_refs`：`backend/app/research/application/search_catalog_adapter.py:444-449`；但 Orchestrator 建立的 `allowed_refs` 只从 `catalog:{paper_id}`、上游 `evidence_refs`/`citation_allowlist` 派生，未建立并校验 `allowed_sources`/上游 `source_refs`：`backend/app/research/application/orchestrator.py:640-661`。因此最小探针 `source="attacker", source_refs=["search:attacker"]` 搭配合法 candidate/ref 仍返回 `True`，而通用 Runner 只校验 source_refs 是稳定 ID：`backend/app/research/application/agent_runtime.py:857-875`。这违反用户要求的“candidate/ref/source 必须来自同 Task Search Worker allowlist”，应对来源字段做同一祖先 Search Worker 绑定，越界时拒绝整条 Evaluator 输出。

### P2

- owner 可选写 Artifact、Delivery 未独立校验当前 Task report version、下载缺显式大小上限/Content-Length、通知 replay 含已读的边界保持上一轮记录：`backend/app/research/infrastructure/research_store.py:2444-2467`、`backend/app/research/application/report_synthesis.py:416-424`、`backend/app/api/routes_research.py:413-498`。

### 本轮验证记录

| 检查 | 结果 |
|---|---|
| Task08 + Task02–07 + Spec027 + conversations 定向 pytest | 0；`180 passed，5 subtests passed` |
| Task08 相关后端与测试 `py_compile` | 0；通过 |
| 聚焦 Ruff（`E9,F63,F7,F82,I001`） | 0；All checks passed |
| `git diff --check` | 0；通过 |
| `_validate_evaluator_scope(candidate/ref 越界)` | 拒绝；通过 |
| `_validate_evaluator_scope(source="attacker", source_refs=["search:attacker"])` | **错误接受**；对应 P1-F3 |

### 最终评审决策

**NO-GO。** Candidate/ref 与 Synthesizer 祖先链隔离已经通过；只需补齐 Search Worker `source/source_refs` allowlist 绑定并新增对应负向测试，方可重新评审。

## 终审（2026-09-13，来源 allowlist 修复后）

### 结论：GO（附 P2）

本轮确认 P1-F3 已修复，且上一轮 P1 不回归。Evaluator 的 `candidate_id`、`evidence_refs`、`source`、`source_refs` 现在均在同一条直接 Search Worker 依赖链建立的 allowlist 内校验；越界结果被标为 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`，不会进入 Synthesizer 或 Delivery。

### 证据核对

- Search Worker 输出绑定当前 WorkItem，并只产生自身候选 ID、来源和 `search:{work_item_id}` 来源引用：`backend/app/research/application/search_catalog_adapter.py:444-451`。
- Orchestrator 对直接上游 Search Worker 建立候选、`catalog:{candidate}` evidence/citation、`source` 与 `source_refs` 四类 allowlist，同时校验上游 `work_item_id`/`research_task_id`：`backend/app/research/application/orchestrator.py:680-720`。Evaluator 输出的顶层和每条记录都会校验 candidate、evidence、source、source_refs 及 citation manifest：`:98-169`；失败转为稳定错误 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`：`:793-814`。
- Synthesizer 只从祖先拓扑中角色为 `paper-evaluator` 且已完成并通过校验的输出构建输入，Critic/其他角色输出不进入；没有验证证据时在模型调用前以 `NO_VALIDATED_EVIDENCE` 失败收敛：`backend/app/research/application/orchestrator.py:721-759`。
- 直接行为探针结果：合法 `usenix` + `search:s1` + `c1/catalog:c1` 为 `True`；`source=attacker`、`source_refs=search:attacker`、`c2/catalog:c2` 均为 `False`。对应回归测试覆盖同一组正负样例：`tests/test_spec034_task08_backend.py:48-70`。

### 上一轮 P1 回归核对

- 严格 bool、title/heading 安全边界仍由 `report_synthesis.py` 的字面量布尔和安全文本校验保护；`source_refs` 必须与已验证 citation manifest 精确相等：`backend/app/research/application/report_synthesis.py:330-354`，负向测试：`tests/test_spec034_task08_backend.py:87-114`。
- Artifact 竞态回读并比较内容 hash，未引入第二套存储；成功 Synthesizer 使用最终 continuation 的 `agent_run_id`：`backend/app/research/application/report_synthesis.py:431-465`、`backend/app/research/application/agent_runtime.py:733-752,1166-1171`、`backend/app/research/application/orchestrator.py:815-821`。
- 依赖失败、空证据、partial/failure 收敛，以及等待审批、interrupted、completed/partial、failed 和 retry 通知调用链保持既有实现；通知 SSE 仍为持续/有界 cursor 轮询，未新建第二条消息流。

### P2（不阻断本 Task）

- `ResearchStore.create_artifact(..., owner_id=None)` 仍保留兼容性可选参数，Delivery 未独立再次断言当前 Task 的 report version：`backend/app/research/infrastructure/research_store.py:2444-2467`、`backend/app/research/application/report_synthesis.py:416-424`。
- 下载仍未显式施加大小上限/`Content-Length`；通知 replay 按 owner cursor 返回历史（含已读），需后续明确“历史事件”还是“未读补发”语义：`backend/app/api/routes_research.py:413-498`、`backend/app/research/infrastructure/research_store.py:2648-2654`。

### 本轮验证

| 检查 | 结果 |
|---|---|
| Task08 + Task02–07 + Spec027 + conversations 定向 pytest | 0；`181 passed，5 subtests passed` |
| Task08 相关后端与测试 `py_compile` | 0；通过 |
| 聚焦 Ruff（`E9,F63,F7,F82,I001`） | 0；All checks passed |
| `git diff --check` | 0；通过 |
| `_validate_evaluator_scope` 合法/attacker source/attacker ref/越界 candidate-ref 探针 | `True / False / False / False` |

### 最终评审决策

**GO（附 P2）。** 来源 allowlist、Evaluator 证据根、Synthesizer 祖先 Evaluator 隔离及上一轮 P1 均已通过验证；允许 Task08 后端进入收口。P2 项保留为后续边界硬化，不阻断本 Task。
