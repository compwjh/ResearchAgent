# Spec032 Task14：Synthesizer 基础输出合同诊断与最小修复

## 结论

对应 fresh run `spec032-task14-fuzzing-diagnostic-20261011T111924Z` / task
`dd2291bec53954328c3c5ec94c2b457f` 的 syn 失败**不是已有证据所能归因的矩阵字段错误**。
公开记录只证明 attempt 1–4 返回 `AGENT_OUTPUT_INVALID`，而不是
`MATRIX_NOT_READY`；四个失败 checkpoint 的 `output=null`、`tool_results=[]`，诊断固定为
`agent.output_contract` 且 `field_paths=[]`。因此无法诚实判断旧模型响应停在 JSON 解析、
provider content 包装、required field、safe-scope、identity、hash 或其他结构阶段。

这不是把 5 篇导入或空 artifact 当作报告的理由。旧 run 仍保持 `partial`、矩阵和 canonical
报告不可用；本文件记录的是诊断缺口及本地最小代码修复，不回填旧 run 的具体模型错误。

## 对应记录的只读审计

只读读取 `data/research/research.sqlite3`（`mode=ro`），仅输出固定字段和结构摘要，没有读取
或保存 env、API key、prompt 全文、hidden reasoning、provider 原文、摘要、locator 或 URL。

| 检查项 | 可复核事实 | 边界 |
|---|---|---|
| syn AgentRun | attempt 1–3 为 qwen fast run，`limit_reached/AGENT_OUTPUT_INVALID`，tool_calls=0；attempt 4 进入 fallback 后完成 | 不含模型正文或解析阶段 |
| 失败 checkpoint | 3 个失败 attempt 均 `output=null`、`tool_results=[]`，只有 `validation_diagnostic` | 空输出不等于可证明的 JSON parse |
| validation event | attempt 1–4 均 `error_code=AGENT_OUTPUT_INVALID`、`rule_id=agent.output_contract`、`field_paths=[]`、`feedback_sent=false`、`not_sent` | 未调用矩阵 validator 的证据 |
| syn 输入 | `matrix_context` 非空，含 schema/plan/dimensions/candidates/allowlist | 只能证明输入准备完整，不能证明模型输出格式 |
| 最终安全 envelope | fallback 后 output 含合法 evidence_matrix，最终报告门禁仍按旧 run 失败 | 成功 fallback 不能反推前四轮响应 |

### 根因判定边界

旧 runtime 的 `_response_parts()` 在解析失败时只返回 `None`，调用方再以空对象进入
`_validate_output()`；所有基础输出错误都被压成同一个 `AGENT_OUTPUT_INVALID`。同时 retry 分支
只有 `MATRIX_NOT_READY` 才写 `validation_feedback`，普通输出合同错误只创建空 checkpoint，
下一轮拿不到修正方向。后者是确定的程序行为缺陷；前者造成旧 run 无法区分具体 stage。

旧 run 缺少以下事实，不能通过推测补写：

- provider content 的安全形状（字符串、空值、列表/块包装）和是否成功 JSON parse；
- 解析后的顶层字段集合及具体缺失/类型错误；
- safe-scope、identity/source binding 或 downstream hash 校验是否触发；
- 每一轮 retry context 是否在线带有反馈。

## 最小修复

修复只位于 `backend/app/research/application/agent_runtime.py`，未放宽输出 schema、矩阵
validator、allowlist、snapshot/digest locator、模型路由、4-attempt 上限、资源 cap 或公开 API。

1. `_response_parts()` 仅记录固定内容形状阶段：`json_parse` 或 `provider_content`；不保留
   provider content。
2. `_validate_output()` 将现有失败点映射为固定 rule/path：
   `agent.output.json_parse`、`agent.output.provider_content`、
   `agent.output.required_fields`、`agent.output.safety`、`agent.output.identity`、
   `agent.output.source_binding`、`agent.output.structure`。字段路径来自固定 allowlist，
   不接受模型或异常文本作为诊断。
3. `AGENT_OUTPUT_INVALID` 的有界重试现在收到 provider-safe 的结构化反馈：固定 required
   fields、shape 和 rule/path；matrix 失败继续走原有 `MATRIX_NOT_READY` feedback，不合并两套
   validator，也不自动生成矩阵。
4. `feedback_sent` 的既有真实性语义保持：只有携带 feedback 的下一次 `_invoke()` 正常返回
   后才置真；取消、预算阻断、checkpoint 失败或 provider 异常均保留 false。

这不会宣称旧任务已修复完成。要确认真实 qwen 的具体失败 stage，必须在修复部署后的全新受控
run 读取新的固定诊断字段；旧 task 不重试。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'generic_output_contract or provider_content_block' --tb=short --maxfail=1` | 0 | 4 passed，57 deselected |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py --tb=short --maxfail=1` | 0 | 61 passed |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py --tb=short --maxfail=1` | 0 | 22 passed |
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py -k 'restart_hydrates_completed_outputs_for_downstream_workers or restart_rejects_persisted_synthesis_matrix_before_reuse' --tb=short --maxfail=1` | 0 | 2 passed，11 deselected |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

未执行：部署、真实 provider 重跑、旧 task 重试、全量回归、env/key 读取、报告或矩阵人工
POST。独立 backend review 待主会话安排。

## 当前裁决

旧 E2E 仍为 `BLOCKED`；本修复阶段为“诊断缺口已补齐、真实 stage 待新 run 验证”，不是
`Spec032 Task14` 的验收通过或报告生成。

