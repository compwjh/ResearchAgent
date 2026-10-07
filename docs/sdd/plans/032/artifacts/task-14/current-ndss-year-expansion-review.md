# NDSS 2025 年度扩展独立后端复审

- 日期：2026-10-08（Asia/Shanghai）
- 角色：backend-reviewer
- 分支：`codex/spec032-final-acceptance`
- 复审范围：`current-ndss-year-expansion.md`、`backend/app/paper_discovery/infrastructure/ndss_paper_parser.py` 的实际 diff、`tests/paper_discovery/test_ndss_official_catalog.py` 的实际 diff、`tests/fixtures/ndss/official-accepted-papers-2025.html`；另只读核对了 NDSS `verified_years` 与现有 catalog runtime 的相关接缝。
- 约束：未修改业务代码、未写生产数据、未做全量回归、未部署、未发起外部网络请求。

## 结论

**有界通过（P0=0，P1=0，限于“2025 官方 accepted-papers listing adapter 切片”）。** 本次变更把 2025 官方列表 URL 加入受控映射，并用固定 HTML 样本证明 listing parser 能读取标题、作者、年份和官方详情页链接；没有伪造 DOI、摘要、关键词或 PDF，也没有把 2025 写入 `SourceRegistry.verified_years`。

该结论不等同于 2025 全年官网目录导入、详情字段覆盖、PDF 下载/入库或生产用户路径的 official-year 覆盖。当前 `CatalogSourceRuntime` 仍只把 2024 路由到 official，2025 在正常 runtime sync 中继续走 Crossref fallback；因此不得把本切片描述为“用户侧 NDSS 2025 官方优先已接通”。若本 Task 的验收要求正常 runtime 对 2025 也使用官方列表，则这是一个**条件性 P1**，需要补 runtime 接线和集成测试后再验收；按交接报告声明的 bounded adapter scope，本轮不将其记为已实现范围内缺陷。

## 核对结果

### 1. 2025 URL 受控

- `NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS`（`ndss_paper_parser.py:81-92`）只由固定的 `NDSS_OFFICIAL_HOST = "www.ndss-symposium.org"` 和常量路径组成：
  `https://www.ndss-symposium.org/ndss2025/accepted-papers/`。
- `NdssPublicationSource.discover_units()` 只从该映射取 URL；未知年份没有 official unit，不接受调用方传入任意根 URL。
- official `fetch_unit()` 只允许 `www.ndss-symposium.org`，关闭重定向，并在响应为 `%PDF-` 或 PDF content type 时拒绝；没有 GET/HEAD/Range PDF 探测。
- 2025 定向测试断言请求 URL 恰为映射值、只发出一次请求、返回 unit key `ndss:2025:official`，并记录 content hash/ETag。
- 该边界依赖内部 `SourceFetchUnit` 由 `discover_units()` 生成；本复审未将人工构造同 host 异路径的内部 unit 当成公开 URL 注入能力。若未来该 unit 可由外部输入，需再加 exact-path allowlist。

### 2. 没有伪造摘要、PDF 或身份字段

- `parse_official_catalog()` 明确只从 listing 页面写入 title、authors、year、container title、article URL；`doi=""`、`abstract=None`、`keywords=()`、`pdf_url=None`，并返回 `NDSS_OFFICIAL_ABSTRACT_MISSING` 与 `NDSS_OFFICIAL_KEYWORDS_MISSING` 告警。
- 2025 fixture 只包含 3 条真实列表片段的标题、作者和 `ndss-paper/` 详情链接；本地文件无 `abstract`、`pdf`、`doi` 文本，SHA-256 为：
  `75d77e4c5c4aff058e51d738a94e553f28960b5afa148e586584a03317e244d3`（2346 bytes）。
- parser 对详情链接执行 `https` + 官方 host 校验，不把详情页摘要/PDF探查结果混入 listing 记录。交接报告中的一次详情页观察没有被写入 fixture 或生产字段。
- OpenAlex/Crossref 的既有富化路径仍是另一条 metadata fallback；本 official 2025 `sync_year(route="official")` 分支不会调用 `enrich_records()`，所以本切片不会凭聚合摘要或 PDF 回填来伪装官网字段。

