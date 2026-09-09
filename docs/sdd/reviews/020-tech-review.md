# 020 技术评审

> 结论：**通过（P0=P1=0）**。本文综合后端评审、前端评审与验收结论，由主 agent 代行技术评审汇总。
> 分项评审：[后端](../reviews/020-backend-review.md) ｜ [前端](../reviews/020-frontend-review.md) ｜ [验收](../reviews/020-acceptance-review.md)

## BUG-01 前端即时反馈与 0 批次文案

- 提交阶段 `setImportPhase('submitting')` 后**立即** `renderImportSummary()`（app.js:1031-1033 连续三行），单次点击即可见反馈，无需二次点击。
- 新增 `paperState.pendingGroups = groups.size`（:1020），提交阶段文案取它（:958）；进入 submitting 前 `if (!groups.size) return`（:1025）保证 N≥1；守卫（:946）防 skipped 误判 failed。
- 卡片动画：非终态 toggle `is-progressing`（:1109），CSS 限定 `#papers-view` 作用域并含 `prefers-reduced-motion` 降级。
- 四项必守核对：DOM 契约无新增/更名 id（PASS）｜`?v=20→21` 同步且契约测试断言一致（PASS）｜无 `innerHTML` 拼接（PASS）｜无构建（PASS）。

## BUG-02 导入补齐 v2 异步索引

- `_default_indexer` 在 v1 同步索引成功后调用 `_submit_v2_index`（application.py:249），先置 v2 `indexing(0)` 再 `submit_index_task(..., CHUNKER_V2)`（:259-283），runner 调 `index_paper_chunker(..., CHUNKER_V2, ...)`。
- 分层合规：符号全来自 `infrastructure.*`，无 `api` 反向依赖，复用既有 `submit_index_task`/`update_chunker_state`，无重复实现。
- 线程池：复用既有单例 `get_executor()`（`max_workers=1`），未新建独立线程池，避免 bge-m3 与 27B 争显存。
- 不阻塞 + 失败隔离：返回 v1 结果；v2 异常兜底层置 `failed` 带原因，导入仍 `INDEXED`，可由 reindex 补救。

## 运行时验证（主 agent + tester 实测）

- 导入新论文 `status=indexed`，响应未被 v2 阻塞；轮询 `chunkers.v2` 由 `indexing(16)→37→70→indexed(100)`，v1 全程 indexed。
- 全量 pytest **791 passed**；契约测试 11 passed；`node --check` 通过。
- 观察项：个别论文导入返回 `424 KB_IMPORT_FAILED`（新错误语义暴露的论文自身问题，非本次回归）。

## 越界检查（确认未触碰）

v1 索引逻辑、spec-012 双版本检索语义与召回归并、上传路径（`routes_kb.py`）、导入 CAS/并发/租约、下载安全策略、前端接口契约与 DOM id 均未被改动。

## 遗留（P2，非阻塞）

1. 后端：v2 置 `indexing` 失败无日志（可观测性增强）。
2. 前端：全部提交失败边角场景文案卡在 submitting（不影响主流程）。
3. 历史已导入论文 v2 仍 `pending`，可经 reindex 补救（非本次范围）。

## 结论

实现与 spec 一致，两 bug 根因已消除，运行时验收通过，无 P0/P1 → **技术评审通过**，同意收口。
