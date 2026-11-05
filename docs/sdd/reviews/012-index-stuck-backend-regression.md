# Spec012 索引任务重启后永久卡「索引中 0%」— 后端回归报告

- 角色：Backend Tester（ECC `verification-loop` / `e2e-runner`）
- 批次：Spec012 缺陷修订（冻结范围：启动收敛接线 + 提交竞态 + auto_requeued 标记语义，不做持久化队列）
- 验证时间：2026-11-06 03:57 – 04:20
- 解释器：`/Users/wjh/ResearchAgent/.venv/bin/python`（项目虚拟环境）
- 边界：仅跑 `tests/kb`、`tests/literature_maps` 与 3 个实现文件 diff 审查；未触碰 `frontend/**`、`data/**`、任何实现文件；未重启服务、未改 `papers.json`、未触发重排。

---

## 1. 命令真实输出摘要

| # | 命令 | 退出码 | 结果摘要 |
|---|------|--------|----------|
| 1 | `.venv/bin/python -m pytest tests/kb -q` | **0** | `519 passed, 5 warnings, 29 subtests passed in 44.60s`（0 failed / 0 error） |
| 2 | `.venv/bin/python -m pytest tests/kb/test_kb_startup_interrupted_recovery.py -v` | **0** | `10 passed in 3.48s`（本批次新增 10 条，全部 PASSED） |
| 3 | `.venv/bin/python -m pytest tests/kb/test_startup_reindex_recovery.py tests/kb/test_kb_tasks.py tests/kb/test_metadata_auto_requeue_compatibility.py -q` | **0** | `35 passed in 4.04s`（8 + 16 + 4 = 28 用例 + subtests） |
| 4 | `.venv/bin/python -m pytest tests/literature_maps -q` | **0** | `240 passed in 18.07s`（地图领域零回归） |
| 5 | `cd backend && .venv/bin/python -c "import app"` | **0** | 输出 `import ok` |
| 6 | `cd backend && .venv/bin/python -m ruff check .` | **1** | `Found 56 errors.` / `18 fixable` — 全部为**存量**告警，见 §4 |

> 说明：`tests/kb` 日志中的 `Transient error HTTPConnectionPool(127.0.0.1:3000) ... otel/v1/traces` 与 `swigvarlink DeprecationWarning` 属既有 OTEL 导出噪声与三方库告警，不影响结果（退出码 0）。

---

## 2. 逐条验收点结论

### 验收点 1 — `tests/kb` 全量 0 failed：**PASS**
- 退出码 0，`519 passed`，与预期 ~519 完全吻合；`grep -c FAILED` = 0。

### 验收点 2 — 三条核心语义仍有断言守护：**PASS**

| 语义 | 守护用例（文件:行） | 关键断言 |
|------|--------------------|----------|
| **每 (document, chunker) 只自动重排一次** | `tests/kb/test_startup_reindex_recovery.py:96` `test_recovers_each_failed_chunker_exactly_once` | 首次 `n == 2` 且 `submitted == {(d1,v1),(d2,v2)}`；第二次 patch 为 `AssertionError("不得二次排队")` 时 `n2 == 0` |
| | `tests/kb/test_kb_startup_interrupted_recovery.py:126` `test_converged_document_is_requeued_once_by_startup_recovery` | 收敛后首次 `recover_failed_reindexes == 1`、`submitted == [(d1, v2)]`；第二次 `== 0` |
| | `tests/kb/test_metadata_auto_requeue_compatibility.py:145` `test_auto_requeue_marker_is_per_chunker_and_restart_idempotent` | 标记按 chunker 独立、带时区时间戳、重载幂等 |
| **真失败不无限重试（防重启风暴）** | `tests/kb/test_startup_reindex_recovery.py:111` `test_still_failed_after_retry_is_not_auto_retried` | 重排后仍 failed，第二次启动 patch `AssertionError` → `n == 0` |
| | `tests/kb/test_startup_reindex_recovery.py:122` `test_submit_failure_is_skipped_and_not_marked` | 单篇提交异常只跳过、不打标记 |
| | `tests/kb/test_kb_startup_interrupted_recovery.py:99` `test_true_failed_record_keeps_requeue_marker` | 真失败 `marked == 0`，状态/error/标记均不被动 |
| **被重启打断可重排一次** | `tests/kb/test_kb_startup_interrupted_recovery.py:80` `test_interrupted_indexing_is_failed_and_marker_cleared` | `marked == 1`、`status=failed`、`error=服务重启导致中断`、`is_chunker_auto_requeued == False` |
| | `tests/kb/test_kb_startup_interrupted_recovery.py:114` `test_marker_of_other_chunker_survives_convergence` | 仅清被收敛 chunker 的标记 |
| | `tests/kb/test_kb_startup_interrupted_recovery.py:211/236` | lifespan 调用顺序 `["mark_interrupted", "recover_failed"]`；收敛抛异常时不阻塞、仍执行自愈 |

新增文件 10 条用例分布：`MarkInterruptedClearsRequeueMarkerTests` 4 条、`ReindexSubmissionRaceTests` 4 条、`InterruptedTaskLifespanOrderTests` 2 条 —— 三条语义加提交竞态全覆盖。

### 验收点 3 — `tests/literature_maps` 零回归：**PASS**
- `240 passed in 18.07s`，退出码 0，与预期 ~240 一致。

