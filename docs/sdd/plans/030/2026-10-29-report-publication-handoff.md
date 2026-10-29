# Spec 030 Task08 正式报告发布接缝调查与最小方案

日期：2026-10-29  
范围：先完成只读调查，再记录本报告投递服务的限定实现。首次调查阶段只新增本报告；实现与验证记录见文末，未触及 Orchestrator、Store、routes、schema、queue、部署或 Git。

## 结论

当前实现已能将 machine-quality pass 的 `report_content`、`quality_validation` 与 generation provenance 写入预留的 `ResearchReport`，并能在应用层确定性渲染 Markdown/HTML；但这条路径在返回 `REPORT_DELIVERY_PENDING` 后没有正式发布接缝。现有 `ReportDeliveryService.deliver` 面向旧 candidate-level `SynthesisResult`，一次性把三类 Artifact、终态消息和通知写完，消息与通知发生在 canonical publish CAS 之前，不能直接用于正式报告。

最小实现应沿用同一 reservation 与 report_version，在既有 Orchestrator 质量通过点插入可恢复的两阶段投递：先用 canonical JSON 和受校验 Evidence context 重渲染；核对/补齐同版本 Markdown、HTML、citation manifest Artifact；以固定 idempotency key 创建 `pending` 最终消息。确认这些行都已持久后，调用既有 `update_report_generation_state` CAS 写 `stage=published,status=completed,published=true`；随后把同一消息改为 `completed`，最后以固定幂等键发 completed notification。恢复入口必须先识别已有 canonical pass reservation，并补做/重放投递，不能再调用模型或分配新 report_version。

## 可复用符号与行为

| 位置 | 可复用能力 | 当前边界 |
|---|---|---|
| `backend/app/research/application/report_generation.py:370` `render_report_payload` | `report_content-v1` 固定 renderer；先重新做机器质量校验，返回 canonical `report`、Markdown、HTML | 结构化正文需要从当前已校验 task/plan/Evidence matrix 重建 `ReportQualityContext`；调用方须传 reservation 的 report ID/version。 |
| `backend/app/research/application/orchestrator.py:4129` `_build_report_quality_context` | 从当前 task、plan、冻结选集、持久 Evidence matrix 重建正文质量上下文 | 需保留 reservation WorkItem 的已验证 `validated_candidates`；它校验 task/plan/version 关系，但不要求 WorkItem 必须是 running。 |
| `backend/app/research/application/orchestrator.py:4456` `_generate_report_quality_body` | dispatch 前验证 reservation、WorkItem、owner/task/plan/report version；预算 claim/settle；最多两轮修改；成功后 canonical CAS | 只负责生成和 canonical JSON 写入，不创建 Artifact/消息/通知。通过后状态仍是 `generating`，返回 `REPORT_DELIVERY_PENDING`。 |
| `backend/app/research/infrastructure/research_store.py:7145` `update_report_generation_state` | 既有 CAS stage/status/published/reason_codes；completed 要求 published stage、quality pass、`path=agent_runner`、`output_disposition=accepted`；同状态重放幂等，终态不可变 | CAS 不跨 SQLite 和 MemoryRepository 验证 Artifact/消息是否存在；上层必须先读回核实三 Artifact 和 pending 消息，再推进 publish CAS。helper 会保留 `store_state` 的 claims/limits/预算 ledger。 |
| `backend/app/research/infrastructure/research_store.py:4485` `create_artifact`、`:4567` `list_artifacts_for_task` | owner/task/version 约束下创建和查找三种 Artifact；既有唯一键是 task/version/type | `list_artifacts_for_task` 当前不依据 canonical `published` 过滤；API 层 list/download 也没有该过滤。 |
| `backend/app/memory/repository.py:967` `create_activity_message`、`:990` `get_activity_message`、`:1029` `update_message` | 固定 key `research-report:{task}:{version}` 对一条 assistant activity 幂等创建；可以先 `pending`，之后更新为 `completed` | `update_message` 本身可把终态改回 pending，publisher 必须读当前状态并只允许 pending→completed 或接受已 completed 的精确重放，不能回退消息状态。 |
| `backend/app/research/application/report_synthesis.py:742` `ReportDeliveryService.deliver` | 当前 legacy 路径已有 Artifact hash 冲突检测、并发唯一插入后回读、消息内容冲突保护、会话 final_message link、通知幂等创建 | 本函数把 artifact 内容取自旧 `SynthesisResult`，消息直接写成 completed/partial/failed，然后立即发通知；citation manifest 序列化为旧候选引用 list，与 canonical renderer 的 manifest object 不同。不能直接承接正式版本。 |
| `backend/app/research/application/report_synthesis.py:856` `ReportDeliveryService.notify` / `ResearchNotificationService.emit` | 复用 owner-scoped `ResearchNotification` 写入；相同 notification idempotency key 可重放 | completed 发布通知应只含 report_version、三 Artifact ID、message ID 等安全字段，不应把旧 summary limitation prose 复制进正式通知。 |

