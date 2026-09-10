# 技术评审报告 — spec-021 论文导入异步进度（后端）

- **评审角色**：backend-reviewer
- **评审范围**：`backend/**` 与后端测试（不含 `frontend/**`）
- **改动文件**：
  - `backend/app/api/routes_paper.py`
  - `backend/app/knowledge_base/application.py`
  - `backend/app/paper_discovery/application/paper_import.py`
  - `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - `tests/test_paper_import_batch_service.py` / `tests/test_paper_import_batch_api.py` / `tests/test_paper_import.py`
- **未改动（重要）**：`backend/app/paper_discovery/infrastructure/paper_import_batch_store.py`（禁用语义 CAS/租约/claim/`import_item_title` 部分唯一索引均未被修改）
- **运行验证**：`.venv/bin/python -m pytest tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import.py -q` → **49 passed**

---

## 结论：**通过（附意见）**

无 CRITICAL / HIGH 问题，不阻塞合并。LOW 级意见见下，建议架构师在合并前确认 INFO 项（进程重启恢复边界）。

---

## 必查项逐条结论

### 1. 单飞与并发 — ✅ PASS
- **单飞保证**：`submit_batch`（`paper_import_batch_service.py:463-481`）在 `_runner_lock`（`threading.Lock`，可哈希）内检查 `existing is not None and not existing.done()`，命中则直接返回既有 `Future`，不二次提交。
- **锁范围正确**：提交与后台 `finally` 的 `pop` 均在 `_runner_lock` 保护下（`:471`、`:491-492`）。`Future.done()` 在 worker 函数 `finally` 执行完毕后才置位，故"读 existing / 写 dict / pop"之间无竞态窗口，无需额外双重检查即等价于双重检查。
- **线程池上限**：模块级 `_batch_runner_executor = ThreadPoolExecutor(max_workers=3)`（`:59-62`），全局有界，超出排队不丢弃、不谎报完成（符合 spec 第 63 行约束）。
- 证据：`test_submit_batch_is_single_flight_and_runs_in_background`、`test_failed_item_retry_runs_in_background_and_is_single_flight`、`test_duplicate_retry_does_not_duplicate_execution`（API）。

### 2. 不阻塞 HTTP — ✅ PASS
- `create_batch(auto_run=True)` → `submit_batch(...)` 后 `返回 queued`（`paper_import_batch_service.py:279-284`），不再同步 `run_batch`。
- `retry_batch` → `submit_batch(...)` 后返回（`:540-543`）。
- `retry_item` → `submit_batch(...)` 后返回目标 `item`（`:563-567`）。
- 证据：`test_create_batch_auto_run_returns_queued_without_finishing_any_item`（桩替换 submit_batch，断言"已提交未执行"）、API 轮询用例 `test_batch_create_returns_queued_and_completes_via_polling`。

### 3. 异常不吞 + 启动恢复 — ✅ PASS（含 INFO 边界）
- **失败不永久 queued**：`_run_batch_in_background`（`:483-492`）try/except 捕获意外异常 → `logger.exception` → `_fail_remaining_queued`（`:494-504`）把仍为 `queued` 的条目标记 `IMPORT_INTERRUPTED` 失败，批次到达终态。
- **复用既有回收**：`get_paper_import_batch`（`routes_paper.py:752-755`）调用 `service.recover_expired_leases()` + `service.maybe_recover_batch(batch_id)`；`maybe_recover_batch`（`:506-520`）仅当 `batch.status=="queued"` 且进程内快照存在时 `submit_batch`，且经单飞不二跑。未新造第二套回收机制（符合 spec 第 67 行）。
- **INFO（设计边界，非阻塞）**：进程重启后快照（process-local）丢失，`maybe_recover_batch` 对"无快照的 queued 批"不重投；若崩溃恰好发生在 `submit_batch` 返回与后台 runner 实际启动之间（条目仍为 queued、无租约），该批会停在 queued 直至用户重试触发。属"候选快照必须 process-local"安全约束的固有边界，代码注释已声明；活跃租约的批由 `recover_expired_leases` 在租约到期后恢复。建议架构师确认此边界可接受。

### 4. 不改禁用语义（store CAS/租约/索引）— ✅ PASS
- `git diff` 确认 `paper_import_batch_store.py` **不在改动列表**，全文核对其 `claim_item`/`transition_item`/`mark_failed`/`retry_item`/`retry_batch` 及 `import_item_title` 部分唯一索引（`:219-223`）均未改动。禁用语义零破坏。

### 5. 错误语义 — ✅ PASS
- **KB_STORAGE_LOCKED 窄匹配**：`paper_import.py:76-82` 与 `knowledge_base/application.py:155-164` 均仅匹配 `"already accessed by another instance" in str(error)`；非此字符串的 RuntimeError 仍回落 `KB_IMPORT_FAILED`/`KB_INDEX_FAILED`（`paper_import.py:301-307`、`:391-397`；`application.py` 在存储占用时 `raise` 交消费方映射，否则走原清理+失败路径）。
- **DUPLICATE_IMPORT 覆盖三路径**：`create_batch`（`:267-275`）、`retry_batch`（`:531-539`）、`retry_item`（`:550-559`）均捕获 `sqlite3.IntegrityError` 且"`import_item_title` in str(error)"时映射为 `DUPLICATE_IMPORT`；其余完整性错误原样上抛，保留旧行为。
- **未被掩盖为 IMPORT_BATCH_ERROR**：路由 `retry_paper_import_item` 的 `except PaperImportBatchServiceError` 分支优先处理上述码（`routes_paper.py:921-922`）；`KB_STORAGE_LOCKED` 为 item 级 error_code（经 `_mark_failed`→白名单），不会作为异常冒泡到路由的 `except Exception`；该 `except Exception` 仅兜底真正未预期异常（→424 IMPORT_BATCH_ERROR）。
- **文案白名单**：固定文案来自 `_SAFE_IMPORT_ERROR_MESSAGES`（`paper_import.py:49-62`），`_mark_failed`/`_paper_batch_payload` 均经 `safe_import_error_message`，异常原文（可能含路径）不回显。证据：`test_storage_locked_*`、`test_duplicate_*`、`test_item_retry_route_hits_duplicate_title_returns_409`。

### 6. 新增路由 POST /api/papers/import-items/{item_id}/retry — ✅ PASS
- **立即返回**：`retry_item` 仅入队后台，路由返回 200 + 批次负载（`routes_paper.py:905-927`）。
- **状态码**：404 `ITEM_NOT_FOUND`（`_paper_snapshot_for_item` 先抛，`:667-670`）；400 `INVALID_STATE_TRANSITION`（store `retry_item` 仅允许 failed→queued）；409 `DUPLICATE_IMPORT`；默认 424 IMPORT_BATCH_ERROR（见 `_PAPER_BATCH_ERROR_STATUS` `:504-519`）。
- **只重跑目标条目**：`store.retry_item` 仅把目标 failed→queued，`run_batch` 仅处理 `ITEM_QUEUED`（`:456`），已完成条目（`completed`）被过滤、不重跑。证据：`test_item_retry_route_requeues_failed_item_and_returns_batch`（`attempts["candidate-2"]==1`）、`test_retry_item_runs_in_background_and_only_retries_target`。

### 7. 测试质量 — ✅ PASS（含 LOW 提示）
- 覆盖单飞、非阻塞、KB_STORAGE_LOCKED 窄匹配+回落、DUPLICATE_IMPORT 三路径、404/400/409、只重跑目标条目；断言非恒真（检查 error_code、attempts 计数、`is first` 同一 Future）。
- 时序：除确定性桩版用例外，轮询用例仅等待终态（有界 `range(200)`×`sleep(0.01)`≈2s），`test_duplicate_retry_does_not_duplicate_execution` 用 `Event`+`timeout=5` 而非裸 sleep 竞态，flaky 风险低。
- 实测 49 passed。

---

## 问题清单

### [LOW] L1 — `_is_storage_locked_error` 重复实现（DRY）
- 文件：`backend/app/paper_discovery/application/paper_import.py:76-82` 与 `backend/app/knowledge_base/application.py:155-164`
- 问题：两份逐字相同的窄匹配函数。受分层约束 knowledge_base 不依赖 paper_discovery，故为可接受的小重复；建议抽到共享工具模块（如 `paper_import_security` 或 domain 层）统一维护，避免日后两边漂移。

### [LOW] L2 — `retry_item` 走整批 `run_batch`（语义为"只重跑目标"的超集）
- 文件：`backend/app/paper_discovery/application/paper_import_batch_service.py:545-567`、`run_batch:450-461`
- 问题：`submit_batch(item.batch_id)` → `run_batch` 重跑**整批所有 queued 条目**，而非严格只跑目标 item。在"仅目标条目被 store.retry_item 置为 queued"的不变量下，实践等价于只重跑目标；但若批次存在其它处于 `queued` 的条目（如先前被中断未领用者），它们也会一并重跑。属可接受行为，但路由注释"仅把该条目回到 queued 并后台提交"与实现"整批 run"略有出入，建议补一句说明该不变量，避免误读。

### [LOW] L3 — 模块级 executor 注释措辞略不精确
- 文件：`backend/app/paper_discovery/application/paper_import_batch_service.py:52-58`
- 问题：注释称容量"mirrors the existing per-batch item concurrency cap"，实际 `max_workers=3` 限制的是**并发批次执行器**数量；`run_batch` 内仍会按 `min(self.max_workers, len(items))` 再开条目级线程池，故多批并发时线程总数可超过 3。非缺陷，仅建议把注释改为"限制同时执行的批次数"，避免误导。

### [INFO] I1 — 进程重启恢复边界（已在上文必查项 #3 详述）
- 进程重启且崩溃窗口恰好落在 submit 与 runner 启动之间、条目仍为 queued（无租约）且无进程内快照时，该批会停在 queued 直至用户重试。属 process-local 快照安全设计的固有边界，非阻塞；建议架构师确认接受。

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 3     | note   |

Verdict: **APPROVE（通过，附 LOW 级意见）** — 7 项必查全部通过，49 个后端测试通过，无阻断性问题；合并前建议架构师确认 INFO-I1 重启恢复边界，并可顺手消化 L1–L3 三项整洁度意见。

- 评审报告：`docs/sdd/reviews/021-tech-review.md`
- 进度日志：`.codebuddy/agent-logs/spec-021/task-05/backend-reviewer/20260910-205436.md`
