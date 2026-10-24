# BLOCKED — WorkItem completed-output recovery 独立后端复审

复审角色：`backend-reviewer`  
复审范围：`current-work-item-recovery-fix.md`、`backend/app/research/application/orchestrator.py` 的 recovery diff、`tests/research/test_work_item_output_recovery.py`。  
基线：当前工作树 HEAD `6bacc29`；本轮未部署、未写生产数据、未修改业务代码、未运行全量测试。budget-agent 的 `agent_runtime.py`/completion 变更不在本复审范围。

## 结论

- P0：`0`。
- P1：`2`，当前 recovery fix 不能通过独立复审。
  1. Search 的恢复 allowlist 与 `source_search_id` 没有重新绑定到持久化的成功 catalog tool result；只要 completed envelope 和 inner 字段形状看起来合法，伪造 candidate/search handle 就能成为 evaluator allowlist 与选集来源。
  2. completed envelope 与非 Search/Evaluator 角色校验过宽：顶层 `schema_version` 可缺失，未校验 output hash/AgentRun 绑定；Critic/Synthesizer 分支只检查 runtime-owned 通用字段，任意结构化结果都可被当作已完成而不重跑。

定向用例证明 failed/null/malformed Search envelope 会被拒绝、不会解锁下游，且有效 completed Search/Evaluator 不会重复执行；这些绿灯不能抵消上述持久化证据边界问题。

## 已确认通过的部分

### 失败 envelope 与终态不重开

`_completed_output_envelope()`（`orchestrator.py:125-152`）会拒绝非字符串、非 JSON、`status != completed`、`output_json` 非 mapping，以及非法 `tool_results` 容器。恢复循环对无效 completed row 只加入本次内存 pass 的 `failed_ids`/`hydration_invalid_ids`，不调用终态回退或重开。

现有回归覆盖：

- failed envelope、null output、malformed JSON 都不能解锁 downstream；Search/Evaluator 原有 terminal 行保持 `completed`，queued Critic/Synthesizer 按 `UPSTREAM_WORK_ITEM_FAILED` 失败。
- 有效 Search/Evaluator hydration 后，runner 只收到 queued Critic/Synthesizer；已完成 Search/Evaluator 没有再次执行。
- 持久 evaluator 的 forged candidate/reference 会被现有 `_validate_evaluator_scope()` 拒绝。

### 有效来源快照字段会被保留

恢复后的 Search output 含 `search_id` 时，Synthesizer 分支会从 `completed_outputs` 建立 candidate → search handle 映射，并由 `_persist_agent_selections()` 写入 `ResearchPaperSelection.source_search_id`。只读临时库探针使用 `trusted-snapshot` 得到：

```text
result completed None; runner calls ['research_critic', 'synthesizer']
source_search_ids ['trusted-snapshot']
```

因此“已验证数据的 provenance 不丢失”方向正确；问题在于当前代码也会原样保存未验证的 handle（见 P1-1）。

## P1-1：Search candidate/handle 未与受控 tool result 重新绑定

恢复 Search 只校验 `queries` 是 list、`source` 在 `{usenix,dblp,all}`、`candidates` 是非空字符串列表、`refresh_diagnostics` 是 mapping（`orchestrator.py:1690-1705`）。它没有校验：

- 每个 candidate 是否出现在 completed envelope 中成功的 `search_paper_catalog` tool result 的 `catalog_paper_ids`；
- `search_id` 是否是安全的服务端 handle，是否与成功 tool result 的 handle 一致；
- `source_refs` 是否包含且只包含与该 handle 相符的 `search:<id>` 引用。

后续 evaluator allowlist 直接从恢复的 `Search.candidates` 生成，Synthesizer 的 `synthesis_candidate_sources` 也直接从恢复的 `search_id` 生成（`orchestrator.py:1973-1982`）。因此“persisted Search output 是唯一召回白名单”在恢复路径中变成了可伪造的 WorkItem JSON 自授权。

无生产写入的临时 SQLite 探针将 Search envelope 改为 `candidates=["forged-candidate"]`、`search_id="forged-snapshot"`，并让已完成 Evaluator 引用同一伪造 ID；tool result 没有该 catalog ID。实际结果：

```text
result completed None; runner calls ['research_critic', 'synthesizer']
selected_ids ['forged-candidate']
source_search_ids ['forged-snapshot']
```

这既不是“拒绝不在目录召回中的 candidate”，也不是仅保留真实 source provenance；后续 acquisition 会把伪造 handle 当作来源快照使用。最小修复应在 hydration 时从成功、结构化 catalog tool result 建立 candidate/handle allowlist，并要求 `search_id` 通过既有安全格式且与 tool result/source ref 一致；任一不一致应按 `AGENT_OUTPUT_INVALID` 失败传播，不能进入 evaluator、selection 或 acquisition。

