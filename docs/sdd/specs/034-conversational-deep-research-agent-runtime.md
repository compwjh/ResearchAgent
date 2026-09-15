# Spec 034 — 会话式深度研究与真实子 Agent Runtime

## 状态

**当前状态：实施中（Task11 报告内容与召回补强）**

> 本 Spec 来自 2026-09-13 多轮 Grilling 的共同裁决。确认前只允许完善规范、任务计划和评审材料，不修改业务代码。
> 2026-09-13：需求评审第二轮 APPROVE、技术评审第二轮 GO；用户此前明确要求“然后再开发034”，视为确认本 Spec，按 Task02 → Task10 顺序实施。
> 2026-09-15：Task10 完成最终全量回归、真实 Ollama/USENIX 目录 Smoke、Artifact 生成、部署探针和复盘；Spec 收口为已完成。

## 一句话目标

让用户在普通会话中自然表达“帮我做一个关于软件供应链攻击的深度研究”，由会话 Agent 真实激活 Deep Research Skill，通过多轮对话补齐参数、生成并等待用户批准计划，再由受控 Orchestrator 调用具备独立模型上下文、Skill 和 Tool 的真实子 Agent 执行 Spec027 已有研究流程；全过程以可恢复的三级处理树展示，最终把可读 Markdown/HTML 报告写回原会话。

## 背景、依赖与优先级

- Spec027 已提供 ResearchTask、ResearchPlan、WorkItem、ResearchEvent、论文选集、初步报告、受控 DAG、预算、ResourceProbe、SSE 和研究工作台，但当前 Planner、Evaluator、Critic、Synthesizer 主要是确定性 Python，搜索 Worker 也是线程池函数；模型路由事件并不等于真实模型执行。
- Spec027 还把入口限定为“从已有会话显式选择深度研究模式”，并允许默认 Planner 生成“总体综述”等兜底 facet。前者不符合本 Spec 的会话式意图，后者会把通用研究方式误当成研究子方向。
- Spec023 已有 Skill Registry、Tool Registry、Ollama function calling 和 ToolExecutor；Spec032.1 已有 `usenix-catalog-orchestration` 等来源 Skill。本 Spec 必须复用这些接缝，不能再造第二套 Skill/Tool 管理。
- Spec015/032.1/033 提供 USENIX/DBLP 目录、增量缓存、详情补抓和 RAG。默认研究路径必须真正接入该目录，不得因未配置临时数据源而静默返回空结果。
- Spec028 的自动租约接管和模型调用中途恢复、Spec030 的完整 Claim/Evidence 矩阵仍为后续能力；本 Spec 只实现可验证检查点后的人工重试和基础引用 manifest。
- 冲突时本 Spec 仅覆盖 Spec027 的以下边界：入口改为普通会话可触发；ResearchTask 在计划批准后才创建或激活；Planner 的能力输出改为 Registry 映射并允许当前计划版本内的显式授权覆盖；产品 Runtime 增加真实子 Agent。Spec027 其余状态机、论文目录复用、资源探针、owner 隔离和“论文内容不可信”规则继续有效。

## 产品行为与完整流程

1. 用户在普通会话输入明确的深度研究请求；会话 Agent 先读取启用 Skill 的名称与简介，判断后调用结构化 `activate_skill`，验证通过才加载 Deep Research Skill 全文。
2. Deep Research Skill 指示 Agent 调用 `begin_research_intake`，创建持久化 ResearchSession 和 ResearchIntakeDraft。关键词只能帮助提供候选，不能直接静默创建任务。
3. Agent 自适应询问缺失参数。阻塞参数为主题、研究目标、时间范围；语言默认中文，来源、深度、引用和输出格式使用可见默认值。每个字段记录用户明确、上下文推断或系统默认的来源和确认状态。
4. 参数完整后，Planner Agent 使用固定 Skill 快照生成结构化计划。计划卡展示目标、范围与排除、真实研究方向、来源/查询策略、预计子 Agent、预算、报告结构和降级策略。
5. 用户必须批准最新 `plan_version`。自然语言和按钮都转换为同一条后端命令；任何结构性修改生成新版本并使旧批准失效。
6. 批准后创建或激活 ResearchTask，并立即在原会话插入一条专用“研究执行”助手消息。确定性 Orchestrator 负责 DAG、状态机、预算和校验，只能由它创建 AgentRun；子 Agent 不得递归创建子 Agent。
7. 会话层 Coordinator 只负责 Intake、命令和交付编排，不是 ResearchAgentRunner 的子 Run；Orchestrator 按角色调用真实子 Agent：Planner、Search Worker、Paper Evaluator、Research Critic、Synthesizer。每个 AgentRun 有独立模型请求循环、最小上下文、Skill 快照、Tool 白名单、结构化输入输出和真实模型元数据。
8. 默认先检索本地论文目录；覆盖不足时通过现有 USENIX/DBLP 编排 Skill 和目录 Tool 增量刷新。搜索使用宽召回、可解释评估和有界阈值软化，零结果必须区分空目录、来源失败、查询不匹配与阈值过高。
9. ResearchEvent 记录研究执行事实，并幂等投影到专用助手消息的 `processing_steps`。前端展示“阶段 → 子 Agent/WorkItem → Skill/Tool”的三级树。
10. 运行完成后，Synthesizer 依据已验证证据生成 Markdown 主 Artifact、引用 manifest 和派生 HTML；系统以幂等方式插入最终助手消息，并提供 Markdown 下载和 HTML 阅读入口。
11. 深度研究 Tab 保留表单和任务卡，作为创建、监控和调试中心；表单走同一 Session/Intake/Plan/Approval 状态机，并自动创建、绑定和打开会话。删除所有普通会话旁的独立“研究”按钮。

## 角色与 Skill/Tool 编排

### 产品 Runtime 角色

- **Coordinator（会话层控制器）**：激活 `deep-research-orchestration`；管理 Intake、计划命令、检查点和最终会话交付。它不创建 `AgentRun`、不调用 `ResearchAgentRunner`，也不递归创建子 Agent；所有研究执行 Run 只能由确定性 Orchestrator 创建。
- **Planner Agent**：激活 `research-plan-authoring`；输出 ResearchPlanOutput，不直接执行搜索。
- **Search Worker Agent**：激活来源 Skill，如 `usenix-catalog-orchestration`；调用现有 `search_paper_catalog`、`fetch_paper_detail` 等注册 Tool。
- **Paper Evaluator Agent**：激活 `research-paper-evaluation`；批量评价候选，保留淘汰理由，不执行下载。
- **Research Critic Agent**：激活 `research-coverage-review`；识别覆盖缺口并提出同范围补搜建议。
- **Synthesizer Agent**：激活 `research-report-synthesis`；只基于已验证证据和引用清单生成报告。

