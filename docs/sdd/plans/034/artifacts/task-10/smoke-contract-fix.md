# Spec034 Task10 Smoke Contract Fix

日期：2026-09-15（Asia/Shanghai）
范围：Search Worker Runtime 的目录 Tool 结果回填与模型 JSON 解析；未 commit、未 push。

## 根因

`search_paper_catalog` 的成功文本同时包含候选标题、稳定 `catalog_paper_id` 和 USENIX 详情页 URL。Runtime 将 Tool 结果交给 `_safe_text` 时，只要文本中出现 `https://` 就把整段摘要替换为 `[REDACTED]`。因此下一轮模型上下文没有候选 ID；模型会重复调用目录 Tool，或者在四次输出重试中始终无法生成包含 `candidates` 的 Search Worker JSON，最终以 `AGENT_OUTPUT_INVALID` 结束。问题不在目录搜索成功语义，也不是 PDF 下载路径。

## 最小修复

- `backend/app/research/application/agent_runtime.py`
  - 对 `search_paper_catalog` 仅逐 URL 替换为 `[redacted-url]`，保留标题、摘要和候选事实；其它 Tool 继续使用原有严格的整体脱敏规则。
  - 从既有 `catalog_paper_id:` 行提取受限字符集的唯一 ID，作为安全上下文字段 `catalog_paper_ids` 回填；不生成新 ID、不回填 PDF URL、不放宽 capability allowlist。
  - Runtime/Ollama 输出解析支持严格 JSON 对象和单层 ` ```json ` 围栏，拒绝带前后 prose 的嵌入对象，避免合法结构化结果因包装形式触发无谓重试。
  - Ollama adapter 现在先发送一条 `system` role contract，再发送原有 JSON user context；明确工具结果存在时停止重复调用、输出单个严格 JSON 对象及 Search Worker 必填字段，并明确禁止 PDF 下载/导入。
- `tests/test_spec034_task10_backend.py`
  - 新增目录成功结果含 URL 时的回填合同：URL 不进入安全结果，`catalog_paper_ids` 和摘要事实可见，模型下一轮生成 Search Worker JSON，目录 Tool 只执行一次。
  - 新增 adapter 消息顺序与 role contract 测试，覆盖 system-first、required fields、收尾指令和 PDF 边界。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py` | 0 | 52 passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/skills/tool_dispatch.py` | 0 | 通过 |
| `git diff --check -- backend tests/test_spec034_task10_backend.py` | 0 | 通过 |

## 风险与 Smoke 复验

- 目录摘要仍可能因通用敏感词（如 `prompt`、`token`、`secret`）触发整体脱敏；此时只保留格式受限的 `catalog_paper_ids`，不会泄露不可信文本。
- 该修复不会把目录成功伪装成完整 Search Worker 输出；模型仍必须返回通过 `ROLE_OUTPUT_FIELDS` 校验的 JSON，失败仍如实返回 `AGENT_OUTPUT_INVALID`。
- 修复后应使用同一固定 Smoke 输入确认事件流中目录 Tool 成功一次、下一轮上下文含 `catalog_paper_ids`、Search Worker 完成并进入后续 Evaluator；全过程仍不调用 `download_and_import_paper`，也不下载 PDF。