## 建议的最小调用契约

1. **发布资格**：从 owner/task-scoped reservation 读取同一 `ResearchReport` 与其 WorkItem；核对 `report_id`、`research_task_id`、`owner_id`、`plan_version`、`report_version`、`request_key`、WorkItem ID/输入绑定。报告必须仍为 `generating`，`quality_validation.status=pass`，`generation.path=agent_runner`，`output_disposition=accepted`；只接纳同 reservation 的已保存正文。任何身份不符或重渲染失败都 fail closed，保持 unpublished。
2. **重渲染 canonical body**：读取当前已批准 plan、validated selection、持久矩阵和 canonical `report_content`，用 `render_report_payload` 再验证和渲染。Artifact 内容只能取此结果：`markdown`、`html`、`json.dumps(rendered["report"]["citation_manifest"], sort_keys=True, separators=(",", ":"))`。消息正文等于同一 Markdown。不得从旧 candidate-level fallback、模型原始输出或 `SynthesisResult` 拼正式内容。
3. **Artifact phase**：复用 `list_artifacts_for_task` 按 task/version/type 查找。三种预期内容分别 SHA-256，与已有 Artifact hash 相同则复用，内容冲突则报告稳定失败并保持 `published=false`；缺失时调用 `create_artifact`，并在并发冲突后回读比较 hash。`generated_by_agent_run_id` 绑定 `generation.agent_run_ids` 中实际产生最终正文的末次 drafting/revision run，不使用 plan_version 或 synthesis run 猜测。
4. **pending-message phase**：以 `research-report:{task}:{version}` 调 `get_activity_message`/`create_activity_message(status="pending")`，验证原有消息内容一致；保留同一 message ID，并写 `ResearchSession.final_message_id` link。此时不发 completed notification、不把消息标 completed。
5. **publish cutover**：确认三 Artifact 均存在且 hash 一致、同 key 消息存在且 status 为 pending 或已经 completed 后，用最新 `get_report_generation_budget` revision 调 `update_report_generation_state(expected_revision=..., stage="published", rewrite_count=..., status="completed", published=True)`。CAS 冲突时重读：如果 canonical 已是相同 completed/published 状态，则只继续补齐消息/通知；其他状态保持失败关闭。
6. **完成通知 phase**：publish CAS 成功后，把相同 activity message 更新为 completed；再以稳定 key（建议沿用 `research-report:{task}:{version}`）幂等写 completed notification，payload 仅含版本、Artifact IDs、message ID。此顺序允许崩溃后从 durable state 补齐后续阶段。
7. **恢复入口**：`_run_agent_work_items` 当前开头发现 latest report 为 generating 且已有 `report_content`/`quality_validation` 时，在约 `orchestrator.py:1395` 直接返回 `REPORT_DELIVERY_PENDING`。这里应先分流 `quality_validation.status=pass` 的 canonical reservation 到上述 publisher；不重新 dispatch AgentRunner、不 claim 新预算、不增加 version。若 CAS 已 completed/published，则仅幂等补齐 message/notification。当前 `get_report_generation_reservation(task, owner, request_key=...)` 可按 generation/request key 找回原 WorkItem；使用其已验证候选输入重建 context。

现有 Store CAS 只对 canonical report row 原子写入；Artifact Store 和 MemoryRepository 是分开的事务。因此不能声称整个流程原子。恢复正确性由以下已有约束组成：Artifact task/version/type 唯一、内容 hash 不可变；activity key 唯一；notification key 唯一；报告 publish CAS 是对客户端可见性的切换点。每一阶段都须读回、冲突时比较内容，并允许完全相同的重放。

