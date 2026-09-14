# Spec034 Task10 Smoke Evidence Path 复核

日期：2026-09-15（Asia/Shanghai）
范围：Search Worker → Evaluator → Synthesizer 的证据交接；未改 Spec 状态，未 push/merge。

## 结论

**代码路径：条件 GO；当前真实 Smoke Artifact：NO-GO（需模型/来源复验）。**

Smoke 中 Evaluator 输出 `keep=false`、`evidence_refs=[]` 后未进入 Synthesizer，是现有 fail-closed 逻辑的预期结果，不是 Synthesizer 调度丢失：

1. Orchestrator 只把 Search Worker 的 `candidates`（稳定 `catalog_paper_id`）交给 Evaluator；真实 `search_paper_catalog` Tool 已产生的标题/摘要安全摘要没有沿 WorkItem 依赖链交接。
2. Evaluator 因没有可判定相关性的目录事实，输出淘汰且无证据引用；`_validated_evaluator_candidates()` 严格要求字面量 `keep=True`/`verified=True` 和非空 `evidence_refs`，因此 Synthesizer 前的 `NO_VALIDATED_EVIDENCE` 门禁正确阻断。
3. 调整 Smoke 主题或固定样本不能可靠修复：Evaluator 输入中的 ID 是不透明稳定标识，现有固定样本/搜索工具没有把标题/摘要传到该阶段。直接把 `keep` 改为 true、补造 `catalog:<id>` 或放宽空证据，都会违反“禁止伪造证据”。

## 最小修复

- `backend/app/research/application/orchestrator.py` 新增内部 `_catalog_evidence_view()`，从 Runner 已经安全化的 `search_paper_catalog` ToolResult 提取 bounded `summary`、与 Search Worker `candidates` 交集后的 `candidate_ids` 和派生的 `catalog:<id>` 引用；不读取原始 Tool 响应、不新增检索或 ID 算法。
- Evaluator WorkItem 的 `work_item_input` 增加 `catalog_evidence`，同时保留既有 `catalog_paper_ids`、来源和查询字段。该视图只来自已成功执行的 Search Worker 目录 Tool，URL 已被 `[redacted-url]` 替换，非候选 ID 被过滤。
- `backend/app/research/application/agent_runtime.py` 的 Evaluator 合同明确要求使用 `catalog_evidence`，且 `evidence_refs` 只能是 supplied `catalog:<candidate_id>`；既有 allowlist 与 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`/`NO_VALIDATED_EVIDENCE` 门禁不变。
- `tests/test_spec034_task10_backend.py` 增加 bounded evidence view 合同，验证详情 Tool 不越界、非候选 ID 被过滤、URL 不泄露。

该改动只恢复真实 Search→Evaluator 证据交接，不能把模型输出强制变成 keep；模型仍必须基于真实目录事实返回合法 Evaluator JSON，Synthesizer 仍只消费已验证候选。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py` | 0 | **56 passed** |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py backend/app/research/application/agent_runtime.py backend/app/skills/tool_dispatch.py` | 0 | 通过 |
| `git diff --check -- backend/app/research/application/orchestrator.py backend/app/research/application/agent_runtime.py tests/test_spec034_task10_backend.py` | 0 | 通过 |

## 真实 Smoke 状态与建议

本轮未把 FakeModel/固定数据当作真实 Artifact，也未声称外部 USENIX/Ollama 成功。应在真实来源可达且模型能返回 Tool/JSON 的环境，用同一固定主题复验，并核对：

- Evaluator 输入含 `catalog_evidence`，其中标题/摘要来自真实 `search_paper_catalog` ToolResult；
- Evaluator 返回 `keep=true` 且每条 `evidence_refs` 命中 `catalog:<candidate_id>`；
- Synthesizer 仅在上述验证通过后运行，并生成真实 Markdown/HTML/manifest Artifact。

若模型仍返回 `keep=false`/空证据，或 USENIX 来源无候选，应继续保持 `NO_VALIDATED_EVIDENCE`/`partial`，记录为真实 NO-GO，不修改证据门禁。

## 改动文件

- `backend/app/research/application/orchestrator.py`
- `backend/app/research/application/agent_runtime.py`
- `tests/test_spec034_task10_backend.py`
- 本报告：`docs/sdd/plans/034/artifacts/task-10/smoke-evidence-path.md`

## 时间

- 开始：2026-09-15 06:12（Asia/Shanghai，约）
- 结束：2026-09-15 06:22（Asia/Shanghai）
- 耗时：约 10 分钟
