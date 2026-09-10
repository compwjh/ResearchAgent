# Task06 canonical metadata statistics 修复报告

## 结果状态摘要

`PASS（隔离回归）`。候选索引构建在两个 chunker 都成功后，会把本次成功解析/构建得到的页数、v1/v2 point 计数和 source hash 状态写入 finalize staging metadata；只有候选校验通过后，既有 `FinalizeBundleStore` 的 marker-last 流程才会把 staging metadata 发布到正式 `data/kb/papers.json`。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 在 `_build()` 完成 v1/v2 后更新 `_finalize_metadata` 内存副本。
  - PDF 的 `page_count` 取 provenance 页数；Markdown 保持 `null`。
  - 顶层 `chunk_count` 取 v1 count；v1/v2 均写入 `status=indexed`、各自 count、`progress=100`、`error=null`。
  - 成功构建后写入 `indexed_source_sha256=source_sha256`、`source_hash_state=verified`。
  - 保留 title、identity、stored_name、source_sha256 等已有字段；build 失败时不调用 staging/finalize，不提前写正式 metadata。
- `tests/test_kb_candidate_rebuild.py`
  - 新增双页 PDF staging/最终 metadata 回归测试，验证两个 metadata 副本一致、页数和 chunk 计数与候选 points 一致、source hash 已核对。
  - 更新 legacy source-hash finalize 断言以匹配成功重建后的 verified 语义。

## 测试命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py::test_successful_finalize_stages_and_publishes_metadata_stats` | 0 | 1 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py` | 0 | 70 passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 决策依据

- `_finalize_metadata` 是 finalize 的运行时 staging 副本；`FinalizeBundleStore.stage()` 只在 `_validate()` 全部通过后调用，正式 metadata 由 commit 的 marker-last 协议发布。
- provenance 对象提供 PDF `pages`；bundle 提供成功构建的 chunks，但 v1/v2 的最终计数以 `expected[document_id][chunker]["chunk_count"]` 为准，与候选点构建使用同一批 points。
- 顶层兼容计数沿用既有约定取 v1，避免改变现有 API 语义；用户字段不从解析器或 bundle 重建，保持原值。

## 风险、停止条件与未执行项

- 本任务没有执行真实 `--confirm-replace`，没有修改生产 Qdrant、正式索引或用户数据。
- 真实重建仍应在服务停止、Qdrant 锁释放的维护窗口执行；成功后检查正式 metadata 与 generation marker 的 digest 一致。

## 主 Agent 后续动作

1. 复核本报告及限定文件 diff，与 Task06 其他修复一并纳入同一提交。
2. 清理此前失败的候选运行后，在服务停止的维护窗口重新执行真实重建。
3. 成功后检查正式 metadata 的 `page_count`、v1/v2 counts、`indexed_source_sha256` 与 `source_hash_state`，再启动服务做运行时验证。

## 时间、模型与工具统计

- 开始：2026-09-10 17:56（Asia/Shanghai）
- 结束：2026-09-10 18:03（Asia/Shanghai）
- 总耗时：约 7 分钟
- 模型：临时分派 Luna xhigh（backend-dev）
- Token 统计：当前工具环境未提供精确 token 用量
- 工具统计：读取、补丁、测试与静态检查若干次

## 进展日志

`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-175629.md`
