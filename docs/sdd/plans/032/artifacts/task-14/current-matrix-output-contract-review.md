# Spec032 Task14 matrix output contract 独立后端复审

结论：**CONDITIONAL PASS / LIVE VERIFICATION BLOCKED**。

本复审针对 `current-matrix-output-contract-fix.md` 的实际未提交 diff、相关定向测试和真实 Ollama adapter probe。未修改业务代码、未部署、未重跑研究任务、未写生产数据、未运行全量回归。

## 复审范围

- 代码：`backend/app/research/application/agent_runtime.py`；
- 合同/桥接测试：`tests/research/test_agent_runtime_contract.py`、`tests/research/test_research_report_matrix_bridge.py`；
- 既有 server-owned matrix validator、`EvidenceMatrixService` 和 orchestrator canonical-report gate；
- frozen run 的真实 synthesizer 输入摘要：5 个候选、2 个维度、5 个 allowlisted paper IDs；
- HEAD：`4b61c3f`，修复仍在工作树未提交状态。

## 逐项结论

### 1. 非空有效 `matrix_context` 才要求内部 extension

**通过（代码级）**。

`_synthesis_matrix_required()` 只在 synthesizer 的 `work_item_input.matrix_context` 为非空 mapping 时开启要求；orchestrator 在运行前先删除旧 context，再从当前冻结 selections、批准 plan facets 和 server catalog snapshot 重新构造 context。无 context 的旧 synthesizer 输入仍不会被强制要求 matrix。任意异常/不完整 context 只会进入严格 validator 并 fail-closed，不会放宽范围。

### 2. 缺失 matrix 的 bounded retry 与字段反馈

**通过（代码级/定向测试）**。

缺失或非 object 的 `evidence_matrix` 返回稳定 `MATRIX_NOT_READY`；retry context 只追加 bounded `validation_feedback`，包含：

- `code=MATRIX_NOT_READY`；
- `required_fields=["evidence_matrix"]`；
- `shape` 中的 `schema_version`、批准 plan version、server dimensions、bounded claims/evidence/cells 和 abstract snapshot locator 要求。

测试实际断言了第二轮收到具体错误码/字段；连续四次缺失时 `model_loops=4`、调用次数为 4、终态为 `failed/MATRIX_NOT_READY`。没有静默默认 matrix。

### 3. 合法 matrix 接纳

**通过（server validator、bridge、真实单候选模型 probe）**。

既有 `_validate_synthesis_matrix_payload()` 仍要求：

- `evidence-report-v1`、批准 plan version；
- dimensions 与 server context 完全相等；
- paper IDs 完整且只来自 allowlist；
- `catalog_snapshot_id`、`abstract_ref`、`abstract_digest` 与 snapshot 一致；
- abstract/catalog evidence 级别、claim/cell 关系和数组上限合法。

矩阵通过后仍复用 `EvidenceMatrixService.build_matrix()` 的现有事务和 `ReportGenerationService` canonical gate，没有新建第二套 matrix 或报告系统。相关 allowlist、dimension、digest、locator、事务回滚和 canonical bridge 测试均通过。

### 4. 无 context 兼容、耗尽语义和 fallback

**通过（代码级/定向测试）**。

- 无 context 的 synthesizer 保持单轮 candidate-level completed；
- `MATRIX_NOT_READY` 已加入 `_ONLINE_FALLBACK_BLOCKED_CODES`；
- validation 分支在耗尽后直接抛出 `MATRIX_NOT_READY`，不会 online fallback、全局换模型或伪造 matrix；
- orchestrator 对缺失/无效 matrix 只保留 degraded candidate artifact，终态保持 `partial`，不创建 canonical `ResearchReport`；
- matrix context 仍为 server-owned，未放宽 locator 或允许 fulltext/document ID/URL/发明 dimension。

### 5. 实际 model prompt / response_format

**单候选真实 probe 通过；provider structured-output 未配置。**

使用项目 `.venv/bin/python`、真实 `qwen3.5:9b`、`reasoning=False` 直连同一 `_OllamaRunnerAdapter`，不经过研究 API、不写 store：

- `ChatOllama.format=None`、`model_kwargs=None`，未下发 `response_format` 或 provider JSON schema；
- 实际 system prompt 包含 `evidence_matrix`、`evidence-report-v1` 以及 `dimensions/claims/evidence/cells` 具体 shape；
- 真实模型返回 object，含 `evidence_matrix`，矩阵字段为 `cells/claims/dimensions/evidence/plan_version/schema_version`；
- 返回结果通过现有 `_validate_synthesis_matrix_payload()`（`matrix_validation=ACCEPT`）。

因此修复不是只靠 FakeModel/validator 才能工作；当前路线依赖现有 prompt + JSON parser + server validator，而不是 provider `response_format`。

## 五候选真实运行门禁

用 frozen run 的真实 `syn` WorkItem 输入做同一 adapter probe，输入规模确认为 5 candidates、2 dimensions、5 allowlisted IDs。该调用超过 150 秒没有返回任何 JSON，随后为防止无界占用以 Ctrl-C 结束（退出码 130）。没有把超时解释为成功，也没有把它解释为越界输出。

这保留一个 **P1 验收门禁**：修复尚未在包含该 diff 的部署上完成真实五候选重跑，不能仅凭单候选 probe 宣称 Spec032 E2E 通过。重跑时必须观察真实 AgentRun 的 prompt/output、matrix build、canonical JSON/Markdown/HTML 和终态；若模型仍超时或缺 matrix，应保留实际 `MATRIX_NOT_READY`/`REPORT_NOT_READY`，不得由 artifact fallback 冒充 canonical report。

## 定向验证

均使用直接路径 `.venv/bin/python`。仓库 `.venv/bin/activate` 当前指向外部 `/Users/wjh/PyCharmMiscProject/.venv`，source 后会错误落到 `/opt/anaconda3/bin/python` 并缺少依赖；没有安装或修改依赖。

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'synthesizer_requires_matrix or matrix_requirement_exhausts or without_matrix_context or ollama_synthesizer_prompt' --maxfail=1` | 退出 0；4 passed，30 deselected |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 退出 0；22 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_synthesis_contract.py --maxfail=1` | 退出 0；62 passed |
| `.venv/bin/python -m pytest -q tests/research/test_evidence_matrix.py tests/research/test_evidence_report_contract.py --maxfail=1` | 退出 0；7 passed |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | 退出 0；All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | 退出 0 |
| `git diff --check` | 退出 0 |

另一次 `tests/research/test_research_runtime_contract.py -k 'matrix or synthesis'` 无匹配测试，pytest 退出 5（38 deselected）；不计入通过数量，也不作为阻塞根因。

## P0/P1 结论

- **P0：0**。没有发现绕过 allowlist、locator、全文边界、fallback 或 canonical gate 的 P0 缺陷。
- **P1：1 个验收门禁保持打开**：五候选真实 runtime probe 超时且修复尚未部署重跑。它是 live evidence 缺口/运行风险，不足以单凭一次超时判定静态实现错误；在部署重跑完成前，不能签署最终验收或标记 PASS。
- 代码级结论：条件 extension、具体反馈、最多四轮、合法接纳、旧路径兼容、partial/no-canonical 语义和安全 locator 约束均通过。

后续最小动作是部署包含该 diff 的服务并新建 run，验证真实 5-candidate synth 是否在有界时间内返回可验证 matrix；不得重试旧失败 batch，不得改 global model/threshold/env，不得通过参数放宽 validator。日志见 `.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261009-045625.md`。
