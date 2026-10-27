# Spec043 Task11 后端分页阶段独立测试

日期：2026-10-28  
角色：Backend Tester  
基线：`ee836345`  
范围：分页 preview create/load-more 阶段影响的四个 literature_maps 后端测试领域。测试数据库由 `tmp_path` 隔离，分页与扩展测试使用 fake Semantic Scholar client，不访问真实来源。

## 验收结果

- 定向后端测试：PASS — 36/36 passed，0 failed，0 skipped；未采集覆盖率。
- 构建、类型、lint、安全扫描、全量回归、真实 API、真实来源网络、部署：本次未运行；不作为本报告通过项。
- 阻塞项：无。

## 执行记录

命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_preview_pagination.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_schema_migrations.py
```

退出码：0；结果：36 passed in 1.91s；失败 0；跳过 0。

覆盖范围包括：分页 create/load-more 请求 schema 与序列化、命令幂等和 revision CAS、并发单飞、cursor 推进与身份去重、空页/未知 total/cursor 循环、500 个唯一候选上限、失败页保留和显式 retry、owner/map/seed 校验、迟到 worker 与 lease 终态、重启后 typed recovery，以及与既有扩展预览和 v8 schema migration 的回归。

未运行全量 pytest 或全量 collection；未调用外网或真实数据库。本报告只确认上述四个测试文件的定向结果。

进展日志：[backend-tester 日志](../../../.codebuddy/agent-logs/spec-043/task-11/backend-tester/20261028-012019.md)。

## P1 坏页缓存修复：独立窄复验（最终候选）

本轮只补跑两个新增 cache 回归和一个既有 429 保留用例，不重跑原 36 项集合或全量 collection。以下测试均使用 `tmp_path` SQLite 与 scripted fake client。

| 测试 | RED / GREEN 记录 |
|---|---|
| `test_explicit_retry_bypasses_existing_bad_page_cache_and_refreshes_only_that_page` | RED（开发阶段修复前记录）：失败页重试再次命中 offset=50 的坏缓存，fake provider 未收到重试请求，预览仍失败。GREEN（本轮独立复验）：通过；排队重试只清目标失败 offset 缓存，保留 offset=0 成功缓存；provider 返回修正页后只请求该页，推进游标校验通过后才把该页写入缓存。 |
| `test_valid_page_cache_survives_finish_crash_and_recovery_reuses_it` | GREEN（本轮独立复验）：通过；通过校验的页即使 finish 前 lease 过期，恢复也复用该有效页缓存完成提交，没有再次请求 provider。 |
| `test_failed_page_preserves_candidates_and_only_explicit_retry_reuses_failed_cursor` | GREEN（本轮独立复验）：通过；429 失败保留既有候选和 next cursor，只允许显式重试失败 offset。 |

命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_preview_pagination.py::test_explicit_retry_bypasses_existing_bad_page_cache_and_refreshes_only_that_page tests/literature_maps/test_map_preview_pagination.py::test_valid_page_cache_survives_finish_crash_and_recovery_reuses_it tests/literature_maps/test_map_preview_pagination.py::test_failed_page_preserves_candidates_and_only_explicit_retry_reuses_failed_cursor
```

退出码：0；结果：3 passed in 0.98s；失败 0；跳过 0。RED 为开发阶段修复前记录，本轮独立运行只验证最终候选 GREEN。