### 3. `verified_years` 没有被提前放行

- `backend/app/paper_discovery/infrastructure/source_registry.py:119-120` 中 NDSS `SourceEntry` 的 `verified_years` 仍为空 tuple；本次实际 diff 未修改该文件。
- 测试将 2023 official 请求保持为空/拒绝，只允许映射中已有 2024、2025；这证明 parser route 支持范围不被误报为可信年度覆盖。
- 因此不能据本切片宣称“NDSS 2025 已验证”“2021–2025 官方覆盖”或“全文可下载/已入库”。

### 4. 生产 runtime 接线边界

当前 `backend/app/paper_discovery/application/catalog_runtime.py:345-350` 仍是：NDSS 选中 2024 时使用 `route="official"`，其余所选年份（包括 2025）进入无 route 的 Crossref fallback。既有定向测试 `test_catalog_runtime_uses_ndss_official_2024_route_and_keeps_other_years_fallback` 也明确断言该行为。

所以本变更的真实能力是：受控 source adapter 可被显式调用 `sync_year(2025, route="official")`，而不是正常 catalog runtime 已自动优先使用 2025 官方目录。该差异已在本报告作为验收边界保留，不通过文档措辞掩盖。

## 定向验证

| 检查 | 命令 | 结果 |
|---|---|---|
| NDSS official/parser 定向回归 | `.venv/bin/python -m pytest -q tests/paper_discovery/test_ndss_official_catalog.py tests/paper_discovery/test_ndss_source_adapter.py` | 退出码 0；70 passed；0.37s |
| runtime 接缝边界 | `.venv/bin/python -m pytest -q tests/paper_discovery/test_catalog_runtime.py -k 'ndss_official_2024_route_and_keeps_other_years_fallback'` | 退出码 0；1 passed，10 deselected；0.90s |
| Ruff | `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/ndss_paper_parser.py tests/paper_discovery/test_ndss_official_catalog.py` | 退出码 0；All checks passed |
| Python 编译 | `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/ndss_paper_parser.py tests/paper_discovery/test_ndss_official_catalog.py` | 退出码 0 |
| diff 空白 | `git diff --check -- backend/app/paper_discovery/infrastructure/ndss_paper_parser.py tests/paper_discovery/test_ndss_official_catalog.py` | 退出码 0 |

测试均为本地 fixture/MockTransport，未请求外部官网；不能替代真实 2025 全目录、详情、身份对齐、PDF 安全下载或可信导入验收。

## 交接建议

- 当前可将本切片标为：**NDSS 2025 官方 listing adapter bounded PASS；`verified_years` 仍未验证**。
- 若只需要为后续受控 source 调用提供 2025 listing route，无需新增 schema、PDF 下载器或摘要 parser。
- 若用户验收需要 2025 在正常 `CatalogSourceRuntime` 中走 official，应由 backend-dev 单独补 `catalog_runtime` 的有界年度路由接线、离线 runtime 测试和 progress/persistence 证据；在此之前应保持 2025 Crossref fallback，并将 official-year 功能标为未接通。
- 若用户验收需要摘要/关键词/DOI/PDF 或完整年度可信覆盖，应另建有真实详情与导入证据的任务；不得由本 fixture 或一次详情页观察推断。

## Runtime 接线追加独立复审（2026-10-08 01:20 CST）

### 复审范围与依据

本追加复审针对 backend-dev 后续补上的 runtime 接线，读取并核对：

- [catalog_runtime.py](/Users/wjh/ResearchAgent/backend/app/paper_discovery/application/catalog_runtime.py:346)
- [ndss_paper_parser.py](/Users/wjh/ResearchAgent/backend/app/paper_discovery/infrastructure/ndss_paper_parser.py:87)
- 既有 [ndss_publication_source.py](/Users/wjh/ResearchAgent/backend/app/paper_discovery/infrastructure/ndss_publication_source.py:197) 的 official unit/fetch 安全边界
- [test_ndss_official_runtime.py](/Users/wjh/ResearchAgent/tests/paper_discovery/test_ndss_official_runtime.py:19)
- [test_catalog_runtime.py](/Users/wjh/ResearchAgent/tests/paper_discovery/test_catalog_runtime.py:207)
- `tests/fixtures/ndss/official-accepted-papers-2025.html`
- [source_registry.py](/Users/wjh/ResearchAgent/backend/app/paper_discovery/infrastructure/source_registry.py:119)

