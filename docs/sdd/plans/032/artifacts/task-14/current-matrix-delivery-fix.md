# Spec032 Task14：真实矩阵交付接缝修复

## 结论

- P0：0。
- P1：1 项真实接缝问题已在本地最小修复：synthesizer 输出虽包含 `evidence_matrix`，但 cell 复用了其它论文的 evidence IDs；旧 runtime 只检查字段类型，导致错误 AgentRun 先 completed，随后编排器完整校验拒绝，矩阵与 canonical report 从未写入。
- 本地定向验证通过；本报告不宣称旧 E2E 已被重试或线上/部署已验证。未重试、修改或补写 task `0681e0df0b355deda6ea47abcad24d74`，未部署，未运行全量回归。

## 范围与安全边界

本轮只读取指定 handoff report/evidence、research SQLite 的脱敏结构与对应 paper-search snapshot 形状；未读取环境变量、secret、prompt 正文或隐藏思考内容。旧任务只读，不执行重试或生产写入。未修改 source registry、batch service 或其它 agent 的未完成文件。

## 真实 E2E 证据（只读）

来源：

- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-handoff-report.md`
- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-handoff-evidence.json`
- task `0681e0df0b355deda6ea47abcad24d74`
- session `9f479edfeb7b4b41bf1ac7cf3ea5c590`

脱敏数据库核对结果：

- 5/5 WorkItem（s1/s2/e1/c1/syn）和 synthesizer AgentRun 为 `completed`。
- synthesizer `output_json` 含 `evidence_matrix`；外层 envelope hash、内部 output hash 与规范化计算一致。
- 候选 markdown/html/citation artifacts 为 report version 1；`research_reports` 为 0。
- `research_claims`、`research_claim_evidence`、`research_comparison_dimensions`、`research_comparison_cells` 均为 0。
- handoff 记录的 evidence-matrix 请求为 HTTP 409 `MATRIX_NOT_READY`；canonical `/reports/1` 的 json/markdown/html 均为 HTTP 404 `REPORT_NOT_READY`。

在脱敏、冻结的五候选 catalog snapshot context 上重放现有完整 `_validate_synthesis_matrix_payload`，确定失败为：

`REPORT_SCHEMA_INVALID: cell evidence 不匹配`

具体形状是：唯一 cell 的 `paper_id` 与首个 evidence 匹配，但该 cell 同时列出了另外四篇论文的 evidence IDs。因而拒绝发生在矩阵 `build_matrix` 之前；不是 `ResearchStore` 写入后读取丢失，也不是 canonical report endpoint 的版本读取问题。

## 最小修复

修改文件：

- `backend/app/research/application/agent_runtime.py`
  - 增加内部结构性 matrix reference gate：在存在 server-owned `matrix_context` 时，检查 schema/plan/dimensions、allowlist paper、Claim/Evidence 归属、cell Claim/Paper/stance 归属及 64 项 bounded arrays。
  - cell evidence 不匹配时返回既有 `MATRIX_NOT_READY`，进入既有 bounded structured retry；不改写、不生成 evidence。
  - retry feedback 和 synthesizer contract prompt 明确：每个 cell 只能引用同一 `claim_id`、`paper_id` 且 stance 与 relation 匹配的 evidence，禁止把全部 claim evidence 复制到每个 paper cell。
  - 将同一 server matrix context 传入 fresh 和 restart hydration 的 runtime validation。
- `backend/app/research/application/orchestrator.py`
  - restart hydration 调用 runtime validator 时传入已持久化的 matrix context；原有完整 allowlist、snapshot locator/digest、atomic matrix store validator 保持不变。
- `tests/research/test_agent_runtime_contract.py`
  - 新增真实失败形状回归：首轮跨论文 evidence 复用必须触发 `MATRIX_NOT_READY` retry，合法第二轮才 completed。

未改变公开 API/schema、数据库表、AgentRun envelope 合同、artifact immutable 语义、矩阵四表事务或报告下载状态机；没有新增第二套 matrix/report 实现。

## 红灯与绿灯证据

红灯：

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py::test_synthesizer_retries_when_cell_reuses_other_paper_evidence
退出码 1：修复前 malformed matrix 被 AgentRunner 直接 completed，未发生 retry。
```

绿灯：

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py::test_synthesizer_retries_when_cell_reuses_other_paper_evidence
退出码 0：1 passed

.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1
退出码 0：64 passed

.venv/bin/python -m pytest -q tests/research/test_research_runtime_contract.py tests/research/test_agent_work_item_completion.py tests/research/test_work_item_output_recovery.py --maxfail=1
退出码 0：56 passed

.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py
退出码 0：All checks passed

.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py && git diff --check
退出码 0
```

