# Spec034 技术评审报告 — 会话式深度研究与真实子 Agent Runtime

## 评审元数据

- **评审者**：`/root/spec034_gate_review`（当前子 Agent，第二轮复审）
- **角色**：开发主管 / SDD Gate Reviewer
- **模型**：当前执行任务的 Agent（本次仅基于只读文件事实评审）
- **分派方式**：由主 Agent 委派；本轮复审不修改业务代码、Spec 状态或 Task 状态
- **评审基线**：`feature/spec-034-conversational-research-runtime`，2026-09-13 修订后工作树
- **评审范围**：Spec034、Task02–Task10，以及 Spec023 Tool/Skill、Spec027 Research Runtime、Spec022 会话处理步骤、Spec032.1/033 来源接缝

## 一、结论

**GO（技术门禁通过）**。

第一轮的三个直接技术阻塞——WorkItem/Tool 参数映射、状态/迁移/投影契约、真实目录来源注入与 Runner 协议——均已在修订 Spec034 和 Task02–Task10 中冻结。文档现在足以让后续任务实现同一套 Runtime；本结论只表示技术门禁通过，不代表业务代码、真实模型或外部来源已运行验证。

## 二、第二轮逐项复审证据

### 1. Registry 复用与参数映射 — 已关闭

- Spec034 第 228–238 行明确 RoleCapabilityRegistry 只读取 Spec023 Skill/Tool Registry，并冻结 `search_paper_catalog` 的 `source/query/years/limit/publication_scope` 映射、`fetch_paper_detail` 的候选详情 URL 约束，以及 `download_and_import_paper` 的候选 `candidate` 约束。
- 同段冻结 Skill/Tool snapshot 字段、hash、enabled、side-effect、未知参数/禁用能力/Schema 漂移的模型调用前拒绝。
- Task05 第 13、46 行和 Task06 第 13–19、43–48 行同步复用边界与测试要求。

### 2. Session/Approval/AgentRun 状态、命令与唯一性 — 已关闭

- Spec034 第 61–179 行冻结六类实体、跨库 owner 校验、Artifact/Notification 独立表及唯一索引。
- 第 198–225 行冻结所有状态转移、统一 payload、CAS/幂等/过期/竞争语义及三种活跃 Session 选择。
- Planner 在批准前只绑定 `research_session_id`；批准后执行 Run 必须绑定 Task/WorkItem（第 119–147、240–247 行），Coordinator 不进入 AgentRun。

### 3. ResearchAgentRunner、Schema、预算、checkpoint 与取消 — 已关闭

- Spec034 第 238–248 行冻结 `run(AgentRunInput) -> AgentRunOutput`、实际模型元数据、五类结构化 Schema 最低字段、整批 Tool 校验、attempt/loop/tool 计数、强模型升级、checkpoint hash、取消前后写屏障和迟到结果丢弃。
- Task05 第 18–29、44–48 行要求 Fake→真实 Ollama、快照、预算、检查点和取消合同；旧 Spec027 Orchestrator 与新 Runner 的单一执行权已明确。

### 4. ProcessingStep v2 与投影 — 已关闭

- Spec034 第 181–196、264–268 行冻结 additive migration、v1 根节点映射、`(message_id,node_key)`、canonical `research-event:{research_task_id}:{event_seq}`、父链/三级限制、SSE 乱序缓存和 projector 重放。
- Task02 第 18–24、48–52 行与 Task07 第 17–20、42–45 行同步迁移、唯一性、失败不回滚和重试标记。

### 5. 真实目录来源工厂与本地优先 — 已关闭

- Spec034 第 266–274 行冻结唯一 `CatalogSourceFactory` 注入 Spec015 PaperDiscoveryStore、USENIX/DBLP source，并调用既有 CatalogSearchGraph/CatalogRagAdapter；无来源必须返回可诊断 `SOURCE_UNAVAILABLE`/partial/failed，不得空目录恒定成功。
- Task06 第 14、43–48 行要求真实注入点、本地优先、远程刷新与无来源失败合同。