### 验收点 4 — 三个实现文件落盘核对：**PASS**

**a) `backend/app/main.py`**
- L19：`from backend.app.knowledge_base.infrastructure import tasks`（接线导入存在）
- L63–68：独立 `try:` → `marked = tasks.mark_interrupted_on_startup()`，`except Exception` 只 `print` 不抛出
- L72–77：`recover_failed_reindexes()` 位于其**之后**，同样独立 `try/except`
- 顺序结论：`mark_interrupted_on_startup`（L64）严格早于 `recover_failed_reindexes`（L73），符合「先收敛后自愈」；注释 L60–62 亦说明该顺序约束。

**b) `backend/app/knowledge_base/application.py`**
- L810 `submit_document_reindex(...)`；L856–857 注释「先提交、后置 indexing」
- L858–867：`submit_index_task` 在 `try` 内调用，`except Exception` 时 `update_chunker_state(... STATUS_FAILED, error="索引任务提交失败")` 并 `accepted = False`
- L868–871：`if accepted:` 才写 `STATUS_INDEXING` —— **False/异常路径不写 indexing**
- L872：`submitted[name] = bool(accepted)` 如实回报每 chunker 结果
- 依赖导入已就位：L20 `import contextlib`、L24 `import logging`、L144 `logger`

**c) `backend/app/knowledge_base/infrastructure/store.py`**
- L785 `mark_interrupted_tasks(...)`；L802–807 先收集 `interrupted` 列表
- L808–814：仅对 `interrupted` 置 `failed/progress=0/error=reason`
- L815–827：`if interrupted:` 才处理标记，`kept = {n:v for ... if n not in interrupted}` —— **仅对被收敛的 chunker 清 `auto_requeued_chunkers`**，其它 chunker 保留、空则 pop key
- 与 `tasks.py:148 mark_interrupted_on_startup()` → `store.mark_interrupted_tasks(reason=...)` 委托链一致（L154）

### 验收点 5 — `upload-closure-matrix.json` 自洽性：**PASS**
- 文件 sha256：`35a4c1ad9dea32da2957a763cb28b887564c1be1a0bd661dfd6e535cc7687702`
- 算法声明：`sha256(sorted(shasum-a-256-lines))`；`schema_version=upload-closure-matrix-v1`，`inventory_git_revision=8b0cde1`，`review_status=verified`
- **8/8 个 inventory_files 的 sha256 与工作树一致**（含 3 个本批次改动文件：main.py `85c9beb1976a`、application.py `833b3ae34716`、store.py `330e5c31bf55`）
- 重算 `sha256("\n".join(sorted(<hash>+"  "+path)) + "\n")` = `834f14da94965400379ba145bbbf9bf127953b271da18e2f70d285beb17ee560`，与声明 `inventory_digest` **完全一致**
- 校验方式：一次性 python heredoc 只读脚本，**未落盘任何文件**

---

## 3. VERIFICATION REPORT

```
VERIFICATION REPORT
===================

Build:     PASS  (import smoke: `import app` -> ok, exit 0)
Types:     N/A   (Python 项目无独立类型检查门禁；导入冒烟已通过)
Lint:      WARN  (ruff 56 errors / 18 fixable — 全部存量，0 条落在本批次 3 个改动文件)
Tests:     PASS  (tests/kb 519/519 passed, 0 failed; 定向 10+35 passed; tests/literature_maps 240/240 passed)
Security:  PASS  (3 个改动文件密钥扫描 0 命中；测试全程使用 tmp_path，data/ 零脏改)
Diff:      3 files changed, 61 insertions(+), 12 deletions(-)  +  1 个新增测试文件

Overall:   READY
```

**后端测试总计**：`519 (tests/kb) + 240 (tests/literature_maps) = 759 passed / 0 failed`，另含 `29 subtests passed`。
**覆盖率**：本批次未跑 `--cov`（不在验收点内），故不报告百分比；三条核心语义与提交竞态由 10 条新增 + 35 条既有定向用例逐条断言守护，行为级覆盖充分。

---

## 4. 阻塞项 / 备注

**阻塞项：无。**

非阻塞观察（供后续跟进，不影响本批次 READY）：
1. **ruff 存量告警 56 条**：分布 `app/memory/repository.py` 15、`app/literature_maps/application/analysis.py` 6、`eval_042/*` 11、`app/research/*` 等；本批次 3 个改动文件均 0 命中。属历史技术债，建议单独立项清理，不应阻塞 Spec012 缺陷修订合入。
2. **OTEL 导出噪声**：测试日志出现 `Transient error HTTPConnectionPool(127.0.0.1:3000) /api/public/otel/v1/traces`，为采集端未启动导致的导出重试日志，不影响退出码与断言结果。
3. **`main.py` import 顺序被 ruff `I001` 规则视为需重排**：本次 diff 中 `literature_maps...runtime` 导入位置有移动，但 `backend/app/main.py` 未出现在 ruff 报错清单中，说明当前顺序已合规，无需处理。

---

## 5. 边界合规声明

- 只运行 `tests/kb`、`tests/literature_maps` 与 `backend/` 导入冒烟、ruff；未运行任何前端测试。
- 未修改 `frontend/**`、`data/**`、任何实现文件；`git status --porcelain data/` 计数 = **0**。
- 未重启服务、未改 `papers.json`、未触发任何重排。
- 本次仅新增本报告文件。
