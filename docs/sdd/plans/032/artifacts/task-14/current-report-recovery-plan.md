# Spec032 Task14：P1-A 报告恢复最小接线方案

> 角色：backend-dev（只读接线审计）  
> 时间：2026-10-08（Asia/Shanghai）  
> 分支：`codex/spec032-final-acceptance`  
> 状态：**分析完成；实现边界已收敛，未修改生产代码**

本轮只读取恢复审计、Spec032 的报告/恢复语义、现有 Research 与论文 issue 路由、报告/证据服务和前端工作台。没有调用用户数据写接口、没有上传/登录/重试、没有创建任务或报告、没有修改 `.env`，也没有提交 git。

## 1. 结论：修正 P1-A 的语义和归属

Spec032 的用户语义是“论文修复后**提示用户生成**报告新版本，旧报告不改写”，不是上传、登录或 retry 路由自动生成报告。因此，`routes_paper.py` 不应在 issue action 内直接调用生成/投递服务；`upload` 返回的 `report_action="generate_new_version"` 应继续作为用户动作提示，而不是伪装成已排队或已完成。

当前证据将缺口分成两层：

| 契约 | 当前证据 | 判定 |
|---|---|---|
| 修复后提示用户 | `routes_paper.py:1405-1409` 返回 `report_action`；`frontend/research-tasks.js:1796-1801` 只写提示文本 | **P1：前端缺少显式“生成报告新版本”按钮和调用** |
| 用户点击后创建新版本 | `POST /api/research-tasks/{task_id}/reports` 已存在（`routes_research.py:1655-1680`），调用 `ReportGenerationService.generate()`；`next_report_version()` 与 `save_research_report()` 为 insert-only | **已有后端接缝可复用** |
| 旧报告不变 | `ResearchStore.save_research_report()` 拒绝同版本冲突；`next_report_version()` 同时检查 `research_reports` 与 `research_artifacts` | **已满足局部契约** |
| canonical session artifacts / final message / notification | 现有 `/reports` POST 只经过 `ReportGenerationService`；没有调用 `ReportDeliveryService`，而 `ReportDeliveryService` 才写 `research_artifacts`、会话 final message 和 notification | **若最终验收要求 artifact/session 投影，仍有条件性 backend P1** |
| 修复后的全文证据进入报告 | upload 只写 `ResearchDocumentLink` 和 `AcquisitionEvent`；`EvidenceMatrixService.read_matrix()` 只读取已持久化 Claim/Evidence/Cell，fulltext 还要求既有 `EvidenceUpgrade` | **不能声称“上传即报告已更新”** |
| 仍在执行的任务只续跑受影响步骤 | `_refresh_issue_links()` 只读 `acquisition.status()`；`Orchestrator` 主链先交付报告再自动导入，`ResearchTask` 终态不可回到 running | **当前没有专用的受影响步骤续跑接缝** |

所以原 `current-recovery-audit.md` 关于“upload 路径没有实际生成新 artifact”的事实判断成立，但“修复路由应自动生成”的隐含方向不符合本次用户语义。最小修复的首要归属是 frontend-dev；canonical artifact 要求若属于收口硬门槛，再由 backend-dev 补现有服务之间的接线，而不是扩大为新的报告系统。

## 2. 已核对的现有链路

### 2.1 论文修复路由只负责导入和状态投影

- `backend/app/api/routes_paper.py:1255-1265` 的 `_refresh_issue_links()` 为关联 task 读取 `ResearchAcquisitionService.status()`，没有启动 Research runner。
- `:1267-1298` 的 login/resume/retry 记录 `ManualResolution`、刷新 issue，仍没有生成报告。
- `:1347-1412` 的 upload 复用 canonical KB 上传；成功后写 `ManualResolution`、`ResearchDocumentLink(status="completed")` 和 `AcquisitionEvent(phase="upload")`，关闭 issue，并返回 `document_id`、`research_task_ids`、`report_action`。没有调用 `ReportGenerationService` 或 `ReportDeliveryService`。

这正好符合“修复完成后给用户下一步提示”的后端职责，不应在这里隐式产生新版本。

### 2.2 既有用户触发报告入口能生成 immutable ResearchReport

`backend/app/api/routes_research.py:1655-1680` 的既有 POST 契约只有 `plan_version`、`report_version`、`title`，`extra="forbid"`。省略 `report_version` 时，`ReportGenerationService.generate()`（`backend/app/research/application/report_generation.py:216-247`）执行：

