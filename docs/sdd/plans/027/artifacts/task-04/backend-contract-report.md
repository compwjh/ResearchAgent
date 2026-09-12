# Spec027 Task04 后端合同修复交接报告

## 状态

已完成。合同修复本身仍仅涉及两个后端代码文件；本次追加了后端定向合同测试。未修改前端、长期模型配置、AGENTS.md、MODEL_REGISTRY 或 `.codebuddy/agents` 定义。

## 修改文件

- `backend/app/api/routes_research.py`
  - `GET /api/research-tasks/{id}/report` 在现有 service owner 校验成功后，通过 `research_store.list_selections()` 读取论文选集。
  - 新增安全 `facets_json` 解析；异常或非数组退化为空数组。
  - 返回 `selections`，每项仅包含 `catalog_paper_id`、`relevance`、`facets`、`evidence_level`、`created_at`，不复制论文元数据。
  - 选集读取异常复用 `SOURCE_UNAVAILABLE` / 503 稳定错误出口并记录服务端日志。

- `backend/app/research/application/orchestrator.py`
  - worker 事件统一从状态更新后返回的 WorkItem 构造，补齐实际存在的 `model_tier`、`resolved_model`、`worker_slot`。
  - 覆盖 `search_catalog`、`evaluate_papers`、`check_coverage`、`synthesize_preliminary_report` 的 running/completed/failed 事件路径；空字段省略。
  - 不写入 Prompt、思维链或原始模型协议，不改变状态机、额度释放、复用接缝和错误码语义。

- `tests/test_spec027_backend_research_slice.py`
  - 新增报告 `selections` 字段白名单测试，确认不含 `title` / `abstract`。
  - 新增真实 `ModelRouter` 注入测试，覆盖 search 的 running/completed/failed，以及 evaluate、coverage、synthesize 的稳定 running/completed 路径；断言实际 `model_tier`、`resolved_model` 与搜索 `worker_slot`。
  - 仅扩展测试构造器的可选 `model_router` 参数，默认路径保持原语义。

## 验证

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/research/application/orchestrator.py` | 通过 |
| `.venv/bin/ruff check backend/app/api/routes_research.py backend/app/research/application/orchestrator.py` | 通过，All checks passed |
| `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py -q` | 通过，88 passed，5 subtests passed，1 个既有 DeprecationWarning |
| `.venv/bin/ruff check tests/test_spec027_backend_research_slice.py` | 通过，All checks passed |
| `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py -q` | 通过，52 passed，5 subtests passed，1 个既有 DeprecationWarning |
| `git diff --check` | 通过 |

## 风险

- 未运行真实浏览器/SSE 网络 smoke；本次仅修复后端合同，Task04 前端报告已记录其自身未完成的运行时 smoke。
- 当前 Task03 的确定性骨架在未注入 model router 时不会产生实际模型字段；注入 router 后事件会携带状态更新后 WorkItem 中的真实解析结果，空值按合同省略。
