# Task09 最终候选全量回归报告

> **当前最终结果：PASS。** 矩阵维护后的第二轮完整回归退出0：3384 passed、0 failed、2合法skip、67 subtests、5 warnings，覆盖率82.38%≥80%。下方首轮BLOCK保留为历史，不能当作当前结果。
>
> 仓库内不可覆盖证据：[首轮原始日志](task-09-runs/final-regression/attempt-1/full-regression.log)、[最终原始日志](task-09-runs/final-regression/attempt-2/full-regression.log)、[最终覆盖率JSON](task-09-runs/final-regression/attempt-2/coverage.json)、[最终覆盖率XML](task-09-runs/final-regression/attempt-2/coverage.xml)。最终日志与原临时产物SHA256均为`ce10ce49153773d4f66e8a2c5e8bdbbca0b5b429ea7973bd266911107c30d98a`。

## 首轮结论（历史）

本轮执行了代码冻结后的唯一一次全量 pytest 与覆盖率门禁。pytest 断言门禁 **BLOCKED**：1 项失败；覆盖率门槛 **PASS**：82.41% ≥ 80%。由于 pytest 退出码为 1，本轮不能作为 Spec043 验收通过或收口通过证据。

失败不是 coverage 门槛失败，而是冻结知识库上传闭环 inventory 的源文件哈希断言失败：矩阵仍记录历史的 `backend/app/knowledge_base/application.py` 哈希，当前候选工作树中的该文件已变更。tester 未修改业务代码、测试、矩阵、依赖或配置，也未重跑全量。

## 候选与隔离事实

- 分支：`codex/spec043-map-interaction`
- 候选 `HEAD`：`458da1b35238691cbe9447c71bf7a1afbb08728f`
- root 提供的当前候选源指纹：`6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`
- 工作树：保留 root 的未提交候选改动；未提交 SHA 未冒充新提交。
- 8000 端口：启动前已有 Python 进程监听；本轮未停止、重启、复用或写入该服务。
- 全新隔离根目录：`/private/tmp/spec043-task09-final-tdU1d9`
- `PaperDiscoveryStore()` 测试无参调用扫描：无命中；测试布局检查和命名检查均通过。
- 所有 SQLite、KB、Qdrant、文章下载、浏览器 profile、pytest cache/basetemp、coverage 产物均位于上述临时根目录；未设置 `MEMORY_DIR`、`RUN_E2E` 或业务模型/embedding override。`PYTHON_DOTENV_DISABLED=1` 禁止加载 `.env`。
- 浏览器：全量运行使用已批准的 Chromium 权限；未把权限失败改写为通过。真实 API、模型和部署验证不在本轮执行。

## 实际运行时间与命令

- 开始：`2026-10-24T21:08:29+08:00`
- 结束：`2026-10-24T21:20:43+08:00`
- pytest 运行时长：`732.50s`（`12m12s`）
- 退出码：`1`

实际命令（路径已展开为本轮临时根目录）：