1. owner/task 校验；
2. `EvidenceMatrixService.read_matrix()` 读取指定计划版本；
3. 通过 `ResearchStore.next_report_version()` 取新版本；
4. `ReportSynthesizer.synthesize_evidence_report()` 生成内容；
5. `save_research_report()` insert-only 保存 `ResearchReport`。

返回值已有 `report_id`、`plan_version`、`report_version`、`status`、`limitations`，所以前端可直接复用该接口，不需要新增公开字段或新 endpoint。旧版本可继续由同一版本 GET 读取，重复使用已占用版本会得到稳定冲突。

### 2.3 `/reports` 与 canonical Delivery 是两条已有但未相连的投影

`backend/app/research/application/report_synthesis.py:563-674` 的 `ReportDeliveryService.deliver()` 才会：

- 按同一 `report_version` 创建 Markdown/HTML/citation manifest `ResearchArtifact`；
- 校验 `generated_by_agent_run_id` 必须是同 task 的 synthesizer run；
- 写幂等的 `research-report:{task_id}:{version}` activity message；
- 更新 Session `final_message_id` 并发出 notification。

但是当前 `/reports` POST 没有 `ReportDeliveryService`，`application/entry.py` 只是导出它，没有为该 POST 装配或调用它。因此“POST 成功”目前证明的是 `research_reports` 行已创建，不证明 `GET /api/research-sessions/{id}/artifacts` 有新 artifact，也不证明会话投影/通知已更新。

此外，`ReportDeliveryService` 消费 `SynthesisResult`，而 `ReportGenerationService` 产出的是 evidence report dict；不能在路由里强行把两种结果拼接，也不能使用未绑定的伪 synthesizer run 绕过 `create_artifact()` 的外键约束。

### 2.4 “修复后全文证据”不是 upload 的隐式副作用

`backend/app/research/application/evidence_matrix.py:160-258` 只验证/读取持久化矩阵。`ResearchDocumentLink` 完成并不自动创建 ClaimEvidence；`EvidenceMatrixService` 对 `fulltext` evidence 还会校验既有 `EvidenceUpgrade` 的 document、hash、manifest generation、fingerprint 和 chunker。故而用户点击新报告前，若目标是让新 PDF 支持全文结论，仍须沿现有 evidence-upgrade → matrix → report 语义产生可验证证据；不能把上传动作本身报告为“已纳入结论”。

### 2.5 续跑边界

`backend/app/research/application/orchestrator.py:1778-1831` 在 agent 路径先调用 `ReportDeliveryService`，随后 `:1866-1879` 才调用批准计划自动导入并把任务收敛为 `completed/partial`。`Orchestrator.run()` 对终态任务直接返回，`TASK_TRANSITIONS` 也禁止 `partial/completed/failed/... → running`。因此：

- 不应在 issue route 中调用完整 `Orchestrator.run()`，那会重新走全链路，或对终态任务立即返回；
- 当前 route 没有“只续跑受影响 WorkItem”的公开应用方法；
- 若任务尚未终态，后续 backend 修复必须复用现有持久 WorkItem/依赖和 runner，只重新安排受影响的证据/报告步骤，不重做来源检索、候选评估或已完成导入；
- 若任务已终态，用户显式点击既有 `/reports` 是“从已持久化矩阵生成新版本”的安全路径；若要把新文档变成全文证据，先走既有 EvidenceUpgrade/矩阵契约。

## 3. 最小分派边界

### 3.1 frontend-dev（首要、无 backend 生产改动）

只改 `frontend/research-tasks.js`、必要的 `frontend/index.html`/样式和前端契约测试：

1. 当 upload 返回 `report_action="generate_new_version"` 时，保留现有提示并渲染显式“生成报告新版本”按钮；按钮绑定 `result.research_task_ids` 中当前 task（或当前 `selectedTaskId`）。
2. 点击按钮才调用既有 `POST /api/research-tasks/{task_id}/reports`，请求只传已知 `plan_version`（不传 `report_version`，让后端分配下一个版本；标题沿用默认）。上传函数本身不得隐式调用该 POST。
3. 对按钮做单飞/禁用和稳定错误提示；成功读取返回的 `report_version`，再复用已有 `loadReport()`、版本选择器和 artifact/session 读取刷新。失败时保留旧报告和原提示，不清空旧版本。
4. 不新增 endpoint、请求字段、outbox、报告缓存或第二套状态机。若当前 POST 只返回 `ResearchReport`，UI 要明确显示“报告版本已生成/等待 artifact 投影”，不能把缺失 artifact 当成功。

