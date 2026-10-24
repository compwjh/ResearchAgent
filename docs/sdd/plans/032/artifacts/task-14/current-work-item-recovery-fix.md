# Task 14 WorkItem completed-output recovery 修复报告

## 结论

已完成同范围最小修复：编排器现在会在 dispatch 前读取持久化的 completed AgentRun envelope，将合法 Search/Evaluator/已有上游输出投影回当前运行的 `completed_outputs` 上下文。Search 的 catalog evidence 继续经过现有 `_catalog_evidence_view`，Evaluator 继续经过 `_sanitize_evaluator_binding` 与 `_validate_evaluator_scope`；因此重启后不会重复执行已完成 Search/Evaluator，也不会重新下载或扩大候选/引用 allowlist。

失败、`null` 或 JSON 畸形的 envelope 不会被当作成功输出。它们只在当前内存 pass 中进入 `failed_ids`/partial 传播；queued 下游沿现有 `UPSTREAM_WORK_ITEM_FAILED` 失败，已 terminal 的 WorkItem 不被 reopen 或重写。未新增 schema、API、状态终态或 AgentRun。

## 改动与路径

- [orchestrator.py](/Users/wjh/ResearchAgent/backend/app/research/application/orchestrator.py)
  - 新增严格 completed envelope 读取：只接受 `status=completed`、结构化 `output_json` 和合法 bounded `tool_results`。
  - 重启 hydration 校验 runtime-owned `work_item_id`/可选 `research_task_id`、通用安全输出字段。
  - Search 输出恢复候选与 evidence；Evaluator 恢复前重建其 Search 依赖 allowlist 并复用既有 scope 校验。
  - 无效持久化终态只影响当前编排结果，不调用终态状态转移。
- [test_work_item_output_recovery.py](/Users/wjh/ResearchAgent/tests/research/test_work_item_output_recovery.py)
  - 红灯/绿灯覆盖：持久 Search+Evaluator -> Critic+Synthesizer 成功、failed/null/malformed envelope 拒绝、Evaluator forged candidate/reference 拒绝。
- 日志：[20261009-053803-work-item-recovery.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261009-053803-work-item-recovery.md)

## 验证

项目虚拟环境（`.venv/bin/python`）定向命令与结果：

```text
.venv/bin/python -m pytest -q \
  tests/research/test_work_item_output_recovery.py \
  tests/research/test_agent_selection_persistence.py \
  tests/research/test_agent_work_item_failure_visibility.py \
  tests/research/test_research_report_matrix_bridge.py
退出码 0；39 passed

.venv/bin/python -m ruff check backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py
退出码 0；All checks passed

.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py
退出码 0

.venv/bin/python scripts/check_test_layout.py
退出码 0；test layout: ok
```

另一次使用 shell 激活后的 `python` 实际解析到 `/opt/anaconda3/bin/python`，38 项在 fixture 导入阶段因缺 `langchain_ollama` 报错；未安装依赖、未改环境。随后改用项目 `.venv/bin/python` 重跑并通过，故该次为验证命令解释器误用，不是本次回归失败。

## 风险与边界

- 只读了持久化 envelope，不验证未存在的全文、下载或来源覆盖；本修复不改变这些证据门禁。
- 恢复校验沿用当前 orchestrator/AgentRuntime 的 `usenix`/`dblp`/`all` 搜索来源 allowlist；不扩大 source registry 或公开契约。
- 已完成但 envelope 不完整的行会保留数据库中的 terminal 状态，同时使本次任务 partial；若要修复数据库历史行，需要独立的受批准恢复任务，不能在本路径重开。
- 本轮未部署、未启动服务、未触发生产重试、未修改 env/AgentRuntime/其他 agent 文件。

## 下一项最小 backend-dev 工作

由 backend-reviewer 复审本报告涉及的两处生产语义，重点确认：

1. completed envelope 的 runtime binding 与 tool-result 过滤不会把跨任务/伪造 evaluator 引用投影进上下文；
2. invalid completed row 的内存失败传播与 queued 下游状态机保持现有错误码/partial 语义，并确认同一终态没有被写回。

若复审通过，下一项只需在当前部署版本做一次受控 restart/retry API E2E，确认 Search/Evaluator 的 runner 调用次数为零且后续 Critic/Synthesizer 成功；不做全量同步或下载。

## 耗时

2026-10-09 05:38–05:40（约 3 分钟，含红灯、修复、39 项定向回归与静态检查）。

## BLOCK2 P1 恢复证据加固（2026-10-09）

### 结论

已修复独立复审指出的 P1：completed Search/Evaluator/Critic/Synthesizer 只有在持久化 envelope、实际 AgentRun 和角色输出契约均一致时才会重新进入当前编排上下文。伪造候选、错配 `search_id`/`search:<id>`/tool handle、篡改 digest、缺失真实 AgentRun 或 Critic/Synthesizer 缺角色字段均 fail-closed；已完成 WorkItem 不 reopen、不重跑。

### 生产改动

