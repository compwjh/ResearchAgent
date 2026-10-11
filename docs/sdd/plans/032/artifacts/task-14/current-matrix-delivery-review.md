# BLOCKED — Spec032 matrix delivery 修复独立后端复审

- 复审时间：2026-10-09（Asia/Shanghai）
- 分支：`codex/spec032-final-acceptance`
- 基线：`HEAD=1699a532c257092c785362f8bd6e355c80f696dc`
- 角色：`backend-reviewer`
- 复审范围：`current-matrix-delivery-fix.md`、未提交的 `agent_runtime.py` / `orchestrator.py` / runtime contract test diff，以及既有 matrix bridge / recovery 合同
- 真实失败参照：task `0681e0df0b355deda6ea47abcad24d74`（cell 复用了其它论文的 evidence IDs，AgentRun 先 completed，orchestrator 后拒绝矩阵持久化）
- 本轮未修改业务代码、未部署、未写生产数据、未读取密钥/环境变量、未创建或批准研究任务、未运行全量回归。

## 结论

- P0：`0`
- P1：`1`
- P2：`1`（测试证据缺口）

**BLOCKED / 不能为当前 matrix delivery 修复签字通过。** 目标失败形状本身已被拦截，且没有发现伪造 evidence、放宽 allowlist 或绕过原子持久化的 P0；但新增 runtime helper 与持久化侧完整 validator 不是同一契约。它是一个只覆盖结构归属的第二套、部分重实现的 validator，因此其它非法 matrix 仍可能先使 AgentRun `completed`，再在 orchestrator 被拒绝，违反本轮要求的“校验与持久化契约完全一致、不得引入分叉 validator”。

## 通过项

### 1. 真实失败形状已进入 bounded retry

`agent_runtime.py:182-289` 的 `_validate_synthesis_matrix_references()` 会在有非空
`matrix_context` 时检查：schema/plan/dimensions、allowlisted paper、claim/evidence
归属、cell 的 claim/paper/stance 归属、`missing` 不得带 evidence，以及数组最多 64
项。cell 跨论文复用 evidence ID 会返回既有 `MATRIX_NOT_READY`，不会改写、补造或把
证据移到另一篇论文。

`agent_runtime.py:160-179` 的反馈明确要求 cell 使用相同 `claim_id`、`paper_id` 和
匹配 stance，并禁止把全部 claim evidence 复制到每个 paper cell；
`tests/research/test_agent_runtime_contract.py:236-287` 的 malformed-first/legal-second
回归确认第二轮收到 `MATRIX_NOT_READY` 且合法矩阵才完成。耗尽路径仍为有界四次调用和
`MATRIX_NOT_READY`，未触发模型替换或伪造 fallback。

### 2. 合法 matrix、原有持久化与安全边界仍保留

`orchestrator.py:733-933` 的 `_validate_synthesis_matrix_payload()` 和
`EvidenceMatrixService.build_matrix()` 未被放宽；完整侧仍负责 snapshot、摘要 digest、
locator、evidence level、claim/cell 合同及事务写入。`orchestrator.py:2555-2592` 仍将
矩阵缺失/非法/构建失败保持为 `MATRIX_NOT_READY`，不把 candidate artifact 冒充 canonical
report，也没有写入第二套矩阵表或报告系统。

使用同一合法 fixture 做只读双校验探针：

```text
legal_runtime_and_persistence=accepted
```

既有矩阵 bridge 和 runtime 定向测试也全部通过（见“定向验证”）。因此本复审没有发现
跨论文 evidence 修复会误拒合法 matrix，也没有发现 EvidenceMatrixService 原子语义、
allowlist 或 no-fabrication 边界回退。

### 3. fresh/recovery 的 context 传递代码方向正确

fresh 路径在 `agent_runtime.py:2254-2265` 用当前 `work_item_input["matrix_context"]`
做 runtime 校验；restart hydration 在 `orchestrator.py:1792-1803` 从已持久化的同一
`matrix_context` 传给相同的 `_validate_output()`，不会另造一套 context。retry 也只把
反馈叠加到既有 context，不改变候选/快照范围。

## P1：runtime 前置 validator 与持久化 validator 分叉

**证据位置：**

- runtime partial gate：`backend/app/research/application/agent_runtime.py:182-289`
- runtime 调用：`agent_runtime.py:1769-1775`
- 完整持久化前 gate：`backend/app/research/application/orchestrator.py:733-933`
- 失配后的降级路径：`orchestrator.py:938-966`、`2538-2592`