需要新增五个通用 Research Skill：`deep-research-orchestration`、`research-plan-authoring`、`research-paper-evaluation`、`research-coverage-review`、`research-report-synthesis`。来源搜索优先复用已有 Skill，不复制来源协议。

### Planner 能力输出与授权

- 默认 Planner 只输出 `{role, capability, source, research_question}`；后端 Role/Capability Registry 映射到固定 Skill/version、Tool、模型档位、Schema 和预算。
- 用户未授权时，未知 `skill_name`/`tool_name` 必须被拒绝，不能越过默认映射。
- 用户可在当前 `plan_version` 内授权 Planner 指定 Registry 中实际存在且已启用的 Skill/Tool；“允许所有”表示批准时可执行 Tool 及版本的快照，未来新增 Tool 不自动获得权限。
- 当前版本允许在计划卡中一次性批准下载、导入等已明确展示目标、数量和副作用的 Tool，不要求第二次确认；Re-plan 新增副作用必须重新批准。
- 本 Spec 不实现、不注册、不批准通用 Shell、Python 或任意公网 URL Tool；若未来确实需要，必须另行修订并重新确认 Spec，写清用途、参数、读写范围、副作用、沙箱、SSRF、凭据和预算边界。
- 当前仅允许 Spec023 已注册且已启用的论文目录、详情、下载/导入 Tool；下载或导入也必须是计划中明确展示的既有 Tool 目标，不能由 Planner 临时生成执行器。
- 最低隔离不可取消：不修改项目源码、Git、用户目录或系统目录；论文/网页内容不能改变角色、Skill、Tool、预算或系统指令。

## 数据模型

### ResearchSession（研究库）

| 字段 | 类型 | 约束 |
|---|---|---|
| research_session_id | UUID | 主键 |
| owner_id | str | 必填，沿用现有 owner 隔离 |
| conversation_id | UUID | 必填，跨库外部引用，读取时校验归属 |
| trigger_message_id | UUID | 发起研究的用户消息 |
| plan_message_id | UUID/null | 最新计划卡助手消息 |
| activity_message_id | UUID/null | 专用研究执行助手消息 |
| final_message_id | UUID/null | 最新报告助手消息 |
| intake_draft_id | UUID | 必填 |
| research_task_id | UUID/null | 计划批准前可空 |
| current_plan_version | int | 从 0 开始，计划生成后至少为 1 |
| status | enum | intake_pending / plan_generating / plan_pending_approval / queued / running / waiting_approval / interrupted / partial / completed / failed / cancelled |
| unread_state_json | JSON | 只存会话级摘要；通知明细独立保存 |
| created_at / updated_at | UTC datetime | 必填 |

ResearchSession 是 Intake 与 ResearchTask 的统一产品投影，不复制其详细数据；状态由 Draft、Approval 和 Task 的真实状态推导，前端不能直接设置。每个 `(owner_id, conversation_id)` 同时最多一个非终态 Session；创建由事务内 CAS/唯一活跃占位保证，冲突统一返回 `RESEARCH_SESSION_ACTIVE_CONFLICT`。

### ResearchIntakeDraft / IntakeField

| 字段 | 类型 | 约束 |
|---|---|---|
| intake_draft_id | UUID | 主键 |
| research_session_id | UUID | 一对一 |
| status | enum | collecting / complete / superseded / cancelled |
| field_name | enum | topic / objective / time_range / language / sources / depth / output / citations / constraints |
| value_json | JSON | 按字段 Schema 校验 |
| source | enum | user_explicit / context_inferred / system_default |
| confidence | number | 0–1 |
| confirmation_status | enum | unconfirmed / confirmed / not_required |
| updated_by_message_id | UUID/null | 可追溯 |
| updated_at | UTC datetime | 必填 |

topic、objective、time_range 缺失时不得生成计划。低置信度或显著改变范围的推断必须询问；安全默认值可以标记 `not_required`，但计划卡必须展示。

### ApprovalRequest（研究库）

| 字段 | 类型 | 约束 |
|---|---|---|
| approval_request_id | UUID | 主键 |
| owner_id | str | 必填，沿用 OWNER_ID 隔离；与 Session owner 一致 |
| research_session_id | UUID | 必填 |
| kind | enum | plan / capability_override / resource_extension |
| subject_id / subject_version | str/int | 绑定精确对象与版本 |
| requested_scope_json | JSON | 请求权限、预算或计划摘要 |
| approved_scope_json | JSON/null | 可小于请求范围 |
| status | enum | pending / approved / rejected / cancelled / superseded |
| idempotency_key | str | owner 内唯一 |
| decided_by_message_id | UUID/null | 自然语言审批时填写 |
| created_at / decided_at | UTC datetime | 必填/可空 |

授权仅对当前 plan_version 生效；同一 Re-plan 未扩大工具范围时可继承已有授权。多窗口或按钮/自然语言竞争时只有第一条有效决策成功。

### AgentRun 与结构化交接物（研究库）

| 字段 | 类型 | 约束 |
|---|---|---|
| agent_run_id | UUID | 主键 |
| research_session_id | UUID | 必填；用于计划批准前的 Planner Run 归属 |
| research_task_id / work_item_id | UUID/null | 计划批准前允许为空；批准后执行 Run 必须同时绑定已创建 Task/WorkItem |
| attempt | int | 从 1 开始 |
| continued_from_agent_run_id | UUID/null | 重试或扩容续跑链 |
| role | enum | planner / search_worker / paper_evaluator / research_critic / synthesizer；Coordinator 是会话层控制器，不是 AgentRun role |
| skill_name / skill_schema_version / skill_content_hash | str | 固定到批准计划的 Skill 快照 |
| resolved_model / reasoning_effort | str | 保存实际值，不写死产品模型名 |
| allowed_tools_json | JSON | 当前计划版本授权快照 |
| status | enum | queued / running / completed / failed / cancelled / interrupted / limit_reached |
| model_loop_count / tool_call_count | int | 单调递增 |
| input_hash / output_hash | str | 不保存隐藏思维链或完整 Prompt |
| checkpoint_ref / checkpoint_hash | str/null | 仅指向已持久化且通过 Schema/业务校验的检查点；哈希按规范化交接物计算 |
| error_code | str/null | 稳定错误码 |
| started_at / ended_at | UTC datetime | 可空 |

计划批准前的 Planner Run 只绑定 `research_session_id`，`research_task_id/work_item_id` 为空；批准命令成功后才创建 ResearchTask，所有 Search Worker/Evaluator/Critic/Synthesizer Run 必须绑定对应 Task 和 WorkItem。这样不会把会话层 Coordinator 偷换成 AgentRun，也不会出现无归属执行记录。

