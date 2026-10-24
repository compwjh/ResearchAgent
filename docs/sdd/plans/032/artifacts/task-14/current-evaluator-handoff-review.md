# BLOCKED — evaluator handoff fix 独立后端复审

复审角色：`backend-reviewer`  
复审范围：`current-evaluator-handoff-fix.md`、实际 `agent_runtime.py`/runtime 测试 diff、orchestrator 的 evaluator handoff 与 WorkItem terminal write-back。  
基线：当前工作树 HEAD `6bacc29`；未部署、未写生产数据、未修改业务代码。

## 结论

- P0：`0`。
- P1：`2`，本修复不能通过独立复审。
  1. source 绑定会把任意模型 source 值静默覆盖为唯一 server scope，不只规范化允许的 skill alias/approved source；unknown 或伪造来源没有 fail-closed。
  2. e1 `completed + NULL/无效 output_json` 仍有可达路径：AgentRunner 先把 WorkItem 标为 completed，orchestrator 后续语义校验/终态写回被宽泛 `suppress(Exception)` 包住；没有“输出持久化成功后才进入 completed”的不变量。
- 定向测试全绿不能抵消以上 P1，也不能把之前的 partial E2E 当作成功。

## 已确认的正确部分

### Server scope 的唯一来源解析

`_approved_search_source()`（`backend/app/research/application/agent_runtime.py:628`）只接受 `{usenix, dblp, all}`，会收集 `source_ids`、`sources`、`source` 三个 server-owned 字段：

- 同一唯一来源（例如 `source_ids=["usenix"]`、`sources=["usenix"]`）返回 `usenix`；
- `usenix`/`dblp` 冲突、多来源列表、unknown 值、非法类型返回 `None`；
- 不会从模型输出、Markdown、全局目录或 URL 猜来源。

这部分对真实 WorkItem scope 是 fail-closed 的，候选 ID、`source_refs`、search handle 和 provenance allowlist 没有被此 diff 放宽。模型 source alias 为 `usenix-catalog-orchestration` 的正常真实形状可以绑定回批准的 `usenix`，解释了当前 fix 能覆盖之前 s2 的 skill-name 泄漏。

### allowlist / provenance 没有被整体绕过

`_validate_output()` 仍先运行 `validate_safe_scope()`、`source_refs` 结构校验、角色必需字段校验和 search candidate normalization；orchestrator 仍在 evaluator 阶段使用 Search Worker 的 recalled candidate/source allowlist 做 `_validate_evaluator_scope()`。当前 diff 只添加 server scope 参数并传入 runtime，未新增来源、candidate 或报告旁路。

## P1-1：source 归一化过宽，覆盖 unknown/伪来源

实际 diff 在 `agent_runtime.py:1585-1593` 的行为是：只要 server WorkItem 能解析出唯一批准来源，就无条件执行 `result["source"] = approved_source`。它没有先判断模型给出的 source 是否为：

- 批准的 source ID；或
- 明确允许的该 role skill alias（本场景为 `usenix-catalog-orchestration`）。

只读无文件探针（调用同一 `_validate_output`）得到：

```text
approved scope = {source_ids: [usenix], sources: [usenix]}
model source                         normalized result
usenix-catalog-orchestration         usenix
usenix                               usenix
dblp                                  usenix
unknown                               usenix
```

因此真正的 `dblp`/unknown/伪造字符串不会暴露为 invalid，也不会交给现有 orchestrator fail-closed；它们被伪装成 `usenix`。server scope 冲突本身虽然返回 `None`，但这一层没有对模型值做相应拒绝。现有新增测试只覆盖 skill-name alias 和 server input scope conflict，没有覆盖模型 source 为 `dblp` 或 unknown 的场景。

影响是 provenance/contract 违反被静默吞掉；在后续逻辑把 `source` 当作已验证绑定时，伪造输出可能被视为合法 handoff。即使 server source 最终仍是 usenix，系统也失去了识别模型越界/格式错误的 fail-closed 信号。

最小修复边界：保留 server-owned 唯一 scope 解析；仅当模型 source 等于允许的 skill alias或批准 source 时做规范化。模型 source 为 unknown、其它来源、非法类型或真正多来源冲突时，应返回 `AGENT_OUTPUT_INVALID`/未绑定状态，让既有 orchestrator 失败并保留真实错误。应增加 `dblp`、unknown、缺失/非法 alias 的回归测试；不放宽 candidate/source_refs/allowlist。

## P1-2：e1 completed + NULL output 的次生状态问题仍未封口