### 6. 安全、错误矩阵、回滚与 Smoke — 已关闭

- Spec034 第 247、315–337、352–395 行冻结 ToolResult 安全化、稳定错误码矩阵、清理 dry-run/失败中止、Shell/Python/公网 URL 不实现和隔离边界。
- Spec034 第 399–438 行及 Task10 第 25、37–45 行冻结 Fake/真实 Smoke 的固定主题、字段级证据、诚实环境阻塞和不得伪造成功。

## 附录 A、第一轮代码事实与复用接缝（历史）

### 1. Spec027 当前并不是可直接替代的真实 Agent Runtime

- `backend/app/research/application/orchestrator.py:1–18` 明确声明当前编排器不做 LLM 调用，评估与覆盖判定是确定性规则；`:155–183` 由确定性 `Planner.build_plan` 生成计划。
- `backend/app/research/application/planner.py:1–18,47–48` 使用规则 Planner，`planner_model` 为 `deterministic-rule-v1`。
- `backend/app/research/application/model_router.py` 是现有路由/记录接缝，并不提供 Spec034 所需的独立 AgentRun、Skill 快照、Tool 循环和结构化交接物。

这支持 Spec034 的问题判断，但也意味着 Task05 必须明确替换/适配边界：哪些 Spec027 确定性节点继续由 Orchestrator 执行，哪些节点改为 `ResearchAgentRunner`，以及同一 WorkItem 不得被旧 Orchestrator 和新 Runner 双重执行。

### 2. Spec023 Tool Registry 的真实 Schema 与 Spec034 WorkItem Schema 不一致

- `backend/app/skills/registry.py:21–63` 的 `search_paper_catalog` 要求/支持 `source`、`query`、`years`、`limit`、`publication_scope`。
- `backend/app/skills/registry.py:98–125` 的 `fetch_paper_detail` 只接受 `url`，并要求服务端 USENIX 白名单。
- Spec034/027 的 WorkItem 合同（`backend/app/research/domain/contracts.py:59–100`）使用 `query`、`facets`、`sources`、`max_results`、`language`，并没有定义到 Registry 参数的转换。
- 现有 `backend/app/skills/tool_dispatch.py:119–163` 对 `source` 的选源、年份、limit 和 publication scope 负责真实业务映射；不能在 Research 命名空间中复制一份。

**阻塞建议 T-01**：在 Spec034/Task05 或 Task06 冻结 `RoleCapabilityRegistry` 的映射接口，明确每个角色/Skill/schema_version 对应的 Tool 名、输入转换、输出安全摘要、副作用和错误码。至少写清 `sources → source`、`max_results → limit`、`facets/language` 如何处理，以及何时从候选 `article_url` 调用 `fetch_paper_detail`。合同测试应对照实际 `ToolEntry.parameters`，并断言未知参数/禁用 Tool/不兼容 Schema 在执行前被拒绝。

### 3. 默认目录路径当前在无数据源注入时会诚实但恒定降级

- `backend/app/research/application/search_catalog_adapter.py:18–25` 明确记录：没有 `accepted_source`/`dblp_source` 注入时，当前分支对空 `papers=[]` 做 RAG，最终恒返回 `SOURCE_DEGRADED`/空结果。
- `:101–169` 的完整 `CatalogSearchGraph` 只有注入真实来源时才会运行；Spec034 又要求默认真实接通本地目录、覆盖不足时刷新来源。
- `backend/app/paper_discovery/application/catalog_search_graph.py:235–280,388–410` 显示 Spec015 现有图的 USENIX/DBLP 开关、九节点和 DBLP 默认跳过语义；Spec034 不能把“远程刷新”写成未声明的旁路。