对应前端测试应补充：按钮确实调用既有 POST、upload handler 本身不调用 POST、旧版本选择器仍可读取；沿现有 `tests/frontend/test_paper_issue_ui_contract.py` 领域命名，不使用 spec/task 编号。

### 3.2 backend-dev（仅在 canonical artifact 属于收口硬门槛时分派）

不改 `routes_paper.py` 的自动行为，也不新增公开接口。只在既有 `/reports` 用户触发链的 application service 内补最小组合：

1. 继续使用 `next_report_version()` **一次**分配版本；同一版本同时绑定 `ResearchReport` 和（若会话存在且该能力已要求）`ReportDeliveryService` 的 artifact/message/notification，旧版本不得 update。
2. 复用已有 `EvidenceMatrixService`、`ReportGenerationService`、`ReportSynthesizer`、`ReportDeliveryService` 和 owner/session/task 绑定；不能在 issue route 拼接内容，不能用任意字符串冒充 synthesizer run，不能绕过 artifact hash/immutable 检查。
3. 复用现有 Orchestrator 已有的 synthesizer WorkItem/run 绑定或增加同一 application 层的受控适配，不新建 outbox、schema、数据库表、第二套报告服务或新 API。若现有 runner/WorkItem 无法安全提供该绑定，应先报告为阻塞，不以伪 artifact 代替。
4. 对仍在执行的 task，只使用现有 durable WorkItem 依赖续跑受影响的 evidence/report 节点；不得从 issue action 重新搜索、扩大候选、重跑已完成节点或把终态 task 强行改回 running。
5. 上传后只更新已有 document link/event；只有用户点击“生成报告新版本”才允许报告写入。若没有可验证的 ClaimEvidence/EvidenceUpgrade，应返回既有 `EVIDENCE_INSUFFICIENT`/`REPORT_NOT_READY` 语义，而不是生成无依据的新结论。

建议后端定向测试放在既有领域：

- `tests/paper_discovery/test_paper_issue_recovery.py`：确认 upload/resume/retry 不自动调用报告生成；upload 仍返回提示 token。
- `tests/research/test_report_recovery_versioning.py`：用户触发后只插入 v+1，v1 内容/hash 不变；重复同版本内容幂等/冲突遵循现有 immutable 合同。
- `tests/research/test_report_synthesis_contract.py` 或同领域新增测试：若启用 canonical delivery，v+1 的 artifacts、Session final message 和 notification 使用同一版本和 owner 绑定。

如果验收只要求 `ResearchReport` 版本行和可下载的现有 `/reports/{version}`，则 backend-dev 不需要本轮改生产代码，frontend-dev 的既有 POST 接线就是最小修复；如果验收明确要求 Session `artifacts[]`、final message 和 notification，则上述 application-level backend 接线是必要的 P1，不能由前端单独掩盖。

## 4. 不需要 schema 变化的结论

在当前用户语义下，不需要改变 `ResearchReportRequest`、`report_action`、`ResearchReport`、`ResearchArtifact` 或 issue DTO：

- `report_action` 已表达“下一步生成”，不是完成状态；
- POST 请求已经有 `plan_version`，报告版本可由服务端安全分配；
- `ResearchStore` 已有 insert-only report/artifact 和 owner/version 约束；
- Session artifact 下载、版本读取和旧报告读取接口均已存在。

唯一需要确认的是现有 `/reports` 入口是否必须同时写 canonical artifacts。若是，优先扩展既有 application service 的内部组合，不在 API 层新增字段；若现有 runner 绑定无法复用，应把该能力标为阻塞并由架构师决定是否修订范围，不能擅自造 schema 或伪造产物。

## 5. 验证结果与后续验收

本轮定向只读测试：

```text
.venv/bin/python -m pytest tests/paper_discovery/test_paper_issue_recovery.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py -q
退出码 0；46 passed in 2.32s

.venv/bin/python -m pytest tests/frontend/test_paper_issue_ui_contract.py -q
退出码 0；3 passed in 0.19s
```

这些测试证明既有 issue 状态、immutable ResearchReport、artifact delivery 合同各自成立，但没有证明“issue 修复 → 用户点击 → v+1 artifact/session projection”集成链；当前报告不把它们拼成 E2E 成功。

