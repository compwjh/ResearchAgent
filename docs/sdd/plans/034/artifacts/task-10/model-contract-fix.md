# Spec034 Task10 Runtime Model Contract Fix

日期：2026-09-15（Asia/Shanghai）
范围：后端 Runtime / Search Worker 定向修复；未 commit、未 push，未运行全量回归。

## 根因

真实 Smoke 的 Search Worker 已成功调用 `search_paper_catalog`，随后对候选详情调用 `fetch_paper_detail`。该详情补抓失败后，`ResearchAgentRunner.run` 对同一轮 Tool 结果的任意 error 直接返回 `TOOL_EXECUTION_FAILED`，没有把失败摘要回灌给模型，也没有保留已取得的目录候选。因此一个可选的详情增强失败会覆盖基础检索成功。

另一个边界是 Runtime 只校验计划批准的 Skill/Tool snapshot，没有提供 WorkItem 级别的进一步收窄；这使得“计划已批准但本 WorkItem 不需要”的 Tool 仍可能被模型尝试。

## 最小改动

- `backend/app/research/application/agent_runtime.py`
  - 增加 `allowed_tools` / `tool_allowlist` 的 WorkItem 级收窄；只允许从已批准 capability 中删减，不允许新增、伪造或绕过 Registry/Schema/Skill 校验。
  - Search Worker 在 `search_paper_catalog` 已成功后，`fetch_paper_detail` 失败改为可降级：保留目录结果，把 `TOOL_EXECUTION_FAILED` 记录到安全 Tool 结果，并继续模型循环。
  - 将降级标记写入现有 `SearchWorker` 输出的 `refresh_diagnostics`（`degraded=true`、`error_code=SOURCE_DEGRADED`、`detail_fetch_failed=true`、详情错误码列表）。不新增第二套搜索、目录或详情实现。
  - 详情失败后从下一轮模型 Tool schema 中移除该可选 Tool；即使 Provider 忽略缩减 schema 重复请求，也不会再次执行详情抓取。
  - 目录搜索本身失败、未先取得目录结果，或其它 Tool 失败仍保持原有 fail-closed `TOOL_EXECUTION_FAILED` 行为。
- `tests/test_spec034_task10_backend.py`
  - 覆盖目录成功 + 详情失败仍完成并保留候选、详情 Tool 不重复执行、降级诊断字段，以及 WorkItem allowlist 只能收窄已批准 Tool。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py` | 0 | 49 passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/search_catalog_adapter.py backend/app/research/application/orchestrator.py` | 0 | 编译通过 |
| `git diff --check -- backend tests/test_spec034_task10_backend.py` | 0 | 空白检查通过 |

未运行项目全量 pytest，符合 Task10 定向修复约束。

## 真实 Smoke 建议

服务启动后用同一固定输入复验，并重点确认：

1. 事件流中 `search_paper_catalog` 成功后，若 `fetch_paper_detail` 失败，Search Worker 仍有 completed/可消费的结构化输出，`refresh_diagnostics.degraded=true`，候选 ID 未丢失。
2. 详情失败后不再出现同一 Search Worker 的重复详情执行；Tool 事件应保留一次失败及其安全错误码。
3. 未批准的详情 Tool 或 WorkItem allowlist 外的 Tool 在 Runtime 执行前被拒绝；不应绕过现有注册表。
4. 若模型仍无法返回 SearchWorker 结构化 JSON，仍应如实记录 `AGENT_OUTPUT_INVALID` / `MODEL_UNAVAILABLE`，不能把降级目录结果冒充完整报告成功。

## 进度

- 状态：完成本次最小代码修复与后端定向验证。
- 未完成：真实 Ollama Smoke 重跑、部署收口与 Spec034 状态变更；由主 Agent 在服务/模型前置满足后执行。
