# Spec015 Task08 旧 KB 集成回归切片

- 执行角色：初级开发（junior-dev）
- 执行模型：`gpt-5.6-luna`，high
- 执行日期：2026-09-05
- 关联任务：`docs/sdd/plans/015/task-08-tests-ranking-and-security.md`
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task08-legacy-kb-20260905.md`

## 范围与结论

**本切片通过；不替代 Task08 总体验收。**

新增 `tests/test_legacy_kb_integration.py`，只改测试文件，不修改生产代码。测试为每个用例创建临时 `papers.json`、临时论文目录和真实可读取 PDF；检索及重建使用内存 `FakeQdrant`，不调用公网、Ollama 或项目 `data/` 目录。

覆盖以下旧数据兼容行为：

1. 旧记录仅含 `file_name` 时，列表接口仍返回记录，并可通过 fake Qdrant 命中后完成 `/api/kb/ask`，引用保留旧文件名。
2. 旧 `{paper_id}.pdf` 物理文件可被真实解析并完成 v1 重建，向量 payload 仍绑定旧 `paper_id`；重建 API 正确提交指定 chunker。
3. 旧物理文件缺失时，重建 API 返回 404 且不提交任务。
4. `papers.json` 损坏时，列表接口安全降级为空列表。
5. 旧记录与同展示名的新命名记录并存时，删除旧记录只删除旧物理文件、旧元数据和旧向量，不删除新记录/新文件。

## 验证结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 新增集成测试 | `.venv/bin/python -m pytest -q tests/test_legacy_kb_integration.py` | `5 passed, 5 warnings` |
| KB 专项回归 | `.venv/bin/python -m pytest -q tests/test_kb_services.py tests/test_kb_routes.py tests/test_kb_tasks.py tests/test_kb_ask_trace.py tests/test_kb_chunkers.py tests/test_kb_normalize.py tests/test_kb_observability.py tests/test_kb_reranker.py tests/test_legacy_kb_integration.py` | `198 passed, 5 warnings, 29 subtests passed` |
| 全量回归 | `.venv/bin/python -m pytest -q` | `525 passed, 1 skipped, 5 warnings, 38 subtests passed` |
| 空白检查 | `git diff --check -- tests/test_legacy_kb_integration.py` | 通过 |
| 冲突标记 | `rg -n '^<<<<<<<|^>>>>>>>|^=======$' tests/test_legacy_kb_integration.py` | 0 命中 |

全量测试中的 1 个跳过项与本切片无关；既有观测导出在测试环境尝试连接本机 3000 端口并失败，但不影响 pytest 退出码和断言结果。

## 未覆盖与后续边界

本切片不宣称真实 Qdrant、真实公开 PDF、真实浏览器 GUI、ACM/IEEE 登录或排序质量 A14 已通过；这些仍由 Task08 总体验收处理。删除路由的向量删除动作通过 fake Qdrant 替身验证调用隔离，未连接外部服务。