```text
env \
  -u MEMORY_DIR -u RUN_E2E -u RERANKER_ENABLED -u OLLAMA_ROUTE \
  -u OLLAMA_MODEL -u EMBED_MODEL -u EMBED_PROVIDER \
  -u SEMANTIC_SCHOLAR_API_KEY -u SEMANTIC_SCHOLAR_ENABLED \
  PYTHON_DOTENV_DISABLED=1 \
  COMPACTION_SUMMARY_MODE=rule \
  LANGFUSE_ENABLED=false \
  KB_DIR=/private/tmp/spec043-task09-final-tdU1d9/data/kb \
  QDRANT_PATH=/private/tmp/spec043-task09-final-tdU1d9/data/kb/qdrant \
  KB_META_PATH=/private/tmp/spec043-task09-final-tdU1d9/data/kb/papers.json \
  MEMORY_DB_PATH=/private/tmp/spec043-task09-final-tdU1d9/data/memory/memory.sqlite3 \
  LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task09-final-tdU1d9/data/literature_maps/literature_maps.sqlite3 \
  RESEARCH_DB_PATH=/private/tmp/spec043-task09-final-tdU1d9/data/research/research.sqlite3 \
  AGENT_TASKS_DB=/private/tmp/spec043-task09-final-tdU1d9/data/agent_tasks/agent_tasks.sqlite3 \
  PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task09-final-tdU1d9/data/paper-search/state.sqlite3 \
  ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-task09-final-tdU1d9/data/articles \
  PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-task09-final-tdU1d9/data/browser-profile \
  COVERAGE_FILE=/private/tmp/spec043-task09-final-tdU1d9/.coverage \
  .venv/bin/python -m pytest tests -q \
    -o cache_dir=/private/tmp/spec043-task09-final-tdU1d9/pytest-cache \
    --basetemp=/private/tmp/spec043-task09-final-tdU1d9/pytest-tmp \
    --cov=backend \
    --cov-fail-under=80 \
    --cov-report=term-missing \
    --cov-report=xml:/private/tmp/spec043-task09-final-tdU1d9/coverage.xml \
    --cov-report=json:/private/tmp/spec043-task09-final-tdU1d9/coverage.json
```

未使用 `-k`、`--ignore`、`--deselect`、`--maxfail`、人工 skip、并行分片或失败排除。

## 测试计数与合法 skip

- 通过：`3383`
- 失败：`1`
- 合法 skip：`2`
- subtests：`67 passed`
- pytest warnings：`5`
- pytest 外的进程收尾警告：`sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute`

两个 skip 均来自 `tests/e2e/test_research_lifecycle_e2e.py` 的模块级门禁，原因是本轮明确未设置 `RUN_E2E=1`，且该集合要求已启动后端服务 `:8000`；未新增或伪造 skip：

- `test_research_task_create_shows_in_list`
- `test_research_lifecycle_follow_through`

## 失败诊断

失败 nodeid：

```text
tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered
```