当前代码路径：

1. `ResearchAgentRunner._cancel(status="completed")` 通过 `_set_work_item_status()` 先把 running WorkItem 写成 completed，但此处只写状态，不写 `output_json`。
2. `orchestrator.py:1971-1985` 仍可能在 AgentRun 返回后发现 evaluator semantic scope 错误，将本次 `terminal` 改为 failed。
3. `orchestrator.py:2052-2069` 计算 `result.to_dict()` 后，用 `with suppress(Exception)` 包住 `update_work_item_status()` 与 worker event 写入。Store 的状态机只允许同一终态携带 payload；若当前已 completed 而 orchestrator 尝试 completed→failed，会抛非法状态转移并被吞掉。
4. 代码对序列化结果直接 `[:100000]`，没有 round-trip JSON、角色必需字段或“completed 必须有有效 output”校验后再允许终态。

这正与本次真实 supported-effort evidence 相符：e1 WorkItem `status=completed`、`output_json=NULL`；c1/syn 为 `UPSTREAM_WORK_ITEM_FAILED`；task terminal 为 `AGENT_OUTPUT_INVALID`/partial。source fix 能消除已知的 skill-name source mismatch 路径，但没有建立通用的 terminal persistence invariant。任何新的 semantic mismatch、terminal race、序列化失败或写回异常仍可能留下 completed + NULL/无效 output，并且不产生可观察关键错误。

最小修复边界：让 semantic validation 和 output round-trip 完成后再提交 completed，或新增现有状态机允许的明确 finalization 事务；禁止 broad `suppress(Exception)` 隐藏 terminal write-back 失败。至少应补一条回归：AgentRunner 已将 evaluator WorkItem 置 completed、orchestrator 随后 scope 校验失败时，最终状态/错误/output/event 必须一致，不能 completed + NULL；另覆盖超长/非法序列化不会进入 completed。

## 真实证据对照

`current-research-e2e-supported-effort-evidence.json` 的 task `2761a22515d5509d8e846debd7a05df5` 提供了本问题的真实运行事实：

- qwen3.5:9b/low Intake、计划批准、5/5 acquisition 都成功；
- e1 AgentRun completed，但对应 WorkItem `output_json` 缺失；
- c1 与 syn `UPSTREAM_WORK_ITEM_FAILED`；
- task terminal `AGENT_OUTPUT_INVALID`、status partial；
- matrix `MATRIX_NOT_READY`，canonical JSON/Markdown/HTML 均 `REPORT_NOT_READY`。

该证据没有被本复审改写，也没有把 artifact/item 元数据当作报告成功。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_runtime_contract.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_agent_selection_persistence.py tests/research/test_research_agent_approval_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | 93 passed in 3.58s |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_search_handle.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `_approved_search_source` conflict/unknown 无文件探针 | 0 | server scope 冲突/unknown 均返回 None |
| `_validate_output` alias/dblp/unknown 无文件探针 | 0 | 三者均被覆盖为 usenix；确认 P1-1 |
| `data/research/research.sqlite3` 只读 WorkItem/AgentRun shape 查询 | 0 | 复核 e1 completed、output_json 缺失、checkpoint 存在 |

## 复审裁决

**BLOCKED / P1 待修复。** 当前 fix 对已知 `usenix-catalog-orchestration` → `usenix` 的真实 handoff 方向正确，且定向测试通过；但 source 归一化过宽，且 terminal output persistence 仍允许 e1 completed + NULL/无效 output 的次生状态。修复并补回归后，需独立 reviewer 再审，再用全新部署/run 验证 c1/syn 正常、matrix 非空、canonical 报告真实可读；不得重试旧 task 或放宽来源/matrix 校验。

复审日志：`/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261009-053652.md`

## Latest remediation review — 2026-10-09 06:00

本节只复审 evaluator-handoff 最新 P1 修复的实际 diff：
`agent_runtime.py` 的 source binding、`orchestrator.py` 的 AgentRun completion/write-back、
`tests/research/test_agent_work_item_completion.py`。WorkItem hydration/recovery 仍是
独立未完成切片；本节不把它计为通过，也不扩大本次复审范围。

### Source binding：本次 P1 已满足要求

`_validate_output()` 现在只有以下两种来源路径：

- 模型 source 等于唯一 server-owned approved source ID；
- 模型 source 等于实际绑定的 `search_skill_name`，且该 skill alias 在显式注册表中映射到同一 approved source。

