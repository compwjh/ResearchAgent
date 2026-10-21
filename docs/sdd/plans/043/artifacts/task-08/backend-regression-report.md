# Spec043 Task08 后端回归修复交接报告

## 结论

本轮修复 API 模块边界失败及独立 review 发现的 application runtime P1。使用项目显式解释器并保留完整 conftest 后，完整 API boundary + literature-map binding + analysis API 精准集合共 18 项全部通过。inventory 仅完成只读审计，closure 仍因候选文件与冻结矩阵不一致而失败，等待 KB agent 与 root 在最终候选上统一重算。

## 范围与根因

### 1. API 直接依赖 literature-map infrastructure

- 根因：`routes_conversations.py` 直接构造 `LiteratureMapStore`/读取 `default_database_path`；`routes_literature_maps.py` 直接导入 `LiteratureMapStoreError`。该依赖方向违反既有 `api → application → domain/infrastructure` 契约。
- 修复：
  - 新增 [`backend/app/literature_maps/domain/errors.py`](/Users/wjh/ResearchAgent/backend/app/literature_maps/domain/errors.py)，将稳定的 `LiteratureMapStoreError` 放到领域边界；infrastructure store 复用该定义，保留原模块导出兼容性。
  - 在 [`backend/app/literature_maps/application/runtime.py`](/Users/wjh/ResearchAgent/backend/app/literature_maps/application/runtime.py) 新增 `read_map_conversation_binding(conversation_id, owner_id)` 应用门面，封装路径解析、无数据库时不创建文件、owner-scoped 绑定读取和只读 `MapAnalysisService` 构造。
  - [`backend/app/api/routes_conversations.py`](/Users/wjh/ResearchAgent/backend/app/api/routes_conversations.py) 的 `_read_map_conversation_binding` 改为调用 application 门面；保留原测试替身点、fail-closed 行为和调用参数。
  - [`backend/app/api/routes_literature_maps.py`](/Users/wjh/ResearchAgent/backend/app/api/routes_literature_maps.py) 从 domain 导入 `LiteratureMapStoreError`。
- 未改变：API 错误码/错误体、CAS revision、幂等合同、owner 参数、地图 runtime 启动/恢复路径。

### 1.1 独立 review P1：application helper 缺少路径导入

- 根因：`application/runtime.py:223` 的 `read_map_conversation_binding()` 调用 `default_database_path()`，但 runtime 只导入了 `LiteratureMapStore`，未导入该既有 store 路径接口；此前只覆盖替身路径的 10 项测试未触发真实 helper，导致 `NameError` 被漏检。
- 红灯补测：新增 3 个不 monkeypatch helper 本体的真实临时 DB 测试，覆盖无文件不创建、已有绑定正常读取与 owner 隔离、存储错误经真实 `_message_stream` fail-closed。修复前结果 `2 failed, 1 passed`，前两项准确报告 `NameError: default_database_path is not defined`。
- 修复：在 runtime 既有 infrastructure store import 中加入 `default_database_path`，不改 helper 逻辑或 API 合同。
- 绿灯：新增 3 项 `3 passed in 1.06s`；完整 boundary + binding + analysis API 精准集合 `18 passed in 3.68s`。

### 2. KB inventory hash 不一致（本轮不修改）

- 根因：Task08 候选已包含其他接缝变更，冻结矩阵 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 的八个文件 hash 尚未与最终候选同步。
- 本轮只读审计结果（审计时间 2026-10-22）：

| 冻结文件 | 当前 SHA-256 | 矩阵 SHA-256 | 结果 |
|---|---|---|---|
| `backend/app/main.py` | `efdf81a23b77646edebd1f61af717c23116d2a2535cfbde0fc53c220d5bf4a47` | `43a41025609611fb959c3305c6ef6af8743883d7947f8c397c16a5925d7f0fff` | 不一致 |
| `backend/app/api/routes_kb.py` | `e595e901f12e2b8918e13a3e3204ff2a53ffcad2e1e3faf613c5ff8b9d4f7d0d` | 同左 | 一致 |
| `backend/app/api/routes_paper.py` | `44f344f8ced34f0dbfd310ffd9189ddc0ee3a4c8c8fcdb3d1ccb4bb0607508af` | `20232f5358dcd6318b18b3b7f705966891ea8698c7ffc5fae9de45172aea25f6` | 不一致 |
| `backend/app/knowledge_base/application.py` | `3edeb07ab77b4d9db3f55535b35175bde45fff0b55ed9bb398f5ffa12ccb0368` | `574112e82b5140d41bf6e572e1bdecae5881e5ec09c7818cb12c1bdff5e93ae5` | 不一致 |
| `backend/app/knowledge_base/infrastructure/store.py` | `d6fc6431ea7e55e4ed460e1869c52b19778414baf5c0e4ec199c54bb67922dcf` | 同左 | 一致 |
| `backend/app/knowledge_base/infrastructure/index.py` | `066dcbc027aa04f7d3a192d2a07f0d7466108d0e867d0987e3903e2faa1db952` | `ee0b6295c1e78ae4f528623dd5f6a760fd860778a05d022276756ba521228404` | 不一致 |
| `backend/app/knowledge_base/infrastructure/tasks.py` | `860f5f0117fff4c11c1d96317f43f2d02f68e69e4282e0876fcd9598e99c744e` | 同左 | 一致 |
| `backend/app/paper_discovery/application/paper_import.py` | `42d1eb879f0176d76794aa32e38416180dbf489c56a0a166e752e0bceaee95d7` | 同左 | 一致 |

