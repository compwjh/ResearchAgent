# Spec032 Task14：真实 E2E Matrix producer 接缝修复

## 状态

`IMPLEMENTED / LIVE_RERUN_PENDING`。本报告只处理真实 task
`e1591ee5833954e7a6e98221ff60cc01` 的 `MATRIX_NOT_READY` producer 缺口；未部署、未重跑服务、未写生产数据。
真实运行仍有一个独立事实：本轮只有 4 个选中候选，而批准计划要求 `min=max=target=5`；本修复不伪造第 5 篇，也不把 4 篇宣称为验收通过。

## 脱敏真实证据

来源：

- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-matrix-report.md`
- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-matrix-evidence.json`
- 只读查询 `data/research/research.sqlite3` 与 `data/paper_search/state.sqlite3`（未对真实库执行写入）

运行服务 commit 为 `68315ba`，task 终态为 `partial`、`error_code=MATRIX_NOT_READY`，terminal `selected_count=4`；4 个 acquisition item 全部 `completed`。两个 search worker 的真实冻结句柄为：

| candidate | persisted `source_search_id` | snapshot | abstract |
|---|---|---|---|
| `ef9e0846844e5b02834163586ea6ddc9` | `85353bd52fdb492398a965a28a48c296` | completed、未过期 | 存在；digest 与 exact UTF-8 bytes 一致 |
| `9793a4a35caad52ee99f926ae7c90810` | `85353bd52fdb492398a965a28a48c296` | completed、未过期 | 存在；digest 与 exact UTF-8 bytes 一致 |
| `4e6322a23b92a271dbec9906c51fe0ab` | `85353bd52fdb492398a965a28a48c296` | completed、未过期 | 存在；digest 与 exact UTF-8 bytes 一致 |
| `57e0402f82fe2ce354bea423b201fde3` | `278c31d7b163455ba5dd4bf7773f917c` | completed、未过期 | 存在；digest 与 exact UTF-8 bytes 一致 |

逐候选 snapshot 的 `search_id`、candidate membership、title、abstract 都能由相应 `search_results.snapshot_json` 复核；没有依赖全局 catalog row 代替 snapshot。

## 根因定位（producer / prompt / parser 阶段）

真实 synthesizer WorkItem 的持久 `input_json` 顶层字段为：

```text
['citation_allowlist', 'evidence_level', 'goal', 'language', 'report_version', 'validated_candidates']
```

`matrix_context` 不存在；`validated_candidates` 有 4 个，ID 与上述 durable selections 一致。对应真实 AgentRun 的实际模型输出（解包 `output_json` 后）字段为 `artifact_ids/citation_manifest/output_hash/report_version/safe_summary/schema_version/sections/source_refs`，没有 `evidence_matrix`，但正常有 4 个 sections、4 个 citations、`report_version=1`。

因此失败发生在“构造 synthesizer 输入 / producer context”之前，不是模型输出带有非法 locator 后被 `_validate_synthesis_matrix_payload()` 拒绝：模型没有得到 `matrix_context`，按既有 prompt 合同自然不会生成内部 `evidence_matrix`。

具体代码原因是生产 `build_research_service()` 使用惰性 `CatalogSearchAdapter()`，其 `_store` 初始为 `None`。`_build_synthesis_matrix_context()` 原先只读取 `self._adapter._store`，为空就直接返回；但真实 search tool 已通过现有 provider 将冻结 snapshot 写入共享 `PaperDiscoveryStore`。同一编排器中的 `_catalog_metadata_resolver()` 已有复用 `_paper_store()` 的安全接缝，矩阵 context builder 漏用了该接缝。

## 先红灯后修复

新增测试 `test_live_snapshot_context_resolves_shared_store_when_adapter_is_unbound`，使用真实运行同形状的 4 candidates、两个 per-selection `source_search_id`、completed `SearchJob`/`SearchResult` snapshot、catalog paper 行和 exact abstract digest；只让 adapter 保持未绑定，并把既有 `_paper_store()` provider 指向临时目录库。

修复前测试在 `assert context is not None` 失败，实际复现 producer 返回 `None`；没有放宽 locator、没有解析 Markdown、没有伪造 matrix payload。

## 最小修复

`backend/app/research/application/orchestrator.py` 的 `_build_synthesis_matrix_context()` 在 adapter `_store` 为空时复用既有 `backend.app.api.common._paper_store()` provider。该 fallback：

1. 使用与搜索/metadata resolver 相同的已配置 `PaperDiscoveryStore`；
2. 仍按 durable selection 的 `source_search_id` 查 job/result，并逐项检查 membership、状态、过期时间、title、abstract 和 exact digest；
3. 不读取全局目录替代 snapshot，不改变 allowlist、facet/dimension、evidence locator 校验；
4. 不新增公开 API、schema、表、缓存、AgentRun 或第二套来源实现。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py::test_live_snapshot_context_resolves_shared_store_when_adapter_is_unbound`（修复前） | 1 | 红灯：context 为 `None` |
| 同上（修复后） | 0 | `1 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `16 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_runtime_contract.py` | 0 | `95 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `81 passed` |
| `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过 |
| `git diff --check -- backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过 |

## 结论与后续门禁

- 本轮根因已定位并修复：真实 producer 现在可从共享冻结 snapshot 构造 `matrix_context`，下一次真实运行才有机会进入模型内部 matrix producer。
- 当前旧 task 不回放、不改写；其 4 篇/target 5 缺口仍是真实业务门禁，不能用本修复掩盖。
- 必须在包含本修复的服务版本上重新执行真实自然语言 E2E，确认 synthesizer `input_json` 有 `matrix_context`、模型输出 `evidence_matrix` 通过 validator、再观察 `EvidenceMatrixService.build_matrix()` 与 canonical report。未完成该 live rerun 前，保持 `LIVE_RERUN_PENDING`，不可宣称部署就绪。

P0=0；本轮未部署、未运行全量回归、未写生产数据。
