# Spec043 Task08 后端独立复审

日期：2026-10-22（Asia/Shanghai）

角色：`backend-reviewer`（只读）
范围：Task08 当前未提交 diff 中的 `domain/errors.py`、`infrastructure/store.py`、`application/runtime.py`、`api/routes_conversations.py`、`api/routes_literature_maps.py`，以及 `artifacts/task-08/backend-regression-report.md`。

明确不做：不修改业务代码、测试、服务、KB inventory/矩阵或 Git；不读取 `.env`/生产数据；不调用 provider/model；不跑全量回归。

## 结论

**BLOCK。** API 边界与稳定错误类型兼容、owner 查询条件、错误/CAS/幂等既有精准测试均通过，但新增 application 绑定读取门面存在一个可直接复现的 P1：`runtime.py` 调用 `default_database_path()` 却未导入该符号。普通会话首次走真实绑定读取路径会立即 `NameError`，因此当前候选不能进入验收收口。

## 阻塞问题

### P1：绑定读取门面缺少 `default_database_path` 导入

- `backend/app/literature_maps/application/runtime.py:13` 仅导入 `LiteratureMapStore`；`read_map_conversation_binding()` 在 `:223` 调用未定义的 `default_database_path()`。
- 独立复现命令（显式项目解释器、禁用 dotenv；路径不存在时不会触碰生产库）：

  ```text
  PYTHON_DOTENV_DISABLED=1 LITERATURE_MAP_DB_PATH=/private/tmp/spec043-review-missing-import.sqlite3 \
  .venv/bin/python - <<'PY'
  from backend.app.literature_maps.application import runtime
  try:
      runtime.read_map_conversation_binding("missing-conversation", "local-user")
  except Exception as exc:
      print(type(exc).__name__, str(exc))
  PY
  ```

  实际输出：`NameError name 'default_database_path' is not defined`。
- 这不是语法检查可发现的问题：五个改动 Python 文件 `py_compile` 均通过。
- 现有绑定测试的绿色结果不能覆盖此路径：`test_map_conversation_binding.py` 的 fail-closed/full-binding 用例替换了 routes 层 `_read_map_conversation_binding` seam；`test_map_analysis_api.py` 不走普通会话读取门面。
- 最小修复边界是让 application 门面使用可注入的 `default_database_path` 符号并重新运行本报告的精准测试；本复审不代行修改。

## 逐项核查

