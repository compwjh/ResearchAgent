# Task05 后端交接报告

## 本轮范围

本轮增量修改 `backend/app/research/application/orchestrator.py`、
`tests/test_spec027_backend_research_slice.py` 与本报告；不修改 Spec、长期规则或模型注册。

## 实际改动

- 报告保存后，若任务仍非终态且当前计划状态为 `active`，将该计划更新为 `completed`；取消或失败的终态不强行覆盖。
- coverage、report、terminal 事件及 `limitations_json` 增加真实 `replan_round` 与稳定 `stop_reason` 摘要。
- 停止原因使用 `coverage_satisfied`、`replan_pending`、`no_new_evidence`、`replan_limit`、`search_item_cap` 与 `budget_exhausted`；软预算只在阶段边界阻止新增 search/re-plan，允许已开始阶段收尾并生成 partial 报告。
- 注入式 `ModelRouter.execute` 的升级事件接入研究任务 `model` 事件流；仅投影固定的 `MODEL_ESCALATED`、档位与稳定原因，丢弃 prompt/论文文本等扩展字段。
- `search-worker/search_catalog` 同样传递任务 ID 与 task_type，升级事件不会因 Worker 路径缺少上下文而丢失。

## 验证结果

- `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py`：通过。
- `.venv/bin/python -m pytest -q --basetemp=/private/tmp/spec027-task05-followup2 tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py`：`90 passed`、`5 subtests passed`、`1 warning`，退出码 0。
- `.venv/bin/ruff check backend/app/research/application/orchestrator.py`：通过。
- `git diff --check -- backend/app/research/application/orchestrator.py`：通过。

## Task05 第二阶段增量验证

- `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py -q`：**95 passed、5 subtests passed、1 warning**，退出码 0。
- `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/test_spec027_backend_research_slice.py`：通过。
- `git diff --check`：通过。

新增 focused 用例覆盖：阶段边界软预算耗尽时禁止新增 Re-plan、稳定 `budget_exhausted` 事件/限制摘要，以及 search/evaluate/critic/synthesizer 的升级事件安全投影。

## 未完成项

- 未新增独立测试文件；新增 focused 用例均补在既有 `tests/test_spec027_backend_research_slice.py`。完整 Spec027 全量回归、最终验收、部署与运行时 smoke 仍由 Task06 收口。

## Task05 定向测试补充（本轮）

### 新增固定样本

- `EndToEndTests.test_replan_adds_version_and_preserves_completed_work_items`：使用按
  facet 返回的固定假 searcher，首轮只选中一个 facet，Re-plan 补搜让既有目录 ID 命中缺口；
  覆盖任务收敛、计划版本、旧 WorkItem 不覆盖、Re-plan WorkItem、payload 安全字段及
  `max_replan_rounds` 上限。
- `EndToEndTests.test_replan_stops_on_no_new_evidence_within_budget`：补充
  `no_new_evidence` 停止语义与 Re-plan 上限断言。

### 验证结果

- `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py -q`：**91 passed、1 failed、5 subtests passed、1 warning**，退出码 1。
- `.venv/bin/ruff check tests/test_spec027_backend_research_slice.py`：通过。
- `git diff --check`：通过。

### 阻塞

新增主 Re-plan 用例的业务收敛、计划版本、状态、WorkItem 和 `no_new_evidence` 断言均通过，
但安全 payload 合同失败：当前 `orchestrator.py` 的初始 `plan` 事件没有
`replan_round` / `stop_reason`；Re-plan 的 `plan` 事件虽有 `replan_round`，仍没有
`stop_reason`。按本轮只允许修改测试与报告的边界，未修改业务代码；该用例保持失败，待后续
业务修复后重跑上述定向命令。

## 合同失败修复结果

- `backend/app/research/application/orchestrator.py`：首轮 `plan` 事件补充真实的
  `replan_round=0`、`stop_reason="replan_pending"`；Re-plan `plan` 事件补充当前轮次和
  同一稳定的 `replan_pending`，保留原有字段与流程不变。
- `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py -q`：**92 passed、0 failed、5 subtests passed、1 warning**，退出码 0。
- `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/test_spec027_backend_research_slice.py`：通过。
- `git diff --check`：通过。

