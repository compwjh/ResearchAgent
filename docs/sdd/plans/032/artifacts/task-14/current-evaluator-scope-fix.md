# Spec032 Task14 evaluator scope 修复记录

## 结论

本轮只读核对最新 shared-matrix 真实 E2E 的 e1 失败形状，并用同一字段形状补充回归。根因不是 Search Worker allowlist 或 snapshot 不一致，而是 qwen3.5:9b 将聚合 evaluator 的 `candidate_id: null` 序列化为字符串 `"null"`。既有 sanitizer 未把该字符串识别为聚合容器，scope 校验遂把它当作候选 ID，产生 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`。

修复只在 `orchestrator._sanitize_evaluator_binding` 中将精确字符串 `"null"` 归一为 `None`。`evidence_refs`、`source_refs` 仍先经过 server allowlist 过滤；没有放宽 allowlist、改写候选 ID、补造候选或证据。

## 脱敏真实记录核对

- task：`7108f5117b375f1ba45c6949aff67c98`；e1：`7108f5117b375f1ba45c6949aff67c98:e1`；部署基线：`38a0da158dce429c9493f5a6603306998b306765`。
- e1 的 server `input_json.catalog_paper_ids` 是 s1/s2 召回 ID 的并集，共 13 个：
  `5c85c0b7af7336e768cb62131b24df93`、`4e6322a23b92a271dbec9906c51fe0ab`、`db2c6ce34dae4bf8988903ce8de871ca`、`1ae0b8101d7d6d0b9dc77592a4de9032`、`ad616f4f6cf150c525df8fb2a3820350`、`45d6ac07d66a0777b02eabf6a2570806`、`494effa3cc4fbb517135c94497369839`、`f5e1aea5a8e7a6c51c5e43890738147a`、`a915c4b9219985b21b2da552dbeba006`、`be1e7ee924f3bb21ee8b966c201ee751`、`463a2ea96cc09b2b62050be045baf099`、`ab05f3f4289fcb2cdde17379c22d03ba`、`077bbff9185f9f53d049e966115d36d3`。
- persisted e1 model output 的关键字段为：`candidate_id` 的 JSON 类型是 text、值为 `"null"`；`evidence_refs` 是 s1 的前 5 个上述 allowlisted `catalog:<id>`；`source="usenix"`；`source_refs` 与这 5 个 catalog refs 相同。
- SQLite JSON 只读集合核对：`server_allowlist_count=13`、`model_evidence_ref_count=5`、`in_scope_count=5`、`out_of_scope_count=0`。因此没有证据表明模型引用了越界 paper ID。
- e1 AgentRun 本身为 `completed`、`attempts_used=1`，checkpoint 中 `candidate_id` 类型仍为 text，未产生 runtime `validation_feedback`；失败发生在 orchestrator 的 evaluator semantic scope post-check，不属于已有 runtime retryable error，故本轮没有 4 次 retry。修复该错误归类后，聚合 refs 才能进入既有 evaluator selection 流程。
- handoff 摘要写 s1/s2 各 5 候选，但原始 persisted rows 显示 s1=5、s2=8，e1 server 输入确实是 13 个并集。该摘要/原始计数差异不影响本根因：模型实际引用的 5 个 refs 全部在 13 个 allowlist 中；本轮不扩展范围修复 s2 计数。

## 红灯复现

新增 `tests/research/test_report_synthesis_contract.py::test_evaluator_accepts_literal_null_aggregate_marker_from_json_model`，使用上述真实候选 ID、真实 s1 五条 refs 和字符串 `"null"`。

```text
.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py::test_evaluator_accepts_literal_null_aggregate_marker_from_json_model --maxfail=1
退出码 1：1 failed；修复前 normalized["candidate_id"] 仍为字符串 "null"。
```

## 最小修复

- 修改 `backend/app/research/application/orchestrator.py`：只把精确的字符串 `"null"` 当作 aggregate marker；其他 candidate ID 不变。
- 修改 `tests/research/test_report_synthesis_contract.py`：覆盖真实 e1 形状、allowlist 不扩展、aggregate refs 展开；同时清理该既有测试文件的 lint 阻塞项。
- 未修改 matrix contract、retry policy、Search Worker recall、snapshot/digest、导入、数据库 schema 或报告门禁。

## 绿灯与静态验证

```text
.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_validated_evaluator_candidates.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_completion.py --maxfail=1
退出码 0：62 passed in 1.95s

