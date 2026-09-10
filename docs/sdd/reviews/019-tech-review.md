# 019 技术评审

> 结论：**通过**（P0=0）。本文综合后端评审与前端评审结论，由主 agent 代行技术评审汇总。
> 分项评审：[后端评审](./019-backend-review.md) ｜ [前端评审](./019-frontend-review.md)

## 一、根因修复（对应 Task02 结论 C）

单篇导入路径 `_import_single_paper` 原先只查 `get_search_session`，而 catalog 异步检索的上下文只存在于 `search_jobs`（`search_sessions` 恒空），导致单篇形态必然误报 `SEARCH_NOT_FOUND`。现已改为与批量路径 `_paper_server_snapshot` 同构：`session is None` 时回退 `_paper_catalog_import_inputs`，候选由 `by_id` 取得。

**判定：通过**。后端评审确认回退逻辑与批量路径真正同构，无遗漏分支。

## 二、错误语义（对应 Task04）

原 5 处 `except Exception` 一律返回 503 `IMPORT_BATCH_UNAVAILABLE`，把真实异常吞掉。现改为 `logger.exception` 落栈 + 424 `IMPORT_BATCH_ERROR`，仅 `DATABASE_LOCKED` 等瞬时冲突保留 503 + `retryable`。同时补齐 `SEARCH_NOT_READY` 的状态码与文案映射，确保"未就绪 / 已过期 / 不存在"三类互斥。

**判定：通过**。验收实测 `IMPORT_BATCH_UNAVAILABLE` 已无引用，三类提示文案互不混淆。

## 三、前端状态一致性（对应 Task03 + P1 修复）

`renderImportSummary()` 成为状态栏唯一写入入口，消除原 944/953/1008 三处覆写导致的"先错后完成"。分组循环改为独立 try/catch，一组失败不影响其余组；静默路径补可见反馈；`partial_success` 与 `completed` 区分。P1 修复后新增 `currentRoundBatchIds` 并每轮重置 `directSuccess`，解决重复导入计数虚高。

**四项必守核对（前端评审结论）**：DOM 契约无新增/更名 id（PASS）｜`?v=N` 同步递增至 20 且契约测试断言一致（PASS）｜新增代码全 `textContent`、无 `innerHTML` 拼接（PASS）｜无构建、纯原生（PASS）。

## 四、越界检查

后端未触碰 CAS 状态机 / 并发领用 / 租约 / 下载安全策略（allowlist、`_peer_from_response`、对端复核）/ `search_jobs` 过期清理；前端未改后端接口与错误码归属。**判定：未越界**。

## 五、遗留项（P2，不阻塞合入）

1. `CANDIDATE_NOT_FOUND` 实际 404 与 spec 接口表标注 400 不一致（既有，非本次引入）→ 建议后续修订 spec 或统一为 404。
2. `session = job` 死赋值，建议清理。
3. 单篇路径仍有两处 `except` 未落日志。
4. 单篇 `CANDIDATE_NOT_FOUND` 分支缺直接测试。

## 结论

实现与 spec 一致，根因已消除，运行时三类场景均通过验收，无 P0 → **技术评审通过**，同意进入验收收口。