- `main.py` 的 AST 写入口扫描仅命中 `main.index`，该符号已在现有 allowlist；`main.lifespan` 的启动恢复/预热/能力调度编排是已登记的生命周期入口，不应因 literature-map 恢复新增 KB entry。
- `index.py` 当前扫描到 `_normalize_index_error`、`_canonical_index_record`、`_mark_index_failed` 三个矩阵未登记符号。其中 `_mark_index_failed` 会发布失败状态、写入 metadata/marker，应由 KB 修复 agent 判断并注册为写入口；前两个是错误归一/规范记录判定 helper，若不作为独立入口，应由最终矩阵生成协议加入明确 allowlist。另有当前已登记/允许的入口均通过。
- 建议：待另一 KB 修复完成后，由 root 对八个 `inventory_files` 一次性重算 hash 与 `inventory_digest`，并根据最终 AST 结果注册上述真实写入口；不要仅更新 `main.py`，也不要删掉 inventory 断言。

## 验证记录

项目显式解释器 `/Users/wjh/ResearchAgent/.venv/bin/python` 的 `sys.prefix` 为 `/Users/wjh/ResearchAgent/.venv`，且 `fastapi`、`langchain_ollama`、`pytest` 均可用。此前使用 `source .venv/bin/activate` 会因 activate 脚本内保留历史路径 `/Users/wjh/PyCharmMiscProject/.venv` 而回退到 `/opt/anaconda3/bin/python`，产生缺依赖的无效 collection error；该错误不是项目 venv 损坏。本次复测均显式调用项目解释器，未安装依赖、未读取 `.env`、未启动/停止服务。

| 命令 | 退出码 | 结果/计数 |
|---|---:|---|
| `source .venv/bin/activate && python -m pytest -q ...`（历史无效环境记录） | 1 | 实际使用 `/opt/anaconda3/bin/python`，setup 2 errors：缺 `langchain_ollama`；不作为项目测试结论 |
| `PYTHON_DOTENV_DISABLED=1 .../.venv/bin/python -m pytest -q tests/system/test_api_module_boundaries.py::test_api_does_not_import_infrastructure tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py -o cache_dir=... --basetemp=...`（修复后，完整 conftest） | 0 | 10 passed in 1.81s；边界 1、绑定 7、分析 API 2 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered -o cache_dir=... --basetemp=...`（未改矩阵） | 1 | 1 failed；真实首个不一致为 `backend/app/main.py` hash |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/domain/errors.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/runtime.py backend/app/api/routes_conversations.py backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_conversation_binding.py` | 0 | 6 个改动 Python 文件语法通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/system/test_api_module_boundaries.py::test_api_does_not_import_infrastructure tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py` | 0 | 10 tests collected |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/system/test_api_module_boundaries.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py`（P1 修复后） | 0 | 18 tests collected |

P1 修复后的完整精准复测使用临时目录 `/private/tmp/spec043-map-regression-review-SS4LoD`，命令未使用 `--confcutdir` 或禁插件：

