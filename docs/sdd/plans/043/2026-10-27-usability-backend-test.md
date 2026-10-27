# Spec043 Task10 后端独立验证报告

日期：2026-10-27（Asia/Shanghai）  
角色：backend-tester  
工作树：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`  
解释器：`/Users/wjh/ResearchAgent/.venv/bin/python`  
进展日志：`.codebuddy/agent-logs/spec-043/task-10/backend-tester/20261027-121515.md`

## VERIFICATION REPORT

- **Build：未运行。** 本次按委托执行后端定向测试，不做构建验证。
- **Types：未运行。**
- **Lint：未运行。**
- **Tests：通过定向 pytest；同时发现一个 API 输入校验缺陷，故 Task 后端验收暂不通过。**
- **Security：未运行。**
- **Diff：未作为后端测试角色执行独立差异评审；交由 backend-reviewer。测试期间未修改代码或测试。
- **部署/真实服务 API：未运行。** 未启动服务、访问生产 DB 或网络来源；API 行为探针只用临时 SQLite 与 TestClient，后台论文发现 job 被替换为 no-op。

### pytest 命令与结果

最终单文件命令（退出码 **0**，**6/6 passed**）：

```bash
TMPDIR=/private/tmp/spec043-task10/run-node-styles/tmp \
XDG_CACHE_HOME=/private/tmp/spec043-task10/run-node-styles/cache \
PYTHONPYCACHEPREFIX=/private/tmp/spec043-task10/run-node-styles/pycache \
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
MEMORY_DB_PATH=/private/tmp/spec043-task10/run-node-styles/memory.sqlite3 \
MEMORY_DIR=/private/tmp/spec043-task10/run-node-styles/memory-dir \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
tests/literature_maps/test_map_node_styles.py \
--basetemp=/private/tmp/spec043-task10/run-node-styles/pytest-tmp \
-o cache_dir=/private/tmp/spec043-task10/run-node-styles/pytest-cache
```

最终 literature_maps 领域回归命令（退出码 **0**，**173/173 passed**，3 条现有 jieba `DeprecationWarning`）：

```bash
TMPDIR=/private/tmp/spec043-task10/run-literature-maps-isolated/tmp \
XDG_CACHE_HOME=/private/tmp/spec043-task10/run-literature-maps-isolated/cache \
PYTHONPYCACHEPREFIX=/private/tmp/spec043-task10/run-literature-maps-isolated/pycache \
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task10/run-literature-maps-isolated/literature-maps.sqlite3 \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task10/run-literature-maps-isolated/paper-discovery.sqlite3 \
MEMORY_DB_PATH=/private/tmp/spec043-task10/run-literature-maps-isolated/memory.sqlite3 \
MEMORY_DIR=/private/tmp/spec043-task10/run-literature-maps-isolated/memory-dir \
KB_DIR=/private/tmp/spec043-task10/run-literature-maps-isolated/kb \
QDRANT_PATH=/private/tmp/spec043-task10/run-literature-maps-isolated/qdrant \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps \
--basetemp=/private/tmp/spec043-task10/run-literature-maps-isolated/pytest-tmp \
-o cache_dir=/private/tmp/spec043-task10/run-literature-maps-isolated/pytest-cache
```

### 独立契约核验

测试覆盖与额外临时 API 探针结果：

- **迁移事务回滚：通过。** `test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry` 在 173 项领域回归中通过；失败注入后可重试。新增测试文件还通过 schema v7 重启幂等及旧节点字段保留检查。
- **批量样式事务原子性：通过。** 批次包含已移除节点时，API 返回 `409 MAP_NODE_REMOVED`；已选有效节点的颜色和地图 revision 均未部分变化。
- **Owner：通过。** 不同 owner 的 store 更新被拒绝，HTTP 层沿用 owner-scoped 查询。
- **Revision：通过。** 旧 revision 更新返回 `409 MAP_CONFLICT`，未产生写入；后续以原 revision 执行节点移除成功。
- **移除节点：通过。** 返回 `409 MAP_NODE_REMOVED`，无部分颜色更新。
- **显式 null：通过。** 成功将节点 override 清空为 null，原 `group_id` 保留。
- **默认样式：通过。** 初始读取为 `{"fill_mode":"filled","fill_opacity":0.3}`。
- **GET 无业务写：通过。** list/map/graph/node/export 五个 GET 均返回 200；读取前后 SQLite `data_version`、地图 revision、事件数保持不变。
- **Export：通过。** 返回 `literature-map-export-v2`，包含节点 `color_override` 和地图 `view_settings.node_style`，测试同时确认不包含 owner、recent colors 与 preview。

临时 API 探针在 `/private/tmp/spec043-task10/manual-api-2/` 执行，生成的测试 map ID 为 `ad8079b407e243479683f54a887e0b98`；进程内导入的 `backend.__file__` 指向本工作树的 `backend/__init__.py`，未从其他 checkout 加载代码。

### 阻塞项

**需修复后再通过后端验收：** `PATCH /api/literature-maps/{map_id}/view` 的 `node_style.fill_opacity` 传 JSON 布尔值 `true` 时，Pydantic 将其强制转换为 `1.0`；API 返回 200 并保存该值。该字段应拒绝布尔值，只接受有限数值 `0..1`。本次仅记录证据，没有修改代码或测试。

### 初次运行与环境修正记录

- 首次单文件运行退出码 1：`2 passed, 4 failed`。四项均因测试夹具创建地图 API 前置返回 503 而在读取 `created["map_id"]` 时报 `KeyError`；已确认 `backend.__file__` 来自当前工作树，根因是未隔离的默认 `MEMORY_DB_PATH` 初始化失败。设置私有临时 memory DB 后同一命令重跑，6 项通过。
- 首次领域套件运行退出码 1：`159 passed, 14 failed`。失败首先由未隔离的 `PAPER_DISCOVERY_DB_PATH` 导致 `sqlite3.OperationalError: unable to open database file`，并引发部分后续 mock 状态级联。补齐论文目录、memory、地图、KB、Qdrant 与缓存路径隔离后重跑，173 项通过。
- 两次初始失败均是执行环境路径不完整的前置问题，最终报告按完整隔离后的重跑结果统计。

## 结论

**NOT READY（存在一个待修复 API 输入校验缺陷）。** 指定节点样式测试 6/6 与 literature_maps 领域测试 173/173 通过；布尔透明度仍被接受为数值。其余构建、静态类型、Lint、安全扫描、差异评审及部署验证不在本次执行范围内。

## 补充：schema 迁移回滚专项重跑

为独立复核事务回滚，再单独运行一次迁移故障注入测试；退出码 **0**，**1/1 passed**：

```bash
TMPDIR=/private/tmp/spec043-task10/run-migration-rollback/tmp \
XDG_CACHE_HOME=/private/tmp/spec043-task10/run-migration-rollback/cache \
PYTHONPYCACHEPREFIX=/private/tmp/spec043-task10/run-migration-rollback/pycache \
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task10/run-migration-rollback/literature-maps.sqlite3 \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task10/run-migration-rollback/paper-discovery.sqlite3 \
MEMORY_DB_PATH=/private/tmp/spec043-task10/run-migration-rollback/memory.sqlite3 \
MEMORY_DIR=/private/tmp/spec043-task10/run-migration-rollback/memory-dir \
KB_DIR=/private/tmp/spec043-task10/run-migration-rollback/kb \
QDRANT_PATH=/private/tmp/spec043-task10/run-migration-rollback/qdrant \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry \
--basetemp=/private/tmp/spec043-task10/run-migration-rollback/pytest-tmp \
-o cache_dir=/private/tmp/spec043-task10/run-migration-rollback/pytest-cache
```

## 修复后复验与最终结论（2026-10-27）

主会话已通知此前两项缺陷已修复且独立 review 复审解除 Block。本轮仅复跑当前节点样式测试文件与 schema 迁移回滚专项，不运行 literature_maps 全套、全仓回归、部署或生产网络。

- `tests/literature_maps/test_map_node_styles.py`：退出码 **0**，**9/9 passed**（2.06s）。当前覆盖新增的创建响应默认 `node_style`，以及 HTTP 拒绝 `fill_opacity:true` 和 `false` 两个布尔输入。
- `tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry`：退出码 **0**，**1/1 passed**（1.89s）。
- 两组测试的 SQLite、Python/pytest 缓存及临时目录均位于各自的 `/private/tmp/spec043-task10/final-rerun/` 子目录；使用 `PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false`。

节点样式命令：

```bash
TMPDIR=/private/tmp/spec043-task10/final-rerun/node-styles/tmp \
XDG_CACHE_HOME=/private/tmp/spec043-task10/final-rerun/node-styles/cache \
PYTHONPYCACHEPREFIX=/private/tmp/spec043-task10/final-rerun/node-styles/pycache \
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task10/final-rerun/node-styles/literature-maps.sqlite3 \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task10/final-rerun/node-styles/paper-discovery.sqlite3 \
MEMORY_DB_PATH=/private/tmp/spec043-task10/final-rerun/node-styles/memory.sqlite3 \
MEMORY_DIR=/private/tmp/spec043-task10/final-rerun/node-styles/memory-dir \
KB_DIR=/private/tmp/spec043-task10/final-rerun/node-styles/kb \
QDRANT_PATH=/private/tmp/spec043-task10/final-rerun/node-styles/qdrant \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
tests/literature_maps/test_map_node_styles.py \
--basetemp=/private/tmp/spec043-task10/final-rerun/node-styles/pytest-tmp \
-o cache_dir=/private/tmp/spec043-task10/final-rerun/node-styles/pytest-cache
```

迁移回滚命令：

```bash
TMPDIR=/private/tmp/spec043-task10/final-rerun/migration/tmp \
XDG_CACHE_HOME=/private/tmp/spec043-task10/final-rerun/migration/cache \
PYTHONPYCACHEPREFIX=/private/tmp/spec043-task10/final-rerun/migration/pycache \
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task10/final-rerun/migration/literature-maps.sqlite3 \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task10/final-rerun/migration/paper-discovery.sqlite3 \
MEMORY_DB_PATH=/private/tmp/spec043-task10/final-rerun/migration/memory.sqlite3 \
MEMORY_DIR=/private/tmp/spec043-task10/final-rerun/migration/memory-dir \
KB_DIR=/private/tmp/spec043-task10/final-rerun/migration/kb \
QDRANT_PATH=/private/tmp/spec043-task10/final-rerun/migration/qdrant \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry \
--basetemp=/private/tmp/spec043-task10/final-rerun/migration/pytest-tmp \
-o cache_dir=/private/tmp/spec043-task10/final-rerun/migration/pytest-cache
```

**最终结论：READY（仅限本次委托的后端定向验证范围）。** 当前 9 项节点样式测试与 1 项迁移回滚专项均通过，两个已修复缺陷对应的回归断言通过。此前报告中的 NOT READY 是修复前结论，保留为历史记录，由本节 supersede。此次未执行的 Build/Types/Lint/Security、全领域回归、Diff review 与部署验证仍不包含在本次复验结论内。