失败位置：`tests/kb/test_kb_upload_closure_matrix.py:81`。冻结矩阵为 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`，具体不一致为：

- 文件：`backend/app/knowledge_base/application.py`
- 矩阵期望 SHA-256：`3edeb07ab77b4d9db3f55535b35175bde45fff0b55ed9bb398f5ffa12ccb0368`
- 当前候选实际 SHA-256：`222bece39de4bd36aa0b033e96995292263fdc11e15557d48ba39b0af896a244`

该失败属于 pytest 的确定性源指纹断言，不属于环境 skip，也不属于 coverage 门槛失败。根据本轮 tester 边界未更新冻结矩阵、未回滚候选改动、未修改测试或业务代码；后续是否按架构师裁决更新矩阵或调整候选，留给 root 的同范围修复与复审流程。

## 覆盖率门禁

- 语句数：`45652`
- 已覆盖：`37620`
- 未覆盖：`8032`
- 总覆盖率：`82.40602821344082%`（终端显示 `82.41%`）
- `--cov-fail-under=80`：达到，coverage gate **PASS**
- XML：[`coverage.xml`](/private/tmp/spec043-task09-final-tdU1d9/coverage.xml)
- JSON：[`coverage.json`](/private/tmp/spec043-task09-final-tdU1d9/coverage.json)

按未覆盖行数排序的后续风险模块（仅供后续定向补测，不在本轮擅自补测）：

1. `backend/app/research/infrastructure/research_store.py`：722 行未覆盖，76.06%。
2. `backend/app/api/routes_research.py`：401 行未覆盖，62.17%。
3. `backend/app/literature_maps/application/service.py`：283 行未覆盖，75.35%。
4. `backend/app/api/routes_conversations.py`：272 行未覆盖，78.33%。
5. `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`：271 行未覆盖，79.81%。
6. `backend/app/api/routes_paper.py`：224 行未覆盖，75.49%。
7. `backend/app/api/routes_kb.py`：167 行未覆盖，70.80%。
8. `backend/app/paper_discovery/application/paper_import_batch_service.py`：151 行未覆盖，74.41%。
9. `backend/app/literature_maps/application/analysis.py`：127 行未覆盖，78.47%。
10. `backend/app/api/routes_literature_maps.py`：116 行未覆盖，70.78%。

覆盖率达到门槛不抵销上述单项 pytest 失败，也不代表这些模块的未覆盖分支已经验收。

## 原始证据

- 完整原始日志：[`full-regression.log`](/private/tmp/spec043-task09-final-tdU1d9/full-regression.log)
- 日志记录的开始/结束时间、候选 SHA、实际退出码和完整 pytest/coverage 输出均保留在临时根目录。
- 本轮未部署服务、未运行真实 API 写入、未调用模型、未执行 git 写操作。

## 第二轮：冻结矩阵最小修复后的最终重跑

首轮失败后，root 按既有 Spec018 Task04 维护规约完成了最小矩阵修复；本节追加记录第二轮，不覆盖首轮 `3383 passed / 1 failed / 82.41%` 证据。修复仅更新以下两项：

- `backend/app/knowledge_base/application.py` 的 inventory SHA-256：更新为 `222bece39de4bd36aa0b033e96995292263fdc11e15557d48ba39b0af896a244`。
- `inventory_digest`：更新为 `38af1e9c3ea0eebd2315485e6ccfc2141ef8ea0c09f386b125d8f7bb1cb378e0`。

root 在重跑前已完成矩阵定向 `2 passed`、KB boundary `8 passed` 和 root diff check `0`；本轮没有修改生产代码、测试、依赖、服务或真实数据。

### 第二轮候选与隔离事实

- 分支：`codex/spec043-map-interaction`
- 候选 `HEAD`：`458da1b35238691cbe9447c71bf7a1afbb08728f`
- root 提供的候选源指纹：`6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`
- 工作树仍为未提交候选；未提交 SHA 未冒充新提交。
- 矩阵文件 SHA-256：`9af817a5231a44ff25bc5096efdfd4c8c4ca712c56450e013875ee17b5134e24`
- 矩阵二进制 diff SHA-256：`edd627a45000fee17b6b87f1d589b3adf780d107cfd1cd834c9948a3aad180f3`
- 8000 端口：已有 Python 进程监听；本轮未停止、重启、复用或写入。
- 新隔离根目录：`/private/tmp/spec043-task09-final-rerun-Are9OK`
- `PaperDiscoveryStore()` 测试无参调用扫描仍无命中；测试布局/命名检查仍通过。
- 所有 SQLite、KB、Qdrant、文章下载、浏览器 profile、pytest cache/basetemp、coverage 产物均位于新临时根目录。未设置 `MEMORY_DIR`、`RUN_E2E` 或业务模型/embedding override，`PYTHON_DOTENV_DISABLED=1` 生效。

### 第二轮实际命令与运行时间

- 开始：`2026-10-24T21:25:27+08:00`
- 结束：`2026-10-24T21:37:09+08:00`
- pytest 运行时长：`700.49s`（`11m40s`）
- 退出码：`0`

第二轮仍执行完整 `tests` 集合，命令与首轮相同，仅将所有临时路径替换为新根目录：

```text
env \
  -u MEMORY_DIR -u RUN_E2E -u RERANKER_ENABLED -u OLLAMA_ROUTE \
  -u OLLAMA_MODEL -u EMBED_MODEL -u EMBED_PROVIDER \
  -u SEMANTIC_SCHOLAR_API_KEY -u SEMANTIC_SCHOLAR_ENABLED \
  PYTHON_DOTENV_DISABLED=1 \
  COMPACTION_SUMMARY_MODE=rule \
  LANGFUSE_ENABLED=false \
  KB_DIR=/private/tmp/spec043-task09-final-rerun-Are9OK/data/kb \
  QDRANT_PATH=/private/tmp/spec043-task09-final-rerun-Are9OK/data/kb/qdrant \
  KB_META_PATH=/private/tmp/spec043-task09-final-rerun-Are9OK/data/kb/papers.json \
  MEMORY_DB_PATH=/private/tmp/spec043-task09-final-rerun-Are9OK/data/memory/memory.sqlite3 \
  LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task09-final-rerun-Are9OK/data/literature_maps/literature_maps.sqlite3 \
  RESEARCH_DB_PATH=/private/tmp/spec043-task09-final-rerun-Are9OK/data/research/research.sqlite3 \
  AGENT_TASKS_DB=/private/tmp/spec043-task09-final-rerun-Are9OK/data/agent_tasks/agent_tasks.sqlite3 \
  PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task09-final-rerun-Are9OK/data/paper-search/state.sqlite3 \
  ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-task09-final-rerun-Are9OK/data/articles \
  PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-task09-final-rerun-Are9OK/data/browser-profile \
  COVERAGE_FILE=/private/tmp/spec043-task09-final-rerun-Are9OK/.coverage \
  .venv/bin/python -m pytest tests -q \
    -o cache_dir=/private/tmp/spec043-task09-final-rerun-Are9OK/pytest-cache \
    --basetemp=/private/tmp/spec043-task09-final-rerun-Are9OK/pytest-tmp \
    --cov=backend \
    --cov-fail-under=80 \
    --cov-report=term-missing \
    --cov-report=xml:/private/tmp/spec043-task09-final-rerun-Are9OK/coverage.xml \
    --cov-report=json:/private/tmp/spec043-task09-final-rerun-Are9OK/coverage.json
