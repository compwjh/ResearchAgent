# 019 后端评审报告（backend-reviewer）

- Spec：spec-019 论文导入状态反馈一致性
- 角色：backend-reviewer（仅评 `backend/**`）
- 评审对象：`backend/app/api/routes_paper.py`（+51/−14）、`tests/test_paper_discovery_api.py`（+207）
- 日期：2026-09-10
- 结论：**通过（附意见）** —— 无 P0、无 P1；4 项 P2 建议（均不阻塞合并）。

---

## 一、结论

**通过（附意见）**。本次改动精准命中 task-02 结论 C 根因，并与批量路径 `_paper_server_snapshot` 真正同构；三类检索上下文错误码互斥且映射自洽；5 处 503 兜底已消除并改为 424 + `logger.exception` 落栈，`DATABASE_LOCKED` 瞬时冲突仍保留 503 retryable；日志真实落地且未泄露敏感信息；**未越界**触碰 CAS/并发/租约、下载安全策略、`search_jobs` 过期清理或前端。

强制约束清单（沉淀，后续改动须遵守）：
1. `routes_paper.py` 中 `_import_single_paper` 与 `_paper_server_snapshot` 对 `session is None` 的 job 回退必须保持同构（共用 `_paper_catalog_import_inputs`，过期检查在前、候选缺失检查在后、SEARCH_NOT_FOUND 仅在 `get_search_job` 为 None 时触发）。
2. `_PAPER_BATCH_ERROR_STATUS` / `messages` 与 `spec-019` 接口表三态（SEARCH_NOT_FOUND/SEARCH_EXPIRED/SEARCH_NOT_READY）必须互斥且文案可区分，新增 code 须同步补两张表。
3. 任何 `except Exception` 兜底必须 `logger.exception` 落栈，不得静默吞异常；未预期异常返回 424 `IMPORT_BATCH_ERROR`（非 503 `IMPORT_BATCH_UNAVAILABLE`）。
4. `DATABASE_LOCKED` 等确属瞬时冲突仍走 503 + `retryable=true`，不得被未预期异常分支吞掉。
5. 严禁触碰 `paper_import_batch_store.py` 的 CAS/并发/租约、下载安全（allowlist/`_peer_from_response`/对端复核）、`search_jobs` 过期清理策略、以及 `frontend/**`。

---

## 二、运行时证据交叉验证

主 agent 实测已佐证（非仅凭 spec）：
- 重启服务后，单篇合法 job：`已导入 → 409 PAPER_ALREADY_EXISTS`（证明会话解析已通过，不再 404 SEARCH_NOT_FOUND）；`未导入 → 200 status=indexed` 落盘 `2024-USENIX-Security-...pdf`。
- 全量 `python -m pytest tests/ -q` → **785 passed**（与评审时读到的 diff 范围内测试一致）。

---

## 三、逐项核对表（含文件:行号证据）

| 评审重点 | 结论 | 证据 |
|---|---|---|
| 1. 根因修复（结论 C） | 达成 | `routes_paper.py:437-454`：`session is None` 时回退 `_paper_catalog_import_inputs(store, request.search_id, [request.candidate_id])`；候选取 `by_id.get(request.candidate_id)`（dict 快照）。与 `_paper_server_snapshot:641-661` / `_paper_catalog_import_inputs:617-638` 同构 |
| 2. 回退与批量路径同构 | 达成 | 共用 `_paper_catalog_import_inputs`；过期检查 `_paper_search_expired(getattr(job,"expires_at",""))` 在前（:445 / :647）；候选缺失在后（:449-453 / :649-651）；`SEARCH_NOT_FOUND` 仅 `get_search_job` 为 None 时（:626-627）。job 已冻结但无 results → 两端均映射 CANDIDATE_NOT_FOUND，无遗漏分支 |
| 3. 三类状态互斥（NOT_FOUND/EXPIRED/NOT_READY） | 达成 | `_PAPER_BATCH_ERROR_STATUS:509` 补 `"SEARCH_NOT_READY":400`；`messages:534` 补 `"搜索结果尚未冻结"`。判定由 `_paper_catalog_import_inputs:628-629`（status∉{completed,partial,failed}→SEARCH_NOT_READY）统一提供，单篇/批量一致 |
| 4. 消除 503 兜底 | 达成 | 5 处 `except Exception`（:718-722 / :745-749 / :768-772 / :791-795 / :874-878）改为 `logger.exception(...)` + `_paper_batch_error_response(PaperImportBatchServiceError("IMPORT_BATCH_ERROR",...))`（424）。原 IMPORT_BATCH_UNAVAILABLE 已无引用 |
| 5. DATABASE_LOCKED 保留 503 retryable | 达成 | `_PAPER_BATCH_ERROR_STATUS:516` `"DATABASE_LOCKED":503`；前置 `except PaperImportBatchServiceError` 分支未动，瞬时冲突语义不变。测试 `:552-567` 验证 |
| 6. 日志真实落地且不泄露 | 达成 | `logger = logging.getLogger(__name__):50`；5 处 `logger.exception("批量导入未预期异常：%s", type(error).__name__)`——仅记异常类名，`.exception` 堆栈不含局部变量，不泄露 URL/credential；响应走固定 `messages` 表（:528-543），不外泄异常细节 |
| 7. 未越界 | 确认未越界 | diff 仅 `routes_paper.py` 与 `tests/`。未触碰 `paper_import_batch_store.py`（CAS/并发/租约）、下载安全（allowlist/`_peer_from_response`/对端复核）、`search_jobs` 过期清理；未改 `frontend/**` |
| 8. 测试断言命中要点 | 达成 | `test_single_import_resolves_catalog_job_fallback_and_succeeds:407-428` 用 `importer.call_args.args[0]` 是 dict 且 `catalog_paper_id==cp-1` 强证回退；`test_single_import_three_search_context_codes_are_mutually_exclusive:430-462` 三 case 各断言 status/code/message/retryable；`PaperImportBatchErrorSemanticsTests:465-567` 用 `assertLogs` 真验证 ERROR 日志 + 424 + code，且覆盖 5 个 handler（含 /import-batches 别名）与 DATABASE_LOCKED 仍 503。无“通过但没断言到点” |