runtime helper 只检查 ownership 关系，并没有执行完整侧已有的以下合同：

- cell 的 `dimension_id` 必须来自 server dimensions；
- evidence 的 `evidence_level`、locator 字段集合、`catalog_snapshot_id`、
  `abstract_ref` 和 `abstract_digest` 必须与冻结 snapshot 对齐；
- claim 的 topic/statement/confidence/status 及“supported 必须有支持性 evidence”；
- missing cell 必须包含非空 `missing_reason`；
- matrix/claim/evidence/cell 的严格字段集合和 ID 格式。

同一 fixture 的只读探针逐项改变后得到：

```text
dimension_id:  runtime=accepted; persistence=rejected:REPORT_SCHEMA_INVALID
locator:       runtime=accepted; persistence=rejected:EVIDENCE_LOCATOR_INVALID
missing_reason: runtime=accepted; persistence=rejected:REPORT_SCHEMA_INVALID
```

这不是当前真实失败的跨论文 ownership 绕过，也没有导致非法行写入——完整
`_validate_synthesis_matrix_payload()` 仍会在 `EvidenceMatrixService` 之前拒绝它；但它
保留了本次要消除的同一接缝：模型输出先完成 AgentRun，随后才在编排器失败，且 retry
反馈不再触发。`current-matrix-delivery-fix.md` 所称“没有新增第二套 matrix/report
实现”不能替代本轮明确要求的“不得引入第二套分叉 validator”。

**最小修复建议（交 backend-dev）：** 将 matrix 合同的纯校验抽到 runtime 与
orchestrator 可共同调用的单一、无副作用 helper（或共享所有 ownership/locator/dimension
原语），使 runtime 在同一 server snapshot context 上执行与持久化侧一致的 contract，
再把完整校验失败统一映射为既有 `MATRIX_NOT_READY` bounded retry。不得通过放宽完整
validator、补造 locator/evidence、重写 cell 或增加 fallback/第二套存储来消除失败。

## P2：recovery 专门回归尚缺

代码已把 persisted `matrix_context` 传给同一 runtime validator，但新增测试只覆盖
fresh FakeModel 的 malformed-first/legal-second；没有一个本轮新增的 recovery fixture
证明：重启读取 persisted context 时同样拒绝跨论文 cell、同样收到 bounded feedback，且
合法输出可以继续进入现有完整 validator。该缺口不改变上述 P1 的代码证据，但在修复收口
前应补一条不重跑 terminal WorkItem 的 restart regression。

## 定向验证

所有命令均使用项目 `.venv`；退出码均为 `0`：

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py::test_synthesizer_retries_when_cell_reuses_other_paper_evidence` | `1 passed in 0.69s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | `64 passed in 2.68s` |
| `.venv/bin/python -m pytest -q tests/research/test_research_runtime_contract.py tests/research/test_agent_work_item_completion.py tests/research/test_work_item_output_recovery.py --maxfail=1` | `56 passed in 2.11s` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | `All checks passed` |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py` | 通过 |
| `git diff --check` | 通过 |

只读双校验 probe 的进程退出码为 `0`；它证明了合法 fixture 两边均接受，同时保留了上
述三类 runtime/persistence 分叉证据。没有执行服务启动、真实 API E2E、旧 task 重试或全量
测试。

## 复审裁决

**BLOCKED / P1 待修复。** 这次最小修复正确解决了 `task 0681...` 的跨论文 evidence
引用接缝，并保持了现有完整持久化安全门；但 runtime partial gate 与完整 validator
存在可复现的接受集合差异，仍不满足“不引入分叉 validator”和 fresh/recovery 完整契约
一致的要求。完成共享 canonical validator/原语并补 recovery regression 后，应由独立
reviewer 重跑本报告中的定向测试，再在新部署和新 run 上执行真实 E2E；不得把本地 64/56
测试或 candidate artifact 当作 Spec032 真实验收成功。

复审日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261009-matrix-delivery-review.md`

---

## 2026-10-11 共享 pure validator 独立后端复审