approved scope 缺失/冲突/多来源/unknown、模型返回 `dblp` 或 `unknown` 而 approved 为
`usenix`、skill snapshot 名不匹配 alias，均进入 `AGENT_OUTPUT_INVALID`；不会再无条件把
任意模型 source 覆盖成批准值。现有定向测试覆盖 alias、冲突、`dblp`、`unknown`，此项复审通过。

### Completion/write-back：主路径通过，但仍有一个 P1 残留

正向确认：

- AgentRunner 完成 AgentRun 后不再提前把 WorkItem 写成 completed；WorkItem 保持 running，
  由 orchestrator 在语义校验和 JSON 序列化后通过现有 store transaction 写入终态与 envelope。
- evaluator provenance 失败走 running → failed，并保存 `status=completed` 的 AgentRun
  envelope；不再尝试 completed → failed。
- terminal output store 写失败不再被 broad `suppress(Exception)` 吞掉；探针确认异常可见，
  WorkItem 保持 running 且无 payload。

但 `orchestrator.py:2114-2147` 仍存在恢复路径回写 NULL 的问题：当 AgentRun 返回
`status="completed"` 且 `output_json` 非 mapping 时，代码先设 `terminal="failed"`，随后若
`_recover_search_worker_output()` 从 CatalogSearchAdapter 得到候选，又把 `terminal` 改回
`completed`。最终写入的仍是原始 `result.to_dict()`，其 `output_json` 为 `null`，于是再次产生
WorkItem `status=completed` + envelope inner `output_json=null`，没有满足“invalid running→failed
有 envelope”的不变量。

无生产写入临时 SQLite 探针（AgentRun `completed`/`output_json=None`，adapter 返回
`paper-1`/`trusted-search`）实际得到：

```text
task result partial AGENT_OUTPUT_INVALID
search-worker completed None {"...", "status": "completed", "output_json": null, "..."}
```

该路径会让下一次 hydration 拒绝该行，但本次仍把无有效输出的 WorkItem 标成 completed，正是
本修复试图消除的 completed+NULL 次生状态。最小修复应禁止“completed AgentRun 的 invalid
output”进入 Search recovery，或用 recovered output 构造完整一致的成功 envelope；更安全的是
保留 running → failed 并持久化明确失败 envelope。不要通过 reopen 已完成行或 broad suppress
隐藏该错误。

### 定向验证与裁决

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_work_item_failure_visibility.py --maxfail=1` | 0 | `12 passed in 1.28s` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_work_item_completion.py tests/research/test_agent_runtime_search_handle.py` | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_work_item_completion.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 临时 adapter 探针：completed + null output 触发 Search recovery | 0 | Search WorkItem 仍为 `completed` 且 inner `output_json=null`，确认残余 P1 |

**最新裁决：BLOCKED / P1 残留。** Source binding 的两个旧 P1 已修复，正常 semantic
failure/write failure 主路径通过；但 Search recovery 仍可把 invalid completed output 重新提升为
completed+NULL。需补回归并修复后再独立复审；WorkItem hydration/recovery 仍不得视为通过，且
未进行部署或真实 E2E。

## Latest completion/null fallback remediation review — 2026-10-09

复审角色：`backend-reviewer`  
复审范围：本报告对应的最新 completion follow-up、实际
`orchestrator.py`/`agent_runtime.py` diff、`test_agent_work_item_completion.py`；只审
AgentRun → WorkItem terminal handoff。Search tool-results 完整性属于 recovery 的独立
切片，本轮不纳入，也不把本切片结果冒充整体验收或真实 API E2E。

### 结论

- P0：`0`。
- 旧的 null-recovery P1 已关闭：invalid `AgentRunOutput` 不再被独立 adapter recovery
  重新提升为 completed；terminal store 写失败可见；正常 runtime completion 先有
  validated output/checkpoint，再返回 completed AgentRun。
- P1：`1`（本轮发现的 durable binding 残余）：新鲜成功路径对 Search 的 runtime-owned
  `work_item_id` 只做内存 canonicalize，却把原始 `result.to_dict()` 写入 WorkItem。
  如果模型返回非真实 ID，WorkItem 可能先显示 completed、输出非空且 hash/checkpoint
  属于 AgentRun，但重启 hydration 会因 inner `work_item_id` 不等于 WorkItem ID 而拒绝，
  形成不可恢复的 terminal success。该问题不同于已关闭的 null fallback，但仍阻止本
  handoff 切片整体签字。

### 已确认通过的 completion 语义