## 需要修改的源码文件

- `backend/app/research/application/orchestrator.py`：将 canonical pass 的 delivery 调用放在 synthesis WorkItem terminal 更新前；delivery 未完成时保持 WorkItem 可恢复状态；在现有 generating+canonical-body 快速返回前添加恢复 publisher 分支。成功后把本轮质量结果从 delivery pending 更新为 completed/published，最终结果再正常收束。质量门禁失败、缺证据、legacy matrix/fallback 仍按现有状态表，不进入正式发布。
- `backend/app/research/application/report_synthesis.py`：将现有 `ReportDeliveryService` 的 Artifact、pending message、message completion、notification 操作拆成可独立重放的内部阶段，并保留 `deliver()` 旧行为作为兼容 wrapper。正式 publisher 的输入应为 canonical renderer 结果/版本绑定，不接受候选 synthesis envelope 作为正文权威。
- `backend/app/research/infrastructure/research_store.py`：为保持既有 `GET ...?format=markdown|html` 可读，扩展已有 `save_report_generation_output` CAS 在同一写入中保存 renderer 派生的 Markdown/HTML 到 `ResearchReport` 现有列；或明确改为从 canonical renderer 重新投影读取。推荐前者以保持读路径简单，但字段只能由经过同一 `report_content`/质量结果验证的 renderer 产生，且不新增列/表。发布阶段继续复用 `update_report_generation_state`，不再建 store 状态 API。
- `backend/app/api/routes_research.py`：session Artifact list/download 对存在 canonical report row 的版本，仅在 report `status=completed` 且 `generation.published is True` 时暴露；不存在 canonical report row 的历史 legacy artifact 保持当前兼容行为。download 必须先通过 session/task/owner，再核对该版本发布标志，防止绕过列表过滤猜 artifact ID 下载。

无需新增 queue、schema 或公开 endpoint。`report_generation.py` 主要复用 `render_report_payload`/现有 read；若 Store 同次 CAS 写回其现有 Markdown/HTML 列，read 函数可保持不变。

## 具体契约障碍 / 风险

- **现有 `deliver()` 顺序与正式合同相反**：它将消息设为终态并发通知，之后才有可能由外层写状态；若先调用再 publish，用户会看到未通过正式 canonical cutover 的完成事实。
- **当前恢复短路会使流程卡住**：canonical body 落库后下一次 orchestrator 调用直接返回 pending，没有重渲染/Artifact/message 补齐路径；而 quality helper 仅允许 WorkItem running。恢复 publisher 应单独完成读取和渲染，不复用会调用 Runner 的质量 helper。
- **canonical renderer 输出没有持久到报告 Markdown/HTML 列**：`save_report_generation_output` 只写 report_json；`ReportGenerationService.read(format="markdown"/"html")` 读这些列。因此单靠当前写入会让 GET 的 Markdown/HTML 为空。建议在同一 CAS 保存渲染结果，恢复时再次 render 并比对列/Artifact hash。
- **Artifact 对外读取没有 unpublished 过滤**：`routes_research.py:1091-1134` 直接按 task/list 或 artifact ID 返回内容。仅依赖 `published=false` 不能隐藏新写入 Artifact，必须在 list 和 download 均按 canonical report status/published 核对，同时不误隐藏历史 legacy artifact。
- **CAS 无法校验跨库前置条件**：`update_report_generation_state` 能确认 machine pass 和 generation provenance，但并不确认三 Artifact 或 pending message；只有 publisher 在 CAS 前检查这些对象，且在 CAS 后把 message/notification 作为可恢复尾阶段补完。
- **现有返回状态会先终结 synthesis WorkItem**：quality helper 的 pass 返回 `generating/REPORT_DELIVERY_PENDING`；`orchestrator.py:2437-2452` 会对此特定诊断放过“继续保持 WorkItem running”的 guard，随后提交 WorkItem completed。当前 `:1395-1415` 快速返回又不恢复 delivery。正式投递需调整为在 WorkItem 完成写回前调用阶段 publisher；在启动恢复短路中补足已保存 canonical pass 的 case。
- **当前 legacy fallback 会创建自己的 candidate-level 版本**：应确保 quality-enabled 正式分支不落入 `_run_pipeline`/`_deliver_synthesized_report` 或旧 `ReportDeliveryService.deliver` 的成功发布路径；fallback 仅可作为 unpublished 诊断材料，不能发 completed notification 或与 canonical report_version 混用。

