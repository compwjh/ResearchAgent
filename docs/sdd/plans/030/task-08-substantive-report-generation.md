# Task 08：后端实质报告生成与质量门禁

关联：Spec 030 2026-10-29 修订；依赖 Task 07 合同评审通过。旧 Task 04/06 继续保持已完成，不覆盖其验收材料。
状态：待 Gate 2 技术复审通过后分派实施；产品范围已确认。

## 目标

沿自然语言主路径产出一份可追溯的五篇论文综述；在发布正式报告前，服务端校验合同中的有界结构、选集/Evidence 映射、计数与预算。人工语义结论由 Task10 rubric 评审，机器校验不得声称证明其通过。未达标时保存 partial/draft 诊断，不把旧目录卡片 fallback 写成正式报告。

## 角色和文件边界

- backend-dev：只改 backend/** 和对应 tests/research/**。
- backend-reviewer：只审 backend/**，单独落盘评审结论。
- backend-tester：只运行后端当前 Task 的定向 pytest/静态检查，不运行前端或全量回归。
- architect：仅维护领域合同文档 .agents/skills/research-report-synthesis/SKILL.md；动笔前按触发规则读取 docs/sdd/SKILL-AUTHORING.md。不得代 backend-dev 写后端代码。

## 最小实现方案

1. 按质量合同实现 versioned `report_content` schema 与 bounds，扩展 `ReportSynthesisOutput`、`Orchestrator._build_synthesis_matrix_context`、AgentRuntime allowlist/prompt 和服务端验证。服务端从当前批准 selection/plan、`ClaimEvidence` (`research_claim_evidence`) 建立 paper/evidence/source-level 映射；只接受当前 task/plan 的 available Evidence ID。fulltext 经现有 `EvidenceMatrixService.read_matrix` 验证 locator，并匹配同一 claim/task 的 `EvidenceUpgrade` document/chunk provenance。只传实际可用的 catalog/abstract/fulltext evidence；无有效 fulltext ID 时忠实声明摘要/目录等级，不用 candidate/document ID 相等关系猜测全文。
2. 机器校验只核结构：五篇批准选集分析且每篇至少一条可用 Evidence；每个 Evidence ID 属于当前 task/plan 并映射到声明的 paper；dimension 在批准计划中；至少一项比较涉及两篇；三项发现各由至少两篇不同论文支持；renderer 正文达到 1,500 CJK；schema、边界、状态和 Artifact 内容一致。`quality_validation` 只写这些确定性结果。摘要/目录来源等级由 Evidence 派生，未知用显式 not_stated/unavailable，不能扩写成全文方法或实验细节。
3. 具体 API 执行链：现有 POST 路由保留请求体 `{plan_version?,report_version?,title}` 和 202。自然语言主流程与 POST 重生成共用 `ResearchStore.reserve_report_generation`：自然语言路径在 `Orchestrator` dispatch synthesis WorkItem 前分配 request_key/report_version 并覆盖当前错误地使用 plan_version 的输入；POST 使用相同原子逻辑。session-backed 请求进入现有 `synthesize_preliminary_report` task_type/role、ResearchStore、Orchestrator、AgentRunner 与 ReportSynthesisService。每个 report_version 对应一个 WorkItem row：初次自然语言流程使用已有 queued/running synthesis item；completed item 不回退，后续版本创建同 task_type/role 新 row。后续 report-only 分支由 `ResearchService` 现有 ThreadPoolExecutor 提交到 Orchestrator 执行，不重开 completed/partial ResearchTask、不新增 executor/queue/Runner/endpoint。启动恢复扫描 generating reservation：queued item 由同一 executor 提交；stale running item 先按现有 lease/retry 状态恢复；若原 WorkItem 已被 task-recovery 标为 terminal interrupted，则创建同 task_type successor row 绑定同 reservation。响应保留原字段并补 `quality_status,published,reason_codes,report_url`，受理态为 generating/pending/false。无 ResearchSession 时保留当前同步矩阵 renderer，但结果为 matrix_api draft/unvalidated/unpublished。GET `/reports/{version}?format=json|markdown|html` 保留路径/格式，可读取草稿和真实状态；404/406 与既有行为一致；版本冲突/已有生成新增 409 `REPORT_VERSION_CONFLICT`/`REPORT_GENERATION_IN_PROGRESS`。
4. 原子预留和幂等：新增 `ResearchStore` 单事务方法，在同一 SQLite `BEGIN IMMEDIATE` 中按 task+UUID `Idempotency-Key` 查 reservation；若不存在且无 generating 版本，则计算 max(ResearchReport, ResearchArtifact)+1 并插入 generating ResearchReport 槽，同时绑定已有 queued/running synthesis WorkItem 或新建一行相同 task_type/role、依赖已完成计划/证据节点的 queued WorkItem，将 request_key/report_version/report_id 写入其 input。不得调用非原子的 `next_report_version()` 完成“分配+插入”。复用现有 `UNIQUE(research_task_id,report_version)` 仲裁并发；同 key 返回/续跑当前 report_id/version/work_item_id；不同 key 在当前版本生成中返回 `REPORT_GENERATION_IN_PROGRESS`；生成结束后用户新 key 才创建新版本。若 interrupted WorkItem 已是终态，恢复 successor 继续同一 report_id/version/request key，generation.work_item_id 更新为当前 row，所有 AgentRun IDs/预算/revision 保留。Generating 槽只可条件推进，终态之后不可变，无 schema migration。显式 report_version 与 reservation 不匹配返回 `REPORT_VERSION_CONFLICT`。
5. 崩溃恢复必须覆盖：reservation 后同一 WorkItem/checkpoint 继续；若已有 terminal interrupted row 则创建同类型 successor 绑定相同 reservation；AgentRun 已有完成 output 时复用 output；canonical JSON 已写但 Artifact 未写时确定性重渲染并按 task/version/type 校验 hash 后补齐；Artifact 已写后创建同 key pending 会话消息；pending message、三类 Artifact 齐备后推进 published marker，再把同一 message 标 completed、幂等补通知。Generating期间 artifact list/download 隐藏该版本，且不发 completed 消息/通知。任何阶段恢复都不新开 report_version、不重置 revision/call/elapsed；启动恢复使用现有 `ResearchService` executor，不开第二执行器。
6. 统一预算账本：初稿、AgentRuntime schema retry、最多 2 轮定向改写、恢复沿用同一 reservation 和 ResearchTask 持久预算，不请求 extension。每 run 40 model loops/160 tool calls；ResearchTask 总上限 160 loops/640 calls/5,400 活跃秒（包括报告前已有 AgentRuns），每 run usage 记入 report_totals，ResearchTask 持久用量写 task_totals。恢复时以旧 counters 初始化 BudgetSnapshot；达到任一 task cap 或 revision_count=2 停止。generation 按合同记录逐 AgentRun loops/calls/elapsed 与 report/task totals；tokens/cost 不可得为 null。schema retry 消耗预算但不增加 revision_count。每个阶段追加安全 ResearchEvent，不写 prompt/输出。
7. 实际执行可观测：`generation.path/output_disposition/provider/model/fallback_reason_code/agent_run_ids` 由 AgentRunner 返回的结构化结果与已持久输出写入；不通过 AgentRun ID 形状、Artifact 或 completed 事件猜测模型输出被接受。先持久 canonical ResearchReport，再产出 Markdown/HTML/manifest；所有 Artifact 和会话最终消息都派生同一 canonical report_version。已发布标记最后提交；notification 使用现有幂等键。

## 主要变更面和定向验证

预期后端文件：`backend/app/api/routes_research.py`（报告 POST/GET、session artifact list/download）、`backend/app/research/application/report_generation.py`（session dispatch、canonical create/read）、`report_synthesis.py`（schema/validation/投影）、`orchestrator.py`（WorkItem input/report_version、`_build_synthesis_matrix_context` 与 report-only branch）、`agent_runtime.py`（prompt、schema、实际分支/usage）、`evidence_matrix.py`（只复用现有验证，不预期改规则）、`research_service.py`（同一 ThreadPoolExecutor 提交/启动恢复）、`backend/app/research/infrastructure/research_store.py`（reservation、WorkItem row 与 generating 条件推进、event）。报告行与 Artifact 唯一约束已存在，沿 report_json/WorkItem 增量使用现有字段，不加 SQL 列/表。若核实需 migration 才可达到上述事务语义，暂停实现并交 architect 复审，不私自扩展。

围绕现有能力扩展 `tests/research/test_report_synthesis_contract.py`、`test_report_generation.py`、`test_agent_runtime_contract.py`、`test_research_report_matrix_bridge.py` 及精确 API/store 测试。至少证明：schema 必填/枚举/长度/总字节边界；1,499/1,500 CJK；标题/目录/引用/ID/附录不计；选择集和 evidence→paper→level/provenance 映射；五篇无比较、无三项支持发现；重复/越界 ID、目录/摘要不支持全文细节；fallback 不发布；两轮与 40/160、160/640、5,400s cap；相同 key 返回同版本、新 key 创建新版本；并发 reservation 唯一；reservation/model output/canonical/Artifact/message/published/notification 各崩溃点可幂等恢复；Artifact list/download 隐藏 unpublished；所有终产物同 version/hash；旧报告下载 hash 不变。只跑后端当前 Task 定向验证与受影响静态检查。

## 失败处置、回滚和完成条件

主要实现风险是现有 ResearchService whole-task worker 与 ResearchTask/WorkItem terminal state 不允许直接重开 completed/partial/interrupted 项。解除方式已限定为使用同一 ThreadPoolExecutor 和同类型 WorkItem 的 report-only dispatch/successor，不改变 ResearchTask 状态，不增加队列或执行器；若实测无法在这条接缝实现，则报告架构阻塞，不绕过状态机。

任一机器门禁失败都 fail closed：保留诊断草稿，旧版本不变，不发成功消息。reservation 冲突、fallback 被标正式、重试重置预算、unpublished artifact 可下载、事件泄漏模型输出或 report JSON/Artifact 内容分叉均为阻塞；backend-dev 在当前 Task 修复后由 backend-reviewer 复审。回滚关闭正式发布门禁并恢复上一部署版本；保留已写草稿/产物用于恢复，不删历史记录。

Task08 结束需有后端交接报告（命令、退出码、通过数、失败/阻塞、run/version 证据）、后端 reviewer PASS 和 backend-tester PASS。真实自然语言端到端、全量回归、部署及用户人工步骤留给 Task10；本 Task 不标 Spec 完成。

## 二轮门禁补充（主会话代行纯文档）

预算与公开status严格引用质量合同“二轮P1最小修订”的唯一公式/优先级状态表，覆盖本Task前文partial/draft概括。测试必须包含600/1500/2700 profile剩余量、历史阶段用量、report-only新版本不重置、失联耗时未知保守扣减及并发余额；POST/GET/恢复按同一映射断言，预算耗尽有正文/无正文、证据不足与其它缺项并存均覆盖。此修订不改产品范围，待原独立评审复核。

2026-10-29执行状态：实施中；用户确认，独立需求/技术GO，首先分派质量schema/确定性校验及对应精准测试。