**阻塞建议 T-02**：Task06 必须冻结真实来源工厂/注入点、目录数据库路径、`CatalogSearchGraph`/`CatalogRagAdapter` 调用形态和 source health 诊断；默认产品入口不得走当前“空 papers 恒空”路径。若环境没有来源，返回 `SOURCE_UNAVAILABLE` 或有明细的 partial/failed，而不是把空结果当成功。补固定样本证明本地命中、远程刷新、单源失败和零结果诊断均来自现有 Spec015 接缝。

## 附录 B、第一轮技术契约逐项评审（历史）

### 1. Session / Intake / Approval 状态机 — 阻塞

Spec034:61–113 给出字段和状态集合，却没有完整转移矩阵。当前只有 Spec027 Task/WorkItem 状态机（`backend/app/research/domain/contracts.py:102–149`），不能推导 `intake_pending → plan_generating → plan_pending_approval → queued/running`、取消、拒绝、supersede 和重试的合法边界。六类命令也没有逐命令 payload、CAS 条件和响应。

**建议 T-03**：为四类对象分别给出 `from → to` 表、终态集合、触发命令、并发条件和稳定错误码；明确计划批准前 `research_task_id` 为 null，批准事务/补偿如何创建 Task 与 activity message；定义自然语言和按钮竞争时的 compare-and-set 规则及重复请求返回原决策。

### 2. ResearchSession 一活跃约束与 owner/跨库校验 — 高风险

Spec034:216、262–267 只写应用层原则。ResearchSession 的表没有唯一索引/约束语义；`conversation_id`、`trigger_message_id`、`plan_message_id`、`activity_message_id` 和 `final_message_id` 是跨库外部 ID，但没有定义每次写入如何验证 owner、消息角色/会话归属和项目归属。现有会话处理步骤 API 通过消息 owner 过滤（`backend/app/api/routes_conversations.py:890–892`），新 projector 不能绕过该隔离。

**建议 T-04**：冻结 `(owner_id, conversation_id, active_status)` 的并发创建策略（事务内唯一占位或应用层 CAS）、所有外部 ID 的验证顺序，以及跨库 Saga 每个步骤的补偿/重放标识。

### 3. AgentRun 与真实模型循环 — 阻塞

Spec034:115–133、170–179 描述了独立上下文、Skill 快照、Tool 白名单、JSON Schema、fast×3/strong×1，但没有定义：模型调用接口、结构化输出 Schema 的具体字段、ToolResult 安全化规则、失败重试是否每次创建 AgentRun、attempt 与 model_loop_count/tool_call_count 的关系、检查点格式、取消屏障和 strong 模型兼容性判断。

现有 Spec023 `ToolLoop`（`backend/app/skills/tool_executor.py:274–347`）是对话 Tool Loop，具有普通消息历史和最多轮次语义；不能未经适配直接当成研究 AgentRun。Spec034 也必须保持 Spec023 已确认的“整批 Tool Call 先校验、非法批次一个都不执行”和 `think=False` 经验（`backend/app/skills/tool_executor.py:1–23`、`docs/sdd/retro/2026-09-11-spec023-skill-tool-management.md`）。

**建议 T-05**：冻结 `ResearchAgentRunner.run(AgentRunInput) -> AgentRunOutput` 及可注入 ModelClient/ToolExecutor 接口；为五种结构化输出给出 JSON Schema/语义约束；定义一次 attempt、一次模型循环、一次 Tool Call 的计数；定义失败/重试/升级的创建链、成本记账、检查点哈希、取消后的写入屏障和迟到结果拒绝条件。明确 Coordinator 是否进入 Runner（见需求评审）。

### 4. Skill/Tool Registry 与授权快照 — 高风险

Spec034:47、51–57 要求新增五个 Skill、固定版本/hash、Role/Capability Registry 和计划版本授权，但没有定义 Registry 的唯一事实源和快照读取 API。Spec023 的 Skill 是磁盘 `.agents/skills/*/SKILL.md`，Tool 是 `build_default_tool_registry()` 的代码注册；状态文件缺失/损坏默认启用（`backend/app/skills/service.py:20–40`），这与“批准时可执行快照”需要的审计语义不同。

