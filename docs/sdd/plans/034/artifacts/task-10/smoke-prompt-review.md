# Spec034 Task10 Search Worker Smoke Prompt/Output Contract Review

日期：2026-09-15（Asia/Shanghai）
范围：只读检查 `agent_runtime.py`、Search Worker Skill/能力快照渲染、Task10 后端合同；未修改业务代码，未 commit/push。

## 结论

本次失败更像是 Runtime 的模型上下文/工具结果契约缺口，而不是
`search_paper_catalog` 执行失败。目录 Tool 已返回成功后，Search Worker 没有被稳定地引导到“停止调用 Tool 并输出
`ROLE_OUTPUT_FIELDS[search_worker]` JSON”，同时下一轮上下文里的 Tool 结果对模型不可用；模型于是重复发出
`search_paper_catalog`，四次输出尝试均没有结构化结果，最终按现有设计返回 `AGENT_OUTPUT_INVALID`。

## 只读证据

1. **生产批准快照不含 Skill 正文。** `PlanApprovalService._normalize_capabilities()` 只保存
   `name/version/schema_version/content_hash/source_ref/enabled/tools`（
   `backend/app/research/application/approval_service.py:447-471`）。
   `_run_agent_work_items()` 将该 envelope 原样传入 Runner（`backend/app/research/application/orchestrator.py:760-785`）。
   Runner 初始 context 只有 `role/work_item_input/checkpoint_ref/skill` 元数据
   （`backend/app/research/application/agent_runtime.py:1070-1073`）；没有 Skill body，也没有 role-specific output
   instructions。`.agents/skills/usenix-catalog-orchestration/SKILL.md:33-52` 中“搜索→按需详情→失败降级”的编排规则因此不会自动进入真实 Search Worker prompt。

2. **成功 Tool 结果被整体抹掉。** `_safe_tool_result()` 将 Tool 输出放到 `summary`，但 `_safe_text()` 只要文本中包含
   `https://`、`token`、`prompt` 等任一标记就返回 `[REDACTED]`
   （`backend/app/research/application/agent_runtime.py:248-254,807-828`）。
   `search_paper_catalog` 的真实候选输出通常包含 USENIX 详情 URL（`backend/app/skills/tool_dispatch.py:158-174`），即使 Task10 已补充
   `catalog_paper_id`，传给下一轮模型的 `context["tool_results"]` 仍只有安全摘要
   （`agent_runtime.py:1224-1241`）。

   用 Fake Tool 做的只读复现：成功输出
   `catalog_paper_id: paper-1` + `https://www.usenix.org/...` 后，下一轮 context 的同一结果为
   `{'status': 'ok', 'result_id': ..., 'summary': '[REDACTED]'}`；模型看不到候选 ID，也看不到可供
   `fetch_paper_detail` 使用的官方 URL。

3. **Tool 调用后缺少强制 output-only 阶段。** Runner 收到 `raw_calls` 后执行 Tool、把 `summaries` 回灌，再无条件继续把完整
   `capability.tools` 传入下一次 `_invoke()`（`agent_runtime.py:1108-1117,1142-1241`）。没有“本次 Search 已成功”“同参数搜索已执行”或
   “下一次必须只给结构化 output”的服务端状态。重复调用只有预算上限保护，不能纠正协议漂移。

4. **现有测试未覆盖真实失败形态。**
   `tests/test_spec034_task10_backend.py:214-270` 仅验证“搜索成功 + 详情失败后保留候选、详情只执行一次”；
   `:273-305` 仅验证 WorkItem allowlist 越权。没有断言：
   - 首次 `search_paper_catalog` 成功后模型下一轮能看到候选 ID/受控详情引用；
   - 同一 `(Tool, normalized args)` 不得重复执行；
   - Search Worker 最终必须在无 `tool_calls` 时给出完整五字段结构化输出；
   - Skill/role output contract 已被放入模型上下文。

## 最小安全修复建议（不扩大 Spec034 范围）

建议拆成一个小的 Runner contract patch，保持持久化的 `tool_results` 和事件摘要继续走现有脱敏路径：

1. **增加服务端拥有的 role contract，而不是把原始 Skill body 直接拼进 prompt。** 初始及每次 Tool 回灌 context 增加
   `role_contract`，至少声明 Search Worker 的固定输出字段
   `work_item_id/queries/source/candidates/refresh_diagnostics`、`schema_version/safe_summary/source_refs`，以及
   “Tool 成功后停止重复搜索，下一次响应必须是 output JSON；候选只能使用 Tool 返回的既有 `catalog_paper_id`”。
   该 contract 应由代码常量生成；不要信任未经重新校验的 Skill body，避免把技能正文中的提示注入带入 Runtime。

2. **为模型上下文建立独立的 bounded tool-result view。** 持久化/事件仍使用现有 `_safe_tool_result()`；给模型的回灌只允许白名单字段：
   `name/status/error_code/result_id`、搜索结果中的 `catalog_paper_id`、标题/摘要的短文本，以及经过既有 USENIX
   presentation URL 白名单校验的 `detail_url`。不得把原始任意 URL、凭据、论文全文或未验证字段回灌；不得把该 model-only view 写入 checkpoint、事件或产品消息。
   这样既恢复 Search Worker 生成候选 ID/调用详情的必要输入，也保持现有观测脱敏边界。

3. **加一个确定性的重复调用屏障。** 在单次 Run 记录已成功的 `(tool_name, normalized_args_hash)`；相同只读搜索再次出现时不重新 dispatch，回灌稳定的
   `TOOL_ALREADY_EXECUTED`，并在下一轮撤掉该 Tool 或要求 output-only。若 Provider 仍返回 Tool call，则 fail-closed 为
   `AGENT_OUTPUT_INVALID`（不伪造 Search Worker 成功），而不是继续消耗四轮重试。不同 query/source/year 的调用仍按现有
   schema 和预算处理。

4. **补 Task10 定向合同。** 在 `tests/test_spec034_task10_backend.py` 增加最小 FakeModel 场景：
   - 首轮成功搜索（输出含 URL + stable `catalog_paper_id`）；
   - 第二轮断言收到 bounded model-only result 与 `role_contract`，返回合法 Search Worker JSON；
   - 第三轮重复同参数搜索断言底层 Tool 只执行一次，并得到稳定 `AGENT_OUTPUT_INVALID`/output-only 屏障；
   - 断言 checkpoint、`AgentRunOutput.tool_results`、runtime event 绝不包含原始 URL/论文全文。

## 不建议的修复

- 不建议简单把 `skill_snapshot["body"]` 原文注入 Runner prompt：生产批准快照刻意不保存正文，直接绕过快照/哈希边界会引入提示注入和版本漂移风险。
- 不建议放宽 `_safe_text()` 为“只要是 USENIX URL 就全部持久化”：该函数同时保护事件、checkpoint 和产品投影，模型所需的最小字段必须与持久化安全摘要分离。
- 不建议把重复 Tool 调用当作成功输出，或把 `AGENT_OUTPUT_INVALID` 改写为 `completed`；这会违反真实 Smoke 不得伪造成功的门禁。

## 验证记录

- `ollama list`：本机存在 `qwen3.8:27b-q4_K_M`、`qwen3.8:27b-mlx`、`qwen3.5:9b` 等模型；此检查不证明模型满足 Runtime Tool/JSON 契约。
- Python 只读复现确认：当前 Runner 的第二次模型 context 将含 USENIX URL 的成功 Search Tool 输出变为 `summary: "[REDACTED]"`。
- 未运行会改变外部服务/数据库状态的 Smoke；未修改业务文件、未 commit/push。