## 未完成门禁与交接

本地测试证明的是 runtime retry 接缝和既有 matrix/report 领域合同；尚未证明真实模型在 fresh deployment 上会按反馈生成合法的每-cell evidence 映射，也未证明旧 task 可被恢复。下一步须由独立 reviewer 审查后，在新的非历史 task 上重新执行真实 E2E；若模型仍产出非法 matrix，应保持 partial/MATRIX_NOT_READY，不得放宽 validator、伪造矩阵或把候选 artifact 当 canonical report。

详见进度日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261009-live-matrix-fix.md`。

## 2026-10-11 纠正：P1/P2 共享完整契约修复

上一版“没有新增第二套 matrix/report 实现”的结论不完整：runtime 新增的 ownership gate 与 orchestrator 完整 validator 接受集合不同，dimension、locator/snapshot/digest、missing_reason 等非法输出仍可能先完成 AgentRun，再在持久化侧失败；restart hydration 也没有本轮专项证明。该结论已由本轮 backend-dev 修复纠正。

### 根因与修复

- 新增 `backend/app/research/application/matrix_contract.py`，抽出原 orchestrator 的无副作用完整 validator，保留严格 schema、64 项上限、server dimensions/allowlist、snapshot/abstract digest、locator、claim/evidence/cell ownership、stance、supported claim 和 missing_reason 规则；cell/evidence 不被过滤、补造或重写。
- `agent_runtime.py` fresh 输出校验与 orchestrator restart hydration/持久化路径调用同一 helper。完整 contract 错误在 AgentRun terminal commit 前统一映射为既有 `MATRIX_NOT_READY`，反馈保留具体 `matrix_error_code` 与字段级静态 detail，并沿原最多 4 次重试；合法 matrix 仍通过。
- 删除 runtime 局部重复 validator；orchestrator 仅保留 `_validate_synthesis_matrix_payload` 的兼容导出，实际指向共享 helper。restart hydration 对非法 persisted synthesizer matrix fail-closed，保留 terminal WorkItem 原状态且不重跑 terminal 项。
- 新增研究领域测试：dimension、locator snapshot、abstract locator digest、missing_reason、claim/evidence/cell 类型与非字符串 cell evidence_ids 的 fresh retry；shared helper identity；persisted matrix context 的 restart hydration rejection/no-rerun。

### 本轮红灯（修复前）

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'full_matrix_contract_failures or cell_reuses_other_paper' --maxfail=1
退出码 1：首个 dimension case 失败，旧 runtime 首轮 calls=1 并直接 completed（1 failed, 1 passed）。

.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py -k 'persisted_synthesis_matrix' --maxfail=1
退出码 1：旧 recovery hydration 错误返回 completed，而非法 persisted matrix 应被拒绝。
```

### 本轮绿灯与静态验证

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_research_report_matrix_bridge.py --maxfail=1
退出码 0：86 passed in 3.28s

.venv/bin/ruff check backend/app/research/application/matrix_contract.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_research_report_matrix_bridge.py
退出码 0：All checks passed

.venv/bin/python -m py_compile backend/app/research/application/matrix_contract.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py
退出码 0

.venv/bin/python scripts/check_test_layout.py
退出码 0：test layout: ok

git diff --check
退出码 0
```

`.venv/bin/activate` 仍指向旧的 `/Users/wjh/PyCharmMiscProject/.venv`，直接 `source` 会误用系统 Python；以上验证均显式使用仓库 `.venv/bin/python`，未安装依赖或改动环境。冲突扫描未发现 `<<<<<<<`/`>>>>>>>` 标记；命中既有 ASCII 表格的 `=======` 不属于冲突。

### 未验证项

本轮未运行全量回归、未启动/部署服务、未执行真实 API/E2E 或新自然语言模型 run，未重试历史 task `0681e0df0b355deda6ea47abcad24d74`，未写生产数据库/读取密钥。独立 backend reviewer 仍需复审共享 helper 与本报告，并由主会话在后续 Spec032 收口门禁中完成真实 E2E、部署和最终验收；非法 matrix 继续保持 `partial`/`MATRIX_NOT_READY`，不得把 candidate artifact 视为 canonical report。
