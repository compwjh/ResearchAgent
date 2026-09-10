# 020 后端评审报告 · BUG-02（导入补齐 v2 异步索引）

- 评审对象：`backend/app/knowledge_base/application.py`（`_default_indexer` 增量 + 新增 `_submit_v2_index`）、`tests/test_paper_import.py`（3 个新用例）
- 对照基准：`backend/app/api/routes_kb.py:120-132` 上传路径 `_submit_index_task`
- 评审角色：backend-reviewer（只读，未改 `backend/**`）
- 评审日期：2026-09-10

## 结论

**通过（Approve）**。改动与 spec-020 BUG-02 方案 A 及 task-03 完全一致：导入路径在 v1 同步建完后，按 paper_id + 落盘路径异步提交 v2，复用既有单线程池与 `update_chunker_state`/`submit_index_task`，未从 `api` 层反向依赖，未新建线程池，未越界。3 个新用例真实断言到点且 venv 实测全绿（3 passed, 1.72s）。**无 P0 / P1**。

---

## 逐项核对表（含文件:行号）

### 1. 语义是否与上传一致
- [OK] 先置 v2 为 indexing(0) 再异步提交：`_submit_v2_index`（`application.py:259-270`）先 `update_chunker_state(paper_id, CHUNKER_V2, status=STATUS_INDEXING, progress=0, error=None, meta_path=...)`；随后 `submit_index_task(record.paper_id, CHUNKER_V2, _runner)`（`application.py:283`），与上传 `_submit_index_task`（`routes_kb.py:135-147`）「先 indexing 再入池」语义对齐。
- [OK] runner 调用 `index_paper_chunker(..., CHUNKER_V2, ...)`：`_runner`（`application.py:272-280`）显式传 `chunker=CHUNKER_V2`，并透传 `client=self.client`、`meta_path=self.meta_path`；`index_paper_chunker` 签名（`index.py:260-269`）接受上述参数，且内部异常自我收敛为 `failed`（与上传 `_runner` 同构）。
- [OK] v1 结果返回、v2 不阻塞：`_default_indexer`（`application.py:235-250`）先 `result = run_index_task_sync(..., CHUNKER_V1, ...)`，再 `self._submit_v2_index(...)` 后 `return result`，v2 提交在返回前已「入池即返回」（`submit_index_task` 仅入池不等待），导入响应不被 v2 阻塞。

### 2. 分层约束
- [OK] 未从 `api` 层 import `routes_kb`：相关符号全部来自 `infrastructure`（`application.py:70-96`）：`CHUNKER_V2`/`STATUS_*`/`update_chunker_state` 来自 `infrastructure.store`，`run_index_task_sync`/`submit_index_task` 来自 `infrastructure.tasks`，`index_paper_chunker` 来自 `infrastructure.index`。与模块 docstring（line 6-9）「其它上下文与 api 层只能依赖本模块」一致。
- [OK] 复用既有能力、无重复实现：v2 提交完全复用 `tasks.submit_index_task` 与 `store.update_chunker_state`，未出现第二套索引/批任务实现（满足 regression-guard 第 9 条，无违例）。

### 3. 线程池约束
- [OK] 复用既有单线程池、未新建：`submit_index_task`（`tasks.py:43-62`）经 `get_executor()` 提交；`get_executor()`（`tasks.py:32-40`）是模块级单例 `ThreadPoolExecutor(max_workers=1)`（docstring 第 1-12 行明确为「避免 bge-m3 与 27B 争显存」硬要求）。v2 与 v1 共用同一队列，无独立线程池。

### 4. 不阻塞 + 失败隔离
- [OK] 不阻塞：见上 §1。
- [OK] v2 失败不判导入失败 + 状态真实 failed 带原因：
  - `update_chunker_state(INDEXING)` 失败被 `except Exception: return` 吞掉（`application.py:268-270`），不拖垮已成功的导入；
  - `submit_index_task` 抛异常被 `except Exception` 捕获并 `update_chunker_state(STATUS_FAILED, error="v2 索引任务提交失败")`（`application.py:284-294`，外层 `contextlib.suppress` 防二次异常）；
  - 后台 runner 内 `index_paper_chunker` 抛错由 `tasks._guarded_run` 兜底写 `STATUS_FAILED` + 真实原因（`tasks.py:101-112`）。
  - 导入成功判定只看 v1：`import_paper` 的 `_index_succeeded(index_result)`（`application.py:358`）作用于 v1 的 `result`，`_submit_v2_index` 不向 `_default_indexer` 冒泡异常 → 导入判 `INDEXED`。可由 `reindex` 补救（spec-012）。