- 复审时间：2026-10-11（Asia/Shanghai）
- 分支：`codex/spec032-final-acceptance`
- 基线：`HEAD=1699a53`（当前改动保持未提交）
- 角色：`backend-reviewer`
- 复审范围：`matrix_contract.py`、`agent_runtime.py`、`orchestrator.py` 的最小 matrix diff，以及 `test_agent_runtime_contract.py`、`test_work_item_output_recovery.py`、`test_research_report_matrix_bridge.py` 的实际定向证据。
- 进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261011-103508-shared-matrix-review.md`
- 本轮未修改业务代码、未写生产数据库、未读取密钥/环境变量、未启动/部署服务、未运行全量回归、未 commit/push。

### 独立复审裁决

- P0：`0`
- P1：`0`
- P2：`0`
- 结论：**PASS（共享 matrix 契约修复代码复审通过）**。这只覆盖本轮 backend matrix 接缝修复，不替代 Spec032 后续真实 API/E2E、部署与最终验收门禁。

### 核查结论

1. **单一 pure validator 已成立。** `backend/app/research/application/matrix_contract.py:52-277` 是唯一 `validate_synthesis_matrix_payload` 实现；`agent_runtime.py:1675-1687` 的 fresh runtime 校验、`orchestrator.py:1557-1577` 的 restart hydration，以及 `orchestrator.py:704-730` 的 persistence 分离路径都调用同一函数 identity。orchestrator 只保留兼容导出，不再保留局部字段校验；目标模块未发现循环导入或第二套 matrix validator。

2. **原完整字段与安全语义未放宽。** 共享 helper 保留 schema/plan、server-owned dimensions、candidate allowlist、snapshot abstract digest/ref、claim/evidence/cell ownership、locator/evidence level/stance、supported claim、missing_reason、严格字段集合与 64 项 bounded arrays。针对合法 fixture 的直接探针同时接受 runtime/persistence；dimension、snapshot、digest、locator、claim、evidence、cell、missing_reason 变体均被拒绝，且输入未被改写。

3. **错误在 AgentRun completed 前进入有界重试并带具体反馈。** `agent_runtime.py:2179-2221` 将完整 helper 错误映射为 `MATRIX_NOT_READY`，保留 `matrix_error_code` 与字段级 detail；合法第二轮可完成。`test_synthesizer_matrix_requirement_exhausts_as_bounded_failure` 证明 malformed 输出最多 4 次 model loop，最终 failed/MATRIX_NOT_READY，不会 completed；`test_synthesizer_retries_before_completion_for_full_matrix_contract_failures` 覆盖各字段错误的 malformed-first/legal-second 反馈。

4. **恢复路径 fail-closed 且不重跑 terminal WorkItem。** `orchestrator.py:1557-1685` 在 hydration 时用已持久化 matrix context 复验，非法 output 标记 invalid、保留原 completed 行但不进入 `completed_outputs`，后续不会重新派发。`test_restart_rejects_persisted_synthesis_matrix_before_reuse` 断言结果为 partial/`AGENT_OUTPUT_INVALID`、`runner.calls == []`、synthesizer WorkItem 仍为 completed。

5. **副作用、原子持久化与测试命名边界未回退。** helper 仅返回 projection/抛既有 `EvidenceMatrixError`，不生成/过滤/补造 evidence 或 cell；既有 `EvidenceMatrixService.build_matrix` 与四表事务路径未被替换。新增测试函数按能力命名，无 spec/task 数字。

### 定向验证（均在仓库 `.venv`，退出码）

```text
source .venv/bin/activate
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_research_report_matrix_bridge.py --maxfail=1
退出码 0：86 passed in 3.43s

.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py::test_synthesizer_requires_matrix_when_context_is_present_and_retries_with_feedback tests/research/test_agent_runtime_contract.py::test_synthesizer_matrix_requirement_exhausts_as_bounded_failure tests/research/test_agent_runtime_contract.py::test_orchestrator_matrix_export_is_the_shared_contract_validator tests/research/test_work_item_output_recovery.py::test_restart_rejects_persisted_synthesis_matrix_before_reuse
退出码 0：4 passed in 0.67s

.venv/bin/python -m ruff check backend/app/research/application/matrix_contract.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_research_report_matrix_bridge.py
退出码 0：All checks passed!

.venv/bin/python -m py_compile backend/app/research/application/matrix_contract.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_research_report_matrix_bridge.py
退出码 0

.venv/bin/python scripts/check_test_layout.py
退出码 0：test layout: ok

git diff --check
退出码 0

只读 Python 双路径/输入不可变性探针
退出码 0：合法 payload 同时接受；7 类非法变体均由 runtime/persistence 共享 helper 拒绝；artifact 不保留非法 evidence_matrix。
```

### 未覆盖项

本轮没有执行真实模型新 run、真实 API/E2E、部署或全量回归；旧历史 task 不应被重试或补写。非法 matrix 仍必须保持 partial/`MATRIX_NOT_READY`，candidate artifact 不得被视为 canonical report。上述事项留给主会话 Spec032 收口门禁。