**建议 T-06**：明确 Skill snapshot = name + schema_version + content_hash + body/不可变引用 + enabled 结论，Tool snapshot = registry name + parameter schema hash + enabled + side-effect class；批准和每次 AgentRun 均保存快照。状态文件损坏、Skill 被删、Registry 版本漂移、未来新增 Tool 的行为必须分别有拒绝/保留旧快照的测试。

### 5. ProcessingStep v2、投影与迁移 — 阻塞

现有会话库 `processing_steps` 的基线表在 `backend/app/memory/repository.py:345–354`，并已有 `logical_sequence`/唯一索引迁移（`:481–550`）；当前 API 在 `backend/app/api/routes_conversations.py:890–892` 返回现有扁平结构。Spec034:153–168 只列新增字段，没有 schema version、迁移 SQL、索引/唯一性、父节点同消息校验、旧 v1 映射和删除/回滚顺序。

`ResearchEvent` 的主键是 `(research_task_id,event_seq)`，而 `source_event_id` 是字符串；没有冻结 canonical ID（例如 `research-event:<task>:<seq>`）。投影“失败后重试”也没有队列、重放入口、attempt/错误状态或同一 `node_key` 的更新规则。

**建议 T-07**：Task02/07 先冻结 additive migration、`(message_id,node_key)` 与 `source_event_id` 唯一语义、canonical event ID、父链校验算法和 v1→v2 输出；明确 projector 的持久化顺序、重试/恢复触发、失败不回滚 ResearchEvent 的证据。用乱序、重复、孤儿、跨消息和三层以上样本做合同测试。

### 6. Artifact / Notification / 报告下载 — 高风险

Spec034:135–151 把两种实体混为一个标题，未定义 Artifact 与 Notification 的表边界、任务/版本唯一性、通知目标和 `read_at` 的竞态。Spec034:253 的下载端点也没有 Content-Type、Content-Disposition、大小上限、路径/`storage_ref` 白名单和 owner 校验契约。

**建议 T-08**：拆分实体和表；冻结 `research_task_id + report_version + artifact_type` 唯一性、Markdown 是源且 HTML/manifest 同版本不可变、最终消息幂等 key、通知 seq/游标/已读 CAS；下载只能按 artifact ID 查询数据库对象，不接受任意路径，并为 Markdown/HTML 指定安全响应头和 XSS 清理验收。

### 7. 预算、资源、取消与恢复 — 部分通过，需精化

Spec034:181–193 的数值（Run 40/160、Task 160/640、最多三次扩容、20% 余量、6 小时上限）完整，但尚未定义这些额度由哪个事务计数、多个 AgentRun 链如何汇总、扩容批准与 `continued_from_agent_run_id` 的唯一性，以及限额与模型不可用/取消的优先级。

现有 `ResourceProbe` 在 `backend/app/platform/ollama.py:373–445` 已定义 `/api/ps`、显存占用、20%余量和失败→单 Worker；Spec034 应复用该接口，不再造一套资源计算。现有实现无驻留模型时会诚实降为单 Worker（`:391–417`），应纳入真实 Smoke 的环境诊断。

**建议 T-09**：给出预算记账表（Run 链、Task、Tool 副作用分别如何累计）、扩容请求/拒绝/批准状态、并发领用锁粒度、取消写屏障以及启动审计标记 interrupted 的幂等条件；规定限额错误码到 WorkItem/Session 状态的唯一映射。

### 8. 检索安全、来源复用与论文注入 — 基本通过

