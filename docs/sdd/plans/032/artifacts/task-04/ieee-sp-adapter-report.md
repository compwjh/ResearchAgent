# Task 04 — IEEE Symposium on Security and Privacy (S&P) 来源适配器报告

> 关联：[Spec 032](../../../specs/032-research-source-expansion.md) ｜ [Task 04](../../task-04-security-conference-adapters.md)
> 角色：backend-dev ｜ 日期：2026-09-14 ｜ source_id：`ieee-sp`

## 1. 实现内容

新增 2 个代码文件（照搬 `ccs_publication_source` / `ccs_paper_parser` 的 source+parser 分离范式）：

| 文件 | 行数 | 职责 |
|---|---|---|
| `backend/app/paper_discovery/infrastructure/ieee_sp_paper_parser.py` | 521 | 纯解析：Crossref work-list → 目录记录；OpenAlex work → 富化；字段级 provenance |
| `backend/app/paper_discovery/infrastructure/ieee_sp_publication_source.py` | 561 | 网络/条件抓取/翻页/富化编排/单元发现/health |

Source Adapter 合同实现（与 spec-032 一致）：

| 合同项 | 实现 |
|---|---|
| `source_id` / `source_kind` | `ieee-sp` / `ieee_sp`（全局唯一） |
| `authority_rank` | `2`（官方 DOI 元数据；官方会议页面 3 > DOI 2 > 聚合来源 1） |
| `discover_units(scope)` | 按年份产出单元，`unit_key="sp:2024"`、`fetch_unit_id="ieee-sp|sp|2024"`；范围非法抛 `IeeeSpUnitRejected`，不发请求 |
| `fetch_unit(unit, conditional_headers)` | ETag / Last-Modified / 内容 hash + 超时 + 304 未变化；429→`IEEE_SP_RATE_LIMITED`，≥400→`IEEE_SP_UNAVAILABLE` |
| `parse_catalog(response)` | 委托 `IeeeSpCatalogParser` |
| `normalize_identity(record)` | 复用 `normalize_doi` / `normalize_title`（DOI 优先，回退 `title:...|year`） |
| `health()` | 无网络、无副作用、无凭据 |
| `sync_year` / `sync_units` | 单年失败不影响其他年份；部分失败 → `status="partial"`，来源级 `error_code=None` |

**复用的既有符号**（无第二套实现）：
`openalex_enricher._abstract_from_inverted_index`（摘要倒排索引还原）、
`paper_discovery_normalization.normalize_doi` / `normalize_title`、
`core.url_security.validate_url`（DNS/内网隔离）、
`platform.observability.spans.utc_now`、领域模型 `SourceFetchUnit`。
未改动任何既有文件（`ccs_*` / `ieee_paper_parser.py` / `usenix_*` / `dblp_*` / 前端均未触碰）。

## 2. 实测数据（Crossref，rows=1000，第一页）

`query.bibliographic="IEEE Symposium on Security and Privacy {year}"`
`filter=member:263,type:proceedings-article,from-pub-date:{y}-01-01,until-pub-date:{y}-12-31`

| 年份 | 页面条目 | matched（主会容器） | 其中前置页（丢弃） | real（研究论文） | EuroS&P 误收（丢弃） |
|---|---|---|---|---|---|
| 2021 | 1000 | 124 | 9 | **115** | 111 |
| 2022 | 1000 | 154 | 7 | **147** | 119 |
| 2023 | 1000 | 206 | 8 | **198** | 153 |
| 2024 | 1000 | 270 | 9 | **261** | 147 |
| 2025 | 1000 | 266 | 10 | **256** | 156 |
| 合计 | 5000 | 1020 | 43 | **977** | 686 |

- **前置页过滤**：5 年共丢弃 43 条（每年 7–10 条），全部为 `Keynotes` / `Title Page` /
  `Author Index` / `Organizing Committee` / `Program Committee` / `External Reviewers` /
  `Table of Contents` / `Copyright (and Reprint Permissions)` / `Message from the ...`。
- **EuroS&P 排除**：5 年共 686 条 EuroS&P 主会/Workshop 条目（单年 111–156）被 `european` 规则挡掉；
  这些容器标题**同样包含** `symposium on security and privacy`，不排除就会污染 S&P。
- **翻页**：主会论文全部落在第一页（最多 270 < 1000），第 2 页 0 命中即停 → 每年 2 次 Crossref 请求。

> ⚠️ **与分派说明的数字不一致**：分派给出的 2025→422/376、2024→417、2023→359/310、
> 2022→273、2021→235/197 明显高于实测。已复核多种 query 变体
> （`no-year` / `prefix:10.1109` / `query.container-title` / 去掉日期过滤 / offset 翻页 0–3000），
> matched 恒为 2025→266、2021→124，无变化。据此判断分派数字来自更宽的匹配
> （如不要求 `symposium on security and privacy`，而用 `security and privacy`：2025 得 471 条，
> 但会混入 TrustCom/SPW/CSP）或不同时点。本适配器采用与 `ccs-paper-acquisition` SKILL
> 配置表完全一致的**精确**匹配，宁可少收不可混入，因此报告以可复现数字为准。

