# Spec032 Task14：真实 synthesizer output / candidate allowlist 修复

## 状态

`IMPLEMENTED / LIVE_RERUN_PENDING`。本轮只处理真实 converged run 的 synthesizer
输入集合漂移与内部 matrix prompt 边界；未部署、未重试真实任务、未写生产数据库。

## 真实脱敏证据

来源：

- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-converged-report.md`
- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-converged-evidence.json`
- 只读查询 `data/research/research.sqlite3`、`data/paper_search/state.sqlite3`

运行 commit 为 `00cdb6b`，task `bf474433be705e479bca55c4b2dbe9c2` 终态为
`partial/AGENT_OUTPUT_INVALID`，`selected_count=5`；acquisition 无 batch/items，matrix 为
`MATRIX_NOT_READY`，session artifacts 为空。

实际 synthesizer WorkItem 输入的顶层字段为：

```text
['citation_allowlist', 'evidence_level', 'goal', 'language', 'report_version', 'validated_candidates']
```

其中 `matrix_context` 缺失，`validated_candidates` 有 5 个。实际 AgentRun 解包后的
`output_json` 顶层字段为：

```text
['artifact_ids', 'citation_manifest', 'output_hash', 'report_version',
 'safe_summary', 'schema_version', 'sections', 'source_refs']
```

没有 `evidence_matrix`，但有 5 个 sections、5 条 citation，`artifact_ids=[]`，
`report_version=1`，且 `report_output_hash(output_json)` 与其 `output_hash` 一致。
在当前 validator 与 `ReportSynthesizer.consume_validated_output()` 上复核通过；因此
这不是模型 candidate envelope 的 schema/hash/parser 误判，也不是 artifact ID 伪造。

## 根因定位

临时数据库只读回放复现了终态错误的具体传播：

1. synthesizer 输入集合包含候选 `ff93...`，模型 citation/section 也引用该真实
   allowlist；输入没有 `matrix_context`，所以模型没有生成可选的内部 `evidence_matrix`。
2. 编排收尾又独立执行一次 floor/metadata 计算并持久化了不同候选集合（真实库中可见
   `bffa...` 替代 `ff93...`）。随后消费模型输出时，citation 不在收尾时的
   evaluator allowlist，`ReportSynthesisError` 以默认 `AGENT_OUTPUT_INVALID` 抛出。
3. deterministic candidate fallback 随后还会触发目录 abstract 的安全文本门禁；它不是
   合法模型输出被拒的根因，也不能通过放宽安全过滤来修复。由于前一步异常被已有
   degraded 语义覆盖，终态只暴露了 `AGENT_OUTPUT_INVALID`，造成“selected=5 但无 artifact”
   的表象。

因此必须冻结“传给 synthesizer 的候选集合”作为同一运行的 canonical allowlist；不能在
模型产出后再次独立选择另一批候选。`matrix_context` 缺失也被明确区分为 producer
接缝问题：无 context 时，缺 `evidence_matrix` 不能被误报为 candidate envelope 无效。

## 先红灯后修复

新增 `test_synthesis_keeps_the_same_candidate_allowlist_after_final_projection_changes`：
第一阶段让模型收到 `paper-a`…`paper-e` 并引用这五项，收尾第二次 floor 计算故意返回
`paper-a`…`paper-d` + 未在 recall 集的 `paper-x`。修复前报告消费/矩阵收尾不稳定并返回
partial；修复后保持同一五项 allowlist，报告完成、selection projection 与模型输入一致。

该测试只模拟真实集合漂移，不放宽 candidate/snapshot locator，不从 Markdown 反解析，
不伪造 evidence 或 AgentRun。

## 最小修复

### 1. 冻结并复用 synthesizer 输入集合

`backend/app/research/application/orchestrator.py`：

- 在 synthesizer dispatch 前保存有界、已验证的 `synthesis_validated_candidates`；
- 从已完成 Search Worker 输出建立候选到真实 `search_id` 的 source map；
- 在构造 matrix context 前，把同一集合写入既有 selection projection，并保留逐候选
  `source_search_id`；
- 收尾阶段复用该冻结集合并再次对齐既有 selection projection，不再让独立 floor pass
  替换模型已经引用的候选；
- 仍使用既有 `_persist_agent_selections()`、`EvidenceMatrixService`、
  `ReportGenerationService`，未新增表、公开 schema、API、缓存或 AgentRun。

### 2. 收紧已有 synthesizer 内部 prompt 边界

`backend/app/research/application/agent_runtime.py` 仅更新已有 role contract：当服务提供
`matrix_context` 且摘要足以支撑 claim 时，要求模型输出内部-only `evidence_matrix`；
若没有可支持 claim，仍必须省略并让运行时记录 `MATRIX_NOT_READY`。prompt 明确禁止
发明 claim/dimension/locator、使用 URL/document/chunk/fulltext；没有把内部 matrix 加入
公开 artifact envelope，也没有改变模型或全局配置。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py -k same_candidate_allowlist --maxfail=1`（修复前） | 1 | 红灯：真实形状的候选集合漂移导致终态不为 completed |
| 同上（修复后） | 0 | `1 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `21 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_agent_runtime_contract.py tests/research/test_report_synthesis_contract.py --maxfail=1` | 0 | `79 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py -k 'live_snapshot or same_candidate_allowlist or canonical_generation or matrix_build_failure' --maxfail=1` | 0 | `5 passed` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

直接读取真实 AgentRun 的复核命令也确认：`output_hash_matches=True`、candidate-level
validator/consumer `PASS`，而 `matrix_context_present=False`、`evidence_matrix` 缺失。

## 结论与后续门禁

- P0：0。
- 本修复消除了真实 `AGENT_OUTPUT_INVALID` 的 candidate allowlist 漂移根因，并把缺 matrix
  明确留在既有 `MATRIX_NOT_READY` 降级语义；不会把缺 matrix 冒充 canonical report 成功。
- 真实 E2E 必须在包含本修复的服务版本上重新执行，确认输入含逐候选真实 snapshot
  `matrix_context`、模型在有支持 claim 时输出内部 matrix、validator/build/generate 成功，
  并观察 acquisition 与 canonical report。live rerun 前保持 `LIVE_RERUN_PENDING`，不可
  宣称已部署或验收通过。