## P1-2：completed envelope/角色合同过宽

`_completed_output_envelope()` 接受 `envelope.get("schema_version") is None`（`orchestrator.py:140-145`），且不验证 envelope 的 `output_hash`、`agent_run_id` 与对应 AgentRun，也没有对 tool result 数量/字段做实际 bounded/schema 校验。只读临时探针删除顶层 envelope `schema_version` 后仍得到：

```text
missing-envelope-schema accepted: completed None; runner calls ['research_critic', 'synthesizer']
```

更重要的是，Hydration 对 `research_critic`/`synthesizer` 进入通用 `elif valid` 分支（`orchestrator.py:1761-1767`），只要求 `work_item_id`、非空 inner `schema_version`、mapping `safe_summary`、字符串 `source_refs`；没有重新执行各角色必需字段/报告合同验证。临时 completed Critic/Synthesizer envelope 只含这些通用字段、无 `coverage`/`sections`/`citation_manifest`，仍被视为 terminal，runner calls 为 `[]`；带 delivery seam 时虽因没有可交付 Synth output 最终降级为 partial，但不是在 hydration 阶段拒绝该 malformed role output。

最小修复边界：要求已知 AgentRun envelope schema（至少严格 `runtime-v1`，或明确的兼容版本表），校验 envelope/output integrity 与 task/work-item/run 绑定；恢复 Critic/Synthesizer 时复用已有角色合同/报告校验，不满足则只做本次失败传播，不重开 terminal row。不要通过放宽字段、伪造 fallback 或重新执行已完成 WorkItem 来掩盖 invalid persisted output。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | `39 passed in 3.24s` |
| `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py` | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check` | 0 | 通过 |
| 临时 SQLite：可信 `search_id` provenance | 0 | `source_search_ids ['trusted-snapshot']`，保留正确字段 |
| 临时 SQLite：伪造 candidate + search handle | 0 | `forged-candidate`/`forged-snapshot` 被接受，确认 P1-1 |
| 临时 SQLite：缺失 envelope schema | 0 | 仍返回 `completed`，确认 P1-2 |

## 复审裁决

**BLOCKED / P1 待修复。** 本修复正确建立了“failed/null/malformed 不解锁下游、有效 terminal 不重复 dispatch”的骨架，也保留了有效 `source_search_id`；但 recovery 仍把持久化 Search candidate/handle 当作可信来源，且对 envelope/非搜索角色缺少完整性与合同校验。修复并补充 candidate↔tool-result、handle↔source-ref、missing schema/hash、critic/synth malformed 的回归后，需独立复审，再做一次全新部署验证；不重试旧任务、不放宽来源 allowlist、不修改 AgentRuntime 之外的范围。

复审日志：见 `.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/` 下本轮日志。

## BLOCK2 最新修复独立复审（2026-10-09）

复审角色：`backend-reviewer`  
复审范围：最新 `current-work-item-recovery-fix.md` 的 BLOCK2、实际
`orchestrator.py` recovery diff、`test_work_item_output_recovery.py`；只审
completed WorkItem hydration。`agent_runtime.py` 的 completion fallback 由另一
切片修复，本轮不纳入结论，也不把 hydration 通过解释为整条研究链通过。

### 结论

- P0：`0`。
- P1：`1`（残余）：Search envelope 的 `tool_results` 内容没有被 inner/outer
  `output_hash` 或对应 AgentRun 的 `output_hash` 绑定。若持久化 WorkItem JSON
  中只篡改成功 catalog tool 的 `catalog_paper_ids`，而不改变 Search inner
  output、inner/outer hash 或 AgentRun 行，当前 hydration 仍会把该候选当成真实
  catalog 召回并完成后续 Critic/Synth。因而本轮不能给 recovery 整体签字通过。
- 代码级修复声明的其余三项均复核通过：最终 hydration gate 要求
  `runtime-v1`、inner/outer hash、owner/session/task/work-item/role/skill 绑定的
  completed AgentRun；Search 的 candidate、handle、`search:<id>` ref 互相绑定；
  Critic/Synthesizer 经过现有 role output contract。

### 通过项与探针证据

1. **Envelope、hash 与真实 AgentRun 绑定**：实际代码在恢复进入
   `completed_outputs` 前重新计算 inner output hash，并同时比较 envelope hash、
   inner `output_hash`、真实 completed AgentRun 的 `output_hash`；还比较
   session/task/work-item/规范化 role/默认 skill。缺失 AgentRun、outer hash 篡改、
   inner hash 篡改、AgentRun work-item 错配、缺失顶层 schema 的临时 SQLite 探针
   均返回 `partial / UPSTREAM_WORK_ITEM_FAILED`，runner 没有执行下游角色。
   `_completed_output_envelope()` 本身保留了 `schema_version=None` 的兼容读取，
   但最终 hydration gate 明确要求 `runtime-v1`，因此当前入口没有绕过。

2. **Search candidate/handle/ref 边界**：Search 恢复只接受成功
   `search_paper_catalog` 结果的 `catalog_paper_ids` 子集，且要求唯一安全 handle、
   output `search_id`、output `source_refs`、`safe_summary.search_id/source_refs` 精确
   一致。此前伪造 candidate+真实 tool snapshot、handle/source-ref drift 的探针均
   返回 `partial / UPSTREAM_WORK_ITEM_FAILED`，没有 selections，也没有调用
   Critic/Synthesizer。

3. **Critic/Synthesizer role contract**：删除 Critic 的 `coverage` 或 Synthesizer
   的 `report_version` 后，completed terminal row 保持不 reopen；恢复不会把通用
   runtime 字段当成角色输出，且不会用 malformed 行解锁下游。两种 malformed 探针
   均为 partial，runner 没有重跑对应的已完成角色。

4. **正向 restart**：可信 envelope/成功 catalog tool/真实 AgentRun 的重启探针返回
   `completed`，runner 只调用 `research_critic, synthesizer`；Search/Evaluator
   没有重复调用，selection 为 `paper-1`，`source_search_id` 保留为 `search-1`。

### P1 残余：tool result 未纳入完整性绑定

复用临时 SQLite 夹具创建 Search output=`paper-1`、真实初始 tool result
`catalog_paper_ids=["paper-not-actual"]`，然后仅把持久 envelope 的
`tool_results[0].catalog_paper_ids` 改成 `["paper-1"]`。没有改 Search inner output、
inner/outer hash、AgentRun 行或 source handle。实际结果为：

```text
status=completed, error_code=None,
runner_roles=['research_critic', 'synthesizer'],
selections=[{'catalog_paper_id': 'paper-1', 'source_search_id': 'search-1'}]
```

这说明当前 hash 只覆盖 inner model output，不覆盖 envelope 中的 tool results；
AgentRun 绑定也只证明该 run/输出摘要属于本任务，不能证明 tool evidence 未被改写。
若 WorkItem 持久化 JSON 发生瞬态损坏或被错误写回，该候选会越过“真实成功 catalog
tool”门禁。最小修复建议是复用现有 AgentRun checkpoint：恢复时校验
`checkpoint_ref/checkpoint_hash` 与 owner/session/task/work-item/run 绑定，并将
checkpoint 中的 canonical tool results 与 envelope 比较；或把 canonical
tool-results digest 纳入现有 envelope/AgentRun output hash。两种方案均不需要新公开
接口、下载、来源或 fallback 系统。

### 定向验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py --maxfail=1` | 0 | `11 passed in 1.68s` |
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | `45 passed in 3.62s` |
| `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py` | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check`（本轮相关路径） | 0 | 通过 |
| 可信 restart / forged candidate / handle drift / outer hash / missing AgentRun / malformed roles / missing schema | 0 | 分别得到预期 completed 或 partial fail-closed；无旧终态 reopen |
| tool-results-only tamper probe | 0 | **复现 P1**：错误 tool evidence 仍可得到 completed |

本轮未修改业务代码、未部署、未创建或批准研究任务、未写生产数据、未下载论文、
未运行全量测试。所有 SQLite 探针均使用临时目录。当前 HEAD 为 `6bacc29`；工作树中
其他 agent 的未提交改动保留不动。

### 复审裁决

**BLOCKED / P1 待修复。** BLOCK2 已关闭此前的 forged candidate/handle、hash、
AgentRun binding 和 generic role contract 缺口；但在 tool result 不受 output hash
保护的场景下，仍不能证明恢复使用的是“真实成功 catalog tool”证据。先由 backend-dev
在现有 checkpoint/hash seam 内补最小完整性绑定，再独立复审 hydration；completion
fallback 和真实部署/API E2E 另行验收，不纳入本裁决。

## Checkpoint/tool_results 完整性最终独立复审（2026-10-09）

复审角色：`backend-reviewer`  
复审范围：最新 `current-work-item-recovery-fix.md` 的
`checkpoint/tool_results 完整性加固`、实际 `orchestrator.py` hydration diff、
`test_work_item_output_recovery.py`；completion-ID 另案修复不计入本切片签字。只审
持久 checkpoint 与 WorkItem envelope 的完整性、真实 runtime 正向恢复和缺证据旧行的
fail-closed 行为。

### 结论

- P0：`0`。
- 本切片 P1：`0`。此前发现的“只改 envelope `tool_results` 仍被接受”已关闭；
  当前恢复必须以 owner-bound AgentRun 的持久 checkpoint 为唯一完整性依据。
- 本结论不等于 completion-ID、source tool-result 之外的整体验收，也不等于真实 API
  E2E 或部署通过。

### 逐项复核

1. **Tool-results 篡改现在 fail-closed**：复用此前临时 SQLite 探针，只把
   `envelope.tool_results[0].catalog_paper_ids` 从真实列表改为追加
   `paper-forged`，inner output、inner/outer hash、AgentRun 行和 source handle 均不变。
   当前结果为：

   ```text
   status=partial, error_code=UPSTREAM_WORK_ITEM_FAILED,
   runner_roles=[], search_terminal_status=completed, selection_count=0
   ```

   checkpoint 原文中的 tool results 与 envelope 不一致，恢复没有将伪造候选投影进
   evaluator/selection；原 terminal row 保持 `completed`，没有 reopen 或写回。

2. **真实 runtime 正向 checkpoint 可恢复**：使用真实
   `ResearchAgentRunner + FakeModel + FakeTool + 临时 SQLite`，不是手工伪造 envelope。
   runtime 返回 completed Search 后，以下条件全部实际匹配：

   - WorkItem ID 已在 runtime hash/checkpoint 前绑定；inner hash、top-level hash、
     重新计算 hash 三者相等；
   - AgentRun 为 `completed`，session/task/work-item/run ID 与当前恢复任务一致，
     `output_hash` 与 envelope 相等；
   - envelope 与 AgentRun 的 checkpoint ref/hash 相等；checkpoint owner、session、
     task、work-item、run、continuation、schema 均匹配；
   - checkpoint content 的 UTF-8 hash 与 canonical payload hash 均正确，checkpoint
     output/tool_results 与 envelope 精确相等。

   将该真实 runtime envelope 写入 completed WorkItem 后重启 hydration 返回
   `completed`，runner 调用数为 `0`，未重复执行 Search；不是只由 fixture 字段拼出的
   正向结果。

3. **缺 checkpoint 的历史终态保持 fail-closed**：删除 completed envelope 的
   checkpoint ref/hash 后运行恢复，结果为 `partial / UPSTREAM_WORK_ITEM_FAILED`，
   Search/Evaluator 的原 terminal 状态保持 `completed`，没有临时 hash、补 checkpoint、
   reopen 或 rerun。

4. **正常 fresh serialization 的边界**：当前最新工作树的真实 runtime fresh probe
   通过了“非空 output + hash/checkpoint + 后续 hydration”链路；checkpoint 校验没有
   因正常 JSON 序列化而过严拒绝。此前一次定向探针在 concurrent completion-ID
   hash-refresh 尚未落地时曾观察到 inner/top hash 不一致；随后该独立修复将
   Search provenance/degradation mutation 后的 inner hash 刷新到同一 output，最新
   复跑 `66 passed` 且真实 fresh probe 全部匹配。本复审不把该独立 completion-ID
   修复计为 checkpoint 切片的业务改动。

### 定向验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py --maxfail=1` | 0 | `12 passed in 1.76s` |
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | `46 passed in 3.81s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_agent_work_item_failure_visibility.py --maxfail=1` | 0 | `66 passed in 2.59s` |
| `.venv/bin/ruff check` 相关 runtime/orchestrator/测试 | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile` 相关 runtime/orchestrator/测试 | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check` | 0 | 通过 |
| 只篡改 envelope tool_results | 0 | 拒绝，旧 terminal 不变，无 selection/rerun |
| 真实 runtime checkpoint 正向 restart | 0 | 全部绑定/哈希/内容匹配，`completed`，rerun `0` |
| 缺 checkpoint ref/hash | 0 | `partial / UPSTREAM_WORK_ITEM_FAILED`，旧 terminal 不变 |

本轮未修改业务代码、未部署、未创建或批准研究任务、未写生产数据、未运行全量测试；
探针均使用临时 SQLite。completion-ID 修复、source tool-results 之外的整体验收和真实
API E2E 保持独立。

### 复审裁决

**PASS（仅 checkpoint/tool_results recovery 切片）。** 当前实现已用既有持久
checkpoint/hash seam 关闭 tool-results 篡改路径，并能恢复合法真实 runtime envelope；
缺证据历史终态按要求保留 terminal、fail-closed。不得将此局部 PASS 扩展为整个 evaluator
handoff、completion-ID、研究报告或 Spec032 E2E 已通过。