## 3. 摘要覆盖率（OpenAlex）

抽样 43 篇真实论文（2021–2025 各 5–12 篇）逐篇请求 `api.openalex.org/works/doi:{doi}`：

- **42/43 有摘要（≈98%）**；唯一缺失的 `10.1109/sp61157.2025.00083` 是 OpenAlex **404**（该篇未入库），
  不是 null 摘要。
- 摘要缺失时只降级该篇（`abstract` 保持 `None`、不写 `abstract` provenance），
  产生 `IEEE_SP_OPENALEX_NO_HIT` / `IEEE_SP_OPENALEX_UNAVAILABLE` 告警，**不**产生来源级错误。
- `best_oa_location.pdf_url` 多数为 `null`（IEEE 付费墙）：抽样中仅 `2025.00241` 有 OA PDF
  （`arxiv.org/pdf/2504.06552`）。`pdf_url` 仅作为元数据记录，**不**下载、**不**探测。

## 4. provenance 方案（字段级）

| 字段 | 来源 | 权威级别 |
|---|---|---|
| title / authors / year / doi / container_title / article_url | Crossref（IEEE member 263 自提交） | 2（官方 DOI） |
| abstract / keywords / pdf_url | OpenAlex | 1（聚合来源） |

- 每条记录 `provenance` 逐字段记录来源 id；Crossref 写入 6 个字段，OpenAlex 只在**字段为空且**
  现有来源权威**严格低于**写入来源时补写（`_may_write`）。
- 未知来源按**最高**权威处理：宁可少写一次，也不覆盖可能是官方页面的值。
- 因此官方会议页面（rank 3）写入的摘要/关键词/PDF 永不被 OpenAlex（rank 1）覆盖
  （`test_lower_authority_enrichment_never_overwrites_higher_authority_fields`）。

## 5. 与 ACM CCS 范式的关键差异

1. **member 263**（不是 ACM 的 320；也不是常被误用的 266）。
2. **必须排除 `european`**（EuroS&P 是另一个会议，容器标题同样命中）。
3. **前置页只能靠标题过滤**：IEEE 真论文 `page` 可能缺失或 `起==止`，**不能**用 CCS 的页数规则
   （两个真实反例 `10.1109/sp46214.2022.9833599` page 缺失、`10.1109/sp46215.2023.10179333`
   page=`2032-2032` 已进 fixture 并加断言）。
4. **`article_url` 取 Xplore 文档页**：Crossref `link[]` 指向
   `http://xplorestaging.ieee.org/...pdf`（http + staging + PDF），不采纳；
   只接受 `resource.primary.URL` 上的 `https://ieeexplore.ieee.org/document/<id>/`，否则回退 `doi.org`。

## 6. 测试与验证

- `tests/test_spec032_ieee_sp_source.py`：**63 passed**（全部离线，`httpx.MockTransport` + 假 DNS resolver）。
  覆盖：多年度、前置页过滤、**EuroS&P 排除**、兄弟会议排除、摘要缺失、container 漂移、
  页数异常真论文保留、provenance、条件抓取（ETag/304）、offset 翻页、单年失败隔离、health 无副作用。
- `tests/fixtures/ieee_sp/`：5 个真实 Crossref 样本（2021–2025，含前置页/EuroS&P/兄弟会议/页数异常真论文）
  + 3 个 OpenAlex 样本（1 个派生，README 已注明）+ `README.md`。
- 验证命令与结果：
  - `cd /Users/wjh/work/ResearchAgent-2/ResearchAgent && env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_ieee_sp_source.py -q --basetemp=/tmp/pt_sp_$RANDOM` → `63 passed`
  - `cd backend && env -u PYTHONPATH ../.venv/bin/python -m ruff check app/paper_discovery/infrastructure/ieee_sp_paper_parser.py app/paper_discovery/infrastructure/ieee_sp_publication_source.py` → `All checks passed!`
  - `env -u PYTHONPATH .venv/bin/python -c "import backend.app.paper_discovery.infrastructure.ieee_sp_publication_source"` → OK

## 7. 已知限制与后续

- **摘要覆盖率随 OpenAlex 波动**：IEEE S&P 抽样覆盖 ≈98%，但个别年份可能更低；适配器已按「缺摘要只降级该篇」处理。
- **未做全量回归**（按分派要求只跑定向 pytest）；`sync_units` 尚未接入上层 store（Task05）。
- **`no-abstract` fixture 为派生样本**（真实响应仅置 `abstract_inverted_index=null`），原因见 fixtures README；
  真实 404 路径由测试直接构造覆盖。
- **PDF 全部为付费墙**：`pdf_url` 常为 null 属正常，未做任何 PDF 下载/探测，符合 spec-032「明确不做」。
- `authority_rank` 暂用「官方 DOI 元数据」级别；若后续接入 IEEE 官方会议页面来源（rank 3），
  可直接复用本模块的 `merge_enrichment` 合并语义。
