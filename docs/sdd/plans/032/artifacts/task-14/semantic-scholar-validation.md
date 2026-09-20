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