- [orchestrator.py](/Users/wjh/ResearchAgent/backend/app/research/application/orchestrator.py)
  - 恢复校验复用现有 `ResearchAgentRunner._validate_output`、`_trusted_catalog_search_id`、`_safe_search_id` 与 `_hash`，没有新增第二套 runtime role validator。
  - 顶层 `runtime-v1` envelope、inner/outer output hash、owner-bound completed `AgentRun` 的 session/task/work-item/role/skill/hash 绑定必须全部相等。
  - Search 候选必须是成功 `search_paper_catalog` tool result 的 `catalog_paper_ids` 子集；tool handle、输出 `search_id`、`source_refs` 和 `safe_summary` 引用严格一致。
  - Critic/Synthesizer 恢复前执行现有 role contract；缺证据只影响当前内存 pass，并沿现有 upstream partial/error 传播。
- [test_work_item_output_recovery.py](/Users/wjh/ResearchAgent/tests/research/test_work_item_output_recovery.py)
  - 红灯覆盖 forged catalog candidate、search handle/source-ref drift、output hash tamper、missing AgentRun、Critic/Synthesizer malformed role output。
  - 夹具改用真实 hash、成功 catalog tool summary 与 owner/session/task/work-item 绑定的 completed AgentRun，避免把元数据字段本身误当证据。

### 验证

```text
.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py
退出码 0；11 passed

.venv/bin/python -m pytest -q \
  tests/research/test_work_item_output_recovery.py \
  tests/research/test_agent_selection_persistence.py \
  tests/research/test_agent_work_item_failure_visibility.py \
  tests/research/test_research_report_matrix_bridge.py
退出码 0；45 passed

.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py
退出码 0；All checks passed

.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py
退出码 0

.venv/bin/python scripts/check_test_layout.py
退出码 0；test layout: ok
```

### 风险与下一步

- 该校验要求 durable AgentRun 的 `output_hash` 与实际 runtime envelope 一致；历史上缺失 AgentRun/摘要 tool evidence 的 terminal 行会被保留为 terminal，但本次恢复结果为 partial，不会自动修复数据库历史。
- Search skill 仍按现有 orchestrator/runtime capability contract 校验；没有扩展来源、schema、API、下载、同步或全文证据范围。
- 下一项最小工作是 backend-reviewer 独立复审本节的 AgentRun 绑定与成功 catalog evidence 约束，然后在新部署版本做一次受控 restart/retry E2E；本轮未部署、未生产重试、未改 env。

## 本轮耗时

2026-10-09 05:52–06:01（约 9 分钟，含红灯 6 用例、最小修复、45 项定向回归与静态检查）。

## BLOCK2 P1 checkpoint/tool_results 完整性加固（2026-10-09）

### 结论

已补齐恢复审查发现的残余 P1：WorkItem envelope 中的 `tool_results` 不再被当作独立可信输入。恢复前必须通过既有 AgentRun checkpoint 持久化 seam，证明 envelope 的 checkpoint ref/hash、checkpoint 原文 hash、checkpoint output 和 checkpoint `tool_results` 与 owner-bound completed AgentRun 完全一致。旧 run 缺 checkpoint 或 checkpoint 未保存足够 tool evidence 时 fail-closed，保留原 terminal 行，不回填临时 hash。

### 改动与红灯依据

- [orchestrator.py](/Users/wjh/ResearchAgent/backend/app/research/application/orchestrator.py)
  - 复用 `ResearchStore.get_agent_checkpoint`、既有 `_hash` 和 store 写入时使用的 UTF-8 内容 SHA-256 完整性规则。
  - 校验 checkpoint owner/session/task/work-item/run/continuation/schema 绑定、原始 content hash、解析后的 canonical checkpoint hash，以及 output/tool_results 的精确一致性。
  - 不新增 schema、表或第二套 tool-result hash；不信任 envelope 自报的 `checkpoint_hash`，必须同时通过持久 checkpoint 内容验证。
- [test_work_item_output_recovery.py](/Users/wjh/ResearchAgent/tests/research/test_work_item_output_recovery.py)
  - 正向夹具为每个 completed AgentRun 持久化真实 checkpoint。
  - 新红灯：仅向 checkpoint/envelope 的成功 catalog `catalog_paper_ids` 追加伪造项，inner output 与 output hash 保持不变；旧逻辑会 completed，修复后拒绝并保持 Search terminal 行不变。

### 验证

```text
.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py
退出码 0；12 passed

.venv/bin/python -m pytest -q \
  tests/research/test_work_item_output_recovery.py \
  tests/research/test_agent_selection_persistence.py \
  tests/research/test_agent_work_item_failure_visibility.py \
  tests/research/test_research_report_matrix_bridge.py
退出码 0；46 passed

.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py
退出码 0；All checks passed

.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_work_item_output_recovery.py
退出码 0

.venv/bin/python scripts/check_test_layout.py
退出码 0；test layout: ok

git diff --check
退出码 0
```

### 风险与下一步

- 旧的 completed AgentRun 若没有持久 checkpoint 或 checkpoint 中没有与 envelope 相同的 `tool_results`，本次恢复会 partial；不会自动重跑、reopen 或伪造证据。这是有意的 fail-closed 行为。
- 本轮未触碰 runtime completion fallback、公开 schema/API、来源同步、下载器或部署；共享工作区中的其他 agent 改动未纳入本轮修改。
- 下一项最小工作仍是 backend-reviewer 复审 checkpoint/tool_results 完整性，然后在新部署版本执行受控 restart/retry E2E。

## 本轮耗时（checkpoint 加固）

2026-10-09 06:12–06:19（约 7 分钟，含红灯、checkpoint 夹具、12 项恢复测试、46 项定向回归与静态检查）。