| 核查项 | 裁定 | 实际证据 |
|---|---|---|
| domain 稳定错误类与旧 infrastructure 导出兼容 | **GO** | `domain/errors.py:6-8` 定义 `LiteratureMapStoreError`；`store.py:25` 重新导入，因此 `store.LiteratureMapStoreError is domain.LiteratureMapStoreError`；routes_literature_maps `:15` 直接从 domain 导入，运行时身份相同。 |
| API 不再直接依赖 literature-map infrastructure | **GO** | AST 精准边界测试 6 passed；routes_conversations `:49-53` 与 routes_literature_maps `:13-16` 均无 literature-map infrastructure import。 |
| application 门面不启动完整 runtime | **GO（设计）/ BLOCK（当前不可调用）** | `runtime.py:213-229` 只解析路径、构造 store、owner-scoped 读取 confirmed binding，绑定存在时才构造 `MapAnalysisService`；但 `default_database_path` 未定义导致该门面当前不可调用。 |
| 无数据库不创建空 DB | **补充探针 GO（注入预期 path seam）** | 临时 SQLite 探针动态注入 `runtime.default_database_path` 后，路径不存在返回 `(None, None)` 且 `db_created=False`；真实当前代码先在 `:223` 抛 P1 NameError。 |
| owner scope / 跨 owner 隔离 | **GO（store）/ 门面被 P1 阻断** | `store.py:1057-1060` 的查询同时限定 `conversation_id`、`owner_id`、`status='confirmed'`；临时库探针在注入 path 后 owner 命中返回 binding，另一 owner 返回 `(None, None)`。 |
| fail-closed | **GO（route 行为）** | `_message_stream` 捕获绑定读取异常并发出 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE`、终态 `failed`；`test_binding_lookup_failure_blocks_project_wide_rag_fallback` 在绑定测试中通过。门面本身保留存储异常向上抛出，符合该 route catch seam。 |
| 路由旧替身接缝与参数 | **GO（routes seam）/ P1 影响 runtime seam** | routes_conversations `:107-116` 保留 `_read_map_conversation_binding(conversation_id, owner_id)`；现有 tests 对该 seam 的 patch 通过。原 route 层 `LiteratureMapStore`/`default_database_path` 名称因边界修复已移除；application 层应提供可 patch 的 path seam，但当前遗漏导入。 |
| API error contract | **GO** | `test_map_api_errors.py` 10 passed；`routes_literature_maps.py:144-180` 的稳定错误映射未被本次 diff 改动。 |
| CAS / revision | **GO** | `test_map_revision_conflicts.py` 2 passed，`test_map_api.py` 1 passed；本次 diff 未改 mutation 调用参数或 expected_revision。 |
| 幂等 | **GO（既有路径）** | `test_map_analysis_api.py` 2 passed，覆盖分析 job 与 conversation idempotency；`test_map_conversation_binding.py` 7 passed，覆盖 binding reservation/reuse；本次 diff 未改 idempotency 参数传递。 |

## 精准验证

项目显式解释器检查：`.venv/bin/python` 的 `sys.executable` 为项目 venv；`fastapi 0.141.1`、`pytest 9.1.1`、`langchain_ollama` 均可导入。所有 pytest 命令均使用 `PYTHON_DOTENV_DISABLED=1` 与 `/private/tmp/spec043-backend-review-final` 隔离数据目录；未 source activate、未安装依赖、未启动/停止服务。

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `PYTHON_DOTENV_DISABLED=1 ... .venv/bin/python -m pytest -q --confcutdir=tests/system tests/system/test_api_module_boundaries.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_revision_conflicts.py tests/literature_maps/test_map_api.py -o cache_dir=/private/tmp/spec043-backend-review-final/pytest-cache --basetemp=/private/tmp/spec043-backend-review-final/pytest-tmp` | 0 | **28 passed in 4.54s**（边界 6、绑定 7、分析 API 2、error 10、revision 2、基础 API 1） |
| `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m py_compile backend/app/literature_maps/domain/errors.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/runtime.py backend/app/api/routes_conversations.py backend/app/api/routes_literature_maps.py` | 0 | 5 个改动 Python 文件语法通过；不能捕获上述运行时未定义名称 |
| `PYTHON_DOTENV_DISABLED=1 LITERATURE_MAP_DB_PATH=/private/tmp/spec043-review-missing-import.sqlite3 .venv/bin/python` 直接调用 `runtime.read_map_conversation_binding(...)` | 0（探针捕获异常） | **复现 `NameError`**：`default_database_path` 未定义 |
| 临时 SQLite 行为探针（动态注入 `runtime.default_database_path`，未写入仓库） | 0 | 无库不创建、同 owner 命中、跨 owner 隐藏、`LiteratureMapStoreError` 向 route seam 传播均通过；仅作为 P1 修复后的行为参考，不抵消当前缺失导入 |

## 最终裁定

**BLOCK。** 需由 backend-dev 补齐 application runtime 的 `default_database_path` 接缝（并保留可注入性），然后由 backend-reviewer 重跑至少上述 28 项精准测试和真实门面调用探针。当前未修改任何实现、测试、服务或 Git。

复审进展日志：`.codebuddy/agent-logs/spec-043/task-08/backend-reviewer/20261022-000000.md`

## P1 修复窄复审（2026-10-22）

### 当前结论

**GO（仅针对本报告上一节的 application runtime P1 与 API 绑定接缝）。** 上一轮 BLOCK 的缺失导入已补齐；新增真实 helper 测试与真实 `_message_stream` fail-closed 路径均通过，未发现新的漏依赖或本范围阻塞。该 GO 不代表 Spec043/Task08 全量收口，也不闭合 root 提到的既有 compaction failure、KB inventory、真实服务或全量回归门禁。

### 修复与逐项裁定

| 核查项 | 当前裁定 | 实际证据 |
|---|---|---|
| `default_database_path` 导入与可调用性 | **GO** | `backend/app/literature_maps/application/runtime.py:13` 现显式导入 `LiteratureMapStore, default_database_path`；独立解释器检查 `callable(runtime.default_database_path)` 为 `True`。 |
| 无数据库不创建空 DB | **GO** | 新增真实测试 `test_read_map_conversation_binding_does_not_create_missing_database` 未替换 helper 本体，仅设置临时 `LITERATURE_MAP_DB_PATH`；断言返回 `(None, None)` 且目标文件不存在。 |
| owner scope | **GO** | 新增真实测试创建 owner-a 的 map/node/binding，经真实 `_read_map_conversation_binding` 读取 owner-a 得到 binding 与 analysis，owner-b 得到 `(None, None)`；底层 `store.py:1057-1060` 仍以 `conversation_id + owner_id + confirmed` 查询。 |
| 实际 `_message_stream` fail-closed | **GO** | 新增 `test_api_map_binding_storage_error_fails_closed_without_rag_fallback` 创建“数据库路径为目录”的存储错误，不替换 helper 或 `_message_stream`；实际事件含 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE`，终态为 `failed`，assistant 消息状态为 `failed`。 |
| domain 错误类兼容 | **GO** | `store.LiteratureMapStoreError is domain.LiteratureMapStoreError` 与 `routes_literature_maps.LiteratureMapStoreError is domain...` 均为 `True`。 |
| API infrastructure 依赖 | **GO** | AST 检查 routes_conversations/routes_literature_maps 的 literature-map infrastructure import 行均为空；完整边界测试通过。 |