下游独立 review/实现后的验收应使用新的 `run_id`：先验证修复路由只产生提示且旧版可读，再由用户点击按钮触发既有 POST；记录 `report_version`、旧版 hash、新版 `ResearchReport`/artifact ID、Session artifact 路径和通知。没有新 artifact 时只能报告“ResearchReport 已生成、canonical artifact 未接通”，不得冒充 Spec032 全 E2E 通过。

## 6. 交接状态

- 生产改动：无。
- 预算修复：未修改、未覆盖。
- 推荐首个实现角色：`frontend-dev`，接通现有 POST 的显式用户动作。
- 条件性 backend-dev：仅为 canonical artifact/session projection 和受影响步骤续跑补既有应用服务接线；不自动生成、不新建 schema/outbox/接口。
- 当前收口：**P1-A 仍需前端接线；canonical artifact 要求下 backend 接线仍阻塞**。本报告不把它误报成已完成，也不把“提示”误报成“自动报告成功”。

## 7. Backend 架构接缝复审（2026-10-08，backend-reviewer）

本节只审查“用户明确生成新版本”后的后端接缝；未修改业务源码、未写入生产数据，也未评审未完成的 batchservice 改动。审查对象为本计划、`ReportGenerationService`、`ReportDeliveryService`、`EvidenceMatrixService`、`routes_research` 现有 reports 入口及其直接契约测试。

### 7.1 结论先行

- **P0：0。** 没有发现需要立即阻断所有报告读取/生成的安全或数据破坏问题。
- **现有 ResearchReport 版本链：PASS（有边界）。** 用户显式调用现有 `POST /api/research-tasks/{task_id}/reports` 时，服务端可从持久化 Evidence Matrix 读取内容、通过 `next_report_version()` 分配新版本并 insert-only 保存 `ResearchReport`；旧版本不被改写。
- **“新 PDF 全文内容进入报告”：条件性可行。** 上传 PDF 本身只形成 document link/acquisition event；必须先有通过校验的 `EvidenceUpgrade`，再由既有矩阵写入可引用的 fulltext `ClaimEvidence`/Cell，报告读取该矩阵后才有资格声称使用了 PDF。不能把 upload 成功等同于报告已升级。
- **canonical session artifact：当前仍为 P1 阻塞。** 现有 `/reports` 入口不调用 `ReportDeliveryService`，因此不会自动产生 `ResearchArtifact`、session `final_message_id` 或 notification。不能用任意字符串、旧 run 或 `_synthesis_run_id()` 伪造 `AgentRun` 绕过 `create_artifact()` 的真实 synthesizer-run 约束。
- **“报告本身生成 PDF”：不属于当前接口能力。** 现有 canonical artifact 类型与下载入口只覆盖 markdown/html/citation_manifest；若验收文字中的“新 PDF”是指报告 PDF 文件，而不是 PDF 论文的全文证据，则必须单独修订接口、artifact 类型、媒体类型和渲染契约。

### 7.2 最小可实施路径（不扩大已确认 Spec032）

