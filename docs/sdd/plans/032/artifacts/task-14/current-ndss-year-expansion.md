# Spec032 Task07 NDSS 官方年度扩展（2025）— backend-dev 交接报告

- 日期：2026-10-08（Asia/Shanghai）
- 分支：`codex/spec032-final-acceptance`
- 角色：backend-dev（本次未提交）
- 结论：**有界通过（2025 官网目录切片）**；不等同于 2025 全年导入、全文覆盖或四年度覆盖验收。

## 范围与安全边界

本次只扩展 NDSS 官方 accepted-papers 列表路由，复用既有
`NdssPublicationSource.discover_units/fetch_unit/sync_year` 与
`parse_official_catalog`。没有新增来源、缓存、下载链或公开字段；没有请求 PDF，
没有批量同步；没有修改 `source_registry.py` 的 `verified_years`、host allowlist、
API schema、前端、env 或其他 agent 文件。2021–2023 的官网 URL 未猜测、未添加。

## 官方真实证据

1. 列表页（一次受控 GET）：
   - URL：<https://www.ndss-symposium.org/ndss2025/accepted-papers/>
   - 时间：2026-10-08 00:58 CST（响应头：Wed, 07 Oct 2026 16:58:49 GMT）
   - HTTP 200；228875 bytes
   - 完整响应缓存 SHA-256：
     `0be2d22e74a39b49a1a87b2117962caec75d1d32e0466fa5a3718a454d8132ff`
   - 现有解析器对缓存完整页解析出 213 条记录；这是解析观察值，不是已导入或验收覆盖声明。

2. 详情页（从列表真实 href 选一条，最多一条详情 GET）：
   - URL：
     <https://www.ndss-symposium.org/ndss-paper/who-is-trying-to-access-my-account-exploring-user-perceptions-and-reactions-to-risk-based-authentication-notifications/>
   - 时间：2026-10-08 00:59 CST；HTTP 200；71482 bytes
   - HTML SHA-256：
     `e552f5d2bcfae859e766f54db6e53b23dc8cd6cad022fc780e759ee301e8c403`
   - 列表首条标题与详情页 `h1` HTML 规范化后完全一致；详情页含摘要和 PDF 链接。PDF 链接未跟随、未下载。
   - 现有 NDSS parser 没有详情 HTML 解析入口，因此没有擅自新增第二套 detail 流程。

3. 固定真实 HTML 样本：
   - 路径：[official-accepted-papers-2025.html](/Users/wjh/ResearchAgent/tests/fixtures/ndss/official-accepted-papers-2025.html)
   - 来源：上述官方列表页中的真实连续 HTML 片段，含 3 条真实标题、作者和详情 href；是 bounded subset，不是 228875-byte 完整快照。
   - 2346 bytes；SHA-256：
     `75d77e4c5c4aff058e51d738a94e553f28960b5afa148e586584a03317e244d3`

## 实现变更

- [ndss_paper_parser.py](/Users/wjh/ResearchAgent/backend/app/paper_discovery/infrastructure/ndss_paper_parser.py:87)
  - 在 `NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS` 增加已实证的 2025 listing URL。
  - 注释明确该映射是官网 listing 路由证据，不是 SourceRegistry 的可信全文/年度导入门禁。
- [ndss_publication_source.py](/Users/wjh/ResearchAgent/backend/app/paper_discovery/infrastructure/ndss_publication_source.py:197)
  - 无代码改动；现有 official route 已正确复用 SourceFetchUnit 的 year、content hash、ETag 和 PDF 拒绝边界。
- [test_ndss_official_catalog.py](/Users/wjh/ResearchAgent/tests/paper_discovery/test_ndss_official_catalog.py:75)
  - 增加 2025 fixture 解析、内容 hash、official route 无 PDF probe、2024/2025 allowlist 与 2023 不发明断言。

官网 listing 只证明 title/authors/year/container/article URL；本切片对 DOI、abstract、keywords、pdf_url
仍保持空值和缺失告警。详情页虽有摘要，但没有在本 Task 中导入，避免把一次详情探查误报为年度字段覆盖。

## 验证结果

