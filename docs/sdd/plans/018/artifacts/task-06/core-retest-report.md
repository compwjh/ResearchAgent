# Spec018 Task06 closure-core backend retest report

## 结论

- **Backend retest：PASS**。8 条固定 core 命令全部退出码 0；相关回归和排除 legacy 集成测试后的全部 `test_kb_*.py` 也全部通过。
- **Task06 closure / production cutover：NO-GO（流程状态阻塞）**。本次只测试，未修改 matrix；`upload-closure-matrix.json` 当前仍为 `review_status=baseline_frozen`，entry/test 状态仍由 matrix owner 收口，不能据此宣称最终 closure 已 verified。
- **测试阻塞：无**。本轮没有实现失败、过时测试或新增矩阵证据失败。

## 执行元数据与安全边界

- 角色：`backend-tester`
- 模型：线上 Luna high
- 时间：2026-09-10（Asia/Shanghai）
- Python：项目 `.venv/bin/python -m pytest`
- 真实资源：**全部命令均为否**——未读取或写入真实 `data/kb`，未连接真实 Qdrant，未启动或调用服务。
- 隔离证据：涉及 Qdrant 的测试使用 `FakeQdrant`、mock 或临时目录客户端；`data/kb` 相关断言均指向 `tmp_path`。测试结束后未执行 `--confirm-replace`、alias 切换或真实 collection 操作。
- 进展日志：[20260910-033643.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-033643.md)

## 8 条固定 core 命令

| Test ID | 命令 | 退出码 | 结果 | 真实 data/kb / Qdrant / 服务 |
|---|---|---:|---|---|
| T-OLD-ROUTES | `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py -k legacy` | 0 | 1 passed, 17 deselected | 否 |
| T-DELETE-TOMBSTONE | `.venv/bin/python -m pytest -q tests/test_kb_document_delete.py` | 0 | 3 passed | 否 |
| T-DIRECT-SYMBOLS | `.venv/bin/python -m pytest -q tests/test_kb_document_boundary.py` | 0 | 14 passed | 否 |
| T-CANDIDATE-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k destination` | 0 | 1 passed, 43 deselected | 否 |
| T-REINDEX-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_kb_document_reindex.py` | 0 | 4 passed | 否 |
| T-BACKGROUND-INVENTORY | `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py -k inventory` | 0 | 2 passed | 否 |
| T-STARTUP-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_kb_startup_generation_gate.py` | 0 | 3 passed | 否 |
| T-REBUILD-ZERO-WRITES | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py -k 'spy or dry_run or source_hash'` | 0 | 4 passed, 42 deselected | 否 |

## 相关回归

命令：

```text
.venv/bin/python -m pytest -q tests/test_kb_services.py tests/test_kb_tasks.py tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_routes.py
```

- 退出码：0
- 结果：**137 passed, 5 warnings, 4 subtests passed**
- 警告：仅 PyMuPDF/SwigPy* `DeprecationWarning`，未导致失败。
- 真实资源：否。

全部 `test_kb_*.py`（按 `rg --files tests | rg '(^|/)test_kb_.*\\.py$' | sort` 收集，共 22 个文件）执行时排除 `tests/test_legacy_kb_integration.py`：

- 退出码：0
- 结果：**378 passed, 5 warnings, 29 subtests passed**
- 真实资源：否。
- 额外输出：出现一次 `Failed to export span batch due to timeout, max retries or shutdown.` telemetry 警告；pytest 仍退出 0，未表明应用服务或真实 Qdrant 被调用。

## 阻塞与后续

本轮测试没有失败项，因此不存在需要按“实现失败 / 过时测试 / 矩阵证据问题”分类的失败。唯一阻塞是流程性：matrix 仍保持 baseline-frozen/open/pending，本报告不修改它，也不授予真实 Qdrant、alias/collection 写删、服务重启或生产切换资格。矩阵 owner 需依据本次报告更新事实状态并完成后续独立评审。