---

## 四、发现的问题（P0 / P1 / P2）

### P0（阻塞）：无

### P1（警告）：无

### P2（建议，不阻塞）

**P2-a｜CANDIDATE_NOT_FOUND 状态码与 spec 接口表不一致（404 vs 400）**
- 位置：`routes_paper.py:507`（`"CANDIDATE_NOT_FOUND": 404`）、单篇路径 `:458`/`:462`（`_paper_api_error(404, "CANDIDATE_NOT_FOUND", ...)`）。
- 事实：`spec-019` 第 37-38 行接口表把 `CANDIDATE_NOT_FOUND` 标为 `400`，但后端 `_PAPER_BATCH_ERROR_STATUS` 与单篇路径实际返回 `404`（既有映射，本次未改动，本次仅补 `SEARCH_NOT_READY:400`）。
- 影响：仅规格/实现标注不一致，不影响本次核心目标（三态互斥、消除 503）。前端 Task03 的 `PAPER_ERROR_TEXT` 需注意对齐。
- 建议：在 spec 或实现中二选一统一（建议遵循 spec 改为 400，或 spec 表更正为 404）。属澄清项，非本次引入。置信度 >90%。

**P2-b｜单篇路径 `session = job` 为死赋值**
- 位置：`routes_paper.py:454`。
- 事实：`session = job` 之后（:456 起为 `else` 分支；:461 `if candidate is None` 及后续）不再读取 `session`，该赋值无副作用，仅为与 `else` 分支结构对称。
- 影响：无害冗余，不影响正确性。
- 建议：删去 `session = job`，或仅保留注释说明“以 job 充当 session 上下文”。置信度 >95%。

**P2-c｜单篇路径两处 `except Exception` 仍静默吞异常未落日志**
- 位置：`routes_paper.py:459-460`、`:470-471`。
- 事实：这两处 `except Exception: return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", ..., True)` 未加 `logger.exception`，与本任务“未预期异常必须落日志”的宗旨不完全一致。`PAPER_DISCOVERY_STORE_UNAVAILABLE` 并非被禁的 `IMPORT_BATCH_UNAVAILABLE`，且这两处不在 task-04 的 5 处修复范围，属既有行为。
- 影响：单篇导入路径 store 级未预期异常仍静默吞（spec-019 边界第 49 条要求“必须落日志”）。风险低、非回归。
- 建议：后续统一为 `logger.exception(...)` + 固定文案响应，与批量路径对齐。不阻塞本次。置信度 >90%。

**P2-d｜单篇路径新增 `CANDIDATE_NOT_FOUND` 分支缺直接测试**
- 位置：`routes_paper.py:449-453`（session is None 分支内 `if candidate is None`）。
- 事实：新增的“job 合法已冻结但该 candidate 不在结果集” → `CANDIDATE_NOT_FOUND` 分支未被新测试显式覆盖（测试 `:430-462` 仅覆盖 NOT_FOUND/NOT_READY/EXPIRED 三态）。批量路径已覆盖 CANDIDATE_NOT_FOUND 语义，故风险低。
- 建议：补一条“catalog job 存在、search_results 不含该 candidate_id”的单篇测试，断言 404 CANDIDATE_NOT_FOUND。置信度 >85%。

---

## 五、明确“未越界”确认

- ✅ **CAS 状态机 / 并发领用 / 租约**：`paper_import_batch_store.py` 无任何改动，diff 仅涉及 `routes_paper.py` 的 API 编排层与错误响应。
- ✅ **下载安全策略**：allowlist / `_peer_from_response` / 对端复核逻辑未被触碰（diff 无相关函数改动）。
- ✅ **`search_jobs` 过期与清理**：仅读取 `get_search_job`/`get_search_results`，未改过期时间策略或清理机制（符合 spec “明确不做”第 4 条）。
- ✅ **前端**：`frontend/**` 改动属于 Task03，不在本次 backend diff 内，未越权评审/修改。
- ✅ **新增测试**：仅新增 `tests/test_paper_discovery_api.py` 两个测试类，无重复实现、无第二套下载/安全/导入逻辑。

---

## 六、Review Summary

| 严重度 | 数量 | 状态 |
|--------|------|------|
| CRITICAL (P0) | 0 | pass |
| HIGH (P1) | 0 | pass |
| MEDIUM (P2) | 4 | note |

Verdict: **通过（附意见）** —— 0 个 P0/P1 阻塞项，4 个 P2 建议项（CANDIDATE_NOT_FOUND 状态码与 spec 不一致、死赋值、单篇 except 未落日志、CANDIDATE_NOT_FOUND 分支缺测）均不阻塞合并，建议后续按强制约束清单统一收口。

评审产出：`docs/sdd/reviews/019-backend-review.md`
进展日志：`.codebuddy/agent-logs/spec-019/task-05/backend-reviewer/20260910-001618.md`