### 5. 越界检查（明确未越界）
- [OK] `git diff HEAD -- backend/` 仅触及 `application.py`（`import contextlib` + `_default_indexer` 增量 + `_submit_v2_index`）。
- [OK] 未改 v1 索引逻辑：`_default_indexer` 内 `run_index_task_sync(..., CHUNKER_V1, ...)` 调用体（`application.py:235-246`）与改动前逐字一致，仅把返回值赋给 `result`。
- [OK] 未改 spec-012 双版本检索语义与召回归并（`retrieve.py` 未触碰）。
- [OK] 未改上传路径 `routes_kb.py`（不在 diff 内）。
- [OK] 未改导入 CAS 状态机 / 并发领用 / 租约（`import_paper` 的 `with self._lock` 段 line 309 起逻辑未变）。
- [OK] 未改下载安全策略（本次均不动）。
- [OK] 未改前端。

### 6. 测试有效性（venv 实测 3 passed）
- [OK] `test_default_indexer_submits_v2_after_v1`（`test_paper_import.py:265-296`）：断言 `run_index_task_sync` 仅 1 次且 `args[1]==CHUNKER_V1`、`submit_index_task` 仅 1 次且 `args[1]==CHUNKER_V2`、返回值为 v1 结果（不阻塞）、且 `update_chunker_state` 被以 `status=STATUS_INDEXING, chunker=CHUNKER_V2` 调用（先置 indexing 被断言）。真断言到点。
- [OK] `test_v2_failure_does_not_fail_import`（`test_paper_import.py:299-325`）：mock `index_paper_chunker` 抛 `RuntimeError("27B 模型不可用")`，经真实 `submit_index_task → _guarded_run` 后台线程执行后，断言导入结果仍为 v1 成功、且捕获到 `status=STATUS_FAILED` 且 `error` 非空。真实走了失败兜底路径。
- [OK] `test_import_paper_submits_v2_with_default_indexer`（`test_paper_import.py:328-351`）：默认索引器（未注入）下 `import_paper` 也提交 v2：断言 `index_status==INDEXED`、`submit_index_task(args[1]==CHUNKER_V2)`。

---

## 问题分级

| 级别 | 数量 | 条目 |
|------|------|------|
| P0（阻塞） | 0 | 无 |
| P1（须改） | 0 | 无 |
| P2（建议/可选） | 1 | 见下 |

### P2-1（可选，非阻塞）
`application.py:268-270` 的 `update_chunker_state(INDEXING)` 失败时仅 `return` 且无日志，运维侧难以观测「v2 置位失败」实例。建议在 `except` 分支加一行 `logging.getLogger(...).warning(...)`（注意沿用项目既有日志风格，避免 `print`）。非阻塞，与上传路径 `_submit_index_task` 对 update 失败的处理也不同（上传未包 try），此处更稳健，仅作可观测性增强建议。

---

## 运行时证据交叉验证
- 主 agent 实测：导入返回 `status=indexed`，轮询 `/api/kb/papers` 见 `v2: indexing(16) → indexing(35) → indexed(100)`，`v1` 全程 `indexed` → 与方案 A「先置 indexing 再异步提交、不阻塞导入」一致。
- 另一篇导入返回 `424 KB_IMPORT_FAILED`（新错误语义生效，非本 diff 引入，属既有导入失败路径，行为未回归）。
- 后端自测：`791 passed`（主 agent）+ 本评审针对 3 用例 venv 实测 `3 passed in 1.72s`。

## 评审 Summary（ECC 格式）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 1     | note   |

Verdict: APPROVE — 无 CRITICAL/HIGH 问题，可合并。
