> 关联：[spec-020 零碎 bug 解决](../../specs/020-misc-bug-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# Task03 导入补齐 v2 异步索引

## 状态与一句话目标

`待执行`。让**导入**进来的论文与**上传**一致，在 v1 建完后**异步提交 v2 索引**，使知识库不再长期停留在"待索引"。

## 背景与前置条件

- 上传路径（`backend/app/api/routes_kb.py:120-132`）：v1 同步 `run_index_task_sync(..., CHUNKER_V1, ...)`，随后 `_submit_index_task(record.paper_id, path, CHUNKER_V2)` 异步提交 v2。
- 导入路径（`backend/app/knowledge_base/application.py` `KnowledgeBasePaperImportAdapter._default_indexer`）：**只建 v1，未提交 v2** → 导入论文 `chunkers.v2.status` 恒为 `pending`。
- 已确认：v2 **既未立刻构建，也不存在后台构建**（根本没提交）。两条入口不一致，属真实功能缺口。
- v2 使用 27B 结构分析（见 chunkers.py），较慢且占显存，**必须异步**，导入响应不得等待。

## 数据、配置与接口

- 不改导入接口契约；内部在 v1 索引成功后提交 v2。
- 复用既有能力：`tasks.submit_index_task`（或等价的异步提交封装）与 `CHUNKER_V2`；状态流转 `pending → indexing → indexed`，失败置 `failed` 并带原因。
- `GET /api/kb/papers` 需能反映 v2 进度（既有轮询能力，不改）。
- 上传路径行为**保持不变**，不得回归。

## 实施步骤与文件边界

1. 在导入适配器的 v1 索引成功之后，按 paper_id 与已落盘文件路径异步提交 v2（与上传路径 `_submit_index_task` 语义一致：先把状态置 `indexing`，再入单线程池）。
2. 确保导入返回**不等待** v2；v2 失败不影响导入结果（导入仍为成功），但要在 v2 状态中记录失败原因。
3. 保持"v1 与 v2 共用同一单线程池"的约束（避免 bge-m3 与 27B 争显存），不得新建独立线程池。
4. 补后端测试：导入后 v2 被提交（状态不再恒 pending）；v2 失败不影响导入成功；上传路径行为不变。

**文件边界**：只改 `backend/app/knowledge_base/application.py`（及必要的测试）；不改 `routes_kb.py` 上传路径。

## 子代理分派

- `backend-dev`（hy3）：一次只产出该文件的增量改动。
- 完成后 `backend-tester`（hy3）跑后端 pytest。
- 日志：`.codebuddy/agent-logs/spec-020/task-03/<role>/<时间戳>.md`。

## 边界与明确不做

- 不改 v1 索引逻辑、spec-012 双版本检索语义与召回归并规则。
- 不在导入响应中同步等待 v2。
- 不改上传路径；不改导入 CAS 状态机与下载安全策略。
- 不动前端（v2 展示由既有轮询承担；如需文案调整，在回传中说明由主 agent 决定）。

## 验收、风险与回滚

- 验收：
  1. 导入完成后 `/api/kb/papers` 中该论文 `chunkers.v2.status` 由 `pending` 变为 `indexing`/`indexed`（不再恒 pending）。
  2. 导入响应不被 v2 阻塞（耗时与改动前同量级）。
  3. v2 失败时导入仍成功，且 v2 状态为 `failed` 并带原因，可通过 reindex 补救。
  4. 上传路径行为不变；后端 pytest 全绿。
- 风险：v2 使用 27B LLM，本机显存/耗时压力大 → 必须异步且共用单线程池；若本机不具备条件，允许 v2 降级或失败，但状态必须真实可见（不得假装成功）。
- 回滚：`git revert` 本任务提交。

## 产出物、执行结果与变更日志

### 改动文件
- `backend/app/knowledge_base/application.py`（仅 `_default_indexer` 增量 + 新增 `_submit_v2_index`）
- `tests/test_paper_import.py`（新增 3 个用例，覆盖 BUG-02）

### v2 提交实现位置
- `backend/app/knowledge_base/application.py:249` —— `_default_indexer` 在 v1 同步索引成功后调用 `self._submit_v2_index(record, path)`（不阻塞导入响应）。
- `backend/app/knowledge_base/application.py:252-298` —— 新增 `_submit_v2_index`：
  - 先 `update_chunker_state(paper_id, CHUNKER_V2, status=STATUS_INDEXING, progress=0, error=None, meta_path=...)` 把 v2 置为 `indexing`，语义与上传路径 `_submit_index_task` 一致；
  - 再 `submit_index_task(paper_id, CHUNKER_V2, _runner)` 经既有单线程池异步执行 `index_paper_chunker(record, path, CHUNKER_V2, ...)`；
  - 复用 `knowledge_base.infrastructure.tasks.submit_index_task` 与 `store.update_chunker_state`，**未**从 `api` 层 import `routes_kb`，**未**新建线程池（共用 `tasks.get_executor()`）；
  - v2 失败不影响导入成功：状态置 `failed` 并带原因（可由 reindex 补救）；提交异常同样不判定导入失败。

### 验收命令与真实输出
```
$ source .venv/bin/activate
$ python -m pytest tests/ -q
791 passed, 6 warnings, 41 subtests passed in 85.54s

$ ruff check backend/app/knowledge_base/application.py tests/test_paper_import.py
app/knowledge_base/application.py:18:1: I001 [*] Import block is un-sorted or un-formatted
app/knowledge_base/application.py:201:9: SIM105 ...
app/knowledge_base/application.py:223:13: SIM105 ...
app/knowledge_base/application.py:228:13: SIM105 ...
app/knowledge_base/application.py:376:13: SIM105 ...
# 以上均为本仓库改动前既有的 I001/SIM105；本任务引入的行（含新增 contextlib.suppress）已全部清零。
```

### 新增/修改测试（tests/test_paper_import.py）
- `test_default_indexer_submits_v2_after_v1`：v1 同步成功后必须异步提交 v2（`submit_index_task` 以 `CHUNKER_V2` 调用），且提交前 v2 状态已置 `indexing`；导入返回的是 v1 结果（不阻塞）。
- `test_v2_failure_does_not_fail_import`：v2 索引抛错时，`_default_indexer` 仍返回 v1 成功，且 v2 状态被真实置为 `failed` 并带原因（后台 `_guarded_run` 兜底）。
- `test_import_paper_submits_v2_with_default_indexer`：默认索引器（未注入）下 `import_paper` 也提交 v2 并返回 `INDEXED`。
- 上传路径既有测试（`test_kb_routes.py::test_upload_stores_file_and_indexes`、`test_reindex_*` 等）零回归。

### 风险与边界
- 未改 v1 索引逻辑、spec-012 双版本检索语义与召回归并规则；未改上传路径；未改导入 CAS/并发/租约/下载策略；未改前端。
- v2 使用 27B，异步且不阻塞导入响应；本机若不具备条件允许 v2 失败，但状态真实可见、可由 reindex 补救。