1. **成功必须来自 runtime 的真实完成路径**：`ResearchAgentRunner` 在返回 completed
   前已通过 `_validate_output()`，写入 canonical output hash，创建并持久化最终
   checkpoint，保存 AgentRun counters/hash，随后将真实 AgentRun 更新为 completed。
   `_cancel(status="completed")` 不再提前把 WorkItem 写成 completed；WorkItem terminal
   commit 由 orchestrator 在语义检查和 envelope 序列化后执行。

   临时 SQLite 的真实 `ResearchAgentRunner + FakeModel` probe 显示 Search 行：

   ```text
   AgentRun status=completed
   output_hash=<非空>
   checkpoint_ref/checkpoint_hash=<均非空>
   WorkItem output_json=<非空>
   ```

   本 probe 的 Evaluator 因故意 out-of-scope candidate 失败，整任务为 partial；不能把
   该 probe 解释成完整研究成功。

2. **null/invalid output 保持 WorkItem failed**：当 AgentRun 返回
   `status=completed, output_json=None` 时，orchestrator 将 terminal 改为 failed，设置
   `AGENT_OUTPUT_INVALID`，不调用 `_recover_search_worker_output()`，不创建伪造
   AgentRun、hash、source handle，也不 reopen 已完成 WorkItem。临时 probe 实际为：

   ```text
   task=partial / AGENT_OUTPUT_INVALID
   WorkItem=failed / AGENT_OUTPUT_INVALID
   persisted envelope.status=completed, envelope.output_json=null
   orchestrator_created_agent_run=false
   ```

   envelope 保留的是 runtime 返回的真实 completed AgentRun 结果；成功语义由
   WorkItem status 决定，不能将这条失败记录当作成功产物。

3. **terminal store transaction 可见**：`update_work_item_status(..., output_json=...)`
   不再被 broad `suppress(Exception)` 包裹。写失败会向调用方抛出，WorkItem 仍为
   `running` 且没有 payload；不会静默报告 completed，也没有 completed→failed 的非法
   reopen。

### P1：canonical output 未写回 durable envelope

`orchestrator.py:2202-2208` 对 Search `normalized_output` 调用
`_canonicalize_search_worker_binding()`，但后续 `output_json` 仍由原始
`result.to_dict()` 序列化（`orchestrator.py:2294`）。因此真实 runtime probe 中，模型
返回 `work_item_id="model-owned"` 时得到：

```text
WorkItem id = <task>:s1
WorkItem status = completed
persisted inner work_item_id = model-owned
inner output_hash == recomputed hash(model-owned output) = true
AgentRun status = completed
AgentRun output_hash = same model-owned hash
checkpoint_ref/checkpoint_hash = non-empty
```

当前运行内存中的 `completed_outputs` 使用了 canonical WorkItem ID，所以一次 fresh pass
可以继续；但下一次 hydration 的 `valid_runtime_binding()` 要求 inner ID 等于持久
WorkItem ID，必然拒绝这条 completed row。该证据来自真实 `ResearchAgentRunner` 临时
SQLite probe，不是只读 Fake runner 的断言。

最小修复边界：不要在 orchestrator 直接改 output 后伪造 hash/AgentRun。应在
`ResearchAgentRunner` 完成 hash/checkpoint 前绑定 runtime WorkItem ID，或在 handoff
时检测模型 ID 不符并按既有 `AGENT_OUTPUT_INVALID` 失败；若确需 canonicalize，必须
在同一持久事务中更新 output、hash、checkpoint 与 AgentRun，不能只改内存投影。补一条
模型返回非真实 WorkItem ID 的成功/重启回归即可验证。

### 定向验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py --maxfail=1` | 0 | `5 passed in 0.92s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_agent_work_item_failure_visibility.py --maxfail=1` | 0 | `59 passed in 2.34s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_selection_persistence.py tests/research/test_research_agent_approval_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | `52 passed in 3.02s` |
| `.venv/bin/ruff check` changed runtime/orchestrator/focused tests | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile` changed runtime/orchestrator/focused tests | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check` | 0 | 通过 |
| null completed + recovery adapter probe | 0 | WorkItem `failed`，无伪 AgentRun/hash，恢复 helper 未提升成功 |
| terminal store write failure probe | 0 | 异常可见，WorkItem `running` 且无 payload |
| real ResearchAgentRunner completion probe | 0 | AgentRun completed、hash/checkpoint/output 非空；整任务仍因故意 evaluator 越界而 partial |
| model-owned Search ID persistence probe | 0 | **复现 P1**：fresh WorkItem completed，但 durable inner ID 与 WorkItem ID 不一致 |