五类结构化输出的最低字段如下，均必须带 `schema_version`、`output_hash`、安全摘要和来源/证据 ID，不得包含 CoT 或隐藏 Prompt：

| Schema | 最低字段 |
|---|---|
| `ResearchPlanOutput` | `plan_version`、`objective`、`scope`、`work_items`、`capabilities`、`budget`、`report_structure` |
| `SearchWorkerOutput` | `work_item_id`、`queries`、`source`、`candidates`、`refresh_diagnostics` |
| `PaperEvaluationOutput` | `candidate_id`、`relevance_score`、`keep`、`reason`、`evidence_refs` |
| `CoverageReviewOutput` | `coverage`、`gaps`、`recommendations`、`bounded_replan` |
| `ReportSynthesisOutput` | `report_version`、`sections`、`citation_manifest`、`artifact_ids` |

交接物使用 WorkItem、EvidenceItem、CoverageGap、ReportSectionDraft 和安全 ToolResult 摘要，记录创建 AgentRun、Schema 版本、内容哈希与来源引用。每个通过校验的结构化输出或副作用边界都可产生新的 checkpoint；子 Agent 不直接互聊。

### ResearchArtifact（研究库）

| 字段 | 类型 | 约束 |
|---|---|---|
| artifact_id | UUID | 主键 |
| research_task_id / report_version | UUID/int | 必填；同任务版本不可覆盖 |
| artifact_type | enum | markdown / html / citation_manifest / intermediate |
| content / storage_ref | text | 二选一；Markdown 为规范源，HTML/manifest 为同版本派生物 |
| content_hash | str | 必填，按规范化内容计算 |
| generated_by_agent_run_id | UUID | 必填，必须是该任务的 Synthesizer Run |
| created_at | UTC datetime | 必填 |

唯一索引为 `(research_task_id, report_version, artifact_type)`；已生成 Artifact 不允许 UPDATE/覆盖。报告消息幂等键为 `research-report:{research_task_id}:{report_version}`。HTML 只能由固定渲染器从同版本 Markdown 生成并经过 XSS 清理，下载按 `artifact_id` 查询且必须校验 owner，不接受任意 `storage_ref`。

### ResearchNotification（研究库）

| 字段 | 类型 | 约束 |
|---|---|---|
| notification_id | UUID | 主键 |
| owner_id | str | 必填，沿用 OWNER_ID 隔离 |
| research_session_id / research_task_id | UUID/null | 至少一个必填，跨库 ID 读取时校验归属 |
| notification_kind | enum | completed / partial / failed / waiting_approval / interrupted |
| status | enum | unread / read；仅允许由 read API 以 CAS 从 unread 转为 read |
| subject_version | int | 绑定精确 Session/Task/Report 版本 |
| event_seq | int | owner 内单调递增，用于通知 SSE 游标 |
| payload_json | JSON | 只含安全摘要和目标 ID，不含 Prompt/CoT |
| idempotency_key | str | owner 内唯一 |
| read_at | UTC datetime/null | 打开对应目标后以 CAS 标记已读 |
| created_at | UTC datetime | 必填 |

唯一索引为 `(owner_id, idempotency_key)` 和 `(owner_id, event_seq)`；`status=read` 必须同时有 `read_at`，反之亦然。通知删除/保留不影响 Artifact；终态研究数据删除时通知可保留为历史摘要，但不得引用不存在的 owner 对象。Artifact 与 Notification 是两个实体，不共用表或主键。

### ProcessingStep v2（会话库，兼容扩展）

在现有字段上新增：

| 字段 | 类型 | 约束 |
|---|---|---|
| parent_step_id | UUID/null | 只能引用同一 message 的节点 |
| node_type | enum | phase / agent / skill / tool / operation |
| node_key | str | 同一 message 内唯一、用于幂等 upsert |
| display_order | int | 同级稳定排序 |
| detail_json | JSON/null | 只存安全化展示字段 |
| source_event_id | str/null | ResearchEvent 投影来源；非空时按 canonical ID 全局唯一 |
| research_session_id | UUID/null | 普通聊天可空 |
| schema_version | int | 旧数据视为 1，新树为 2 |

层级由父链计算，不保存 depth。旧数据全部视为根节点；普通聊天允许一至二级，深度研究最多三级。拒绝循环、超过三级、跨消息父节点和不存在父节点。父节点必须先持久化，SSE 乱序时前端可短暂缓存子节点。

### 状态转移合同

状态只能由后端服务层的单一转移函数改变；表中未列出的转移一律返回 `INVALID_STATE_TRANSITION`，重复命令返回原决策而不产生副作用。

| 对象 | 合法转移 |
|---|---|
| ResearchSession | `intake_pending → plan_generating → plan_pending_approval → queued → running → {waiting_approval, partial, completed, failed, cancelled, interrupted}`；`plan_pending_approval → intake_pending`（结构性修改）；`waiting_approval → running`；终态不可回退 |
| ResearchIntakeDraft | `collecting → complete → superseded`；`collecting/complete → cancelled` |
| ApprovalRequest | `pending → {approved, rejected, cancelled, superseded}`；终态不可回退 |
| AgentRun | `queued → running → {completed, failed, cancelled, interrupted, limit_reached}`；`limit_reached` 只能由新 Run 通过 `continued_from_agent_run_id` 续跑 |
| ResearchArtifact | 创建后不可变；新报告版本只能 INSERT，不能覆盖旧版本 |
| ResearchNotification | `unread → read` 仅由 read API CAS 完成；通知事实不可改写，删除遵循保留策略 |

### 统一命令输入与竞争合同

`POST /api/research-sessions/{id}/commands` 的请求固定为：
`{command, subject_version, scope_json, idempotency_key}`。`scope_json` 按命令 Schema 校验，不能包含未注册 Skill/Tool、任意 URL、Shell 或 Python。命令与前端按钮、自然语言审批共用同一 service。