1. **保留当前显式用户动作。** upload/recovery route 只返回现有 `report_action="generate_new_version"` 提示；不在 upload、issue refresh 或 retry 中隐式调用报告生成。用户点击既有按钮后，继续调用现有 `/reports`，请求只带已支持的 `plan_version`（前端不传 `report_version`，让服务端安全分配下一个版本）。
2. **先满足证据前置条件。** 上传后沿现有 document-link → `EvidenceUpgradeService` → evidence-matrix 契约处理。只有升级状态、文档 ID、source hash、manifest generation/fingerprint、chunker 与 chunk IDs 均通过验证，并且对应 fulltext ClaimEvidence/Cell 已写入矩阵，才允许新报告引用该 PDF 内容；否则沿既有 `EVIDENCE_INSUFFICIENT`/`REPORT_NOT_READY` 语义返回，不静默生成无依据结论。
3. **生成并保留新版本。** `ReportGenerationService.generate()` 读取矩阵，调用 `next_report_version()` 一次，渲染并 `save_research_report()`。同一任务的旧 `ResearchReport` 只读保留；重复使用已占用版本继续遵循现有 immutable 冲突/幂等约束。该路径不需要新增 request 字段、公开 endpoint、表或第二套状态机。
4. **若本轮只要求 ResearchReport。** 以上就是最小 backend 路径；前端显示“报告新版本已生成”并刷新已有 JSON/Markdown 读取即可。不得把“无 artifact”显示成“会话报告交付完成”。
5. **若必须有 canonical artifact/session 投影。** 只能复用现有真实 agent 运行链：为本次新版本安排一个与 task/session 绑定的真实 synthesizer WorkItem，由现有 `ResearchAgentRunner` 产生真实 `AgentRun`，再把经验证的 `SynthesisResult` 交给 `ReportDeliveryService.deliver()`，由它创建 markdown/html/citation manifest、activity、final message 和 notification。若现有 runner/WorkItem 无法为终态任务安全重排受影响的 synthesis 节点，应先报告阻塞，不用伪 artifact 代替。
6. **不要把两个输出类型硬拼。** 当前 `ReportGenerationService` 的 deterministic evidence-report dict 与 `ReportDeliveryService` 消费的 `SynthesisResult` 不是同一契约。必须由架构师选择并确认：要么扩展已有 synthesis contract 使真实 agent 能消费并输出已验证的 matrix/fulltext 内容；要么正式扩展 artifact provenance，允许受控的 deterministic matrix renderer 作为生成者。两者都会改变现有报告合成/产物语义，不能在 route 层 cast 或拼字典规避。
7. **续跑仅限现有 durable 节点。** 对仍在执行的 task，只复用已有 WorkItem/依赖重新安排受影响的 evidence/report 节点；不重新搜索来源、不扩大候选、不重做已完成导入。对 `partial/completed/failed` 等终态，不能调用当前 `Orchestrator.run()` 期待其自动续跑，也不能强行把任务状态改回 running；终态用户路径应是“证据准备完成后显式生成新版本”。

### 7.3 已确认范围与需再次确认的接口界线

**在当前已确认 Spec032 范围内，可以直接采用：**

- 复用既有 upload、evidence-upgrade、evidence-matrix 和 `/reports` 入口；不新增公开请求字段。
- 通过服务端 `next_report_version()` 创建新 `ResearchReport`，保持旧版本 immutable、可按原版本读取。
- 把 `report_action` 当作下一步提示，而不是“报告已生成”状态；显式按钮才触发报告 POST。
- 复用既有 `EvidenceUpgrade`、ClaimEvidence/Cell、owner/task/session 绑定和现有错误/冲突语义。
- 不新建 PDF 仓库、下载器、Planner、报告合成器、outbox 或第二套下载/状态机。

**以下任一项都必须先由架构师修订/再次确认 Spec032（或新 spec），再实现：**

- 在 `/reports` 请求中新增 `document_id`、`evidence_upgrade_id`、自动续跑开关、异步 job ID、状态查询/轮询字段或新 endpoint。
- 自动把一个上传文档映射为所有 claim/question 的 fulltext evidence；当前没有无界且可验证的这种映射接缝。
- 为终态 task 增加 resume/reopen 状态迁移，或让 issue route 直接启动第二次 Orchestrator 全链路。
- 让现有 synthesizer agent 输出全文发现、修改 `SynthesisResult`/agent prompt 的来源语义，或新增 WorkItem/AgentRun schema/role。
- 允许 deterministic matrix renderer 伪装成 synthesizer 生成 artifact，或放宽 `create_artifact()` 的真实 AgentRun 校验。
- 增加 PDF report artifact 类型、PDF renderer、下载路由、媒体类型、artifact schema 或 session artifact contract。

### 7.4 验证证据与剩余风险

本轮只读定向测试：

```text
.venv/bin/python -m pytest -q tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_evidence_matrix.py tests/research/test_fulltext_evidence.py tests/paper_discovery/test_paper_issue_recovery.py
退出码 0；53 passed in 1.81s
```

这些测试分别覆盖版本生成、delivery 合同、矩阵/fulltext 校验和 issue recovery；没有覆盖“issue 修复 → 用户显式点击 → fulltext matrix → 新版本 → canonical artifact/session message/notification”的集成链。因此当前可部署结论必须拆开：**ResearchReport v+1 路径可复用；canonical artifact/fulltext 一键升级路径不可宣称已完成，仍是 P1（无真实 AgentRun 或接口边界决定前不部署为收口能力）。** 实现后至少应补一条同一 task、同一新版本、旧版 hash 不变且 artifact/session 投影一致的定向集成测试，再由最终验收执行真实 API E2E。