## 建议的精准验证

实现阶段只运行新建/复用的 `tests/research/test_report_publication.py`（能力命名；覆盖 publisher 顺序、身份绑定、hash 冲突、消息/通知重放），扩展 `tests/research/test_report_synthesis_contract.py`（保证 legacy `deliver()` 兼容），以及现有路由测试覆盖 unpublished list/download 隐藏。重点断点应覆盖：三 Artifact 后崩溃、pending message 后崩溃、publish CAS 后消息仍 pending、消息 completed 后通知缺失；每次恢复均不得重复 Artifact、不得重跑模型/预算或改变 version，通知最终只一条。另验证非 pass、非 agent_runner、plan/report version mismatch、owner/task/WorkItem mismatch 不能 publish，`store_state` budget ledger 保持不变。

上述测试表为首次只读调查阶段的下游建议；实际执行结果记录在后续实现章节。

## ReportDeliveryService 两阶段接口（2026-10-29 20:39）

本轮按限定范围只修改 `backend/app/research/application/report_synthesis.py` 与新增能力测试 `tests/research/test_report_publication.py`；Orchestrator、Store、routes、schema 和 queue 未改。

Orchestrator 调用顺序：

```python
prepared = delivery.prepare_canonical(
    task=task,
    session=session,
    owner_id=owner_id,
    reservation=reservation,
    report=canonical_report,
    report_version=canonical_report.report_version,
    rendered=rendered,
)
# 调用方此时以最新 Store revision 执行 stage=published/status=completed/published=True CAS。
finished = delivery.finalize_canonical(
    task=task,
    session=session,
    owner_id=owner_id,
    reservation=reservation,
    report=published_result["report"],
    report_version=canonical_report.report_version,
    rendered=rendered,
    prepared=prepared,
)
```

`prepare_canonical` 重读 owner/task/session/report 与 request-key reservation，核对 report/plan/work-item/version 身份、质量 pass、`agent_runner/accepted`、renderer 的 report id/version/plan/content/quality 绑定，然后按 markdown、html、citation_manifest 顺序幂等创建/复用 Artifact。Artifact 内容按 UTF-8 SHA-256 和正文逐字比较；最终正文 Artifact 绑定 canonical generation 中最后一个 AgentRun ID。之后才创建 `research-report:{task}:{version}` pending activity 并更新 session final-message link。该方法不执行 publish CAS、不完成消息、不发通知，返回 Artifact/message IDs 和当前 message status。

`finalize_canonical` 会重读 report，并只接受已持久的 `completed + generation.published=true`；再次确认三 Artifact、准备回执和 pending activity 的内容/身份相同，再把 pending 消息更新为 completed，最后以同一个稳定 key 调用 `ResearchNotificationService.emit(completed)`。已 completed 的同内容消息、已存在的通知均可精确重放。消息已 completed 但报告还未 published 时，prepare fail closed；CAS 之前的所有读写失败都会留在 unpublished，调用方可用同 reservation/renderer 重试。

legacy `ReportDeliveryService.deliver()` 保持原签名和一次性投递语义，现有 candidate-level 调用方不必迁移。两阶段接口只提供服务层接缝；正式业务路径仍需 Orchestrator 在 Worker terminal commit 前调用 prepare、执行 publish CAS、再调用 finalize，并在 canonical pass 快速恢复分支复用这两步。Artifact list/download 的 published 过滤仍需按前节在 API routes 接入。