| command | 前置状态/subject | 成功副作用 | 竞争/幂等 |
|---|---|---|---|
| `approve_plan` | 当前 `plan_version`、Approval=pending | Approval approved；创建/激活 Task、activity message，Session→queued | 旧版本=`APPROVAL_STALE`；同 key 返回原响应；首个 CAS 成功，其余=`APPROVAL_CONFLICT` |
| `revise_plan` | Intake complete 或当前计划待批准 | 生成新 `plan_version`，旧计划/Approval superseded | 结构性变更必须带新 scope；重复 key 返回原版本 |
| `approve_capability` | capability_override pending | 写入当前版本 Skill/Tool 快照授权 | 不能扩大 subject 版本；竞争同上 |
| `approve_resource_extension` | resource_extension pending | 按绝对上限创建续跑 Run | 超上限=`TASK_MODEL_LIMIT_REACHED`/`TASK_TIME_LIMIT_REACHED` |
| `decline_request` | 任一 pending Approval | 当前分支 rejected；其余分支继续，必要时 Session→partial/failed | 重放返回原拒绝决策 |
| `cancel_research` | Session 非终态 | 禁止新节点，向运行调用发取消信号，最终收敛 cancelled | 终态=`TASK_TERMINAL_CONFLICT`；重复 key 返回终态 |

同一会话活跃 Session 冲突时，Coordinator 必须展示三个明确选择：`modify_current`（回到当前 Intake/计划）、`cancel_then_new`（先取消再创建）、`new_conversation`（在新会话创建）；不得静默覆盖。

### RoleCapabilityRegistry 与 Spec023 映射

RoleCapabilityRegistry 不是第二套 Tool Registry；它只读取 Spec023 的 Skill Scanner/状态和 `build_default_tool_registry()`，输出固定映射：

| Role/Skill | Spec023 Tool | 输入映射 | 副作用 |
|---|---|---|---|
| Search Worker / 来源 Skill | `search_paper_catalog` | `sources[0]→source`（仅 `usenix/dblp/all`）、`query→query`、`time_range.years→years`、`max_results→limit`、`publication_scope` 原样；`facets/language` 仅进入查询摘要，不得新增 Tool 参数 | 目录刷新/写入既有目录，按注册 Tool 语义执行 |
| Search Worker / 来源 Skill | `fetch_paper_detail` | 只接受候选返回的 `article_url`/`official_page_url→url`；禁止拼接或接受任意 URL | 只读详情页，复用 USENIX 白名单 |
| Search Worker / Paper Evaluator | `download_and_import_paper` | 只接受已选候选 `candidate`（`title/authors/year/doi/source_links`）；不得单独传 URL，下载主机由既有服务端白名单校验 | 下载/导入个人知识库，必须绑定计划批准的候选和副作用摘要 |

未知参数、未知 Tool、禁用 Skill/Tool、参数 Schema hash 不匹配均在模型调用前拒绝并返回 `CAPABILITY_NOT_AUTHORIZED` 或 `AGENT_OUTPUT_INVALID`。Skill snapshot 固定保存 `name, schema_version, content_hash, enabled, source_ref`；Tool snapshot 固定保存 `name, parameters_hash, enabled, side_effect_class, entry`。批准时生成快照，AgentRun 只使用该快照；未来 Registry 变化不影响已批准版本。

## 子 Agent 执行协议

- `ResearchAgentRunner` 是产品后端内部 Runtime，不调用 CodeBuddy Task。Coordinator 是会话层控制器，不进入本 Runner；Orchestrator 是唯一创建 AgentRun、分派 WorkItem 和写入运行状态的组件，旧 Spec027 Orchestrator 不得与新 Runner 同时执行同一 WorkItem。
- 固定接口为 `run(AgentRunInput) -> AgentRunOutput`：输入包含 `agent_run_id, research_session_id, research_task_id?, work_item_input, role, skill_snapshot, tool_snapshot, checkpoint_ref?, checkpoint_hash?, budget_snapshot, cancellation_token`；输出包含 `status, schema_version, output_json, output_hash, checkpoint_ref?, checkpoint_hash?, model_metadata, usage, error_code`。`research_task_id` 仅在计划批准后的执行 Run 必填。
- 标准循环：加载角色、Skill 快照、最小上下文和授权 Tool → 调模型 → 校验整批 Tool Call → 执行 → 安全结果回灌 → 直到结构化输出有效或达到上限。
- 同一轮多个 Tool Call 只有在 Tool Registry 声明只读、可并行且互不依赖时才能并行；下载、导入、写入和其他副作用顺序执行。
- 每次输出同时进行 JSON Schema 和业务语义校验；失败计入 `model_loop_count` 并允许自修复。五类 Schema 为 `ResearchPlanOutput`、`SearchWorkerOutput`、`PaperEvaluationOutput`、`CoverageReviewOutput`、`ReportSynthesisOutput`，均必须有 `schema_version`、安全字段、来源/证据 ID 和内容哈希；不得包含 CoT。
- fast 模型：初始尝试 + 两次 fast 重试；仍失败时最后一次切换 role-compatible strong 模型，共最多 4 次 attempt。每次 attempt 创建一个 AgentRun，`attempt` 从 1 开始；模型循环与 Tool Call 分别单调计数并同时计入 Run 链和 Task 预算。
- Planner 只收确认 Intake；Search Worker 只收自己的研究问题和来源预算；Evaluator 只收候选与标准；Critic 只收计划、统计和证据摘要；Synthesizer 只收验证证据、引用、结构和写作要求。下游不读取完整会话或全部记忆。
- ToolResult 只保留注册 Tool 声明的安全摘要、状态、错误码、结果 ID、长度上限和 content hash；移除凭据、完整响应头、隐藏 Prompt、CoT 和未授权 URL。取消屏障在每次模型调用、Tool 执行前后和 Artifact 写入前检查；取消/终态后迟到结果只能记录丢弃事件，不能更新 WorkItem、ProcessingStep 或 Artifact。
- 论文与网页内容是不可信数据，不得改变角色、Skill、Tool、预算、权限或系统指令。

## 预算、资源申请与取消

- 每个 AgentRun 初始最多 40 个模型循环、160 次 Tool Call。
- 每个 ResearchTask 初始最多 160 次模型调用、640 次 Tool Call。
- 标准档最多 4 个并发子 Agent，默认最长 90 分钟；ResourceProbe 必须保留至少 20% 系统资源，失败时降为单 Worker。
- 达到上限时 AgentRun 进入 `limit_reached`，对应 WorkItem 进入 `waiting_approval`；独立分支继续。只有所有剩余工作都被阻塞时，ResearchTask/Session 才进入 `waiting_approval`。
- 资源卡展示执行者、已用额度、已完成、缺失结果、申请原因、增量、预计时间、Skill/Tool 和副作用；用户可批准更少额度、拒绝或取消。
- 默认每次扩容最多增加：AgentRun 链 40 模型循环、160 Tool Call；ResearchTask 160 模型调用、640 Tool Call；执行时间 90 分钟。
- 最多扩容 3 次。绝对上限：单 AgentRun 链 160 模型循环、640 Tool Call；ResearchTask 640 模型调用、2560 Tool Call、6 小时。
- 扩容后创建新的 AgentRun 并设置 `continued_from_agent_run_id`；旧 Run 保持 `limit_reached`，从最后一个已验证检查点继续。
- 同参数 Tool 调用优先使用幂等结果或缓存；具体 Tool 可声明更低上限。下载/导入只作用于计划批准的对象。
- 用户拒绝时该分支记为 partial/cancelled，其他分支继续；审批可无限期等待。证据足够时生成 partial 报告，否则明确失败。
- 取消为协作式：立即停止创建新工作，向可取消调用发送信号；终态后迟到结果不得写回状态或 Artifact。

