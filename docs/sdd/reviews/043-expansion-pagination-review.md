# Spec043 Task11 后端分页阶段评审

- 评审者：backend-reviewer
- 模型：临时 Luna xhigh
- 分派方式：主会话多 Agent 分派
- 日期：2026-10-28
- 范围：分页阶段 backend/** 与后端测试；对照已确认接口合同 §1、§2 的创建/续页条款及 §5 worker 生命周期。未评审 revalidate、batch-apply、expand_batch metadata 等后续阶段。

## 发现

### [HIGH / P1] 游标校验失败后，显式重试会重复读取 24 小时缓存的坏页

文件：`backend/app/literature_maps/application/service.py:1565`（缓存写入）、`407-415`（游标循环判定）；失败页重试复用 cursor 的位置：`backend/app/literature_maps/infrastructure/store.py:2113-2116`。

问题：`_cached_graph_request` 收到可解析的成功响应后，会在 `run_preview_page` 校验 `next_offset` 是否推进/循环之前，将整页写入请求缓存。若响应游标不前进或循环，worker 会把页标记为 `SEMANTIC_SCHOLAR_CURSOR_CYCLE` 失败；用户随后使用 `retry_failed=true` 时，重试仍请求同一 offset，因此命中同一缓存项，再次失败且不会访问来源。该成功响应缓存 TTL 为 86400 秒，用户在此期间无法通过显式重试获取更新后的来源页。

复现：临时 SQLite 与 scripted client 返回 offset 0 的正常页，随后 offset 50 的页仍返回 `next_offset=50`。首次续页失败后，用 `retry_failed=true` 重试；来源调用记录保持 `[(..., 0), (..., 50)]`，没有新的 offset 50 请求，预览仍为 `failed / SEMANTIC_SCHOLAR_CURSOR_CYCLE`。未修改仓库测试文件或真实数据库。

修复建议：对游标循环/不前进等分页层校验失败的响应，删除或标记该 offset 的缓存项；也可让显式失败页重试绕过该缓存。保留有效响应在 worker 崩溃后的缓存复用能力。

## 已核对项

- 创建分页预览只接受 references/citations 和冻结的 50/500 参数；旧非分页预览路径保持原样。owner/map/seed 的请求校验及服务端 cursor 持久化均存在。
- `load-more` 同一幂等键同参数在旧 preview revision 检查前重放原命令；异参冲突；不同键并发由事务状态 CAS 保证单预览最多一个在途页。
- 候选去重、loaded_count、next_cursor、分页状态与 token 校验后的 job finish 在同一 SQLite 事务提交；空页带后续 cursor 会推进，total 未知可保留为 null，500 唯一候选触发 capped。
- 来源错误保留既有候选和 next_cursor，failed_cursor 仅允许显式重试；种子在请求期间被移除时，完成事务不会提交候选或游标。
- lease 过期后的迟到 worker 不能写领域结果；重启通过 preview_page typed handler 恢复，不走通用建图 run_job。

## 定向验证

执行命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_preview_pagination.py \
  tests/literature_maps/test_map_expansion.py \
  tests/literature_maps/test_map_auxiliary_jobs.py \
  tests/literature_maps/test_map_schema_migrations.py
```

结果：36 passed。另用临时 SQLite/scripted client 验证游标循环后的 `retry_failed=true` 命中同一坏缓存且不发新请求。未运行全量测试、未访问外网或模型、未启动/部署服务。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | fail |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: WARNING — 修复 1 个 HIGH 问题后复审。未覆盖后续 handler/API 阶段。

## 窄复审最终结论：坏页缓存重试修复

复核范围仅限原 P1：显式失败页重试是否清除对应坏缓存、validated page 是否仍可在 finish 崩溃后复用，以及同键幂等重放是否会重复清缓存。

- `queue_preview_page` 在事务中先解析幂等重放，只有新建且通过状态、revision、failed cursor 校验的显式重试才删除传入的单一失败页 cache key（`backend/app/literature_maps/infrastructure/store.py:2102-2133`）。因此同键重放不会再次执行删除；不同参数复用该键仍按幂等冲突处理。
- `run_preview_page` 延迟新鲜页写缓存，待 offset、候选数量、cursor 推进/循环及 total 校验完成后才写入；已验证的页仍会在领域 finish 前缓存，以支持合法的崩溃恢复复用（`backend/app/literature_maps/application/service.py:388-433`）。
- 显式重试回归确认旧坏页被绕过、来源 offset 只重新请求一次、只刷新该页缓存且保留首页面缓存。另以临时 SQLite/scripted client 检查同键重放：队列后放入该页缓存，再重放同一请求，缓存保持存在且响应与首次排队结果相同。

定向测试命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_preview_pagination.py::test_repeated_source_cursor_fails_without_advancing_or_losing_prior_candidates \
  tests/literature_maps/test_map_preview_pagination.py::test_explicit_retry_bypasses_existing_bad_page_cache_and_refreshes_only_that_page \
  tests/literature_maps/test_map_preview_pagination.py::test_valid_page_cache_survives_finish_crash_and_recovery_reuses_it \
  tests/literature_maps/test_map_preview_pagination.py::test_preview_pages_use_server_cursor_and_dedupe_even_when_page_is_empty
```

结果：4 passed。临时 SQLite 幂等重放检查通过。未运行全量测试、未访问外网或模型、未启动/部署服务。

最终结论：原 P1 已修复并通过上述窄复核，分页阶段评审结论更新为 **PASS**。本结论仅关闭坏页缓存重试问题，不扩展到后续 batch/revalidate/metadata 阶段。
