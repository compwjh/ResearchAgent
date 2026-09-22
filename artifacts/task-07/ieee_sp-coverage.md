# Spec032 Task07：IEEE S&P 官网目录覆盖证据

## 结论

- 状态：PARTIAL_GO（仅 2024 官网固定样本可验证）
- 官方入口：<https://sp2024.ieee-security.org/program-papers.html>
- 固定样本：tests/fixtures/ieee_sp/official-program-papers-2024.html
- 样本 SHA-256：8451c8a7add62768828e693f11c8fc4909251a40ab7f994cd301d4083569781d
- 采集边界：目录阶段只抓 HTML；不对 PDF 发 GET/HEAD/Range，也不把发现 URL 视为下载成功。

## 2024 固定样本统计

| 指标 | 数值 |
|---|---:|
| 官方页面/样本 | 1 / 1 |
| 解析记录 | 3 |
| 摘要缺失 | 3（官方页面未提供，稳定 warning） |
| 关键词缺失 | 3（官方页面未提供，稳定 warning） |
| PDF 候选 | 0（目录阶段不探测 PDF） |
| 正确下载 / 入库 | 0 / 0（留给 ConferencePdfDownloader 与后续 Task08） |

标题、作者、年份、container title、官网页面 URL 的 provenance 为 canonical
ieee_sp；DOI、摘要、关键词、PDF 保持空值，后续 Crossref/OpenAlex 只能 fill-if-missing。
单元为 sp:2024:official，保存 ETag/Last-Modified 与 HTML content hash。

## 年份覆盖

- 已验证：2024（固定官方页面样本，3 条记录）
- 未验证：2021、2022、2023、2025；不能由 MIN_YEAR/MAX_YEAR 推断成功
- 代码只注册 2024 官方 URL；未注册年份显式返回空单元/IEEE_SP_UNIT_REJECTED

## 验证命令

    .venv/bin/python -m pytest tests/test_spec032_task07_official_catalog.py tests/test_spec032_ieee_sp_source.py tests/test_spec032_task06_contract.py -q
    76 passed in 0.55s (exit 0)
    .venv/bin/ruff check backend/app/paper_discovery/infrastructure/ieee_sp_paper_parser.py backend/app/paper_discovery/infrastructure/ieee_sp_publication_source.py tests/test_spec032_task07_official_catalog.py
    All checks passed (exit 0)
    .venv/bin/python -m compileall -q backend/app/paper_discovery/infrastructure/ieee_sp_paper_parser.py backend/app/paper_discovery/infrastructure/ieee_sp_publication_source.py tests/test_spec032_task07_official_catalog.py
    exit 0
    git diff --check
    exit 0

## 风险与后续

2024 官网 accepted-paper 页面没有 DOI/摘要/关键词/逐篇 PDF 链接，无法在本任务内证明年度下载/入库覆盖；
Task08 仍需把官方记录与 Crossref/OpenAlex 合并并调用既有安全下载链。若官网 HTML 结构变化，解析器应返回稳定错误，
而不是静默把空目录视为成功。