## 检索、阈值与覆盖策略

- “总体综述”是通用研究方式，不是默认研究方向，Planner 禁止把它作为兜底 facet。单一宽主题可以只有一个真实方向，并通过查询或来源 lane 并行。
- Orchestrator 通过唯一 `CatalogSourceFactory` 注入 Spec015 的 `PaperDiscoveryStore`、`UsenixAcceptedSource` 和可用的 DBLP source，再调用既有 `CatalogSearchGraph`/`CatalogRagAdapter`；禁止在 `research` 命名空间复制采集、缓存、目录或 RAG。没有可用来源时必须返回可诊断的 `SOURCE_UNAVAILABLE`/partial/failed，不得走空 `papers=[]` 后静默生成成功或恒定空结果。
- 本地 Spec015 目录是默认第一来源；候选不足或覆盖缺失时自动调用已注册目录刷新 Tool。只读网络刷新只限已批准的 `search_paper_catalog`/来源 Skill 范围。
- 检索先宽召回再由 Evaluator 排序；硬性用户范围（年份、来源、主题排除）不可突破，相关度是可调软阈值。
- 零结果时依次：在批准范围内生成查询变体、检查本地目录和来源健康、检查阈值、在有界范围内软化阈值。仍为零时输出证据缺口，不伪造 completed。
- 最多两轮同范围自动 Re-plan；只有来源、时间、Skill/Tool、预算或目标扩大时需要重新批准。
- 任务详情展示安全化诊断：实际查询、来源、本地命中、远程刷新、各阶段数量、去重、相关度分布、阈值变化、淘汰原因、限流/失败和证据缺口。

## processing_steps 三级树与显示规则

- ResearchEvent 是执行审计事实，ProcessingStep 是会话持久化显示投影。Projector 先读已持久化事件，再按 `source_event_id/node_key` 幂等 upsert；投影失败不回滚研究结果，而是重试并显示“轨迹同步中”。
- v2 迁移只做 additive 变更：在现有 `processing_steps` 增加上述字段和索引，不重写旧行；旧行 `schema_version=1`、`parent_step_id=null`、`node_type=operation`，原 `kind/label/status/summary` 保持可读。新增唯一索引 `(message_id,node_key)`，非空 `source_event_id` 全局唯一。
- `source_event_id` 规范化为全局唯一的 `research-event:{research_task_id}:{event_seq}`；Projector 先持久化父节点再写子节点，校验同 message、无循环、最多三级。乱序 SSE 由前端按 `parent_step_id` 暂存，重复事件按 `source_event_id/node_key` 更新而不新增。
- Projector 失败记录 `TRACE_PROJECTION_FAILED` 和待重放标记；重试从已持久化 ResearchEvent 按序重放，成功后清除标记。投影失败不回滚 ResearchEvent、WorkItem 或 Artifact。
- 研究树固定为：一级 Phase；二级 Child Agent/WorkItem；三级 Skill 激活或 Tool 调用。Skill 与 Tool 是同级操作节点；Tool 标注由哪个 Skill 指导，不增加第四级。
- 正在运行的路径自动展开至第三级；已完成阶段默认折叠到第二级并显示耗时和结果摘要；失败节点强制展开。
- 用户手动展开状态以 `owner + research_session_id + node_id` 保存在浏览器 localStorage，刷新后保留，暂不跨设备同步。
- 自动滚动只在用户未离开当前运行区域时跟随活动节点，不抢夺阅读位置。
- running 节点有轻量动画；终态停止动画；失败通过图标、文本和颜色共同表达；遵守 `prefers-reduced-motion` 和树形 ARIA。
- REST 返回按顺序排列的扁平邻接表；SSE 每次只发送新增或更新节点，带 `schema_version: 2` 和 `parent_step_id`。旧客户端忽略新增字段后仍可扁平展示。

## 会话、Tab 与通知

- 同一会话最多一个活跃 ResearchSession；再次提出新研究时提供“修改当前研究 / 取消后新建 / 新会话研究”三个选择，不自动覆盖。
- Deep Research 不占用现有单一 `conversation_active_skill`。研究回复通过最近上下文、显式引用和 `research_session_id` 关联；普通聊天不自动成为研究参数。
- Intake/计划问答使用各自消息的普通处理步骤；计划批准后创建一条专用活动助手消息，全部三级树绑定于此；最终报告使用独立助手消息。
- 计划、能力和资源审批卡同时出现在会话、研究 Tab 详情和应用内待处理通知中。终端不承担产品审批。
- 所有按钮与自然语言调用同一命令层。按钮提交中禁用；过期卡保留历史但禁用；失败恢复可重试状态。
- 用户级 Research 通知 SSE 只发送 completed、partial、failed、waiting_approval、interrupted；任务 SSE 发送详情节点。断线后按游标补发，打开目标后标记已读。
- 深度研究 Tab 保留创建表单和任务卡；显示绑定会话、阶段、进度、等待操作、耗时和 Agent/Tool 摘要，并提供“打开对应会话”。三级树复用会话组件。
- 表单创建标题默认 `深度研究：<主题>`，继承当前项目（无项目则不绑定），把表单摘要写成第一条自然语言用户消息并自动打开会话。
- 报告在会话直接渲染，提供 Markdown 下载和派生 HTML；PDF 不是本 Spec 强制产物。

## 状态机、命令与错误码

### 状态规则

- Session 状态只由后端推导。`partial` 表示已形成可读报告但存在证据/分支缺口；`failed` 表示无法形成可用报告。
- 计划结构变化产生新版本并 supersede 旧 Approval；小型、非结构指令可以在既有检查点应用。
- 仅当来源、时间、Skill/Tool、预算或目标扩大时 Re-plan 必须重新批准。
- 启动审计把无有效执行租约的非终态 AgentRun 标记 interrupted；已验证 Artifact/ToolResult/证据保留。用户重试时创建新 Run，不从未持久化模型上下文续写。
- Synthesizer 失败时保留证据，任务为 partial 并显示错误；重试只运行 synthesis，成功后创建新报告版本并完成。

### 统一命令