```

未使用 `-k`、`--ignore`、`--deselect`、`--maxfail`、人工 skip、并行分片或失败排除；Chromium 使用已批准权限。

### 第二轮计数与结论

- 通过：`3384`
- 失败：`0`
- 合法 skip：`2`
- subtests：`67 passed`
- pytest warnings：`5`
- pytest 外的进程收尾警告：`sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute`
- 两个 skip 仍为 `tests/e2e/test_research_lifecycle_e2e.py` 的两个用例，因未设置 `RUN_E2E=1` 且需要已启动 `:8000` 服务；未新增或伪造 skip。
- pytest 门禁：**PASS**（退出码 `0`）。

### 第二轮覆盖率

- 语句数：`45652`
- 已覆盖：`37608`
- 未覆盖：`8044`
- 总覆盖率：`82.37974239901867%`（终端显示 `82.38%`）。
- `--cov-fail-under=80`：达到，coverage gate **PASS**。
- XML：[`coverage.xml`](/private/tmp/spec043-task09-final-rerun-Are9OK/coverage.xml)
- JSON：[`coverage.json`](/private/tmp/spec043-task09-final-rerun-Are9OK/coverage.json)

按未覆盖行数排序的风险模块与首轮相同，前十项为：`research/infrastructure/research_store.py`（722）、`api/routes_research.py`（401）、`literature_maps/application/service.py`（283）、`api/routes_conversations.py`（272）、`knowledge_base/infrastructure/candidate_rebuild.py`（271）、`api/routes_paper.py`（224）、`api/routes_kb.py`（167）、`paper_discovery/application/paper_import_batch_service.py`（151）、`literature_maps/application/analysis.py`（127）、`api/routes_literature_maps.py`（116）未覆盖行；这些仅作为后续定向补测风险，不在本轮擅自补测。

### 第二轮原始证据

- 完整原始日志：[`full-regression.log`](/private/tmp/spec043-task09-final-rerun-Are9OK/full-regression.log)
- 第二轮日志包含候选 SHA、源指纹、矩阵文件 SHA、开始/结束时间、完整 pytest/coverage 输出及退出码。
- 8000 服务和生产数据库/Qdrant 未触碰；未部署、未执行真实 API 写入、未调用模型配置覆盖、未执行 git 写操作。