### 独立精准验证

所有 pytest 使用项目 `.venv/bin/python`、`PYTHON_DOTENV_DISABLED=1` 和 `/private/tmp/spec043-backend-review-r2` 临时数据目录；未 source activate、未读取 `.env`、未启动/停止服务。

| 命令/探针 | 退出码 | 实际结果 |
|---|---:|---|
| `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/literature_maps/test_map_conversation_binding.py -k 'read_map_conversation_binding_does_not_create_missing_database or api_map_conversation_binding_read_is_owner_scoped or api_map_binding_storage_error_fails_closed_without_rag_fallback'` | 0 | **3 passed, 7 deselected in 1.05s**；三项均为真实 helper/真实 stream 路径，未 monkeypatch helper 本体。 |
| `PYTHON_DOTENV_DISABLED=1 ... .venv/bin/python -m pytest -q tests/system/test_api_module_boundaries.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py -o cache_dir=/private/tmp/spec043-backend-review-r2/pytest-cache --basetemp=/private/tmp/spec043-backend-review-r2/pytest-tmp` | 0 | **18 passed in 3.50s**。 |
| 显式解释器 import/AST 探针 | 0 | `runtime_default_path_imported True`；稳定错误类身份 `True True`；两个 API 路由 infrastructure import 行均为空。 |
| `.venv/bin/python -m py_compile`（5 个实现文件 + 新增绑定测试） | 0 | 通过。 |

### 复审边界

- 本轮只裁定上一轮 P1 修复及绑定接缝；保留上一轮 BLOCK 原文作为历史证据。
- root 提到的全量回归中既有 compaction failure（发生在本次缺失导入修复前）未在本轮诊断或闭合；不把 import 修复等同于该问题已解决。
- 未运行服务、真实部署 API、KB inventory/full regression 或其他端职责验证。

窄复审结论：**GO（P1 修复范围）**。复审进展日志仍为：`.codebuddy/agent-logs/spec-043/task-08/backend-reviewer/20261022-000000.md`。

## Compaction threshold 测试隔离增量复审（2026-10-22）