| 检查 | 命令 | 结果 |
|---|---|---|
| NDSS 定向回归 | `.venv/bin/python -m pytest -q tests/paper_discovery/test_ndss_official_catalog.py tests/paper_discovery/test_ndss_source_adapter.py` | exit 0；70 passed |
| Ruff | `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/ndss_paper_parser.py backend/app/paper_discovery/infrastructure/ndss_publication_source.py tests/paper_discovery/test_ndss_official_catalog.py` | exit 0；All checks passed |
| 编译 | `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/ndss_paper_parser.py backend/app/paper_discovery/infrastructure/ndss_publication_source.py tests/paper_discovery/test_ndss_official_catalog.py` | exit 0 |
| diff 空白检查 | `git diff --check -- <上述生产/测试文件>` | exit 0 |

基线为 official 5 passed、NDSS adapter 63 passed；增加 2025 测试后合计 70 passed。

## 覆盖判定、风险与下一步

- 已证明：2025 官方 accepted-papers 列表可读；现有 parser 可解析该页结构；固定 3 条样本的标题、作者、年份、官方详情链接和字段缺失语义；单元可持久化 2025 year/hash/ETag。
- 未证明：2025 全年真实目录导入、每篇详情摘要/关键词、DOI 对齐、PDF 可信下载/入库；也未证明 2021–2023 官网年度目录。Crossref fixture/解析能力不能替代官网年度证据。
- 因此 `verified_years` 仍不应加入 2025，NDSS 仍不能对用户宣称可信全文覆盖或四年度覆盖。
- P1 风险：详情 HTML 与 listing HTML 是两种结构；当前 parser 仅支持 listing。若产品要求摘要补齐，下一项最小 backend-dev 工作应限定为：
  1. 固定上述详情页为 `tests/fixtures/ndss/official-paper-2025-first.html` 并记录 URL/日期/hash；
  2. 在 `backend/app/paper_discovery/infrastructure/ndss_paper_parser.py` 增加只读 detail parser（仅写入页面实际提供的 title/authors/year/abstract/provenance，不生成 DOI/keywords/PDF）；
  3. 在既有 `fetch_paper_detail` 入口 [tool_dispatch.py](/Users/wjh/ResearchAgent/backend/app/skills/tool_dispatch.py:385) 做 NDSS 路由前先补契约评审，并用 `tests/paper_discovery/test_fetch_paper_detail_dispatch.py` 的离线 MockTransport 模式增加 NDSS 正/负例；不得跟随页面中的 PDF href。
  4. detail 证据和受控导入稳定后，再单独评估 registry 年度门禁；不能由本 listing slice 直接放行。

## 交接与耗时

- 代码/fixture：见上方路径；未提交、未部署。
- 日志：[20261008-005800.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-07/backend-dev/20261008-005800.md)
- 受控网络缓存仅在 `/private/tmp`，未写入仓库。
- 处理时间：约 6 分钟（00:57:46–01:03:40 CST）。

## Runtime 接线补充（2026-10-08，backend-dev）

后续复审发现原实现只在 `CatalogSourceRuntime` 中把 2024 分流到 official，2025 虽可由 `NdssPublicationSource.sync_year(route="official")` 直接调用，但正常 runtime sync 仍会走 Crossref。现已做最小接线：

- `backend/app/paper_discovery/application/catalog_runtime.py` 复用 `NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS` 的年份 key 作为 NDSS official route allowlist；当前只包含 2024、2025。
- 选中 NDSS 2024/2025 时，runtime 先调用既有 `sync_units({"years": [...], "route": "official"})`，因此 2025 请求固定 `https://www.ndss-symposium.org/ndss2025/accepted-papers/`，沿用原 host/PDF 拒绝、ETag、content hash、`ndss:2025:official` unit 和既有 SQLite 持久化。
- 未在 `NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS` 中的年份（如 2023）仍进入原 Crossref fallback；未修改其他来源、host、`verified_years`、缓存 schema 或下载链。
- 新增按功能命名的 `tests/paper_discovery/test_ndss_official_runtime.py`，并扩展 runtime 集成测试覆盖 2024/2025 official + 2023 fallback。先运行红灯后再实现：红灯 `1 failed`，实现后 runtime 定向 `2 passed`。

该接线只证明受控 runtime 路由和列表单元可用，不改变“2025 全年目录/详情/PDF/可信导入未验证”的结论；`SourceRegistry.verified_years` 仍为空，不得据此宣称年度覆盖已放行。
