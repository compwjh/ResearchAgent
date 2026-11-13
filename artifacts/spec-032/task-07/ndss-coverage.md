# Spec032 Task07：NDSS 官网目录覆盖证据

## 结论

- 状态：PARTIAL_GO（仅 2024 官网固定样本可验证）
- 官方入口：<https://www.ndss-symposium.org/ndss2024/accepted-papers/>
- 固定样本：tests/fixtures/ndss/official-accepted-papers-2024.html
- 样本 SHA-256：`9291d34e821196694fbf19222c2130ee2cc972d65bef5d99c99b18124d007929`
- 样本性质：基于官方页真实可核验条目的受控 bounded subset（3 条），不是完整原始页面快照；不代表 2024 年度全量。
- 采集边界：目录阶段只抓 HTML；不对 PDF 发 GET/HEAD/Range，也不把页面中的下载地址视为下载成功。

## 2024 固定样本统计

| 指标 | 数值 |
|---|---:|
| 官方页面/样本 | 1 / 1 |
| 解析记录 | 3（受控固定样本子集，不代表年度全量） |
| 摘要缺失 | 3（官方 accepted-papers 页面未提供，稳定 warning） |
| 关键词缺失 | 3（官方 accepted-papers 页面未提供，稳定 warning） |
| DOI / PDF 候选 | 0（官网固定样本不提供；目录阶段不探测 PDF） |
| 正确下载 / 入库 | 0 / 0（留给安全下载链及后续 Task08/Task10） |

标题、作者、年份、container title、官网页面 URL 的 provenance 为
`ndss`（官方路由由 `ndss:2024:official` 单元区分）；DOI、摘要、关键词、PDF 保持空值，后续 Crossref/OpenAlex 只能
fill-if-missing 并保留真实聚合 provenance。

单元为 `ndss:2024:official`，保存 ETag/Last-Modified 与 HTML content hash；
官方路由拒绝非白名单主机和 PDF 响应。

## 年份覆盖

- 已验证：2024（官方 accepted-papers 固定样本，3 条记录）
- 未验证：2021、2022、2023、2025；不能由 MIN_YEAR/MAX_YEAR 或 Crossref 年份结果推断成功
- Task08 交接：runtime 对 NDSS 2024 使用 `route=official`；其它年份继续使用 Crossref fallback。

后续必须先隔离 accepted-paper 列表与详情摘要链、固定允许主机及 FetchUnit/hash；
其余年度继续保留现有 Crossref/OpenAlex fallback，不伪造 NDSS 官方年度覆盖。

## 验证命令

    .venv/bin/python -m pytest tests/test_spec032_task07_ndss_official.py tests/test_spec032_ndss_source.py -q
    68 passed (exit 0)
    .venv/bin/ruff check backend/app/paper_discovery/infrastructure/ndss_paper_parser.py backend/app/paper_discovery/infrastructure/ndss_publication_source.py tests/test_spec032_task07_ndss_official.py
    All checks passed (exit 0)
    .venv/bin/python -m compileall -q backend/app/paper_discovery/infrastructure/ndss_paper_parser.py backend/app/paper_discovery/infrastructure/ndss_publication_source.py tests/test_spec032_task07_ndss_official.py
    exit 0
    git diff --check
    exit 0