`approve_plan`、`revise_plan`、`cancel_research`、`approve_capability`、`approve_resource_extension`、`decline_request`。命令必须携带 session、目标版本和幂等键。

### 新增稳定错误码

`RESEARCH_SESSION_NOT_FOUND`、`RESEARCH_SESSION_ACTIVE_CONFLICT`、`INTAKE_INCOMPLETE`、`PLAN_VERSION_STALE`、`APPROVAL_STALE`、`APPROVAL_CONFLICT`、`SKILL_DISABLED`、`CAPABILITY_NOT_AUTHORIZED`、`AGENT_OUTPUT_INVALID`、`MODEL_LOOP_LIMIT_REACHED`、`TOOL_CALL_LIMIT_REACHED`、`TASK_MODEL_LIMIT_REACHED`、`TASK_TIME_LIMIT_REACHED`、`TRACE_PROJECTION_FAILED`、`ARTIFACT_NOT_READY`、`MODEL_UNAVAILABLE`。继续复用 Spec027 的来源、资源和状态错误码。

### 错误出口矩阵

所有错误响应统一为 `{error: {code, message, retryable, subject_version}, data: ...}`；SSE 使用同一 `code`，不得把内部异常文本回传。

| 错误码 | HTTP/SSE | retryable | 用户动作 | 保留数据 |
|---|---|---|---|---|
| `RESEARCH_SESSION_NOT_FOUND` | 404 / error | 否 | 返回列表或新建 Session | 不写入 |
| `RESEARCH_SESSION_ACTIVE_CONFLICT` | 409 / error | 否 | 选择修改当前、取消后新建或新会话研究 | 当前 Session/Task 不变 |
| `INTAKE_INCOMPLETE` | 400 / plan_rejected | 否 | 补齐 topic/objective/time_range | Draft 与用户消息保留 |
| `PLAN_VERSION_STALE`、`APPROVAL_STALE` | 409 / approval_stale | 否 | 刷新最新计划卡 | 旧计划/审批保留为历史 |
| `APPROVAL_CONFLICT` | 409 / approval_conflict | 否 | 查看首个有效决策 | 首个决策保留 |
| `SKILL_DISABLED`、`CAPABILITY_NOT_AUTHORIZED` | 403 / capability_rejected | 否 | 修改计划或启用已注册能力 | Intake/旧计划保留 |
| `AGENT_OUTPUT_INVALID`、`MODEL_UNAVAILABLE` | 422/503 / agent_failed | 是 | 按提示重试或等待模型恢复 | Run、检查点、证据保留 |
| `MODEL_LOOP_LIMIT_REACHED`、`TOOL_CALL_LIMIT_REACHED`、`TASK_MODEL_LIMIT_REACHED`、`TASK_TIME_LIMIT_REACHED` | 429 / waiting_approval | 是 | 批准较小或受上限约束的扩容，或取消 | 已验证交接物/Artifact 保留 |
| `TRACE_PROJECTION_FAILED` | 503 / trace_syncing | 是 | 等待重放或重试投影 | ResearchEvent/研究结果保留 |
| `ARTIFACT_NOT_READY` | 409 / artifact_pending | 是 | 等待 synthesis 或重试 synthesis | 证据与旧报告保留 |

旧未绑定 Task 清理必须先 dry-run 输出目标 Task/children ID 与计数；计数写入 Task09 产物，任何选择条件、owner 校验或删除步骤失败即中止且不删部分数据。确认后才按应用层顺序删除 Task、Plan、WorkItem、Event、Selection、Report；会话、目录和 KB 计数/内容前后必须一致。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| POST `/api/conversations/{id}/messages` | 普通自然语言消息 | 原 SSE；可新增 Skill 激活、Intake、计划卡和研究命令事件 | 现有错误；Skill/Session 稳定错误 |
| POST `/api/research-sessions` | 表单摘要、可选 conversation/project | 202 + Session、会话和首条消息 | 400；404；409 |
| GET `/api/research-sessions` | project/status/cursor | 稳定分页 Session 列表 | 400；404 |
| GET `/api/research-sessions/{id}` | session id | Intake、计划、审批、Task、通知和报告摘要 | 404 |
| POST `/api/research-sessions/{id}/commands` | command、subject_version、scope、idempotency_key | 更新后的 Session/Approval | 400；404；409 |
| GET `/api/research-sessions/{id}/artifacts` | report_version 可选 | Artifact 和引用 manifest | 404；409 |
| GET `/api/research-sessions/{id}/artifacts/{artifact_id}/download` | artifact id | 安全文件响应（固定 Content-Type/Content-Disposition、大小上限） | 404；409 |
| GET `/api/research-notifications/events` | Last-Event-ID/after_seq | owner 级重要通知 SSE | 400；410 |
| POST `/api/research-notifications/{id}/read` | 空 body | 已读通知 | 404 |
| GET `/api/messages/{id}/processing-steps` | message id | v2 扁平邻接表，兼容 v1 | 404 |
| POST `/api/research-tasks` | 旧创建请求 | 202 + 兼容创建的 Session，进入 Intake/计划审批而非直接运行 | 400；404；409 |

现有 ResearchTask 查询、事件、报告、取消、移动和删除端点暂时保留供 Tab 与调试使用。新前端只以 Session 为产品入口，旧 POST 适配器暂不删除。

## 存储、一致性与删除

- Session、Intake、Approval、AgentRun、交接物、Artifact、Notification 放在 `data/research/research.sqlite3`；processing_steps 继续在会话库。
- 跨库只保存外部 ID，不建立 SQLite 外键。读取时校验对象存在、owner 与 conversation/project 归属。
- 创建与投影采用可重放幂等 Saga：会话消息 → Session → ResearchEvent → ProcessingStep 投影。不得声称跨库原子事务。
- 会话存在活跃研究时删除返回冲突并要求先取消；研究终态后可删会话，研究数据保留并解除绑定，可从 Tab 重新绑定新会话。
- 单独删除 ResearchTask 必须显式操作并展示删除范围；不删除论文目录和知识库。
- 迁移时不得直接删除旧版数据；旧版未绑定会话的 ResearchTask 及其计划、WorkItem、事件、选集和报告必须交由 Task09 的 dry-run/确认流程处理，且不得删除会话、目录、知识库或已绑定 Task。

## 边界