### 范围与结论

本轮仅复审 `tests/conversation/test_conversation_context_usage_api.py` 的未提交测试隔离 diff，以及 `backend-regression-report.md` 中关于 `GET used=3754 → POST est_tokens_before=3804` 异步 memory worker 竞态的最新记录。未修改 production compaction/memory 逻辑、服务、Git 或其他测试。

**GO（测试隔离增量）。** 原失败由异步 `MemoryAnalysisWorker` 在阈值检查前写入隔离 `MEMORY.md` 导致，不是地图 API 或生产阈值逻辑回归。新增 `_StableBackgroundWorker` 只记录 `enqueue`/`enqueue_session`，不启动线程、不写 memory 文件；真实 route-side `compute_context_usage`、真实 `_message_stream`、0.79/0.80 阈值和 auto 入队断言均保留。根级 `stop_all_workers` autouse fixture 仍在每个 case 前后清理并清空 production worker cache；受控 stub 不进入该 cache。

### 独立验证

环境均为显式 `.venv/bin/python`、`PYTHON_DOTENV_DISABLED=1`、`COMPACTION_SUMMARY_MODE=rule`，所有 `KB_DIR`、`MEMORY_DB_PATH`、`LITERATURE_MAP_DB_PATH`、`RESEARCH_DB_PATH`、`AGENT_TASKS_DB`、`PAPER_DISCOVERY_DB_PATH`、下载目录和 browser profile 指向独立 `/private/tmp/spec043-compaction-review-r2/{repeat1,repeat2,full,probe}`；未读取 `.env`，未启动服务或运行 full suite。

1. `PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule ... .venv/bin/python -m pytest -q tests/conversation/test_conversation_context_usage_api.py::test_auto_compaction_threshold_boundary --basetemp=/private/tmp/spec043-compaction-review-r2/repeat1/pytest-tmp -o cache_dir=/private/tmp/spec043-compaction-review-r2/repeat1/pytest-cache`：**1 passed in 25.50s**，退出码 0。
2. 同一边界命令，仅替换为 `repeat2` 隔离根：**1 passed in 26.13s**，退出码 0。
3. `PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule ... .venv/bin/python -m pytest -q tests/conversation/test_conversation_context_usage_api.py --basetemp=/private/tmp/spec043-compaction-review-r2/full/pytest-tmp -o cache_dir=/private/tmp/spec043-compaction-review-r2/full/pytest-cache`：**13 passed in 38.56s**，退出码 0。
4. 独立请求级 SSE 探针（同一 `.venv/bin/python` 与 `probe` 隔离根）对低/高阈值各发起真实 `TestClient` POST，patch 两个 worker factory 为 `_StableBackgroundWorker`，不 patch `compute_context_usage`、`_message_stream` 或模型 stream：退出码 0。低侧 `HTTP 200`，事件序列以 `done(status=completed)` 结束，无 `error/tool_error`，auto=0；高侧同样 `done(status=completed)`、无错误，auto=1 且 `est_tokens_before=3754 == used_tokens=3754`；两 worker 分别记录 2 次入队，`MEMORY.md` 不存在。

### 边界裁定

- 两个 worker 接口 stub 只控制后台副作用，不替换被测阈值计算或生产 memory 写逻辑；高侧 auto 仍由真实 route-side `compute_context_usage` 触发。
- 低/高请求均完成完整 SSE terminal `done`，未出现仅 HTTP 200 的隐藏失败；无 error/tool_error 事件。
- 0.79 不自动压缩、0.80 恰好一次自动入队、`est_tokens_before == used_tokens` 与 memory 文件不落盘均通过。
- 本次仅关闭测试隔离竞态，不改变 API/阈值/worker 生产合同；地图 P1 修复与 KB verified 状态不在本节重复裁定。

本轮最终结论：**GO（conversation context usage 测试隔离范围）**。完整 Task08 是否收口仍由 root 依据全量、服务和其他验收门禁裁定。
