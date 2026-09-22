# Semantic Scholar 回退验证记录

日期：2026-09-21
分支：`fix/spec029-030-031-pipeline`
实现提交：`31ac3cd`

## 验证结果

| 项目 | 命令/动作 | 结果 |
|---|---|---|
| Academic Graph API probe | `curl -sS --max-time 15 'https://api.semanticscholar.org/graph/v1/paper/ARXIV:2403.11445?...'` | 当前环境 DNS 无法解析 `api.semanticscholar.org`；未伪造外部成功 |
| 适配器字段与错误 | `pytest -q tests/paper_discovery/test_semantic_scholar_adapter.py` | 4 passed |
| OA 回退进入统一导入 | `pytest -q tests/paper_discovery/test_semantic_scholar_import_fallback.py` | 1 passed |
| Worker Tool 回归 | `pytest -q tests/skills/test_paper_worker_tools.py` | 7 passed |
| 既有导入/解析链 | `pytest -q tests/paper_discovery/test_paper_import.py tests/paper_discovery/test_doi_resolver_import.py tests/paper_discovery/test_paper_import_batch_integration.py tests/paper_discovery/test_conference_pdf_download.py` | 105 passed，5 warnings |
| 静态与布局 | `ruff check ...`、`scripts/check_test_layout.py` | 通过 |

## 受控闭环

1. 候选已有 DOI/ArXiv ID，主 PDF 下载失败。
2. Semantic Scholar 适配器查询 `paper/{DOI|ARXIV}`，核对标题、作者和年份。
3. 只接受 `openAccessPdf.url` 且主机在既有固定 allowlist；arXiv 由来源注册表声明。
4. 将候选的 `pdf_url` 替换为 OA 地址，再次调用同一个 `paper_import.import_candidate`。
5. PDF 安全校验、去重、知识库写入、索引和补偿保持原实现。

## 未完成的外部证据

当前网络环境不能解析 Semantic Scholar API 域名，因此尚未记录真实 API 返回和真实下载文件。部署环境恢复网络后，应使用 `ARXIV:2403.11445` 或已知 DOI 做一次单篇低频 probe；若返回无 OA、未知主机或 401/403/429，应显示稳定失败状态并转人工下载/上传。

## 2026-09-22 运行时补充

- 18080 服务以 `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` 启动，`GET /api/health` 返回 HTTP 200，`paper_discovery_enabled=true`。
- `GET /api/papers/semantic-scholar/autocomplete?query=privacy&limit=1` 返回 HTTP 200 和一条候选；本次未把供应商响应原文写入日志或前端。
- 429 处理已统一到 OA 回退适配器和 Academic Graph 客户端：先采用合法数字 `Retry-After`，再与指数退避取较大值，单次最多等待 30 秒；网络异常不会复用上一轮响应的 `Retry-After`。
- 定向回归：72 passed、12 subtests；Ruff 通过。Spec032 的最终全量回归、四来源覆盖、导入恢复和收口仍由 Task14 负责，不能据此标记 Spec032 完成。
- SQLite 持久化验证：`test_semantic_scholar_catalog_persistence.py` 覆盖 `SourceFetchUnit`、目录论文、来源记录、字段 provenance 和重启后的 completed fetch-unit 命中；同一 query 的 bulk 请求只发生 1 次，35 项相关测试通过。

## 2026-09-22 Retry-After 隔离合同补充（Task 14）

本次仅补强 Semantic Scholar 适配器和 Academic Graph 客户端的重试合同测试，未修改业务代码。两条新增用例均固定请求序列：第一次返回带 `Retry-After` 的 429，第二次抛出网络异常，第三次成功；断言等待序列分别为 `[3.0, 2.0]` 和 `[4.0, 2.0]`。这证明上一轮 429 的供应商等待值不会跨响应复用，网络异常会按当前 attempt 使用指数退避（`backoff=1.0`、第二次尝试为 2 秒）。

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 定向 pytest | `.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_adapter.py tests/paper_discovery/test_semantic_scholar_metadata.py` | 0 | 23 passed |
| Ruff | `.venv/bin/ruff check tests/paper_discovery/test_semantic_scholar_adapter.py tests/paper_discovery/test_semantic_scholar_metadata.py` | 0 | All checks passed |
| 差异空白检查 | `git diff --check -- tests/paper_discovery/test_semantic_scholar_adapter.py tests/paper_discovery/test_semantic_scholar_metadata.py docs/sdd/plans/032/artifacts/task-14/semantic-scholar-validation.md` | 0 | 通过 |

决策依据：测试直接驱动两条真实重试路径（`httpx` 网络异常和 HTTP 429），并将 `Retry-After` 与指数退避分别设为可区分值，避免仅测试成功结果而漏掉等待合同。风险与阻塞：未发现本地测试阻塞；外部 Semantic Scholar DNS/API 可用性仍沿用上文记录，未伪造外部证据。本次未提交或推送。