```text
PYTHON_DOTENV_DISABLED=1 \
KB_DIR=/private/tmp/spec043-map-regression-review-SS4LoD/data/kb \
QDRANT_PATH=/private/tmp/spec043-map-regression-review-SS4LoD/data/kb/qdrant \
KB_META_PATH=/private/tmp/spec043-map-regression-review-SS4LoD/data/kb/papers.json \
MEMORY_DB_PATH=/private/tmp/spec043-map-regression-review-SS4LoD/data/memory/memory.sqlite3 \
LITERATURE_MAP_DB_PATH=/private/tmp/spec043-map-regression-review-SS4LoD/data/literature_maps/literature_maps.sqlite3 \
RESEARCH_DB_PATH=/private/tmp/spec043-map-regression-review-SS4LoD/data/research/research.sqlite3 \
AGENT_TASKS_DB=/private/tmp/spec043-map-regression-review-SS4LoD/data/agent_tasks/agent_tasks.sqlite3 \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-map-regression-review-SS4LoD/data/paper-search/state.sqlite3 \
ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-map-regression-review-SS4LoD/data/articles \
PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-map-regression-review-SS4LoD/data/browser-profile \
LANGFUSE_ENABLED=false \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/system/test_api_module_boundaries.py \
  tests/literature_maps/test_map_conversation_binding.py \
  tests/literature_maps/test_map_analysis_api.py \
  -o cache_dir=/private/tmp/spec043-map-regression-review-SS4LoD/pytest-cache \
  --basetemp=/private/tmp/spec043-map-regression-review-SS4LoD/pytest-tmp
```

输出：`.................. [100%]`、`18 passed in 3.68s`、退出码 `0`。其中 binding 文件包含新增的 3 个真实 helper 回归测试。

显式解释器复测使用的完整隔离命令（临时目录为 `/private/tmp/spec043-map-regression-KmoZwW`；未使用 `--confcutdir` 或禁插件）：

```text
PYTHON_DOTENV_DISABLED=1 \
KB_DIR=/private/tmp/spec043-map-regression-KmoZwW/data/kb \
QDRANT_PATH=/private/tmp/spec043-map-regression-KmoZwW/data/kb/qdrant \
KB_META_PATH=/private/tmp/spec043-map-regression-KmoZwW/data/kb/papers.json \
MEMORY_DB_PATH=/private/tmp/spec043-map-regression-KmoZwW/data/memory/memory.sqlite3 \
LITERATURE_MAP_DB_PATH=/private/tmp/spec043-map-regression-KmoZwW/data/literature_maps/literature_maps.sqlite3 \
RESEARCH_DB_PATH=/private/tmp/spec043-map-regression-KmoZwW/data/research/research.sqlite3 \
AGENT_TASKS_DB=/private/tmp/spec043-map-regression-KmoZwW/data/agent_tasks/agent_tasks.sqlite3 \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-map-regression-KmoZwW/data/paper-search/state.sqlite3 \
ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-map-regression-KmoZwW/data/articles \
PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-map-regression-KmoZwW/data/browser-profile \
LANGFUSE_ENABLED=false \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/system/test_api_module_boundaries.py::test_api_does_not_import_infrastructure \
  tests/literature_maps/test_map_conversation_binding.py \
  tests/literature_maps/test_map_analysis_api.py \
  -o cache_dir=/private/tmp/spec043-map-regression-KmoZwW/pytest-cache \
  --basetemp=/private/tmp/spec043-map-regression-KmoZwW/pytest-tmp
```

输出：`.......... [100%]`、`10 passed in 1.81s`、退出码 `0`。closure 复测使用同样的环境变量与 `/Users/wjh/ResearchAgent/.venv/bin/python`，仅目标替换为 `tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered`，输出 `1 failed`、退出码 `1`，首个真实断言为 `backend/app/main.py` hash。

## 交给 root 的独立复审关注点

1. 复核并可在有效项目依赖环境中重跑地图绑定生命周期与地图 API 精准测试；本轮已验证新增 application 门面保持“无数据库不创建、绑定按 owner 查询、存储异常 fail-closed、分析服务只读构造”。
2. 复核 `routes_conversations.py` 与 `routes_literature_maps.py` 的 AST import，确认 API 不再直接引用任何 `.infrastructure`，且 `LiteratureMapStoreError` 的原 infrastructure 导出兼容仍在。
3. 复核 `runtime.py` 的显式 `default_database_path` import 与新增 3 项真实临时 DB 测试，确认无 helper 自身 monkeypatch。
4. 与 KB 修复 agent 的最终候选合并后重新执行 inventory AST/hash 协议；本报告中的 hash 只代表本次审计时状态，不是可直接发布的最终矩阵。

## 改动文件

- `backend/app/literature_maps/domain/errors.py`
- `backend/app/literature_maps/infrastructure/store.py`
- `backend/app/literature_maps/application/runtime.py`
- `backend/app/api/routes_conversations.py`
- `backend/app/api/routes_literature_maps.py`
- `tests/literature_maps/test_map_conversation_binding.py`

进展日志：`.codebuddy/agent-logs/spec-043/task-08/backend-dev/20261021-235900.md`