复审没有修改业务代码、测试代码或 schema，没有写生产数据，没有部署，也没有发起外部官网请求。

### 复审结论

**Runtime 接线 PASS（P0=0，P1=0）；仍是有界 official listing 能力，不是 `verified_years` 或全年覆盖放行。**

此前报告中“2025 正常 runtime 仍走 Crossref”的条件性 P1 已由这次接线实际消除：

1. `CatalogSourceRuntime.run()` 使用 `NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS` 的固定 key 作为 NDSS official route allowlist。选中 2025 时先调用既有 `source.sync_units({"years": [2025], "route": "official"})`，不会把 2025 放入 Crossref scope。
2. `NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS[2025]` 精确为 `https://www.ndss-symposium.org/ndss2025/accepted-papers/`。runtime 测试只允许该 URL，断言一次请求、官方 host、非 PDF 路径，并验证持久化 `ndss:2025:official` 与 3 条 fixture 记录。
3. 2023 不在固定映射中，组合 runtime 测试确认 2023 请求仍为 `api.crossref.org`，且持久化 unit 为 `ndss:2023`；同一请求中 2024/2025 分别是 `:official` unit。这证明 fallback 未被年度扩展吞掉。
4. `SourceRegistry` 的 NDSS `verified_years` 未改动，运行时断言仍为 `()`。官方 listing route 的可用性没有被误写成可信年度/全文导入门禁。

### 下载、安全与 schema 边界

- 本次业务 diff 只有 `catalog_runtime.py` 的 scope 分流和 parser URL 映射；没有改 `ndss_publication_source.py`、`source_registry.py`、下载器、导入器、域模型或公开 DTO/schema。
- 既有 official fetch 仍使用固定 unit URL、host allowlist、`follow_redirects=False`，并拒绝 PDF magic bytes/content type；2025 runtime 测试也断言没有 PDF 请求。没有新增详情页跟随、PDF 下载、重定向或新来源 host。
- 2025 parser 继续只写 listing 实际提供的 title/authors/year/container/article URL；DOI、abstract、keywords、pdf_url 保持缺失告警语义。runtime 只改变路由，不改变字段或持久化 schema。

### 定向验证

| 检查 | 命令 | 结果 |
|---|---|---|
| NDSS official/parser/source/runtime | `.venv/bin/python -m pytest -q tests/paper_discovery/test_ndss_official_runtime.py tests/paper_discovery/test_ndss_official_catalog.py tests/paper_discovery/test_ndss_source_adapter.py` | 退出码 0；71 passed in 0.37s |
| catalog runtime | `.venv/bin/python -m pytest -q tests/paper_discovery/test_catalog_runtime.py` | 退出码 0；11 passed in 1.00s |
| 目标源码与测试 Ruff | `.venv/bin/ruff check backend/app/paper_discovery/application/catalog_runtime.py backend/app/paper_discovery/infrastructure/ndss_paper_parser.py tests/paper_discovery/test_ndss_official_runtime.py tests/paper_discovery/test_catalog_runtime.py tests/paper_discovery/test_ndss_official_catalog.py` | 退出码 0；All checks passed |
| Python 编译 | `.venv/bin/python -m py_compile`（上述目标源码/测试文件） | 退出码 0 |
| diff 空白 | `git diff --check --`（上述 tracked 目标文件） | 退出码 0 |
| 年度门禁断言 | `.venv/bin/python -c '...NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS...; SourceRegistry().get("ndss").verified_years == ()...'` | 退出码 0；固定 URL 为 2024/2025，`verified_years=()` |

### 剩余边界

本次复审只通过“2025 受控 official listing 在正常 runtime 中接通”。2025 全年真实目录、详情摘要/关键词/DOI、PDF 安全下载与可信导入仍没有证据，因此 `verified_years` 继续保持空值是正确的；不能把本次 runtime PASS 表述为 NDSS 2025 全年覆盖或全文可用。未见需要阻断本次 runtime 接线的 P0/P1 缺陷。