.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_report_synthesis_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_validated_evaluator_candidates.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_completion.py
退出码 0：All checks passed

.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_synthesis_contract.py
退出码 0

.venv/bin/python scripts/check_test_layout.py
退出码 0：test layout: ok

git diff --check
退出码 0
```

## 未验证项与边界

本轮未重跑真实 E2E、未部署、未重试旧 task、未写生产数据库、未执行全量回归，也未改变 `.env`/密钥/模型配置。独立 reviewer 应在新 conversation/task 上复跑真实自然语言入口，确认 e1 能完成并继续到 coverage/synthesis；仍须保持 server recall allowlist 和 selection cap fail-closed。s2 原始 8 候选与 handoff 摘要 5 候选的计数差异留给独立复审，不在本修复中放宽或重写。

## 2026-10-11 独立复审 REQUEST CHANGES 的纠正

独立复审发现上一节的“精确字符串 `"null"` 一律归一为 aggregate”结论不完整，追加本轮最小修复如下：

- P1：`_validate_evaluator_scope` 在收集顶层记录前增加 `candidate_id` 类型门禁；只允许 `None`（aggregate）或 `str`（per-candidate），`False`、`0`、`[]`、`{}` 等 JSON falsey 非字符串值 fail-closed，不再从其 `evidence_refs` 进入 selection persistence。已保留嵌套 per-candidate 的既有 allowlist/source 校验。
- P2：`_sanitize_evaluator_binding` 仅在真实 server allowlist 不含 `catalog:null` 时把精确字符串 `"null"` 规范为 aggregate `None`；若 `catalog:null` 是真实 allowlisted candidate，则保留字符串 ID，`keep=False` 继续按 per-candidate reject 语义处理。未放宽 recall allowlist、source allowlist 或 selection cap。
- P2：paper evaluator prompt 改为同一契约：`candidate_id` 可作为 aggregate container 为 `null`，即使 `evidence_refs` 非空；否则必须是 supplied candidate ID，并且 evidence 只能引用 supplied catalog refs。

## 本轮红灯与绿灯证据

红灯（修复前）：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py::test_evaluator_rejects_non_string_falsey_candidate_ids_before_aggregate_expansion tests/research/test_report_synthesis_contract.py::test_evaluator_preserves_allowlisted_literal_null_candidate_id tests/research/test_agent_runtime_contract.py::test_evaluator_prompt_matches_non_empty_aggregate_contract --maxfail=1
退出码 1：首个 False candidate_id 被旧 scope 校验误接受（按预期复现 P1 红灯）。
```

绿灯与静态检查：

| 验证 | 结果 |
|---|---|
| evaluator P1/P2 + prompt 三条定向测试 | 退出码 0：6 passed |
| 五文件 evaluator/report/persistence 领域定向回归 | 退出码 0：67 passed |
| `tests/research/test_agent_runtime_contract.py` | 退出码 0：52 passed |
| 上述六文件组合回归 | 退出码 0：119 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check`（两生产文件及受影响测试） | 退出码 0：All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile`（两生产文件及两测试） | 退出码 0 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 退出码 0：test layout: ok |
| `git diff --check` | 退出码 0 |

## 解释器与依赖核验

复审记录中的依赖缺失在当前真实项目解释器下不可复现；只读核验命令为：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -c 'import sys; print(sys.executable); import langchain_ollama; print("langchain_ollama=ok"); import fastapi; print("fastapi=ok")'
退出码 0：解释器为 /Users/wjh/ResearchAgent/.venv/bin/python，langchain_ollama=ok，fastapi=ok。
```

未安装依赖、未修改 `.venv`/环境变量；未重跑真实 E2E、未部署、未写生产数据库、未提交或推送。真实自然语言入口和独立 reviewer 复审仍由主会话执行。