## 当前未完成项

- 未覆盖真实 Ollama fast 失败与 strong 重试；当前使用可注入 Router 接缝验证事件投影，默认确定性骨架不主动发起 LLM 调用。
- 完整 Spec027 全量回归、最终验收、真实 USENIX/DBLP/Ollama 与 390px 浏览器 smoke 仍由 Task06 收口。

## Task05 收口复验（2026-09-13）

### 决策

本轮不补业务代码。`ModelRouter.execute` 已实现 fast 首次失败 → fast 重试一次 → strong 的真实路由算法；`Orchestrator` 的生产骨架按 Spec027 明确的确定性评估/覆盖/报告合同运行，模型路由作为可注入调用接缝并投影安全 `MODEL_ESCALATED` 事件，不在本 Task 新建第二套模型客户端。`CatalogSearchAdapter` 已通过唯一受控入口惰性装配既有 Spec015 `CatalogSearchGraph`/`CatalogRagAdapter`；无来源时诚实降级，有固定来源时进入既有 Graph，未发现需要第二套目录或 RAG 实现的缺口。

### 固定样本与真实环境结果

- 固定路由样本使用已安装模型名 `qwen3.5:9b`、`qwen3.8:27b-mlx` 驱动 `ModelRouter`：调用序列为 `fast, fast, strong`，最终选择 `strong/qwen3.8:27b-mlx`，事件为 `MODEL_ESCALATED`（含固定升级原因）。这证明真实 `ModelRouter` 实现的升级分支，不伪称为 Ollama 推理成功。
- 真实 Ollama 只读探测（`get_available_models()` 与 `chat_direct(..., think=False, num_predict=1)`）均被环境阻断：`http://0.0.0.0:11434` 连接返回 `ConnectError [Errno 1] Operation not permitted`；没有把 CLI 的本地模型清单或失败请求记作服务成功。
- 固定目录装配样本使用真实 `CatalogSearchAdapter`、`CatalogRagAdapter`、`CatalogSearchGraph` 与临时 `PaperDiscoveryStore`，注入不触网的 fixed source/RAG failure seam：无 source 返回 `SearchOutcome((), 0, degraded=True, error_code='SOURCE_DEGRADED')`；固定 source 分支返回 `('fixed-catalog-1',), count=1, degraded=False`。这证明装配与诚实降级路径，不冒充 USENIX/DBLP 网络成功。

### 验证命令与结果

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py -q` | 退出码 0；95 passed、5 subtests passed（2.18s） |
| `ollama list` | 退出码 0；本机 CLI 列出 11 个已安装模型，不能证明 HTTP 服务可达 |
| `OLLAMA_BASE_URL=http://0.0.0.0:11434 PYTHONPATH=. .venv/bin/python docs/sdd/plans/027/artifacts/task-05/task05-close-probe.py` | 退出码 0；固定路由与 Adapter 通过；真实 `/api/tags`、`/api/chat` 如实记录环境阻断 |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py` | 退出码 0 |
| `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/test_spec027_backend_research_slice.py` | 退出码 0 |
| `git diff --check` | 退出码 0 |

### 当前状态与交接

Task05 可标记为 **已完成（固定样本通过；真实 Ollama/外部来源环境延期）**。真实 USENIX/DBLP/Ollama、浏览器、全量回归和部署仍是 Task06 的范围；复验步骤是先恢复 `OLLAMA_BASE_URL` 对应服务可达，再运行同一只读探针并记录 `/api/tags`、`/api/chat` 的真实响应，禁止用 CLI 模型清单替代 HTTP 证据。可重跑探针：`docs/sdd/plans/027/artifacts/task-05/task05-close-probe.py`。耗时：2026-09-13 03:39:28+08:00–03:40:43+08:00，约 1 分 15 秒。执行 Agent：当前任务 Agent；模型/上下文：自身（上下文上限 200k）；本轮工具统计详见主 Agent 回传（含定向 pytest、`ollama list`、固定探针与文档校验），未调用网络搜索、未调用子 Agent；业务代码改动：0。