- 明确深度研究请求激活 Skill；普通“查一下”不静默建 Session；含糊请求先澄清；Coordinator 只在会话层工作，不创建 AgentRun。
- 同一消息重放、SSE 重连、按钮双击、多窗口审批和自然语言/按钮竞争均不创建重复 Session、Approval、ProcessingStep 或报告消息。
- topic/objective/time_range 任一缺失不得生成计划；推断参数必须展示来源和确认状态。
- Planner 输出未知能力、禁用 Skill、未授权 Tool、循环依赖、非法 Schema 或超预算时拒绝执行。
- 用户批准只绑定最新 plan_version 和当时可执行 Tool 快照；未来新增 Tool、扩大来源或副作用不得继承授权。
- 同会话活跃 Session 冲突必须提供三种选择，不覆盖现有任务。
- processing_steps 兼容旧扁平数据和二级普通聊天；拒绝超过三级、循环、孤儿和跨消息父节点。
- 投影失败不丢 ResearchEvent 或研究结果；恢复后同一 source_event_id 只生成一个节点。
- 完成阶段折叠到第二级，运行路径展开到第三级，失败强制展开；刷新保留手动展开，自动滚动不抢用户位置。
- 目录为空、单源失败、双源失败、零结果、阈值过高和无摘要分别给出真实诊断；不得用“总体综述”伪造子方向或伪造论文。
- 单次 fast + 两次 fast 重试 + 一次 strong 封顶；非兼容模型不得冒充降级成功。
- AgentRun、Task 模型/Tool/时间达到上限时保留结果、停止对应节点并生成资源卡；批准后新 Run 从验证检查点继续。
- ResourceProbe 失败降为单 Worker；用户批准并发也不能突破 20% 系统余量。
- 取消后不启动新节点，迟到 Tool/模型结果不能覆盖终态。
- 报告 Markdown、HTML、manifest 版本不可变；HTML 无 XSS；相同任务/版本只写回一条最终消息。
- 会话删除冲突、终态解绑、重新绑定、Task 显式删除和旧未绑定数据清理不得波及目录/KB。
- 模型不可用时 Intake 保留，计划显示 `MODEL_UNAVAILABLE`，生产不得用规则模板伪装真实 Planner。
- 本 Spec 不创建、不注册、不批准通用 Shell/Python/公网 URL Tool；任何未来加入都必须另立修订并重新确认，当前边界测试应断言不存在此类 Tool。

## 明确不做

- 不实现完整权限与安全策略中心；当前只实现计划版本级授权、Registry 和最低隔离。
- 不实现跨设备同步树节点展开状态。
- 不实现浏览器系统通知、邮件或移动推送，只做应用内通知。
- 不强制生成 PDF。
- 不允许子 Agent 递归创建子 Agent。
- 不实现 Spec028 的自动租约接管和模型调用中途续跑。
- 不实现 Spec030 的完整 Claim/Evidence 矩阵，只提供引用 manifest 和可追踪证据。
- 不新增多用户账号、组织或角色权限系统，继续使用现有 OWNER_ID 隔离。
- 不删除深度研究 Tab 创建表单。
- 不在未再次修订并确认本 Spec 的情况下主动新增通用 Shell/Python/任意 URL Tool；这不是永久禁止，而是范围门禁。

## 验收方式

### 确定性自动验收

- 使用明确标记的 Fake Agent Runtime 覆盖：意图候选与激活门禁、Intake 字段来源、计划版本、全部审批类型、命令幂等、Session/Task 状态机、Agent 输出 Schema、模型/Tool/时间预算、扩容链、取消、投影重试、通知补发、Artifact 版本、删除与兼容适配。
- processing_steps 验证 v1 扁平、v2 二级和三级树、循环/孤儿/深度拒绝、SSE 乱序缓存、刷新恢复、折叠策略、失败展开、reduced motion、XSS 和 DOM 契约。
- 检索固定样本验证本地优先、远程刷新、真实研究方向、宽召回、阈值软化、淘汰原因、单源降级和零证据 partial/failed。
- 注入恶意论文、ToolResult 和模型输出，验证不能改变计划、权限、Skill/Tool、预算或前端 DOM。

### 真实运行 Smoke

必须用本机真实 Ollama 和真实前端，从会话输入“帮我做一个深度研究：总结 2020–2024 年 USENIX Security 论文中的软件供应链攻击面与防御方法”开始，完成：

`意图识别 → Skill 激活 → Intake → 真实 Planner → 前端批准 → 至少一个真实 Search Worker → 目录 Tool → Evaluator/Critic/Synthesizer → 三级树 → Markdown/HTML 报告消息`

Smoke 必须证明：

- AgentRun 保存并展示实际模型和推理档位；临时研发分派模型不写入产品 Runtime 规则。
- 至少一个 Search Worker 真正调用现有目录 Tool；有论文则显示真实候选与引用，无论文则显示可复查来源/阈值诊断，不能伪造。
- 所有审批均可在前端完成，终端不参与。
- 页面刷新和 SSE 重连后三级树、审批和通知恢复且无重复。
- 最终 Markdown 可下载、HTML 可安全阅读。
- 最终候选执行受影响领域回归、全量回归、桌面与窄屏浏览器验收、直接启动服务和运行时验证；真实环境阻塞必须明确记录，不能用 Fake 冒充。

## 产品使用步骤（可执行用户旅程与验收点）

1. 在已打开的普通会话输入：“帮我做一个深度研究，主题是软件供应链攻击，目标是总结 2020–2024 年 USENIX Security 论文中的攻击面与防御方法。”会话 Agent 只先展示启用 Skill 摘要并调用 `activate_skill`；验收点：明确请求激活 `deep-research-orchestration`，普通“查一下软件供应链攻击”不创建 Session。
2. Agent 调用 `begin_research_intake` 后逐项询问缺失的 topic/objective/time_range；验收点：每个 IntakeField 显示 value、source、confidence、confirmation_status，字段未齐不得生成计划；刷新会话后值不丢失。
3. 参数齐全后查看计划卡；卡片必须展示目标、范围/排除、真实研究方向、来源与查询策略、预计 Agent、预算、报告结构和降级策略；验收点：不得出现“总体综述”伪 facet，Planner 输出只含已注册能力。
4. 在会话或 Research Tab 点击“批准计划”；也可输入自然语言批准；验收点：两者进入同一 `approve_plan` 命令，按钮重复点击/双窗口只产生一个 Approval 和一个 Task；批准前 ResearchTask 不存在或未激活。
5. 若卡片提出能力或资源审批，分别查看副作用、目标、增量和上限后点击“批准/拒绝”；验收点：三类 Approval 均可在前端完成，过期版本返回 `APPROVAL_STALE`，终端不参与。
6. 执行期间打开专用研究消息；验收点：一级 Phase、二级 Agent/WorkItem、三级 Skill/Tool 按 `parent_step_id` 显示，模型、Skill 快照、Tool 名和安全摘要可见，Prompt/CoT/凭据不可见；失败节点展开，完成阶段折叠到二级。
7. 刷新页面或断开再连接 SSE；验收点：按游标补发且不重复，乱序子节点最终挂到父节点，localStorage 恢复展开状态且不抢用户滚动位置。
8. 在运行中点击取消；验收点：Session/Task 收敛为 cancelled，不创建新节点，迟到模型/Tool 结果不能改写终态、树或 Artifact。
9. 运行完成或 partial 后，在最终助手消息打开报告；验收点：同一 Task/report_version 只有一条消息，Markdown 可下载，HTML 由 Markdown 安全派生且无 XSS，引用 manifest 中每条引用可追溯到已验证目录证据。
10. 在模型不可用、来源为空、单源失败、阈值过高和 synthesis 失败场景复试；验收点：分别显示 `MODEL_UNAVAILABLE`、来源/阈值诊断、partial/failed 或可单独重试，不以规则模板或假论文伪装成功。