Spec034:195–202、271–290 继承 Spec027 的本地优先、硬范围不可突破、阈值有界软化、零结果诊断和论文内容不可信；Spec032.1/033 的 USENIX 解析器 fail-closed、PDF URL 白名单和摘要/作者来源约束在既有评审中已验证。技术上可行，但必须把 `search_paper_catalog`/`fetch_paper_detail` 的实际 Registry 参数映射冻结（T-01），并把恶意论文/ToolResult/模型输出的注入测试绑定到具体计划、权限和 Tool 快照。

## 附录 C、第一轮执行配置与任务拆分审计（历史）

- Spec034:339–345 的上下文上限（架构师 200k，其余 32k）与 `MODEL_REGISTRY.md:20–35` 的本地模型登记名匹配：`qwen3.8:27b-mlx`、`qwen3.5:9b` 均由 `ollama list` 实测存在。
- 但 `AGENTS.md` 的当前角色表声明现有 `.codebuddy/agents/*.md` 的 `model:` 实际统一为 `hy3`，而 Spec034 执行配置写的是 qwen 名称；这会造成“产品模型配置”“研发子代理分派模型”“模型库登记”三者含义混淆。不得在 Spec 中把临时研发子代理模型写成产品 Runtime 规则。
- Spec034:341 的架构师模型只有“自身”，未采用 Gate Checklist 要求的“自身（当前执行任务的 Agent，不写死模型代号）”审计措辞。
- Task02–10 的端拆分总体合理（backend/frontend 分离、Task07/08 依赖关系无环），但 Task02 依赖不存在的 Task01 文件；Task03 的 Q90/Q91 引用也无法定位。

**建议 T-10**：在 Spec 中明确两套配置：研发角色分派模型按 `MODEL_REGISTRY.md`/当前 agent 实际可用性记录，产品 Runtime 只保存 `resolved_model`；修正架构师审计措辞；修正 Task01/Q90/Q91 链接后再允许 Gate 2。

## 附录 D、第一轮技术门禁放行条件（已关闭）

以下全部完成后复审，之前保持 NO-GO：

- [x] 冻结 Role/Capability Registry 与 Spec023 Tool/Skill 的真实参数、版本/hash、授权快照映射。
- [x] 冻结 Session/Intake/Approval/AgentRun/Artifact/Notification 状态机、命令 payload、CAS/唯一性和错误映射。
- [x] 冻结 ResearchAgentRunner 的 ModelClient/ToolExecutor/Schema/attempt/预算/检查点/取消协议，明确与旧 Orchestrator 的单一执行权。
- [x] 冻结 ProcessingStep v2 migration、canonical `source_event_id`、projector retry 和 v1 兼容合同。
- [x] 冻结 Task06 的真实 CatalogSearchGraph/来源注入路径，证明默认路径不恒定空结果。
- [x] 修正 Task01、Q90/Q91 和执行配置审计口径；补齐可重复 Fake/真实 Smoke 契约。

## 附录 E、第一轮验证命令与退出码（历史）

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `git status --short --branch` | 0 | 当前为 `feature/spec-034-conversational-research-runtime`，评审前无业务改动 |
| `ollama list` | 0 | `qwen3.8:27b-mlx` 与 `qwen3.5:9b` 实际存在 |
| `rg -n 'Q90|Q91' docs/sdd/specs/034... docs/sdd/plans/034` | 0（无命中） | Task03 依赖引用未定义 |
| `rg -n 'class (CatalogSearchGraph|ResourceProbe)|build_default_tool_registry|processing_steps' backend/app/...` | 0 | 核对现有复用接缝和基线 schema |
| `find docs/sdd/plans/034 -maxdepth 2 -type f -print` | 0 | Task02–10 文件均存在；未找到独立 Task01 文件 |

本次未运行 pytest、服务或 Smoke，因为 Spec 尚未确认且任务要求本轮只做只读门禁评审；不存在“测试通过”的实现结论。

## 当前复审决策

**GO**。技术文档契约达到实现门禁要求；在用户明确确认前，继续保持 Spec034“待确认”、Task02–Task10“待执行”，不得修改业务代码或模型注册。