### 本轮定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_publication.py`（接口未实现时的初始 RED） | 1 | 11 failed：均因 `prepare_canonical` 尚不存在 |
| 同上（实现和扩展身份/顺序边界后） | 0 | 16 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py -k delivery` | 0 | 2 passed，33 deselected；legacy delivery 兼容 |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/report_synthesis.py tests/research/test_report_publication.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | test naming check passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_publication.py` | 0 | 16 tests collected |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/report_synthesis.py tests/research/test_report_publication.py` | 0 | 通过，无输出 |

能力用例覆盖三 Artifact 顺序/hash 和最终正文 run binding、task/owner/session/plan/report version 身份不匹配、非质量通过/非 AgentRunner 路径拒绝、完成消息早于 publish 的拒绝、Artifact 完成后 message 写失败的恢复、publish 后 notification 写失败的恢复、finalize/prepare 同版本重放，以及旧版本恢复不覆盖更新的 session final-message link。未改 Orchestrator 集成、API 可见性、报告 markdown/html 列持久化；这些是后续接缝，不能把本轮服务方法单独视作正式发布路径已上线。

## Session Artifact list/detail 类型一致性（2026-10-29 20:47）

后续 route 可见性补片将 `markdown`、`html`、`citation_manifest` 作为唯一可公开 Artifact 类型；session Artifact list 与 session detail 共享 `_visible_session_artifacts` 类型过滤，并与 download 的 allowlist 一致。该类型过滤同时适用于已发布 canonical 版本与无 canonical row 的 legacy 版本，因此 intermediate 等内部产物不会出现在列表/详情，即使其 canonical report 已 published；legacy 三种正式 Artifact 仍保持兼容。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| 新 list/detail 回归用例首次 RED（两个用例） | 1 | 2 failed：published intermediate 被 list/detail 返回 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_artifact_visibility.py` | 0 | 8 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check tests/research/test_report_artifact_visibility.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/api/routes_research.py tests/research/test_report_artifact_visibility.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | test naming check passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/api/routes_research.py tests/research/test_report_artifact_visibility.py` | 1 | routes 文件报告两条与本补片无关的现有诊断：import block 排序（第 33 行）和 SIM105（第 616 行）；测试文件单独 lint 通过 |

## Publication P1 评审修复（2026-10-29）

原 reviewer 在 `docs/sdd/reviews/030-report-publication-review.md` 记录的两项 P1 已由原作者按 RED→GREEN 修正，服务层方法签名保持不变。

1. **Canonical renderer 来源校验**：`prepare_canonical` 与 `finalize_canonical` 现在都会从 durable reservation WorkItem 的 `input_params.validated_candidates` 读取候选，并核对其均属于任务持久选集；再以 owner-scoped task/plan 的 `EvidenceMatrixService.read_matrix` 和持久 EvidenceUpgrade 重建 `ReportQualityContext`，调用固定 `render_report_payload` 从 canonical `report_content` 重渲染。机器质量字段与 canonical `quality_validation` 比较（revision_count按持久 store_state rewrite_count恢复）；传入渲染需与服务端重新生成的 report identity、citation manifest、Markdown、HTML逐项相同。三类 Artifact 的 hash 和正文只从服务端可信渲染结果计算， forged 任一产物会在写入 Artifact/message 前 fail closed。
2. **较新链接保护**：回放旧版本时先读取 session 当前 `final_message_id` 指向的实际 Memory Message，并验证 owner、conversation、assistant role、父 activity、状态和正文。再查找高版本 Markdown Artifact，要求它属于当前 task、版本更高、hash匹配其内容且内容等于当前 linked message；并要求该版本固定 activity key 查询到的 message ID/metadata 与当前链接一致。该保护不依赖高版本一定存在 canonical ResearchReport 行，因而覆盖 legacy N+1 Activity+Artifact；仍保留已有 canonical newer reservation 回归路径。

### 定向验证

| 命令/阶段 | 退出码 | 结果 |
|---|---:|---|
| RED：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_publication.py` | 1 | 4 failed、16 passed：Markdown/HTML/manifest forged 内容均被接受；rowless legacy N+1 link 被旧版本重放覆盖 |
| GREEN：同一 publication 测试文件 | 0 | 20 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py -k delivery` | 0 | 2 passed，33 deselected；legacy `deliver()` 行为通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/report_synthesis.py tests/research/test_report_publication.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/report_synthesis.py tests/research/test_report_publication.py` | 0 | 通过，无输出 |

修复只涉及 `report_synthesis.py`、`test_report_publication.py` 与本交接文档；没有改 Orchestrator、Store/schema、routes 或队列。本节不替代 Orchestrator 恢复入口集成测试或 route 可见性独立评审。