### 必测反例与验收判据

- 普通聊天、含糊请求、重复消息、活跃 Session 冲突、旧 plan_version、审批竞争、禁用 Skill/Tool、未知参数、未来新增 Tool 均不得产生越权副作用。
- 固定 Fake Runtime 必须逐项断言状态转移、CAS/幂等键、五类结构化 Schema、Run/Task 预算、checkpoint、取消屏障、投影重试和 Artifact/Notification 唯一性。
- 真实 Smoke 固定使用上述主题、时间范围 `2020–2024`、来源 `usenix`、中文输出；字段级证据必须包含实际 `resolved_model/reasoning_effort`、实际 Tool 名、`research-event:{task}:{seq}`、三级 `ProcessingStep`、Markdown/HTML/manifest ID。真实来源或 Ollama 不可用时，验收记录环境阻塞及复验命令，不得用 Fake 冒充成功。

## 执行配置

> 2026-09-13 已用 `ollama list` 实测本机存在 `qwen3.8:27b-mlx` 与 `qwen3.5:9b`。本次研发会话的临时模型选择不在本 Spec 留存，也不写入产品 Runtime、长期规则或记忆。研发分派模型只用于 `Task(...)` 文档/实现分工；产品 Runtime 只在 AgentRun 中保存能力注册表解析出的 `resolved_model/reasoning_effort`，两者不得混用。产品 Runtime 模型按角色能力和实际可用模型动态解析。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订 Spec、技术决策、范围与最终落地校验 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | Spec 确认后补产品步骤与验收旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 需求/技术/验收总控、复用与安全边界评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | `Task(backend-dev)` / `Task(frontend-dev)` | 按端实现；复杂 Runtime、跨库幂等和树形 UI 均按复杂任务处理 |
| 测试 | `qwen3.5:9b` | 32k | `Task(backend-tester)` / `Task(frontend-tester)` / `Task(tester)` | 定向测试、跨端验收、真实 Smoke 和最终签字 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec034 | 本文件 | — | 完成 |
| 02 | 冻结数据模型、状态机、迁移与兼容接缝 | [`task-02-session-state-and-migration-gate.md`](../plans/034/task-02-session-state-and-migration-gate.md) | Spec确认、双评审 | 已完成 |
| 03 | 实现会话意图、Deep Research Skill 与 Intake | [`task-03-conversational-intake.md`](../plans/034/task-03-conversational-intake.md) | 02 | 已完成 |
| 04 | 实现计划版本、统一审批命令与前端卡片 | [`task-04-plan-and-approvals.md`](../plans/034/task-04-plan-and-approvals.md) | 03 | 已完成 |
| 05 | 实现 ResearchAgentRunner 与真实子 Agent 循环 | [`task-05-agent-runtime.md`](../plans/034/task-05-agent-runtime.md) | 02、04 | 已完成 |
| 06 | 接通论文目录、评估、Critic 与覆盖补偿 | [`task-06-research-execution.md`](../plans/034/task-06-research-execution.md) | 05 | 已完成 |
| 07 | 实现 processing_steps 三级树与实时投影 | [`task-07-processing-tree.md`](../plans/034/task-07-processing-tree.md) | 02、05 | 已完成 |
| 08 | 实现报告 Artifact、会话写回与通知 | [`task-08-report-and-notifications.md`](../plans/034/task-08-report-and-notifications.md) | 06、07 | 已完成 |
| 09 | 复用 Research Tab、清理旧入口与旧数据 | [`task-09-workspace-and-cleanup.md`](../plans/034/task-09-workspace-and-cleanup.md) | 04、07、08 | 已完成 |
| 10 | 最终评审、全量回归、真实 Smoke、部署与复盘 | [`task-10-review-regression-deploy.md`](../plans/034/task-10-review-regression-deploy.md) | 02–09 | 已完成 |
| 11 | 至少五篇候选与实质性综述输出 | [`task-11-report-content-and-recall.md`](../plans/034/task-11-report-content-and-recall.md) | 06、08、10 | 实施中 |

## 评审记录

- 需求评审：`docs/sdd/reviews/034-requirement-review.md`（第二轮复审：APPROVE）
- 技术评审：`docs/sdd/reviews/034-tech-review.md`（第二轮复审：GO）
- 验收评审：`docs/sdd/reviews/034-acceptance-review.md`（测试报告、真实 Smoke 证据与开发主管签字；通过）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-13 | 架构师（自身） | 根据多轮 Grilling 创建 Spec034，冻结会话式入口、Intake/计划审批、真实子 Agent Runtime、三级处理树、目录接线、资源申请与报告回写边界 |
| 2026-09-13 | SDD Gate Reviewer（当前子 Agent） | 需求评审 REVISE、技术评审 NO-GO：发现产品步骤占位、Task/Q 断链、运行/状态/迁移/Registry/来源注入契约缺口，已落盘两份评审报告 |
| 2026-09-13 | 架构师（自身） | 依据门禁评审进入修订中：补齐产品旅程、状态/命令/CAS、Artifact/Notification、真实 Runner/Registry/目录接缝与可重复 Smoke；Spec 保持待确认 |
| 2026-09-15 | 架构师（自身） | Task10 修复目录 RAG 降级排序与 Search→Evaluator 事实交接；最终全量 pytest `1878 passed, 1 skipped, 5 warnings, 52 subtests`；真实端口 18083 完成 Intake→Plan→Approval→Search→Evaluator→Synthesizer 并生成 Markdown/HTML/citation manifest，完成部署、验收与复盘，Spec 标记已完成 |
| 2026-09-16 | 架构师（自身） | 真实 Artifact 仅含一篇证据对象且报告渲染只输出 ID；新增 Task11，补强至少五篇候选保留和标题/摘要/关键词/跨论文归纳，Spec 暂回实施中 |