本轮未修改业务代码、未部署、未创建或批准研究任务、未写生产数据、未运行全量测试。
所有探针使用临时 SQLite；source tool-results integrity 和 WorkItem hydration 仍由独立
报告负责。

### 复审裁决

**BLOCKED / P1 待修复。** 最新修复已正确关闭 null recovery promotion、伪 hash/AgentRun
和 terminal store write suppression 的主路径；但 fresh Search handoff 的 canonical
ID 没有写入 durable AgentRun envelope，导致成功行无法通过自身的 restart binding。先
修复该 durable binding（不伪造 hash/AgentRun），再独立复审；source tool-results、hydration
完整性与真实 API E2E 不纳入本轮通过结论。

## Completion-ID 最终独立复审（2026-10-09 06:37 +0800）

复审角色：`backend-reviewer`。本轮只复审最新 completion-ID / AgentRun handoff
修复，并把此前已通过的 checkpoint/tool_results hydration 作为联合回归；不把它扩大为
真实 API E2E、报告产物或 Spec032 整体验收。completion-ID 修复已落在工作树的
`agent_runtime.py`、`orchestrator.py` 与对应研究领域测试中，本轮未修改业务代码。

### Runtime 身份与持久化 hash

- 对所有非 planner role，`AgentRunInput.work_item_id` 是 server-owned 身份；
  `_validate_output()` 在 role 归一化和 hash 计算前绑定该 ID。模型返回的
  `model-owned` 不再进入 durable output；`research_task_id`、`research_session_id`
  或 `owner_id` 若显式返回且冲突则 fail-closed 为 `AGENT_OUTPUT_INVALID`，不做静默
  改写。
- Search 的 handle/source-ref 与 detail-degraded 标记发生在初次 validation 之后，
  但其后重新计算 inner `output_hash` 并写回 output；同一 canonical output 被写入
  checkpoint，AgentRun counters 保存同一 hash/ref。因而 inner output、返回值、
  checkpoint 与 AgentRun 不再漂移。
- 实际 `ResearchAgentRunner + FakeModel + FakeTool + SQLite` 正向路径验证了模型给出
  非 server ID 时，AgentRun 仍为 `completed`、inner/top hash 相等，checkpoint 与
  AgentRun work-item/session/task/owner 绑定一致；terminal write 后新 Orchestrator
  hydration 不调用 runner，rerun=0。

### Orchestrator、source alias 与失败语义

- 当前 `_run_agent_work_items` 主 handoff 已删除 Search 的临时 ID rewrite，并把同一
  server identities 传入 hydration validator；不通过 validator 的 completed envelope
  不会被提升为成功。
- 私有 `_recover_search_worker_output()` 中仍保留旧的 `_canonicalize_search_worker_binding`
  辅助函数，但当前主 handoff 不再调用 recovery promotion；测试也明确要求合法
  AgentRun 不调用它。它是未用于 terminal completion 的历史私有 seam，不构成当前
  completion-ID P1；若后续要求彻底删除死代码，可单独做非功能性清理。
- `usenix-catalog-orchestration -> usenix` 仅在显式注册 alias 且批准 scope 唯一时
  归一化；`dblp`、`unknown`、冲突/多来源 scope 仍拒绝。此前 source-alias 与
  source-conflict 回归保持通过。
- `completed + output_json=null` 仍保持 WorkItem failed，并保留真实 AgentRun envelope；
  不再由 orchestrator 的 adapter recovery 伪造 completed。terminal store 写失败
  仍向上抛出，WorkItem 保持 running 且无 payload，不 reopen terminal 行。

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_work_item_completion.py tests/research/test_work_item_output_recovery.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_research_agent_approval_contract.py tests/research/test_agent_selection_persistence.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | `120 passed in 4.68s` |
| completion-ID/source/null/atomic/checkpoint 精选回归 | 0 | `9 passed, 57 deselected in 1.53s` |
| `.venv/bin/ruff check` runtime/orchestrator/相关定向测试 | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile` 同上 | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check` | 0 | 通过 |

### 最终裁决

- P0：`0`。
- P1：`0`，completion-ID handoff 与此前 checkpoint/tool_results hydration 联合切片
  通过：fresh → terminal → restart 能恢复且不重跑；source alias、冲突身份、null
  output、atomic terminal write 的失败语义均未回退。
- 本结论不代表生产部署、真实 API E2E、报告产物或 Spec032 全部完成；未部署、未写
  生产数据、未重试历史任务、未运行全量测试。
